# Android GUI Agent Input Bridge (Type-B Prototype)

A minimal research toolkit for sending GUI-agent touch gestures to a **user-controlled Android phone** using a Linux `uinput` virtual touchscreen over ADB. It can record kernel `getevent` data and verify that each action produces one complete contact. It is intended as an **execution and provenance layer**, not a behavioral detector or a phone app.

**Artifact status:** This is a device-specific prototype, not a universal Android driver. Tested on one 1080 × 2400 Android 12-class Huawei device with an authorized ADB shell that can open `/dev/uinput` without root. Most stock Android devices do **not** offer that permission. The same binary should not be assumed to work on other phones. No root, private credentials, or system modifications are provided.

## Architecture

```text
GUI-agent action (tap/swipe)
         |
         v
Python CLI / agent adapter
         |
         v
ADB shell -> native Type-B uinput executor
         |                        |
         v                        v
Android UI gesture         Linux getevent stream
                                  |
                                  v
                    virtual-event-only normalized log
                                  |
                                  v
                       gesture alignment / guard API
```

**Important:** `adb shell input tap` can interact with the UI, but on the tested device it was **not observed in the kernel `getevent` stream**. This project uses a separate virtual input device that was observable in `getevent`. The generated events are *not human physical touches*.

## Prerequisites

- macOS or Linux, `adb` on PATH, USB debugging authorized for exactly one device.
- Android NDK with `aarch64-linux-android28-clang` (tested with NDK r27c on Intel macOS).
- Python 3.9+ (standard library only for the CLI; optional `pip install -e .` installs the `guiagent-touch` entry point).
- A phone where the ADB shell can write `/dev/uinput`; **do not attempt to weaken device security to get this permission**.
- Current native axis bounds: **1080 × 2400**. Other screen sizes are intentionally rejected.

## Build and deploy

```bash
bash scripts/build.sh
bash scripts/deploy.sh
python3 -m guiagent_touch doctor
```

`build.sh` auto-detects NDK versions under `ANDROID_SDK_ROOT/ndk` or reads `ANDROID_NDK_HOME`. The deployed executable is `/data/local/tmp/uinput_typeb_agent_compat`. The legacy executor (if any) is left untouched. `deploy.sh` checks the binary's local and remote SHA-256 hashes.

## One safe action

First visually open a harmless test page and check that the requested coordinates have no purchase, account-changing, or data-deleting consequences. Then explicitly authorize one action:

```bash
python3 -m guiagent_touch tap 440 204 --dwell 100 --yes
python3 -m guiagent_touch swipe 540 1550 540 850 --duration 450 --profile linear --yes
```

These commands **really interact with the phone**. They are not dry runs. The tool cannot determine whether a target is safe.

## Record one provenance-checked gesture

```bash
python3 -m guiagent_touch probe-tap 440 204 --dwell 100 --yes --out runs
python3 -m guiagent_touch probe-swipe 540 1550 540 850 --duration 450 --yes --out runs
```

Each command starts `getevent -lt`, executes exactly one user-authorized action, and saves:

- `virtual_events_normalized.log`: **observed** Type-B virtual-touchscreen events only. No invented samples.
- `summary.json`: dynamic event nodes; tracking starts/ends; complete gestures; alignment status; event-log hash; input provenance.

The potentially sensitive all-device `getevent` output is held in a temporary file and deleted; only virtual-device events are preserved. `runs/` is gitignored.

Optional packaging: from this directory run `python3 -m pip install -e .`, then use `guiagent-touch doctor` instead of `python3 -m guiagent_touch doctor`.

## Agent integration

`docs/ADAPTER_INTERFACE.md` describes mapping agent coordinates to display pixels and calling this executable. This module provides the **execution/provenance layer only**. Other directories in this repository contain available defense-source references; the frozen online model and author classifier model assets must be supplied from the original local project for full reproduction. See the root README.

## Reproducibility scope

On the initial device, isolated tests demonstrated: (1) Type-B and ordinary ADB tapping the same music-search target both opened search, (2) a Type-B swipe produced one complete kernel gesture and visually triggered scrolling, and (3) a six-tap Type-B trace preserved gesture alignment in an existing frozen detector. These are **single-device, small-scale functional checks**, not statistical estimates of security performance. See `docs/EXPERIMENT_PROTOCOL.md`.

Run parser tests:

```bash
python3 -m unittest discover -s tests -v
```

## Licensing

No license is asserted in this initial preparation package. Before publishing, confirm ownership and third-party source provenance and select a license compatible with all components. Public visibility alone is not an open-source license.
