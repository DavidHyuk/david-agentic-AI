#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Check Hermes cron scheduler health and optionally restart the gateway.

Purpose
-------
Detects failure modes that silently stop Telegram cron alerts:
  1. ``~/.hermes/cron/.tick.lock`` held longer than a threshold (stuck tick).
  2. ``jobs.json`` last_run timestamps older than expected (scheduler idle).
  3. a cron job with a failed terminal status (one bounded retry per run).

Standalone CLI for manual checks or cron/systemd watchdog use. A caller can
target a profile home and its matching systemd gateway service. Exit 0 when
healthy, 1 when warnings are present, 2 when action is recommended.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_HERMES_HOME = Path(os.path.expanduser("~/.hermes"))
DEFAULT_LOCK_STALE_MINUTES = 30
DEFAULT_JOB_STALE_HOURS = 36
DEFAULT_GATEWAY_SERVICE = "hermes-gateway.service"
DEFAULT_RESTART_TIMEOUT_SECONDS = 75
DEFAULT_CRON_RUN_TIMEOUT_SECONDS = 20
FAILED_STATUSES = frozenset({"failed", "error", "timeout", "cancelled", "canceled"})

SECRET_PATTERNS = (".env", "credentials", "secret", "token", "auth.json")


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.now().astimezone()


