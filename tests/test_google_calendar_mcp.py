# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for the official Google Calendar MCP setup and smoke helpers."""
import json
import stat

import pytest
import yaml

import calendar_smoke
import setup_google_calendar as setup


def _credentials(redirects=None):
    return {
        "web": {
            "client_id": "client.apps.googleusercontent.com",
            "client_secret": "secret",
            "redirect_uris": redirects or [setup.CALLBACK_URI],
        }
    }


def test_load_web_credentials(tmp_path):
    path = tmp_path / "client.json"
    path.write_text(json.dumps(_credentials()))
    assert setup.load_web_credentials(path) == {
        "client_id": "client.apps.googleusercontent.com",
        "client_secret": "secret",
    }


def test_load_web_credentials_rejects_desktop_client(tmp_path):
    path = tmp_path / "client.json"
    path.write_text(json.dumps({"installed": _credentials()["web"]}))
    with pytest.raises(ValueError, match="Web application"):
        setup.load_web_credentials(path)


def test_load_web_credentials_requires_callback(tmp_path):
    path = tmp_path / "client.json"
    path.write_text(json.dumps(_credentials(["http://localhost:9999/callback"])))
    with pytest.raises(ValueError, match="redirect URI"):
        setup.load_web_credentials(path)


def test_load_web_credentials_rejects_invalid_redirect_shape(tmp_path):
    payload = _credentials()
    payload["web"]["redirect_uris"] = "not-a-list"
    path = tmp_path / "client.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="must be a list"):
        setup.load_web_credentials(path)


def test_template_is_read_only():
    template = setup.load_template()
    assert template["url"] == setup.SERVER_URL
    assert tuple(template["tools"]["include"]) == setup.READ_ONLY_TOOLS
    assert "create_event" not in template["tools"]["include"]


def test_build_server_config_injects_credentials_without_mutating_template():
    template = setup.load_template()
    server = setup.build_server_config(
        template,
        {"client_id": "id", "client_secret": "secret"},
    )
    assert server["oauth"]["client_id"] == "id"
    assert "client_id" not in template["oauth"]
    assert "name" not in server


def test_write_runtime_config_preserves_unrelated_settings_and_secures_file(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("model:\n  provider: existing\n")
    server = setup.build_server_config(
        setup.load_template(),
        {"client_id": "id", "client_secret": "secret"},
    )
    setup.write_runtime_config(config, server)
    payload = yaml.safe_load(config.read_text())
    assert payload["model"]["provider"] == "existing"
    assert payload["mcp_servers"]["google-calendar"]["url"] == setup.SERVER_URL
    assert stat.S_IMODE(config.stat().st_mode) == 0o600


def test_validate_runtime_config_reports_missing_config(tmp_path):
    problems = setup.validate_runtime_config(tmp_path / "missing.yaml")
    assert problems and "cannot read" in problems[0]


def test_write_runtime_config_rejects_invalid_mcp_block(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("mcp_servers: invalid\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        setup.write_runtime_config(config, {})


def test_smoke_output_recognition():
    assert calendar_smoke.connection_is_healthy(
        "Connected (123ms)\nTools discovered: 3"
    )
    assert not calendar_smoke.connection_is_healthy("Connection failed")
    assert calendar_smoke.e2e_is_healthy("HERMES_CALENDAR_OK\n")
    assert not calendar_smoke.e2e_is_healthy("calendar details")
