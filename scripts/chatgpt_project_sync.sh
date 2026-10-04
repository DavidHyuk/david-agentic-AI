#!/usr/bin/env bash
# Author: David Choi. Purpose: daily project-only ChatGPT capture and local RAG refresh.
set -euo pipefail
hermes_sync_root="${HERMES_HOME:-/home/david/.hermes}"
exec timeout --signal=TERM --kill-after=20s 25m \
  "$hermes_sync_root/venvs/youtube-history/bin/python" \
  "$hermes_sync_root/scripts/chatgpt_archive.py" \
  --data-dir "$hermes_sync_root/data/chatgpt" sync-daily \
  --project "Silicon Valley Career 2027" \
  --runtime-dir "$hermes_sync_root/venvs/youtube-history" \
  --rag-python "$hermes_sync_root/venvs/chatgpt-rag/bin/python"
