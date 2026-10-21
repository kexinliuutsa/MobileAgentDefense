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

## Third: approved single-task phone pilot

Only after preflight passes, start with a harmless QQ Music navigation task on a dedicated non-sensitive test phone. The native adapter asks for the operator's confirmation. **No purchase, personal data export, account changes, messages or posting.**

```bash
python "$RUNNER" \
  --agent mobile-agent-e \
  --project "$PROJECT" \
  --mobile-agent-e-repo "$HOME/Desktop/MobileAgent/Mobile-Agent-E" \
  --expected-package com.tencent.qqmusic \
  --task-id qqmusic_mobile_e_001 \
  --task "在 QQ 音乐搜索一位歌手，查看专辑和歌曲详情后停止。禁止购买、收藏、登录、发送消息或更改设置。" \
  --max-steps 12 \
  --execute
```

**Mobile-Agent-E model/API configuration is controlled by the official environment** (`BACKBONE_TYPE`, its corresponding `OPENAI_API_KEY` / `GEMINI_API_KEY` / `CLAUDE_API_KEY`, and `QWEN_API_KEY` for its captioning provider). Do not supply `--model` for Mobile-Agent-E in this wrapper; that is not part of its original CLI. Never commit credentials, model responses, device screenshots, logs, or raw touch trajectories.

The native Mobile-Agent-E adapter writes into `PROJECT/real_device_online/mobile_agent_e_typeb_shadow/<run-id>/`. AutoGLM writes under `autoglm_v3_shadow/`; MAI-UI under `mai_ui_8b_typeb_shadow/`. The orchestrator saves a `generalization_manifest.json` referencing the source adapter SHA256 and declared task metadata.

For Mobile-Agent-E, the official runner uses `--max-steps` to limit planner iterations; it has no independent `--max-actions` flag. Do not claim that `--max-actions` enforces a separate hardware budget for that agent.

## Frozen paired replay after a real run (no additional device actions)

With a previously verified source task cluster `C`, both detectors can replay the **same captured raw Type-B log**. Run `dual_replay.py --preflight-only` first to verify the locally installed original Author source, weights, scaler and P10 run.py hashes; then:

```bash
python "$ROOT/real_device_generalization/dual_replay.py" \
  --project "$PROJECT" \
  --log "$PROJECT/real_device_online/mobile_agent_e_typeb_shadow/ACTUAL_RUN/virtual_events_normalized.log" \
  --task-cluster C \
  --session-id qqmusic_mobile_e_001 \
  --out "$PROJECT/real_device_online/mobile_agent_e_typeb_shadow/ACTUAL_RUN/dual_prefix_scores.json"
```

Replace `ACTUAL_RUN` with the actual directory and `C` only with the verified original cluster. Otherwise, record V3 without fabricating Author eligibility. The optional `runner.py --score-after` performs the same separate no-phone replay after execution but **requires** `--task-cluster`.

P74 local assets remain outside this repository: see [P74 external asset pointers](../author_ultimate/external_asset_pointers.json). Raw observation must come from an actual Type-B capture and must not be synthesized.

## Publication / verification status

This branch is a **Draft PR**, not merged into frozen `main`. Historical P74 cohort scores belong to the original 1,752 paired sessions, **not** these new pilot trajectories. No three-agent phone run, new generalization result or human false-alarm estimate is claimed by this code upload. Before merging: three native preflight checks, a real-log two-detector parity audit on an eligible task, one authorized pilot per Agent, and manual task-completion verification.
