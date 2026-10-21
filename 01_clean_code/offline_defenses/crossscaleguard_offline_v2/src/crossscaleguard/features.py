"""Feature extraction using only the copied native extractors."""
import importlib.util
import sys
import traceback
from . import ARTIFACT_ROOT
from .parser import parse_log

# Private namespace prevents an unrelated top-level `src` package from shadowing
# the vendored src.features modules. No defense/pipeline/training code is imported.
_NATIVE = "_crossscaleguard_v2_native"
def native_module(name):
    if _NATIVE not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            _NATIVE, ARTIFACT_ROOT / "vendor/ours_src/src/__init__.py",
            submodule_search_locations=[str(ARTIFACT_ROOT / "vendor/ours_src/src")])
        module = importlib.util.module_from_spec(spec)
        sys.modules[_NATIVE] = module
        spec.loader.exec_module(module)
    return importlib.import_module(_NATIVE + "." + name)

def error_details(exc):
    return {"error_type": type(exc).__name__, "error_message": str(exc),
            "traceback_tail": traceback.format_exc()[-2000:]}

def extract_features_from_log(log_path):
    out = {"parse_status": "pending", "n_actions": 0,
           "session_feature_status": "not_run", "cross_feature_status": "not_run",
           "session_features": {}, "cross_features": {}, "errors": {}}
    try:
        parsed = parse_log(log_path)
        out["parse_status"] = parsed["parse_status"]
        actions = parsed["actions"]
        out["n_actions"] = len(actions)
    except Exception as exc:
        out["parse_status"] = "error"
        out.update(error_details(exc))
        out["errors"]["parser"] = error_details(exc)
        return out
    if out["parse_status"] != "ok":
        return out
    for key, module, function in [
        ("session", "features.session_features", "extract_session_features"),
        ("cross", "features.cross_action_features", "extract_cross_action_features")]:
        try:
            result = getattr(native_module(module), function)(actions)
            if not result:
                raise ValueError("Native extractor returned no features")
            out[key + "_features"] = {k: float(v) for k, v in result.items()}
            out[key + "_feature_status"] = "ok"
        except Exception as exc:
            out[key + "_feature_status"] = "error"
            out["errors"][key] = error_details(exc)
            out.update(error_details(exc))
    return out
