#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Register the declarative cron jobs in cron/jobs.yaml with Hermes.

Purpose
-------
Reads the version-controlled schedule (cron/jobs.yaml) and creates the corresponding
Hermes cron jobs via the `hermes cron create` CLI. Idempotent-ish: it removes any
existing job with the same name first so re-running syncs the schedule to the file.

Requires the Hermes CLI on PATH and the gateway configured (cron runs in the
gateway daemon). Use --dry-run to print the commands without executing them.

Usage:
  python bootstrap/register_cron.py --dry-run
  python bootstrap/register_cron.py
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required: pip install -r requirements.txt") from exc

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JOBS = REPO_ROOT / "cron" / "jobs.yaml"

REQUIRED_FIELDS = ("name", "schedule", "prompt")


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


def build_create_command(job: dict) -> list[str]:
    """Build the `hermes cron create` argv for one job."""
    prompt = " ".join(str(job["prompt"]).split())  # collapse YAML folded whitespace
    cmd = ["hermes", "cron", "create", str(job["schedule"]), prompt, "--name", job["name"]]
    for skill in job.get("skills", []) or []:
        cmd += ["--skill", skill]
    if job.get("deliver"):
        cmd += ["--deliver", str(job["deliver"])]
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


def register(jobs: list[dict], dry_run: bool = False) -> None:
    have_cli = shutil.which("hermes") is not None
    for job in jobs:
        remove_cmd = build_remove_command(job["name"], job.get("profile"))
        create_cmd = build_create_command(job)
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
