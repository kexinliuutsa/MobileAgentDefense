#!/usr/bin/env python3
"""P74: original author classifiers with P73 reconstructed OUTER StandardScaler (candidate).

Swipe: one longest-duration swipe (tie: earliest); native SVM/XGB predict().
Tap: last tap's author original threshold log-odds, >0 is Agent.
Interval: last available inter-gesture interval's original threshold log-odds, >0.
Ultimate: original UltimateClassifier.predict(X, REAL task_cluster_id) final score >0.
V3: frozen P64 projected session outcome, unchanged.
No classifier fitting, threshold tuning, or FPR matching. Candidate scaler reconstruction, NOT exact-proven.
"""
from __future__ import annotations
import argparse, hashlib, json, sys, traceback
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import binomtest

NAMES={"Swipe SVM":"svm_pred","Swipe XGB":"xgb_pred","Tap":"tap_pred","Interval":"interval_pred","Author Ultimate":"ultimate_pred","Ours V3":"v3_pred"}

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def metrics(d,method,col):
    q=d.loc[d[col].notna()]
    y=q.label.eq('agent').to_numpy(); p=q[col].astype(int).to_numpy()
    tp=int((y&(p==1)).sum());fn=int((y&(p==0)).sum());fp=int((~y&(p==1)).sum());tn=int((~y&(p==0)).sum())
    recall=tp/(tp+fn) if tp+fn else np.nan;fpr=fp/(fp+tn) if fp+tn else np.nan
    return dict(method=method,N=len(q),Agent_N=tp+fn,Human_N=fp+tn,TP=tp,FN=fn,FP=fp,TN=tn,
                Accuracy=(tp+tn)/len(q) if len(q) else np.nan,Agent_Recall=recall,Human_FPR=fpr)

