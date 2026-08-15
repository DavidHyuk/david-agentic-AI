# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Validate the vLLM service restart helper and its documented interface."""
from __future__ import annotations

import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
RESTARTER = REPO / "local-model" / "restart_service.sh"
INSTALLER = REPO / "local-model" / "install_service.sh"
GATEWAY_DROPIN = REPO / "local-model" / "hermes-gateway-vllm.conf"
VLLM_UNIT = REPO / "local-model" / "hermes-vllm.service"


def test_restart_helper_exposes_safe_service_controls():
    text = RESTARTER.read_text()

    assert "systemctl --user restart" in text
    assert "systemctl --user is-active --quiet" in text
    assert '"${API_URL}/models"' in text
    assert "--wait" in text
    assert "--timeout" in text
    assert 'GPU_UTIL="0.50"' in text
    assert "--gpu-util" in text
    assert "Environment=HERMES_VLLM_GPU_UTIL=%s" in text
    assert "systemctl --user daemon-reload" in text
    assert "HERMES_VLLM_SERVICE" in text
    assert "HERMES_VLLM_API_URL" in text


def test_restart_helper_help_is_available_without_restarting_service():
    result = subprocess.run(
        ["bash", str(RESTARTER), "--help"],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Usage: bash local-model/restart_service.sh" in result.stdout
    assert result.stderr == ""


def test_gateway_dropin_waits_for_expected_vllm_model():
    text = GATEWAY_DROPIN.read_text()

    assert "Requires=hermes-vllm.service" in text
    assert "After=hermes-vllm.service" in text
    assert "wait_for_vllm.py" in text
    assert "--expected-model Qwen3.6-35B-A3B-FP8" in text
    assert "TimeoutStartSec=930" in text


def test_vllm_installer_deploys_gateway_readiness_assets():
    text = INSTALLER.read_text()

    assert "20-vllm-readiness.conf" in text
    assert "scripts/wait_for_vllm.py" in text
    assert "systemctl --user restart hermes-gateway.service" in text


def test_vllm_unit_uses_the_renamed_checkout() -> None:
    text = VLLM_UNIT.read_text()

    assert "%h/workspace/David-Agent" in text
    assert "%h/workspace/david-agentic-ai" not in text


def test_restart_helper_rejects_an_invalid_gpu_util_before_touching_service():
    result = subprocess.run(
        ["bash", str(RESTARTER), "1.1"],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "GPU_UTIL must be a number in (0, 1]." in result.stderr
