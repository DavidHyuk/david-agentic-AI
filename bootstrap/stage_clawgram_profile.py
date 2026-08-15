#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Stage the version-controlled ClawGram identity into its Hermes profile."""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import stat
from pathlib import Path

import stage


REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILE_SOURCE = REPO_ROOT / "profiles" / "clawgram"
DEFAULT_PROFILE_HOME = Path.home() / ".hermes" / "profiles" / "clawgram"
DEFAULT_DAVID_HOME = Path.home() / ".hermes"


def ensure_local_model_environment(home: Path) -> Path:
    """Add only the non-secret local-vLLM key without replacing bot secrets."""
    env_path = home / ".env"
    current = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    if any(line.startswith("OPENAI_API_KEY=") for line in current.splitlines()):
        env_path.chmod(0o600)
        return env_path
    suffix = "" if not current or current.endswith("\n") else "\n"
    content = f"{current}{suffix}OPENAI_API_KEY=sk-local-no-key-required\n"
    temporary = env_path.with_name(f".{env_path.name}.tmp-{os.getpid()}-{secrets.token_hex(4)}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(env_path)
        env_path.chmod(0o600)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return env_path


def stage_profile(
    home: Path,
    *,
    source: Path = PROFILE_SOURCE,
    cleanup_default_home: Path | None = None,
) -> dict:
    """Stage one isolated profile and optionally remove its legacy skill copy."""
    resolved_home = home.expanduser().resolve()
    resolved_home.mkdir(parents=True, exist_ok=True)
    report = {
        "home": str(resolved_home),
        "memory": stage.stage_memory(resolved_home, source),
        "skills": stage.stage_skills(resolved_home, source),
        "config_merged": stage.stage_config(resolved_home, source),
    }
    stage.stage_soul(resolved_home, source)
    ensure_local_model_environment(resolved_home)
    (resolved_home / "data" / "clawgram").mkdir(parents=True, exist_ok=True)
    report["soul"] = (resolved_home / "SOUL.md").exists()
    report["environment"] = str(resolved_home / ".env")
    report["removed_legacy_skill"] = False
    if cleanup_default_home is not None:
        default_home = cleanup_default_home.expanduser().resolve()
        legacy = default_home / "skills" / "personal" / "family-letter"
        expected = default_home / "skills" / "personal" / "family-letter"
        if legacy.resolve() != expected.resolve():  # pragma: no cover - defensive
            raise ValueError("legacy skill path escaped the default Hermes home")
        if legacy.is_dir():
            shutil.rmtree(legacy)
            report["removed_legacy_skill"] = True
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=DEFAULT_PROFILE_HOME)
    parser.add_argument("--cleanup-default", action="store_true")
    parser.add_argument("--default-home", type=Path, default=DEFAULT_DAVID_HOME)
    args = parser.parse_args()
    report = stage_profile(
        args.home,
        cleanup_default_home=args.default_home if args.cleanup_default else None,
    )
    print(f"Staged isolated ClawGram profile into {report['home']}")
    print("  SOUL.md     :", "ok" if report["soul"] else "missing")
    print("  memory      :", report["memory"] or "kept existing")
    print("  skills      :", ", ".join(report["skills"]) or "none")
    print("  config.yaml :", "merged" if report["config_merged"] else "missing")
    print("  .env        : local model key ready; other secrets preserved")
    print("  David skill :", "removed" if report["removed_legacy_skill"] else "not present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
