# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for isolated English profile staging."""
from pathlib import Path

import stage_english_profile


def test_stage_profile_includes_only_english_assets(tmp_path: Path) -> None:
    profile_home = tmp_path / "hermes" / "profiles" / "english"
    report = stage_english_profile.stage_profile(profile_home)

    assert report["skills"] == ["learning/english-practice"]
    assert "english_intake.py" in report["scripts"]
    assert (profile_home / "SOUL.md").exists()
    assert (profile_home / "skills" / "learning" / "english-practice" / "SKILL.md").exists()
    assert not (profile_home / "data" / "clawgram").exists()
    environment = (profile_home / ".env").read_text()
    assert "TELEGRAM_BOT_TOKEN" not in environment
    assert "ENGLISH_LESSONS_DIR=" in environment
    assert "ENGLISH_STATE_PATH=" in environment
    assert "ENGLISH_DECK_PATH=" in environment


def test_stage_profile_removes_legacy_default_english_skill(tmp_path: Path) -> None:
    profile_home = tmp_path / "hermes" / "profiles" / "english"
    default_home = tmp_path / "hermes"
    legacy = default_home / "skills" / "learning" / "english-practice"
    legacy.mkdir(parents=True)

    report = stage_english_profile.stage_profile(
        profile_home, cleanup_default_home=default_home
    )

    assert report["removed_legacy_skill"] is True
    assert not legacy.exists()
