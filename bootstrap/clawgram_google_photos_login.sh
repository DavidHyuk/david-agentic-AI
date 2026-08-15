#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
# Purpose: prepare remote DevTools login for ClawGram's headed private browser.
set -euo pipefail
umask 077

CLAWGRAM_LOGIN_SERVICE="clawgram-google-photos-browser.service"
CLAWGRAM_LOGIN_PYTHON="/home/david/miniconda3/envs/clawgram/bin/python"
CLAWGRAM_LOGIN_REPO="/home/david/workspace/ClawGram"
CLAWGRAM_LOGIN_BROWSER="$HOME/.hermes/node_modules/.bin/agent-browser"
CLAWGRAM_LOGIN_CDP="http://127.0.0.1:19223"
CLAWGRAM_LOGIN_URL="https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fphotos.google.com%2F"

if [[ -n "${1:-}" && "${1:-}" != "--check" ]]; then
  echo "Usage: $0 [--check]" >&2
  exit 2
fi

cd "$CLAWGRAM_LOGIN_REPO"
if [[ "${1:-}" == "--check" ]]; then
  exec "$CLAWGRAM_LOGIN_PYTHON" -m clawgram.collect_sources --check-auth
fi
if "$CLAWGRAM_LOGIN_PYTHON" -m clawgram.collect_sources --check-auth \
  >/dev/null 2>&1; then
  echo "ClawGram Google Photos session is already authenticated."
  exit 0
fi

systemctl --user start "$CLAWGRAM_LOGIN_SERVICE"
for _ in {1..50}; do
  if curl --fail --silent "$CLAWGRAM_LOGIN_CDP/json/version" >/dev/null; then
    break
  fi
  sleep 0.2
done
if ! curl --fail --silent "$CLAWGRAM_LOGIN_CDP/json/version" >/dev/null; then
  echo "ClawGram Chromium CDP did not become ready" >&2
  exit 1
fi
if ! "$CLAWGRAM_LOGIN_BROWSER" \
  --cdp "$CLAWGRAM_LOGIN_CDP" \
  --session clawgram-google-photos \
  --json open "$CLAWGRAM_LOGIN_URL" >/dev/null; then
  echo "Could not navigate the dedicated browser to Google login" >&2
  exit 1
fi

cat <<'STEPS'
Google login is ready in the headed virtual Chromium.
1. Keep an SSH local forward open: 19223 -> 127.0.0.1:19223 on the DGX.
2. Open chrome://inspect/#devices in local Chrome.
3. Configure localhost:19223, click inspect, and enable Toggle screencast.
4. Complete Google login/2FA, then leave the tab at https://photos.google.com/.
5. Verify on the DGX:
   bash /home/david/workspace/David-Agent/bootstrap/clawgram_google_photos_login.sh --check
STEPS
