#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
# Purpose: install the isolated ClawGram Hermes profile, source, and worker units.
set -euo pipefail

CLAWGRAM_INSTALL_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CLAWGRAM_AGENT_REPO="$(cd -- "$CLAWGRAM_INSTALL_SCRIPT_DIR/.." && pwd)"
CLAWGRAM_USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
CLAWGRAM_WORKER_ENV="${XDG_CONFIG_HOME:-$HOME/.config}/clawgram/worker.env"
CLAWGRAM_PROFILE_HOME="$HOME/.hermes/profiles/clawgram"
CLAWGRAM_PROFILE_ENV="$CLAWGRAM_PROFILE_HOME/.env"
CLAWGRAM_ENABLE_TIMER=false

if [[ "${1:-}" == "--enable-timer" ]]; then
  CLAWGRAM_ENABLE_TIMER=true
elif [[ -n "${1:-}" ]]; then
  echo "Usage: $0 [--enable-timer]" >&2
  exit 2
fi

if ! hermes profile show clawgram >/dev/null 2>&1; then
  hermes profile create clawgram --no-skills \
    --description "Private child-focused family-letter agent with explicit review authority boundaries."
fi

python3 "$CLAWGRAM_INSTALL_SCRIPT_DIR/stage_clawgram_profile.py" --cleanup-default
python3 "$CLAWGRAM_AGENT_REPO/mcp/setup_clawgram.py" \
  --home "$CLAWGRAM_PROFILE_HOME" --no-restart
python3 "$CLAWGRAM_AGENT_REPO/mcp/setup_clawgram.py" \
  --home "$HOME/.hermes" --remove --no-restart
bash "$CLAWGRAM_INSTALL_SCRIPT_DIR/install_clawgram_xvfb.sh"

mkdir -p "$CLAWGRAM_USER_UNIT_DIR"
for unit in \
  clawgram-family-letter.service \
  clawgram-family-letter.timer \
  clawgram-source.service \
  clawgram-worker.service \
  clawgram-assessment.service \
  clawgram-review.service \
  clawgram-google-photos-browser.service; do
  install -m 0644 \
    "$CLAWGRAM_INSTALL_SCRIPT_DIR/$unit" \
    "$CLAWGRAM_USER_UNIT_DIR/$unit"
done
systemctl --user daemon-reload
systemctl --user enable --now \
  clawgram-google-photos-browser.service \
  clawgram-assessment.service \
  clawgram-review.service

if [[ -f "$CLAWGRAM_PROFILE_ENV" ]] && \
   grep -Eq '^TELEGRAM_BOT_TOKEN=.+$' "$CLAWGRAM_PROFILE_ENV"; then
  # Hermes currently has no non-interactive install flag. Answer its two
  # fixed Linux prompts: start now, and enable the user service at login.
  printf 'y\ny\n' | hermes -p clawgram gateway install --force
  mkdir -p "$CLAWGRAM_USER_UNIT_DIR/hermes-gateway-clawgram.service.d"
  install -m 0644 \
    "$CLAWGRAM_INSTALL_SCRIPT_DIR/hermes-gateway-clawgram-vllm.conf" \
    "$CLAWGRAM_USER_UNIT_DIR/hermes-gateway-clawgram.service.d/20-vllm-readiness.conf"
  systemctl --user daemon-reload
  systemctl --user restart hermes-gateway-clawgram.service
else
  echo "ClawGram Telegram token is not configured yet. Run: hermes -p clawgram gateway setup"
fi

if [[ "$CLAWGRAM_ENABLE_TIMER" == true ]]; then
  if [[ ! -f "$CLAWGRAM_WORKER_ENV" ]] || \
     ! grep -Eq '^CLAWGRAM_ASSESSMENT_URL=.+$' "$CLAWGRAM_WORKER_ENV"; then
    echo "Refusing to enable: set CLAWGRAM_ASSESSMENT_URL in $CLAWGRAM_WORKER_ENV" >&2
    exit 1
  fi
  if ! grep -Eq '^CLAWGRAM_REVIEW_BASE_URL=https://.+$' "$CLAWGRAM_WORKER_ENV"; then
    echo "Refusing to enable: set an HTTPS CLAWGRAM_REVIEW_BASE_URL in $CLAWGRAM_WORKER_ENV" >&2
    exit 1
  fi
  if [[ ! -f "$CLAWGRAM_PROFILE_ENV" ]] || \
     ! grep -Eq '^TELEGRAM_BOT_TOKEN=.+$' "$CLAWGRAM_PROFILE_ENV"; then
    echo "Refusing to enable: configure the dedicated ClawGram Telegram bot first" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$CLAWGRAM_WORKER_ENV"
  set +a
  (
    cd /home/david/workspace/ClawGram
    /home/david/miniconda3/envs/clawgram/bin/python \
      -m clawgram.collect_sources --check-auth
  )
  systemctl --user enable --now clawgram-family-letter.timer
else
  systemctl --user disable --now clawgram-family-letter.timer >/dev/null 2>&1 || true
  echo "Timer installed but disabled until Telegram, Google login, and HTTPS review are ready."
fi

systemctl --user restart hermes-gateway.service
echo "Isolated ClawGram profile, MCP, and user units installed."
