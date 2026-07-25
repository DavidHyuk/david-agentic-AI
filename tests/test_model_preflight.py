# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for local-model/model_preflight.py checkpoint validation."""

import json

import pytest

import model_preflight as mp


def _checkpoint(tmp_path, *, quantization="fp8", context_length=262_144):
    model = tmp_path / "model"
    model.mkdir()
    (model / "config.json").write_text(
        json.dumps(
            {
                "model_type": "qwen3_5_moe",
                "architectures": ["Qwen3_5MoeForConditionalGeneration"],
                "text_config": {"max_position_embeddings": context_length},
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


def test_validate_qwen36_fp8_checkpoint(tmp_path):
    metadata = mp.validate_checkpoint(
        _checkpoint(tmp_path),
        expected_quantization="fp8",
        min_context_length=131_072,
    )
    assert metadata["quantization"] == "fp8"
    assert metadata["context_length"] == 262_144
    assert metadata["weight_files"] == 1


def test_rejects_quantization_mismatch(tmp_path):
    with pytest.raises(ValueError, match="quantization mismatch"):
        mp.validate_checkpoint(
            _checkpoint(tmp_path, quantization="awq"),
            expected_quantization="fp8",
        )


def test_rejects_context_shorter_than_requested(tmp_path):
    with pytest.raises(ValueError, match="below the requested"):
        mp.validate_checkpoint(
            _checkpoint(tmp_path, context_length=65_536),
            expected_quantization="fp8",
            min_context_length=131_072,
        )


def test_rejects_missing_weight_files(tmp_path):
    model = _checkpoint(tmp_path)
    (model / "layers-0.safetensors").unlink()
    with pytest.raises(ValueError, match="no safetensors"):
        mp.validate_checkpoint(model, expected_quantization="fp8")
