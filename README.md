# MobileAgentDefense — two frozen behavioral defense baselines

This release branch contains two distinct research defenses side-by-side:

| Folder | Model | Purpose |
| --- | --- | --- |
| [`author_ultimate/`](author_ultimate/) | **AHB Author Ultimate (P74, restored original preprocessing)** | Author's original five task-cluster models, original cumulative scorer, P73/P75 restored outer scaler and Tap/Interval compatibility. Original weights/source/scaler are **external links only**. |
| [`our_defense/`](our_defense/) | **CrossScaleGuard Frozen V3 (P10 Full Fusion)** | Our frozen trained heads and corresponding extracted algorithm sources. Five `.joblib` model heads and original `training_config.json` are committed. Older V1/V2/V3-OR code is separately labeled as legacy. |

**Publication status:** This is an auditable source-and-artifact release, not an independently validated standalone real-device dual-defense runtime. The two detectors do not share weights or decision thresholds. The Author uses its original task cluster; CrossScaleGuard full fusion does not.

**Release status:** The original P10 runtime source, its original feature extraction source, and frozen model weights are bundled under their canonical Paper Rebuild paths. The GitHub Action validates frozen SHA256 hashes and executes a synthetic full-model inference smoke test. This does not replace a prospective real-device evaluation.

---

## Run our frozen P10 Full Fusion (from a fresh clone)

For our CrossScaleGuard baseline **no external source repo or separate model download is needed**. It uses our released weights and original feature extractors under `01_clean_code/offline_defenses/`. Python 3.11 with pinned package versions is recommended.

```bash
git clone https://github.com/kexinliuutsa/MobileAgentDefense.git
cd MobileAgentDefense

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-frozen-v3.txt

# Read-only source/model hash audit + synthetic end-to-end scoring
python our_defense/verify_frozen_release.py --smoke

# Offline/shadow scoring on an independently collected Android getevent log
python 01_clean_code/offline_defenses/crossscaleguard_offline_v3/run.py \
  --mode predict \
  --log /path/to/virtual_events_normalized.log
```

Frozen threshold: **0.8711460070813885**. The historical `run.py` and the frozen Session/Strict native feature extraction sources were restored byte-for-byte by SHA256. The [Frozen V3 README](our_defense/README.md) explains provenance and why the older V1 OR V2 OR V3 implementation must not be confused with P10 Full Fusion. The [GitHub Actions workflow](.github/workflows/frozen-p10-audit.yml) independently checks the published files on Linux.

The Author Ultimate P74 baseline is different: its released upstream model binaries and the P73 reconstructed Scaler remain **external**, documented in [asset pointers](author_ultimate/external_asset_pointers.json). The historical P74 replay scripts also rely on original Paper Rebuild P20/P31 modules. **The Author baseline is not a standalone online deployment here.**

---

# Reconstructed AHB Author Ultimate — P74 Online Shadow Evaluation

This repository branch documents our **unofficial research reconstruction** of the original AHB five-cluster `UltimateClassifier.predict()` evaluator and its historical causal completed-touch-prefix replay. It is **not an upstream official release** or a tested plug-and-play Android runtime.

Original upstream: https://github.com/Gebro13/Passing-the-Turing-Test-on-Screen-Agent-Humanization-Benchmark

## Restoration rationale

- **Released weights unchanged:** the five task-cluster Swipe SVM/XGB, Tap, and inter-action interval classifiers are loaded from original author assets. The task cluster ID (0–4) must be supplied and validated for each session.
- **Restored preprocessing:** P73 reconstructs the outer `StandardScaler` used during original Swipe training. P74's `OuterScaledClassifier` only applies this scaler at inference, forwarding probabilities to original frozen classifiers.
- **Independent verification:** P75 replays the original training preprocessing per cluster and checks the reconstructed outer scaler and the embedded SVM inner scaler. All five clusters achieved `STRONG_NUMERIC_EQUIVALENCE`; this is strong numerical evidence, not byte-identical proof.
- **Compatible Tap/Interval posterior:** existing P31 loader adapts original fitted confusion count objects with 0.5 pseudocount smoothing. This is a compatibility intervention, not an untouched official binary release.
- **Decision:** original `UltimateClassifier.predict()` cumulative score, equal prior `prior_log_odds=0`, binary Agent when score > 0. **This is our declared reproduction cutoff, not a documented author-published deployment threshold.** No evaluation FPR matching or retuning.

## Exact external asset pointers (no binaries committed)

Machine-readable paths, roles, and SHA256 checksums for the **five external P74 inputs** are in [`author_ultimate/external_asset_pointers.json`](author_ultimate/external_asset_pointers.json). Resolve these paths **relative to your local `GUI_AHB_PAPER_REBUILD` project root**, not relative to the GitHub checkout:

| Dependency | Project-relative path | SHA256 (first 12 chars) |
| --- | --- | --- |
| Author `judge_library.py` (validated local snapshot) | `00_original/author_repo/analysis/processing/judge_library.py` | `6433b9261d1b` |
| Released Swipe classifiers | `00_original/author_repo/humanized_swipe_classifiers.pkl` | `47b9517c8f11` |
| Released Tap classifiers | `00_original/author_repo/raw_tap_classifier_us_across_clusters.pkl` | `ebf2d307fb9f` |
| Released Interval classifiers | `00_original/author_repo/interval_classifier_microseconds_across_clusters.pkl` | `4af23a501f81` |
| P73 reconstructed outer Scaler | `06_paper_tables/P68_ORIGINAL_CLUSTER_NATIVE_SESSION_TABLE/P73_AUTHOR_NATIVE_RECOVERY/candidate_outer_scalers_all_clusters.joblib` | `855f33bdac5c` |

