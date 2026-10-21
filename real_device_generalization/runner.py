#!/usr/bin/env python3
"""Three-agent frozen Type-B shadow runner. Default: PHONE PRE-FLIGHT ONLY.

Uses independently validated original adapter sources, not new GUI logic.
Only --execute may call models or touch the phone; underlying adapter additionally
requires the user's interactive phone-task approval. No model or threshold changes.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
AGENTS={
 'autoglm':('run_autoglm.py','autoglm_v3_shadow'),
 'appagent':('run_appagent.py','appagent_typeb_shadow'),
 'mai-ui':('run_mai_ui.py','mai_ui_8b_typeb_shadow')
}

def sha256(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
 return h.hexdigest()

def command(a, execute=False):
 name,_=AGENTS[a.agent]; adapter=ROOT/'adapters'/name
 if not adapter.is_file():raise FileNotFoundError(adapter)
 cmd=[sys.executable,str(adapter),'--project',str(a.project),'--expected-package',a.expected_package,
      '--max-steps',str(a.max_steps)]
 if a.agent=='autoglm':
  cmd+=['--remote-binary',a.remote_binary]
  if a.autoglm_repo:cmd+=['--autoglm',str(a.autoglm_repo)]
 elif a.agent=='appagent':
  cmd+=['--original-runner',str(ROOT/'adapters'/'run_autoglm.py'),
        '--appagent-repo',str(a.appagent_repo),'--max-actions',str(a.max_actions),
        '--ui-mode',a.ui_mode]
 else:
  cmd+=['--original-adapter',str(ROOT/'adapters'/'run_autoglm.py'),
        '--mai-repo',str(a.mai_repo),'--remote-binary',a.remote_binary,
        '--max-actions',str(a.max_actions)]
  if a.mai_api_base:cmd+=['--api-base',a.mai_api_base]
 if a.model:cmd+=['--model',a.model]
 cmd+=['--task',a.task] if execute else ['--preflight-only']
 return cmd

def cli(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--agent',choices=AGENTS,required=True)
 p.add_argument('--project',type=Path,default=Path.home()/'Desktop'/'GUI_AHB_PAPER_REBUILD')
 p.add_argument('--expected-package',required=True,help='Exact foreground Android package')
 p.add_argument('--task-id',default='')
 p.add_argument('--task',default='',help='Read-only browsing task; required in execute mode')
 p.add_argument('--task-cluster',type=int,choices=range(5),default=None,
                help='OPTIONAL: independently verified P74 original task cluster, never guessed')
 p.add_argument('--max-steps',type=int,default=25)
 p.add_argument('--max-actions',type=int,default=25)
 p.add_argument('--model',default='')
 p.add_argument('--autoglm-repo',type=Path)
 p.add_argument('--appagent-repo',type=Path,default=Path.home()/'Desktop'/'AppAgent')
 p.add_argument('--mai-repo',type=Path,default=Path.home()/'Desktop'/'MAI-UI')
 p.add_argument('--mai-api-base',default='')
 p.add_argument('--remote-binary',default='/data/local/tmp/uinput_typeb_agent_compat')
 p.add_argument('--ui-mode',choices=('auto','element','grid'),default='auto')
 p.add_argument('--execute',action='store_true',help='MAY call API and move phone; require adapter interactive approval')
 p.add_argument('--score-after',action='store_true',help='Run exact P74 and V3 prefix replay on captured log; requires cluster')
 p.add_argument('--self-test',action='store_true',help='No phone/API/model')
 a=p.parse_args(argv)
 if a.self_test:
  for agent in AGENTS:
   a.agent=agent;a.project=Path('/tmp/dummy');a.expected_package='com.example.app'
   assert '--preflight-only' in command(a)
   assert '--task' not in command(a)
   a.task='Browse a page';assert '--task' in command(a,execute=True)
  print('GENERALIZATION RUNNER SELF-TEST PASS (3 agent adapter contracts, offline)')
  return 0
 if a.score_after and (not a.execute or a.task_cluster is None):
  p.error('--score-after needs --execute and PREDECLARED --task-cluster 0..4')
 if a.execute and (not a.task_id or not a.task.strip()):
  p.error('--execute requires --task-id and --task')
 if not 1<=a.max_steps<=60 or not 1<=a.max_actions<=60:p.error('budgets must be 1..60')
 if not a.expected_package.startswith(('com.','org.')):p.error('explicit Android package ID required')
 a.project=a.project.expanduser().resolve()
 source=ROOT/'adapters'/AGENTS[a.agent][0]
 print('MODE:','EXECUTE WITH INTERACTIVE APPROVAL' if a.execute else 'READ-ONLY PHONE PREFLIGHT',flush=True)
 print('ADAPTER:',source,'SHA256:',sha256(source),flush=True)
 pre=subprocess.run(command(a),check=False)
 if pre.returncode or not a.execute:
  return pre.returncode
 # Snapshot only the agent's native run output folder. No invented session identity.
 subdir=AGENTS[a.agent][1];outroot=a.project/'real_device_online'/subdir
 before={x.name for x in outroot.iterdir() if x.is_dir()} if outroot.is_dir() else set()
 print('PREFLIGHT PASS; native adapter requests its own approval before actions.',flush=True)
 started=dt.datetime.now(dt.timezone.utc).isoformat()
 run=subprocess.run(command(a,execute=True),check=False)
 after={x.name for x in outroot.iterdir() if x.is_dir()} if outroot.is_dir() else set()
 created=sorted(after-before)
 if len(created)!=1:
  print('NO UNIQUE RUN DIRECTORY: preserve evidence, do not guess:',created,file=sys.stderr)
  return run.returncode or 3
 out=outroot/created[0]
 manifest={
  'schema':'csg_real_device_generalization_v1','agent':a.agent,
  'task_id':a.task_id,'task':a.task,'expected_package':a.expected_package,
  'declared_original_task_cluster':a.task_cluster,
  'author_eligible':a.task_cluster is not None,
  'started_utc':started,'adapter_sha256':sha256(source),
  'agent_returncode':run.returncode,'shadow_only':True,
  'task_success':'NOT_VERIFIED'}
 (out/'generalization_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
 print('RUN RECORD:',out,flush=True)
 if a.score_after:
  log=out/'virtual_events_normalized.log'
  if not log.is_file():
   print('MISSING REAL TYPE-B LOG; refusing synthetic replay.',file=sys.stderr)
   return run.returncode or 4
  rc=subprocess.run([sys.executable,str(ROOT/'dual_replay.py'),'--project',str(a.project),
     '--log',str(log),'--task-cluster',str(a.task_cluster),
     '--session-id',a.task_id,'--out',str(out/'dual_prefix_scores.json')],check=False).returncode
  if rc:print('DUAL REPLAY FAILED; native logs preserved, no fallback.',file=sys.stderr)
  return run.returncode or rc
 return run.returncode

if __name__=='__main__':raise SystemExit(cli())
