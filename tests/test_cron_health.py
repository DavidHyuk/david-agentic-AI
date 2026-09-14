# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for scripts/cron_health.py."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

import cron_health as ch


PACIFIC = timezone(timedelta(hours=-7))


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@pytest.fixture
def hermes_home(tmp_path: Path) -> Path:
    cron_dir = tmp_path / "cron"
    cron_dir.mkdir()
    return tmp_path


def test_check_tick_lock_not_held_when_missing(hermes_home):
    report = ch.check_tick_lock(hermes_home, now=datetime(2026, 6, 10, 12, 0, tzinfo=PACIFIC))
    assert report["held"] is False
    assert report["stale"] is False


def test_check_tick_lock_stale_when_held_too_long(hermes_home, monkeypatch):
    lock = hermes_home / "cron" / ".tick.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("")
    now = datetime(2026, 6, 10, 12, 0, tzinfo=PACIFIC)
    old = now - timedelta(minutes=45)
    import os

    os.utime(lock, (old.timestamp(), old.timestamp()))
    monkeypatch.setattr(ch, "lock_holder_pid", lambda _path: 12345)

    report = ch.check_tick_lock(hermes_home, stale_minutes=30, now=now)
    assert report["held"] is True
    assert report["holder_pid"] == 12345
    assert report["stale"] is True
    assert report["age_minutes"] == pytest.approx(45.0)


def test_check_jobs_stale_flags_overdue_next_run(hermes_home):
    now = datetime(2026, 6, 10, 12, 0, tzinfo=PACIFIC)
    jobs_path = hermes_home / "cron" / "jobs.json"
    jobs_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "abc",
                        "name": "morning-brief",
                        "enabled": True,
                        "last_run_at": _iso(now - timedelta(days=2)),
                        "next_run_at": _iso(now - timedelta(hours=1)),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = ch.check_jobs_stale(jobs_path, stale_hours=36, now=now)
    assert report["healthy"] is False
    assert len(report["stale_jobs"]) == 1
    assert report["stale_jobs"][0]["name"] == "morning-brief"
    assert report["stale_jobs"][0]["overdue_next_run"] is True


def test_check_jobs_stale_ignores_disabled_jobs(hermes_home):
    now = datetime(2026, 6, 10, 12, 0, tzinfo=PACIFIC)
    jobs_path = hermes_home / "cron" / "jobs.json"
    jobs_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "abc",
                        "name": "paused-job",
                        "enabled": False,
                        "last_run_at": _iso(now - timedelta(days=10)),
                        "next_run_at": _iso(now - timedelta(days=9)),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = ch.check_jobs_stale(jobs_path, stale_hours=36, now=now)
    assert report["healthy"] is True
    assert report["stale_jobs"] == []


def test_check_jobs_stale_flags_overdue_job_that_never_ran(hermes_home):
    now = datetime(2026, 6, 10, 12, 0, tzinfo=PACIFIC)
    jobs_path = hermes_home / "cron" / "jobs.json"
    jobs_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "new",
                        "name": "papers-digest",
                        "enabled": True,
                        "last_run_at": None,
                        "next_run_at": _iso(now - timedelta(minutes=10)),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = ch.check_jobs_stale(jobs_path, now=now)

    assert report["healthy"] is False
    assert report["stale_jobs"][0]["hours_since_last_run"] is None
    assert report["stale_jobs"][0]["overdue_next_run"] is True


def test_check_jobs_stale_accepts_old_last_run_when_next_run_is_future(hermes_home):
    now = datetime(2026, 6, 10, 12, 0, tzinfo=PACIFIC)
    jobs_path = hermes_home / "cron" / "jobs.json"
    jobs_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "weekly",
                        "name": "weekly-review",
                        "enabled": True,
                        "last_run_at": _iso(now - timedelta(days=6)),
                        "next_run_at": _iso(now + timedelta(days=1)),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = ch.check_jobs_stale(jobs_path, stale_hours=36, now=now)

    assert report["healthy"] is True
    assert report["stale_jobs"] == []


