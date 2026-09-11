#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Stage repository-owned, headless specialist profiles for Hermes HQ."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import shutil
import stat

import yaml

import stage


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "profiles" / "specialists.yaml"
PROFILE_DIRS = (
    "memories", "sessions", "skills", "skins", "logs", "plans", "workspace",
    "cron", "home",
)


def load_manifest(path: Path = MANIFEST) -> dict[str, dict]:
    """Return validated profile definitions from the repository manifest."""
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profiles = document.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("specialists.yaml must define at least one profile")
    for name, definition in profiles.items():
        if not isinstance(name, str) or not name.replace("-", "").isalnum():
            raise ValueError(f"invalid specialist profile name: {name!r}")
        if not isinstance(definition, dict) or not str(definition.get("description", "")).strip():
            raise ValueError(f"specialist {name!r} needs a description")
        skills = definition.get("skills", [])
        if not isinstance(skills, list) or not all(isinstance(item, str) for item in skills):
            raise ValueError(f"specialist {name!r} has invalid skills")
    return profiles


def ensure_local_environment(home: Path) -> None:
    """Supply only the non-secret key expected by the localhost vLLM endpoint."""
    path = home / ".env"
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    keys = {line.split("=", 1)[0] for line in current.splitlines()
            if line and not line.startswith("#") and "=" in line}
    if "OPENAI_API_KEY" in keys:
        path.chmod(0o600)
        return
    separator = "" if not current or current.endswith("\n") else "\n"
    content = current + separator + "OPENAI_API_KEY=sk-local-no-key-required\n"
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{secrets.token_hex(4)}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                         stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        path.chmod(0o600)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def stage_skills(home: Path, skill_names: list[str], shared_home: Path,
                 repo: Path = REPO_ROOT) -> list[str]:
    """Replace skills and resolve shared-data paths for an isolated worker HOME."""
    destination = home / "skills"
    destination.mkdir(parents=True, exist_ok=True)
    allowed = set(skill_names)
    for skill_file in list(destination.rglob("SKILL.md")):
        relative = str(skill_file.parent.relative_to(destination))
        if relative not in allowed:
            shutil.rmtree(skill_file.parent)
    staged = []
    for relative in skill_names:
        source = repo / "skills" / relative
        if not (source / "SKILL.md").is_file():
            raise ValueError(f"missing specialist skill: {relative}")
        target = destination / relative
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        skill_file = target / "SKILL.md"
        skill_file.write_text(
            skill_file.read_text(encoding="utf-8").replace(
                "~/.hermes", str(shared_home.resolve()),
            ),
            encoding="utf-8",
        )
        staged.append(relative)
    (home / ".no-bundled-skills").write_text(
        "Managed by David-Agent/bootstrap/stage_specialist_profiles.py\n",
        encoding="utf-8",
    )
    return staged


def stage_profile(root: Path, name: str, definition: dict, repo: Path = REPO_ROOT) -> dict:
    """Create or refresh one headless profile without copying user secrets."""
    home = root / name
    home.mkdir(parents=True, exist_ok=True)
    for directory in PROFILE_DIRS:
        (home / directory).mkdir(parents=True, exist_ok=True)
    source = repo / "profiles" / name
    soul = source / "config/soul/SOUL.md"
    if not soul.is_file():
        raise ValueError(f"missing specialist SOUL: {name}")
    shutil.copy2(soul, home / "SOUL.md")
    stage.stage_memory(home, repo)
    stage.stage_config(home, repo)
    skills = stage_skills(home, definition.get("skills", []), root.parent, repo)
    ensure_local_environment(home)
    (home / "profile.yaml").write_text(yaml.safe_dump({
        "description": definition["description"].strip(),
        "description_auto": False,
    }, sort_keys=False), encoding="utf-8")
    return {"name": name, "home": str(home), "skills": skills}


def stage_all(root: Path, *, manifest: Path = MANIFEST,
              repo: Path = REPO_ROOT) -> list[dict]:
    definitions = load_manifest(manifest)
    return [stage_profile(root, name, definition, repo)
            for name, definition in definitions.items()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path,
                        default=Path.home() / ".hermes" / "profiles")
    args = parser.parse_args()
    for result in stage_all(args.root.expanduser().resolve()):
        print(f"Staged {result['name']}: {', '.join(result['skills']) or 'no skills'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
