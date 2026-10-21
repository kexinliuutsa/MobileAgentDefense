import argparse
import hashlib
import json
import subprocess
import sys
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import roc_auc_score, average_precision_score, accuracy_score, balanced_accuracy_score, confusion_matrix, brier_score_loss
from .core import ROOT, dump, threshold, HumanReference, FakeRules, head_scores, scores
SEED=20261014
PROJECT=ROOT.parents[2]
POOL=PROJECT/'02_rebuilt_benchmark/P6_frozen_paper_dataset/main_evaluation_pool_1770.csv'
REPORT=ROOT/'reports'
ART=ROOT/'artifacts'

def build():
    subprocess.run([sys.executable,str(ROOT.parent/'crossscaleguard_offline_v2/run.py'),'--mode','features','--pool',str(POOL),'--out',str(REPORT/'features_1770.csv')],check=True)
    d=pd.read_csv(REPORT/'features_1770.csv', float_precision="round_trip")
    valid=np.logical_and.reduce([d[k].eq('ok') for k in ('parse_status','session_feature_status','cross_feature_status')])
    x=d.loc[valid].copy()
    if len(d)!=1770 or len(x)!=1764: raise ValueError('Unexpected feature validation counts')
    if not x.label.isin(['agent','human']).all(): raise ValueError('Unknown label')
    x['y']=x.label.map({'human':0,'agent':1})
    schema={'session_54d':[c for c in x if c.startswith('session_') and c not in ('session_id','session_feature_status')],
            'strict_cross_17d':[c for c in x if c.startswith('cross_') and c!='cross_feature_status'],
            'metadata_inputs':['n_actions'],'report_only':['condition_final','agent_final','session_id','log_path','label'],
            'fusion_inputs':['session_score','strict_score','human_reference_score','fake_artifact_score','n_actions']}
    assert len(schema['session_54d'])==54 and len(schema['strict_cross_17d'])==17
    cols=schema['session_54d']+schema['strict_cross_17d']+['n_actions']
    assert np.isfinite(x[cols].to_numpy(float)).all()
    x.to_csv(REPORT/'dataset_valid_1764.csv',index=False)
    d.loc[~valid].to_csv(REPORT/'excluded_rows.csv',index=False)
    dump(ART/'feature_schema.json',schema)
    dump(REPORT/'dataset_summary.json',{'total':len(d),'valid':len(x),'excluded':int((~valid).sum()),'labels':x.label.value_counts().to_dict(),'conditions':x.condition_final.value_counts(dropna=False).to_dict(),'pool_sha256':hashlib.sha256(POOL.read_bytes()).hexdigest()})

def candidate(name):
    if name=='logistic': return make_pipeline(RobustScaler(),LogisticRegression(max_iter=5000,class_weight='balanced',random_state=SEED))
    if name=='hist_gradient_boosting': return HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=15,l2_regularization=1,random_state=SEED)
    return ExtraTreesClassifier(n_estimators=160,min_samples_leaf=3,class_weight='balanced',random_state=SEED,n_jobs=2)

def calibrated(est): return CalibratedClassifierCV(estimator=est,method='sigmoid',cv=3,n_jobs=1)

def metrics(y,s,t):
    y=np.asarray(y); p=np.asarray(s)>=t
    tn,fp,fn,tp=confusion_matrix(y,p,labels=[0,1]).ravel()
    return {'n':len(y),'n_human':int((y==0).sum()),'n_agent':int((y==1).sum()),
      'AUROC':roc_auc_score(y,s) if len(np.unique(y))==2 else None,
      'AUPRC':average_precision_score(y,s) if len(np.unique(y))==2 else None,
      'accuracy':accuracy_score(y,p),'balanced_accuracy':balanced_accuracy_score(y,p) if len(np.unique(y))==2 else None,
      'agent_recall':tp/(tp+fn) if tp+fn else None,'human_FPR':fp/(fp+tn) if fp+tn else None,
      'threshold':t,'TN':int(tn),'FP':int(fp),'FN':int(fn),'TP':int(tp)}

