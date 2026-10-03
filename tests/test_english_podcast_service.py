# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Validate English podcast transcript prefetch service wiring."""
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def test_legacy_transcript_timer_is_disabled_for_evening_history() -> None:
    service = (REPO / "bootstrap/hermes-english-podcast-sync.service").read_text()
    timer = (REPO / "bootstrap/hermes-english-podcast-sync.timer").read_text()
    installer = (REPO / "bootstrap/install_english_bot.sh").read_text()

    assert "english_podcast.py prepare" in service
    assert "%h/.hermes/profiles/english/scripts/english_podcast.py" in service
    assert "ENGLISH_PODCAST_YT_DLP=%h/.local/bin/yt-dlp" in service
    assert "ReadWritePaths=%h/.hermes/data/english-podcast" in service
    assert "OnCalendar=*-*-* 08:25:00" in timer
    assert "Persistent=true" in timer
    assert "disable --now hermes-english-podcast-sync.timer" in installer
    assert "enable --now hermes-english-podcast-sync.timer" not in installer
    assert "stage_english_profile.py" in installer
