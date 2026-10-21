"""M5B B1: loss-aware, session-isolated *native* Frozen V3.0 streaming adapter.

No alternate thresholds, synthetic task clusters, full-session extension, or Android gating.
Legacy context MUST come from a trusted offline runner, never an untrusted client.
"""
from __future__ import annotations

import hashlib
import json
import math
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

NATIVE_START, NATIVE_STOP = 11, 16
MAX_POINTS = 100_000
MAX_COORD = 100_000
MAX_GAP_US = 300 * 1_000_000  # configurable policy cap; NOT a change to native scoring

class MonitorError(Exception):
    pass


def _sha_json(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _validate_gesture(points: Any) -> List[Dict[str, Any]]:
    if not isinstance(points, list) or not 2 <= len(points) <= MAX_POINTS:
        raise MonitorError('INVALID_GESTURE: expected 2..100000 points')
    out = []
    for i, p in enumerate(points):
        if not isinstance(p, dict):
            raise MonitorError(f'INVALID_POINT: index={i}')
        t = p.get('t_us', p.get('timestamp_us'))
        if isinstance(t, bool) or not isinstance(t, int) or t < 0:
            raise MonitorError(f'INVALID_TIMESTAMP: index={i}; integer microseconds required')
        xy = []
        for name in ('x', 'y'):
            val = p.get(name)
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or abs(val)>MAX_COORD:
                raise MonitorError(f'INVALID_{name.upper()}: index={i}')
            xy.append(float(val))
        if out and t < out[-1]['t_us']:
            raise MonitorError(f'NONMONOTONIC_TIMESTAMP: index={i}')
        out.append({'t_us': t, 'x': xy[0], 'y': xy[1]})
    if out[-1]['t_us'] <= out[0]['t_us']:
        raise MonitorError('INVALID_GESTURE: zero duration')
    return out


def _native_record(gestures: List[List[Dict[str, Any]]], ctx: Dict[str, str]) -> Dict[str, Any]:
    """Same projection as validated V3 Window pilot; preserve *full prefix* g1..gN.

    Rebase only at first session event; do NOT rebase each gesture or local-window.
    """
    zero = gestures[0][0]['t_us']
    native = []
    for gesture in gestures:
        native.append([SimpleNamespace(x=p['x'], y=p['y'],
                                       timestamp_us=p['t_us']-zero, t_us=p['t_us']-zero)
                       for p in gesture])
    return {'participant': ctx['participant'], 'session_id': ctx['session_id'],
            'group': ctx.get('group', ''), 'gestures': native}


@dataclass
class _Session:
    token: str
    ctx: Optional[Dict[str, str]]
    detector: Any = None
    gestures: List[List[Dict[str, Any]]] = field(default_factory=list)
    digests: Dict[int, str] = field(default_factory=dict)
    cached: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    first_ask_hold_g: Optional[int] = None
    first_intervene_g: Optional[int] = None
    integrity_flag: bool = False
    quarantined: bool = False
    ended: bool = False
    end_reason: Optional[str] = None
    started_mono_ns: int = field(default_factory=time.perf_counter_ns)
    last_mono_ns: int = field(default_factory=time.perf_counter_ns)


class RuntimeMonitor:
    """One detector instance per trusted session, NEVER per gesture.

    Isolated sessions are serialized under the runtime lock for correctness in B1.
    Performance optimization/pooling is a separate validated change.
    """
    def __init__(self, manifest_sha: str = 'UNVERIFIED', detector_factory: Optional[Callable[[], Any]] = None,
                 max_gap_us: int = MAX_GAP_US, idle_timeout_sec: Optional[float] = 300.0):
        if not isinstance(max_gap_us, int) or max_gap_us < 1:
            raise ValueError('max_gap_us must be positive integer')
        self.manifest_sha = manifest_sha
        self.max_gap_us = max_gap_us
        if idle_timeout_sec is not None and (not isinstance(idle_timeout_sec,(int,float)) or idle_timeout_sec <= 0):
            raise ValueError('idle_timeout_sec must be positive or None')
        self.idle_timeout_sec = idle_timeout_sec
        self._factory = detector_factory
        self._lock = threading.RLock()
        self._sessions: Dict[str, _Session] = {}

    def _new_detector(self):
        if self._factory is not None:
            return self._factory()
        from real_device_monitor.online_trajectory_defense_v3 import OnlineTrajectoryDefenseV3
        return OnlineTrajectoryDefenseV3()

    def start_session(self, *, trusted_legacy_context: Optional[Dict[str, str]] = None) -> str:
        """No context -> valid stream transport but no native scoring (UNSUPPORTED_CONTEXT).

        trusted_legacy_context: only from local benchmark harness, NEVER Android / public HTTP.
        Original Frozen V3 will still independently validate its task-cluster lookup.
        """
        ctx = None
        if trusted_legacy_context is not None:
            if not isinstance(trusted_legacy_context, dict):
                raise MonitorError('INVALID_TRUSTED_CONTEXT')
            required = ('participant', 'session_id')
            if any(not isinstance(trusted_legacy_context.get(k), str) or not trusted_legacy_context[k] for k in required):
                raise MonitorError('INVALID_TRUSTED_CONTEXT: participant,session_id required')
            ctx = {k: str(v) for k, v in trusted_legacy_context.items() if k in ('participant','session_id','group')}
        with self._lock:
            token = secrets.token_urlsafe(24)
            self._sessions[token] = _Session(token=token, ctx=ctx)
            return token

    def _lookup(self, token) -> _Session:
        if token not in self._sessions:
            raise MonitorError('SESSION_NOT_FOUND')
        return self._sessions[token]

    def _error(self, state: Optional[_Session], code: str, seq: Any, quarantine: bool = False):
        if state is not None:
            state.integrity_flag = True
            if quarantine:
                state.quarantined = True
        return {'session': state.token if state else None, 'gesture': seq,
                'status': 'ERROR', 'coverage': 'NONE', 'response': 'ERROR',
                'error_code': code, 'integrity_flag': bool(state and state.integrity_flag),
                'first_ask_hold_g': state.first_ask_hold_g if state else None,
                'first_intervene_g': state.first_intervene_g if state else None,
                'manifest_sha': self.manifest_sha, 'gate_advice': 'HOLD_PROTECTED_ACTION'}

    def push_gesture(self, token: str, *, seq: int, points: Any) -> Dict[str, Any]:
        begin = time.perf_counter_ns()
        with self._lock:
            try:
                s = self._lookup(token)
            except MonitorError as exc:
                return self._error(None, str(exc), seq)
            if s.ended:
                return self._error(s, 'SESSION_ENDED', seq)
            if self.idle_timeout_sec is not None and (begin-s.last_mono_ns)/1e9>self.idle_timeout_sec:
                s.ended=True
                s.end_reason='IDLE_TIMEOUT'
                return self._error(s, 'SESSION_IDLE_TIMEOUT', seq)
            if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
                return self._error(s, 'INVALID_SEQUENCE', seq, quarantine=True)
            try:
                clean = _validate_gesture(points)
            except MonitorError as exc:
                return self._error(s, str(exc), seq, quarantine=True)
            digest = _sha_json(clean)
            if s.quarantined:
                return self._error(s, 'SESSION_QUARANTINED', seq)
            if seq in s.digests:
                if digest != s.digests[seq]:
                    return self._error(s, 'DUPLICATE_CONFLICT', seq, quarantine=True)
                # Same exact payload: idempotent, regardless of subsequent pushes
                return {**s.cached[seq], 'idempotent_replay': True}
            expected = len(s.gestures) + 1
            if seq != expected:
                return self._error(s, 'SEQUENCE_GAP' if seq > expected else 'OUT_OF_ORDER', seq, quarantine=True)
            if s.gestures:
                gap = clean[0]['t_us'] - s.gestures[-1][-1]['t_us']
                if gap < 0:
                    return self._error(s, 'TIME_ORDER_VIOLATION', seq, quarantine=True)
                if gap > self.max_gap_us:
                    return self._error(s, 'EXCESSIVE_IDLE_GAP_SESSION_SPLIT_REQUIRED', seq, quarantine=True)
            s.gestures.append(clean)
            s.digests[seq] = digest
            s.last_mono_ns = time.perf_counter_ns()
            output = {'session': token, 'gesture': seq, 'manifest_sha': self.manifest_sha,
                      'native_response': None, 'strict_score': None, 'evidence_region': None,
                      'reason': None, 'first_ask_hold_g': s.first_ask_hold_g,
                      'first_intervene_g': s.first_intervene_g, 'integrity_flag': False,
                      'gate_advice': 'HOLD_PROTECTED_ACTION', 'idempotent_replay': False}
            if seq < NATIVE_START:
                output.update(status='WARMUP', coverage='NONE', response='WARMUP', reason='INSUFFICIENT_PREFIX')
            elif seq > NATIVE_STOP:
                output.update(status='UNMONITORED', coverage='NONE', response='UNMONITORED',
                              reason='OUTSIDE_CALIBRATED_WINDOW')
            elif s.ctx is None:
                output.update(status='UNSUPPORTED_CONTEXT', coverage='NONE', response='UNSUPPORTED_CONTEXT',
                              reason='TASK_CLUSTER_METADATA_UNAVAILABLE')
            else:
                if s.detector is None:
                    try:
                        s.detector = self._new_detector()
                    except Exception as exc:
                        output.update(status='ERROR', coverage='NONE', response='ERROR',
                                      reason='MODEL_LOAD_ERROR', error_code=type(exc).__name__)
                if s.detector is not None:
                    rec = _native_record(s.gestures, s.ctx)
                    try:
                        native = s.detector.evaluate_prefix(rec)
                        if native.get('phase') != 'ACTIVE' or native.get('gesture') != seq:
                            raise RuntimeError('NATIVE_PHASE_OR_GESTURE_MISMATCH')
                        response = native.get('response')
                        if response not in ('ALLOW','MONITOR','ASK_HOLD','INTERVENE'):
                            raise RuntimeError('UNKNOWN_NATIVE_RESPONSE')
                        if response == 'ASK_HOLD' and s.first_ask_hold_g is None:
                            s.first_ask_hold_g = seq
                        if response == 'INTERVENE' and s.first_intervene_g is None:
                            s.first_intervene_g = seq
                        output.update(status='OK', coverage='ACTIVE', response=response,
                                      native_response=response, strict_score=native.get('strict_score'),
                                      evidence_region=native.get('evidence_region'), reason=native.get('reason'),
                                      first_ask_hold_g=s.first_ask_hold_g,
                                      first_intervene_g=s.first_intervene_g,
                                      native_result={k:v for k,v in native.items() if isinstance(v, (str,int,float,bool,type(None)))},
                                      gate_advice='ALLOW' if response in ('ALLOW','MONITOR') else 'HOLD_PROTECTED_ACTION')
                    except Exception as exc:
                        msg = str(exc)
                        missing = 'No frozen task-cluster mapping' in msg
                        output.update(status='UNSUPPORTED_CONTEXT' if missing else 'ERROR',
                                      coverage='NONE', response='UNSUPPORTED_CONTEXT' if missing else 'ERROR',
                                      reason='TASK_CLUSTER_NOT_IN_FROZEN_LOOKUP' if missing else 'NATIVE_INFERENCE_ERROR',
                                      error_code=type(exc).__name__)
            output['latency_ms'] = round((time.perf_counter_ns()-begin)/1e6, 6)
            output['integrity_flag'] = s.integrity_flag
            # errors are not permission; fail-closed advice, no phone enforcement yet
            s.cached[seq] = output.copy()
            return output

    def end_session(self, token: str, *, reason: str = 'EXPLICIT_END') -> Dict[str, Any]:
        with self._lock:
            try:
                s = self._lookup(token)
            except MonitorError as exc:
                return self._error(None, str(exc), None)
            if reason not in ('EXPLICIT_END','APP_BACKGROUND','APP_STOP','SESSION_RESET'):
                return self._error(s, 'INVALID_END_REASON', None)
            s.ended = True
            s.end_reason = reason
            return {'session': token, 'status': 'ENDED', 'end_reason': reason, 'gestures': len(s.gestures),
                    'first_ask_hold_g': s.first_ask_hold_g,
                    'first_intervene_g': s.first_intervene_g, 'integrity_flag': s.integrity_flag,
                    'manifest_sha': self.manifest_sha}
