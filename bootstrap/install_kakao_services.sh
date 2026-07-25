#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
#
# Install the Kakao feedback webhook plus a Cloudflare Quick Tunnel as user
# services without staging unrelated dirty worktree files.
set -euo pipefail

KAKAO_ROTATE_PATH=false
if [ "${1:-}" = "--rotate-path" ]; then
  KAKAO_ROTATE_PATH=true
elif [ "$#" -gt 0 ]; then
  echo "Usage: $0 [--rotate-path]" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KAKAO_HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
KAKAO_USER_BIN="$HOME/.local/bin"
KAKAO_USER_UNITS="$HOME/.config/systemd/user"
KAKAO_ENV_FILE="$KAKAO_HERMES_HOME/.env"

mkdir -p "$KAKAO_HERMES_HOME/scripts" \
  "$KAKAO_HERMES_HOME/skills/learning/english-practice" \
  "$KAKAO_USER_BIN" "$KAKAO_USER_UNITS"
install -d -m 0700 \
  "$KAKAO_HERMES_HOME/data/english" \
  "$HOME/english-lessons"

install -m 0755 "$REPO_ROOT/scripts/kakao_webhook.py" \
  "$KAKAO_HERMES_HOME/scripts/kakao_webhook.py"
install -m 0755 "$REPO_ROOT/scripts/english_intake.py" \
  "$KAKAO_HERMES_HOME/scripts/english_intake.py"
install -m 0755 "$REPO_ROOT/scripts/english_srs.py" \
  "$KAKAO_HERMES_HOME/scripts/english_srs.py"
install -m 0644 "$REPO_ROOT/skills/learning/english-practice/SKILL.md" \
  "$KAKAO_HERMES_HOME/skills/learning/english-practice/SKILL.md"

touch "$KAKAO_ENV_FILE"
chmod 600 "$KAKAO_ENV_FILE"
if ! grep -q '^KAKAO_WEBHOOK_PATH=' "$KAKAO_ENV_FILE"; then
  KAKAO_SECRET_PATH="$(
    python3 "$KAKAO_HERMES_HOME/scripts/kakao_webhook.py" --generate-path
  )"
  printf '\nKAKAO_WEBHOOK_PATH=%s\n' "$KAKAO_SECRET_PATH" >> "$KAKAO_ENV_FILE"
fi
if ! grep -q '^KAKAO_WEBHOOK_PORT=' "$KAKAO_ENV_FILE"; then
  printf 'KAKAO_WEBHOOK_PORT=8787\n' >> "$KAKAO_ENV_FILE"
fi
if "$KAKAO_ROTATE_PATH"; then
  python3 "$KAKAO_HERMES_HOME/scripts/kakao_webhook.py" \
    --rotate-path --env-file "$KAKAO_ENV_FILE"
fi

if ! command -v cloudflared >/dev/null 2>&1 && \
   [ ! -x "$KAKAO_USER_BIN/cloudflared" ]; then
  case "$(uname -m)" in
    x86_64) KAKAO_CLOUDFLARED_ARCH="amd64" ;;
    aarch64|arm64) KAKAO_CLOUDFLARED_ARCH="arm64" ;;
    *)
      echo "Unsupported architecture for cloudflared: $(uname -m)" >&2
      exit 1
      ;;
  esac
  KAKAO_DOWNLOAD_PATH="$(mktemp)"
  trap 'rm -f "$KAKAO_DOWNLOAD_PATH"' EXIT
  curl --fail --location --retry 3 \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${KAKAO_CLOUDFLARED_ARCH}" \
    --output "$KAKAO_DOWNLOAD_PATH"
  install -m 0755 "$KAKAO_DOWNLOAD_PATH" "$KAKAO_USER_BIN/cloudflared"
fi

install -m 0644 "$REPO_ROOT/bootstrap/kakao-webhook.service" \
  "$KAKAO_USER_UNITS/kakao-webhook.service"
install -m 0644 "$REPO_ROOT/bootstrap/kakao-tunnel.service" \
  "$KAKAO_USER_UNITS/kakao-tunnel.service"

systemctl --user daemon-reload
systemctl --user enable --now kakao-webhook.service kakao-tunnel.service
systemctl --user restart kakao-webhook.service
if [ "$(systemctl --user is-active kakao-tunnel.service)" != "active" ]; then
  systemctl --user restart kakao-tunnel.service
fi

KAKAO_TUNNEL_ORIGIN=""
for _attempt in $(seq 1 30); do
  KAKAO_TUNNEL_PID="$(
    systemctl --user show kakao-tunnel.service --property MainPID --value
  )"
  KAKAO_TUNNEL_LOGS=""
  if [ -n "$KAKAO_TUNNEL_PID" ] && [ "$KAKAO_TUNNEL_PID" != "0" ]; then
    KAKAO_TUNNEL_LOGS="$(
      journalctl --user "_PID=$KAKAO_TUNNEL_PID" --no-pager 2>/dev/null || true
    )"
  fi
  KAKAO_TUNNEL_ORIGIN="$(
    printf '%s\n' "$KAKAO_TUNNEL_LOGS" |
      grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' |
      tail -n 1 || true
  )"
  if [ -n "$KAKAO_TUNNEL_ORIGIN" ] && \
     printf '%s\n' "$KAKAO_TUNNEL_LOGS" |
       grep -q 'Registered tunnel connection'; then
    break
  fi
  sleep 1
done

if [ -n "$KAKAO_TUNNEL_ORIGIN" ]; then
  KAKAO_SECRET_PATH="$(
    sed -n 's/^KAKAO_WEBHOOK_PATH=//p' "$KAKAO_ENV_FILE" | tail -n 1
  )"
  KAKAO_SKILL_URL_FILE="$KAKAO_HERMES_HOME/data/english/kakao-skill-url.txt"
  printf '%s%s\n' "$KAKAO_TUNNEL_ORIGIN" "$KAKAO_SECRET_PATH" \
    > "$KAKAO_SKILL_URL_FILE"
  chmod 600 "$KAKAO_SKILL_URL_FILE"
else
  echo "Tunnel started but its public origin was not found in 30 seconds." >&2
  exit 1
fi

echo "Kakao webhook and temporary HTTPS tunnel services are running."
echo "The private Open Builder skill URL was refreshed at:"
echo "  $KAKAO_HERMES_HOME/data/english/kakao-skill-url.txt"
