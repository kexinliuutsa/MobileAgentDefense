#!/usr/bin/env python3
"""Read-only, raw touch-closure-prefix replay of original-author Ultimate and Frozen V3 (V3).

Requires user's original GUI_AHB_PAPER_REBUILD project and completed P74.
NO model training, fitting, calibration or threshold changes. No held-out-530 metric.

Both detectors receive identical truncated original log bytes at each completed raw touch
closure (TRACKING_ID ffffffff followed by SYN_REPORT), NOT a prefix chosen using
any future model prediction. Native parsers can legitimately discard/filter some
raw touch closures, so their action counts need not equal closure step count.
All last-prefix predictions must match P74 frozen session decisions.
No model fitting or changed thresholds; prefix parse failures = abstentions.
Author Ultimate emits 2*N-1 log-odds events for N gestures (interval updates
plus gesture endings); only gesture-ending events are online checkpoints.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time
import traceback

import numpy as np
import pandas as pd

POOL_N = 1770
THRESHOLDS = (1, 3, 5, 10, 15)
EXCLUSION = ('skip_p74_ineligible','skip_missing_cluster')


def hash_file(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def require(p):
    p=Path(p)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return p


def ensure_sql(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS prefixes (
        row_index INTEGER NOT NULL, session_id TEXT NOT NULL, label TEXT NOT NULL,
        family TEXT NOT NULL, gesture_index INTEGER NOT NULL, n_gestures INTEGER NOT NULL,
        author_score REAL, author_pred INTEGER,
        v3_status TEXT NOT NULL, v3_score REAL, v3_pred INTEGER,
        v3_n_actions INTEGER, v3_reason TEXT,
        PRIMARY KEY(row_index,gesture_index))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS completed (
        row_index INTEGER PRIMARY KEY, session_id TEXT NOT NULL,
        status TEXT NOT NULL, n_gestures INTEGER, n_v3_valid INTEGER,
        error TEXT)''')
    conn.commit()


def get_boundaries(raw):
    """Shared causal clock: raw completed touch closures, NOT author valid actions.

    Author's gesture parser may drop incomplete/invalid touch closures; V3 may
    apply a different filter. Both methods must see the SAME raw bytes each step.
    """
    boundaries=[];pending=False;active=False;offset=0
    for line in raw.splitlines(keepends=True):
        low=line.lower()
        match=re.search(rb'abs_mt_tracking_id\s+([0-9a-f]{8})\b',low)
        if match:
            if match.group(1)==b'ffffffff':
                if active:
                    pending=True
                    active=False
                # Orphan UP without matching DOWN is not a physical gesture.
            else:
                active=True
        offset += len(line)
        if pending and b'syn_report' in low:
            boundaries.append(offset);pending=False
    if pending:
        raise ValueError('Unclosed touch-release marker: ffffffff without SYN_REPORT')
    if not boundaries:
        raise ValueError('No complete DOWN→UP touch gestures; cannot define raw-prefix clock')
    if len(boundaries)!=len(set(boundaries)) or boundaries!=sorted(boundaries):
        raise ValueError('Invalid raw-prefix boundaries')
    if boundaries[-1] > len(raw):raise AssertionError('Final boundary outside log')
    # The last prefix contains all trailing non-gesture lines, ensuring it is
    # byte-identical to the original log for the mandatory frozen-score check.
    boundaries[-1]=len(raw)
    return boundaries


def event_signature(ev, startT_us, endT_us, is_tap):
    return (int(startT_us(ev)),int(endT_us(ev)),bool(is_tap(ev)))


def numeric(x):
    if x is None:return None
    v=float(x)
    if math.isnan(v):return None
    return v


def author_gesture_end_scores(trace, events, begin_us, end_us):
    """Return N action-end cumulative scores from an author's 2*N-1 trace.

    Original judge_library.UltimateClassifier.predict outputs:
    gesture_1_end, interval_2_begin, gesture_2_end, ... , gesture_N_end.
    Interval updates are NOT finished gestures and must NOT count as steps.
    Original timestamps are checked to ensure this is really that trace.
    """
    n = len(events)
    want = 2*n-1 if n else 0
    if len(trace) != want:
        raise ValueError(f'Original Ultimate trace has {len(trace)} score events for {n} gestures; expected {want}')
    result=[]
    for j, event in enumerate(events):
        if j:
            interval_timestamp=int(trace[2*j-1][0])
            expected_start=int(begin_us(event))
            if interval_timestamp!=expected_start:
                raise ValueError(f'Original Ultimate interval timestamp mismatch at gesture {j+1}: {interval_timestamp}!={expected_start}')
        idx=2*j
        got_end=int(trace[idx][0]);expected_end=int(end_us(event))
        if got_end!=expected_end:
            raise ValueError(f'Original Ultimate gesture-end timestamp mismatch at gesture {j+1}: {got_end}!={expected_end}')
        score=float(trace[idx][1])
        if not math.isfinite(score):
            raise ValueError(f'Original Ultimate nonfinite cumulative score at gesture {j+1}')
        result.append(score)
    return result


def self_test_author_trace():
    # No dependencies on the user's Mac or models; verify original 2N-1 contract.
    E=lambda a,b:(a,b)
    a=[E(10,20),E(30,40),E(50,60)]
    seq=[(20,1.5),(30,1.2),(40,-.7),(50,-.5),(60,2.0)]
    z=author_gesture_end_scores(seq,a,lambda x:x[0],lambda x:x[1])
    assert z==[1.5,-.7,2.0],z
    assert [int(v>0) for v in z]==[1,0,1]
    for bad in (seq[:-1], seq[:1]):
        try:author_gesture_end_scores(bad,a,lambda x:x[0],lambda x:x[1])
        except ValueError:pass
        else:raise AssertionError('Length mismatch not detected')
    try:author_gesture_end_scores([(21,1.5)]+seq[1:],a,lambda x:x[0],lambda x:x[1])
    except ValueError:pass
    else:raise AssertionError('Timestamp mismatch not detected')
    raw=(b'ABS_MT_TRACKING_ID 00000001\nSYN_REPORT\n'
         b'ABS_MT_TRACKING_ID ffffffff\nSYN_REPORT\n'
         b'ABS_MT_TRACKING_ID 00000002\nSYN_REPORT\n'
         b'ABS_MT_TRACKING_ID ffffffff\nSYN_REPORT\n')
    cuts=get_boundaries(raw)
    assert len(cuts)==2 and cuts[-1]==len(raw),cuts
    print('SELF-TEST PASS: author 2N-1 trace, gesture-end indexing, timestamps, raw closure clock')


def summarise(rows, detector):
    a=rows[rows.label=='agent']; h=rows[rows.label=='human']
    first=f'{detector}_first_alarm'
    valid=f'{detector}_valid_prefixes'
    detected=a[first].notna()
    alarms=h[first].notna()
    n_agent=len(a);n_human=len(h)
    successes=int(detected.sum());fal=int(alarms.sum())
    res={'detector':detector,'N':len(rows),'Agent_N':n_agent,'Human_N':n_human,
         'First_Detection_Success_Rate':successes/n_agent if n_agent else None,
         'Anytime_Human_FPR':fal/n_human if n_human else None,
         'Agent_Detected_N':successes,'Human_Anytime_False_Alarm_N':fal,
         'Mean_Detection_Steps_Detected_Only':float(a.loc[detected,first].mean()) if successes else None,
         'Median_Detection_Steps_Detected_Only':float(a.loc[detected,first].median()) if successes else None,
         'Mean_Capped_Steps_Miss_Equals_Length_Plus_One':float(a[first].fillna(a.n_gestures+1).mean()) if n_agent else None,
         'Agent_No_Valid_Prefix_N':int((a[valid]==0).sum()),
         'Human_No_Valid_Prefix_N':int((h[valid]==0).sum())}
    for k in THRESHOLDS:
        res[f'Success_At_{k}']=int(a[first].le(k).sum())/n_agent if n_agent else None
    return res


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--project',type=Path,default=Path.cwd())
    ap.add_argument('--limit',type=int,default=0,help='For smoke testing only (will write separate folder)')
    ap.add_argument('--restart',action='store_true',help='Clear ONLY this script\'s previous prefix sqlite records')
    ap.add_argument('--self-test',action='store_true',help='Run offline trace-format tests without requiring project files')
    args=ap.parse_args()
    if args.self_test:
        self_test_author_trace()
        return
    if args.limit<0:ap.error('--limit must be nonnegative')
    root=args.project.expanduser().resolve()
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(root/'scripts'))
    import P20_four_model_runner as p20
    import P31_hex_online as p31
    from P31_hex_frame_adapter import parse_log
    from P74_original_author_reconstructed_scaler_1770 import OuterScaledClassifier
    import joblib

    author_root=next((p for p in [root/'00_original/author_repo',Path.home()/'Desktop/Passing-the-Turing-Test-on-Screen-Agent-Humanization-Benchmark-main']
                      if (p/'analysis/processing/judge_library.py').is_file()),None)
    if author_root is None:raise FileNotFoundError('Cannot find original author source')
    judge,_=p31.load_original_author(root,author_root)
    from analysis.lib.motionevent_classes import FingerEvent
    from analysis.lib.feature_library import startT_us, endT_us, is_tap

    bundle_path=require(root/'06_paper_tables/P68_ORIGINAL_CLUSTER_NATIVE_SESSION_TABLE/P73_AUTHOR_NATIVE_RECOVERY/candidate_outer_scalers_all_clusters.joblib')
    scalers=joblib.load(bundle_path)
    if set(scalers)!=set(range(5)):raise AssertionError('Five cluster scalers required')
    judge.classifiers_to_use_for_clusters={
        c:tuple(OuterScaledClassifier(clf,scalers[c]) for clf in judge.classifiers_to_use_for_clusters[c][:2])
        for c in range(5)}

    poolpath=require(root/'02_rebuilt_benchmark/P6_frozen_paper_dataset/main_evaluation_pool_1770.csv')
    mapfile=require(root/'reports/P22_fresh_native_online/P22_original_task_cluster_recovered.csv')
    p74path=require(root/'06_paper_tables/P74_CANDIDATE_SCALER_AUTHOR_ORIGINAL_MODELS/paired_session_predictions.csv')
    v3root=root/'01_clean_code/offline_defenses/crossscaleguard_offline_v3'
    v3run_path=require(v3root/'run.py')
    spec=importlib.util.spec_from_file_location('frozen_v3_online_entry',v3run_path)
    if spec is None or spec.loader is None:raise ImportError('Cannot import frozen V3 runtime')
    v3run=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v3run)
    v3_bundle,v3_config,v3_schema=v3run.load()

    pool=pd.read_csv(poolpath,dtype={'session_id':str},keep_default_na=False)
    p74=pd.read_csv(p74path,dtype={'session_id':str},low_memory=False)
    if len(pool)!=POOL_N or len(p74)!=POOL_N:raise ValueError('Must have original 1770 full pool')
    if pool.session_id.duplicated().any() or p74.session_id.duplicated().any():raise ValueError('Duplicate session_id')
    if list(p74.row_index.astype(int))!=list(range(POOL_N)) or not np.array_equal(pool.session_id.to_numpy(),p74.session_id.to_numpy()):
        raise ValueError('P74/1770 identity/order mismatch')
    if not pool.label.astype(str).str.lower().equals(p74.label.astype(str).str.lower()):
        raise ValueError('P74/1770 truth-label mismatch')
    cmap={}
    for r in pd.read_csv(mapfile,keep_default_na=False).itertuples(index=False):
        if str(r.task_match_status)!='MATCHED':continue
        i=int(r.p6_row);c=int(float(r.task_cluster))
        if i in cmap and cmap[i]!=c:raise ValueError('Conflicting cluster mapping')
        cmap[i]=c

    out=root/'06_paper_tables/P74_CANDIDATE_SCALER_AUTHOR_ORIGINAL_MODELS/ONLINE_1770_RAW_TOUCH_PREFIX_V3'
    if args.limit:out=out/f'SMOKE_{args.limit}'
    out.mkdir(parents=True,exist_ok=True)
    dbpath=out/'PREFIX_STEP_CACHE.sqlite3'
    if args.restart and dbpath.exists():dbpath.unlink()
    conn=sqlite3.connect(dbpath)
    ensure_sql(conn)
    conn.execute('PRAGMA journal_mode=WAL')
    frozen_dep_files=[
        v3root/'artifacts'/name for name in
        ('session_head.joblib','strict_head.joblib','human_reference_head.joblib',
         'fusion_head.joblib','fake_artifact_calibration.json',
         'feature_schema.json','training_config.json')]
    v2root=v3root.parent/'crossscaleguard_offline_v2/src/crossscaleguard'
    frozen_dep_files.extend([v2root/name for name in ('parser.py','adapter.py','features.py')])
    frozen_dep_files.extend([author_root/name for name in
        ('humanized_swipe_classifiers.pkl','raw_tap_classifier_us_across_clusters.pkl',
         'interval_classifier_microseconds_across_clusters.pkl',
         'analysis/processing/judge_library.py')])
    # The P74 release artifacts are immutable; if any input changes, a resumed
    # score cache is invalidated instead of silently mixing model versions.
    guard={
        'frozen_model_and_extractor_sha256':{str(f):hash_file(require(f)) for f in frozen_dep_files},
        'pool_sha256':hash_file(poolpath),'P74_predictions_sha256':hash_file(p74path),
        'scaler_sha256':hash_file(bundle_path),'v3_run_sha256':hash_file(v3run_path),
        'v3_config_threshold':float(v3_config['thresholds']['full fusion']),
        'protocol':'v3 native 2N-1 author cumulative trace at gesture END; raw TRACKING_ID up + SYN_REPORT checkpoints; both frozen detectors use identical prefix; final P74 audit',
        'limit':args.limit}
    config_path=out/'INPUT_FREEZE.json'
    if config_path.exists():
        old=json.loads(config_path.read_text())
        if old!=guard:raise RuntimeError('Inputs changed since previous partial run; use --restart')
    else:config_path.write_text(json.dumps(guard,indent=2))
    target=range(min(args.limit,POOL_N)) if args.limit else range(POOL_N)
    failures=0;ok=0;skips=0
    t0=time.time()
    with tempfile.TemporaryDirectory(prefix='gui_online_raw_prefix_') as tmpdir:
        tmp=Path(tmpdir)/'prefix.log'
        for seq,i in enumerate(target,1):
            sid=str(pool.iloc[i].session_id); label=str(pool.iloc[i].label).lower()
            family=str(pool.iloc[i].condition_final)
            old=conn.execute('SELECT status FROM completed WHERE row_index=?',(i,)).fetchone()
            if old is not None:
                if old[0]=='ok':ok+=1
                elif old[0].startswith('skip'):skips+=1
                else:failures+=1
                continue
            records=[];reason=None;status='ok';n=0
            try:
                original=p74.iloc[i]
                if pd.isna(original.ultimate_pred) or pd.isna(original.v3_pred):
                    status='skip_p74_ineligible'
                    reason='P74 at least one missing final prediction'
                elif i not in cmap:
                    status='skip_missing_cluster';reason='No verified source task cluster'
                else:
                    cid=cmap[i]
                    path=p20.find_log(pool.iloc[i].to_dict(),poolpath,root)
                    if path is None:raise FileNotFoundError(f'No gesture log for {sid}')
                    parsed=parse_log(path)
                    if parsed.get('parse_status')!='ok' or not parsed['gestures'] or len(parsed['gestures'])!=len(parsed['actions']):
                        raise ValueError('Invalid author gesture parser output')
                    events=p20.author_actions(parsed['gestures'],FingerEvent)
                    if len(events)!=len(parsed['actions']):raise ValueError('FingerEvent mismatch')
                    n_author=len(events)
                    reference_signatures=[event_signature(e,startT_us,endT_us,is_tap) for e in events]
                    raw=Path(path).read_bytes()
                    cuts=get_boundaries(raw)
                    n=len(cuts)  # Denominator clock = raw completed touch closures.
                    if n < n_author:
                        raise ValueError(f'Fewer raw touch closures ({n}) than author recognized actions ({n_author})')
                    # Original final complete-session result must reproduce P74. Author emits 2N-1 scores.
                    author_full=judge.predict((sid,events),cid,prior_log_odds=0.0)
                    full_end_scores=author_gesture_end_scores(author_full,events,startT_us,endT_us)
                    if int(full_end_scores[-1]>0)!=int(original.ultimate_pred):
                        raise ValueError('Author complete-session prediction differs from frozen P74')
                    raw_author=[]; raw_v3=[]; previous_author_count=0
                    for k,cut in enumerate(cuts,1):
                        tmp.write_bytes(raw[:cut])
                        # The author and V3 independently parse THE SAME raw
                        # temporal prefix, not a filtered action list from the future.
                        p=parse_log(tmp)
                        if p.get('parse_status')=='ok' and len(p.get('gestures',[]))==len(p.get('actions',[])):
                            current=p20.author_actions(p['gestures'],FingerEvent)
                            m=len(current)
                            if m>n_author:
                                raise ValueError(f'Author prefix at touch={k} parsed too many gestures: {m}>{n_author}')
                            current_sig=[event_signature(e,startT_us,endT_us,is_tap) for e in current]
                            if current_sig!=reference_signatures[:m]:
                                raise ValueError(f'Author prefix changed previously observed gestures at raw touch={k}')
                            if m<previous_author_count:
                                raise ValueError(f'Author prefix gesture count decreased at touch={k}: {m}<{previous_author_count}')
                            previous_author_count=m
                            if m:
                                a_trace=judge.predict((sid,current),cid,prior_log_odds=0.0)
                                prefix_end_scores=author_gesture_end_scores(a_trace,current,startT_us,endT_us)
                                if not np.allclose(prefix_end_scores,full_end_scores[:m],rtol=1e-10,atol=1e-10):
                                    raise ValueError(f'Original Ultimate prefix scores changed with unseen future gestures at touch={k}')
                                score=prefix_end_scores[-1]
                                a_pred=int(score>0)
                            else:
                                score=None; a_pred=None  # No recognized author action yet.
                        else:
                            score=None;a_pred=None  # Parser abstains on this prefix.
                        raw_author.append((score,a_pred))
                        z=v3run.predict(tmp,v3_bundle,v3_config,v3_schema)
                        z_status=str(z.get('status','missing'))
                        n_seen=z.get('n_actions')
                        if n_seen is not None:
                            n_seen=int(n_seen)
                            if n_seen<0:
                                raise ValueError(f'Invalid V3 action count at touch={k}')
                        # V3 may recognize a DIFFERENT action count from the
                        # original author; requiring n_seen==k is incorrect.
                        vv=z.get('detected'); vscore=numeric(z.get('final_score'))
                        if z_status=='ok':
                            if vv is None or vscore is None:
                                raise ValueError(f'V3 status ok without prediction at touch={k}')
                            pv=int(bool(vv))
                        else:
                            if z_status!='feature_error' or vv is not None:
                                raise ValueError(f'Unexpected V3 prefix status={z_status}, detected={vv} at touch={k}')
                            pv=None  # Expected short-prefix abstention; no false-negative substitution.
                        raw_v3.append((z_status,vscore,pv,n_seen,str(z.get('decision_trace',''))[:500]))
                    # Last prefix is EXACTLY the full original log bytes.
                    if raw_author[-1][1]!=int(original.ultimate_pred):
                        raise ValueError('Last raw-touch prefix Author != frozen P74 full prediction')
                    if raw_v3[-1][0]!='ok' or raw_v3[-1][2]!=int(original.v3_pred):
                        raise ValueError('Last raw-touch prefix V3 != frozen P74 full prediction')
                    if previous_author_count!=n_author:
                        raise ValueError(f'Last prefix author parsed {previous_author_count} actions, expected {n_author}')
                    for k,((a_score,a_pred),(z_status,v_score,v_pred,seen,why)) in enumerate(zip(raw_author,raw_v3),1):
                        records.append((i,sid,label,family,k,n,a_score,a_pred,z_status,v_score,v_pred,seen,why))
            except Exception as e:
                status='failed_protocol';reason=f'{type(e).__name__}: {e}'
            with conn:
                if status=='ok':
                    conn.executemany('''INSERT OR REPLACE INTO prefixes
                    (row_index,session_id,label,family,gesture_index,n_gestures,author_score,author_pred,
                    v3_status,v3_score,v3_pred,v3_n_actions,v3_reason)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',records)
                conn.execute('INSERT OR REPLACE INTO completed(row_index,session_id,status,n_gestures,n_v3_valid,error) VALUES(?,?,?,?,?,?)',
                             (i,sid,status,n,sum(x[10] is not None for x in records),reason))
            if status=='ok':ok+=1
            elif status.startswith('skip'):skips+=1
            else:
                failures+=1
                if failures<=10:print(f'PROTOCOL FAIL row={i} sid={sid} {reason}',flush=True)
            # Three early failures usually mean a parser / prefix API mismatch,
            # not three isolated bad sessions. Stop instead of wasting hours.
            if seq<=25 and failures>=3:
                raise RuntimeError('Early protocol check failed on >=3 sessions. Inspect '+str(out/'PREFIX_STEP_CACHE.sqlite3')+'; do not continue full batch')
            if seq%20==0 or seq==len(target):
                print(f'PROGRESS {seq}/{len(target)} valid={ok} skip={skips} fail={failures} elapsed_s={time.time()-t0:.1f}',flush=True)

    done=pd.read_sql_query('SELECT * FROM completed ORDER BY row_index',conn)
    steps=pd.read_sql_query('SELECT * FROM prefixes ORDER BY row_index,gesture_index',conn)
    conn.close()
    done.to_csv(out/'SESSION_COVERAGE.csv',index=False)
    steps.to_csv(out/'PER_GESTURE_PREDICTIONS.csv',index=False)
    if not len(steps):
        print('\nNO VALID PREFIX PAIRS; see SESSION_COVERAGE.csv. STATUS: NOT_PAPER_READY')
        raise SystemExit(2)
    session=[]
    for i,g in steps.groupby('row_index',sort=True):
        g=g.sort_values('gesture_index');n=int(g.n_gestures.iloc[0]);assert len(g)==n
        for d,pcol in (('author','author_pred'),('v3','v3_pred')):
            vals=g.loc[g[pcol].eq(1),'gesture_index']
            s=g[pcol].notna().sum()
            if d=='author':
                rec=dict(row_index=int(i),session_id=g.session_id.iloc[0],label=g.label.iloc[0],
                         family=g.family.iloc[0],n_gestures=n)
            rec[f'{d}_first_alarm']=int(vals.iloc[0]) if len(vals) else np.nan
            rec[f'{d}_valid_prefixes']=int(s)
        session.append(rec)
    df=pd.DataFrame(session).sort_values('row_index')
    df.to_csv(out/'SESSION_FIRST_ALARMS.csv',index=False)
    tab=pd.DataFrame([summarise(df,'author'),summarise(df,'v3')])
    tab.to_csv(out/'ONLINE_MAIN_TABLE.csv',index=False)
    fam=[]
    for family,g in df.groupby('family'):
        for d in ('author','v3'):
            fam.append(dict(family=family,**summarise(g,d)))
    pd.DataFrame(fam).to_csv(out/'ONLINE_ATTACK_FAMILY.csv',index=False)
    audit={'status':'PASS' if failures==0 and skips==int((p74.ultimate_pred.isna()|p74.v3_pred.isna()).iloc[list(target)].sum()) else 'PARTIAL_NOT_PAPER_READY',
           'pool_size':POOL_N,'attempted':len(target),'valid_common_online':len(df),'excluded':skips,
           'protocol_failures':failures,'expected_p74_paired_eligible':int((p74.ultimate_pred.notna()&p74.v3_pred.notna()).iloc[list(target)].sum()),
           'total_valid_prefix_rows':len(steps),'inputs':guard,
           'interpretation':'Both frozen detectors independently parse identical raw completed-touch prefixes; counts of recognized gestures can differ; NOT real-device streaming latency',
           'caveats':'Raw touch closure is the common time-step unit, not parser-accepted gestures. Author interval-only score events are excluded from detection checkpoints. Early prefixes may abstain. 1770 pool can contain related/mutated sessions. Not wall-clock latency.'}
    (out/'ONLINE_AUDIT.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False))
    print('\nONLINE PREFIX EVALUATION — EXACT SAME RAW TOUCH CLOSURE INDICES\n'+tab.to_string(index=False))
    print('\nCOVERAGE\n'+done.status.value_counts().to_string())
    print('\nFINAL STATUS:',audit['status'])
    print('SAVED:',out)
    if audit['status']!='PASS':
        print('WARNING: Protocol failures occurred; results are diagnostic, NOT final paper metrics.')
        raise SystemExit(2)

if __name__=='__main__':main()