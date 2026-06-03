#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
#
# Download MiniMax-M2.7 AWQ 4-bit weights for single-GPU DGX Spark (128GB).
# Recommended repo: cyankiwi/MiniMax-M2.7-AWQ-4bit (DGX Spark community recipe).
#
# Requires: huggingface-cli (pip install huggingface_hub[cli])
# Optional: huggingface-cli login  (for gated models; this repo is usually public)
#
# Usage (from repo root, or inside Docker with /app mounted):
#   bash local-model/download_minimax_m27.sh
#   # or override destination:
#   HERMES_MODEL_DIR=/data/models bash local-model/download_minimax_m27.sh

set -euo pipefail

REPO_ID="${MINIMAX_HF_REPO:-cyankiwi/MiniMax-M2.7-AWQ-4bit}"
DEST="${HERMES_MODEL_DIR:-./models/MiniMax/MiniMax-M2.7-AWQ-4bit}"

if ! command -v huggingface-cli >/dev/null 2>&1; then
  echo "Installing huggingface_hub CLI..."
  python3 -m pip install --user -U "huggingface_hub[cli]"
fi

mkdir -p "$(dirname "$DEST")"
echo "Downloading ${REPO_ID}"
echo "  -> ${DEST}"
echo "(~100GB+; may take a while depending on network)"
echo

huggingface-cli download "${REPO_ID}" \
  --local-dir "${DEST}" \
  --local-dir-use-symlinks False

echo
echo "Done. Weights at: ${DEST}"
echo "Next: stop any running Qwen vLLM, then:"
echo "  bash local-model/run_hermes_model_minimax.sh"