def lock_holder_pid(lock_file: Path) -> int | None:
    """Return the PID holding ``lock_file``, or None if unheld / unknown."""
    if not lock_file.exists():
        return None
    try:
        result = subprocess.run(
            ["fuser", str(lock_file)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    for token in result.stdout.split():
        if token.isdigit():
            return int(token)
    return None


def check_tick_lock(
    hermes_home: Path,
    *,
    stale_minutes: int = DEFAULT_LOCK_STALE_MINUTES,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return health info for ``cron/.tick.lock``."""
    lock_file = hermes_home / "cron" / ".tick.lock"
    current = now or _now()
    pid = lock_holder_pid(lock_file)
    held = pid is not None
    age_minutes = None
    if lock_file.exists():
        mtime = datetime.fromtimestamp(lock_file.stat().st_mtime, tz=current.tzinfo)
        age_minutes = (current - mtime).total_seconds() / 60.0
    stale = held and age_minutes is not None and age_minutes >= stale_minutes
    return {
        "lock_file": str(lock_file),
        "held": held,
        "holder_pid": pid,
        "age_minutes": age_minutes,
        "stale": stale,
        "stale_minutes": stale_minutes,
    }


def _enabled_jobs(doc: dict) -> list[dict]:
    jobs = doc.get("jobs") or []
    return [j for j in jobs if j.get("enabled", True)]


def _failed_jobs(doc: dict) -> list[dict[str, Any]]:
    """Return enabled jobs whose most recent execution reached a failed status."""
    failures: list[dict[str, Any]] = []
    for job in _enabled_jobs(doc):
        status = str(job.get("last_status") or "").strip().lower()
        if status not in FAILED_STATUSES:
            continue
        failures.append(
            {
                "id": str(job.get("id") or ""),
                "name": str(job.get("name") or job.get("id") or "?"),
                "last_run_at": job.get("last_run_at"),
                "last_status": status,
                "last_error": str(job.get("last_error") or ""),
            }
        )
    return failures


def check_jobs_stale(
    jobs_path: Path,
    *,
    stale_hours: int = DEFAULT_JOB_STALE_HOURS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Flag jobs with overdue next runs or stale jobs lacking a next run."""
    current = now or _now()
    if not jobs_path.exists():
        return {
            "jobs_file": str(jobs_path),
            "exists": False,
            "stale_jobs": [],
            "healthy": False,
        }
    doc = json.loads(jobs_path.read_text(encoding="utf-8"))
    stale_jobs: list[dict[str, Any]] = []
    for job in _enabled_jobs(doc):
        last_run = _parse_iso(job.get("last_run_at"))
        next_run = _parse_iso(job.get("next_run_at"))
        name = job.get("name") or job.get("id", "?")
        overdue_next = next_run is not None and next_run < current
        hours_since = (
            (current - last_run).total_seconds() / 3600.0
            if last_run is not None
            else None
        )
        stale_without_schedule = (
            next_run is None
            and hours_since is not None
            and hours_since >= stale_hours
        )
        if overdue_next or stale_without_schedule:
            stale_jobs.append(
                {
                    "name": name,
                    "last_run_at": job.get("last_run_at"),
                    "next_run_at": job.get("next_run_at"),
                        "hours_since_last_run": (
                            round(hours_since, 1)
                            if hours_since is not None
                            else None
                        ),
                    "overdue_next_run": overdue_next,
                }
            )
    return {
        "jobs_file": str(jobs_path),
        "exists": True,
        "stale_jobs": stale_jobs,
        "healthy": not stale_jobs,
        "stale_hours": stale_hours,
        "failed_jobs": _failed_jobs(doc),
    }


def assess_health(
    hermes_home: Path,
    *,
    lock_stale_minutes: int = DEFAULT_LOCK_STALE_MINUTES,
    job_stale_hours: int = DEFAULT_JOB_STALE_HOURS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Combine lock + jobs checks into one report."""
    lock = check_tick_lock(
        hermes_home, stale_minutes=lock_stale_minutes, now=now,
    )
    jobs = check_jobs_stale(
        hermes_home / "cron" / "jobs.json",
        stale_hours=job_stale_hours,
        now=now,
    )
    critical = lock["stale"] or (not jobs.get("healthy", True))
    return {"lock": lock, "jobs": jobs, "critical": critical}


def restart_gateway(
    *,
    service: str = DEFAULT_GATEWAY_SERVICE,
    timeout: int = DEFAULT_RESTART_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Restart the systemd user gateway with a bounded client-side wait."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "restart", service],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, "systemctl not found on PATH"
    except subprocess.TimeoutExpired:
        return False, f"{service} restart timed out after {timeout}s"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, detail or f"exit {result.returncode}"
    return True, (result.stdout or "").strip() or f"{service} restarted"


def gateway_service_exists(service: str) -> bool:
    """Return whether systemd knows the profile's gateway unit."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show", service, "--property=LoadState", "--value"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() not in {"", "not-found"}


def _format_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lock = report["lock"]
    if lock["held"]:
        age = lock.get("age_minutes")
        age_txt = f"{age:.0f} min" if age is not None else "unknown age"
        lines.append(
            f"tick lock held by pid {lock['holder_pid']} ({age_txt})"
        )
        if lock["stale"]:
            lines.append(
                f"  -> stale (>{lock['stale_minutes']} min); cron ticks are likely blocked"
            )
    else:
        lines.append("tick lock: not held")

    jobs = report["jobs"]
    if not jobs.get("exists"):
        lines.append(f"jobs.json missing at {jobs['jobs_file']}")
    elif jobs["stale_jobs"]:
        lines.append("stale cron jobs:")
        for item in jobs["stale_jobs"]:
            last_run = item["last_run_at"] or "never"
            age = item.get("hours_since_last_run")
            age_text = f" ({age}h ago)" if age is not None else ""
            lines.append(
                f"  - {item['name']}: last run {last_run}{age_text}"
            )
    else:
        lines.append("cron jobs: last_run timestamps look current")
    if jobs.get("failed_jobs"):
        lines.append("failed cron jobs:")
        for item in jobs["failed_jobs"]:
            lines.append(
                f"  - {item['name']}: {item['last_status']} at "
                f"{item['last_run_at'] or 'unknown time'}"
            )
    return "\n".join(lines)


def _retry_key(job: dict[str, Any]) -> str:
    """Identify one specific failed execution, not merely a recurring job."""
    return f"{job['id']}:{job.get('last_run_at') or 'unknown'}"


def load_retry_state(path: Path) -> set[str]:
    """Read previously queued retry keys; invalid runtime state is ignored."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {str(key) for key in data.get("retried", [])}


def save_retry_state(path: Path, retried: set[str]) -> None:
    """Persist retry keys atomically under the profile's mutable cron state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"retried": sorted(retried)}, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run_cron_job(
    job_id: str,
    *,
    profile: str | None = None,
    timeout: int = DEFAULT_CRON_RUN_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Queue one job for its next scheduler tick without waiting for its result."""
    command = ["hermes"]
    if profile:
        command += ["--profile", profile]
    command += ["cron", "run", job_id]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=timeout,
        )
    except FileNotFoundError:
        return False, "hermes CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return False, f"cron run timed out after {timeout}s"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, detail or f"exit {result.returncode}"
    return True, (result.stdout or "").strip() or f"queued {job_id}"


def retry_failed_jobs_once(
    hermes_home: Path,
    failed_jobs: list[dict[str, Any]],
    *,
    profile: str | None = None,
    retry_state_path: Path | None = None,
) -> list[dict[str, str]]:
    """Queue at most one retry for each failed execution and record the attempt."""
    state_path = retry_state_path or hermes_home / "cron" / "retry-state.json"
    retried = load_retry_state(state_path)
    outcomes: list[dict[str, str]] = []
    for job in failed_jobs:
        key = _retry_key(job)
        if not job["id"] or key in retried:
            continue
        ok, detail = run_cron_job(job["id"], profile=profile)
        outcomes.append({"name": job["name"], "result": "queued" if ok else "failed", "detail": detail})
        if ok:
            retried.add(key)
    save_retry_state(state_path, retried)
    return outcomes


def retryable_failed_jobs(hermes_home: Path, failed_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exclude executions that have already consumed their single retry."""
    retried = load_retry_state(hermes_home / "cron" / "retry-state.json")
    return [job for job in failed_jobs if job.get("id") and _retry_key(job) not in retried]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hermes-home",
        default=str(DEFAULT_HERMES_HOME),
        help="Hermes home directory (default: ~/.hermes)",
    )
    parser.add_argument(
        "--profile",
        help="Hermes profile name when retrying a profile-local cron job",
    )
    parser.add_argument(
        "--retry-failed-once",
        action="store_true",
        help="Restart then queue one retry for each newly failed cron execution",
    )
    parser.add_argument(
        "--lock-stale-minutes",
        type=int,
        default=DEFAULT_LOCK_STALE_MINUTES,
        help="Warn when tick lock held longer than this (default: 30)",
    )
    parser.add_argument(
        "--job-stale-hours",
        type=int,
        default=DEFAULT_JOB_STALE_HOURS,
        help="Warn when enabled jobs last ran longer ago than this (default: 36)",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart the gateway when health check is critical",
    )
    parser.add_argument(
        "--gateway-service",
        default=DEFAULT_GATEWAY_SERVICE,
        help=f"systemd user service to restart (default: {DEFAULT_GATEWAY_SERVICE})",
    )
    parser.add_argument(
        "--skip-missing-home",
        action="store_true",
        help="Exit successfully when --hermes-home does not exist",
    )
    parser.add_argument(
        "--skip-missing-gateway",
        action="store_true",
        help="Exit successfully when the selected systemd gateway is not installed",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    home = Path(args.hermes_home).expanduser()
    if args.skip_missing_home and not home.exists():
        print(f"Hermes home not installed; skipping: {home}")
        return 0
    if args.skip_missing_gateway and not gateway_service_exists(args.gateway_service):
        print(f"Hermes gateway not installed; skipping: {args.gateway_service}")
        return 0
    report = assess_health(
        home,
        lock_stale_minutes=args.lock_stale_minutes,
        job_stale_hours=args.job_stale_hours,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_format_report(report))

    failures = report["jobs"].get("failed_jobs", [])
    retryable_failures = retryable_failed_jobs(home, failures)
    should_recover = report["critical"] or (
        args.retry_failed_once and bool(retryable_failures)
    )
    if should_recover:
        if args.restart:
            ok, msg = restart_gateway(service=args.gateway_service)
            if ok:
                print("gateway restart: ok")
                if msg:
                    print(msg)
                if args.retry_failed_once and retryable_failures:
                    outcomes = retry_failed_jobs_once(
                        home, retryable_failures, profile=args.profile,
                    )
                    for outcome in outcomes:
                        print(
                            f"cron retry {outcome['result']}: "
                            f"{outcome['name']} ({outcome['detail']})"
                        )
                    if any(outcome["result"] == "failed" for outcome in outcomes):
                        return 2
                return 0
            print(f"gateway restart failed: {msg}")
            return 2
        return 2
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
