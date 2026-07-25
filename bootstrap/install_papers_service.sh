#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
# Purpose: stage and enable the daily paper-ingestion user service and timer.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
HERMES_RUNTIME_HOME="${HERMES_HOME:-$HOME/.hermes}"
USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

python3 "$REPO_ROOT/bootstrap/stage.py" --home "$HERMES_RUNTIME_HOME"
install -d -m 0700 "$HERMES_RUNTIME_HOME/data/papers"
mkdir -p "$USER_UNIT_DIR"
install -m 0644 \
  "$REPO_ROOT/bootstrap/hermes-papers-ingest.service" \
  "$USER_UNIT_DIR/hermes-papers-ingest.service"
install -m 0644 \
  "$REPO_ROOT/bootstrap/hermes-papers-ingest.timer" \
  "$USER_UNIT_DIR/hermes-papers-ingest.timer"

systemctl --user daemon-reload
systemctl --user enable --now hermes-papers-ingest.timer
systemctl --user start hermes-papers-ingest.service

echo "Paper ingestion installed."
systemctl --user --no-pager status hermes-papers-ingest.timer
python3 "$HERMES_RUNTIME_HOME/scripts/papers_ingest.py" \
  --db "$HERMES_RUNTIME_HOME/data/papers/papers.db" \
  --status
