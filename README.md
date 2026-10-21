# Reconstructed AHB Author Ultimate — P74 Online Shadow Evaluation

This repository branch documents our **unofficial research reconstruction** of the original AHB five-cluster `UltimateClassifier.predict()` evaluator and its historical causal completed-touch-prefix replay. It is **not an upstream official release** or a tested plug-and-play Android runtime.

Original upstream: https://github.com/Gebro13/Passing-the-Turing-Test-on-Screen-Agent-Humanization-Benchmark

## Restoration rationale

- **Released weights unchanged:** the five task-cluster Swipe SVM/XGB, Tap, and inter-action interval classifiers are loaded from original author assets. The task cluster ID (0–4) must be supplied and validated for each session.
- **Restored preprocessing:** P73 reconstructs the outer `StandardScaler` used during original Swipe training. P74's `OuterScaledClassifier` only applies this scaler at inference, forwarding probabilities to original frozen classifiers.
- **Independent verification:** P75 replays the original training preprocessing per cluster and checks the reconstructed outer scaler and the embedded SVM inner scaler. All five clusters achieved `STRONG_NUMERIC_EQUIVALENCE`; this is strong numerical evidence, not byte-identical proof.
- **Compatible Tap/Interval posterior:** existing P31 loader adapts original fitted confusion count objects with 0.5 pseudocount smoothing. This is a compatibility intervention, not an untouched official binary release.
- **Decision:** original `UltimateClassifier.predict()` cumulative score, equal prior `prior_log_odds=0`, binary Agent when score > 0. **This is our declared reproduction cutoff, not a documented author-published deployment threshold.** No evaluation FPR matching or retuning.

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