def fit(train,val,schema,protocol,summary):
    y=train.y.to_numpy(); bundle={}; names={}
    for head,key in [('session','session_54d'),('strict','strict_cross_17d')]:
        ranking=[]
        for name in ['logistic','hist_gradient_boosting','extra_trees']:
            model=calibrated(candidate(name)).fit(train[schema[key]],y)
            s=model.predict_proba(val[schema[key]])[:,1]
            m=metrics(val.y,s,.5)
            summary.append({'protocol':protocol,'head':head,'candidate':name,'split':'validation',**m})
            ranking.append((m['AUROC'],-m['human_FPR'],name,model))
        best=max(ranking,key=lambda r:r[:2]); names[head]=best[2]; bundle[head]=best[3]
    columns=schema['session_54d']+schema['strict_cross_17d']
    bundle['human']=HumanReference().fit(train[columns].to_numpy(float),y)
    bundle['fake']=FakeRules().fit(train,y,columns+['n_actions'])
    oof=np.zeros((len(train),5))
    for ti,vi in StratifiedKFold(3,shuffle=True,random_state=SEED).split(train,y):
        tr=train.iloc[ti]; fold={}
        for head,key in [('session','session_54d'),('strict','strict_cross_17d')]:
            fold[head]=calibrated(candidate(names[head])).fit(tr[schema[key]],tr.y)
        fold['human']=HumanReference().fit(tr[columns].to_numpy(float),tr.y)
        fold['fake']=FakeRules().fit(tr,tr.y,columns+['n_actions'])
        oof[vi]=head_scores(fold,train.iloc[vi],schema)
    for head,z in [('fusion',oof),('pair',oof[:,:2])]:
        bundle[head]=calibrated(make_pipeline(RobustScaler(),LogisticRegression(max_iter=5000,class_weight='balanced',random_state=SEED))).fit(z,y)
    validation=scores(bundle,val,schema)
    thresholds={k:threshold(s,val.y) for k,s in validation.items()}
    return bundle, thresholds, names, validation

def split_ids(d,idx): return d.iloc[idx].row_index.astype(int).tolist()

def train():
    d=pd.read_csv(REPORT/'dataset_valid_1764.csv', float_precision="round_trip"); schema=json.loads((ART/'feature_schema.json').read_text())
    outer,test=train_test_split(np.arange(len(d)),test_size=.30,stratify=d.y,random_state=SEED)
    tr,va=train_test_split(outer,test_size=.25,stratify=d.iloc[outer].y,random_state=SEED)
    manifest={'seed':SEED,'stratified_train_test':{'train':split_ids(d,tr),'validation':split_ids(d,va),'test':split_ids(d,test)},'leave_one_condition_out':{}}
    summary=[]; protocol='stratified_train_test'
    bundle,ts,names,vs=fit(d.iloc[tr],d.iloc[va],schema,protocol,summary)
    for head in ('session','strict','human','fusion'): joblib.dump(bundle[head],ART/({'human':'human_reference_head'}.get(head,head+'_head')+'.joblib'))
    joblib.dump(bundle['pair'],ART/'session_strict_head.joblib')
    fake=bundle['fake'].export(); fake['validation_threshold']=ts['fake only']; dump(ART/'fake_artifact_calibration.json',fake)
    config={'csv_float_precision':'round_trip','seed':SEED,'sklearn_version':sklearn.__version__,'numpy_version':np.__version__,'label_mapping':{'agent':1,'human':0},'selected_candidates':names,'thresholds':ts,'target_human_FPR':.025,'selection':'highest validation AUROC, then lowest FPR at 0.5','probability_calibration':'sigmoid, 3-fold training-only CV','fusion_training':'3-fold out-of-fold training head scores; calibrated logistic fusion','split':'70% development / 30% test; development split 75% fitting / 25% validation','production_training_scope':'training partition only; no refit after threshold selection','conditions_are_features':False,'agents_are_features':False}
    config.update({'candidate_parameters':{'logistic':{'max_iter':5000,'class_weight':'balanced','scaler':'RobustScaler'},'hist_gradient_boosting':{'max_iter':100,'max_leaf_nodes':15,'l2_regularization':1},'extra_trees':{'n_estimators':160,'min_samples_leaf':3,'class_weight':'balanced','n_jobs':2}},'human_reference':{'scaler':'RobustScaler','neighbors':5,'PCA':False,'score':'human-training leave-self-out mean-kNN distance ECDF'},'fake_rules':{'lower_quantile':.01,'upper_quantile':.99,'scale':'human-training IQR floored at 0.001','n_actions_tail':'upper only'},'fusion':{'model':'RobustScaler + balanced LogisticRegression','max_iter':5000,'out_of_fold_splits':3},'split_counts':{'train':len(tr),'validation':len(va),'test':len(test)}})
    dump(ART/'training_config.json',config)
    records=[]; calibrations=[]
    def record(protocol,ids,b,thresholds,validation,val_ids):
        ss=scores(b,d.iloc[ids],schema)
        for head,s in ss.items():
            for idx,score in zip(ids,s):
                r=d.iloc[idx]
                records.append({'protocol':protocol,'head':head,'row_index':int(r.row_index),'session_id':r.session_id,'y':int(r.y),'agent_final':r.agent_final,'condition_final':r.condition_final,'score':float(score),'threshold':thresholds[head],'detected':int(score>=thresholds[head])})
        for head,s in validation.items():
            calibrations.append({'protocol':protocol,'head':head,'split':'validation',**metrics(d.iloc[val_ids].y,s,thresholds[head]),'brier_score':brier_score_loss(d.iloc[val_ids].y,s) if head not in ('human-reference only','fake only') else None,'score_is_probability':head not in ('human-reference only','fake only')})
    record(protocol,test,bundle,ts,vs,va)
    for condition in sorted(d.condition_final.fillna('UNKNOWN').unique()):
        held=np.flatnonzero(d.condition_final.fillna('UNKNOWN').eq(condition)); dev=np.flatnonzero(~d.condition_final.fillna('UNKNOWN').eq(condition))
        if d.iloc[dev].y.nunique()<2:
            manifest['leave_one_condition_out'][condition]={'status':'not_estimable','reason':'Holding out Human removes all human training/validation examples; binary fitting and human-FPR calibration impossible','test':split_ids(d,held)}
            continue
        ti,vi=train_test_split(dev,test_size=.25,stratify=d.iloc[dev].y,random_state=SEED)
        p='leave_one_condition_out::'+condition
        print('Training',p,flush=True)
        b,t,n,v=fit(d.iloc[ti],d.iloc[vi],schema,p,summary)
        manifest['leave_one_condition_out'][condition]={'train':split_ids(d,ti),'validation':split_ids(d,vi),'test':split_ids(d,held),'thresholds':t,'selected_candidates':n}
        record(p,held,b,t,v,vi)
    dump(ART/'split_manifest.json',manifest)
    pd.DataFrame(summary).to_csv(REPORT/'train_summary.csv',index=False)
    pd.DataFrame(calibrations).to_csv(REPORT/'calibration_metrics.csv',index=False)
    pd.DataFrame(records).to_csv(REPORT/'heldout_predictions.csv',index=False)
    evaluate()

