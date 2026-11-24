#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Run the shared Flash-Next FP4-Local model using the pinned Strata runtime."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

MODEL_NAME = "Qwen3.8-Flash-Next-FP4-Local"
MODEL_ALIAS = "Qwen3.8-Flash-Next-UD-IQ4_XS"
CONTEXT = 131072
SLOTS = 2


def strata_config(runtime: Path, weights: Path, projector: Path) -> dict:
    control = runtime / "strata-0.1.68"
    engine = runtime / "engine-0.1.67"
    dense = weights / "dense.gguf"
    pack = weights / "pack"
    return {
        "exe": str(engine / "strata"),
        "cwd": str(control),
        "lib_dirs": [str(engine)],
        "log": str(runtime / "engine.log"),
        "backend": "cuda",
        "arch": "qwen4exp",
        "model_name": MODEL_NAME,
        "aliases": [MODEL_ALIAS],
        "strict_model": True,
        "tokenizer": str(pack / "tokenizer"),
        "parallel": SLOTS,
        "engine_ready_s": 360,
        "drafting": "mtp",
        "args": [
            "--pack", str(pack),
            "--native", str(dense),
            "--native-dense-gguf", str(dense),
            "--ple-gguf", str(weights / "ple-nvfp4.gguf"),
            "--expert-profile", str(control / "data/expert-profile.bin"),
            "--mtp", str(weights / "mtp/rt"),
            "--spec", "2",
            "--batch-mtp",
            "--max-context", str(CONTEXT),
            "--prefill", "auto:8192",
            "--kv", "int8",
            "--mmap-experts",
            "--expert-cache", "auto",
            "--vram-reserve-mib", "8192",
            "--ram-keep-gib", "12",
            "--vision",
        ],
        "vision": {
            "exe": str(engine / "strata-vision"),
            "mmproj": str(projector),
            "model": str(dense),
            "gpu": True,
            "max_tokens": 1024,
        },
    }


def main() -> None:
    home = Path.home()
    models = home / "workspace/models"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=home / ".local/share/hermes-nvfp4")
    parser.add_argument("--weights", type=Path, default=models / "nvidia" / f"{MODEL_NAME}-Strata")
    parser.add_argument("--projector", type=Path,
                        default=models / "unsloth/Qwen3.8-Flash-Next-GGUF/mmproj-F16.gguf")
    parser.add_argument("--port", type=int, default=8004)
    args = parser.parse_args()

    runtime, weights = args.runtime.resolve(), args.weights.resolve()
    config = strata_config(runtime, weights, args.projector.resolve())
    control = Path(config["cwd"])
    python = runtime / "venv/bin/python"
    required_files = [
        python, Path(config["exe"]), control / "serve/server.py",
        Path(config["vision"]["exe"]), Path(config["vision"]["mmproj"]),
        *(weights / name for name in ("ple-nvfp4.gguf.done", "dense.gguf.done", "pack.done", "draft.done")),
    ]
    missing = [str(path) for path in required_files if not path.is_file()]
    if missing:
        parser.exit(78, "Missing Strata runtime or prepared model files:\n" + "\n".join(missing) + "\n")

    config_path = runtime / f"serve-{args.port}.json"
    with NamedTemporaryFile(dir=runtime, mode="w", encoding="utf-8", delete=False) as output:
        json.dump(config, output)
    Path(output.name).replace(config_path)
    os.chdir(control)
    os.execv(python, [str(python), "-m", "serve.server", "--engine", "strata",
                      "--config", str(config_path), "--host", "127.0.0.1", "--port", str(args.port)])


if __name__ == "__main__":
    main()
