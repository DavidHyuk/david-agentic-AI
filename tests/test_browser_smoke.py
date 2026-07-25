# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Unit tests for the deterministic Hermes browser smoke-test helpers."""

import json

import pytest

import browser_smoke


def test_parse_version():
    assert browser_smoke.parse_version("agent-browser 0.33.0\n") == "0.33.0"


def test_parse_version_rejects_unexpected_output():
    with pytest.raises(ValueError, match="unexpected"):
        browser_smoke.parse_version("0.33.0")


def test_validate_result():
    payload = browser_smoke.validate_result(
        json.dumps({"success": True, "data": "READY"}),
        "get text",
    )
    assert payload["data"] == "READY"


def test_validate_result_rejects_failure():
    with pytest.raises(ValueError, match="failed"):
        browser_smoke.validate_result(
            json.dumps({"success": False, "error": "boom"}),
            "click",
        )


def test_result_field_reads_metadata_wrapped_value():
    payload = {
        "success": True,
        "data": {"lifecycle": {"reused": True}, "text": "READY"},
    }
    assert browser_smoke.result_field(payload, "text") == "READY"


def test_result_field_rejects_missing_value():
    with pytest.raises(ValueError, match="has no"):
        browser_smoke.result_field({"success": True, "data": {}}, "title")
