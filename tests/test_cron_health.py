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


@pytest.mark.parametrize('state,expected', [({'active':1,'waiting':0},True),
    ({'active':0,'waiting':1},True),({'active':0,'waiting':0,'cooling_paused':True},True),
    ({'active':0,'waiting':0,'resource_paused':True},True),({},True),
    ({'active':0,'waiting':0},False)])
def test_recovery_requires_verified_idle_inference(monkeypatch, state, expected):
    from contextlib import contextmanager
    import io
    @contextmanager
    def response(*args, **kwargs):
        yield io.StringIO(json.dumps(state))
    monkeypatch.setattr(ch, 'urlopen', response)
    assert ch.inference_recovery_deferred('http://127.0.0.1:8003/admission') is expected


def test_missing_admission_defers_recovery(monkeypatch):
    monkeypatch.setattr(ch, 'urlopen', lambda *a, **k: (_ for _ in ()).throw(OSError('missing')))
    assert ch.inference_recovery_deferred('http://127.0.0.1:8003/admission')


def test_busy_inference_defers_gateway_restart_and_failed_cron_retry(hermes_home, monkeypatch, capsys):
    monkeypatch.setattr(ch, 'assess_health', lambda *a, **k: {'critical':True,'jobs':{'failed_jobs':[]}})
    monkeypatch.setattr(ch, 'inference_recovery_deferred', lambda url: True)
    monkeypatch.setattr(ch, 'restart_gateway', lambda **k: pytest.fail('active answer interrupted'))
    monkeypatch.setattr(ch, 'retry_failed_jobs_once', lambda *a, **k: pytest.fail('retry submitted while busy'))
    assert ch.main(['--hermes-home',str(hermes_home),'--json','--restart','--retry-failed-once',
                    '--inference-admission-url','http://127.0.0.1:8003/admission']) == 1
    assert 'recovery deferred' in capsys.readouterr().out


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


def test_check_jobs_stale_allows_due_job_startup_grace(hermes_home):
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

    assert report["healthy"] is True
    assert report["stale_jobs"] == []


def test_check_jobs_stale_flags_job_beyond_startup_grace(hermes_home):
    now = datetime(2026, 6, 10, 12, 0, tzinfo=PACIFIC)
    jobs_path = hermes_home / "cron" / "jobs.json"
    jobs_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "late",
                        "name": "papers-digest",
                        "enabled": True,
                        "last_run_at": None,
                        "next_run_at": _iso(now - timedelta(minutes=16)),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = ch.check_jobs_stale(jobs_path, now=now)

    assert report["healthy"] is False
    assert report["overdue_grace_minutes"] == 15
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


def test_failed_retry_does_not_restart_or_repeat_until_success(hermes_home, monkeypatch):
    jobs_path = hermes_home / "cron" / "jobs.json"
    calls = []
    monkeypatch.setattr(ch, "lock_holder_pid", lambda _path: None)
    monkeypatch.setattr(ch, "restart_gateway", lambda **_k: pytest.fail("healthy gateway restarted"))
    monkeypatch.setattr(ch, "run_cron_job", lambda job_id, **_k: (calls.append(job_id) is None, "queued"))
    args = ["--hermes-home", str(hermes_home), "--restart", "--retry-failed-once"]
    now = ch._now()

    def write_run(status, run_at):
        jobs_path.write_text(json.dumps({"jobs": [{
            "id": "bad-job", "name": "sync", "last_status": status,
            "last_run_at": run_at.isoformat(),
            "next_run_at": (now + timedelta(days=1)).isoformat(),
        }]}))

    write_run("error", now - timedelta(minutes=10))
    assert ch.main(args) == 0
    write_run("error", now - timedelta(minutes=5))
    assert ch.main(args) == 1
    assert ch.main(args) == 1
    assert calls == ["bad-job"]
    write_run("ok", now)
    assert ch.main(args) == 0
    write_run("error", now + timedelta(minutes=1))
    assert ch.main(args) == 0
    assert calls == ["bad-job", "bad-job"]


def test_existing_retry_state_blocks_changed_failure_timestamp(hermes_home, monkeypatch):
    ch.save_retry_state(hermes_home / "cron" / "retry-state.json", {
        "bad-job:2026-10-08T10:00:00-07:00",
    })
    failure = {"id": "bad-job", "name": "sync", "last_run_at": "2026-10-08T10:10:00-07:00"}
    monkeypatch.setattr(ch, "run_cron_job", lambda *_a, **_k: pytest.fail("retry loop continued"))
    assert ch.retryable_failed_jobs(hermes_home, [failure]) == []
    assert ch.retry_failed_jobs_once(hermes_home, [failure]) == []


