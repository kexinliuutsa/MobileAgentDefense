#!/usr/bin/env python3
"""Single-command author baseline reconstruction + full 1770 audit. No retraining.
Runs P75 hard-gated validation before P74. Reports only FULL_POOL_1770.
"""
from pathlib import Path
import argparse, hashlib, json, subprocess, sys, ast
import pandas as pd
import numpy as np
import joblib

def digest(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def require(v, msg):
 if not v: raise AssertionError(msg)

def run(cmd, cwd):
 print('\nRUN:', ' '.join(map(str,cmd)),flush=True)
 subprocess.run([str(c) for c in cmd],cwd=cwd,check=True)

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--project',type=Path,default=Path.cwd())
 args=parser.parse_args()
 root=args.project.expanduser().resolve()
 author=root/'00_original/author_repo'
 original=Path.home()/'Desktop/Passing-the-Turing-Test-on-Screen-Agent-Humanization-Benchmark-main'
 if not (original/'analysis_playground.ipynb').is_file(): raise FileNotFoundError(original/'analysis_playground.ipynb')
 srcdir=root/'scripts'
 P75=srcdir/'P75_verify_author_scaler_equivalence.py'
 P74=srcdir/'P74_original_author_reconstructed_scaler_1770.py'
 for p in [P75,P74,original/'analysis/processing/judge_library.py',original/'analysis/processing/calculate_roc_auc_from_feature.py',original/'analysis/processing/extract_feature_of_swipes.py', original/'analysis/lib/gesture_log_reader_utils.py',original/'analysis/lib/feature_library.py',original/'analysis/lib/motionevent_classes.py',original/'Formated_Data_Renamed.xlsx',original/'humanized_swipe_classifiers.pkl',original/'raw_tap_classifier_us_across_clusters.pkl',original/'interval_classifier_microseconds_across_clusters.pkl']:
  require(p.is_file(),f'Missing required original dependency: {p}')
 source=(original/'analysis/processing/calculate_roc_auc_from_feature.py').read_text()
 tree=ast.parse(source)
 func=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='calculate_svm_and_xgboost')
 code=ast.get_source_segment(source,func)
 for marker in ('scaler.fit_transform(X)','train_test_split(','make_pipeline(StandardScaler(), SVC(','xgb_clf.fit(X_train, y_train)'):
  require(marker in code, f'Original author training sequence changed: {marker}')
 judge_src=(original/'analysis/processing/judge_library.py').read_text()
 judge_tree=ast.parse(judge_src)
 cls=next(n for n in judge_tree.body if isinstance(n,ast.ClassDef) and n.name=='UltimateClassifier')
 pfunc=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='predict')
 judge_code=ast.get_source_segment(judge_src,pfunc)
 for marker in ('predict_log_proba(', 'cumulant_log_odds += swipe_log_odds', 'cumulant_log_odds += tap_log_odds', 'cumulant_log_odds += interval_log_odds'):
  require(marker in judge_code,'Author Ultimate implementation changed: '+marker)
 print('PASS: Original author model-training and Ultimate source signature',flush=True)
 frozen_paths={k:original/k for k in ['humanized_swipe_classifiers.pkl','raw_tap_classifier_us_across_clusters.pkl','interval_classifier_microseconds_across_clusters.pkl']}
 before={k:digest(v) for k,v in frozen_paths.items()}
 for k,p in frozen_paths.items():
  copy=author/k
  require(copy.is_file() and digest(copy)==before[k],f'Author original-vs-project weight mismatch: {k}')
 m=joblib.load(original/'humanized_swipe_classifiers.pkl')
 require(set(m)==set(range(5)),'Original five cluster keys missing')
 for cid,(svm,xgb) in m.items():
  require(list(svm.classes_)==[0,1] and list(xgb.classes_)==[0,1],f'Class order mismatch cluster {cid}')
  require(len(svm.feature_names_in_)==24 and len(xgb.feature_names_in_)==24,f'24-d feature mismatch cluster {cid}')
  require(list(svm.feature_names_in_)==list(xgb.feature_names_in_),f'Feature order mismatch {cid}')
 print('PASS: Original weights SHA256 identical between source and staged repo; clusters/classes/features',flush=True)
 run([sys.executable,'-B',P75,'--project',root,'--author',original,'--fail-on-mismatch'],root)
 p75=root/'06_paper_tables/P68_ORIGINAL_CLUSTER_NATIVE_SESSION_TABLE/P75_ORIGINAL_SCALER_EQUIVALENCE_AUDIT'
 eq=pd.read_csv(p75/'cluster_equivalence_summary.csv')
 require(len(eq)==5 and set(eq.cluster)==set(range(5)),'P75 cluster coverage')
 require(eq.verdict.eq('STRONG_NUMERIC_EQUIVALENCE').all(),'P75 does not prove numerical equivalence')
 require(eq.train_n_match.astype(str).str.lower().eq('true').all(),'Train counts mismatch')
 require(eq.p73_outer_stats_match.astype(str).str.lower().eq('true').all(),'Reconstructed scaler mismatch')
 require(eq.read_errors.eq(0).all(),'Training source read errors')
 for c in ('max_abs_inner_mean_diff','max_abs_inner_var_diff','max_abs_inner_scale_diff'):
  require(float(eq[c].abs().max())<=1e-8,c+' is not numerically equal')
 manifest=json.loads((p75/'audit_manifest.json').read_text())
 outer=root/'06_paper_tables/P68_ORIGINAL_CLUSTER_NATIVE_SESSION_TABLE/P73_AUTHOR_NATIVE_RECOVERY/candidate_outer_scalers_all_clusters.joblib'
 require(manifest['p73_sha256']==digest(outer),'P75-reported outer scaler hash mismatch')
 require(manifest['author_model_sha256']==before['humanized_swipe_classifiers.pkl'],'P75 evaluated different model')
 print('PASS: P75 original training-split scaler statistics match all 5 saved SVM internal scalers',flush=True)
 run([sys.executable,'-B',P74,'--project',root],root)
 dest=root/'06_paper_tables/P74_CANDIDATE_SCALER_AUTHOR_ORIGINAL_MODELS'
 pred=pd.read_csv(dest/'paired_session_predictions.csv',dtype={'session_id':str})
 table=pd.read_csv(dest/'main_table.csv');fam=pd.read_csv(dest/'attack_family_table.csv');errors=pd.read_csv(dest/'failures.csv')
 log=json.loads((dest/'audit.json').read_text())
 require(len(pred)==1770,'Not 1770 sessions')
 require(pred.row_index.tolist()==list(range(1770)),'Rows not in frozen 1770 sequence')
 require(pred.session_id.is_unique,'Duplicate session IDs')
 require(log['attempted']==1770 and log['candidate_outer_scaler_sha256']==digest(outer),'P74 audit provenance mismatch')
 require(log['source_sha256']==digest(P74),'P74 running script and output hash mismatch')
 require(log['errors']==len(errors),'P74 error count inconsistency')
 require(len(table[table.split=='FULL_POOL_1770'])==6,'Missing full pool six-model rows')
 require(set(pred.label)=={'agent','human'},'Invalid ground-truth labels')
 require(set(pred.cluster.dropna().astype(int)).issubset(set(range(5))),'Invalid cluster ID')
 require(not (pred.ultimate_pred.notna() & pred.cluster.isna()).any(),'Ultimate scores on unmatched cluster')
 for name,col in [('Swipe SVM','svm_pred'),('Swipe XGB','xgb_pred'),('Tap','tap_pred'),('Interval','interval_pred'),('Author Ultimate','ultimate_pred'),('Ours V3','v3_pred')]:
  q=pred[pred[col].notna()]
  require(q[col].isin([0,1]).all(),f'{name}: non-binary predictions')
  tp=int(((q.label=='agent') & (q[col]==1)).sum());fn=int(((q.label=='agent') & (q[col]==0)).sum());fp=int(((q.label=='human') & (q[col]==1)).sum());tn=int(((q.label=='human') & (q[col]==0)).sum())
  r=table[(table.split=='FULL_POOL_1770') & (table.method==name)]
  require(len(r)==1,f'Missing model row: {name}');r=r.iloc[0]
  require(all(int(r[k])==v for k,v in [('N',len(q)),('TP',tp),('FN',fn),('FP',fp),('TN',tn)]),f'Metrics differ from row-level predictions: {name}')
 # Frozen V3 must exactly match previously packaged predictions used by P74.
 reference=pd.read_csv(root/'06_paper_tables/P64_RETRAINED_GLOBAL_AUTHOR_COMPONENTS_1770/paired_predictions_1770.csv',dtype={'session_id':str})
 require(reference.session_id.tolist()==pred.session_id.tolist(),'Frozen V3 IDs differ')
 a=pd.to_numeric(reference.v3_pred,errors='coerce');b=pd.to_numeric(pred.v3_pred,errors='coerce')
 require(np.array_equal(a.fillna(-999).to_numpy(),b.fillna(-999).to_numpy()),'Frozen V3 predictions changed')
 after={k:digest(v) for k,v in frozen_paths.items()}
 require(before==after,'Original author model weights modified during audit')
 report={'status':'PASS_RECONSTRUCTED_AUTHOR_1770_AUDIT','interpretation':'Original released weights, author native scoring code, author-derived P73 reconstructed scaler with P75 strong numeric equivalence, P74 full-pool evaluation. Not identical to unmodified released judge invocation because original judge omitted external scaler.', 'total_sessions':1770,'successfully_assigned_clusters':int(pred.cluster.notna().sum()),'evaluation_errors':int(len(errors)),'model_sha256':before,'outer_scaler_sha256':digest(outer),'p74_script_sha256':digest(P74),'training_cluster_verdicts':eq[['cluster','verdict']].to_dict('records'),'full_pool_main_table':table[table.split=='FULL_POOL_1770'].to_dict('records')}
 report_path=dest/'FINAL_AUTHOR_1770_AUDIT.json';report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False))
 print('\n'+'='*90+'\nFINAL RESULT: PASS — RECONSTRUCTED AUTHOR BASELINE, FULL 1770 ONLY\n'+'='*90)
 print(table[table.split=='FULL_POOL_1770'].to_string(index=False))
 print('\nAttack family (full pool):')
 print(fam[fam.split=='FULL_POOL_1770'].pivot(index='family',columns='method',values='recall').round(4).to_string())
 print('\n'+'-'*90+'\nREPORT:',report_path,'\nFAILURES:',len(errors),'\nDISCLAIMER: Original source Ultimate.predict() contains no external scaler; this is verified training-preprocessing reconstruction, not an unmodified release inference call.')

if __name__=='__main__':
 try:main()
 except Exception as exc:
  print('\nFINAL AUTHOR 1770 AUDIT: FAIL:',type(exc).__name__,str(exc),file=sys.stderr)
  raise