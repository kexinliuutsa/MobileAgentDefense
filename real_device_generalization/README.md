# Real-device GUI-agent generalization: AutoGLM · Mobile-Agent-E · MAI-UI

**Experiment branch; not part of the frozen main release.** Three independent GUI-agent planners use a prevalidated Mac-to-Android Type-B executor with a kernel `getevent` shadow capture. Frozen detector heads and their native thresholds remain untouched. The unified runner defaults to **read-only preflight**: only an explicit `--execute`, followed by the selected adapter's interactive confirmation, can start a phone task.

## Exactly which three GUI agents?

| Agent | Source in this branch | Official integration and limitations |
| --- | --- | --- |
| **Open-AutoGLM / PhoneAgent** | [`adapters/run_autoglm.py`](adapters/run_autoglm.py) | Cloned Open-AutoGLM `phone_agent` planner, with the validated original Type-B `Shadow`; model typically `autoglm-phone` |
| **X-PLUG Mobile-Agent-E** | [`adapters/run_mobile_agent_e.py`](adapters/run_mobile_agent_e.py) | Original `X-PLUG/MobileAgent/Mobile-Agent-E` inference (`inference_agent_E.run_single_task`, `MobileAgentE.agents.Operator`); patches **only** Tap/Swipe IO to the validated Type-B executor, refuses unexpected interface changes |
| **MAI-UI-8B** | [`adapters/run_mai_ui.py`](adapters/run_mai_ui.py) | Official MAI-UI navigation agent, prompt and action parser; adapter maps its supported actions to validated Type-B touches |

**Tencent AppAgent is not used or included in this experiment.** Mobile-Agent-E and Tencent AppAgent are different projects.

The three adapter files preserve previously supplied original Mac integration scripts; we did not replace their GUI decision logic or synthesize any touch evidence. AutoGLM's validated `Shadow` functions also serve as the shared Type-B monitor used by the other two adapters. This repository does **not** bundle the official agent repositories, model weights, service accounts or the Android Type-B binary.

## Frozen comparison contract

- **CrossScaleGuard P10 Frozen V3:** four evidence streams (Session, Strict, Human Reference, Fake Artifact) and frozen Full Fusion decision at `0.8711460070813885`. Never substitute the older V1 OR V2 OR V3 rule-based model.
- **Reconstructed AHB Author P74:** published author five-cluster classifier weights, original `UltimateClassifier.predict()`, P73 restored outer scaler, P31 Tap/Interval compatibility, equal-prior `score > 0`. P74 can be scored only for tasks with an **independently verified, predeclared original cluster ID 0–4**. A new app without such mapping is **V3-only / Author not estimable**, not an excuse to guess a cluster.
- **Same physical observation:** completed `ABS_MT_TRACKING_ID ffffffff` + `SYN_REPORT` touch prefixes, independently parsed by each frozen detector. The author's `2N−1` evidence events contain interval updates, which must not be counted as touch gestures.
- **Metrics:** report per-agent coverage, raw touches, parser abstentions, final detection, earliest alarm, latency and independently judged task completion. Human FPR requires separate labeled *Human* sessions. A later final-session decision cannot retroactively prevent earlier actions. This is a **Shadow**, not a blocking guard.
- **Native task logic:** no change to original GUI agent planner, prompt or learned model as a result of defender outcomes. Mobile-Agent-E sets single-task operation with its official default perception and disabled cross-task experience retrieval, as in the saved adapter. Different adapter-specific settings should be logged rather than called identical planners.

## First: offline checks (no phone, no API)

```bash
git clone -b experiment/real-device-generalization-v1 \
  https://github.com/kexinliuutsa/MobileAgentDefense.git \
  ~/Desktop/MobileAgentDefense-generalization

cd ~/Desktop/MobileAgentDefense-generalization

python real_device_generalization/runner.py \
  --agent autoglm --expected-package com.tencent.qqmusic --self-test

python real_device_generalization/dual_replay.py --self-test
```

GitHub CI compiles all three adapters and executes both offline contract tests. This does **not** prove device compatibility, P74 per-prefix parity or target-app generalization.

## Second: read-only preflight for all three agents

Use the Python environment already working with your local agent dependencies. The underlying preflight checks the actual official source files, existing verified Type-B binary and foreground application. **No model inference, no touch, no task execution.**

```bash
ROOT="$HOME/Desktop/MobileAgentDefense-generalization"
PROJECT="$HOME/Desktop/GUI_AHB_PAPER_REBUILD"
RUNNER="$ROOT/real_device_generalization/runner.py"

# AutoGLM
python "$RUNNER" \
  --agent autoglm --project "$PROJECT" \
  --expected-package com.tencent.qqmusic

# Mobile-Agent-E: point at the directory containing inference_agent_E.py
python "$RUNNER" \
  --agent mobile-agent-e --project "$PROJECT" \
  --mobile-agent-e-repo "$HOME/Desktop/MobileAgent/Mobile-Agent-E" \
  --expected-package com.tencent.qqmusic

# MAI-UI
python "$RUNNER" \
  --agent mai-ui --project "$PROJECT" \
  --mai-repo "$HOME/Desktop/MAI-UI" \
  --expected-package com.tencent.qqmusic
```

