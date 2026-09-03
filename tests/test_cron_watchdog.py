# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Validate the automatic Hermes cron recovery service and installer."""
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
SERVICE = REPO / "bootstrap" / "hermes-cron-watchdog.service"
TIMER = REPO / "bootstrap" / "hermes-cron-watchdog.timer"
DROPIN = REPO / "bootstrap" / "hermes-gateway-cron-recovery.conf"
INSTALLER = REPO / "bootstrap" / "install_cron_watchdog.sh"


def test_watchdog_checks_frequently_and_recovers_stale_locks():
    service = SERVICE.read_text()
    timer = TIMER.read_text()

    assert "cron_health.py --lock-stale-minutes 20 --restart" in service
    assert "--hermes-home %h/.hermes/profiles/english" in service
    assert "--gateway-service hermes-gateway-english.service" in service
    assert "--skip-missing-home" in service
    assert "TimeoutStartSec=180" in service
    assert "OnBootSec=5min" in timer
    assert "OnUnitActiveSec=5min" in timer


def test_gateway_shutdown_is_bounded_for_stuck_workers():
    assert "TimeoutStopSec=45" in DROPIN.read_text()


def test_installer_stages_script_and_enables_watchdog():
    text = INSTALLER.read_text()

    assert "bootstrap/stage.py" in text
    assert "30-cron-recovery.conf" in text
    assert "enable --now hermes-cron-watchdog.timer" in text
    assert "start hermes-cron-watchdog.service" in text