def test_check_jobs_stale_reports_a_failed_execution(hermes_home):
    now = datetime(2026, 6, 10, 12, 0, tzinfo=PACIFIC)
    jobs_path = hermes_home / "cron" / "jobs.json"
    jobs_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "failed-id",
                        "name": "papers-digest",
                        "enabled": True,
                        "last_run_at": _iso(now - timedelta(minutes=5)),
                        "next_run_at": _iso(now + timedelta(days=2)),
                        "last_status": "failed",
                        "last_error": "stream stalled",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = ch.check_jobs_stale(jobs_path, now=now)

    assert report["healthy"] is True
    assert report["failed_jobs"] == [
        {
            "id": "failed-id",
            "name": "papers-digest",
            "last_run_at": _iso(now - timedelta(minutes=5)),
            "last_status": "failed",
            "last_error": "stream stalled",
        }
    ]


def test_retry_failed_jobs_queues_only_one_retry_per_execution(hermes_home, monkeypatch):
    failed = {
        "id": "failed-id",
        "name": "papers-digest",
        "last_run_at": "2026-06-10T11:55:00-07:00",
        "last_status": "failed",
        "last_error": "stream stalled",
    }
    calls = []
    monkeypatch.setattr(
        ch,
        "run_cron_job",
        lambda job_id, **kwargs: (calls.append((job_id, kwargs)) is None, "queued"),
    )

    first = ch.retry_failed_jobs_once(hermes_home, [failed], profile="english")
    second = ch.retry_failed_jobs_once(hermes_home, [failed], profile="english")

    assert first == [{"name": "papers-digest", "result": "queued", "detail": "queued"}]
    assert second == []
    assert calls == [("failed-id", {"profile": "english"})]
    assert ch.retryable_failed_jobs(hermes_home, [failed]) == []


def test_run_cron_job_uses_the_target_profile(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="queued", stderr="")

    monkeypatch.setattr(ch.subprocess, "run", fake_run)

    assert ch.run_cron_job("job-123", profile="english") == (True, "queued")
    assert calls[0][0] == [
        "hermes", "--profile", "english", "cron", "run", "job-123",
    ]


def test_assess_health_critical_when_lock_stale(hermes_home, monkeypatch):
    lock = hermes_home / "cron" / ".tick.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("")
    now = datetime(2026, 6, 10, 12, 0, tzinfo=PACIFIC)
    import os

    old = now - timedelta(hours=2)
    os.utime(lock, (old.timestamp(), old.timestamp()))
    monkeypatch.setattr(ch, "lock_holder_pid", lambda _path: 99)
    jobs_path = hermes_home / "cron" / "jobs.json"
    jobs_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "ok",
                        "name": "papers-digest",
                        "enabled": True,
                        "last_run_at": _iso(now - timedelta(hours=2)),
                        "next_run_at": _iso(now + timedelta(hours=2)),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = ch.assess_health(hermes_home, now=now)
    assert report["critical"] is True


def test_check_api_health_accepts_a_fast_unauthorized_response(monkeypatch):
    def unauthorized(*_args, **_kwargs):
        raise HTTPError(ch.DEFAULT_API_HEALTH_URL, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(ch, "urlopen", unauthorized)

    report = ch.check_api_health()

    assert report["healthy"] is True
    assert report["status"] == 401


def test_check_api_health_flags_a_timeout(monkeypatch):
    monkeypatch.setattr(ch, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("timed out")))

    report = ch.check_api_health()

    assert report["healthy"] is False
    assert report["status"] is None
    assert "TimeoutError" in report["error"]


def test_assess_health_marks_unresponsive_api_critical(hermes_home, monkeypatch):
    (hermes_home / "cron" / "jobs.json").write_text('{"jobs": []}', encoding="utf-8")
    monkeypatch.setattr(
        ch,
        "check_api_health",
        lambda: {"url": "http://127.0.0.1:8642/health", "healthy": False, "status": None, "error": "timeout"},
    )

    report = ch.assess_health(hermes_home, check_api=True)

    assert report["critical"] is True
    assert report["api"]["healthy"] is False


