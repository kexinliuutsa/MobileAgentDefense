#!/usr/bin/env python3
"""Aggregate REAL labeled sessions; separate live alarms, final, latency & task success.

Never treat agent-only runs as evidence for Human FPR or balanced accuracy.
Missing/abstaining detector decisions are NOT silently counted as true negatives.
"""
from __future__ import annotations
import argparse,csv,json,math,statistics
from collections import defaultdict
from pathlib import Path


def pct(num,den):
 return round(100.0*num/den,4) if den else None

def mean(values):
 vals=[float(x) for x in values if x is not None and math.isfinite(float(x))]
 return round(statistics.mean(vals),5) if vals else None

def as_label(z):
 label=z.get("ground_truth_actor")
 if label in ("agent","human") and (label=="human" or z.get("agent") in
                                         ("autoglm","mobile-agent-e","mai-ui")):
  return label
 return None

def get_final(m,det):
 v=m.get("metrics",{}).get(det,{}).get("retrospective_session_final")
 if not isinstance(v,dict):return None
 if det=="author":
  return v.get("detected") if v.get("status")=="ok" else None
 return v.get("detected") if v.get("status")=="ok" and v.get("alignment_pass") is True else None

def get_task_success(path):
 p=path/"summary.json"
 if not p.is_file():return "unknown"
 try:z=json.loads(p.read_text(encoding="utf-8"))
 except (ValueError,OSError):return "unknown"
 s=z.get("task_success_manual",z.get("task_success_self_reported",z.get("task_success","unknown")))
 if s is True or s in ("yes","y","pass"):return "manually_reported_success"
 if s is False or s in ("no","n","fail"):return "manually_reported_failure"
 return "unknown"

def session_rows(root):
 for file in sorted(root.rglob("generalization_manifest.json")):
  folder=file.parent
  metrics=folder/"paired_online_metrics.json"
  try:
   manifest=json.loads(file.read_text(encoding="utf-8"))
  except (OSError,ValueError):
   continue
  record={"path":str(folder),"agent":manifest.get("agent"),
          "task_id":manifest.get("task_id"),
          "package":manifest.get("expected_package"),
          "label":as_label(manifest),"cluster":manifest.get("original_author_task_cluster",
                      manifest.get("author_cluster")),
          "task_success":get_task_success(folder),
          "metrics_exists":metrics.is_file(),"mode":manifest.get("mode",manifest.get("defense_mode"))}
  if not metrics.is_file():
   yield record
   continue
  try:z=json.loads(metrics.read_text(encoding="utf-8"))
  except (OSError,ValueError):
   yield record
   continue
  record["physical_g"]=z.get("completed_typeb_contacts")
  record["paired_runtime_errors"]=len(z.get("errors",[]))
  record["author_parity"]=z["metrics"]["author"].get("online_last_equals_final")
  for d in ("author","v3"):
   m=z["metrics"][d]
   record[d+"_first_alarm_g"]=m.get("first_online_alarm_g")
   record[d+"_ever_online"]=bool(m.get("first_online_alarm_g"))
   record[d+"_final"]=get_final(z,d)
   record[d+"_eligible_prefixes"]=m.get("online_evaluable_prefix_count")
   record[d+"_prefix_coverage"]=m.get("online_prefix_coverage")
   record[d+"_mean_latency_ms"]=m.get("online_latency",{}).get("mean_ms")
   record[d+"_p95_latency_ms"]=m.get("online_latency",{}).get("p95_ms")
  yield record

