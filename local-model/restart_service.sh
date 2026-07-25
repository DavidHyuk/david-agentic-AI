#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
#
# Restart the always-on Hermes vLLM user service and optionally wait until its
# OpenAI-compatible endpoint is ready to receive requests.

set -euo pipefail

SERVICE_NAME="${HERMES_VLLM_SERVICE:-hermes-vllm.service}"
API_URL="${HERMES_VLLM_API_URL:-http://127.0.0.1:8003/v1}"
GPU_UTIL="0.50"
WAIT_FOR_READY=0
TIMEOUT_SECONDS=600
OVERRIDE_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user/${SERVICE_NAME}.d"
OVERRIDE_FILE="${OVERRIDE_DIR}/gpu-memory.conf"

usage() {
  cat <<'EOF'
Usage: bash local-model/restart_service.sh [GPU_UTIL] [--wait] [--timeout SECONDS]

Restart the Hermes vLLM user service. GPU_UTIL sets the persistent
HERMES_VLLM_GPU_UTIL systemd override; it defaults to 0.50 and must be in
(0, 1]. --wait polls the OpenAI-compatible /models endpoint until the model
finishes loading (up to 600 seconds by default). Override the service and
endpoint with HERMES_VLLM_SERVICE and HERMES_VLLM_API_URL when needed.
EOF
}

is_valid_gpu_util() {
  [[ "$1" =~ ^[0-9]+(\.[0-9]+)?$ ]] && awk -v value="$1" 'BEGIN {
    exit !(value > 0 && value <= 1)
  }'
}

GPU_UTIL_SET=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --wait)
      WAIT_FOR_READY=1
      ;;
    --timeout)
      if [ "$#" -lt 2 ] || ! [[ "$2" =~ ^[1-9][0-9]*$ ]]; then
        echo "ERROR: --timeout requires a positive integer." >&2
        exit 2
      fi
      TIMEOUT_SECONDS="$2"
      shift
      ;;
    --gpu-util)
      if [ "$#" -lt 2 ] || ! is_valid_gpu_util "$2"; then
        echo "ERROR: --gpu-util requires a number in (0, 1]." >&2
        exit 2
      fi
      GPU_UTIL="$2"
      GPU_UTIL_SET=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [ "${GPU_UTIL_SET}" = "1" ] || ! is_valid_gpu_util "$1"; then
        echo "ERROR: GPU_UTIL must be a number in (0, 1]." >&2
        usage >&2
        exit 2
      fi
      GPU_UTIL="$1"
      GPU_UTIL_SET=1
      ;;
  esac
  shift
done

install -d -m 0755 "${OVERRIDE_DIR}"
printf '[Service]\nEnvironment=HERMES_VLLM_GPU_UTIL=%s\n' "${GPU_UTIL}" > "${OVERRIDE_FILE}"
systemctl --user daemon-reload
systemctl --user restart "${SERVICE_NAME}"

if ! systemctl --user is-active --quiet "${SERVICE_NAME}"; then
  systemctl --user --no-pager --full status "${SERVICE_NAME}" || true
  echo "ERROR: ${SERVICE_NAME} did not become active." >&2
  exit 1
fi

echo "Set HERMES_VLLM_GPU_UTIL=${GPU_UTIL} and restarted ${SERVICE_NAME}."

if [ "${WAIT_FOR_READY}" = "0" ]; then
  echo "The model loads in a few minutes. Follow logs: journalctl --user -u ${SERVICE_NAME} -f"
  exit 0
fi

deadline=$(( $(date +%s) + TIMEOUT_SECONDS ))
while ! curl -fsS --max-time 5 "${API_URL}/models" >/dev/null; do
  if [ "$(date +%s)" -ge "${deadline}" ]; then
    echo "ERROR: Timed out after ${TIMEOUT_SECONDS}s waiting for ${API_URL}/models." >&2
    exit 1
  fi
  sleep 5
done

echo "vLLM API is ready at ${API_URL}."
