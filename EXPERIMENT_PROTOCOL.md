# Input-layer validation protocol

This package is a functional research prototype, not a published accuracy benchmark.

## Minimal acceptance checks

1. `doctor`: exactly one authorized ADB device, expected 1080x2400 screen, remote executable installed.
2. **Tap A/B**: on the *same stable, harmless page*, send the *same* coordinate via ordinary ADB and Type-B uinput, and compare the actual app transitions. A single matching outcome is evidence of functionality, not proof of all-action equivalence.
3. **Swipe**: capture one Type-B swipe and verify one tracking start, one lift, one complete gesture and actual UI movement by human observation. Returning to the same final screen does not invalidate an observed transient scroll.
4. **Trace provenance**: count complete gestures in `getevent` independently of Python wrapper action count; preserve unmodified event data, not synthetic traces.
5. **Frozen model regression**: compare causal prefixes to full captured traces only after the model and preprocessing have been packaged separately. Do not change frozen scores, weights or operating points while validating input code.

## EAD-g5 reporting

Policy: observe gestures 1–4, evaluate from gesture 5 onward in shadow mode. For tasks with 0–4 complete gestures, mark `online_eligible=false`, `prefixes_scored=0`, and store retrospective end-of-task scores separately. Do not count these as online misses or attack escapes. Track task success and agent completion independently.

## Scope and limitations

- Originally tested with one rooted-*not-required* device whose `adb shell` had `/dev/uinput` permission. Other OEM builds may block virtual-device creation.
- The fixed 1080x2400 coordinate range is an explicit limitation, not a display-independent driver.
- Virtual kernel input is not equal to human physical input.
- One-shot per-action registration introduces latency, and gesture generation includes Gaussian perturbation in swipe point sampling. The protocol may matter when studying timing-sensitive detectors.
- No API calls, detector implementations, logs, screenshots, or benchmark task data are contained in this release.
