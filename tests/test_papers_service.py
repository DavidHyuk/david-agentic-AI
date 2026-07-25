# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Validate the paper-ingestion systemd unit and installation wiring."""
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
SERVICE = REPO / "bootstrap" / "hermes-papers-ingest.service"
TIMER = REPO / "bootstrap" / "hermes-papers-ingest.timer"
INSTALLER = REPO / "bootstrap" / "install_papers_service.sh"


def test_service_runs_staged_script_and_writes_only_runtime_catalog():
    text = SERVICE.read_text()
    assert "%h/.hermes/scripts/papers_ingest.py" in text
    assert "%h/.hermes/data/papers/papers.db" in text
    assert "ProtectSystem=strict" in text
    assert "ProtectHome=read-only" in text
    assert "ReadWritePaths=%h/.hermes/data/papers" in text
    assert "ExecStart=hermes " not in text


def test_timer_runs_before_digest_and_survives_downtime():
    text = TIMER.read_text()
    assert "OnCalendar=*-*-* 08:00:00" in text
    assert "Persistent=true" in text


def test_installer_enables_timer_and_runs_initial_ingestion():
    text = INSTALLER.read_text()
    assert 'install -d -m 0700 "$HERMES_RUNTIME_HOME/data/papers"' in text
    assert "enable --now hermes-papers-ingest.timer" in text
    assert "start hermes-papers-ingest.service" in text
    assert "papers_ingest.py" in text
