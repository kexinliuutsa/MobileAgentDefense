#!/usr/bin/env python3
"""Read-only P75: reproduce author outer + inner scaler statistics on original cluster Swipe rows.
No SVM/XGB fitting or thresholds, no evaluation-pool statistics. Separate reports.
"""
import argparse, json, re, sys, hashlib
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

CLUSTERS={
 'social_media':['今日头条','微博','小红书','知乎'],
 'shopping':['jd','淘宝','菜鸟裹裹','美团','eleme'],
 'video_streaming':['iqiyi','哔哩哔哩','qqmusic'],
 'trip_planning':['ctrip','高德地图','航旅纵横','去哪儿'],
 'office_learning':['腾讯文档','腾讯会议','有道词典','好大夫'],
}
HUMAN_INDICES=[2,3,4,33,34,35,36]
AGENT_INDICES=[5,7,9,20]

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--project',type=Path,default=Path.cwd())
 ap.add_argument('--author',type=Path,default=Path.home()/'Desktop/Passing-the-Turing-Test-on-Screen-Agent-Humanization-Benchmark-main')
 ap.add_argument('--fail-on-mismatch',action='store_true')
 args=ap.parse_args()
 project=args.project.expanduser().resolve();author=args.author.expanduser().resolve()
 bundle_path=project/'06_paper_tables/P68_ORIGINAL_CLUSTER_NATIVE_SESSION_TABLE/P73_AUTHOR_NATIVE_RECOVERY/candidate_outer_scalers_all_clusters.joblib'
 if not bundle_path.is_file():raise FileNotFoundError(bundle_path)
 sys.path.insert(0,str(author))
 import analysis.lib.gesture_log_reader_utils as reader
 from analysis.lib.gesture_log_reader_utils import rectify_timestamp_idx
 from analysis.processing.extract_feature_of_swipes import deprecated_cleanse_into_swipe,build_features_dataframe
 from analysis.processing.calculate_roc_auc_from_feature import get_numeric_feature_column_names,get_feature_columns
 data=pd.read_excel(author/'Formated_Data_Renamed.xlsx',header=0,index_col=None,dtype=str)
 names=list(data.columns)
 people={'humanized_agents':[names[i] for i in AGENT_INDICES],'humans':[names[i] for i in HUMAN_INDICES]}
 expected=set(a for v in CLUSTERS.values() for a in v)
 if set(data['app'].dropna().astype(str))!=expected:raise ValueError('Author app clusters changed')
 models=joblib.load(author/'humanized_swipe_classifiers.pkl')
 outer=joblib.load(bundle_path)
 if set(outer)!=set(range(5)) or set(models)!=set(range(5)):raise ValueError('Missing expected cluster keys')
 files=defaultdict(list)
 for p in author.rglob('gesture_recording_*.log'):
  m=re.fullmatch(r'gesture_recording_(\d{8}_\d{6})\.log',p.name)
  if m:files[m.group(1)].append(p)
 out=project/'06_paper_tables/P68_ORIGINAL_CLUSTER_NATIVE_SESSION_TABLE/P75_ORIGINAL_SCALER_EQUIVALENCE_AUDIT'
 out.mkdir(parents=True,exist_ok=True)
 summaries=[];features=[];coverage=[]
 for cid,(cname,apps) in enumerate(CLUSTERS.items()):
  taskset=set(data.index[data['app'].isin(apps)])
  row_batches=[];yvals=[];failed=0;skipped=0;n_sessions=0
  print(f'CLUSTER {cid} {cname} reading original training Swipe rows',flush=True)
  for typ in ('humanized_agents','humans'):
   stamps=rectify_timestamp_idx(data,people[typ])
   for person in people[typ]:
    for idx,ts in stamps[person]:
     if idx not in taskset:continue
     n_sessions+=1
     paths=files.get(ts,[])
     if len(paths)!=1:
      coverage.append({'cluster':cid,'timestamp':ts,'participant':person,'status':f'FILE_COUNT_{len(paths)}'})
      failed+=1;continue
     original_finder=reader.file_finder
     def finder(search_scope,file_name,found=paths[0]):
      if file_name!=found.name:raise ValueError('Unexpected filename')
      return found
     try:
      reader.file_finder=finder
      result=reader.session_noexcept_handling(ts)
     except Exception as ex:
      coverage.append({'cluster':cid,'timestamp':ts,'participant':person,'status':'EXCEPTION','error':repr(ex)[:150]})
      failed+=1;continue
     finally:
      reader.file_finder=original_finder
     if result is None:
      skipped+=1
      coverage.append({'cluster':cid,'timestamp':ts,'participant':person,'status':'AUTHOR_SKIPPED'})
      continue
     _,gestures=result
     try:
      swipe=[g for act in gestures if (g:=deprecated_cleanse_into_swipe(act)) is not None]
      if swipe:
       frame=build_features_dataframe([(typ,swipe)])
       cols=get_numeric_feature_column_names(frame)
       X=get_feature_columns(frame,cols)
       if cols!=list(models[cid][0].feature_names_in_):raise ValueError('Feature order mismatch')
       row_batches.append(X)
       yvals.extend([1 if typ=='humanized_agents' else 0]*len(X))
      coverage.append({'cluster':cid,'timestamp':ts,'participant':person,'status':'OK','swipe_rows':len(swipe)})
     except Exception as ex:
      failed+=1
      coverage.append({'cluster':cid,'timestamp':ts,'participant':person,'status':'FEATURE_ERROR','error':repr(ex)[:150]})
  if not row_batches:raise RuntimeError(f'No data cluster {cid}')
  X=pd.concat(row_batches,ignore_index=True);y=np.asarray(yvals,dtype=int)
  # The author first applies StandardScaler to the FULL filtered cluster dataframe,
  # then uses 70/30 stratified train_test_split on standardized rows.
  outer_rebuilt=StandardScaler().fit(X)
  z=pd.DataFrame(outer_rebuilt.transform(X),columns=X.columns,index=X.index)
  xtrain,xtest,ytrain,ytest=train_test_split(z,y,test_size=0.3,random_state=42,stratify=y)
  inner_rebuilt=StandardScaler().fit(xtrain)
  inner_stored=models[cid][0].named_steps['standardscaler']
  candidate=outer[cid]
  raw_n=int(len(X));stored_n=int(np.asarray(inner_stored.n_samples_seen_).max())
  n_match=len(xtrain)==stored_n
  feature_cols=list(X.columns)
  mu_diff=np.abs(inner_rebuilt.mean_-inner_stored.mean_)
  var_diff=np.abs(inner_rebuilt.var_-inner_stored.var_)
  scale_diff=np.abs(inner_rebuilt.scale_-inner_stored.scale_)
  outer_mu_diff=np.abs(outer_rebuilt.mean_-np.asarray(candidate['mean']))
  outer_scale_diff=np.abs(outer_rebuilt.scale_-np.asarray(candidate['scale']))
  max_mean=float(mu_diff.max()); max_var=float(var_diff.max());max_scale=float(scale_diff.max())
  candidate_match=bool(np.allclose(outer_rebuilt.mean_,candidate['mean'],rtol=1e-12,atol=1e-10) and np.allclose(outer_rebuilt.scale_,candidate['scale'],rtol=1e-12,atol=1e-10))
  strict=bool(n_match and failed==0 and candidate_match and np.allclose(inner_rebuilt.mean_,inner_stored.mean_,rtol=1e-8,atol=1e-8) and np.allclose(inner_rebuilt.var_,inner_stored.var_,rtol=1e-8,atol=1e-8) and np.allclose(inner_rebuilt.scale_,inner_stored.scale_,rtol=1e-8,atol=1e-8))
  entry={'cluster':cid,'cluster_name':cname,'source_sessions':n_sessions,'author_skipped_sessions':skipped,'read_errors':failed,'all_swipe_rows':raw_n,'agent_swipes':int(y.sum()),'human_swipes':int(len(y)-y.sum()),'rebuilt_train_swipes':len(xtrain),'stored_inner_train_swipes':stored_n,'train_n_match':n_match,'p73_outer_stats_match':candidate_match,'max_abs_outer_mean_difference_from_P73':float(outer_mu_diff.max()),'max_abs_outer_scale_difference_from_P73':float(outer_scale_diff.max()),'max_abs_inner_mean_diff':max_mean,'max_abs_inner_var_diff':max_var,'max_abs_inner_scale_diff':max_scale,'inner_n_samples_seen_raw':str(inner_stored.n_samples_seen_),'verdict':'STRONG_NUMERIC_EQUIVALENCE' if strict else 'NOT_EXACT_VERIFIED'}
  summaries.append(entry)
  for i,f in enumerate(feature_cols):
   features.append({'cluster':cid,'feature':f,'rebuilt_inner_mean':float(inner_rebuilt.mean_[i]),'stored_inner_mean':float(inner_stored.mean_[i]),'abs_mean_diff':float(mu_diff[i]),'rebuilt_inner_var':float(inner_rebuilt.var_[i]),'stored_inner_var':float(inner_stored.var_[i]),'abs_var_diff':float(var_diff[i]),'rebuilt_inner_scale':float(inner_rebuilt.scale_[i]),'stored_inner_scale':float(inner_stored.scale_[i]),'abs_scale_diff':float(scale_diff[i])})
  print(' RESULT',entry['verdict'],'swipes',raw_n,'train',len(xtrain),'stored',stored_n,'max mean diff',f'{max_mean:.8g}','max scale diff',f'{max_scale:.8g}',flush=True)
 pd.DataFrame(summaries).to_csv(out/'cluster_equivalence_summary.csv',index=False)
 pd.DataFrame(features).to_csv(out/'per_feature_inner_scaler_comparison.csv',index=False)
 pd.DataFrame(coverage).to_csv(out/'training_session_coverage.csv',index=False)
 manifest={'status':'READ_ONLY_AUDIT_NO_CLASSIFIER_FIT','p73_sha256':sha(bundle_path),'author_model_sha256':sha(author/'humanized_swipe_classifiers.pkl'),'xlsx_sha256':sha(author/'Formated_Data_Renamed.xlsx'),'results':summaries}
 (out/'audit_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False,default=str))
 print('\nP75 CLUSTER EQUIVALENCE SUMMARY\n',pd.DataFrame(summaries).to_string(index=False),flush=True)
 print('\nSAVED:',out,flush=True)
 print('NOTE: numeric scaler equivalence is strong evidence, not a cryptographic proof of identical training rows.')
 if args.fail_on_mismatch and any(r['verdict']!='STRONG_NUMERIC_EQUIVALENCE' for r in summaries):sys.exit(2)

if __name__=='__main__':main()