# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for Kakao i Open Builder request parsing and safe feedback queuing."""
from datetime import datetime
import json
from pathlib import Path
import threading
import urllib.request

import pytest

import kakao_webhook as kw


REPO = Path(__file__).resolve().parent.parent


def payload(text="Please say 'I agree', not 'I am agree.'", user_id="teacher-1"):
    return {"userRequest": {"utterance": text, "user": {"id": user_id}}}


def test_extract_feedback_reads_kakao_utterance_and_user():
    assert kw.extract_feedback(payload()) == ("Please say 'I agree', not 'I am agree.'", "teacher-1")


def test_extract_feedback_rejects_missing_or_empty_text():
    with pytest.raises(ValueError):
        kw.extract_feedback({})
    with pytest.raises(ValueError):
        kw.extract_feedback(payload("   "))


def test_process_payload_saves_correction_in_date_session(tmp_path):
    response, saved, sender = kw.process_payload(
        payload(), str(tmp_path), {"teacher-1"}, datetime(2026, 7, 25, 13, 1, 2, 3)
    )
    assert sender == "teacher-1"
    assert saved == tmp_path / "2026-07-25" / "kakaotalk-feedback-130102000003.txt"
    assert saved.read_text(encoding="utf-8").startswith("Please say")
    assert response["version"] == "2.0"
    assert "저장" in response["template"]["outputs"][0]["simpleText"]["text"]


def test_process_payload_ignores_unapproved_sender(tmp_path):
    response, saved, sender = kw.process_payload(payload(user_id="stranger"), str(tmp_path), {"teacher-1"})
    assert sender == "stranger"
    assert saved is None
    assert "등록된" in response["template"]["outputs"][0]["simpleText"]["text"]
    assert list(tmp_path.iterdir()) == []


def test_allowed_user_ids_and_path_generation():
    assert kw.allowed_user_ids(" teacher-1, teacher-2 ,, ") == {"teacher-1", "teacher-2"}
    assert kw.generate_endpoint_path().startswith("/kakao/")


def test_record_sender_is_private_and_returns_only_fingerprint(tmp_path):
    state_path = tmp_path / "private" / "senders.json"
    fingerprint = kw.record_sender(
        "teacher-secret-id", str(state_path), datetime(2026, 7, 25, 13, 0, 0)
    )
    assert fingerprint != "teacher-secret-id"
    assert len(fingerprint) == 12
    assert state_path.stat().st_mode & 0o777 == 0o600
    assert state_path.parent.stat().st_mode & 0o777 == 0o700
    assert "teacher-secret-id" in state_path.read_text()


def test_process_payload_records_rejected_sender_without_logging_id(tmp_path):
    state_path = tmp_path / "senders.json"
    response, saved, sender = kw.process_payload(
        payload(user_id="new-teacher"),
        str(tmp_path / "lessons"),
        {"approved-teacher"},
        datetime(2026, 7, 25, 13, 1, 2),
        str(state_path),
    )
    assert saved is None
    assert sender == "new-teacher"
    assert "등록된" in response["template"]["outputs"][0]["simpleText"]["text"]
    assert "new-teacher" in state_path.read_text()


def test_rotate_path_and_approve_latest_sender_preserve_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=keep-me\nKAKAO_ALLOWED_USER_IDS=teacher-1\n")
    state_path = tmp_path / "senders.json"
    kw.record_sender("teacher-2", str(state_path), datetime(2026, 7, 25, 13, 0, 0))

    path_fingerprint = kw.rotate_endpoint_path(str(env_file))
    sender_fingerprint = kw.approve_latest_sender(str(state_path), str(env_file))
    values = dict(
        line.split("=", 1)
        for line in env_file.read_text().splitlines()
        if "=" in line
    )
    assert len(path_fingerprint) == 12
    assert len(sender_fingerprint) == 12
    assert values["OPENAI_API_KEY"] == "keep-me"
    assert values["KAKAO_WEBHOOK_PATH"].startswith("/kakao/")
    assert set(values["KAKAO_ALLOWED_USER_IDS"].split(",")) == {
        "teacher-1",
        "teacher-2",
    }
    assert env_file.stat().st_mode & 0o777 == 0o600


def test_startup_message_does_not_print_secret_path(tmp_path, monkeypatch, capsys):
    class FakeServer:
        def __init__(self, *_args):
            pass

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    monkeypatch.setattr(kw, "ThreadingHTTPServer", FakeServer)
    secret = "/kakao/super-secret-value"
    assert kw.main(["--path", secret, "--sender-state", str(tmp_path / "s.json")]) == 0
    output = capsys.readouterr().out
    assert secret not in output
    assert "/<secret>" in output


def test_http_request_log_redacts_secret_path(tmp_path, capsys):
    secret = "/kakao/never-log-this"
    handler = kw.make_handler(
        str(tmp_path / "lessons"),
        secret,
        set(),
        str(tmp_path / "senders.json"),
    )
    server = kw.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    payload_bytes = json.dumps(payload()).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}{secret}",
        data=payload_bytes,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        assert response.status == 200
    thread.join(timeout=2)
    server.server_close()
    logs = capsys.readouterr().err
    assert secret not in logs
    assert "teacher-1" not in logs
    assert "sender=" in logs


def test_webhook_service_limits_writable_paths():
    text = (REPO / "bootstrap" / "kakao-webhook.service").read_text()
    assert "ProtectSystem=strict" in text
    assert "ProtectHome=read-only" in text
    assert "ReadWritePaths=%h/english-lessons %h/.hermes/data/english" in text
    assert "UMask=0077" in text


def test_installer_supports_secret_rotation_and_private_url_file():
    text = (REPO / "bootstrap" / "install_kakao_services.sh").read_text()
    assert "--rotate-path" in text
    assert "kakao-skill-url.txt" in text
    assert 'chmod 600 "$KAKAO_SKILL_URL_FILE"' in text


def test_webhook_restart_does_not_rotate_quick_tunnel_dependency():
    text = (REPO / "bootstrap" / "kakao-tunnel.service").read_text()
    assert "Wants=network-online.target kakao-webhook.service" in text
    assert "Requires=kakao-webhook.service" not in text
