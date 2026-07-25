#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Validate a local model checkpoint before handing it to vLLM.

The launcher uses this dependency-free check to catch a wrong checkpoint,
quantization mismatch, missing tokenizer, or undersized context before vLLM
allocates unified GPU memory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def load_metadata(model_path: Path) -> dict[str, Any]:
    """Load and normalize the checkpoint metadata needed by the launcher."""
    config_path = model_path / "config.json"
    if not config_path.is_file():
        raise ValueError(f"{config_path} not found")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {config_path}: {exc}") from exc

    text_config = config.get("text_config") or {}
    quantization = config.get("quantization_config") or {}
    context_length = (
        text_config.get("max_position_embeddings")
        or config.get("max_position_embeddings")
        or 0
    )
    return {
        "model_type": config.get("model_type") or "",
        "architectures": config.get("architectures") or [],
        "quantization": str(quantization.get("quant_method") or "").lower(),
        "quantization_format": quantization.get("fmt") or "",
        "context_length": int(context_length),
    }


def validate_checkpoint(
    model_path: Path,
    *,
    expected_quantization: str | None = None,
    min_context_length: int = 65_536,
) -> dict[str, Any]:
    """Validate files and model properties, returning normalized metadata."""
    if not model_path.is_dir():
        raise ValueError(f"model directory not found: {model_path}")

    metadata = load_metadata(model_path)
    actual_quantization = metadata["quantization"]
    if expected_quantization:
        expected = expected_quantization.lower()
        if actual_quantization != expected:
            raise ValueError(
                "quantization mismatch: "
                f"checkpoint={actual_quantization or 'unquantized'}, expected={expected}"
            )

    context_length = metadata["context_length"]
    if context_length < min_context_length:
        raise ValueError(
            f"checkpoint context length {context_length:,} is below "
            f"the requested {min_context_length:,}"
        )

    if not (model_path / "tokenizer_config.json").is_file():
        raise ValueError(f"{model_path / 'tokenizer_config.json'} not found")

    weight_files = list(model_path.glob("*.safetensors"))
    if not weight_files:
        raise ValueError(f"no safetensors weights found in {model_path}")
    if any(weight.stat().st_size == 0 for weight in weight_files):
        raise ValueError(f"empty safetensors weight found in {model_path}")

    metadata["weight_files"] = len(weight_files)
    return metadata


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_path", type=Path)
    parser.add_argument("--expected-quantization")
    parser.add_argument("--min-context-length", type=int, default=65_536)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        metadata = validate_checkpoint(
            args.model_path.expanduser().resolve(),
            expected_quantization=args.expected_quantization,
            min_context_length=args.min_context_length,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(
        "Model preflight OK:"
        f" type={metadata['model_type'] or 'unknown'}"
        f" quantization={metadata['quantization'] or 'none'}"
        f" format={metadata['quantization_format'] or 'default'}"
        f" context={metadata['context_length']:,}"
        f" weight_files={metadata['weight_files']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
