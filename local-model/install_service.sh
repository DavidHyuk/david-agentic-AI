#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
#
# Install and optionally start the Qwen3.6 vLLM user service.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_SOURCE="${SCRIPT_DIR}/hermes-vllm.service"
UNIT_TARGET="${HOME}/.config/systemd/user/hermes-vllm.service"
START_SERVICE=1

if [ "${1:-}" = "--no-start" ]; then
  START_SERVICE=0
elif [ "$#" -gt 0 ]; then
  echo "Usage: $0 [--no-start]" >&2
  exit 2
fi

install -D -m 0644 "${UNIT_SOURCE}" "${UNIT_TARGET}"
systemctl --user daemon-reload

if [ "${START_SERVICE}" = "1" ]; then
  systemctl --user enable --now hermes-vllm.service
  echo "Installed and started hermes-vllm.service"
  echo "Follow startup: journalctl --user -u hermes-vllm.service -f"
else
  systemctl --user enable hermes-vllm.service
  echo "Installed and enabled hermes-vllm.service (not started)"
fi
