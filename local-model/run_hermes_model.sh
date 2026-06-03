#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
#
# Start a dedicated vLLM OpenAI-compatible server for the Hermes agent.
#
# Uses the same Qwen3.5-122B-A10B-AWQ weights already on disk from ClawGram
# (no extra download required). Serves on :8003 to avoid conflicts with
# ClawGram's inference (:8001) and openai-compat (:8002) servers.
#
# Key differences from ClawGram's run_inference.sh:
#   --max-model-len 65536          Hermes Agent requires >= 64K context window.
#   --enable-auto-tool-choice      Hermes sends tools on every turn (required).
#   --tool-call-parser qwen3_xml   Same parser as ClawGram (CLAWGRAM_TOOL_CALL_PARSER).
#
# presence_penalty / repetition_penalty are NOT vllm serve CLI flags (they error).
# Set them per request via providers.qwen-hermes.extra_body in config.fragment.yaml.
#
# NOTE: Loading the 122B model into a second vLLM process requires ~60GB
# additional VRAM (AWQ 4-bit). On DGX Spark (128GB HBM3e), this is feasible
# when ClawGram also runs (ClawGram: gpu_memory_utilization=0.85 ≈ 109GB on its
# allocation vs 128GB total). To share VRAM, stop ClawGram's inference server
# first, or run with --gpu-memory-utilization tuned down if needed.
#
# Usage:
#   bash local-model/run_hermes_model.sh          # foreground
#   nohup bash local-model/run_hermes_model.sh &  # background

set -euo pipefail

MODEL_PATH="${HERMES_MODEL_PATH:-./models/Qwen/Qwen3.5-122B-A10B-AWQ}"
PORT="${HERMES_VLLM_PORT:-8003}"
GPU_UTIL="${HERMES_VLLM_GPU_UTIL:-0.85}"

echo "Starting Hermes vLLM server"
echo "  model   : ${MODEL_PATH}"
echo "  port    : ${PORT}"
echo "  gpu_util: ${GPU_UTIL}"
echo "  context : 65536 tokens"
echo "  tool_call_parser  : qwen3_xml"
echo "  sampling penalties: via Hermes providers.qwen-hermes.extra_body (not CLI)"
echo

exec vllm serve "${MODEL_PATH}" \
    --served-model-name "Qwen3.5-122B-A10B-AWQ" \
    --quantization awq \
    --tensor-parallel-size 1 \
    --gpu-memory-utilization "${GPU_UTIL}" \
    --max-model-len 65536 \
    --kv-cache-dtype fp8 \
    --trust-remote-code \
    --enable-auto-tool-choice \
    --tool-call-parser qwen3_xml \
    --enable-prefix-caching \
    --max-num-batched-tokens 8192 \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --uvicorn-log-level warning
