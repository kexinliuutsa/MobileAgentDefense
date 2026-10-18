# Our defense: retrieved source vs frozen deployment

- `offline_v3_source/` contains available **original V3 offline algorithm source**, not frozen trained `.joblib` artifacts.
- `runtime_reference/m5b_runtime/` is a runtime-monitoring **reference**; it is NOT a replacement for the user's frozen V3 native deployment.
- `frozen_online_v3/` will be created by `scripts/complete_with_local_sources.py` on the user's Mac, copying the actual frozen implementation from `GUI--Defense_Strategy` without retraining or recalibration.

The staging package must NOT be represented as a reproducible complete frozen defense until the local files and model assets have been imported and tested.
