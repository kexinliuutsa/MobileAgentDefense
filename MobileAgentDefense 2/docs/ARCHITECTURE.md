# Implementation boundaries

```text
GUI-agent planner / executor
          |
          v
Android Type-B input bridge  <--- typeb_input/guiagent_touch + native/
          |
          v
kernel getevent (virtual device) -> normalized events -> gesture aggregation
          |
          v
frozen online V3 features -> frozen native head(s) -> online decision
          |
          +-----------------------> author comparison through native
                                      UltimateClassifier.predict()
```

- `typeb_input/native/uinput_typeb_agent_compat.c`: Linux `/dev/uinput` Type-B virtual contact implementation.
- `typeb_input/guiagent_touch/__main__.py`: ADB controller, tap/swipe/probe CLI.
- `typeb_input/guiagent_touch/events.py`: event filtering, gesture boundaries and alignment.
- `typeb_input/scripts/build.sh` and `deploy.sh`: Android NDK build/device deploy.
- `typeb_input/tests/test_events.py`: parser unit tests.
- `our_defense/offline_v3_source`: offline V3 source, not the pretrained deployed model.
- `author_defense/analysis/processing/judge_library.py`: native author predictor.
- `author_defense/repair/official_predict_patch.py`: native helper correction.

Risk and accuracy thresholds used in comparisons should remain **frozen at their native operating points**. Never implement FPR matching or a reconstructed substitute decision rule and label it as the official baseline.
