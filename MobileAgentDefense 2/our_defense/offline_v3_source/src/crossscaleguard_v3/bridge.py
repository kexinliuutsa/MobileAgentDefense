"""Import only the existing v2 feature API; never its package initializer/scorer."""
import importlib.util
import sys
import types
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT.parent / "crossscaleguard_offline_v2"
def extractor():
    name = "_crossscaleguard_v3_feature_bridge"
    if name not in sys.modules:
        package=types.ModuleType(name)
        package.__path__=[str(V2 / "src/crossscaleguard")]
        package.ARTIFACT_ROOT=V2
        sys.modules[name]=package
    from importlib import import_module
    return import_module(name+".features").extract_features_from_log
