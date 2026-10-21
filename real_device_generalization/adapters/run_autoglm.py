#!/usr/bin/env python3
"""PhoneAgent -> validated Type-B uinput tap/swipe -> getevent -> frozen V3 EAD-g5.

Pilot-only SHADOW monitor. Never blocks based on V3. Never trains/recalibrates.
Requirements: existing project's frozen V3, Open-AutoGLM install, one connected
Android phone, validated Type-B agent-compatible executable in /data/local/tmp.

Security: do NOT run with accounts allowing purchases, messages, deletes or transfers.
"""
from __future__ import annotations

import argparse
import base64
import io
import datetime as dt
import getpass
import importlib.util
import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

V3_REL = Path('01_clean_code/offline_defenses/crossscaleguard_offline_v3/run.py')
V2_REL = Path('01_clean_code/offline_defenses/crossscaleguard_offline_v2/src')
NODE = re.compile(rb'^\s*add device\s+\d+:\s+(/dev/input/event\d+)\s*$')
NAME = re.compile(rb'^\s*name:\s*"Virtual Touch Screen"')
EVLINE = re.compile(rb'^(\[\s*\d+\.\d+\])\s+(/dev/input/event\d+):\s+(.*)$')
TRACK = re.compile(rb'\bABS_MT_TRACKING_ID\s+([0-9a-fA-F]{8})\b')
SYN = re.compile(rb'\bSYN_REPORT\b')


TYPEB_REMOTE = '/data/local/tmp/uinput_typeb_agent_compat'
TYPEB_LOCAL_REL = Path('real_device_online/uinput_typeb_agent_compat/uinput_typeb_agent_compat')


def _attach_live_p74_to_original_v3_shadow(shadow, project, outdir):
    """Only instrumentation on validated native Shadow; never changes GUI actions."""
    if os.environ.get("CSG_DUAL_ONLINE") != "1":
        return shadow
    shared=Path(__file__).resolve().parents[1]
    if str(shared) not in sys.path:
        sys.path.insert(0,str(shared))
    from live_dual_shadow import wrap
    return wrap(shadow,project,outdir)


def verify_typeb_preflight(project, adb, remote, expected_package=None, verify_hash=True):
    """Read-only checks. No screen taps, no model API, no V3 inference."""
    if remote != TYPEB_REMOTE:
        raise RuntimeError(
            f'This baseline requires the separately validated Type-B executor: {TYPEB_REMOTE}; got {remote}')
    if not (project/V3_REL).is_file() or not (project/V2_REL/'crossscaleguard').is_dir():
        raise FileNotFoundError('Frozen V3 entry and shared V2 dependencies missing under project')
    local = project/TYPEB_LOCAL_REL
    if not local.is_file():
        raise FileNotFoundError(f'Compiled, previously validated Type-B binary missing: {local}. Run BUILD_UINPUT_TYPEB_AGENT_COMPAT_MAC.sh first.')
    check = subprocess.run(adb+['shell','test','-x',remote],capture_output=True,text=True,timeout=12)
    if check.returncode:
        raise RuntimeError('Type-B remote executable not found/authorized on phone: '+remote)
    local_sha = hashlib.sha256(local.read_bytes()).hexdigest()
    phone_sha = None
    if verify_hash:
        p = subprocess.run(adb+['shell','sha256sum',remote],capture_output=True,text=True,timeout=12)
        if p.returncode != 0 or not re.search(r'^[0-9a-fA-F]{64}\b',p.stdout):
            raise RuntimeError('Could not verify remote binary sha256 (no input sent). Run: adb shell sha256sum '+remote)
        phone_sha = p.stdout.split()[0].lower()
        if local_sha != phone_sha:
            raise RuntimeError('Type-B binary mismatch! Refuse to run: Mac SHA256='+local_sha+' phone SHA256='+phone_sha)
    # The validated C executable uses a fixed 1080x2400 input axis, so refuse other effective resolutions.
    p = subprocess.run(adb+['shell','wm','size'],capture_output=True,text=True,timeout=12)
    if p.returncode:
        raise RuntimeError('Failed to read Android display dimensions: '+p.stderr.strip())
    entries = re.findall(r'(?:Physical|Override) size:\s*(\d+)x(\d+)',p.stdout)
    if not entries or tuple(map(int,entries[-1])) != (1080,2400):
        raise RuntimeError(f'Type-B fixed pixel coordinates require 1080x2400 effective display, got: {p.stdout.strip()}')
    if expected_package:
        q=subprocess.run(adb+['shell','dumpsys','window'],capture_output=True,text=True,timeout=20)
        focused=next((line.strip() for line in q.stdout.splitlines() if 'mCurrentFocus=' in line),'UNKNOWN')
        if expected_package not in focused:
            raise RuntimeError(f'Expected {expected_package} in foreground BEFORE running task, got {focused}. Open app first.')
    print('TYPE-B PREFLIGHT PASS: executable present; frozen model files present; display=1080x2400.',flush=True)
    if verify_hash:
        print('  Mac vs Phone Type-B SHA256 verified:',local_sha,flush=True)
    else:
        print('  WARNING: Type-B executable SHA256 comparison skipped at user request.',flush=True)
    if expected_package:
        print('  Foreground app check PASS:',expected_package,flush=True)
    return {'remote_binary':remote,'local_sha256':local_sha,'phone_sha256':phone_sha,
            'binary_match': (local_sha==phone_sha) if verify_hash else None,
            'effective_screen':[1080,2400], 'expected_package':expected_package}