The original [`judge_library.py` upstream path](https://github.com/Gebro13/Passing-the-Turing-Test-on-Screen-Agent-Humanization-Benchmark/blob/main/analysis/processing/judge_library.py) is linked for provenance; **the exact locally audited P74 source snapshot has the SHA256 above**, which need not equal a different upstream version or checkout. Do not download a newly changed source version and silently treat it as equivalent. The author's `.pkl` models and our P73 Scaler remain external local inputs; this manifest is **not a download URL or a copy of the assets**.

Verify before loading Python Pickle/Joblib (only load models from trusted sources):

```bash
cd ~/Desktop/GUI_AHB_PAPER_REBUILD
shasum -a 256 \
  00_original/author_repo/analysis/processing/judge_library.py \
  00_original/author_repo/humanized_swipe_classifiers.pkl \
  00_original/author_repo/raw_tap_classifier_us_across_clusters.pkl \
  00_original/author_repo/interval_classifier_microseconds_across_clusters.pkl \
  06_paper_tables/P68_ORIGINAL_CLUSTER_NATIVE_SESSION_TABLE/P73_AUTHOR_NATIVE_RECOVERY/candidate_outer_scalers_all_clusters.joblib
```

To reproduce the baseline, also retain `scripts/P31_hex_online.py` (Tap/Interval compatibility loader) and `scripts/P31_hex_frame_adapter.py` from the audited Paper Rebuild workspace. No author-model file, original data, or reconstructed serialized Scaler is being redistributed here.

## Audited historical numbers

On 1,752 valid paired sessions (1,310 Agent / 442 Human), the P74 row-level predictions yield:

| Detector | TP | FN | FP | TN | Agent Recall | Human FPR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Reconstructed Author Ultimate | 554 | 756 | 0 | 442 | 42.29% | 0.00% |
| Frozen CrossScaleGuard V3 | 1191 | 119 | 2 | 440 | 90.92% | 0.45% |

The saved `FINAL_AUTHOR_1770_AUDIT.json` reported `PASS_RECONSTRUCTED_AUTHOR_1770_AUDIT`. Reconstructed scaler SHA256: `855f33bdac5ce4fe49da528b87fe4e11024c155fcd13bc0092a079a54fbb57cb`. These are offline historical results; they do not establish prospective Android effectiveness or independence from original training sessions.

## Files

- `author_ultimate/p74_reconstructed_session_eval.py` — original five-cluster session-final evaluation with restored outer scaler.
- `author_ultimate/p75_verify_original_scaler.py` — verifies scaler statistics on original author training data.
- `author_ultimate/final_p74_audit.py` — hard-gated hash, scaler, frozen model and row-level result audit.
- `author_ultimate/online_raw_touch_prefix_v3.py` — historical causal raw-touch-completion-prefix replay, including final-verdict consistency checks.

**These scripts retain original project imports and are not standalone.** In the existing `GUI_AHB_PAPER_REBUILD/scripts/` workspace, restore original filenames `P74_original_author_reconstructed_scaler_1770.py`, `P75_verify_author_scaler_equivalence.py`, `FINAL_author_1770_audit.py`, and `ONLINE_1770_RAW_TOUCH_PREFIX_V3.py`, respectively. They depend on `P20_four_model_runner.py`, `P31_hex_online.py`, `P31_hex_frame_adapter.py`, the P73 scaler bundle, author weights/source, and the existing Frozen V3 evaluator. Run read-only self-test:

```bash
cd ~/Desktop/GUI_AHB_PAPER_REBUILD
python scripts/ONLINE_1770_RAW_TOUCH_PREFIX_V3.py --self-test
```

The full historical replay additionally requires the locally licensed source logs and prior P74 outputs. It is not a live phone evaluation.

## Shadow online scoring contract

For future MAI-UI/AutoGLM/AppAgent integration, append actual completed Type-B touches; at each valid prefix, independently score the original author `FingerEvent` sequence with the correct predeclared cluster ID and restored P73 scaler, and independently score the same physical prefix using Frozen V3. Log gesture-end score events (not intermediate interval log-odds events) and both native decisions. Report the first Agent alarm, first Human false alarm on separately collected real Human sessions, last-session decision, scorer coverage/latency, and separately verified task completion. ADBKeyboard text and ADB key events are not Type-B gestures. Offline replay does not demonstrate live interception.

## Exclusions and provenance

No third-party original source files, original weight files, reconstructed Joblib assets, raw logs, user information, API keys, or frozen CrossScaleGuard weights are included here. Obtain upstream materials from their original authorized sources and review license and redistribution conditions. The original upstream GitHub repository does not currently expose a clearly declared license in its metadata. Cite the original AHB authors and label this as **reconstructed original-preprocessing Author Ultimate**, not an untouched original release.

Avoid substituting P50 unscaled inference, P61B global retrained components, P64 global trained components, or the unrelated M4Z2 alternative threshold for this P74 baseline.
