#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
#
# Start vLLM for Hermes using MiniMax-M2.7 AWQ 4-bit (single DGX Spark).
#
# Prerequisite: bash local-model/download_minimax_m27.sh
# Stop Qwen vLLM first — both models cannot share 128GB VRAM at once.
#
# MiniMax differs from Qwen launch:
#   --tool-call-parser minimax_m2  (not qwen3_xml)
#   --reasoning-parser minimax_m2  (or minimax_m2_append_think)
#   No --quantization awq (cyankiwi uses compressed-tensors)
#
# Official BF16 MiniMaxAI/MiniMax-M2.7 needs ~220GB weights + multi-GPU;
# use cyankiwi/MiniMax-M2.7-AWQ-4bit on 128GB instead.
#
# vLLM >= 0.19 recommended. Upgrade inside Docker if serve fails:
#   pip install -U "vllm>=0.19.0"
#
# Usage:
#   bash local-model/run_hermes_model_minimax.sh

set -euo pipefail

MODEL_PATH="${HERMES_MODEL_PATH:-./models/MiniMax/MiniMax-M2.7-AWQ-4bit}"
SERVED_NAME="${HERMES_SERVED_MODEL_NAME:-MiniMax-M2.7-AWQ-4bit}"
PORT="${HERMES_VLLM_PORT:-8003}"
GPU_UTIL="${HERMES_VLLM_GPU_UTIL:-0.90}"
# Hermes requires >=64K; cyankiwi benchmarks show 65536 works on Spark (slower at long ctx)
MAX_LEN="${HERMES_VLLM_MAX_MODEL_LEN:-65536}"
TP="${HERMES_VLLM_TENSOR_PARALLEL:-1}"

echo "Starting Hermes vLLM server (MiniMax-M2.7)"
echo "  model   : ${MODEL_PATH}"
echo "  served  : ${SERVED_NAME}"
echo "  port    : ${PORT}"
echo "  gpu_util: ${GPU_UTIL}"
echo "  max_len : ${MAX_LEN}"
echo "  tp      : ${TP}"
echo "  tool_call_parser: minimax_m2"
echo "  sampling penalties: Hermes providers.minimax-hermes.extra_body"
echo

if [ ! -f "${MODEL_PATH}/config.json" ]; then
  echo "ERROR: ${MODEL_PATH}/config.json not found." >&2
  echo "Run: bash local-model/download_minimax_m27.sh" >&2
  exit 1
fi

export SAFETENSORS_FAST_GPU="${SAFETENSORS_FAST_GPU:-1}"
export VLLM_USE_V1="${VLLM_USE_V1:-0}"

exec vllm serve "${MODEL_PATH}" \
    --served-model-name "${SERVED_NAME}" \
    --tensor-parallel-size "${TP}" \
    --gpu-memory-utilization "${GPU_UTIL}" \
    --max-model-len "${MAX_LEN}" \
    --kv-cache-dtype fp8 \
    --trust-remote-code \
    --enable-auto-tool-choice \
    --tool-call-parser minimax_m2 \
    --reasoning-parser minimax_m2 \
    --host 0.0.0.0 \
    --port "${PORT}"
