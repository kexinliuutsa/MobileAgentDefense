#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}"
NDK="${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-}}"
if [[ -z "$NDK" ]]; then
  if [[ ! -d "$SDK/ndk" ]]; then echo "NDK missing: $SDK/ndk" >&2; exit 2; fi
  NDK="$(find "$SDK/ndk" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -n 1)"
fi
if [[ ! -d "$NDK" ]]; then echo "NDK not found: $NDK" >&2; exit 2; fi
CLANG=""
for PLATFORM in darwin-x86_64 darwin-arm64 linux-x86_64; do
  MAYBE="$NDK/toolchains/llvm/prebuilt/$PLATFORM/bin/aarch64-linux-android28-clang"
  if [[ -x "$MAYBE" ]]; then CLANG="$MAYBE"; break; fi
done
if [[ -z "$CLANG" ]]; then echo "Android ARM64 NDK clang unavailable under $NDK" >&2; exit 2; fi
mkdir -p "$ROOT/build"
OUT="$ROOT/build/uinput_typeb_agent_compat"
"$CLANG" -std=gnu11 -O2 -Wall -Wextra -Werror \
  -o "$OUT" "$ROOT/native/uinput_typeb_agent_compat.c" -lm
printf 'BUILD PASS: %s\n' "$OUT"
