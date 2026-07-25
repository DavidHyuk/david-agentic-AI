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
#   qwen           Qwen3.5-122B-A10B-AWQ    — legacy baseline
#   qwen-hybrid    Qwen3.5-122B AR-INT4+FP8 — legacy hybrid checkpoint
#   qwen36         Qwen3.6-35B-A3B-FP8      — Hermes default, fast MoE
#   minimax        MiniMax-M2.7-AWQ-4bit    — alternative MoE
#
# MTP (Multi-Token Prediction) is disabled by default. Enable only after the
# base server is stable, for example:
#   MTP_TOKENS=2 bash local-model/run_model.sh qwen36
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
#   HERMES_MODEL_DIR          base model directory (default: workspace/models)
#   HERMES_VLLM_BIN           vLLM executable (default: local-model/.venv/bin/vllm)
#   HERMES_VLLM_DRY_RUN=1     validate and print the command without launching

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE_ROOT="$(cd "${REPO_ROOT}/.." && pwd)"

MODEL_TYPE="${1:-qwen}"
PORT="${HERMES_VLLM_PORT:-8003}"
MTP_TOKENS="${MTP_TOKENS:-0}"
MODEL_BASE_DIR="${HERMES_MODEL_DIR:-${WORKSPACE_ROOT}/models}"
LANGUAGE_MODEL_ONLY="${HERMES_VLLM_LANGUAGE_MODEL_ONLY:-0}"

REASONING_PARSER=""
EXPECTED_QUANTIZATION=""
MTP_METHOD="mtp"

# ── Per-model defaults ────────────────────────────────────────────────────────
case "${MODEL_TYPE}" in

  qwen|qwen35)
    MODEL_PATH="${HERMES_MODEL_PATH:-${MODEL_BASE_DIR}/Qwen/Qwen3.5-122B-A10B-AWQ}"
    SERVED_NAME="Qwen3.5-122B-A10B-AWQ"
    GPU_UTIL="${HERMES_VLLM_GPU_UTIL:-0.85}"
    MAX_MODEL_LEN="${HERMES_VLLM_MAX_MODEL_LEN:-65536}"
    TOOL_CALL_PARSER="qwen3_xml"
    QUANTIZATION="awq"
    EXPECTED_QUANTIZATION="awq"
    KV_CACHE_DTYPE="fp8"
    EXTRA_FLAGS=(
      --enable-prefix-caching
      --max-num-batched-tokens 8192
    )
    ;;

  qwen-hybrid)
    # Intel AutoRound INT4: better calibration than AWQ, ~51 tok/s on DGX Spark.
    # Download: bash local-model/download_model.sh qwen-hybrid
    MODEL_PATH="${HERMES_MODEL_PATH:-${MODEL_BASE_DIR}/Qwen/Qwen3.5-122B-A10B-int4-AutoRound}"
    SERVED_NAME="Qwen3.5-122B-A10B-AWQ"   # same name so Hermes config needs no change
    GPU_UTIL="${HERMES_VLLM_GPU_UTIL:-0.90}"
    MAX_MODEL_LEN="${HERMES_VLLM_MAX_MODEL_LEN:-65536}"
    TOOL_CALL_PARSER="qwen3_xml"
    QUANTIZATION=""                        # AutoRound uses compressed-tensors; vLLM auto-detects
    KV_CACHE_DTYPE="fp8"
    # AutoRound tokenizer_config.json references TokenizersBackend which is
    # unavailable here — reuse the tokenizer from the AWQ model (same base).
    TOKENIZER="${HERMES_VLLM_TOKENIZER:-${MODEL_BASE_DIR}/Qwen/Qwen3.5-122B-A10B-AWQ}"
    EXTRA_FLAGS=(
      --tokenizer "${TOKENIZER}"
      --enable-prefix-caching
      --max-num-batched-tokens 8192
    )
    ;;

  qwen36|qwen36-fp8)
    MODEL_PATH="${HERMES_MODEL_PATH:-${MODEL_BASE_DIR}/Qwen/Qwen3.6-35B-A3B-FP8}"
    SERVED_NAME="Qwen3.6-35B-A3B-FP8"
    GPU_UTIL="${HERMES_VLLM_GPU_UTIL:-0.70}"
    MAX_MODEL_LEN="${HERMES_VLLM_MAX_MODEL_LEN:-131072}"
    REASONING_PARSER="qwen3"
    TOOL_CALL_PARSER="qwen3_coder"
    # The checkpoint declares fine-grained FP8 in config.json. Let vLLM
    # auto-detect it; passing --quantization awq makes this model fail to load.
    QUANTIZATION=""
    EXPECTED_QUANTIZATION="fp8"
    # The checkpoint does not include calibrated FP8 KV q/prob scales. Keep
    # weights in FP8 but use the model dtype for KV cache to protect quality.
    KV_CACHE_DTYPE="auto"
    MTP_METHOD="qwen3_next_mtp"
    EXTRA_FLAGS=(
      --enable-prefix-caching
      --max-num-batched-tokens 8192
    )
    ;;

  minimax)
    MODEL_PATH="${HERMES_MODEL_PATH:-${MODEL_BASE_DIR}/MiniMax/MiniMax-M2.7-AWQ-4bit}"
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
PREFLIGHT_ARGS=("${MODEL_PATH}" --min-context-length "${MAX_MODEL_LEN}")
if [ -n "${EXPECTED_QUANTIZATION}" ]; then
  PREFLIGHT_ARGS+=(--expected-quantization "${EXPECTED_QUANTIZATION}")
