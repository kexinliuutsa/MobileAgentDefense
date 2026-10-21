#!/usr/bin/env python3
"""Read-only P74 Author Ultimate + P10 Frozen V3 replay on identical REAL Type-B prefixes.

Original author model/scaler files stay external to GitHub. No retraining, no FPR
matching, no phone actions. A new app needs an independently verified cluster ID
for P74 comparison; never infer the cluster from detection results.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,math,re,sys,tempfile,time
from pathlib import Path

RELEASE=re.compile(rb'ABS_MT_TRACKING_ID\s+(?:ffffffff|-1)\b',re.I)
SYN=re.compile(rb'\bSYN_REPORT\b',re.I)

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for z in iter(lambda:f.read(1<<20),b''):h.update(z)
 return h.hexdigest()

def cuts(raw):
 out=[];offset=0;pending=False
 for line in raw.splitlines(keepends=True):
  offset+=len(line)
  if RELEASE.search(line):pending=True
  if pending and SYN.search(line):
   out.append(offset);pending=False
 if pending:raise ValueError('Unclosed Type-B release: do not synthesize touches')
 if not out or sorted(set(out))!=out:raise ValueError('No valid completed Type-B contacts')
 out[-1]=len(raw)
 return out

def author_end_scores(trace,events,start_us,end_us):
 n=len(events)
 if not n or len(trace)!=2*n-1:
  raise ValueError(f'Expected Author 2N-1 evidence events; got {len(trace)} for {n} gestures')
 out=[]
 for j,e in enumerate(events):
  if j and int(trace[2*j-1][0])!=int(start_us(e)):
   raise ValueError('Author interval event timestamp mismatch')
  if int(trace[2*j][0])!=int(end_us(e)):
   raise ValueError('Author gesture-end timestamp mismatch')
  z=float(trace[2*j][1])
  if not math.isfinite(z):raise ValueError('Nonfinite Author score')
  out.append(z)
 return out

def prerequisites(root):
 scripts=root/'scripts'
 for name in ('P20_four_model_runner.py','P31_hex_online.py','P31_hex_frame_adapter.py',
              'P74_original_author_reconstructed_scaler_1770.py'):
  if not (scripts/name).is_file():raise FileNotFoundError(f'P74 original bridge missing: {scripts/name}')
 author=root/'00_original'/'author_repo'
 scaler=root/'06_paper_tables'/'P68_ORIGINAL_CLUSTER_NATIVE_SESSION_TABLE'/'P73_AUTHOR_NATIVE_RECOVERY'/'candidate_outer_scalers_all_clusters.joblib'
 v3=root/'01_clean_code'/'offline_defenses'/'crossscaleguard_offline_v3'/'run.py'
 assets={
  author/'analysis/processing/judge_library.py':'6433b9261d1b7343a52cc7d51c9e153dabd53fb90fa5a5c75edf331a79895b19',
  author/'humanized_swipe_classifiers.pkl':'47b9517c8f1122b14a9f7b1f9694f3b8c065cc69909f99115a5e0a63cb5dd3ef',
  author/'raw_tap_classifier_us_across_clusters.pkl':'ebf2d307fb9f68606483019e405ab3e31a177f3f8156dae4658e0954220a2b3f',
  author/'interval_classifier_microseconds_across_clusters.pkl':'4af23a501f81e0905d56ab8d5b803a2c8242c0364e45e6eee07242c665ec7f3f',
  scaler:'855f33bdac5ce4fe49da528b87fe4e11024c155fcd13bc0092a079a54fbb57cb',
  v3:'c109f1324ed0266f78f43e103b050a5572114735a6dddb1d2f7cf714dc7c373c'
 }
 for path,digest in assets.items():
  if not path.is_file():raise FileNotFoundError('FROZEN INPUT MISSING: '+str(path))
  if sha(path)!=digest:raise RuntimeError('FROZEN INPUT SHA256 CHANGED: '+str(path))
 return scripts,author,scaler,v3,assets

def replay(root,log,task_cluster,session_id):
 raw=log.read_bytes();boundaries=cuts(raw)
 scripts,author,scaler,v3,assets=prerequisites(root)
 sys.dont_write_bytecode=True
 sys.path.insert(0,str(scripts))
 import P20_four_model_runner as p20
 import P31_hex_online as p31
 from P31_hex_frame_adapter import parse_log
 from P74_original_author_reconstructed_scaler_1770 import OuterScaledClassifier
 from analysis.lib.motionevent_classes import FingerEvent
 from analysis.lib.feature_library import startT_us,endT_us
 import joblib
 # Original repaired author loader and immutable upstream weights, NOT a proxy judge.
 judge,_=p31.load_original_author(root,author)
 scalers=joblib.load(scaler)
 if set(scalers)!=set(range(5)):raise RuntimeError('P73 must supply five outer scaler clusters')
 judge.classifiers_to_use_for_clusters={
  c:tuple(OuterScaledClassifier(clf,scalers[c]) for clf in judge.classifiers_to_use_for_clusters[c][:2])
  for c in range(5)}
 spec=importlib.util.spec_from_file_location('original_p10_v3_replay',v3)
 if not spec or not spec.loader:raise RuntimeError('Cannot import frozen P10')
 v3run=importlib.util.module_from_spec(spec);spec.loader.exec_module(v3run)
 bundle,conf,schema=v3run.load()
 if float(conf['thresholds']['full fusion'])!=0.8711460070813885:
  raise RuntimeError('Frozen V3 threshold changed')
 records=[];prev_count=0;previous_signatures=[]
 with tempfile.TemporaryDirectory(prefix='csg_real_device_dual_prefix_') as td:
  tmp=Path(td)/'prefix.log'
  for g,b in enumerate(boundaries,1):
   tmp.write_bytes(raw[:b])
   t=time.perf_counter(); z=parse_log(tmp)
   a_score=None;a_pred=None;a_count=None;a_status='abstain'
   if z.get('parse_status')=='ok' and len(z.get('gestures',[]))==len(z.get('actions',[])):
    events=p20.author_actions(z['gestures'],FingerEvent);a_count=len(events)
    if a_count>g or a_count<prev_count:raise RuntimeError('Noncausal Author action-count evolution')
    signatures=[(int(startT_us(e)),int(endT_us(e))) for e in events]
    if signatures[:len(previous_signatures)]!=previous_signatures:
     raise RuntimeError('Observed gesture timestamps changed after seeing future actions')
    previous_signatures=signatures;prev_count=a_count
    if events:
     trace=judge.predict((session_id,events),task_cluster,prior_log_odds=0.0)
     a_score=author_end_scores(trace,events,startT_us,endT_us)[-1]
     a_pred=int(a_score>0);a_status='ok'
   author_ms=(time.perf_counter()-t)*1000
   t=time.perf_counter();v=v3run.predict(tmp,bundle,conf,schema)
   v3_ms=(time.perf_counter()-t)*1000
   v_score=float(v['final_score']) if v.get('status')=='ok' else None
   v_pred=int(bool(v['detected'])) if v_score is not None else None
   records.append({'touch_g':g,'author_status':a_status,'author_n_actions':a_count,
      'author_score':a_score,'author_agent_pred':a_pred,'author_latency_ms':author_ms,
      'v3_status':str(v.get('status')),'v3_n_actions':v.get('n_actions'),
      'v3_score':v_score,'v3_agent_pred':v_pred,'v3_latency_ms':v3_ms})
 def first(name):
  return next((z['touch_g'] for z in records if z[name+'_agent_pred']==1),None)
 return {'schema':'csg_dual_replay_v1','source_log_sha256':sha(log),
  'session_id':session_id,'declared_original_task_cluster':task_cluster,
  'completed_physical_touches':len(boundaries),
  'asset_sha256':{str(p.relative_to(root)):h for p,h in assets.items()},
  'author_rule':'P74 original cumulative log Bayes evidence > 0 at equal prior',
  'v3_rule':'Original frozen Full Fusion >= 0.8711460070813885',
  'first_agent_alarm_touch':{'author':first('author'),'v3':first('v3')},
  'final_predictions':{'author':records[-1]['author_agent_pred'],'v3':records[-1]['v3_agent_pred']},
  'task_completion':'NOT_VERIFIED_INDEPENDENTLY','prefixes':records}

def self_test():
 raw=(b'ABS_MT_TRACKING_ID 00000001\nSYN_REPORT\n'
      b'ABS_MT_TRACKING_ID ffffffff\nSYN_REPORT\n'
      b'ABS_MT_TRACKING_ID 00000002\nSYN_REPORT\n'
      b'ABS_MT_TRACKING_ID ffffffff\nSYN_REPORT\n')
 assert len(cuts(raw))==2 and cuts(raw)[-1]==len(raw)
 assert author_end_scores([(3,0.1),(4,0.3),(7,1.2)],[(1,3),(4,7)],
       lambda x:x[0],lambda x:x[1])==[0.1,1.2]
 try:cuts(b'ABS_MT_TRACKING_ID 00000001\nSYN_REPORT\n')
 except ValueError:pass
 else:raise AssertionError('Open contact accepted')
 print('DUAL REPLAY SELF-TEST PASS: Type-B closure and native Author 2N-1 trace')

def cli(argv=None):
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--project',type=Path,default=Path.home()/'Desktop'/'GUI_AHB_PAPER_REBUILD')
 ap.add_argument('--log',type=Path)
 ap.add_argument('--task-cluster',type=int,choices=range(5))
 ap.add_argument('--session-id',default='real-device-shadow')
 ap.add_argument('--out',type=Path)
 ap.add_argument('--self-test',action='store_true')
 ap.add_argument('--preflight-only',action='store_true',help='Check local source, scaler and frozen model hashes, no loading')
 a=ap.parse_args(argv)
 if a.self_test:self_test();return 0
 root=a.project.expanduser().resolve()
 if a.preflight_only:
  prerequisites(root)
  print('P74/P10 PRE-FLIGHT PASS: all required original source and model hash checks; no API/phone')
  return 0
 if a.log is None or a.task_cluster is None:
  ap.error('REAL --log and independently PREDECLARED --task-cluster are required')
 log=a.log.expanduser().resolve()
 if not log.is_file():ap.error('Missing real capture log: '+str(log))
 z=replay(root,log,a.task_cluster,a.session_id)
 data=json.dumps(z,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
 if a.out:
  a.out.expanduser().resolve().parent.mkdir(parents=True,exist_ok=True)
  a.out.expanduser().resolve().write_text(data,encoding='utf-8')
  print('DUAL PREFIX REPLAY WRITTEN:',a.out)
 else:print(data)
 return 0

if __name__=='__main__':raise SystemExit(cli())
