#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
#
# Create an isolated CUDA-compatible vLLM runtime for the DGX Spark.
# The host base environment is intentionally left untouched.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${HERMES_VLLM_VENV:-${SCRIPT_DIR}/.venv}"
PYTHON_BIN="${HERMES_VLLM_PYTHON:-python3.12}"
VLLM_VERSION="${HERMES_VLLM_VERSION:-0.19.0}"
CUDA_VARIANT="${HERMES_VLLM_CUDA_VARIANT:-130}"
CPU_ARCH="$(uname -m)"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is required. Install it before creating the vLLM runtime." >&2
  exit 1
fi

if [ ! -x "${VENV_DIR}/bin/python" ]; then
  echo "Creating vLLM environment at ${VENV_DIR}"
  uv venv --python "${PYTHON_BIN}" --seed "${VENV_DIR}"
fi

VLLM_WHEEL_URL="${HERMES_VLLM_WHEEL_URL:-https://github.com/vllm-project/vllm/releases/download/v${VLLM_VERSION}/vllm-${VLLM_VERSION}%2Bcu${CUDA_VARIANT}-cp38-abi3-manylinux_2_35_${CPU_ARCH}.whl}"

echo "Installing vLLM ${VLLM_VERSION}+cu${CUDA_VARIANT} for ${CPU_ARCH}"
uv pip install \
  --python "${VENV_DIR}/bin/python" \
  "${VLLM_WHEEL_URL}" \
  --torch-backend="cu${CUDA_VARIANT}"

"${VENV_DIR}/bin/python" - <<'PY'
import torch
import vllm

if torch.version.cuda is None:
    raise SystemExit("ERROR: the isolated environment installed a CPU-only PyTorch build")
if not torch.cuda.is_available():
    raise SystemExit("ERROR: PyTorch cannot access the DGX Spark GPU")

probe = torch.ones(1, device="cuda")
if probe.item() != 1:
    raise SystemExit("ERROR: CUDA tensor smoke test returned an unexpected value")

print(f"vLLM Python package: vllm={vllm.__version__}")
print(f"PyTorch runtime: torch={torch.__version__} cuda={torch.version.cuda}")
print(f"GPU: {torch.cuda.get_device_name(0)}")
PY

"${VENV_DIR}/bin/vllm" --version
echo "vLLM CUDA extension import: OK"
echo "Next: bash local-model/run_model.sh qwen36"