fi
python3 "${SCRIPT_DIR}/model_preflight.py" "${PREFLIGHT_ARGS[@]}"

if [ -n "${HERMES_VLLM_BIN:-}" ]; then
  VLLM_BIN="${HERMES_VLLM_BIN}"
elif [ -x "${SCRIPT_DIR}/.venv/bin/vllm" ]; then
  VLLM_BIN="${SCRIPT_DIR}/.venv/bin/vllm"
elif command -v vllm >/dev/null 2>&1; then
  VLLM_BIN="$(command -v vllm)"
else
  echo "ERROR: vLLM executable not found." >&2
  echo "Create the isolated runtime with: bash local-model/setup_vllm.sh" >&2
  exit 1
fi

# ── Launch ────────────────────────────────────────────────────────────────────
echo "Starting Hermes vLLM server"
echo "  model   : ${MODEL_TYPE} (${SERVED_NAME})"
echo "  path    : ${MODEL_PATH}"
echo "  port    : ${PORT}"
echo "  gpu_util: ${GPU_UTIL}"
echo "  max_len : ${MAX_MODEL_LEN}"
echo "  weights : ${EXPECTED_QUANTIZATION:-auto}"
echo "  kv_cache: ${KV_CACHE_DTYPE}"
echo "  reasoning_parser: ${REASONING_PARSER:-none}"
echo "  tool_call_parser: ${TOOL_CALL_PARSER}"
echo "  mtp_tokens: ${MTP_TOKENS} (multi-token prediction)"
echo "  sampling penalties: via Hermes providers.extra_body (not CLI)"
echo

# Build command — conditionally add --quantization only when set
VLLM_ARGS=(
  "${VLLM_BIN}" serve "${MODEL_PATH}"
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

if [ -n "${REASONING_PARSER}" ]; then
  VLLM_ARGS+=(--reasoning-parser "${REASONING_PARSER}")
fi

if [ -n "${QUANTIZATION}" ]; then
  VLLM_ARGS+=(--quantization "${QUANTIZATION}")
fi

# MTP: opt-in; Qwen3.6 uses the checkpoint's next-token prediction heads.
if [ "${MTP_TOKENS}" -gt 0 ] && [ "${MODEL_TYPE}" != "minimax" ]; then
  VLLM_ARGS+=(--speculative-config "{\"method\": \"${MTP_METHOD}\", \"num_speculative_tokens\": ${MTP_TOKENS}}")
fi

if [ "${LANGUAGE_MODEL_ONLY}" = "1" ]; then
  VLLM_ARGS+=(--language-model-only)
fi

VLLM_ARGS+=("${EXTRA_FLAGS[@]}")

if [ "${HERMES_VLLM_DRY_RUN:-0}" = "1" ]; then
  printf "Command:"
  printf " %q" "${VLLM_ARGS[@]}"
  printf "\n"
  exit 0
fi

if ! VLLM_VERSION_OUTPUT="$("${VLLM_BIN}" --version 2>&1)"; then
  echo "ERROR: ${VLLM_BIN} exists but cannot load its CUDA/PyTorch runtime." >&2
  echo "${VLLM_VERSION_OUTPUT}" >&2
  echo "Recreate the isolated runtime with: bash local-model/setup_vllm.sh" >&2
  exit 1
fi
echo "  vllm    : ${VLLM_VERSION_OUTPUT}"

exec "${VLLM_ARGS[@]}"
