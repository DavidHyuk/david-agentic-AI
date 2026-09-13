# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for isolated English podcast profile staging."""
from pathlib import Path

import yaml

import stage_english_podcast_profile


def test_stage_profile_includes_only_podcast_assets(tmp_path: Path) -> None:
    profile_home = tmp_path / "hermes" / "profiles" / "english-podcast"
    report = stage_english_podcast_profile.stage_profile(profile_home)

    assert report["skills"] == ["learning/english-podcast-coach"]
    assert "english_podcast.py" in report["scripts"]
    assert "english_srs.py" in report["scripts"]
    assert (profile_home / "SOUL.md").exists()
    assert (
        profile_home
        / "skills"
        / "learning"
        / "english-podcast-coach"
        / "SKILL.md"
    ).exists()
    environment = (profile_home / ".env").read_text()
    assert "TELEGRAM_BOT_TOKEN" not in environment
    assert "ENGLISH_PODCAST_DATA_DIR=" in environment
    assert "ENGLISH_DECK_PATH=" in environment
    assert "ENGLISH_TUTOR_PROFILE_HOME=" in environment
    assert "ENGLISH_PODCAST_YT_DLP=" in environment
    config = yaml.safe_load((profile_home / "config.yaml").read_text())
    assert config["skills"]["creation_nudge_interval"] == 0
    assert config["curator"]["enabled"] is False


def test_stage_profile_preserves_secret_and_removes_unmanaged_skill(tmp_path: Path) -> None:
    profile_home = tmp_path / "hermes" / "profiles" / "english-podcast"
    profile_home.mkdir(parents=True)
    (profile_home / ".env").write_text("TELEGRAM_BOT_TOKEN=kept\n")
    generated = profile_home / "skills" / "generated"
    generated.mkdir(parents=True)
    (generated / "SKILL.md").write_text("generated")

    report = stage_english_podcast_profile.stage_profile(profile_home)

    assert report["removed_unmanaged_skills"] == ["generated"]
    assert "TELEGRAM_BOT_TOKEN=kept" in (profile_home / ".env").read_text()
    assert not generated.exists()
