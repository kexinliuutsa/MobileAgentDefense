# Author defense reference (AHB)

This directory contains authentic author-side source files recovered from the user-provided P19 source bundle. `analysis/processing/judge_library.py` contains `UltimateClassifier.predict()`.

`repair/official_predict_patch.py` provides the threshold-posterior correction from the user's archived `m4z3_direct_ultimate_predict.py`. It **patches only a module-global helper** and still calls the author's original `UltimateClassifier.predict()`; it does not change the learned models or the native decision operating point.

**Not self-contained in this staging ZIP:** original author classifier pickle files and some upstream imports (e.g. `calculate_roc_auc_from_feature`, `extract_feature_of_swipes`) are only on the original Mac project. Do not claim author native model evaluation has been reproduced from this staging ZIP.

Upstream origin: `Gebro13/Passing-the-Turing-Test-on-Screen-Agent-Humanization-Benchmark`. Verify the upstream source/model redistribution terms before making this third-party material public; do not imply a license grant.