If the Mobile-Agent-E location differs, pass its actual path (or omit the flag to use the original adapter's known locations / `MOBILE_AGENT_E_HOME`). The official `MobileAgentE/agents.py`, `MobileAgentE/controller.py` and `inference_agent_E.py` interfaces must match the tested version. If not, preflight fails closed: **never silently fall back to `adb input tap/swipe`.**

## Single-run **live** dual-defense experiment (not executed yet)

The prior AutoGLM/Mobile-Agent-E/MAI-UI → validated Type-B executor → kernel getevent chain remains unchanged. **Once** each genuine Type-B tap/swipe ends, the original Shadow scores native Frozen P10 V3 (eligible online only from g≥5) and the added [`live_dual_shadow.py`](live_dual_shadow.py) evaluates the **same raw touch prefix** with frozen reconstructed P74 Author Ultimate. The Agent does not repeat the task; both detectors are observation-only. The original Agent still makes all GUI decisions and the original native V3 result is returned without modification.

**No new experiments are being run as part of this code release.** An eventual Mobile-Agent-E example with a task cluster independently established **before execution**:

```bash
ROOT="$HOME/Desktop/MobileAgentDefense-generalization"
PROJECT="$HOME/Desktop/GUI_AHB_PAPER_REBUILD"
RUNNER="$ROOT/real_device_generalization/runner.py"

# C is only a placeholder; never invent a task cluster for a new app.
# SOURCE_RECORD must document how the AHB ORIGINAL task cluster was verified.
python "$RUNNER" \
  --agent mobile-agent-e \
  --project "$PROJECT" \
  --mobile-agent-e-repo "$HOME/Desktop/MobileAgent/Mobile-Agent-E" \
  --expected-package com.tencent.qqmusic \
  --task-id qqmusic_mobile_e_001 \
  --task "在 QQ 音乐搜索一位歌手，查看专辑和歌曲详情后停止。禁止购买、收藏、登录、发送消息或更改设置。" \
  --task-cluster C \
  --cluster-evidence "SOURCE_RECORD: verified before experiment" \
  --max-steps 12 \
  --execute
```

The command is an **example only**, not a request to run the phone now. If no independently substantiated original AHB cluster exists (especially for a new unseen application), use explicit `--v3-only` instead of asserting a misleading P74 comparison. No Human FPR can be inferred from the three GUI-agent traces alone.

Mobile-Agent-E's native `--max-steps` limits planner iterations; `--max-actions` is **not** a separate Mobile-Agent-E hardware gesture limit. Its official API environment supplies `BACKBONE_TYPE`, `QWEN_API_KEY` and the selected backbone provider key; never pass an artificial `--model` argument to this original Mobile-Agent-E interface.

### What each live run records

The existing adapter still creates its native directory under `PROJECT/real_device_online/`:
- `autoglm_v3_shadow/<run-id>/`
- `mobile_agent_e_typeb_shadow/<run-id>/`
- `mai_ui_8b_typeb_shadow/<run-id>/`

Each eligible live-dual session now also contains:

| Local file | Purpose |
| --- | --- |
| `virtual_events_normalized.log` | Independently captured real Type-B virtual touchscreen events |
| `v3_prefix_results.jsonl` | **Untouched** original P10 V3 EAD g≥5 prefix results |
| `dual_online_prefixes.jsonl` | One row per completed physical touch: P74 and V3 eligibility, native scores, decisions, independent parser coverage, processing latency, observation timestamp, and SHA256 of identical physical prefix |
| `paired_online_metrics.json` | First live alarm gesture/UTC, anytime detection, native retrospective session-final decision, P74 final-prefix parity, valid-prefix coverage, detector scoring mean/median/p95 ms, frozen artifact SHA256 and any parser failures |
| `generalization_manifest.json` | Agent, task ID, exact foreground app, source adapter hash, task-cluster provenance, ground truth actor, run status |
| `summary.json` | Original agent's task-completion/self-report and V3 native summary (not rewritten by dual sidecar) |

**Online vs final is intentionally separate.** P10 V3's first live alarm uses g≥5 as originally implemented; P74's original cumulative evidence uses recognized finished gestures, with every interval update excluded from the gesture clock. A session with fewer than five gestures can have a retrospective V3 final classification but **cannot** be credited with an earlier g≥5 live alert. Scoring is synchronous after each action and therefore adds measured overhead before the next agent decision; it is not a real-time zero-overhead blocking defense.

### Optional second read-only parity replay (not required for paired live scoring)

If one wants independent consistency checks after the run, add `--audit-replay-after` to the eventual live command. It replays the SAME saved trace offline using [`dual_replay.py`](dual_replay.py), saves `independent_dual_audit_replay.json`, and performs **no additional phone actions**. This is a verification step; the paired online scores are already saved during the single Agent run.

### Aggregate metrics without inventing Human FPR

After multiple recorded sessions, this script produces total and **Agent × App** tables, including native final accuracy/recall (where identifiable), anytime recall, first-alarm gesture index, g5/g11 rates for all-session and reached-g denominators, coverage, per-detector timing, and manually reported task completion:

```bash
python "$ROOT/real_device_generalization/summarize_generalization.py" \
  --runs-root "$PROJECT/real_device_online" \
  --out "$PROJECT/real_device_online/generalization_metrics.json"
```

**Human FPR, balanced accuracy and accuracy remain null (not zero)** until separately collected and correctly labeled Human sessions are included. Report per-detector valid final denominators and paired subset denominators separately. A model self-declared completion is not an independently judged task success. Do not claim an agent-only experimental run measures user burden, override behavior or Human FPR.

Original P74 weights/Scaler are **not redistributed**; [asset pointers](../author_ultimate/external_asset_pointers.json) and frozen hashes are verified before live execution. Predeclared cluster provenance is mandatory for dual trials, and an invalid/unknown task cluster is never silently replaced with another model.


## Publication / verification status

This branch is a **Draft PR**, not merged into frozen `main`. Historical P74 cohort scores belong to the original 1,752 paired sessions, **not** these new pilot trajectories. No three-agent phone run, new generalization result or human false-alarm estimate is claimed by this code upload. Before merging: three native preflight checks, a real-log two-detector parity audit on an eligible task, one authorized pilot per Agent, and manual task-completion verification.