def test_restart_gateway_uses_bounded_systemd_restart(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(ch.subprocess, "run", fake_run)

    ok, detail = ch.restart_gateway(timeout=45)

    assert ok is True
    assert detail == "hermes-gateway.service restarted"
    assert calls[0][0] == [
        "systemctl", "--user", "restart", "hermes-gateway.service",
    ]
    assert calls[0][1]["timeout"] == 45


def test_restart_gateway_reports_timeout(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(ch.subprocess, "run", fake_run)

    ok, detail = ch.restart_gateway(timeout=45)

    assert ok is False
    assert detail == "hermes-gateway.service restart timed out after 45s"


def test_main_restarts_requested_profile_gateway(hermes_home, monkeypatch, capsys):
    monkeypatch.setattr(
        ch,
        "assess_health",
        lambda *_a, **_k: {
            "lock": {"held": False, "stale": False},
            "jobs": {
                "jobs_file": str(hermes_home / "cron" / "jobs.json"),
                "exists": False,
                "healthy": False,
                "stale_jobs": [],
            },
            "critical": True,
        },
    )
    calls = []
    monkeypatch.setattr(
        ch,
        "restart_gateway",
        lambda **kwargs: (calls.append(kwargs) is None, "restarted"),
    )

    assert ch.main([
        "--hermes-home", str(hermes_home),
        "--gateway-service", "hermes-gateway-english.service",
        "--restart",
    ]) == 0
    assert calls == [{"service": "hermes-gateway-english.service"}]
    assert "gateway restart: ok" in capsys.readouterr().out


def test_main_can_skip_an_uninstalled_profile(tmp_path, monkeypatch, capsys):
    missing = tmp_path / "profiles" / "english"
    monkeypatch.setattr(
        ch,
        "assess_health",
        lambda *_a, **_k: pytest.fail("missing profile should not be assessed"),
    )

    assert ch.main([
        "--hermes-home", str(missing), "--skip-missing-home",
    ]) == 0
    assert "not installed; skipping" in capsys.readouterr().out


def test_main_can_skip_a_profile_without_gateway(hermes_home, monkeypatch, capsys):
    monkeypatch.setattr(ch, "gateway_service_exists", lambda _service: False)
    monkeypatch.setattr(
        ch,
        "assess_health",
        lambda *_a, **_k: pytest.fail("missing gateway should not be assessed"),
    )

    assert ch.main([
        "--hermes-home", str(hermes_home),
        "--gateway-service", "hermes-gateway-missing.service",
        "--skip-missing-gateway",
    ]) == 0
    assert "gateway not installed; skipping" in capsys.readouterr().out


def test_main_exit_codes(hermes_home, monkeypatch, capsys):
    jobs_path = hermes_home / "cron" / "jobs.json"
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime(2026, 6, 10, 12, 0, tzinfo=PACIFIC)
    jobs_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "x",
                        "name": "morning-brief",
                        "enabled": True,
                        "last_run_at": _iso(now - timedelta(days=3)),
                        "next_run_at": _iso(now - timedelta(days=2)),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ch, "check_tick_lock", lambda *_a, **_k: {"held": False, "stale": False})
    monkeypatch.setattr(
        ch,
        "check_jobs_stale",
        lambda *_a, **_k: {
            "exists": True,
            "healthy": False,
            "stale_jobs": [
                {
                    "name": "morning-brief",
                    "last_run_at": "2026-06-07T07:30:00-07:00",
                    "hours_since_last_run": 72.0,
                }
            ],
        },
    )

    assert ch.main(["--hermes-home", str(hermes_home)]) == 2
    out = capsys.readouterr().out
    assert "stale cron jobs" in out
