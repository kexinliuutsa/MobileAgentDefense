#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT/build/uinput_typeb_agent_compat"
REMOTE="/data/local/tmp/uinput_typeb_agent_compat"
if [[ ! -f "$BIN" ]]; then echo "Run scripts/build.sh first" >&2; exit 2; fi
if ! command -v adb >/dev/null; then echo 'adb not installed or not in PATH' >&2; exit 2; fi
SERIALS="$(adb devices | awk 'NR>1 && $2=="device" {print $1}')"
N="$(printf '%s\n' "$SERIALS" | grep -c . || true)"
if [[ "$N" != 1 ]]; then echo "Require exactly one authorized ADB device; found $N" >&2; exit 2; fi
SERIAL="$SERIALS"
adb -s "$SERIAL" push "$BIN" "$REMOTE"
adb -s "$SERIAL" shell chmod 755 "$REMOTE"
if command -v shasum >/dev/null; then
  LOCAL_SHA="$(shasum -a 256 "$BIN" | awk '{print $1}')"
else
  LOCAL_SHA="$(sha256sum "$BIN" | awk '{print $1}')"
fi
REMOTE_SHA="$(adb -s "$SERIAL" shell sha256sum "$REMOTE" | awk '{print $1}')"
if [[ "$LOCAL_SHA" != "$REMOTE_SHA" ]]; then echo 'HASH MISMATCH: deployment invalid' >&2; exit 3; fi
printf 'DEPLOY PASS: %s\nSHA256: %s\nOriginal uinput_tap_probe untouched\n' "$REMOTE" "$LOCAL_SHA"
