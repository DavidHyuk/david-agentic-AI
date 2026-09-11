#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Register the declarative cron jobs in cron/jobs.yaml with Hermes.

Purpose
-------
Reads the version-controlled schedule (cron/jobs.yaml) and creates the corresponding
Hermes cron jobs via the `hermes cron create` CLI. Idempotent-ish: it removes any
existing job with the same name first so re-running syncs the schedule to the file.

Requires the Hermes CLI on PATH and the gateway configured (cron runs in the
gateway daemon). Per-job Telegram chat IDs are read from ~/.hermes/.env so they
stay out of version control. Use --dry-run to print the commands without
executing them.

Usage:
  python bootstrap/register_cron.py --dry-run
  python bootstrap/register_cron.py
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required: pip install -r requirements.txt") from exc

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JOBS = REPO_ROOT / "cron" / "jobs.yaml"
DEFAULT_ENV_FILE = Path.home() / ".hermes" / ".env"

REQUIRED_FIELDS = ("name", "schedule", "prompt")
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TELEGRAM_CHAT_ID_RE = re.compile(r"^-?\d+$")


def load_jobs(jobs_path: Path) -> list[dict]:
    """Parse jobs.yaml, applying ``defaults`` to each job and validating fields."""
    doc = yaml.safe_load(jobs_path.read_text()) or {}
    defaults = doc.get("defaults", {}) or {}
    jobs = doc.get("jobs", []) or []
    resolved = []
    for job in jobs:
        merged = {**defaults, **job}
        missing = [f for f in REQUIRED_FIELDS if not merged.get(f)]
        if missing:
            raise ValueError(f"job {merged.get('name', '?')} missing fields: {missing}")
        resolved.append(merged)
    names = [j["name"] for j in resolved]
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate job names: {names}")
    return resolved


def load_env_file(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE entries without exposing or evaluating them."""
    if not path.exists():
        return {}

    values = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not ENV_NAME_RE.fullmatch(key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def runtime_environment(env_file: Path = DEFAULT_ENV_FILE) -> dict[str, str]:
    """Combine the Hermes env file with process variables taking precedence."""
    return {**load_env_file(env_file), **os.environ}


def resolve_delivery(
    job: dict,
    environment: dict[str, str],
    allow_missing_env: bool = False,
) -> str | None:
    """Resolve an optional per-job chat ID while keeping it out of source."""
    deliver = job.get("deliver")
    env_name = job.get("deliver_chat_id_env")
    if not env_name:
        return str(deliver) if deliver else None
    if not ENV_NAME_RE.fullmatch(str(env_name)):
        raise ValueError(f"job {job['name']} has invalid deliver_chat_id_env: {env_name}")
    if deliver != "telegram":
        raise ValueError(
            f"job {job['name']} uses deliver_chat_id_env but deliver is not telegram"
        )

    chat_id = environment.get(str(env_name), "").strip()
    if not chat_id:
        if allow_missing_env:
            return f"telegram:<{env_name}>"
        raise ValueError(
            f"job {job['name']} requires {env_name} in {DEFAULT_ENV_FILE} "
            "or the process environment"
        )
    if not TELEGRAM_CHAT_ID_RE.fullmatch(chat_id):
        raise ValueError(f"{env_name} must be a numeric Telegram chat ID")
    return f"telegram:{chat_id}"


def build_create_command(
    job: dict,
    environment: dict[str, str] | None = None,
    allow_missing_delivery_env: bool = False,
) -> list[str]:
    """Build the `hermes cron create` argv for one job."""
    prompt = " ".join(str(job["prompt"]).split())  # collapse YAML folded whitespace
    cmd = ["hermes", "cron", "create", str(job["schedule"]), prompt, "--name", job["name"]]
    for skill in job.get("skills", []) or []:
        cmd += ["--skill", skill]
    delivery = resolve_delivery(
        job,
        environment or {},
        allow_missing_env=allow_missing_delivery_env,
    )
    if delivery:
        cmd += ["--deliver", delivery]
    if job.get("workdir"):
        cmd += ["--workdir", str(job["workdir"])]
    if job.get("profile"):
        cmd += ["--profile", str(job["profile"])]
    return cmd


def build_remove_command(name: str, profile: str | None = None) -> list[str]:
    """Build removal in the same profile store used by job creation."""
    cmd = ["hermes"]
    if profile:
        cmd += ["-p", profile]
    return cmd + ["cron", "remove", name]


def register(
    jobs: list[dict],
    dry_run: bool = False,
    environment: dict[str, str] | None = None,
) -> None:
    environment = runtime_environment() if environment is None else environment
    have_cli = shutil.which("hermes") is not None
    for job in jobs:
        remove_cmd = build_remove_command(job["name"], job.get("profile"))
        create_cmd = build_create_command(
            job,
            environment=environment,
            allow_missing_delivery_env=dry_run,
        )
        if dry_run or not have_cli:
            prefix = "[dry-run]" if dry_run else "[no hermes CLI on PATH]"
            print(prefix, " ".join(repr(c) if " " in c else c for c in create_cmd))
            continue
        subprocess.run(remove_cmd, capture_output=True, text=True)  # best-effort
        result = subprocess.run(create_cmd, capture_output=True, text=True)
        status = "ok" if result.returncode == 0 else f"FAILED: {result.stderr.strip()}"
        print(f"  {job['name']}: {status}")


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", default=str(DEFAULT_JOBS))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    jobs = load_jobs(Path(args.jobs))
    print(f"Loaded {len(jobs)} cron jobs from {args.jobs}")
    register(jobs, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
