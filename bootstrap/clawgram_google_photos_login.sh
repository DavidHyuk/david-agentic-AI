#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
# Purpose: perform the one interactive Google login in ClawGram's private profile.
set -euo pipefail
umask 077

CLAWGRAM_LOGIN_PROFILE="$HOME/snap/chromium/common/clawgram-google-photos-profile"
CLAWGRAM_LOGIN_SERVICE="clawgram-google-photos-browser.service"
CLAWGRAM_LOGIN_PYTHON="/home/david/miniconda3/envs/clawgram/bin/python"
CLAWGRAM_LOGIN_REPO="/home/david/workspace/ClawGram"

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  echo "A graphical desktop session is required for Google login and 2FA." >&2
  exit 1
fi

mkdir -p "$CLAWGRAM_LOGIN_PROFILE"
systemctl --user stop "$CLAWGRAM_LOGIN_SERVICE"
restart_browser() {
  systemctl --user start "$CLAWGRAM_LOGIN_SERVICE" >/dev/null 2>&1 || true
}
trap restart_browser EXIT

echo "Sign in to Google Photos, complete any 2FA, then close this Chromium window."
/snap/bin/chromium \
  --no-first-run \
  --no-default-browser-check \
  --user-data-dir="$CLAWGRAM_LOGIN_PROFILE" \
  https://photos.google.com/

restart_browser
trap - EXIT
sleep 2
cd "$CLAWGRAM_LOGIN_REPO"
exec "$CLAWGRAM_LOGIN_PYTHON" -m clawgram.collect_sources --check-auth
