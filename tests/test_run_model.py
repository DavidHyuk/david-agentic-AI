# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Black-box tests for the Qwen3.6 FP8 vLLM launcher command."""

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER = REPO_ROOT / "local-model" / "run_model.sh"


def _checkpoint(tmp_path, quantization="fp8"):
    model = tmp_path / "Qwen3.6-35B-A3B-FP8"
    model.mkdir()
    (model / "config.json").write_text(
        json.dumps(
            {
                "model_type": "qwen3_5_moe",
                "text_config": {"max_position_embeddings": 262_144},
                "quantization_config": {
                    "quant_method": quantization,
                    "fmt": "e4m3",
                },
            }
        )
    )
    (model / "tokenizer_config.json").write_text("{}")
    (model / "layers-0.safetensors").write_bytes(b"weights")
    return model


def _run(model):
    env = {
        **os.environ,
        "HERMES_MODEL_PATH": str(model),
        "HERMES_VLLM_BIN": "/usr/bin/true",
        "HERMES_VLLM_DRY_RUN": "1",
    }
    return subprocess.run(
        ["bash", str(RUNNER), "qwen36"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_qwen36_uses_fp8_compatible_vllm_flags(tmp_path):
    result = _run(_checkpoint(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "--served-model-name Qwen3.6-35B-A3B-FP8" in result.stdout
    assert "--max-model-len 131072" in result.stdout
    assert "--kv-cache-dtype auto" in result.stdout
    assert "--reasoning-parser qwen3" in result.stdout
    assert "--tool-call-parser qwen3_coder" in result.stdout
    assert "--quantization" not in result.stdout


def test_qwen36_rejects_awq_checkpoint(tmp_path):
    result = _run(_checkpoint(tmp_path, quantization="awq"))
    assert result.returncode == 1
    assert "quantization mismatch" in result.stdout
