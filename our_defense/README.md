# Our Defense — CrossScaleGuard Frozen V3 (P10 Full Fusion)

This folder restores **our own frozen CrossScaleGuard V3 source and model heads** from a previously committed release staging folder in this very GitHub repository. The original Git history source was commit `a6c4de2a01b620ef5f2c4d616c23e4c1ed44dae1`, under `MobileAgentDefense 2/our_defense/`. Model binary blobs were reused directly without refitting or regenerating them.

**Do not confuse this with the reconstructed AHB Author Ultimate in [`../author_ultimate/`](../author_ultimate/).** The two algorithms are independent; the author baseline uses an original task-cluster ID, whereas P10 Frozen V3 Full Fusion does not.

## Primary frozen model: `offline_v3_source/`

The authoritative P10 Full Fusion release ingredients available in this folder are:

| Path | Role |
| --- | --- |
| `offline_v3_source/artifacts/session_head.joblib` | Session-distribution evidence head |
| `offline_v3_source/artifacts/strict_head.joblib` | Strict cross-action evidence head |
| `offline_v3_source/artifacts/human_reference_head.joblib` | Human-reference evidence head |
| `offline_v3_source/artifacts/session_strict_head.joblib` | Session + strict combination head |
| `offline_v3_source/artifacts/fusion_head.joblib` | Frozen full-fusion decision head |
| `offline_v3_source/artifacts/fake_artifact_calibration.json` | Frozen fake-action calibration evidence |
| `offline_v3_source/artifacts/feature_schema.json` | Feature names / ordering contract |
| `offline_v3_source/artifacts/training_config.json` | Original selected thresholds and training metadata |
| `offline_v3_source/src/crossscaleguard_v3/` | P10 V3 algorithmic modules |
| `offline_v2_dependencies/src/crossscaleguard/` | Feature parser / adapter / extractor source dependencies |

**Frozen Full Fusion threshold:** `0.8711460070813885` (read from `training_config.json`, not retuned).

This source contains training utilities, but **do not run training to reproduce the frozen operating point**. The full-fusion model reads the stored artifacts, preserved by Git object SHA and their original recorded SHA256 hashes. See [`FROZEN_ASSET_SHA256.json`](FROZEN_ASSET_SHA256.json).

### What this copy does *not* establish

The original P10 `run.py` and its matching model and feature-extraction sources **have now been restored with hash checks** in `../01_clean_code/offline_defenses/`. The original `run.py` SHA256 is `c109f1324ed0266f78f43e103b050a5572114735a6dddb1d2f7cf714dc7c373c`, and the historical native 54D and 17D feature sources match their original manifest checksums. A read-only [verification and synthetic-smoke script](verify_frozen_release.py) checks these files. CI runs this check on Python 3.11. A passing CI smoke validates the runnable scorer interface, **not historical score-level parity or real-world accuracy**.

The release now preserves the exact canonical sibling directory layout and artifact filenames used in the original Mac project. Clone the repository, install `requirements-frozen-v3.txt`, run `python our_defense/verify_frozen_release.py --smoke`, then use `python 01_clean_code/offline_defenses/crossscaleguard_offline_v3/run.py --mode predict --log /path/to/virtual_events_normalized.log`. This is shadow scoring; it does not execute or control gestures.

The `split_manifest.json` used in original experiment bookkeeping was **not republished in this branch**, pending review for identifier and data privacy. It is not a model weight.

## Legacy and reference code: NOT the P10 full-fusion runtime

The `frozen_online_v3/` scripts are saved historic research implementations. In particular, `evaluation/frozen_deployment_defense.py` documents a separate **V1 OR V2 OR V3** rule-based three-part deployment and `real_device_monitor/online_trajectory_defense_v3.py` expects dependencies such as `dynamic_probe_runtime_v2` and a separate evidence-region calibration artifact. These dependencies are not provided here.

The `runtime_reference/m5b_runtime/` code contains adapter experiments and validation checks, not the original P10 frozen entry point.

**Do not compare or claim P10 results by silently switching to these legacy scripts.** We preserve them for provenance and future review, not as an interchangeable primary detector.

## Comparison protocol

For each independently acquired valid physical completed Type-B gesture prefix, score:

- Reconstructed AHB Author Ultimate with the validated real task-cluster ID, original released author model weights, P73 recovered scaler, and the declared equal-prior `score > 0` decision.
- CrossScaleGuard Frozen V3 Full Fusion with its original model weights, original feature extraction, and threshold `0.8711460070813885`; **no cluster information or threshold matching**.

Report valid-prefix coverage, first online alarm gesture, last valid full-session verdict, Human false alarms from separately collected Human sessions, actual inference latency, and task completion independently. An offline final-session verdict is not an online preventive intervention.

### Historical P74 paired cohort (offline, NOT real device)

| Detector | Agent positive / 1,310 | Human false alarms / 442 |
| --- | ---: | ---: |
| Reconstructed Author Ultimate | 554 (42.29%) | 0 (0.00%) |
| Frozen CrossScaleGuard V3 | 1191 (90.92%) | 2 (0.45%) |

These values come from previously validated P74 saved row-level predictions, **not from any new re-evaluation of the files restored into GitHub today**.

## Release integrity

Five weights, the calibration/schema/config JSONs and source files were restored from immutable Git blobs that had previously been uploaded to this repository. We did not load potentially unsafe pickle/joblib binaries or execute inference during this GitHub restoration. Independently validate trusted sources and versions before loading serialized Python objects. No Human touch logs, screenshots, account credentials, or AHB author's model weights are included here.

If you need an independently runnable, end-to-end package, use the original P10 `run.py` restored under `01_clean_code/offline_defenses/` and validate score-level parity on a saved real-device trajectory; the synthetic CI test alone is not enough to establish prospective performance.
