#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
#
# Install the pinned agent-browser CLI and the local Chromium CDP user service
# used by Hermes Built-in Browser. Safe to re-run; --check is read-only.
set -euo pipefail

AGENT_BROWSER_VERSION="0.33.0"
CDP_URL="http://127.0.0.1:19222"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
AGENT_BROWSER_BIN="$HERMES_HOME/node_modules/.bin/agent-browser"
UNIT_SOURCE="$REPO_ROOT/browser/hermes-browser.service"
UNIT_TARGET="$HOME/.config/systemd/user/hermes-browser.service"

say() { printf '%s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

installed_version() {
  [ -x "$AGENT_BROWSER_BIN" ] || return 1
  "$AGENT_BROWSER_BIN" --version 2>/dev/null | awk '{print $2}'
}

check_cdp() {
  curl --fail --silent --show-error --max-time 3 "$CDP_URL/json/version"
}

check_all() {
  local current
  current="$(installed_version || true)"
  [ "$current" = "$AGENT_BROWSER_VERSION" ] || \
    fail "agent-browser $AGENT_BROWSER_VERSION required; found ${current:-nothing}"
  systemctl --user is-active --quiet hermes-browser.service || \
    fail "hermes-browser.service is not active"
  check_cdp >/dev/null || fail "Chromium CDP is not reachable at $CDP_URL"
  say "agent-browser $current: ok"
  say "hermes-browser.service: active"
  say "Chromium CDP $CDP_URL: ready"
}

if [ "${1:-}" = "--check" ]; then
  check_all
  exit 0
fi
[ "$#" -eq 0 ] || fail "usage: $0 [--check]"

command -v npm >/dev/null 2>&1 || fail "npm is required"
command -v curl >/dev/null 2>&1 || fail "curl is required"
command -v systemctl >/dev/null 2>&1 || fail "systemctl is required"
[ -x /snap/bin/chromium ] || fail "/snap/bin/chromium is required on this DGX Spark"

say "Installing agent-browser $AGENT_BROWSER_VERSION into $HERMES_HOME"
mkdir -p "$HERMES_HOME"
# The published package declares Node 24 for source builds, but ships a native
# linux-arm64 binary. The Node 20 shim is verified below before the service starts.
npm_config_engine_strict=false npm install \
  --prefix "$HERMES_HOME" \
  --no-save \
  --package-lock=false \
  "agent-browser@$AGENT_BROWSER_VERSION"

current="$(installed_version || true)"
[ "$current" = "$AGENT_BROWSER_VERSION" ] || \
  fail "installed agent-browser version is ${current:-unreadable}"

say "Installing localhost-only Chromium CDP service"
mkdir -p "$(dirname "$UNIT_TARGET")"
install -m 0644 "$UNIT_SOURCE" "$UNIT_TARGET"
systemctl --user daemon-reload
systemctl --user enable --now hermes-browser.service

for _ in $(seq 1 30); do
  if check_cdp >/dev/null 2>&1; then
    check_all
    say "Run: python3 $REPO_ROOT/browser/browser_smoke.py"
    exit 0
  fi
  sleep 0.5
done

systemctl --user status hermes-browser.service --no-pager || true
fail "Chromium CDP did not become ready at $CDP_URL"
