# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Validate the vLLM service restart helper and its documented interface."""
from __future__ import annotations

import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
RESTARTER = REPO / "local-model" / "restart_service.sh"


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
