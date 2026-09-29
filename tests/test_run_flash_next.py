# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Check the 4-bit GGUF launcher before it can replace the running service."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


LAUNCHER = Path(__file__).resolve().parent.parent / "local-model" / "run_flash_next.sh"
PREFIX = "Qwen3.8-Flash-Next-UD-IQ4_XS"


def test_launcher_requires_every_shard(tmp_path: Path) -> None:
    (tmp_path / f"{PREFIX}-00001-of-00003.gguf").write_bytes(b"GGUF")
    result = subprocess.run(
        ["bash", str(LAUNCHER)],
        env={**os.environ, "HERMES_FLASH_NEXT_DIR": str(tmp_path)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "00002-of-00003.gguf" in result.stderr


def test_launcher_uses_two_64k_slots_and_ram_resident_ngram(tmp_path: Path) -> None:
    for shard in range(1, 4):
        (tmp_path / f"{PREFIX}-{shard:05d}-of-00003.gguf").write_bytes(b"GGUF")
    fake_server = tmp_path / "llama-server"
    fake_server.write_text("#!/bin/sh\nexit 0\n")
    fake_server.chmod(0o755)
    projector = tmp_path / "mmproj-F16.gguf"
    projector.write_bytes(b"GGUF")
    result = subprocess.run(
        ["bash", str(LAUNCHER)],
        env={
            **os.environ,
            "HERMES_FLASH_NEXT_DIR": str(tmp_path),
            "HERMES_FLASH_NEXT_MMPROJ": str(projector),
            "HERMES_LLAMA_SERVER_BIN": str(fake_server),
            "HERMES_MODEL_DRY_RUN": "1",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--alias Qwen3.8-Flash-Next-UD-IQ4_XS" in result.stdout
    assert f"--mmproj {projector}" in result.stdout
    assert "--ctx-size 131072" in result.stdout
    assert "--parallel 2" in result.stdout
    assert "--gpu-layers auto" in result.stdout
    assert "--lazy-mode off" in result.stdout
    assert "--host 127.0.0.1" in result.stdout
