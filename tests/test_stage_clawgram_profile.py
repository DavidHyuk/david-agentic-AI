# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for isolated ClawGram Hermes profile staging."""

from pathlib import Path
import stat

import stage_clawgram_profile


REPO = Path(__file__).resolve().parent.parent


def test_profile_stage_isolated_from_default_agent(tmp_path) -> None:
    profile_home = tmp_path / "hermes" / "profiles" / "clawgram"
    default_home = tmp_path / "hermes"
    legacy = default_home / "skills" / "personal" / "family-letter"
    legacy.mkdir(parents=True)
    (legacy / "SKILL.md").write_text("legacy")

    report = stage_clawgram_profile.stage_profile(
        profile_home,
        cleanup_default_home=default_home,
    )

    assert report["removed_legacy_skill"] is True
    assert not legacy.exists()
    assert (profile_home / "SOUL.md").exists()
    assert (profile_home / "memories" / "MEMORY.md").exists()
    assert (profile_home / "skills" / "personal" / "family-letter" / "SKILL.md").exists()
    assert (profile_home / "config.yaml").exists()
    assert "OPENAI_API_KEY=sk-local-no-key-required" in (
        profile_home / ".env"
    ).read_text()
    assert stat.S_IMODE((profile_home / ".env").stat().st_mode) == 0o600


def test_profile_stage_preserves_existing_telegram_token(tmp_path) -> None:
    profile_home = tmp_path / "clawgram"
    profile_home.mkdir()
    (profile_home / ".env").write_text("TELEGRAM_BOT_TOKEN=private-test-value\n")

    stage_clawgram_profile.stage_profile(profile_home)

    content = (profile_home / ".env").read_text()
    assert "TELEGRAM_BOT_TOKEN=private-test-value" in content
    assert content.count("OPENAI_API_KEY=sk-local-no-key-required") == 1


def test_profile_memory_seeds_respect_hermes_limits() -> None:
    memory = (
        REPO / "profiles" / "clawgram" / "config" / "memory" / "MEMORY.md"
    ).read_text()
    user = (
        REPO / "profiles" / "clawgram" / "config" / "memory" / "USER.md"
    ).read_text()

    assert len(memory) <= 2200
    assert len(user) <= 1375
