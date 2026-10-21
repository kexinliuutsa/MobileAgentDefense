#!/usr/bin/env python3
import argparse
import csv
import json
import sys
from pathlib import Path
import joblib
import pandas as pd
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from crossscaleguard_v3.core import FakeRules, head_scores
from crossscaleguard_v3.bridge import extractor

def load():
    a=ROOT/'artifacts'
    config=json.loads((a/'training_config.json').read_text())
    schema=json.loads((a/'feature_schema.json').read_text())
    b={k:joblib.load(a/f) for k,f in [('session','session_head.joblib'),('strict','strict_head.joblib'),('human','human_reference_head.joblib'),('fusion','fusion_head.joblib')]}
    b['fake']=FakeRules.load(json.loads((a/'fake_artifact_calibration.json').read_text()))
    return b,config,schema

def predict(path,b,config,schema):
    payload=extractor()(path)
    result={'detected':None,'final_score':None,'threshold':config['thresholds']['full fusion'],
            'session_score':None,'strict_score':None,'human_reference_score':None,'fake_artifact_score':None,
            'n_actions':payload['n_actions'],**{k:payload[k] for k in ('parse_status','session_feature_status','cross_feature_status')}}
    if any(payload[k]!='ok' for k in ('parse_status','session_feature_status','cross_feature_status')):
        result.update(status='feature_error',decision_trace=json.dumps({'reason':'incomplete features; abstain','errors':payload.get('errors',{})}))
        return result
    row={'session_'+k:v for k,v in payload['session_features'].items()}
    row.update({'cross_'+k:v for k,v in payload['cross_features'].items()}); row['n_actions']=payload['n_actions']
    h=head_scores(b,pd.DataFrame([row]),schema)
    s=float(b['fusion'].predict_proba(h)[0,1]); t=result['threshold']
    result.update(status='ok',detected=bool(s>=t),final_score=s)
    result.update(dict(zip(schema['fusion_inputs'][:4],map(float,h[0,:4]))))
    result['decision_trace']=json.dumps({'rule':'final_score >= validation-frozen threshold','score':s,'threshold':t,'calibration_target_human_FPR':config['target_human_FPR'],'model':'CrossScaleGuard-Offline-v3'})
    return result

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--mode',choices=['metadata','predict'],required=True)
    source=parser.add_mutually_exclusive_group(); source.add_argument('--log',type=Path); source.add_argument('--pool',type=Path)
    parser.add_argument('--out',type=Path); args=parser.parse_args()
    if args.mode=='metadata':
        print(json.dumps({'name':'CrossScaleGuard-Offline-v3','training_config':json.loads((ROOT/'artifacts/training_config.json').read_text()),'feature_schema':json.loads((ROOT/'artifacts/feature_schema.json').read_text()),'feature_dependency':'sibling v2 parser/adapter/native features only'},indent=2)); return
    if not args.log and not args.pool: parser.error('--log or --pool required')
    if args.pool and not args.out: parser.error('--out required for pool')
    b,c,s=load()
    if args.log:
        result=predict(args.log,b,c,s); text=json.dumps(result,indent=2,allow_nan=False)
        if args.out: args.out.parent.mkdir(parents=True,exist_ok=True); args.out.write_text(text+'\n')
        print(text); return
    rows=[]; project=ROOT.parents[2]
    with args.pool.open(newline='',encoding='utf-8-sig') as stream:
        for i,row in enumerate(csv.DictReader(stream)):
            path=None
            for key in ('extracted_path','log_path','path','source_path','gesture_log_path','file_path'):
                if not row.get(key): continue
                p=Path(row[key]).expanduser()
                choices=[p] if p.is_absolute() else [project/p,args.pool.resolve().parent/p,Path.cwd()/p]
                path=next((p for p in choices if p.is_file()),choices[0])
                if path.is_file(): break
            result=predict(path or '',b,c,s)
            rows.append({'row_index':i,**{k:row.get(k,'') for k in ('session_id','label','condition_final','agent_final')},**result})
    args.out.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(args.out,index=False)
    print(json.dumps({'rows':len(rows),'predicted':sum(r['status']=='ok' for r in rows),'output':str(args.out)}))
if __name__=='__main__': main()
