#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
# Purpose: install the Hermes cron watchdog and bounded gateway recovery policy.
set -euo pipefail

WATCHDOG_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WATCHDOG_REPO_ROOT="$(cd -- "$WATCHDOG_SCRIPT_DIR/.." && pwd)"
WATCHDOG_HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
WATCHDOG_USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
WATCHDOG_GATEWAY_DROPIN_DIR="$WATCHDOG_USER_UNIT_DIR/hermes-gateway.service.d"

python3 "$WATCHDOG_REPO_ROOT/bootstrap/stage.py" \
  --home "$WATCHDOG_HERMES_HOME"

mkdir -p "$WATCHDOG_USER_UNIT_DIR" "$WATCHDOG_GATEWAY_DROPIN_DIR"
install -m 0644 \
  "$WATCHDOG_SCRIPT_DIR/hermes-cron-watchdog.service" \
  "$WATCHDOG_USER_UNIT_DIR/hermes-cron-watchdog.service"
install -m 0644 \
  "$WATCHDOG_SCRIPT_DIR/hermes-cron-watchdog.timer" \
  "$WATCHDOG_USER_UNIT_DIR/hermes-cron-watchdog.timer"
install -m 0644 \
  "$WATCHDOG_SCRIPT_DIR/hermes-gateway-cron-recovery.conf" \
  "$WATCHDOG_GATEWAY_DROPIN_DIR/30-cron-recovery.conf"

systemctl --user daemon-reload
systemctl --user enable --now hermes-cron-watchdog.timer
systemctl --user start hermes-cron-watchdog.service

echo "Hermes cron watchdog installed."
systemctl --user --no-pager status hermes-cron-watchdog.timer
