#!/usr/bin/env python3
"""One agent run, one Type-B trace, native Frozen V3 plus live P74 shadow.

Default --preflight-only does not call the model or touch Android.
--execute still requires the original adapter's interactive authorization.
"""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,os,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
AGENTS={
 "autoglm":("run_autoglm.py","autoglm_v3_shadow"),
 "mobile-agent-e":("run_mobile_agent_e.py","mobile_agent_e_typeb_shadow"),
 "mai-ui":("run_mai_ui.py","mai_ui_8b_typeb_shadow"),
}
def sha(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()

def command(a,execute=False):
 name,_=AGENTS[a.agent]
 f=ROOT/"adapters"/name
 if not f.is_file():raise FileNotFoundError(f)
 cmd=[sys.executable,str(f),"--project",str(a.project),
      "--expected-package",a.expected_package,"--max-steps",str(a.max_steps)]
 if a.agent=="autoglm":
  cmd+=["--remote-binary",a.remote_binary]
  if a.autoglm_repo:cmd+=["--autoglm",str(a.autoglm_repo)]
 elif a.agent=="mobile-agent-e":
  if a.model:raise ValueError("Mobile-Agent-E must use official BACKBONE_TYPE API environment")
  cmd+=["--existing-typeb-runner",str(ROOT/"adapters"/"run_autoglm.py")]
  if a.mobile_agent_e_repo:cmd+=["--mobile-agent-e",str(a.mobile_agent_e_repo)]
 else:
  cmd+=["--original-adapter",str(ROOT/"adapters"/"run_autoglm.py"),
        "--mai-repo",str(a.mai_repo),"--remote-binary",a.remote_binary,
        "--max-actions",str(a.max_actions)]
  if a.mai_api_base:cmd+=["--api-base",a.mai_api_base]
 if a.model:cmd+=["--model",a.model]
 return cmd+(["--task",a.task] if execute else ["--preflight-only"])

def cli(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--agent",choices=AGENTS,required=True)
 p.add_argument("--project",type=Path,default=Path.home()/"Desktop"/"GUI_AHB_PAPER_REBUILD")
 p.add_argument("--expected-package",required=True)
 p.add_argument("--task-id",default="")
 p.add_argument("--task",default="")
 p.add_argument("--task-cluster",type=int,choices=range(5),
                help="Independently verified original P74 task cluster 0-4, fixed before task")
 p.add_argument("--cluster-evidence",default="",
                help="Explicit external evidence for cluster map; not a guessed app ID")
 p.add_argument("--v3-only",action="store_true",help="No verified original cluster; explicitly exclude P74")
 p.add_argument("--max-steps",type=int,default=25)
 p.add_argument("--max-actions",type=int,default=25)
 p.add_argument("--model",default="")
 p.add_argument("--autoglm-repo",type=Path)
 p.add_argument("--mobile-agent-e-repo",type=Path)
 p.add_argument("--mai-repo",type=Path,default=Path.home()/"Desktop"/"MAI-UI")
 p.add_argument("--mai-api-base",default="")
 p.add_argument("--remote-binary",default="/data/local/tmp/uinput_typeb_agent_compat")
 p.add_argument("--execute",action="store_true")
 p.add_argument("--audit-replay-after",action="store_true",
                help="Optional independent retrospective P74/P10 score parity audit")
 p.add_argument("--self-test",action="store_true")
 a=p.parse_args(argv)
 if a.self_test:
  for agent in AGENTS:
   a.agent=agent;a.project=Path("/tmp/mock_project");a.expected_package="com.example.app"
   a.model="";a.task="Browse"
   pre,exe=command(a),command(a,execute=True)
   assert "--preflight-only" in pre and "--task" not in pre
   assert "--task" in exe and "--preflight-only" not in exe
   assert ("--existing-typeb-runner" in pre)==(agent=="mobile-agent-e")
  print("3-AGENT REAL-DEVICE LIVE-DUAL RUNNER SELF-TEST PASS (offline)")
  return 0

 if a.audit_replay_after and (not a.execute or a.v3_only):
  p.error("--audit-replay-after requires real dual run")
 if a.v3_only and (a.task_cluster is not None or a.cluster_evidence):
  p.error("Cannot combine --v3-only with Author cluster declarations")
 if a.execute:
  if not a.task_id or not a.task.strip():p.error("--task-id and --task are required")
  if not a.v3_only:
   if a.task_cluster is None:p.error("Dual run requires --task-cluster; do not guess")
   evidence=a.cluster_evidence.strip()
   if len(evidence)<8 or evidence.lower() in ("guess","unknown","default","qqmusic"):
    p.error("Dual run requires original task-cluster --cluster-evidence")
 if a.model and a.agent=="mobile-agent-e":
  p.error("Mobile-Agent-E uses native BACKBONE_TYPE API configuration")
 if not 1<=a.max_steps<=60 or not 1<=a.max_actions<=60:p.error("Step budgets must be 1..60")
 if not a.expected_package.startswith(("com.","org.")):p.error("Exact Android package required")
 a.project=a.project.expanduser().resolve()
 adapter=ROOT/"adapters"/AGENTS[a.agent][0]
 print("MODE:",("P74 + P10 LIVE" if not a.v3_only else "P10 ONLY") if a.execute else "READ-ONLY PREFLIGHT",flush=True)
 print("ADAPTER SHA256:",sha(adapter),flush=True)
 pre=subprocess.run(command(a),check=False)
 if pre.returncode or not a.execute:return pre.returncode

 if not a.v3_only:
  q=subprocess.run([sys.executable,str(ROOT/"dual_replay.py"),
    "--project",str(a.project),"--preflight-only"],check=False)
  if q.returncode:
   print("Author P74 source/model/scaler hash check FAILED; no agent started",file=sys.stderr)
   return q.returncode

 runroot=a.project/"real_device_online"/AGENTS[a.agent][1]
 before={f.name for f in runroot.iterdir() if f.is_dir()} if runroot.is_dir() else set()
 env=os.environ.copy()
 for key in ("CSG_DUAL_ONLINE","CSG_AUTHOR_CLUSTER","CSG_AUTHOR_CLUSTER_EVIDENCE","CSG_SESSION_ID"):
  env.pop(key,None)
 if not a.v3_only:
  env.update({"CSG_DUAL_ONLINE":"1",
              "CSG_AUTHOR_CLUSTER":str(a.task_cluster),
              "CSG_AUTHOR_CLUSTER_EVIDENCE":a.cluster_evidence.strip(),
              "CSG_SESSION_ID":a.task_id})
 started=dt.datetime.now(dt.timezone.utc).isoformat()
 run=subprocess.run(command(a,execute=True),check=False,env=env)
 created=sorted({f.name for f in runroot.iterdir() if f.is_dir()}-before) if runroot.is_dir() else []
 if len(created)!=1:
  print("Cannot identify one new native run directory:",created,file=sys.stderr)
  return run.returncode or 3
 out=runroot/created[0]
 manifest={
  "schema":"csg_generalization_live_dual_v2","agent":a.agent,
  "task_id":a.task_id,"task":a.task,"expected_package":a.expected_package,
  "start_utc":started,"adapter_sha256":sha(adapter),
  "mode":"v3_only" if a.v3_only else "live_simultaneous_p74_p10",
  "author_cluster":a.task_cluster,
  "author_cluster_evidence":a.cluster_evidence.strip() or None,
  "agent_returncode":run.returncode,"shadow_only":True,
  "ground_truth_actor":"agent","task_success":"NOT_INDEPENDENTLY_VERIFIED",
  "human_FPR":"NOT_ESTIMABLE_FROM_AGENT_ONLY_RUN"
 }
 (out/"generalization_manifest.json").write_text(
  json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 metrics=out/"paired_online_metrics.json"
 if not a.v3_only and not metrics.is_file():
  print("Paired LIVE metrics missing: DO NOT include as a paired trial",file=sys.stderr)
  return run.returncode or 5
 if metrics.is_file():
  m=json.loads(metrics.read_text(encoding="utf-8"))
  print("ONLINE:",json.dumps({
   "physical_g":m["completed_typeb_contacts"],
   "author_first_alarm_g":m["metrics"]["author"]["first_online_alarm_g"],
   "v3_first_alarm_g":m["metrics"]["v3"]["first_online_alarm_g"],
   "author_eligible_prefixes":m["metrics"]["author"]["online_evaluable_prefix_count"],
   "v3_eligible_prefixes":m["metrics"]["v3"]["online_evaluable_prefix_count"],
   "metrics_file":str(metrics)},ensure_ascii=False),flush=True)
 if a.audit_replay_after:
  log=out/"virtual_events_normalized.log"
  if not log.is_file():return run.returncode or 4
  q=subprocess.run([sys.executable,str(ROOT/"dual_replay.py"),
   "--project",str(a.project),"--log",str(log),"--task-cluster",str(a.task_cluster),
   "--session-id",a.task_id,"--out",str(out/"independent_dual_audit_replay.json")],check=False)
  if q.returncode:print("Independent parity replay failed; native logs preserved",file=sys.stderr)
  return run.returncode or q.returncode
 return run.returncode

if __name__=="__main__":raise SystemExit(cli())
