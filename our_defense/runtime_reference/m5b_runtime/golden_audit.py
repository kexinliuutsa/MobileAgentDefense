"""M5B native parity: replay one exported AHB JSON against matching M4V Golden prefixes."""
from __future__ import annotations
import argparse, csv, json, math
from pathlib import Path
from .runtime_monitor import RuntimeMonitor

COMPARE_TEXT = ('response','reason','evidence_region')
COMPARE_BOOL = ('v1_detect','v2_detect','v3_detect','legacy_final','cf_checked','cf_fragile','cf_confirmed')

def _norm_bool(v):
    if v is None or str(v).strip().lower() in ('','none','null','nan'):
        return None
    if isinstance(v,bool): return v
    if str(v).strip().lower() in ('true','1'): return True
    if str(v).strip().lower() in ('false','0'): return False
    return 'UNKNOWN:'+str(v)


def audit(source_json, golden_csv, record_id, cohort, output=None, tolerance=1e-12, manifest_sha='UNVERIFIED'):
    obj = json.loads(Path(source_json).read_text())
    with Path(golden_csv).open(newline='') as f:
        rows=[r for r in csv.DictReader(f) if r.get('cohort')==cohort and r.get('record_id')==record_id]
    by_g = {int(r['gesture']):r for r in rows}
    if len(by_g)!=len(rows) or not rows:
        raise RuntimeError('No unique Golden rows: cohort='+cohort+' record_id='+record_id)
    participant = obj.get('participant')
    session_id = obj.get('session_id')
    if not participant or not session_id:
        raise RuntimeError('Export JSON must include original participant and session_id')
    monitor = RuntimeMonitor(manifest_sha=manifest_sha)
    token = monitor.start_session(trusted_legacy_context={
        'participant':str(participant), 'session_id':str(session_id),
        'group':str(obj.get('group') or obj.get('label') or cohort)})
    result_rows=[]
    for g, gesture in enumerate(obj['gestures'], 1):
        if g>16: break
        if g<11:
            monitor.push_gesture(token,seq=g,points=gesture)
            continue
        got=monitor.push_gesture(token,seq=g,points=gesture)
        row=by_g.get(g)
        if row is None: continue
        diffs=[]
        if got.get('status')!='OK':
            diffs.append('STATUS:'+str(got.get('status'))+' '+str(got.get('reason')))
        observed=got.get('native_result',{})
        for field in COMPARE_TEXT:
            a=observed.get(field)
            b=row.get(field)
            if str(a) != str(b):
                diffs.append(f'{field}:{a!r}!={b!r}')
        for field in COMPARE_BOOL:
            if field in row and row[field].strip()!='':
                a=_norm_bool(observed.get(field))
                b=_norm_bool(row[field])
                if a!=b: diffs.append(f'{field}:{a!r}!={b!r}')
        a=observed.get('strict_score')
        b=row.get('strict_score')
        if b not in (None,''):
            if a is None or not math.isclose(float(a),float(b),rel_tol=0,abs_tol=tolerance):
                diffs.append(f'strict_score:{a!r}!={b!r}')
        result_rows.append({'record_id':record_id, 'gesture':g, 'pass':not diffs,
                            'difference':'; '.join(diffs), 'response':got.get('response'),
                            'strict_score':got.get('strict_score'),
                            'latency_ms':got.get('latency_ms')})
        print(f'G{g} {"PASS" if not diffs else "FAIL"} {got.get("response")} '+ '; '.join(diffs),flush=True)
    expected={g for g in by_g if 11<=g<=min(16,len(obj['gestures']))}
    tested={r['gesture'] for r in result_rows}
    if expected!=tested:
        raise RuntimeError(f'Not all expected prefixes evaluated; missing {sorted(expected-tested)}')
    if output:
        p=Path(output);p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('w',newline='') as f:
            wr=csv.DictWriter(f,fieldnames=list(result_rows[0]));wr.writeheader();wr.writerows(result_rows)
    passes=sum(r['pass'] for r in result_rows)
    print(f'GOLDEN PARITY {passes}/{len(result_rows)}; source coverage {len(result_rows)} of full Golden file (NOT 1656)')
    return passes==len(result_rows)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source-json',required=True)
    p.add_argument('--golden-csv',required=True)
    p.add_argument('--record-id',required=True)
    p.add_argument('--cohort',default='human')
    p.add_argument('--out',default='results/real_device_monitor/m5b_runtime/parity_one_session.csv')
    p.add_argument('--manifest-json',help='provisional manifest; verify before scoring')
    p.add_argument('--repo-root',default='.')
    a=p.parse_args()
    sha='UNVERIFIED'
    if a.manifest_json:
        from .artifact_manifest import verify_manifest
        sha=verify_manifest(a.manifest_json, a.repo_root)['manifest_sha']
    ok=audit(a.source_json,a.golden_csv,a.record_id,a.cohort,a.out,manifest_sha=sha)
    if not ok: raise SystemExit(2)

if __name__=='__main__':main()
