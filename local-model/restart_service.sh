#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
#
# Restart the always-on Hermes vLLM user service and optionally wait until its
# OpenAI-compatible endpoint is ready to receive requests.

set -euo pipefail

SERVICE_NAME="${HERMES_VLLM_SERVICE:-hermes-vllm.service}"
API_URL="${HERMES_VLLM_API_URL:-http://127.0.0.1:8003/v1}"
WAIT_FOR_READY=0
TIMEOUT_SECONDS=600

usage() {
  cat <<'EOF'
Usage: bash local-model/restart_service.sh [--wait] [--timeout SECONDS]

Restart the Hermes vLLM user service. --wait polls the OpenAI-compatible
/models endpoint until the model finishes loading (up to 600 seconds by
default). Override the service and endpoint with HERMES_VLLM_SERVICE and
HERMES_VLLM_API_URL when needed.
EOF
}

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
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

systemctl --user restart "${SERVICE_NAME}"

if ! systemctl --user is-active --quiet "${SERVICE_NAME}"; then
  systemctl --user --no-pager --full status "${SERVICE_NAME}" || true
  echo "ERROR: ${SERVICE_NAME} did not become active." >&2
  exit 1
fi

echo "Restarted ${SERVICE_NAME}."

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
