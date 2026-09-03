#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Stage the isolated English-coaching identity into its Hermes profile."""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import stat
from pathlib import Path

import stage


REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILE_SOURCE = REPO_ROOT / "profiles" / "english"
DEFAULT_PROFILE_HOME = Path.home() / ".hermes" / "profiles" / "english"
DEFAULT_DAVID_HOME = Path.home() / ".hermes"


def ensure_profile_environment(home: Path) -> Path:
    """Add non-secret runtime defaults without replacing Telegram secrets."""
    env_path = home / ".env"
    current = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    existing_keys = {
        line.split("=", 1)[0]
        for line in current.splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    defaults = {
        "OPENAI_API_KEY": "sk-local-no-key-required",
        # Hermes profiles intentionally override HOME. Use absolute shared-data
        # paths so this profile continues the existing Kakao/SRS history.
        "ENGLISH_LESSONS_DIR": str(Path.home() / "english-lessons"),
        "ENGLISH_STATE_PATH": str(Path.home() / ".hermes" / "data" / "english" / "processed.json"),
        "ENGLISH_DECK_PATH": str(Path.home() / ".hermes" / "data" / "english" / "srs_deck.json"),
    }
    missing = {key: value for key, value in defaults.items() if key not in existing_keys}
    if not missing:
        env_path.chmod(0o600)
        return env_path
    suffix = "" if not current or current.endswith("\n") else "\n"
    additions = "".join(f"{key}={value}\n" for key, value in missing.items())
    content = f"{current}{suffix}{additions}"
    temporary = env_path.with_name(f".{env_path.name}.tmp-{os.getpid()}-{secrets.token_hex(4)}")
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
    """Remove runtime-created skills from the repository-owned English profile."""
    skills_root = (home / "skills").resolve()
    managed_dirs = {(skills_root / rel).resolve() for rel in managed_skills}
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
    cleanup_default_home: Path | None = None,
) -> dict:
    """Stage the English-only profile while preserving its Telegram token."""
    resolved_home = home.expanduser().resolve()
    resolved_home.mkdir(parents=True, exist_ok=True)
    managed_skills = stage.stage_skills(resolved_home, source)
    report = {
        "home": str(resolved_home),
        "memory": stage.stage_memory(resolved_home, source),
        "skills": managed_skills,
        "removed_unmanaged_skills": remove_unmanaged_skills(
            resolved_home, managed_skills,
        ),
        "scripts": stage.stage_scripts(resolved_home, REPO_ROOT),
        "config_merged": stage.stage_config(resolved_home, source),
    }
    stage.stage_soul(resolved_home, source)
    ensure_profile_environment(resolved_home)
    # The Kakao service and existing SRS deck deliberately remain under the main
    # Hermes home, allowing the dedicated bot to continue the existing learning
    # history without copying tutor feedback or card state.
    report["soul"] = (resolved_home / "SOUL.md").exists()
    report["environment"] = str(resolved_home / ".env")
    report["shared_english_data"] = str(Path.home() / ".hermes" / "data" / "english")
    report["removed_legacy_skill"] = False
    if cleanup_default_home is not None:
        default_home = cleanup_default_home.expanduser().resolve()
        legacy = default_home / "skills" / "learning" / "english-practice"
        expected = default_home / "skills" / "learning" / "english-practice"
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
    print(f"Staged isolated English profile into {report['home']}")
    print("  SOUL.md     :", "ok" if report["soul"] else "missing")
    print("  skills      :", ", ".join(report["skills"]) or "none")
    print(
        "  unmanaged   :",
        ", ".join(report["removed_unmanaged_skills"]) or "none",
    )
    print("  scripts     :", ", ".join(report["scripts"]) or "none")
    print("  .env        : local model key ready; Telegram token preserved")
    print("  shared data :", report["shared_english_data"])
    print("  David skill :", "removed" if report["removed_legacy_skill"] else "not present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