class OuterScaledClassifier:
    """Inference-only adapter. Original classifier and original judge.predict remain unchanged."""
    def __init__(self, original, stats):
        self.original = original
        self.names = list(stats["feature_names"])
        self.mean = np.asarray(stats["mean"], dtype=float)
        self.scale = np.asarray(stats["scale"], dtype=float)
        if len(self.names) != len(self.mean) or len(self.names) != len(self.scale):
            raise ValueError("Candidate scaler dimensionality mismatch")
        if not np.isfinite(self.mean).all() or not np.isfinite(self.scale).all() or np.any(self.scale <= 0):
            raise ValueError("Invalid scaler statistics")
        trained = list(original.feature_names_in_)
        if trained != self.names:
            raise ValueError("Feature names/order mismatch to original classifier")
    def _x(self, X):
        if list(X.columns) != self.names:
            raise ValueError("Input features do not match author order")
        y = (X[self.names].to_numpy(dtype=float) - self.mean) / self.scale
        if not np.isfinite(y).all():
            raise ValueError("Non-finite transformed features")
        return pd.DataFrame(y, columns=self.names, index=X.index)
    def predict(self, X):
        return self.original.predict(self._x(X))
    def predict_proba(self, X):
        return self.original.predict_proba(self._x(X))
    def predict_log_proba(self, X):
        return self.original.predict_log_proba(self._x(X))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,default=Path.cwd());ap.add_argument('--limit',type=int,default=0)
    a=ap.parse_args();root=a.project.expanduser().resolve()
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(root/'scripts'))
    import P20_four_model_runner as p20
    import P31_hex_online as p31
    from P31_hex_frame_adapter import parse_log
    # Original author loader and release artifacts; NO P64 fitted global weights.
    author=next((p for p in [root/'00_original/author_repo',Path.home()/'Desktop/Passing-the-Turing-Test-on-Screen-Agent-Humanization-Benchmark-main'] if (p/'analysis/processing/judge_library.py').is_file()),None)
    if author is None:raise FileNotFoundError('Original author repository missing')
    judge,_=p31.load_original_author(root,author)
    import joblib
    bundle_path=root/'06_paper_tables/P68_ORIGINAL_CLUSTER_NATIVE_SESSION_TABLE/P73_AUTHOR_NATIVE_RECOVERY/candidate_outer_scalers_all_clusters.joblib'
    if not bundle_path.is_file(): raise FileNotFoundError(bundle_path)
    scaler_bundle=joblib.load(bundle_path)
    if set(scaler_bundle) != set(range(5)): raise ValueError('Expected 5 recovered cluster scalers')
    judge.classifiers_to_use_for_clusters={
        cid: tuple(OuterScaledClassifier(clf, scaler_bundle[cid]) for clf in judge.classifiers_to_use_for_clusters[cid][:2])
        for cid in range(5)
    }
    print("P74: author original sklearn models + candidate P73 OUTER scalers; original Ultimate.predict unchanged",flush=True)
    print("P73 candidate scaler SHA256:",sha(bundle_path),flush=True)
    from analysis.lib.motionevent_classes import FingerEvent
    from analysis.lib.feature_library import is_tap,startT_us,endT_us
    from analysis.processing.extract_feature_of_swipes import build_features_dataframe
    from analysis.processing.calculate_roc_auc_from_feature import get_numeric_feature_column_names,get_feature_columns
    from analysis.processing.judge_library import get_log_odds_with_threshold_posterior

    pool_path=root/'02_rebuilt_benchmark/P6_frozen_paper_dataset/main_evaluation_pool_1770.csv'
    map_path=root/'reports/P22_fresh_native_online/P22_original_task_cluster_recovered.csv'
    p64=root/'06_paper_tables/P64_RETRAINED_GLOBAL_AUTHOR_COMPONENTS_1770'
    for f in [pool_path,map_path,p64/'paired_predictions_1770.csv',p64/'MODEL_FREEZE_MANIFEST.json']:
        if not f.is_file():raise FileNotFoundError(f)
    frozen=json.loads((p64/'MODEL_FREEZE_MANIFEST.json').read_text())
    for rel,digest in frozen['sha256_files'].items():
        f=p64/rel
        if not f.is_file() or sha(f)!=digest:raise RuntimeError('P64 V3 reference checksum failed: '+rel)
    pool=pd.read_csv(pool_path,dtype={'session_id':str},keep_default_na=False)
    assert len(pool)==1770 and not pool.session_id.duplicated().any()
    baseline=pd.read_csv(p64/'paired_predictions_1770.csv',dtype={'session_id':str})
    assert len(baseline)==1770 and list(baseline.row_index.astype(int))==list(range(1770))
    assert (baseline.session_id.to_numpy()==pool.session_id.to_numpy()).all()
    assert baseline.label.isin(['agent','human']).all()
    assert 'v3_pred' in baseline.columns
    mapping={};conflicts=[]
    m=pd.read_csv(map_path,keep_default_na=False)
    for row in m.itertuples(index=False):
        if str(row.task_match_status)!='MATCHED':continue
        idx=int(row.p6_row);cid=int(float(row.task_cluster))
        if idx in mapping and mapping[idx]!=cid:conflicts.append(idx)
        mapping[idx]=cid
    if conflicts:raise RuntimeError(f'Conflicting task cluster assignments: {conflicts[:10]}')
    print('P74 RECONSTRUCTED-OUTER-SCALER SESSION EVALUATION',flush=True)
    print('Original author source:',author,flush=True)
    print('Verified original cluster assignments:',len(mapping),'/ 1770',flush=True)
    print('Rules: longest swipe; last tap; last interval; original Ultimate final; frozen V3',flush=True)
    out=root/'06_paper_tables/P74_CANDIDATE_SCALER_AUTHOR_ORIGINAL_MODELS'
    if a.limit:out=out/f'SMOKE_{a.limit}'
    out.mkdir(parents=True,exist_ok=True)
    selected=[];errors=[];rows=[]
    target=pool.head(a.limit) if a.limit else pool
    for idx,r in enumerate(target.itertuples(index=False)):
        sid=str(r.session_id); label=str(r.label).lower(); family=str(r.condition_final)
        record=dict(row_index=idx,session_id=sid,label=label,family=family,cluster=mapping.get(idx,np.nan),
                    n_swipe=0,n_tap=0,n_interval=0,svm_pred=np.nan,xgb_pred=np.nan,tap_pred=np.nan,
                    interval_pred=np.nan,ultimate_pred=np.nan,v3_pred=baseline.iloc[idx].v3_pred)
        try:
            if idx not in mapping:
                errors.append(dict(row_index=idx,session_id=sid,stage='cluster',error='No verified original task cluster'))
                rows.append(record);continue
            cid=mapping[idx]
            if cid not in judge.classifiers_to_use_for_clusters or cid not in judge.tap_us_classifier or cid not in judge.interval_us_classifier:
                raise KeyError('Original author model missing cluster '+str(cid))
            path=p20.find_log(pool.iloc[idx].to_dict(),pool_path,root)
            if path is None:raise FileNotFoundError('Original gesture log not found')
            parsed=parse_log(path)
            if parsed.get('parse_status')!='ok' or not parsed['gestures'] or len(parsed['gestures'])!=len(parsed['actions']):
                raise RuntimeError('Gesture parser failed or gesture/action mismatch')
            evs=p20.author_actions(parsed['gestures'],FingerEvent)
            if not evs or len(evs)!=len(parsed['actions']):raise RuntimeError('Native FingerEvent mapping mismatch')
            sw=[(k,e) for k,e in enumerate(evs) if not is_tap(e)]
            taps=[(k,e) for k,e in enumerate(evs) if is_tap(e)]
            record['n_swipe']=len(sw);record['n_tap']=len(taps);record['n_interval']=max(0,len(evs)-1)
            if sw:
                # max duration, earlier wins tie (argmax first occurrence).
                k,e=max(sw,key=lambda p:(int(endT_us(p[1])-startT_us(p[1])),-p[0]))
                f=build_features_dataframe([('temp',[e])]);features=get_numeric_feature_column_names(f)
                X=get_feature_columns(f,features)
                if len(X)!=1 or not np.isfinite(X.to_numpy(dtype=float)).all():raise RuntimeError('Bad native longest Swipe feature')
                svm,xgb=judge.classifiers_to_use_for_clusters[cid][:2]
                record['svm_pred']=int(np.asarray(svm.predict(X)).reshape(-1)[0])
                record['xgb_pred']=int(np.asarray(xgb.predict(X)).reshape(-1)[0])
                selected.append(dict(row_index=idx,session_id=sid,kind='swipe',index=k+1,duration_us=int(endT_us(e)-startT_us(e))))
            if taps:
                k,e=taps[-1]
                score=float(get_log_odds_with_threshold_posterior(endT_us(e)-startT_us(e),judge.tap_us_classifier[cid]))
                if np.isnan(score):raise RuntimeError('Tap original posterior NaN')
                record['tap_pred']=int(score>0)
                selected.append(dict(row_index=idx,session_id=sid,kind='tap',index=k+1,duration_us=int(endT_us(e)-startT_us(e)),log_odds=score))
            if len(evs)>1:
                k=len(evs)-1
                gap=int(startT_us(evs[k])-endT_us(evs[k-1]))
                score=float(get_log_odds_with_threshold_posterior(gap,judge.interval_us_classifier[cid]))
                if np.isnan(score):raise RuntimeError('Interval original posterior NaN')
                record['interval_pred']=int(score>0)
                selected.append(dict(row_index=idx,session_id=sid,kind='interval',index=k+1,duration_us=gap,log_odds=score))
            # Preserve original classifier, cluster ID, posterior names, numerical arithmetic.
            native=judge.predict(('P68',evs),cid)
            if not native:raise RuntimeError('Original Ultimate returned empty decision trace')
            last=float(native[-1][1]);
            if np.isnan(last):raise RuntimeError('Original Ultimate final score NaN')
            record['ultimate_pred']=int(last>0)
            record['ultimate_final_log_odds']=last
        except Exception as exc:
            errors.append(dict(row_index=idx,session_id=sid,stage='evaluation',error=type(exc).__name__+': '+str(exc)[:500]))
        rows.append(record)
        if (idx+1)%100==0:print(f'PROCESS {idx+1}/{len(target)} errors={len(errors)}',flush=True)
    d=pd.DataFrame(rows)
    assert d.row_index.is_unique
    if not a.limit:assert len(d)==1770
    test_manifest=root/'06_paper_tables/FINAL_PAPER_USE__P61B_CORRECTED_VS_P10_FROZEN_V3/ours_p10_frozen_v3/artifacts/split_manifest.json'
    if not test_manifest.is_file():raise FileNotFoundError(test_manifest)
    sp=json.loads(test_manifest.read_text())['stratified_train_test'];test=set(map(int,sp['test']));assert len(test)==530
    tables=[];families=[];pair=[]
    for split,part in [('FULL_POOL_1770',d),('HELDOUT_530',d[d.row_index.isin(test)])]:
        if not a.limit:assert len(part)==(1770 if split.startswith('FULL') else 530)
        for name,col in NAMES.items():tables.append(dict(split=split,**metrics(part,name,col)))
        for fam,g in part[part.label.eq('agent')].groupby('family'):
            for name,col in NAMES.items():
                z=g[g[col].notna()];families.append(dict(split=split,family=fam,method=name,agent_total=len(g),eligible=len(z),detected=int((z[col]==1).sum()),recall=float((z[col]==1).mean()) if len(z) else np.nan))
        for name,col in NAMES.items():
            if col=='v3_pred':continue
            q=part.dropna(subset=[col,'v3_pred'])
            for lab in ('agent','human'):
                u=q[q.label==lab];truth=1 if lab=='agent' else 0
                aok=u[col].eq(truth);bok=u.v3_pred.eq(truth)
                onlya=int((aok&~bok).sum());onlyb=int((~aok&bok).sum());n=onlya+onlyb
                pair.append(dict(split=split,method=name,label=lab,n=len(u),author_only=onlya,ours_only=onlyb,
                                 mcnemar_exact_p=binomtest(min(onlya,onlyb),n,.5).pvalue if n else 1.0))
    d.to_csv(out/'paired_session_predictions.csv',index=False)
    pd.DataFrame(tables).to_csv(out/'main_table.csv',index=False)
    pd.DataFrame(families).to_csv(out/'attack_family_table.csv',index=False)
    pd.DataFrame(pair).to_csv(out/'paired_significance.csv',index=False)
    pd.DataFrame(selected).to_csv(out/'selected_actions.csv',index=False)
    pd.DataFrame(errors,columns=['row_index','session_id','stage','error']).to_csv(out/'failures.csv',index=False)
    audit={'protocol':'Author original task-cluster models + P73 RECONSTRUCTED outer scaler, longest Swipe, last Tap/Interval, original Ultimate method, frozen V3; NOT exact-equivalence-verified',
           'attempted':len(d),'with_verified_cluster':sum(d.cluster.notna()),'errors':len(errors),'author_repo':str(author),
           'selection':'duration max earliest tie for Swipe; last Tap; last interval','source_sha256':sha(Path(__file__)),'candidate_outer_scaler_sha256':sha(bundle_path),'status':'RECONSTRUCTED_PREPROCESSING_CANDIDATE_NOT_EXACT_ORIGINAL'}
    (out/'audit.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False))
    t=pd.DataFrame(tables)
    for split in t.split.unique():
        print('\n'+split+' SESSION RESULTS',flush=True)
        print(t[t.split.eq(split)].to_string(index=False),flush=True)
    print('\nATTACK FAMILY RESULTS (FULL POOL)',flush=True)
    fam=pd.DataFrame(families);p=fam[fam.split.eq('FULL_POOL_1770')]
    if len(p):
        print(p.pivot(index='family',columns='method',values='recall').round(4).to_string(),flush=True)
    print('\nSAVED:',out,'FAILURES:',len(errors),'STATUS: RECONSTRUCTED CANDIDATE — NOT EXACT ORIGINAL',flush=True)

if __name__=='__main__':main()