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


def test_watch_history_installer_and_cron_use_explicit_playwright_environment():
    import yaml
    installer = (REPO / 'bootstrap/install_youtube_history.sh').read_text()
    english_installer = (REPO / 'bootstrap/install_english_bot.sh').read_text()
    jobs = yaml.safe_load((REPO / 'cron/jobs.yaml').read_text())['jobs']
    job = next(job for job in jobs if job['name'] == 'english-podcast-daily')
    assert '.hermes/venvs/youtube-history' in installer
    assert 'playwright>=1.55,<2' in installer
    assert 'from playwright.sync_api import sync_playwright' in installer
    assert 'install_youtube_history.sh' in english_installer
    assert '/home/david/.hermes/venvs/youtube-history/bin/python' in job['prompt']
    assert 'Run python3' not in job['prompt']
