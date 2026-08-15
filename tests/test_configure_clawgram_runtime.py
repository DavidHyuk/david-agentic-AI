# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for secret-safe ClawGram runtime configuration."""

import stat

import pytest

from configure_clawgram_runtime import build_environment, configure


def test_runtime_environment_is_private_and_complete(tmp_path):
    path = configure(tmp_path / "clawgram" / "worker.env", "https://spark.example.ts.net")
    content = path.read_text()

    assert "CLAWGRAM_ASSESSMENT_URL=http://127.0.0.1:8010/v1/assessments" in content
    assert "CLAWGRAM_REVIEW_BASE_URL=https://spark.example.ts.net" in content
    assert "CLAWGRAM_GOOGLE_PHOTOS_MAX_CANDIDATES=750" in content
    assert "CLAWGRAM_SOURCE_KEY=" in content
    assert "CLAWGRAM_VLM_MODEL=Qwen3.6-35B-A3B-FP8" in content
    assert "CLAWGRAM_GOOGLE_PHOTOS_CDP_URL=http://127.0.0.1:19223" in content
    assert "CLAWGRAM_GOOGLE_PHOTOS_TIMEZONE=America/Los_Angeles" in content
    assert "CLAWGRAM_HERMES_PROFILE=clawgram" in content
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_runtime_environment_requires_https_and_does_not_overwrite(tmp_path):
    with pytest.raises(ValueError, match="HTTPS"):
        build_environment("http://phone.local")
    path = tmp_path / "worker.env"
    configure(path, "https://spark.example.ts.net")
    with pytest.raises(FileExistsError):
        configure(path, "https://spark.example.ts.net")
