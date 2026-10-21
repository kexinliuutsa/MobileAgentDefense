import hashlib
import json
import platform
from pathlib import Path
from .core import ROOT, dump

def package():
    required=['session_head.joblib','strict_head.joblib','fusion_head.joblib','human_reference_head.joblib','fake_artifact_calibration.json','feature_schema.json','split_manifest.json','training_config.json','session_strict_head.joblib']
    for name in required:
        if not (ROOT/'artifacts'/name).is_file(): raise FileNotFoundError(name)
    files={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in str(p) and p.name!='manifest.json'}
    v2=ROOT.parent/'crossscaleguard_offline_v2'
    paths=[v2/'src/crossscaleguard'/n for n in ('parser.py','adapter.py','features.py')]+[p for p in (v2/'vendor').rglob('*.py')]
    dump(ROOT/'manifest.json',{'name':'CrossScaleGuard-Offline-v3','version':'3.0.0','python':platform.python_version(),'self_contained_learned_models':True,'feature_dependency':'sibling crossscaleguard_offline_v2 parser, adapter, native feature extractors','legacy_wrapper_dependencies':[],'files_sha256':files,'pipeline_scripts_sha256':{str(p.relative_to(ROOT.parents[2])):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT.parents[2]/'scripts').glob('P10*.py')},'feature_dependency_sha256':{str(p.relative_to(v2)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}})
    print('Packaged',len(files),'files')
