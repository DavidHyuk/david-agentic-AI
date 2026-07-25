#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
#
# One-shot bootstrap for David's personalized Hermes agent.
# Installs the Hermes runtime (if missing), stages this repo's config into
# ~/.hermes, points the agent at the local DGX Spark vLLM endpoint, and prints
# the remaining interactive steps (paper timer, gateway link, Calendar OAuth, cron).
#
# Safe to re-run: staging is idempotent and backs up anything it overwrites.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }

say "1/6  Ensuring Python deps for the config tooling"
python3 -m pip install --quiet --user -r "$REPO_ROOT/requirements.txt" || \
  warn "Could not pip install deps; ensure PyYAML + pytest are available."

say "2/6  Installing the Hermes Agent runtime"
if command -v hermes >/dev/null 2>&1; then
  echo "hermes already installed: $(command -v hermes)"
else
  echo "Installing hermes-agent via pip..."
  if python3 -m pip install --quiet --user hermes-agent; then
    echo "Installed hermes-agent."
  else
    warn "pip install hermes-agent failed. Falling back to the official installer:"
    warn "  curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash"
    warn "Re-run this script after Hermes is on PATH."
  fi
fi

say "3/6  Staging skills, memory, SOUL, scripts, and config into $HERMES_HOME"
HERMES_HOME="$HERMES_HOME" python3 "$REPO_ROOT/bootstrap/stage.py" --home "$HERMES_HOME"

# Seed the local-endpoint API key into .env if not already present.
ENV_FILE="$HERMES_HOME/.env"
if [ ! -f "$ENV_FILE" ] || ! grep -q '^OPENAI_API_KEY=' "$ENV_FILE" 2>/dev/null; then
  echo "OPENAI_API_KEY=sk-local-no-key-required" >> "$ENV_FILE"
  chmod 600 "$ENV_FILE" 2>/dev/null || true
  echo "Seeded local endpoint key into $ENV_FILE"
fi

say "4/6  Installing the Hermes Built-in Browser runtime"
bash "$REPO_ROOT/browser/setup_browser.sh"

say "5/6  Verifying the staged Qwen3.6 FP8 provider configuration"
if command -v hermes >/dev/null 2>&1; then
  hermes config check 2>/dev/null || true
  echo "Confirm the served model name with: curl -s localhost:8003/v1/models"
else
  warn "hermes CLI not found; the model settings are already in config.yaml via stage.py."
fi

say "6/6  Next — service and interactive setup"
cat <<'STEPS'
  a) Start the local model with >=64K context (NOT the 8K Subscribe-Papers script):
       bash /home/david/workspace/david-agentic-ai/local-model/setup_vllm.sh
       bash /home/david/workspace/david-agentic-ai/local-model/install_service.sh
       journalctl --user -u hermes-vllm.service -f

     Model checkpoints are managed separately in /home/david/workspace/models.
     To add one: cd /home/david/workspace/models && python3 download_model.py OWNER/MODEL

  b) Verify a plain chat works:
       hermes -z "Say hi and tell me which model you are."

  c) Install the independent daily paper-ingestion timer:
       bash /home/david/workspace/david-agentic-ai/bootstrap/install_papers_service.sh

  d) Connect WhatsApp (QR device-link, one-time):
       hermes gateway setup        # choose WhatsApp, scan the QR
       hermes gateway install      # run the gateway as a service (needed for cron)

  e) Authorize Google Calendar (one-time OAuth) so the calendar skill can read it:
       # First follow docs/google-calendar-mcp.md to download a Web OAuth client.
       python3 /home/david/workspace/david-agentic-ai/mcp/setup_google_calendar.py \
         --credentials ~/.config/google/hermes-calendar-client.json
       python3 /home/david/workspace/david-agentic-ai/mcp/calendar_smoke.py

  f) Register the scheduled WhatsApp briefs (after the gateway is up):
       python3 /home/david/workspace/david-agentic-ai/bootstrap/register_cron.py --dry-run
       python3 /home/david/workspace/david-agentic-ai/bootstrap/register_cron.py

  g) Drop English lessons (audio + corrections) into ~/english-lessons/
STEPS
echo
echo "Done. Repo is the source of truth — edit, then re-run stage.py to re-sync."
