# Real-device GUI-agent generalization (research branch)

A **non-blocking shadow** experiment harness for three previously validated Mac-to-Android Type-B GUI-agent adapters. This is an experiment workstream, **not a change to the frozen defenses on `main`**. Real phone execution always requires explicit `--execute` and the underlying adapter's interactive authorization; the default is **read-only preflight**.

## Existing agent integration paths

| Agent | Recovered adapter | Native agent path | Notes |
| --- | --- | --- | --- |
| AutoGLM / PhoneAgent | [`adapters/run_autoglm.py`](adapters/run_autoglm.py) | Cloned Open-AutoGLM repo and `phone_agent`; validated Mac Type-B `Shadow` | Direct native action execution; default model `autoglm-phone` |
| Tencent AppAgent | [`adapters/run_appagent.py`](adapters/run_appagent.py) | Existing AppAgent repo official prompt files; `--ui-mode auto/element/grid` | Standalone adapter using official prompts/action syntax, **not untouched upstream AppAgent**; imports our validated AutoGLM Type-B Shadow |
| MAI-UI-8B | [`adapters/run_mai_ui.py`](adapters/run_mai_ui.py) | Local MAI-UI repository, official navigation prompt and parser, compatible vLLM endpoint | Official planner with validated Type-B action adapter; imports AutoGLM Type-B Shadow |

The three adapter sources were taken unchanged from previously supplied working Mac pilot scripts. No alternative ADB `input tap/swipe` fallback, fake gesture interpolation, model retraining or threshold reconstruction has been introduced. Source-level adapter provenance is tracked by SHA256 in each new run's `generalization_manifest.json`.

## Experiment invariants

1. **Real physical Type-B only.** A native agent chooses actions; Type-B executor injects contacts; the independent `getevent` capture is the observed trace. ADB keyboard text and Back/Enter key events are separate non-touch events; do not count them as completed physical contacts.
2. **Frozen V3 full fusion:** Original P10 `run.py`, original 54D + 17D feature extractors, existing model files, decision `score >= 0.8711460070813885`. Do not substitute legacy V1 OR V2 OR V3 pipelines.
3. **P74 original Author Ultimate:** only if a **predeclared, independently verified source task-cluster ID** (0–4) is appropriate to the task. Use original released author weights + P73 recovered outer Scaler, P31 Tap/Interval compatibility, native `UltimateClassifier.predict()` with equal prior `score > 0`. Do not assign arbitrary clusters just to score a new app.
4. **Same raw prefix, separate parsers:** Both detectors receive the same completed `TRACKING_ID ffffffff` + `SYN_REPORT` prefix, and produce their own eligibility, score, first alarm and last observed final verdict. Author's 2N-1 cumulative evidence events are reduced to the N **gesture-end** updates; interval evidence events do not count as gestures.
5. **Performance definitions:** Agent detection recall, Human FPR, prefix anytime alarms, final-session verdict, action steps, physical contacts, task success, and latency must be reported **separately**. An end-of-session decision is not a preventative intervention. Human FPR needs real labeled Human sessions, not just agent-only pilots.
6. **True generalization:** reserve truly unseen applications, tasks, interactions, and devices for later assessment. Avoid selecting thresholds from evaluation outcomes; report coverage, failures and exclusions.

## Mac setup

Clone this branch. For the original historical Mac setup, the **project** is the existing `~/Desktop/GUI_AHB_PAPER_REBUILD` folder containing frozen V3 and (if P74 is used) the original-author assets and P20/P31/P74 source. Separately retain the cloned upstream AutoGLM, AppAgent, MAI-UI code and the validated Type-B phone binary.

```bash
git clone -b experiment/real-device-generalization-v1 \
  https://github.com/kexinliuutsa/MobileAgentDefense.git
cd MobileAgentDefense

# Laptop-only tests (no ADB / no API / no gesture)
python real_device_generalization/runner.py \
  --agent autoglm --expected-package com.tencent.qqmusic --self-test
python real_device_generalization/dual_replay.py --self-test

# FIRST phone step: hardware/source preflight only; NEVER touches the phone
python real_device_generalization/runner.py \
  --agent autoglm \
  --project ~/Desktop/GUI_AHB_PAPER_REBUILD \
  --expected-package com.tencent.qqmusic

# Same preflight pattern for AppAgent and MAI-UI; pass --appagent-repo
# or --mai-repo when clones are outside the default ~/Desktop paths.
```

A real AutoGLM read-only browsing pilot, **only after the previous preflight passes**:

```bash
python real_device_generalization/runner.py \
  --agent autoglm \
  --project ~/Desktop/GUI_AHB_PAPER_REBUILD \
  --expected-package com.tencent.qqmusic \
  --task-id music_navigation_001 \
  --task "在 QQ 音乐中搜索一位歌手，查看专辑和歌曲详情，然后停止。不得购买、收藏、发送消息或更改账户。" \
  --max-steps 25 \
  --execute
```

This `--execute` run still performs a fresh read-only phone preflight, then requests the adapter's own interactive consent. Do not enable execution on a phone holding payment/account credentials or private material. Agent models may receive screenshots over the selected API. No screenshot, token or real-device trace is to be committed to GitHub.

For a **P74-eligible** task with *independently validated cluster* `C` (integer 0–4), pass `--task-cluster C --score-after` to run a **second, read-only** frozen dual replay after the native agent finishes. Do not set a guessed `C`. If this new task's original cluster is undefined, run V3-only and mark P74 as *not estimable* for this case.

## Offline paired replay (no Android interaction)

```bash
python real_device_generalization/dual_replay.py --self-test

# File-hash-only preflight; does not load pickles or call the phone
python real_device_generalization/dual_replay.py \
  --project ~/Desktop/GUI_AHB_PAPER_REBUILD --preflight-only

# Supply a REAL existing normalized Type-B getevent log, a genuine
# source task cluster, and a unique session ID.
python real_device_generalization/dual_replay.py \
  --project ~/Desktop/GUI_AHB_PAPER_REBUILD \
  --log ~/Desktop/GUI_AHB_PAPER_REBUILD/real_device_online/EXISTING_RUN/virtual_events_normalized.log \
  --task-cluster C \
  --session-id example_001 \
  --out ~/Desktop/GUI_AHB_PAPER_REBUILD/real_device_online/EXISTING_RUN/paired_prefixes.json
```

The `C` placeholder is deliberate: replace only with a verified source mapping. If the original parser cannot recognize a new Type-B log or asset SHA disagrees, the replay **fails**; it never substitutes another Author model, surrogate threshold, or synthetic trajectory. `--score-after` additionally stores `dual_prefix_scores.json` in the local run directory.

## Scope and limitations

- No new phone experiments, prospective detection accuracy, or new Human false-positive estimates have been claimed.
- Historical P74 paper counts (Author: 554/1,310 agent detections and 0/442 human FPs; Frozen V3: 1,191/1,310 and 2/442) belong to the old 1,752-session paired cohort, **not** to the new real-device pilot.
- Frozen V3 can be cloned and loaded from GitHub main. P74 source/weights/scaler are **external** and remain in the user's original audited Mac workspace; see [P74 asset pointers](../author_ultimate/external_asset_pointers.json).
- No recorded source-to-device generalization, AppAgent/MAI agent authorization, phone model inference or true task-success checking has been verified by GitHub CI.
- This research branch is intentionally **not merged to `main`** until preflight, one old-log replay and an approved phone pilot pass.
