#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
# Serve the 4-bit Qwen3.8 Flash-Next GGUF checkpoint on the local Hermes port.

set -euo pipefail

MODEL_DIR="${HERMES_FLASH_NEXT_DIR:-/home/david/workspace/models/unsloth/Qwen3.8-Flash-Next-GGUF/UD-IQ4_XS}"
MODEL_PREFIX="Qwen3.8-Flash-Next-UD-IQ4_XS"
MODEL_PATH="${MODEL_DIR}/${MODEL_PREFIX}-00001-of-00003.gguf"
MMPROJ_PATH="${HERMES_FLASH_NEXT_MMPROJ:-${MODEL_DIR}/../mmproj-F16.gguf}"
SERVER_BIN="${HERMES_LLAMA_SERVER_BIN:-/home/david/workspace/llama.cpp/build-qwen38/bin/llama-server}"
GPU_CHECK_BIN="${HERMES_GPU_CHECK_BIN:-nvidia-smi}"
PORT="${HERMES_MODEL_PORT:-8003}"
CONTEXT="${HERMES_MODEL_CONTEXT:-131072}"
PARALLEL="${HERMES_MODEL_PARALLEL:-2}"
SERVED_NAME="${HERMES_MODEL_NAME:-Qwen3.8-Flash-Next-UD-IQ4_XS}"

for shard in 1 2 3; do
  printf -v suffix '%05d' "${shard}"
  file="${MODEL_DIR}/${MODEL_PREFIX}-${suffix}-of-00003.gguf"
  if [ ! -s "${file}" ]; then
    echo "ERROR: Missing or empty model shard: ${file}" >&2
    exit 1
  fi
done

if [ ! -s "${MMPROJ_PATH}" ]; then
  echo "ERROR: Missing or empty vision projector: ${MMPROJ_PATH}" >&2
  exit 1
fi

if [ ! -x "${SERVER_BIN}" ]; then
  echo "ERROR: llama-server is not executable: ${SERVER_BIN}" >&2
  exit 1
fi

ARGS=(
  "${SERVER_BIN}"
  --model "${MODEL_PATH}"
  --mmproj "${MMPROJ_PATH}"
  --alias "${SERVED_NAME}"
  --host 127.0.0.1
  --port "${PORT}"
  --ctx-size "${CONTEXT}"
  --parallel "${PARALLEL}"
  --gpu-layers auto
  --lazy-mode off
  --fit on
  --fit-target 8192
  --fit-ctx "${CONTEXT}"
  --metrics
  --no-webui
)

if [ "${HERMES_MODEL_DRY_RUN:-0}" = "1" ]; then
  printf 'Command:'
  printf ' %q' "${ARGS[@]}"
  printf '\n'
  exit 0
fi

if ! "${GPU_CHECK_BIN}" -L >/dev/null 2>&1; then
  echo "ERROR: NVIDIA GPU is unavailable; refusing CPU-only model fallback." >&2
  exit 78
fi

exec "${ARGS[@]}"
