#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
#
# Install the Kakao feedback webhook plus a Cloudflare Quick Tunnel as user
# services without staging unrelated dirty worktree files.
set -euo pipefail

KAKAO_ROTATE_PATH=false
KAKAO_PUBLIC_ORIGIN=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --rotate-path) KAKAO_ROTATE_PATH=true; shift ;;
    --public-origin)
      if [ "$#" -lt 2 ]; then
        echo "--public-origin requires an HTTPS origin." >&2
        exit 2
      fi
      KAKAO_PUBLIC_ORIGIN="$2"
      shift 2
      ;;
    *) echo "Usage: $0 [--rotate-path] [--public-origin https://hostname[:port]]" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KAKAO_HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
KAKAO_USER_BIN="$HOME/.local/bin"
KAKAO_USER_UNITS="$HOME/.config/systemd/user"
KAKAO_ENV_FILE="$KAKAO_HERMES_HOME/.env"

mkdir -p "$KAKAO_HERMES_HOME/scripts" \
  "$KAKAO_HERMES_HOME/profiles/english/skills/learning/english-practice" \
  "$KAKAO_USER_BIN" "$KAKAO_USER_UNITS"
install -d -m 0700 \
  "$KAKAO_HERMES_HOME/data/english" \
  "$HOME/english-lessons"

install -m 0755 "$REPO_ROOT/scripts/kakao_webhook.py" \
  "$KAKAO_HERMES_HOME/scripts/kakao_webhook.py"
install -m 0755 "$REPO_ROOT/scripts/kakao_tunnel_url.py" \
  "$KAKAO_HERMES_HOME/scripts/kakao_tunnel_url.py"
install -m 0755 "$REPO_ROOT/scripts/english_intake.py" \
  "$KAKAO_HERMES_HOME/scripts/english_intake.py"
install -m 0755 "$REPO_ROOT/scripts/english_srs.py" \
  "$KAKAO_HERMES_HOME/scripts/english_srs.py"
install -m 0644 "$REPO_ROOT/profiles/english/skills/learning/english-practice/SKILL.md" \
  "$KAKAO_HERMES_HOME/profiles/english/skills/learning/english-practice/SKILL.md"

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

KAKAO_ORIGIN_FILE="$KAKAO_HERMES_HOME/data/english/kakao-public-origin.txt"
if [ -z "$KAKAO_PUBLIC_ORIGIN" ] && [ -f "$KAKAO_ORIGIN_FILE" ]; then
  KAKAO_PUBLIC_ORIGIN="$(cat "$KAKAO_ORIGIN_FILE")"
fi

if [ -z "$KAKAO_PUBLIC_ORIGIN" ] && ! command -v cloudflared >/dev/null 2>&1 && \
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
systemctl --user enable --now kakao-webhook.service
systemctl --user restart kakao-webhook.service
if [ -n "$KAKAO_PUBLIC_ORIGIN" ]; then
  python3 "$KAKAO_HERMES_HOME/scripts/kakao_tunnel_url.py" \
    --home "$KAKAO_HERMES_HOME" --origin "$KAKAO_PUBLIC_ORIGIN"
  systemctl --user disable --now kakao-tunnel.service
  echo "Kakao webhook is running through the verified fixed HTTPS origin."
else
  systemctl --user enable --now kakao-tunnel.service
  python3 "$KAKAO_HERMES_HOME/scripts/kakao_tunnel_url.py" --home "$KAKAO_HERMES_HOME"
  echo "Kakao webhook and temporary HTTPS tunnel services are running."
fi
echo "The private Open Builder skill URL was refreshed at:"
echo "  $KAKAO_HERMES_HOME/data/english/kakao-skill-url.txt"
