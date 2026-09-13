#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Stage the isolated transcript-backed English podcast Hermes profile."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import shutil
import stat

import stage


REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILE_SOURCE = REPO_ROOT / "profiles" / "english-podcast"
DEFAULT_PROFILE_HOME = Path.home() / ".hermes" / "profiles" / "english-podcast"


def ensure_profile_environment(home: Path) -> Path:
    """Add non-secret shared-data defaults without replacing bot secrets."""
    env_path = home / ".env"
    current = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    existing_keys = {
        line.split("=", 1)[0]
        for line in current.splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    defaults = {
        "OPENAI_API_KEY": "sk-local-no-key-required",
        "ENGLISH_PODCAST_DATA_DIR": str(
            Path.home() / ".hermes" / "data" / "english-podcast"
        ),
        "ENGLISH_DECK_PATH": str(
            Path.home() / ".hermes" / "data" / "english" / "srs_deck.json"
        ),
        "ENGLISH_TUTOR_PROFILE_HOME": str(
            Path.home() / ".hermes" / "profiles" / "english"
        ),
        "ENGLISH_PODCAST_YT_DLP": str(Path.home() / ".local" / "bin" / "yt-dlp"),
    }
    missing = {key: value for key, value in defaults.items() if key not in existing_keys}
    if not missing:
        env_path.chmod(0o600)
        return env_path
    separator = "" if not current or current.endswith("\n") else "\n"
    content = current + separator + "".join(
        f"{key}={value}\n" for key, value in missing.items()
    )
    temporary = env_path.with_name(
        f".{env_path.name}.tmp-{os.getpid()}-{secrets.token_hex(4)}"
    )
    descriptor = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR
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


def remove_unmanaged_skills(home: Path, managed_skills: list[str]) -> list[str]:
    """Remove runtime-created skills from this repository-owned profile."""
    skills_root = (home / "skills").resolve()
    managed_dirs = {(skills_root / relative).resolve() for relative in managed_skills}
    removed: list[str] = []
    for skill_file in list(skills_root.rglob("SKILL.md")):
        relative = skill_file.relative_to(skills_root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        skill_dir = skill_file.parent.resolve()
        if skill_dir in managed_dirs:
            continue
        shutil.rmtree(skill_dir)
        removed.append(str(skill_file.parent.relative_to(skills_root)))
    return sorted(removed)


def stage_profile(
    home: Path,
    *,
    source: Path = PROFILE_SOURCE,
    repo: Path = REPO_ROOT,
) -> dict:
    """Stage the podcast-only identity while preserving Telegram credentials."""
    resolved_home = home.expanduser().resolve()
    resolved_home.mkdir(parents=True, exist_ok=True)
    managed_skills = stage.stage_skills(resolved_home, source)
    report = {
        "home": str(resolved_home),
        "memory": stage.stage_memory(resolved_home, source),
        "skills": managed_skills,
        "removed_unmanaged_skills": remove_unmanaged_skills(
            resolved_home, managed_skills
        ),
        "scripts": stage.stage_scripts(resolved_home, repo),
        "config_merged": stage.stage_config(resolved_home, source),
    }
    stage.stage_soul(resolved_home, source)
    ensure_profile_environment(resolved_home)
    report["soul"] = (resolved_home / "SOUL.md").exists()
    report["environment"] = str(resolved_home / ".env")
    report["podcast_data"] = str(
        Path.home() / ".hermes" / "data" / "english-podcast"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=DEFAULT_PROFILE_HOME)
    args = parser.parse_args()
    report = stage_profile(args.home)
    print(f"Staged English podcast profile into {report['home']}")
    print("  SOUL.md     :", "ok" if report["soul"] else "missing")
    print("  skills      :", ", ".join(report["skills"]) or "none")
    print("  unmanaged   :", ", ".join(report["removed_unmanaged_skills"]) or "none")
    print("  scripts     :", ", ".join(report["scripts"]) or "none")
    print("  .env        : local model key ready; Telegram token preserved")
    print("  podcast data:", report["podcast_data"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
