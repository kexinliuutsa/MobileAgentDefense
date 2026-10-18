"""Provisional, content-addressed B0 inventory; not proof of full model dependencies."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

CANDIDATES=[
 'real_device_monitor/online_trajectory_defense_v3.py',
 'real_device_monitor/dynamic_probe_runtime_v1.py',
 'real_device_monitor/dynamic_probe_runtime_v2.py',
 'evaluation/frozen_deployment_defense.py',
 'evaluation/frozen_evidence_regions_v1.json',
 'evaluation/frozen_strict_online_gate_v1.json',
 'results/real_device_monitor/m4v_full_v3_replay/prefix_results.csv',
 'results/real_device_monitor/m4v_full_v3_replay/session_results.csv',
]

def manifest(root, extras=()):
    root=Path(root).resolve()
    files=[]
    for rel in sorted(set(CANDIDATES+list(extras))):
        path=(root/rel).resolve()
        if root not in path.parents: raise ValueError('Path outside repo: '+rel)
        if not path.is_file(): raise FileNotFoundError(path)
        h=hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
        files.append({'path':rel,'size_bytes':path.stat().st_size,'sha256':h.hexdigest()})
    core={'manifest_type':'PROVISIONAL_SOURCE_INVENTORY_NOT_COMPLETE_FROZEN_MANIFEST',
          'runtime_policy':'FROZEN_V3_0_UNCHANGED', 'files':files}
    digest=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {**core, 'manifest_sha':digest}

def verify_manifest(path, root='.'):
    """Verify listed bytes AND canonical digest. Does not prove inventory complete."""
    import json
    data=json.loads(Path(path).read_text())
    sha=data.pop('manifest_sha',None)
    calc=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if calc!=sha: raise ValueError('MANIFEST_SHA_MISMATCH')
    root=Path(root).resolve()
    for f in data['files']:
        p=(root/f['path']).resolve()
        if root not in p.parents or not p.is_file(): raise FileNotFoundError(p)
        h=hashlib.sha256(p.read_bytes()).hexdigest()
        if h != f['sha256']:raise ValueError('FILE_SHA_MISMATCH:'+f['path'])
    data['manifest_sha']=sha
    return data


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',default='.')
    p.add_argument('--add',nargs='*',default=[])
    p.add_argument('--out',default='results/real_device_monitor/m5b_runtime_b0/provisional_manifest.json')
    a=p.parse_args()
    m=manifest(a.root,a.add)
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    print('SHA:',m['manifest_sha'])
    print('PROVISIONAL:',len(m['files']),'files; add actual model artifacts after source trace.')
    print('OUTPUT:',dest.resolve())

if __name__=='__main__':main()