def test_busy_inference_defers_retry_without_restarting_healthy_gateway(hermes_home, monkeypatch):
    monkeypatch.setattr(ch, "assess_health", lambda *_a, **_k: {
        "critical": False, "jobs": {"failed_jobs": [{"id": "bad-job", "name": "sync"}]},
    })
    monkeypatch.setattr(ch, "inference_recovery_deferred", lambda _url: True)
    monkeypatch.setattr(ch, "restart_gateway", lambda **_k: pytest.fail("healthy gateway restarted"))
    monkeypatch.setattr(ch, "run_cron_job", lambda *_a, **_k: pytest.fail("busy inference retried"))
    assert ch.main(["--hermes-home", str(hermes_home), "--json", "--restart", "--retry-failed-once",
                    "--inference-admission-url", "http://127.0.0.1:8003/admission"]) == 1


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


@pytest.mark.parametrize("restarted,verified,expected", [
    (True, True, "건강 검사를 통과했습니다"),
    (True, False, "추가 점검이 필요합니다"),
    (False, False, "복구 완료로 처리하지 않습니다"),
])
def test_restart_notice_explains_fault_remedy_and_actual_result(restarted, verified, expected):
    report = {"lock": {"stale": True, "age_minutes": 25},
              "jobs": {"exists": True, "stale_jobs": []},
              "api": {"healthy": False, "status": None, "error": "secret-token-value"}}
    text = ch.restart_notice(report, service="hermes-gateway-english.service", profile="english",
                             restarted=restarted, verified=verified)
    assert "25분" in text
    assert "Observatory API" in text
    assert "내부 원인은 아직 확정되지 않음" in text
    assert "타임아웃을 점검" in text
    assert "hermes-gateway-english.service" in text
    assert expected in text
    assert "secret-token-value" not in text


def test_restart_notice_identifies_delayed_jobs_and_missing_config():
    reasons, remedies = ch.restart_explanation({
        "jobs": {"exists": False, "stale_jobs": [{"name": "morning-brief"}]},
    })
    assert any("jobs.json" in item for item in reasons)
    assert any("morning-brief" in item for item in reasons)
    assert any("백업에서 복구" in item for item in remedies)


def test_restart_notice_uses_profile_home_and_hides_cli_errors(hermes_home, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "other-profile-token")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "9999")
    monkeypatch.setenv("HERMES_CRON_JOB_ID", "unrelated-cron")
    calls = []
    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=1, stderr="secret-token-value", stdout="")
    monkeypatch.setattr(ch.subprocess, "run", fake_run)
    ok, detail = ch.send_restart_notice(hermes_home, "incident", profile="english")
    assert not ok
    assert "secret-token-value" not in detail
    command, kwargs = calls[0]
    assert command == ["hermes", "--profile", "english", "send", "--to", "telegram", "--quiet"]
    assert kwargs["input"] == "incident"
    assert kwargs["env"]["HERMES_HOME"] == str(hermes_home)
    assert "TELEGRAM_BOT_TOKEN" not in kwargs["env"]
    assert "TELEGRAM_HOME_CHANNEL" not in kwargs["env"]
    assert "HERMES_CRON_JOB_ID" not in kwargs["env"]


def test_restart_notice_records_failed_delivery_without_failing_recovery(hermes_home, monkeypatch):
    args = ch._parse_args(["--hermes-home", str(hermes_home), "--notify-restarts"])
    report = {"critical": True, "jobs": {"exists": False}}
    monkeypatch.setattr(ch, "verify_restart", lambda *_a: (False, report))
    monkeypatch.setattr(ch, "send_restart_notice", lambda *_a, **_k: (False, "unavailable"))
    ch.report_restart(hermes_home, report, args, restarted=True)
    stored = json.loads((hermes_home / "cron" / "last-restart-notice.json").read_text())
    assert stored["restarted"] is True
    assert stored["verified"] is False
    assert stored["delivered"] is False
    assert "추가 점검이 필요합니다" in stored["message"]


@pytest.mark.parametrize("restart_ok,exit_code", [(True, 0), (False, 2)])
def test_watchdog_notifies_successful_and_failed_restart(hermes_home, monkeypatch, restart_ok, exit_code):
    monkeypatch.setattr(ch, "assess_health", lambda *_a, **_k: {"critical": True, "jobs": {}})
    monkeypatch.setattr(ch, "restart_gateway", lambda **_k: (restart_ok, "result"))
    calls = []
    monkeypatch.setattr(ch, "report_restart", lambda *_a, **kwargs: calls.append(kwargs))
    assert ch.main(["--hermes-home", str(hermes_home), "--json", "--restart", "--notify-restarts"]) == exit_code
    assert calls == [{"restarted": restart_ok}]