def summarize_one(rows,d):
 people=[r for r in rows if r.get("label")=="human"]
 agents=[r for r in rows if r.get("label")=="agent"]
 final=[r for r in rows if r.get(d+"_final") is not None]
 paired_agent=[r for r in agents if r.get(d+"_final") is not None]
 paired_human=[r for r in people if r.get(d+"_final") is not None]
 tp=sum(r[d+"_final"] is True for r in paired_agent)
 fp=sum(r[d+"_final"] is True for r in paired_human)
 # There are two useful online denominators: all sessions and reached-k.
 online_tp=sum(bool(r.get(d+"_ever_online")) for r in agents)
 online_fp=sum(bool(r.get(d+"_ever_online")) for r in people)
 first=[r.get(d+"_first_alarm_g") for r in agents if r.get(d+"_first_alarm_g") is not None]
 def anytime_at(k,group):
  return sum(r.get(d+"_first_alarm_g") is not None and r[d+"_first_alarm_g"]<=k
             for r in group)
 def reached(k,group):
  return [r for r in group if (r.get("physical_g") or 0)>=k]
 result={
  "n_agent_sessions":len(agents),"n_human_sessions":len(people),
  "n_final_evaluable":len(final),
  "agent_final_evaluable":len(paired_agent),"human_final_evaluable":len(paired_human),
  "agent_final_TP":tp,"agent_final_FN":len(paired_agent)-tp,
  "human_final_FP":fp,"human_final_TN":len(paired_human)-fp,
  "agent_final_recall_pct":pct(tp,len(paired_agent)),
  "human_final_FPR_pct":pct(fp,len(paired_human)),
  "final_coverage_pct":pct(len(final),len(agents)+len(people)),
  "balanced_accuracy_pct":((pct(tp,len(paired_agent)) + 100-pct(fp,len(paired_human)))/2
     if paired_agent and paired_human else None),
  "accuracy_pct":pct(tp+len(paired_human)-fp,len(paired_agent)+len(paired_human))
    if paired_agent and paired_human else None,
  "anytime_agent_recall_all_sessions_pct":pct(online_tp,len(agents)),
  "anytime_human_FPR_all_sessions_pct":pct(online_fp,len(people)),
  "first_alarm_g_mean_among_detected":mean(first),
  "first_alarm_g_median_among_detected":(statistics.median(first) if first else None),
  "mean_online_prefix_coverage_pct":mean([100*r[d+"_prefix_coverage"] for r in rows
                                           if r.get(d+"_prefix_coverage") is not None]),
  "mean_inference_latency_ms":mean([r.get(d+"_mean_latency_ms") for r in rows]),
  "mean_p95_latency_ms":mean([r.get(d+"_p95_latency_ms") for r in rows]),
 }
 for k in (5,11):
  ag=reached(k,agents);hu=reached(k,people)
  result[f"g{k}"]={
   "agent_reached":len(ag),"human_reached":len(hu),
   "anytime_agent_detection_all_sessions_pct":pct(anytime_at(k,agents),len(agents)),
   "anytime_agent_detection_reached_only_pct":pct(anytime_at(k,ag),len(ag)),
   "anytime_human_FPR_all_sessions_pct":pct(anytime_at(k,people),len(people)),
   "anytime_human_FPR_reached_only_pct":pct(anytime_at(k,hu),len(hu))
  }
 return result

def build(rows):
 by=defaultdict(list)
 for r in rows:
  if r.get("label") is None:continue
  by[(r.get("agent"),r.get("package"))].append(r)
 output={
  "schema":"csg_agent_generalization_v1",
  "limitations":["Only observed, labeled sessions included; no synthetic Human traces",
                 "Human FPR / balanced accuracy remain null until valid Human sessions exist",
                 "Author P74 task clusters must be independently predeclared",
                 "Session-final classification is retrospective, not preventive",
                 "Manual task completion is not independent blinded ground truth"],
  "observed_folders":len(rows),
  "labeled_sessions":sum(r.get("label") is not None for r in rows),
  "overall":{"author":summarize_one(rows,"author"),
             "v3":summarize_one(rows,"v3")},
  "by_agent_and_app":[{"agent":agent,"package":package,"n":len(records),
                       "author":summarize_one(records,"author"),
                       "v3":summarize_one(records,"v3")}
                       for (agent,package),records in sorted(by.items())],
  "task_success":{
   "manually_reported_success":sum(r.get("task_success")=="manually_reported_success" for r in rows),
   "manually_reported_failure":sum(r.get("task_success")=="manually_reported_failure" for r in rows),
   "unverified_or_unknown":sum(r.get("task_success")=="unknown" for r in rows)
  },
  "session_rows":rows
 }
 return output

def self_test():
 a={"agent":"mobile-agent-e","package":"com.tencent.qqmusic","label":"agent",
    "author_final":True,"v3_final":False,"physical_g":8,
    "author_ever_online":True,"v3_ever_online":False,"author_first_alarm_g":3,
    "author_prefix_coverage":1.0,"v3_prefix_coverage":.5}
 z=build([a])
 assert z["overall"]["author"]["agent_final_TP"]==1
 assert z["overall"]["v3"]["agent_final_TP"]==0
 assert z["overall"]["author"]["human_final_FPR_pct"] is None
 assert z["overall"]["author"]["balanced_accuracy_pct"] is None
 assert z["overall"]["author"]["g11"]["agent_reached"]==0
 print("GENERALIZATION METRICS SELF-TEST PASS (agent-only FPR correctly undefined)")

def cli(argv=None):
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument("--runs-root",type=Path)
 ap.add_argument("--out",type=Path)
 ap.add_argument("--self-test",action="store_true")
 a=ap.parse_args(argv)
 if a.self_test:self_test();return 0
 if not a.runs_root:ap.error("--runs-root required")
 rows=list(session_rows(a.runs_root.expanduser().resolve()))
 output=build(rows)
 text=json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+"\n"
 if a.out:
  a.out.expanduser().resolve().parent.mkdir(parents=True,exist_ok=True)
  a.out.expanduser().resolve().write_text(text,encoding="utf-8")
  print("METRICS SAVED:",a.out)
 else:print(text)
 return 0

if __name__=="__main__":raise SystemExit(cli())
