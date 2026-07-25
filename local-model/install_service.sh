#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
#
# Install and optionally start the Qwen3.6 vLLM user service.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
UNIT_SOURCE="${SCRIPT_DIR}/hermes-vllm.service"
UNIT_TARGET="${HOME}/.config/systemd/user/hermes-vllm.service"
GATEWAY_DROPIN_SOURCE="${SCRIPT_DIR}/hermes-gateway-vllm.conf"
GATEWAY_DROPIN_TARGET="${HOME}/.config/systemd/user/hermes-gateway.service.d/20-vllm-readiness.conf"
WAIT_SOURCE="${REPO_ROOT}/scripts/wait_for_vllm.py"
WAIT_TARGET="${HERMES_HOME:-${HOME}/.hermes}/scripts/wait_for_vllm.py"
START_SERVICE=1

if [ "${1:-}" = "--no-start" ]; then
  START_SERVICE=0
elif [ "$#" -gt 0 ]; then
  echo "Usage: $0 [--no-start]" >&2
  exit 2
fi

install -D -m 0644 "${UNIT_SOURCE}" "${UNIT_TARGET}"
install -D -m 0644 "${GATEWAY_DROPIN_SOURCE}" "${GATEWAY_DROPIN_TARGET}"
install -D -m 0755 "${WAIT_SOURCE}" "${WAIT_TARGET}"
systemctl --user daemon-reload

if [ "${START_SERVICE}" = "1" ]; then
  systemctl --user enable --now hermes-vllm.service
  if systemctl --user is-active --quiet hermes-gateway.service; then
    systemctl --user restart hermes-gateway.service
  fi
  echo "Installed and started hermes-vllm.service with gateway readiness gating"
  echo "Follow startup: journalctl --user -u hermes-vllm.service -f"
else
  systemctl --user enable hermes-vllm.service
  echo "Installed readiness gating and enabled hermes-vllm.service (not started)"
fi
