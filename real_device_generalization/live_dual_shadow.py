#!/usr/bin/env python3
"""P74 Author Ultimate live shadow, attached to the validated P10 Type-B Shadow.

The original Shadow does ALL phone I/O, kernel capture, original frozen V3
inference, and V3 alarm clock (g>=5). This wrapper never sends a device action.
Author evaluation uses the *same* existing completed-touch prefix. Additional
synchronous scoring latency is measured and disclosed (not a blocking policy).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import statistics
import sys
import tempfile
import time
from pathlib import Path


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def safe_jsonl(path, row):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, allow_nan=False, default=str) + "\n")


def stats(xs):
    ys=sorted(float(x) for x in xs if x is not None and math.isfinite(float(x)))
    if not ys:
        return {"n":0,"mean_ms":None,"median_ms":None,"p95_ms":None,"sum_ms":0.0}
    return {"n":len(ys),"mean_ms":statistics.mean(ys),
            "median_ms":statistics.median(ys),
            "p95_ms":ys[max(0,math.ceil(.95*len(ys))-1)],
            "sum_ms":sum(ys)}


def evidence_check(value):
    if not value or len(value.strip())<8:
        raise ValueError("P74 requires an explicit, independently documented source-cluster provenance")
    if value.strip().lower() in ("guess", "unknown", "default", "qqmusic", "0", "1", "2", "3", "4"):
        raise ValueError("Do not use a guessed, app-name-only, or fallback cluster mapping")
    return value.strip()


class NativeP74:
    """Single frozen model load, then independent native parsing on each raw prefix."""
    def __init__(self, project, cluster, evidence):
        if cluster not in range(5):
            raise ValueError("P74 original cluster must be in 0..4")
        self.evidence=evidence_check(evidence)
        self.cluster=cluster
        self.project=Path(project).expanduser().resolve()

        from dual_replay import prerequisites, author_end_scores
        self._end_scores=author_end_scores
        scripts, author, scaler, _v3, assets=prerequisites(self.project)
        self.asset_sha256={str(p.relative_to(self.project)):v for p,v in assets.items()}
        sys.dont_write_bytecode=True
        if str(scripts) not in sys.path:
            sys.path.insert(0,str(scripts))
        import P20_four_model_runner as p20
        import P31_hex_online as p31
        from P31_hex_frame_adapter import parse_log
        from P74_original_author_reconstructed_scaler_1770 import OuterScaledClassifier
        from analysis.lib.motionevent_classes import FingerEvent
        from analysis.lib.feature_library import startT_us, endT_us
        import joblib
        judge,_=p31.load_original_author(self.project,author)
        scalers=joblib.load(scaler)
        if set(scalers)!=set(range(5)):
            raise RuntimeError("P73 must contain all five reconstructed original-cluster scalers")
        judge.classifiers_to_use_for_clusters={
            c:tuple(OuterScaledClassifier(clf,scalers[c])
                    for clf in judge.classifiers_to_use_for_clusters[c][:2])
            for c in range(5)
        }
        self.judge=judge
        self.p20=p20
        self.parse_log=parse_log
        self.FingerEvent=FingerEvent
        self.start_us=startT_us
        self.end_us=endT_us
        self.previous_signature=[]
        self.previous_count=0
        self._tmp=tempfile.TemporaryDirectory(prefix="csg_p74_live_shadow_")
        self._prefix=Path(self._tmp.name)/"native_typeb_prefix.log"

    def score(self, blob, physical_g, check_history=True):
        t0=time.perf_counter()
        result={"status":"abstain","score":None,"detected":None,
                "n_actions":None,"latency_ms":None,"error":None}
        try:
            self._prefix.write_bytes(blob)
            p=self.parse_log(self._prefix)
            if p.get("parse_status")!="ok" or len(p.get("gestures",[]))!=len(p.get("actions",[])):
                result["status"]="parser_abstain:" + str(p.get("parse_status"))
                return result
            events=self.p20.author_actions(p["gestures"],self.FingerEvent)
            n=len(events)
            result["n_actions"]=n
            if not n:
                result["status"]="no_recognized_gestures"
                return result
            if n>physical_g:
                raise ValueError("Author parser observed more actions than physical completed contacts")
            signatures=[(int(self.start_us(e)),int(self.end_us(e))) for e in events]
            if check_history:
                if n<self.previous_count or signatures[:len(self.previous_signature)]!=self.previous_signature:
                    raise ValueError("Previously observed Author gestures changed after unseen future input")
                self.previous_signature=signatures
                self.previous_count=n
            trace=self.judge.predict(("real_device_live",events),self.cluster,prior_log_odds=0.0)
            z=self._end_scores(trace,events,self.start_us,self.end_us)[-1]
            result.update(status="ok",score=float(z),detected=bool(z>0))
            return result
        except Exception as exc:
            result.update(status="error",error=type(exc).__name__+": "+str(exc))
            return result
        finally:
            result["latency_ms"]=round((time.perf_counter()-t0)*1000,3)

    def close(self):
        self._tmp.cleanup()


class DualShadow:
    """Delegates all I/O and V3 scoring untouched to validated original Shadow."""
    def __init__(self, original_shadow, project, outdir, cluster, evidence, session_id):
        self.original=original_shadow
        self.outdir=Path(outdir)
        self.session_id=session_id
        self.author=NativeP74(project,cluster,evidence)  # fail before any touch
        self.eventsfile=self.original.eventsfile  # preserve original V3 consumer
        self.dual_eventsfile=self.outdir/"dual_online_prefixes.jsonl"
        self.rows=[]
        self._final=None
        self._closed=False
        self._first_alarm={"author":None,"v3":None}
        self._first_alarm_utc={"author":None,"v3":None}
        self._start_utc=None
        self._errors=[]

    def __getattr__(self, name):
        return getattr(self.original,name)

    def start(self):
        self._start_utc=utc_now()
        return self.original.start()

    def stop(self):
        # AutoGLM and Mobile-Agent-E call stop() BEFORE final().
        # Do not close native Author resources until retrospective final scoring.
        return self.original.stop()

    def score_new(self, expected_delta, action_type):
        """Always score actual kernel closure, never a planned action."""
        source=self.original.score_new(expected_delta,action_type)
        # score_new has just read and validated the *same* kernel capture for P10.
        blob=self.original.last_blob
        cuts=self.original.gestures
        for z in source:
            g=int(z["hardware_g"])
            if g<1 or g>len(cuts):
                raise RuntimeError("Invalid physical g in native Frozen V3 Shadow")
            prefix=blob[:cuts[g-1]]
            source_hash=sha256_bytes(prefix)
            author=self.author.score(prefix,g)
            v3_status=(str(z.get("v3_status","not_online_eligible"))
                       if g>=5 else "not_online_eligible_g<5")
            v3_score=z.get("score") if g>=5 else None
            v3_pred=(bool(z["detected"]) if g>=5 and z.get("detected") is not None else None)
            row={
                "utc":utc_now(),"physical_g":g,"action_type":str(action_type),
                "source_prefix_sha256":source_hash,
                "author_status":author["status"],"author_score":author["score"],
                "author_detected":author["detected"],"author_n_actions":author["n_actions"],
                "author_latency_ms":author["latency_ms"],"author_error":author["error"],
                "v3_status":v3_status,"v3_score":v3_score,
                "v3_detected":v3_pred,"v3_n_actions":z.get("v3_n_actions") if g>=5 else None,
                "v3_latency_ms":z.get("latency_ms") if g>=5 else None,
                "v3_eligible_from_g":5,
                "author_eligible_from_g":1,
                "shadow_mode":"observe_no_block"
            }
            for key in ("author","v3"):
                if row[key+"_detected"] is True and self._first_alarm[key] is None:
                    self._first_alarm[key]=g
                    self._first_alarm_utc[key]=row["utc"]
            if author["status"]=="error":
                self._errors.append({"g":g,"detector":"author","error":author["error"]})
            safe_jsonl(self.dual_eventsfile,row)
            self.rows.append(row)
        return source  # do not alter the original V3 status/agent-control contract

    def final(self):
        if self._final is not None:
            return self._final
        native=self.original.final()
        blob=self.original.last_blob
        cuts=self.original.gestures
        n=len(cuts)
        author_final=None
        if n and cuts[-1]<=len(blob):
            author_final=self.author.score(blob[:cuts[-1]],n,check_history=True)
            if author_final["status"]=="error":
                self._errors.append({"g":n,"detector":"author_final",
                                     "error":author_final["error"]})
        v3_native={"status":native.get("v3_status"),
                   "score":native.get("final_score"),
                   "detected":native.get("final_detected"),
                   "n_actions":native.get("v3_n_actions"),
                   "latency_ms":native.get("latency_ms"),
                   "alignment_pass":native.get("alignment_pass")}
        # The original v3 g>=5 shadow path and Author action-closure clock are
        # separate. Final-only predictions are NOT retroactive online alarms.
        last_author=next((r for r in reversed(self.rows)
                         if r["physical_g"]==n and r["author_status"]=="ok"),None)
        parity=None
        if last_author and author_final and author_final["status"]=="ok":
            parity=math.isclose(last_author["author_score"],author_final["score"],
                                rel_tol=1e-10,abs_tol=1e-10)
            if not parity:
                self._errors.append({"g":n,"detector":"author_parity",
                                     "error":"Last online score differs from full-prefix score"})
        metrics={}
        for detector in ("author","v3"):
            ok=[r for r in self.rows if
                (r["author_status"] if detector=="author" else r["v3_status"])=="ok"]
            timing=[r[detector+"_latency_ms"] for r in ok]
            metrics[detector]={
                "first_online_alarm_g":self._first_alarm[detector],
                "first_online_alarm_utc":self._first_alarm_utc[detector],
                "ever_online_alarm":self._first_alarm[detector] is not None,
                "first_alarm_g_fraction":(self._first_alarm[detector]/n if n and self._first_alarm[detector] else None),
                "online_evaluable_prefix_count":len(ok),
                "online_prefix_coverage":(len(ok)/n if n else None),
                "online_latency":stats(timing),
                "eligible_g":1 if detector=="author" else 5
            }
        metrics["author"].update({
            "retrospective_session_final":author_final,
            "online_last_equals_final":parity
        })
        metrics["v3"].update({
            "retrospective_session_final":v3_native,
            "native_v3_ead":True
        })
        out={
            "schema":"csg_p74_p10_live_dual_shadow_v1",
            "session_id":self.session_id,
            "recorded_utc_start":self._start_utc,
            "recorded_utc_end":utc_now(),
            "completed_typeb_contacts":n,
            "virtual_capture_sha256":sha256_bytes(blob),
            "raw_log":"virtual_events_normalized.log",
            "dual_events":"dual_online_prefixes.jsonl",
            "v3_original_events":"v3_prefix_results.jsonl",
            "author_cluster":self.author.cluster,
            "author_cluster_evidence":self.author.evidence,
            "author_assets_sha256":self.author.asset_sha256,
            "shadow_only_no_intervention":True,
            "native_v3_short_final_is_retrospective":n<5,
            "metrics":metrics,
            "errors":self._errors,
            "task_completion":"pending_independent_or_manual_adjudication"
        }
        path=self.outdir/"paired_online_metrics.json"
        path.write_text(json.dumps(out,ensure_ascii=False,indent=2,
                                   allow_nan=False,default=str)+"\n",encoding="utf-8")
        self._final=native  # original adapter expects original V3 final()
        if not self._closed:
            self.author.close()
            self._closed=True
        return native


def wrap(original_shadow, project, outdir):
    """Attach only on explicitly opted-in real agent runs."""
    import os
    if os.getenv("CSG_DUAL_ONLINE")!="1":
        return original_shadow
    c=os.getenv("CSG_AUTHOR_CLUSTER")
    evidence=os.getenv("CSG_AUTHOR_CLUSTER_EVIDENCE","")
    sid=os.getenv("CSG_SESSION_ID") or Path(outdir).name
    if c is None or not c.isdigit() or int(c) not in range(5):
        raise RuntimeError("CSG_DUAL_ONLINE requires verified CSG_AUTHOR_CLUSTER 0..4")
    return DualShadow(original_shadow,project,outdir,int(c),evidence,sid)


def self_test():
    # End-to-end mocked integration without P74 imports, Android or API.
    # This deliberately covers the AutoGLM/Mobile-Agent-E order: stop() then final().
    assert evidence_check("verified-source-task-map: fixed-before-testing")!= ""
    for invalid in ("guess","default","qqmusic","0",""):
        try:evidence_check(invalid)
        except ValueError:pass
        else:raise AssertionError("Unsupported cluster provenance accepted")
    assert stats([10,20,30,40])["p95_ms"]==40

    import tempfile as _tempfile
    class FakeAuthor:
        close_called=False
        def __init__(self, project,cluster,evidence):
            self.cluster=cluster
            self.evidence=evidence
            self.asset_sha256={"mock":"mock"}
        def score(self,blob,physical_g,check_history=True):
            if self.close_called:raise RuntimeError("Author model closed before final")
            return {"status":"ok","score":float(physical_g)-1.5,
                    "detected":physical_g>=2,"n_actions":physical_g,
                    "latency_ms":0.2,"error":None}
        def close(self):
            self.close_called=True

    class FakeV3:
        def __init__(self, folder):
            self.outdir=folder
            self.last_n=0
            self.last_blob=b""
            self.gestures=[]
            self.eventsfile=folder/"v3_prefix_results.jsonl"
            self.error=None
            self.stopped=False
        def start(self):pass
        def stop(self):
            self.stopped=True
        def score_new(self, expected_delta,action_type):
            assert expected_delta==1
            g=self.last_n+1
            self.last_blob=b"Z"*g
            self.gestures=list(range(1,g+1))
            self.last_n=g
            if g<5:return [{"hardware_g":g,"state":"OBSERVE","action_type":action_type}]
            return [{"hardware_g":g,"state":"EAD_SHADOW","action_type":action_type,
                     "v3_status":"ok","v3_n_actions":g,
                     "score":.92,"detected":True,"latency_ms":2.5}]
        def final(self):
            return {"v3_status":"ok","final_score":.92,"final_detected":True,
                    "v3_n_actions":self.last_n,"alignment_pass":True,
                    "latency_ms":1.0}
    original=globals()["NativeP74"]
    try:
        globals()["NativeP74"]=FakeAuthor
        with _tempfile.TemporaryDirectory(prefix="csg_dual_test_") as d:
            folder=Path(d)
            native=FakeV3(folder)
            shadow=DualShadow(native,folder,folder,2,
                              "verified-source-task-map: fixed-before-testing","mock_session")
            shadow.start()
            for g in range(1,7):
                native_rows=shadow.score_new(1,"Tap")
                assert len(native_rows)==1
                assert shadow.rows[-1]["physical_g"]==g
                assert shadow.rows[-1]["source_prefix_sha256"]==sha256_bytes(b"Z"*g)
            shadow.stop()
            assert native.stopped
            assert not shadow._closed
            result=shadow.final()
            assert result["final_detected"] is True
            assert shadow._closed
            m=json.loads((folder/"paired_online_metrics.json").read_text())
            assert m["completed_typeb_contacts"]==6
            assert m["metrics"]["author"]["first_online_alarm_g"]==2
            assert m["metrics"]["v3"]["first_online_alarm_g"]==5
            assert m["metrics"]["author"]["online_evaluable_prefix_count"]==6
            assert m["metrics"]["v3"]["online_evaluable_prefix_count"]==2
            assert m["metrics"]["author"]["online_last_equals_final"] is True
            assert len((folder/"dual_online_prefixes.jsonl").read_text().splitlines())==6
    finally:
        globals()["NativeP74"]=original
    print("LIVE DUAL SHADOW MOCK INTEGRATION PASS: one source, native EAD g5, author, stop-then-final, latency")


if __name__=="__main__":
    self_test()