def adb_devices():
    p = subprocess.run(['adb','devices'], capture_output=True, text=True, timeout=10, check=True)
    devices = [t[0] for l in p.stdout.splitlines()[1:] if len(t := l.split()) >= 2 and t[1] == 'device']
    if len(devices) != 1:
        raise RuntimeError('Exactly ONE authorized ADB device is required; found '+str(len(devices)))
    return ['adb', '-s', devices[0]]


def virtual_normalize(raw):
    """Keep observed virtual-device events ONLY; no synthetic input samples."""
    pending = None
    nodes = set()
    for line in raw.splitlines():
        m = NODE.match(line)
        if m: pending = m.group(1)
        elif NAME.match(line) and pending: nodes.add(pending)
    if not nodes:
        return b'', []
    selected = []
    for line in raw.splitlines():
        m = EVLINE.match(line)
        if m and m.group(2) in nodes:
            selected.append(m.group(1)+b' '+m.group(3)+b'\n')
    return b''.join(selected), sorted(n.decode() for n in nodes)


def gesture_cuts(blob):
    """End of gesture = SYN_REPORT committing TRACKING_ID ffffffff."""
    live, committed_live, pos, cuts = False, False, 0, []
    ndown, nup = 0, 0
    for line in blob.splitlines(keepends=True):
        pos += len(line)
        m = TRACK.search(line)
        if m:
            live = int(m.group(1),16) != 0xffffffff
            if live: ndown += 1
            else: nup += 1
        if SYN.search(line):
            if committed_live and not live:
                cuts.append(pos)
            committed_live = live
    return cuts, {'downs': ndown, 'ups': nup, 'complete':len(cuts), 'open_contact':live}


def load_v3(project):
    src=project/V2_REL
    entry=project/V3_REL
    if not (src/'crossscaleguard').is_dir() or not entry.is_file():
        raise FileNotFoundError('Frozen V3 or V2 shared src not found in project')
    sys.path.insert(0,str(src))
    spec = importlib.util.spec_from_file_location('autoglm_frozen_crossscaleguard_v3',entry)
    if spec is None or spec.loader is None:
        raise RuntimeError('Cannot load frozen V3')
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m,m.load()


def jsonline(path, value):
    with path.open('a',encoding='utf-8') as f:
        f.write(json.dumps(value,ensure_ascii=False,default=str)+'\n')


