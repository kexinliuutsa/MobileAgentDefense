# Agent action adapter

This repository intentionally does not bundle Open-AutoGLM, proprietary model APIs, or frozen detector weights. An agent framework should convert a *model-planned* action into a pixel-space, user-authorized action, and call the installed native helper.

A minimal subprocess example:

```python
import subprocess

REMOTE = '/data/local/tmp/uinput_typeb_agent_compat'

def agent_tap(x_normalized: int, y_normalized: int, adb=('adb',)):
    # Example for 0..1000 model coordinates, on a fixed 1080x2400 display.
    # Match the model framework's exact rounding and screen-orientation rules.
    x = max(0, min(1079, int(x_normalized * 1080 / 1000)))
    y = max(0, min(2399, int(y_normalized * 2400 / 1000)))
    return subprocess.run([*adb, 'shell', REMOTE,
                           'tap', str(x), str(y), '100', '0'],
                          check=True, capture_output=True, text=True)
```

The integration must additionally:

1. Capture and archive only permitted screenshots; never upload private screen data to a public repo.
2. Reject disallowed target regions or irreversible actions (payment, credential, delete, message send).
3. Capture observed `getevent` data during **each** action and use dynamic node discovery rather than relying on a fixed `/dev/input/event6`.
4. Validate the number of complete physical virtual-device contacts against the number of invoked Tap/Swipe wrappers, and abort on disagreement.
5. Keep frozen detector parameters unmodified, separate online causal-prefix scores from retrospective end-of-task evaluation.
6. Record task completion independently of detection. Short tasks that finish with fewer than five gestures are **not eligible** for EAD-g5 online assessment.

The tested Type-B binary is one-shot: each invocation registers a touchscreen, sends one gesture, then unregisters. A persistent native service could reduce action latency in a future version, but **is not implemented here**. Do not claim performance advantages without benchmarking that different executor.