def evaluate():
    p=pd.read_csv(REPORT/'heldout_predictions.csv', float_precision="round_trip"); summary=[]; by=[]
    for (protocol,head),g in p.groupby(['protocol','head']):
        summary.append({'protocol':protocol,'head':head,'split':'test','threshold_policy':'human_fpr_calibrated',**metrics(g.y,g.score,g.threshold.iloc[0])})
        if protocol=='stratified_train_test':
            summary.append({'protocol':protocol,'head':head,'split':'test','threshold_policy':'default_0.5',**metrics(g.y,g.score,.5)})
        for key in ('condition_final','agent_final'):
            for value,gg in g.groupby(key,dropna=False):
                by.append({'protocol':protocol,'head':head,'group_type':key,'group':value,**metrics(gg.y,gg.score,gg.threshold.iloc[0])})
    manifest=json.loads((ART/'split_manifest.json').read_text())
    data=pd.read_csv(REPORT/'dataset_valid_1764.csv', float_precision="round_trip")
    for condition,fold in manifest['leave_one_condition_out'].items():
        if fold.get('status')!='not_estimable': continue
        held=data[data.row_index.isin(fold['test'])]
        for head in sorted(p['head'].unique()):
            summary.append({'protocol':'leave_one_condition_out::'+condition,'head':head,'split':'test','threshold_policy':'human_fpr_calibrated','status':'not_estimable','reason':fold['reason'],'n':len(held),'n_human':int((held.y==0).sum()),'n_agent':int((held.y==1).sum())})
            by.append({'protocol':'leave_one_condition_out::'+condition,'head':head,'group_type':'condition_final','group':condition,'status':'not_estimable','reason':fold['reason'],'n':len(held),'n_human':int((held.y==0).sum()),'n_agent':int((held.y==1).sum())})
    out=pd.DataFrame(summary); out['status']=out['status'].fillna('ok'); out.to_csv(REPORT/'ablation_metrics.csv',index=False)
    out[out['head']=='full fusion'].to_csv(REPORT/'evaluation_summary.csv',index=False)
    groups=pd.DataFrame(by); groups['status']=groups['status'].fillna('ok'); groups.to_csv(REPORT/'by_condition_metrics.csv',index=False)
    p[p.y!=p.detected].to_csv(REPORT/'error_cases.csv',index=False)
    print(out[out['head']=='full fusion'].to_string(index=False),flush=True)
