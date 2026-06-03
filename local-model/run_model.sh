#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
#
# Unified vLLM launcher for Hermes agent models on the DGX Spark (128GB).
#
# Usage:
#   bash local-model/run_model.sh [MODEL]      # foreground
#   nohup bash local-model/run_model.sh [MODEL] &  # background
#
# MODEL choices:
#   qwen           Qwen3.5-122B-A10B-AWQ    (default) — ~14 tok/s baseline
#   qwen-hybrid    Qwen3.5-122B AR-INT4+FP8 — ~51 tok/s (requires re-download)
#   qwen36         Qwen3.6-35B-A3B-AWQ      — agent-optimised, ~18GB, fast
#   minimax        MiniMax-M2.7-AWQ-4bit    — alternative MoE, ~100GB
#
# MTP (Multi-Token Prediction) is enabled by default for qwen/qwen-hybrid/qwen36.
# Disable with: MTP_TOKENS=0 bash local-model/run_model.sh qwen
#
# After switching models, point Hermes at the right provider:
#   cp config/config.fragment.<model>.yaml config/config.fragment.yaml
#   python3 bootstrap/stage.py
#   hermes gateway restart
#
# Environment overrides (any model):
#   HERMES_VLLM_PORT          default 8003
#   HERMES_VLLM_GPU_UTIL      override gpu-memory-utilization
#   HERMES_VLLM_MAX_MODEL_LEN override max-model-len
#   HERMES_MODEL_PATH         override model directory

set -euo pipefail

MODEL_TYPE="${1:-qwen}"
PORT="${HERMES_VLLM_PORT:-8003}"
MTP_TOKENS="${MTP_TOKENS:-0}"   # MTP requires built-in draft heads; Qwen3.5 AWQ loads full model twice without them

# ── Per-model defaults ────────────────────────────────────────────────────────
case "${MODEL_TYPE}" in

  qwen|qwen35)
    MODEL_PATH="${HERMES_MODEL_PATH:-./models/Qwen/Qwen3.5-122B-A10B-AWQ}"
    SERVED_NAME="Qwen3.5-122B-A10B-AWQ"
    GPU_UTIL="${HERMES_VLLM_GPU_UTIL:-0.85}"
    MAX_MODEL_LEN="${HERMES_VLLM_MAX_MODEL_LEN:-65536}"
    TOOL_CALL_PARSER="qwen3_xml"
    QUANTIZATION="awq"
    KV_CACHE_DTYPE="fp8"
    EXTRA_FLAGS=(
      --enable-prefix-caching
      --max-num-batched-tokens 8192
    )
    ;;

  qwen-hybrid)
    # Intel AutoRound INT4: better calibration than AWQ, ~51 tok/s on DGX Spark.
    # Download: bash local-model/download_model.sh qwen-hybrid
    MODEL_PATH="${HERMES_MODEL_PATH:-./models/Qwen/Qwen3.5-122B-A10B-int4-AutoRound}"
    SERVED_NAME="Qwen3.5-122B-A10B-AWQ"   # same name so Hermes config needs no change
    GPU_UTIL="${HERMES_VLLM_GPU_UTIL:-0.90}"
    MAX_MODEL_LEN="${HERMES_VLLM_MAX_MODEL_LEN:-65536}"
    TOOL_CALL_PARSER="qwen3_xml"
    QUANTIZATION=""                        # AutoRound uses compressed-tensors; vLLM auto-detects
    KV_CACHE_DTYPE="fp8"
    EXTRA_FLAGS=(
      --enable-prefix-caching
      --max-num-batched-tokens 8192
    )
    ;;

  qwen36)
    MODEL_PATH="${HERMES_MODEL_PATH:-./models/Qwen/Qwen3.6-35B-A3B-AWQ}"
    SERVED_NAME="Qwen3.6-35B-A3B-AWQ"
    GPU_UTIL="${HERMES_VLLM_GPU_UTIL:-0.50}"
    MAX_MODEL_LEN="${HERMES_VLLM_MAX_MODEL_LEN:-65536}"
    TOOL_CALL_PARSER="qwen3_xml"
    QUANTIZATION="awq"
    KV_CACHE_DTYPE="fp8"
    EXTRA_FLAGS=(
      --enable-prefix-caching
      --max-num-batched-tokens 8192
    )
    ;;

  minimax)
    MODEL_PATH="${HERMES_MODEL_PATH:-./models/MiniMax/MiniMax-M2.7-AWQ-4bit}"
    SERVED_NAME="MiniMax-M2.7-AWQ-4bit"
    GPU_UTIL="${HERMES_VLLM_GPU_UTIL:-0.90}"
    MAX_MODEL_LEN="${HERMES_VLLM_MAX_MODEL_LEN:-65536}"
    TOOL_CALL_PARSER="minimax_m2"
    QUANTIZATION=""          # cyankiwi repo uses compressed-tensors, not awq
    KV_CACHE_DTYPE="fp8"
    EXTRA_FLAGS=(
      --reasoning-parser minimax_m2
    )
    export SAFETENSORS_FAST_GPU="${SAFETENSORS_FAST_GPU:-1}"
    export VLLM_USE_V1="${VLLM_USE_V1:-0}"
    ;;

  *)
    echo "ERROR: Unknown model '${MODEL_TYPE}'" >&2
    echo "Usage: $0 [qwen|qwen-hybrid|qwen36|minimax]" >&2
    exit 1
    ;;
esac

# ── Pre-flight check ─────────────────────────────────────────────────────────
if [ ! -f "${MODEL_PATH}/config.json" ]; then
  echo "ERROR: ${MODEL_PATH}/config.json not found." >&2
  echo "Download first:  bash local-model/download_model.sh ${MODEL_TYPE}" >&2
  exit 1
fi

# ── Launch ────────────────────────────────────────────────────────────────────
echo "Starting Hermes vLLM server"
echo "  model   : ${MODEL_TYPE} (${SERVED_NAME})"
echo "  path    : ${MODEL_PATH}"
echo "  port    : ${PORT}"
echo "  gpu_util: ${GPU_UTIL}"
echo "  max_len : ${MAX_MODEL_LEN}"
echo "  tool_call_parser: ${TOOL_CALL_PARSER}"
echo "  mtp_tokens: ${MTP_TOKENS} (multi-token prediction)"
echo "  sampling penalties: via Hermes providers.extra_body (not CLI)"
echo

# Build command — conditionally add --quantization only when set
VLLM_ARGS=(
  vllm serve "${MODEL_PATH}"
  --served-model-name "${SERVED_NAME}"
  --tensor-parallel-size 1
  --gpu-memory-utilization "${GPU_UTIL}"
  --max-model-len "${MAX_MODEL_LEN}"
  --kv-cache-dtype "${KV_CACHE_DTYPE}"
  --trust-remote-code
  --enable-auto-tool-choice
  --tool-call-parser "${TOOL_CALL_PARSER}"
  --host 0.0.0.0
  --port "${PORT}"
  --uvicorn-log-level warning
)

if [ -n "${QUANTIZATION}" ]; then
  VLLM_ARGS+=(--quantization "${QUANTIZATION}")
fi

# MTP: enabled for all Qwen models; skip for minimax (unsupported)
if [ "${MTP_TOKENS}" -gt 0 ] && [ "${MODEL_TYPE}" != "minimax" ]; then
  VLLM_ARGS+=(--speculative-config "{\"method\": \"mtp\", \"num_speculative_tokens\": ${MTP_TOKENS}}")
fi

VLLM_ARGS+=("${EXTRA_FLAGS[@]}")

exec "${VLLM_ARGS[@]}"
