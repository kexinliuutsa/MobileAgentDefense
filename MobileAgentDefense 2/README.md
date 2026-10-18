# MobileAgentDefense — research code organization

Android GUI-agent touch provenance, defense source, author baseline source, and reproducibility scaffolding.

**IMPORTANT: THIS ZIP IS A SOURCE STAGING BUNDLE — NOT A COMPLETE FROZEN DEFENSE RELEASE.** The available files have been reconstructed from earlier user-provided source archives. The true frozen online V3 deployment files and some `.joblib` / original author `.pkl` assets remain on the user's Mac. For a complete, reviewed release, run `bash scripts/make_full_release_mac.sh` from the extracted directory. Do not upload this staging bundle as if all models were present.

## Layout

- `typeb_input/` — complete original Android Type-B implementation (all code and parser tests), excluding unrelated submission-administration documents.
- `our_defense/offline_v3_source/` — available algorithm source, no frozen weights.
- `our_defense/runtime_reference/` — early runtime adapter/source reference, not the frozen online classifier.
- `author_defense/` — original author `UltimateClassifier.predict()` source and audited helper correction, some dependencies still missing.
- `docs/` — execution pipeline and paired evaluation boundary.
- `.github/workflows/ci.yml` — tests for the Type-B code in a Linux runner (no Mac Docker needed).
- `scripts/make_full_release_mac.sh` — fills missing original sources and model assets from your Mac without retraining, then creates a new ZIP.

## Verify the available Type-B implementation

```bash
cd typeb_input
python3 -m unittest discover -s tests -v
# On Linux only:
gcc -std=gnu11 -Wall -Wextra -Werror -fsyntax-only native/uinput_typeb_agent_compat.c
```

## Publication checklist

Review source and model licenses, Python pickle provenance, repo history, credentials, user/participant records, absolute home paths, and artifact dependencies. Third-party model files are **not** automatically redistributable. The local completion script reports missing required files and refuses to produce a falsely complete archive.

To upload from GitHub's web interface: **unzip the final ZIP and upload the folders/files inside**, not the ZIP itself. GitHub does not automatically expand uploaded ZIP archives.
