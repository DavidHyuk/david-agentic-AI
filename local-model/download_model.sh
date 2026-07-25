#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
#
# Unified model downloader for Hermes agent models.
#
# Usage:
#   bash local-model/download_model.sh [MODEL]
#
# MODEL choices:
#   qwen36       Qwen3.6-35B-A3B-FP8          (~35GB)  — recommended for agents
#   qwen-hybrid  Qwen3.5-122B AR-INT4+FP8     (~65GB)  — ~51 tok/s on DGX Spark
#   minimax      MiniMax-M2.7-AWQ-4bit        (~100GB) — alternative MoE
#   qwen         Qwen3.5-122B-A10B-AWQ        — already on disk (skip or re-download)
#
# Environment overrides:
#   HERMES_MODEL_DIR   base directory for model weights (default: workspace/models)
#   HF_REPO            override the Hugging Face repo ID

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE_ROOT="$(cd "${REPO_ROOT}/.." && pwd)"

MODEL_TYPE="${1:-}"
MODEL_BASE_DIR="${HERMES_MODEL_DIR:-${WORKSPACE_ROOT}/models}"

if [ -z "${MODEL_TYPE}" ]; then
  echo "Usage: $0 [qwen36|minimax|qwen]" >&2
  exit 1
fi

# ── Per-model config ──────────────────────────────────────────────────────────
case "${MODEL_TYPE}" in

  qwen-hybrid)
    HF_REPO="${HF_REPO:-Intel/Qwen3.5-122B-A10B-int4-AutoRound}"
    DEST="${MODEL_BASE_DIR}/Qwen/Qwen3.5-122B-A10B-int4-AutoRound"
    SIZE="~77GB"
    NEXT_STEP="bash local-model/run_model.sh qwen-hybrid"
    ;;

  qwen36)
    HF_REPO="${HF_REPO:-Qwen/Qwen3.6-35B-A3B-FP8}"
    DEST="${MODEL_BASE_DIR}/Qwen/Qwen3.6-35B-A3B-FP8"
    SIZE="~35GB"
    NEXT_STEP="bash local-model/run_model.sh qwen36"
    ;;

  minimax)
    HF_REPO="${HF_REPO:-cyankiwi/MiniMax-M2.7-AWQ-4bit}"
    DEST="${MODEL_BASE_DIR}/MiniMax/MiniMax-M2.7-AWQ-4bit"
    SIZE="~100GB"
    NEXT_STEP="bash local-model/run_model.sh minimax"
    ;;

  qwen|qwen35)
    HF_REPO="${HF_REPO:-Qwen/Qwen3.5-122B-A10B-AWQ}"
    DEST="${MODEL_BASE_DIR}/Qwen/Qwen3.5-122B-A10B-AWQ"
    SIZE="~60GB"
    NEXT_STEP="bash local-model/run_model.sh qwen"
    ;;

  *)
    echo "ERROR: Unknown model '${MODEL_TYPE}'" >&2
    echo "Usage: $0 [qwen-hybrid|qwen36|minimax|qwen]" >&2
    exit 1
    ;;
esac

# ── Pre-flight ────────────────────────────────────────────────────────────────
python3 -m pip install -q -U "huggingface_hub" "hf_transfer" 2>/dev/null || true

if [ -f "${DEST}/config.json" ]; then
  echo "Model already present at ${DEST}"
  echo "Delete the directory and re-run if you want a fresh download."
  exit 0
fi

mkdir -p "$(dirname "${DEST}")"

echo "Downloading ${HF_REPO}"
echo "  -> ${DEST}"
echo "  size: ${SIZE} (may take a while)"
echo

# Use Python API directly — avoids huggingface-cli binary version mismatches.
# hf_transfer accelerates large downloads when available.
HF_HUB_ENABLE_HF_TRANSFER=1 python3 - <<PYEOF
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="${HF_REPO}",
    local_dir="${DEST}",
    local_dir_use_symlinks=False,
)
PYEOF

echo
echo "Done. Weights at: ${DEST}"
echo "Next: stop any running vLLM server, then:"
echo "  ${NEXT_STEP}"
