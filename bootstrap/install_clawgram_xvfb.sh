#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
# Purpose: install Ubuntu's signed Xvfb package without requiring root access.
set -euo pipefail
umask 077

CLAWGRAM_XVFB_ROOT="${CLAWGRAM_XVFB_ROOT:-$HOME/.local/opt/clawgram-xvfb}"
CLAWGRAM_XVFB_BIN="$CLAWGRAM_XVFB_ROOT/usr/bin/Xvfb"

if [[ -x "$CLAWGRAM_XVFB_BIN" ]]; then
  echo "ClawGram virtual display already installed at $CLAWGRAM_XVFB_ROOT"
  exit 0
fi
if [[ -e "$CLAWGRAM_XVFB_ROOT" ]]; then
  echo "Refusing to replace incomplete path: $CLAWGRAM_XVFB_ROOT" >&2
  exit 1
fi

CLAWGRAM_XVFB_TEMP="$(mktemp -d "${TMPDIR:-/tmp}/clawgram-xvfb.XXXXXX")"
cleanup() {
  rm -rf -- "$CLAWGRAM_XVFB_TEMP"
}
trap cleanup EXIT

(
  cd "$CLAWGRAM_XVFB_TEMP"
  apt-get download xvfb
)
CLAWGRAM_XVFB_PACKAGE="$(
  find "$CLAWGRAM_XVFB_TEMP" -maxdepth 1 -type f -name 'xvfb_*.deb' \
    -print -quit
)"
if [[ -z "$CLAWGRAM_XVFB_PACKAGE" ]]; then
  echo "Ubuntu xvfb package download produced no package" >&2
  exit 1
fi

mkdir -p "$CLAWGRAM_XVFB_TEMP/root"
dpkg-deb --extract "$CLAWGRAM_XVFB_PACKAGE" "$CLAWGRAM_XVFB_TEMP/root"
if [[ ! -x "$CLAWGRAM_XVFB_TEMP/root/usr/bin/Xvfb" ]] || \
   [[ ! -x "$CLAWGRAM_XVFB_TEMP/root/usr/bin/xvfb-run" ]]; then
  echo "Downloaded xvfb package omitted its expected executables" >&2
  exit 1
fi

mkdir -p "$(dirname "$CLAWGRAM_XVFB_ROOT")"
mv "$CLAWGRAM_XVFB_TEMP/root" "$CLAWGRAM_XVFB_ROOT"
echo "Installed Ubuntu Xvfb into $CLAWGRAM_XVFB_ROOT"
