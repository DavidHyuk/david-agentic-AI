#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
# Purpose: register ClawGram MCP and install its independent worker/timer units.
set -euo pipefail

CLAWGRAM_INSTALL_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CLAWGRAM_AGENT_REPO="$(cd -- "$CLAWGRAM_INSTALL_SCRIPT_DIR/.." && pwd)"
CLAWGRAM_USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
CLAWGRAM_WORKER_ENV="${XDG_CONFIG_HOME:-$HOME/.config}/clawgram/worker.env"
CLAWGRAM_ENABLE_TIMER=false

if [[ "${1:-}" == "--enable-timer" ]]; then
  CLAWGRAM_ENABLE_TIMER=true
elif [[ -n "${1:-}" ]]; then
  echo "Usage: $0 [--enable-timer]" >&2
  exit 2
fi

python3 "$CLAWGRAM_AGENT_REPO/bootstrap/stage.py"
python3 "$CLAWGRAM_AGENT_REPO/mcp/setup_clawgram.py" --no-restart
mkdir -p "$CLAWGRAM_USER_UNIT_DIR"
install -m 0644 \
  "$CLAWGRAM_INSTALL_SCRIPT_DIR/clawgram-family-letter.service" \
  "$CLAWGRAM_USER_UNIT_DIR/clawgram-family-letter.service"
install -m 0644 \
  "$CLAWGRAM_INSTALL_SCRIPT_DIR/clawgram-family-letter.timer" \
  "$CLAWGRAM_USER_UNIT_DIR/clawgram-family-letter.timer"
install -m 0644 \
  "$CLAWGRAM_INSTALL_SCRIPT_DIR/clawgram-worker.service" \
  "$CLAWGRAM_USER_UNIT_DIR/clawgram-worker.service"
systemctl --user daemon-reload

if [[ "$CLAWGRAM_ENABLE_TIMER" == true ]]; then
  if [[ ! -f "$CLAWGRAM_WORKER_ENV" ]] || \
     ! grep -Eq '^CLAWGRAM_ASSESSMENT_URL=.+$' "$CLAWGRAM_WORKER_ENV"; then
    echo "Refusing to enable: set CLAWGRAM_ASSESSMENT_URL in $CLAWGRAM_WORKER_ENV" >&2
    exit 1
  fi
  systemctl --user enable --now clawgram-family-letter.timer
else
  systemctl --user disable --now clawgram-family-letter.timer >/dev/null 2>&1 || true
  echo "Timer installed but disabled until a VLM assessment backend is selected."
fi

systemctl --user restart hermes-gateway.service
echo "ClawGram MCP and user units installed."
