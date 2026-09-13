#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
# Purpose: install the English podcast profile, transcript timer, and Telegram gateway.
set -euo pipefail

PODCAST_INSTALL_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PODCAST_REPO_ROOT="$(cd -- "$PODCAST_INSTALL_SCRIPT_DIR/.." && pwd)"
PODCAST_PROFILE_HOME="$HOME/.hermes/profiles/english-podcast"
PODCAST_PROFILE_ENV="$PODCAST_PROFILE_HOME/.env"
PODCAST_USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if command -v uv >/dev/null 2>&1; then
  uv tool install --upgrade 'yt-dlp>=2025.8.22'
else
  python3 -m pip install --quiet --user 'yt-dlp>=2025.8.22'
fi

if ! hermes profile show english-podcast >/dev/null 2>&1; then
  hermes profile create english-podcast --no-skills \
    --description "Daily transcript-grounded English Goal Podcast coaching through its own Telegram bot."
fi

python3 "$PODCAST_INSTALL_SCRIPT_DIR/stage_english_podcast_profile.py"

mkdir -p "$PODCAST_USER_UNIT_DIR"
install -m 0644 \
  "$PODCAST_INSTALL_SCRIPT_DIR/hermes-english-podcast-sync.service" \
  "$PODCAST_USER_UNIT_DIR/hermes-english-podcast-sync.service"
install -m 0644 \
  "$PODCAST_INSTALL_SCRIPT_DIR/hermes-english-podcast-sync.timer" \
  "$PODCAST_USER_UNIT_DIR/hermes-english-podcast-sync.timer"
systemctl --user daemon-reload
systemctl --user enable --now hermes-english-podcast-sync.timer
if ! systemctl --user start hermes-english-podcast-sync.service; then
  echo "Initial transcript download failed; the 09:00 job will retry preparation."
  echo "Inspect with: journalctl --user -u hermes-english-podcast-sync.service -n 50"
fi

if [[ -f "$PODCAST_PROFILE_ENV" ]] && grep -Eq '^TELEGRAM_BOT_TOKEN=.+$' "$PODCAST_PROFILE_ENV"; then
  printf 'y\ny\n' | hermes -p english-podcast gateway install --force
  mkdir -p "$PODCAST_USER_UNIT_DIR/hermes-gateway-english-podcast.service.d"
  install -m 0644 \
    "$PODCAST_INSTALL_SCRIPT_DIR/hermes-gateway-english-podcast-vllm.conf" \
    "$PODCAST_USER_UNIT_DIR/hermes-gateway-english-podcast.service.d/20-vllm-readiness.conf"
  systemctl --user daemon-reload
  systemctl --user restart hermes-gateway-english-podcast.service
else
  echo "Configure the dedicated bot first: hermes -p english-podcast gateway setup"
fi

python3 "$PODCAST_INSTALL_SCRIPT_DIR/register_cron.py" --name english-podcast-daily
echo "English podcast profile is staged; transcript sync is 08:30 and coaching is 09:00."
