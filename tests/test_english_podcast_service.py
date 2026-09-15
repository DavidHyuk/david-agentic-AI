# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Validate English podcast transcript prefetch service wiring."""
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def test_transcript_sync_runs_before_daily_coaching() -> None:
    service = (REPO / "bootstrap/hermes-english-podcast-sync.service").read_text()
    timer = (REPO / "bootstrap/hermes-english-podcast-sync.timer").read_text()
    installer = (REPO / "bootstrap/install_english_bot.sh").read_text()

    assert "english_podcast.py prepare" in service
    assert "%h/.hermes/profiles/english/scripts/english_podcast.py" in service
    assert "ENGLISH_PODCAST_YT_DLP=%h/.local/bin/yt-dlp" in service
    assert "ReadWritePaths=%h/.hermes/data/english-podcast" in service
    assert "OnCalendar=*-*-* 08:25:00" in timer
    assert "Persistent=true" in timer
    assert "enable --now hermes-english-podcast-sync.timer" in installer
    assert "stage_english_profile.py" in installer
