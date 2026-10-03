#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
# Purpose: provision an explicit Python runtime for SSH and cron YouTube reads.
set -euo pipefail
umask 077

YOUTUBE_HISTORY_RUNTIME_DIR="${YOUTUBE_HISTORY_RUNTIME_DIR:-$HOME/.hermes/venvs/youtube-history}"
YOUTUBE_HISTORY_RUNTIME_PYTHON="$YOUTUBE_HISTORY_RUNTIME_DIR/bin/python"
YOUTUBE_HISTORY_UV="$(command -v uv || true)"
if [[ -z "$YOUTUBE_HISTORY_UV" && -x "$HOME/.local/bin/uv" ]]; then
  YOUTUBE_HISTORY_UV="$HOME/.local/bin/uv"
fi

if [[ ! -x "$YOUTUBE_HISTORY_RUNTIME_PYTHON" ]]; then
  if [[ -n "$YOUTUBE_HISTORY_UV" ]]; then
    "$YOUTUBE_HISTORY_UV" venv --python /usr/bin/python3 "$YOUTUBE_HISTORY_RUNTIME_DIR"
  else
    /usr/bin/python3 -m venv "$YOUTUBE_HISTORY_RUNTIME_DIR"
  fi
fi

if [[ -n "$YOUTUBE_HISTORY_UV" ]]; then
  "$YOUTUBE_HISTORY_UV" pip install --python "$YOUTUBE_HISTORY_RUNTIME_PYTHON" 'playwright>=1.55,<2' 'yt-dlp>=2025.8.22'
else
  "$YOUTUBE_HISTORY_RUNTIME_PYTHON" -m pip install 'playwright>=1.55,<2' 'yt-dlp>=2025.8.22'
fi

# Install a matching headless browser in a stable path, even when Hermes changes HOME.
PLAYWRIGHT_BROWSERS_PATH="$YOUTUBE_HISTORY_RUNTIME_DIR/browsers" \
  "$YOUTUBE_HISTORY_RUNTIME_PYTHON" -m playwright install chromium --only-shell --no-remove
"$YOUTUBE_HISTORY_RUNTIME_PYTHON" -c 'from playwright.sync_api import sync_playwright; print("YouTube history Python and browser runtime ready.")'
