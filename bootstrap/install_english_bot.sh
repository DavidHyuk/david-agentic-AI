#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
# Purpose: install the dedicated English Hermes profile and its Telegram gateway.
set -euo pipefail

ENGLISH_INSTALL_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENGLISH_PROFILE_HOME="$HOME/.hermes/profiles/english"
ENGLISH_PROFILE_ENV="$ENGLISH_PROFILE_HOME/.env"
ENGLISH_USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if ! hermes profile show english >/dev/null 2>&1; then
  hermes profile create english --no-skills \
    --description "English tutor-feedback analysis and SRS coaching, delivered through its own Telegram bot."
fi

# Refresh the root configuration too, then remove its former English skill so
# incoming messages to the main bot cannot invoke the English workflow.
python3 "$ENGLISH_INSTALL_SCRIPT_DIR/stage.py"
python3 "$ENGLISH_INSTALL_SCRIPT_DIR/stage_english_profile.py" --cleanup-default

if [[ -f "$ENGLISH_PROFILE_ENV" ]] && grep -Eq '^TELEGRAM_BOT_TOKEN=.+$' "$ENGLISH_PROFILE_ENV"; then
  # Hermes currently asks two fixed Linux questions: start now and enable at login.
  printf 'y\ny\n' | hermes -p english gateway install --force
  mkdir -p "$ENGLISH_USER_UNIT_DIR/hermes-gateway-english.service.d"
  install -m 0644 \
    "$ENGLISH_INSTALL_SCRIPT_DIR/hermes-gateway-english-vllm.conf" \
    "$ENGLISH_USER_UNIT_DIR/hermes-gateway-english.service.d/20-vllm-readiness.conf"
  systemctl --user daemon-reload
  systemctl --user restart hermes-gateway-english.service
else
  echo "Configure the dedicated bot first: hermes -p english gateway setup"
fi

# Recreates same-named jobs, removing their prior root-profile versions.
python3 "$ENGLISH_INSTALL_SCRIPT_DIR/register_cron.py"
echo "English Telegram profile is staged; its cron jobs target profile=english."
