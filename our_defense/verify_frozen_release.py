#!/usr/bin/env python3
"""Read-only exact-asset audit and optional local inference smoke test for P10 Frozen V3.

Does not modify model artifacts, recalibrate operating points or access Android.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "01_clean_code" / "offline_defenses" / "crossscaleguard_offline_v3"
V2 = ROOT / "01_clean_code" / "offline_defenses" / "crossscaleguard_offline_v2"
SHA256 = {
    "01_clean_code/offline_defenses/crossscaleguard_offline_v3/run.py": "c109f1324ed0266f78f43e103b050a5572114735a6dddb1d2f7cf714dc7c373c",
    "01_clean_code/offline_defenses/crossscaleguard_offline_v3/artifacts/session_head.joblib": "ac6176d8f696bbf6c20a7e189f7b8b75c0e5bc349a2709736acfc46f8146a9d3",
    "01_clean_code/offline_defenses/crossscaleguard_offline_v3/artifacts/strict_head.joblib": "5c780c8604a5aea5fdfcf8918df58ea74c4b051f0c4667a32e34e66749ab0567",
    "01_clean_code/offline_defenses/crossscaleguard_offline_v3/artifacts/fusion_head.joblib": "7fa14739a62cc8eb12a96e9b9fc8a37109d1186b95875c8596b9beeecd62f3e3",
    "01_clean_code/offline_defenses/crossscaleguard_offline_v3/artifacts/human_reference_head.joblib": "05af3032be6aae68d7d996cfe5702363132a657f656b35201e3d75890afbf937",
    "01_clean_code/offline_defenses/crossscaleguard_offline_v3/artifacts/session_strict_head.joblib": "cc328e4b5c42372da76719469e19f2cc047d6bb341b9cd290d36d5472bfa49f8",
    "01_clean_code/offline_defenses/crossscaleguard_offline_v3/artifacts/fake_artifact_calibration.json": "709e012143cf3563d00cf434d65907e947b6fa51d1dd753ff43262107a1869cd",
    "01_clean_code/offline_defenses/crossscaleguard_offline_v3/artifacts/feature_schema.json": "c69cc680f98f699fd264d1de930beb6a44bb570cfb84d2649f8f49718d46008b",
    "01_clean_code/offline_defenses/crossscaleguard_offline_v3/artifacts/training_config.json": "64ec1dac43b82bd78ac661701ea5bcb9d035aee0d25755769a147c8642c188cd",
    "01_clean_code/offline_defenses/crossscaleguard_offline_v2/src/crossscaleguard/parser.py": "45710f16a2c27974e99ad6f04db5d4977eb437a6c67c243990110f8c1dbec88f",
    "01_clean_code/offline_defenses/crossscaleguard_offline_v2/src/crossscaleguard/adapter.py": "afe6eadcfb663314e30aebdf52399e8b204317251bf589476cb342f8e6fa4439",
    "01_clean_code/offline_defenses/crossscaleguard_offline_v2/src/crossscaleguard/features.py": "6a375a685abfda5260d7af58579d54cda4a87af07f037534d8772e3912d3254c",
    "01_clean_code/offline_defenses/crossscaleguard_offline_v2/vendor/ours_src/src/features/session_features.py": "f298b893c71a95907ba5aa96441e463a7e5916ca17e6a006f2f0b48cd8f11e00",
    "01_clean_code/offline_defenses/crossscaleguard_offline_v2/vendor/ours_src/src/features/cross_action_features.py": "87a5238c26a81bf8d98ae10ce026e66a41dab2d6100abbac143942a10183672a",
    "01_clean_code/offline_defenses/crossscaleguard_offline_v2/vendor/ours_src/src/features/__init__.py": "6046b920000710702d89cec4269d29be3065b1174cb2a59d8c2971c4195a89ec"
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def audit() -> None:
    bad = []
    for name, expected in SHA256.items():
        p = ROOT / name
        actual = digest(p) if p.is_file() else "MISSING"
        if actual != expected:
            bad.append((name, expected, actual))
    if bad:
        for name, wanted, got in bad:
            print(f"FAIL {name}\n  expected: {wanted}\n  actual:   {got}")
        raise SystemExit("Frozen V3 asset integrity FAILED")
    config = json.loads((V3 / "artifacts/training_config.json").read_text())
    schema = json.loads((V3 / "artifacts/feature_schema.json").read_text())
    assert config["thresholds"]["full fusion"] == 0.8711460070813885
    assert len(schema["session_54d"]) == 54 and len(schema["strict_cross_17d"]) == 17
    assert len(schema["fusion_inputs"]) == 5
    print(f"FROZEN V3 INTEGRITY PASS: {len(SHA256)} verified files; threshold 0.8711460070813885")


def synthetic_touch_log(path: Path) -> None:
    # Synthetic gestures exercise only the parser and model interface.
    # This is NOT a human/agent test and does not imply any accuracy number.
    lines = []
    def ev(t, code, value):
        lines.append(f"[ {t:.6f}] /dev/input/event7: EV_ABS {code} {value}")
    start = 1700000000.0
    for g in range(9):
        t = start + 1.2 * g
        ev(t, "ABS_MT_TRACKING_ID", f"{g+1:08x}")
        for k in range(5):
            tx = t + 0.03 * (k + 1)
            x = 120 + 29 * g + 11 * k
            y = 410 + 33 * g + 23 * k
            ev(tx, "ABS_MT_POSITION_X", f"{x:08d}")
            ev(tx + 0.0001, "ABS_MT_POSITION_Y", f"{y:08d}")
        ev(t + 0.24, "ABS_MT_TRACKING_ID", "ffffffff")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def smoke() -> None:
    spec = importlib.util.spec_from_file_location("crossscaleguard_frozen_p10", V3 / "run.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("P10 run.py unavailable")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    model, config, schema = mod.load()
    with tempfile.TemporaryDirectory(prefix="p10_shadow_smoke_") as td:
        log = Path(td) / "synthetic_touch.log"
        synthetic_touch_log(log)
        pred = mod.predict(log, model, config, schema)
        if pred["status"] != "ok":
            raise RuntimeError("Frozen V3 synthetic interface failure: " + json.dumps(pred))
        score = float(pred["final_score"])
        assert math.isfinite(score) and 0 <= score <= 1
        assert pred["n_actions"] == 9
        assert float(pred["threshold"]) == 0.8711460070813885
        print(f"FROZEN V3 PREDICTION SMOKE PASS: nine synthetic gestures; score={score:.9f}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true", help="Also load original frozen weights and execute synthetic interface prediction")
    args = p.parse_args()
    audit()
    if args.smoke:
        smoke()


if __name__ == "__main__":
    main()
