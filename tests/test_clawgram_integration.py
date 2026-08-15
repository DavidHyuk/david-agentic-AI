# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Validate ClawGram MCP registration and independent systemd wiring."""

from __future__ import annotations

import stat
from pathlib import Path

import yaml

import setup_clawgram as setup

REPO = Path(__file__).resolve().parent.parent
SERVICE = REPO / "bootstrap" / "clawgram-family-letter.service"
TIMER = REPO / "bootstrap" / "clawgram-family-letter.timer"
WORKER = REPO / "bootstrap" / "clawgram-worker.service"
INSTALLER = REPO / "bootstrap" / "install_clawgram_integration.sh"


def test_template_exposes_control_tools_without_approval_authority() -> None:
    template = setup.load_template()
    tools = tuple(template["tools"]["include"])

    assert tools == setup.ALLOWED_TOOLS
    assert not setup.FORBIDDEN_AUTHORITY.intersection(tools)


def test_server_config_is_cwd_independent_and_uses_one_database(tmp_path) -> None:
    root = tmp_path / "ClawGram"
    python = tmp_path / "env" / "bin" / "python"
    config = setup.build_server_config(
        setup.load_template(),
        clawgram_root=root,
        python_path=python,
    )

    assert config["command"] == str(python.resolve())
    assert config["args"] == ["-m", "clawgram.mcp_server"]
    assert config["env"]["PYTHONPATH"] == str(root.resolve())
    assert config["env"]["CLAWGRAM_DATABASE_PATH"].endswith(
        "/ClawGram/data/clawgram-v2.sqlite3"
    )


def test_write_runtime_config_preserves_other_servers_and_secures_file(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("mcp_servers:\n  existing:\n    url: https://example.com/mcp\n")
    server = setup.build_server_config(
        setup.load_template(),
        clawgram_root=tmp_path / "ClawGram",
        python_path=tmp_path / "python",
    )

    setup.write_runtime_config(config_path, server)
    payload = yaml.safe_load(config_path.read_text())

    assert payload["mcp_servers"]["existing"]["url"] == "https://example.com/mcp"
    assert payload["mcp_servers"]["clawgram"] == server
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


def test_timer_is_weekly_with_biweekly_gate_and_not_hermes_cron() -> None:
    service = SERVICE.read_text()
    timer = TIMER.read_text()

    assert "python -m clawgram.scheduler --minimum-gap-days 13" in service
    assert "start --no-block clawgram-worker.service" in service
    assert "OnCalendar=Sat *-*-* 02:00:00" in timer
    assert "Persistent=true" in timer


def test_worker_is_low_priority_and_refuses_implicit_backend_configuration() -> None:
    worker = WORKER.read_text()

    assert "EnvironmentFile=-%h/.config/clawgram/worker.env" in worker
    assert "Nice=10" in worker
    assert "CPUWeight=20" in worker
    assert "IOWeight=20" in worker
    assert "python -m clawgram.worker" in worker


def test_installer_keeps_timer_disabled_until_backend_is_explicit() -> None:
    text = INSTALLER.read_text()

    assert "--enable-timer" in text
    assert "CLAWGRAM_ASSESSMENT_URL" in text
    assert "disable --now clawgram-family-letter.timer" in text
    assert "bootstrap/stage.py" in text
    assert "setup_clawgram.py" in text