def test_healthy_gateway_does_not_send_restart_notice(hermes_home, monkeypatch):
    monkeypatch.setattr(ch, "assess_health", lambda *_a, **_k: {"critical": False, "jobs": {}})
    monkeypatch.setattr(ch, "report_restart", lambda *_a, **_k: pytest.fail("spurious restart notice"))
    assert ch.main(["--hermes-home", str(hermes_home), "--json", "--restart", "--notify-restarts"]) == 0


def test_verify_restart_waits_for_service_and_api_health(hermes_home, monkeypatch):
    args = ch._parse_args(["--check-api"])
    states = iter([SimpleNamespace(returncode=0, stdout="active"), SimpleNamespace(returncode=0, stdout="active")])
    reports = iter([{"critical": True}, {"critical": False}])
    monkeypatch.setattr(ch.subprocess, "run", lambda *_a, **_k: next(states))
    monkeypatch.setattr(ch, "assess_health", lambda *_a, **_k: next(reports))
    monkeypatch.setattr(ch.time, "sleep", lambda _seconds: None)
    assert ch.verify_restart(args, hermes_home) == (True, {"critical": False})


@pytest.mark.parametrize("result,expected", [
    ("oom-kill", "메모리 부족"), ("timeout", "대기 시간이 초과"),
    ("success", "요청자는 종료 상태만으로 확인할 수 없음"),
    ("exit-code", "내부 원인은 로그 확인 필요"),
])
def test_service_restart_notice_distinguishes_exit_causes(result, expected):
    message = ch.restart_notice({"service_exit": {"result": result, "status": "1"}},
        service="hermes-gateway.service", profile=None, restarted=True, verified=True)
    assert expected in message
    assert "systemd가 종료된" in message
    assert "해결 방법:" in message


def test_service_exit_is_reported_on_next_start_only(hermes_home, monkeypatch):
    monkeypatch.setenv("SERVICE_RESULT", "oom-kill")
    monkeypatch.setenv("EXIT_STATUS", "KILL")
    calls = []
    monkeypatch.setattr(ch, "report_restart", lambda home, report, args, **kwargs: calls.append(report))
    base = ["--hermes-home", str(hermes_home)]
    assert ch.main(base + ["--service-event", "start"]) == 0
    assert calls == []
    assert ch.main(base + ["--service-event", "stop"]) == 0
    assert calls == []
    assert ch.main(base + ["--service-event", "start"]) == 0
    assert calls[0]["service_exit"]["result"] == "oom-kill"
    assert calls[0]["service_exit"]["status"] == "KILL"
    assert ch.main(base + ["--service-event", "start"]) == 0
    assert len(calls) == 1


def test_watchdog_owned_restart_suppresses_duplicate_start_notice(hermes_home, monkeypatch):
    ch.save_service_event(hermes_home / "cron" / "watchdog-restart.json", {"time": ch._now().isoformat()})
    monkeypatch.setattr(ch, "report_restart", lambda *_a, **_k: pytest.fail("duplicate restart notice"))
    base = ["--hermes-home", str(hermes_home)]
    assert ch.main(base + ["--service-event", "stop"]) == 0
    assert ch.main(base + ["--service-event", "start"]) == 0


def test_stale_watchdog_marker_does_not_hide_service_restart(hermes_home, monkeypatch):
    ch.save_service_event(hermes_home / "cron" / "watchdog-restart.json", {
        "time": (ch._now() - timedelta(minutes=11)).isoformat(),
    })
    calls = []
    monkeypatch.setattr(ch, "report_restart", lambda *_a, **_k: calls.append(True))
    base = ["--hermes-home", str(hermes_home)]
    ch.main(base + ["--service-event", "stop"])
    ch.main(base + ["--service-event", "start"])
    assert calls == [True]


def test_start_hook_verifies_during_systemd_activation(hermes_home, monkeypatch):
    args = ch._parse_args(["--service-event", "start"])
    monkeypatch.setattr(ch.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=3, stdout="activating"))
    monkeypatch.setattr(ch, "assess_health", lambda *_a, **_k: {"critical": False})
    assert ch.verify_restart(args, hermes_home) == (True, {"critical": False})


def test_pending_notice_retries_delivery_once_without_restart(hermes_home, monkeypatch):
    path = hermes_home / "cron" / "last-restart-notice.json"
    ch.save_service_event(path, {"message": "restart incident", "delivered": False})
    calls = []
    monkeypatch.setattr(ch, "send_restart_notice", lambda *_a, **_k: (calls.append(True) is None, "sent"))
    monkeypatch.setattr(ch, "restart_gateway", lambda **_k: pytest.fail("notification triggered restart"))
    ch.deliver_pending_restart_notice(hermes_home, profile="english")
    ch.deliver_pending_restart_notice(hermes_home, profile="english")
    assert calls == [True]
    assert json.loads(path.read_text())["delivered"] is True


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