class Shadow:
    def __init__(self, project, adb, remote_binary, capfile, outdir, v3, params, dwell_ms=100, swipe_ms=450):
        self.project,self.adb,self.remote_binary=project,adb,remote_binary
        self.capfile,self.outdir,self.v3,self.params=capfile,outdir,v3,params
        self.dwell_ms,self.swipe_ms=dwell_ms,swipe_ms
        self.last_n=0
        self.gestures=[]
        self.nodes=[]
        self.last_blob=b''
        self.error=None
        self._temp=tempfile.TemporaryDirectory(prefix='autoglm_v3_shadow_')
        self.scratch=Path(self._temp.name)/'prefix.log'
        self.eventsfile=outdir/'v3_prefix_results.jsonl'
        self.capture=None
        self.capture_fh=None

    def start(self):
        self.capture_fh=self.capfile.open('wb')
        self.capture=subprocess.Popen(self.adb+['shell','getevent','-lt'],stdout=self.capture_fh,stderr=subprocess.STDOUT)
        time.sleep(1.25)
        if self.capture.poll() is not None:
            raise RuntimeError('getevent exited before actions')

    def stop(self):
        if self.capture is not None and self.capture.poll() is None:
            self.capture.terminate()
            try: self.capture.wait(timeout=3)
            except subprocess.TimeoutExpired: self.capture.kill();self.capture.wait(timeout=3)
        if self.capture_fh:
            self.capture_fh.close()
        self._temp.cleanup()

    def read(self, wait=0.25):
        time.sleep(wait)
        raw=self.capfile.read_bytes()
        blob,nodes=virtual_normalize(raw)
        cuts,counts=gesture_cuts(blob)
        self.nodes=nodes
        self.last_blob=blob
        self.gestures=cuts
        return blob,cuts,counts

    def do(self, typ, *numbers):
        cmd=self.adb+['shell',self.remote_binary,typ]+[str(x) for x in numbers]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
        if p.returncode:
            raise RuntimeError(f'uinput {typ} returned {p.returncode}: {p.stderr[-300:]}')
        return p.stdout.strip()

    def score_new(self, expected_delta, action_type):
        prev_n=self.last_n
        blob,cuts,counts=self.read()
        now_n=len(cuts)
        if counts['open_contact'] or counts['downs']!=counts['ups'] or now_n-prev_n!=expected_delta:
            raise RuntimeError(f'GESTURE ALIGNMENT FAILED after {action_type}: previous={prev_n} current={now_n} expected_delta={expected_delta}; stats={counts}; nodes={self.nodes}')
        results=[]
        for g in range(prev_n+1,now_n+1):
            status={'hardware_g':g,'state':'OBSERVE' if g < 5 else 'EAD_SHADOW',
                    'action_type':action_type}
            if g >= 5:
                self.scratch.write_bytes(blob[:cuts[g-1]])
                t0=time.perf_counter()
                z=self.v3.predict(self.scratch,*self.params)
                status.update({'latency_ms':round(1000*(time.perf_counter()-t0),2),
                               'v3_status':z.get('status'),'v3_n_actions':z.get('n_actions'),
                               'score':z.get('final_score'),'detected':z.get('detected')})
                status['alignment_pass']=z.get('status')=='ok' and z.get('n_actions')==g
                if not status['alignment_pass']:
                    jsonline(self.eventsfile,status)
                    raise RuntimeError(f'V3 prefix alignment failed at g={g}: {status}')
                print(f'  EAD g={g}: score={status["score"]:.6f} detected={status["detected"]} latency={status["latency_ms"]:.1f}ms [SHADOW]',flush=True)
            else:
                print(f'  OBSERVE physical_g={g}/5',flush=True)
            jsonline(self.eventsfile,status)
            results.append(status)
        self.last_n=now_n
        return results

    def final(self):
        blob,cuts,counts=self.read(0.25)
        (self.outdir/'virtual_events_normalized.log').write_bytes(blob)
        self.nodes=self.nodes or []
        if counts['open_contact']:
            raise RuntimeError('Unclosed touch at end')
        # Short tasks receive retrospective-only evaluation, not realtime alerts.
        path=self.outdir/'virtual_events_normalized.log'
        if not cuts:
            return {'status':'no_touch_gestures', 'hardware_gestures':0,'nodes':self.nodes}
        t0=time.perf_counter()
        z=self.v3.predict(path,*self.params)
        result={'hardware_gestures':len(cuts),'v3_status':z.get('status'),
                'v3_n_actions':z.get('n_actions'),'final_score':z.get('final_score'),
                'final_detected':z.get('detected'),'latency_ms':round(1000*(time.perf_counter()-t0),2),
                'nodes':self.nodes,'end_fallback_only':len(cuts)<5}
        result['alignment_pass']=(z.get('status')=='ok' and z.get('n_actions')==len(cuts))
        return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project',type=Path,default=Path.cwd())
    ap.add_argument('--autoglm',type=Path,default=None,help='Open-AutoGLM cloned repository path')
    ap.add_argument('--task',default=None,help='One SAFE real-app task; avoid transactions, messaging and account changes')
    ap.add_argument('--base-url',default=os.getenv('PHONE_AGENT_BASE_URL','https://open.bigmodel.cn/api/paas/v4'))
    ap.add_argument('--model',default=os.getenv('PHONE_AGENT_MODEL','autoglm-phone'))
    ap.add_argument('--max-steps',type=int,default=15)
    ap.add_argument('--save-step-screenshots',action='store_true',help='Save each actual model-view screenshot locally; may contain private information')
    ap.add_argument('--stop-on-screen-loop',action='store_true',help='EXPERIMENTAL; not recommended for this re-test due possible false loop stops')
    ap.add_argument('--loop-image-mae',type=float,default=7.0,help='Mean pixel-difference cutoff on 36x80 grayscale thumbnail (default: 7.0)')
    ap.add_argument('--dwell-ms',type=int,default=100)
    ap.add_argument('--swipe-ms',type=int,default=450)
    ap.add_argument('--remote-binary',default=TYPEB_REMOTE,help='Must be verified Type-B executor (never old uinput)')
    ap.add_argument('--expected-package',default=None,help='Optional Android package required to be foreground, e.g. com.tencent.qqmusic')
    ap.add_argument('--preflight-only',action='store_true',help='Read-only preflight: no API key, no model call, no touch')
    ap.add_argument('--skip-binary-hash-check',action='store_true',help='Not recommended. Skip exact Mac-vs-phone executable SHA256 check')
    a=ap.parse_args()
    project=a.project.expanduser().resolve()
    if not a.preflight_only and not a.task:
        ap.error('--task is required except for --preflight-only')
    if a.max_steps<1 or a.max_steps>100: ap.error('--max-steps must be 1..100')
    if a.loop_image_mae<0 or a.loop_image_mae>50: ap.error('--loop-image-mae must be 0..50')
    if not 50<=a.dwell_ms<=500: ap.error('--dwell-ms must be 50..500')
    if not 150<=a.swipe_ms<=2000: ap.error('--swipe-ms must be 150..2000')
    if not shutil.which('adb'):ap.error('adb is not installed')
    adb=adb_devices()
    preflight=verify_typeb_preflight(project,adb,a.remote_binary,a.expected_package,not a.skip_binary_hash_check)
    if a.preflight_only:
        print('PREFLIGHT ONLY PASS: no touch, no AutoGLM API call, no V3 inference.',flush=True)
        return 0
    if a.autoglm:
        r=a.autoglm.expanduser().resolve()
        if not (r/'phone_agent'/'agent.py').is_file():
            ap.error('Open-AutoGLM clone invalid: '+str(r))
        sys.path.insert(0,str(r))
    try:
        from phone_agent import PhoneAgent
        from phone_agent.agent import AgentConfig
        from phone_agent.model import ModelConfig
        from phone_agent.actions.handler import ActionResult
    except ImportError as e:
        ap.error('Open-AutoGLM package import failed. Clone and run pip install -r requirements.txt && pip install -e .; '+str(e))
    key=os.getenv('PHONE_AGENT_API_KEY','')
    if not key:
        key=getpass.getpass('AutoGLM API key (hidden, never saved): ').strip()
    if not key:ap.error('Missing API key. Use PHONE_AGENT_API_KEY environment variable')
    print('Loading ORIGINAL Frozen CrossScaleGuard V3...',flush=True)
    v3,params=load_v3(project)
    config=ModelConfig(base_url=a.base_url,api_key=key,model_name=a.model,temperature=0.0)
    agent=PhoneAgent(config,AgentConfig(max_steps=a.max_steps,lang='cn',verbose=False))
    outdir=project/'real_device_online'/'autoglm_v3_shadow'/dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    print('\nSHADOW PILOT - FIRST AGENT TASK',flush=True)
    print('Goal:',a.task,flush=True)
    print('Model:',a.model,'endpoint:',a.base_url,flush=True)
    print('Input: independently validated ROOTLESS Type-B uinput; EAD first decision at g5; NO blocking.',flush=True)
    print(f'Tap: {a.dwell_ms}ms, no jitter; Swipe: {a.swipe_ms}ms, linear profile, curvature=0, overshoot=0.',flush=True)
    print('NOTE: C implementation still adds minor 0.8px Gaussian swipe noise; this is a uinput baseline, not an exact raw ADB trace.',flush=True)
    print('Other actions (Type, Launch, Back, Home) use official Android helpers and are NOT counted as touch gestures.',flush=True)
    print('Only run on non-sensitive apps; screenshots are sent to the selected model API.',flush=True)
    print('CTRL+C safely stops the agent and closes getevent. No purchases, posting or messaging.',flush=True)
    if input('Type YES to authorize executing this task on your PHONE: ').strip()!='YES':
        print('CANCELLED. No Agent actions sent.');return 0
    outdir.mkdir(parents=True,exist_ok=False)
    watcher=_attach_live_p74_to_original_v3_shadow(Shadow(project,adb,a.remote_binary,outdir/'getevent_all_devices.log',outdir,v3,params,a.dwell_ms,a.swipe_ms),project,outdir)
    original=agent.action_handler.execute
    user_cancelled=False
    stop_reason='max_steps'
    stepfile=outdir/'agent_steps.jsonl'
    # Capture the EXACT screenshot handed to AutoGLM, rather than taking a second
    # possibly stale snapshot after the step. No model/defense changes.
    from PIL import Image, ImageChops, ImageStat
    from phone_agent.device_factory import get_device_factory
    device_factory = get_device_factory()
    original_screenshot = device_factory.get_screenshot
    seen_screens = []  # {step, thumbnail}; only kept in memory
    completed_actions = [] # {step, action}, does not include unfinished step
    step_number = [0]
    screenshot_dir = outdir/'model_view_screenshots'
    if a.save_step_screenshots:
        screenshot_dir.mkdir(parents=True,exist_ok=True)
    screen_audit_file = outdir/'screen_audit.jsonl'

    class RecurrentScreenLoop(RuntimeError):
        pass

    def instrumented_screenshot(device_id=None, timeout=10):
        shot = original_screenshot(device_id, timeout)
        step = step_number[0]
        row={'step':step,'width':shot.width,'height':shot.height,
             'is_sensitive':bool(getattr(shot,'is_sensitive',False)),
             'screen_recurs':False,'loop_detected':False}
        # Skip black/sensitive fallbacks. Screenshots are already being sent to the
        # chosen model API by Open-AutoGLM. Local saving is strictly opt-in.
        if not row['is_sensitive']:
            try:
                image=Image.open(io.BytesIO(base64.b64decode(shot.base64_data))).convert('RGB')
                if a.save_step_screenshots:
                    image.save(screenshot_dir/f'step_{step:03d}_model_view.png')
                thumb=image.convert('L').resize((36,80))
                similar=[]
                for previous in seen_screens:
                    mad=ImageStat.Stat(ImageChops.difference(thumb,previous['thumb'])).mean[0]
                    if mad<=a.loop_image_mae:
                        similar.append((previous['step'],round(mad,3)))
                row['matching_prior_steps']=similar[-12:]
                row['screen_recurs']=bool(similar)
                if len(similar)>=2:
                    first_match=similar[0][0]
                    intervening=[x['action'] for x in completed_actions if x['step']>=first_match]
                    n_back=sum(x=='Back' for x in intervening)
                    n_tap=sum(x=='Tap' for x in intervening)
                    if n_back>=2 and n_tap>=2:
                        row['loop_detected']=True
                        row['loop_pattern']='same screenshot >=3 times, >=2 Back, >=2 Tap since first match'
                seen_screens.append({'step':step,'thumb':thumb})
            except Exception as exc:
                row['screen_audit_error']=f'{type(exc).__name__}: {exc}'
        jsonline(screen_audit_file,row)
        if row['loop_detected']:
            print(f'\nSCREEN LOOP at step {step}: revisited screen from steps {row.get("matching_prior_steps")}; prior Back/Tap cycles confirmed.',flush=True)
            if a.stop_on_screen_loop:
                raise RecurrentScreenLoop(f'Repeated UI state before step {step}; task not progressing')
        return shot

    device_factory.get_screenshot=instrumented_screenshot
    
    def wrapped(action,w,h):
        actionname=action.get('action') if action.get('_metadata')=='do' else None
        if actionname in ('Double Tap','Long Press'):
            return ActionResult(False,True,'Pilot stopped: double tap/long press not yet instrumented as atomic touch gestures')
        if actionname not in ('Tap','Swipe'):
            return original(action,w,h)
        if action.get('message'):
            ok=agent.action_handler.confirmation_callback(action['message'])
            if not ok:return ActionResult(False,True,'User declined sensitive touch')
        try:
            if actionname=='Tap':
                pt=action.get('element')
                if not isinstance(pt,(list,tuple)) or len(pt)!=2:raise ValueError('Tap requires element [x,y]')
                x,y=(max(0,min(d-1,int(float(c)/1000*d))) for c,d in zip(pt,(w,h)))
                watcher.do('tap',x,y,a.dwell_ms,0)
            else:
                start,end=action.get('start'),action.get('end')
                if not isinstance(start,(list,tuple)) or not isinstance(end,(list,tuple)) or len(start)!=2 or len(end)!=2:
                    raise ValueError('Swipe requires start,end coordinate pairs')
                x1,y1=(max(0,min(d-1,int(float(c)/1000*d))) for c,d in zip(start,(w,h)))
                x2,y2=(max(0,min(d-1,int(float(c)/1000*d))) for c,d in zip(end,(w,h)))
                watcher.do('swipe',x1,y1,x2,y2,a.swipe_ms,0,'linear',0)
            watcher.score_new(1,actionname)
            return ActionResult(True,False)
        except Exception as e:
            watcher.error=f'{type(e).__name__}: {e}'
            print('STOPPING ON INJECTION/ALIGNMENT/SCORING ERROR:',watcher.error,flush=True)
            return ActionResult(False,True,'Experiment stopped: '+watcher.error)

    agent.action_handler.execute=wrapped
    result=None
    try:
        watcher.start()
        for i in range(a.max_steps):
            step_number[0]=i+1
            print(f'\nAGENT STEP {i+1}/{a.max_steps} - current virtual gestures={watcher.last_n}',flush=True)
            started=time.perf_counter()
            try:
                result=agent.step(a.task if i==0 else None)
            except RecurrentScreenLoop as exc:
                stop_reason='repeated_screen_loop'
                print('STOPPING REPEATED SCREEN LOOP:',exc,flush=True)
                break
            record={'step':i+1,'action':result.action,'success':result.success,
                    'finished':result.finished,'message':result.message,
                    'elapsed_s':round(time.perf_counter()-started,2),
                    'virtual_gestures':watcher.last_n}
            jsonline(stepfile,record)
            completed_actions.append({'step':i+1,'action':(result.action or {}).get('action','')})
            print('  ACTION:', (result.action or {}).get('action',(result.action or {}).get('_metadata')),
                  '| finished=',result.finished,'| elapsed=',record['elapsed_s'],'s',flush=True)
            if result.finished:
                stop_reason='agent_finished' if not watcher.error else 'protocol_failure'
                break
    except KeyboardInterrupt:
        print('\nSTOPPED BY USER CTRL+C',flush=True)
        user_cancelled=True
        stop_reason='user_interrupt'
    finally:
        device_factory.get_screenshot=original_screenshot
        watcher.stop()
    try:
        final=watcher.final()
    except Exception as exc:
        final={'error':str(exc)}
        print('FINAL V3 AUDIT FAILED:',exc,flush=True)
    task_success='unknown'
    if not user_cancelled:
        ans=input('Task REALLY completed correctly? [y/n/u=unknown]: ').strip().lower()
        task_success={'y':'yes','n':'no'}.get(ans,'unknown')
    alarms=[]
    if watcher.eventsfile.is_file():
        alarms=[json.loads(l) for l in watcher.eventsfile.read_text().splitlines() if l.strip()]
    alarmed=[x for x in alarms if x.get('detected') is True]
    summary={'model':a.model,'base_url':a.base_url,'task':a.task,
             'experimental_mode':'uinput-typeb-baseline_EAD-g5_shadow_loopguard' if a.stop_on_screen_loop else 'uinput-typeb-baseline_EAD-g5_shadow',
             'stop_on_screen_loop':bool(a.stop_on_screen_loop),
             'stopping_reason':stop_reason,'protocol_error':watcher.error,
             'api_error':getattr(result,'message',None) if result and result.action is None else None,
             'task_success_self_reported':task_success,
             'gestures_from_action_wrappers':watcher.last_n,
             'input_provenance':'kernel virtual touchscreen, MT Type-B, not human physical touch',
             'executor_preflight':preflight,
             'v3_final':final,'first_alarm_g':alarmed[0]['hardware_g'] if alarmed else None,
             'anytime_alarm_after_g5':bool(alarmed),'prefixes_scored':len([x for x in alarms if x.get('v3_status')=='ok']),
             'screen_loop_detected':stop_reason=='repeated_screen_loop',
             'step_screen_audit':'screen_audit.jsonl',
             'model_view_screenshots_saved':a.save_step_screenshots,
             'task_completion_requires_manual_verification':True,
             'api_key_saved':False}
    (outdir/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    print('\nFINAL SHADOW SUMMARY:',json.dumps(summary,indent=2,ensure_ascii=False,default=str),flush=True)
    print('SAVED:',outdir,flush=True)
    print('No original model weights, thresholds or previous cache modified.',flush=True)
    return 0 if not watcher.error and final.get('alignment_pass') is True else 2


if __name__=='__main__':
    try:sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)