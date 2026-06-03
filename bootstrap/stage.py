#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Stage this repo's config into a Hermes home directory (default ~/.hermes).

Purpose
-------
Hermes reads skills, memory, personality, scripts, and config from HERMES_HOME. This
script copies the version-controlled assets in this repo into that runtime location
idempotently, backing up anything it would overwrite. Running it again after editing
the repo re-syncs the agent — the repo stays the single source of truth.

What it stages:
  config/soul/SOUL.md      -> $HERMES_HOME/SOUL.md            (backup if exists)
  config/memory/*.md       -> $HERMES_HOME/memories/*.md      (seed only if empty)
  skills/<cat>/<name>/     -> $HERMES_HOME/skills/<cat>/<name>/
  scripts/*                -> $HERMES_HOME/scripts/           (+x for *.sh)
  config/config.fragment.yaml deep-merged into $HERMES_HOME/config.yaml (backup)

Usage:
  python bootstrap/stage.py                 # stage into ~/.hermes (or $HERMES_HOME)
  python bootstrap/stage.py --home /tmp/h    # stage into a custom home (used by tests)
  python bootstrap/stage.py --force-memory   # overwrite existing memory seeds
"""
from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency guard
    raise SystemExit("PyYAML is required: pip install -r requirements.txt") from exc

REPO_ROOT = Path(__file__).resolve().parent.parent


def _backup(path: Path) -> None:
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = path.with_suffix(path.suffix + f".bak-{stamp}")
        shutil.copy2(path, bak)


def deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge ``overlay`` into ``base`` (overlay wins on scalars)."""
    out = dict(base)
    for key, val in overlay.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def stage_soul(home: Path, repo: Path = REPO_ROOT) -> None:
    src = repo / "config" / "soul" / "SOUL.md"
    dst = home / "SOUL.md"
    if not src.exists():
        return
    _backup(dst)
    shutil.copy2(src, dst)


def stage_memory(home: Path, repo: Path = REPO_ROOT, force: bool = False) -> list[str]:
    """Seed MEMORY.md / USER.md. By default only seeds when the target is missing
    or empty, so we never clobber memory the agent has since curated."""
    mem_dir = home / "memories"
    mem_dir.mkdir(parents=True, exist_ok=True)
    staged = []
    for fname in ("MEMORY.md", "USER.md"):
        src = repo / "config" / "memory" / fname
        if not src.exists():
            continue
        dst = mem_dir / fname
        if dst.exists() and dst.stat().st_size > 0 and not force:
            continue
        if force:
            _backup(dst)
        shutil.copy2(src, dst)
        staged.append(fname)
    return staged


def stage_skills(home: Path, repo: Path = REPO_ROOT) -> list[str]:
    skills_root = repo / "skills"
    dst_root = home / "skills"
    staged = []
    if not skills_root.is_dir():
        return staged
    for skill_md in skills_root.rglob("SKILL.md"):
        rel = skill_md.parent.relative_to(skills_root)  # e.g. research/papers-digest
        dst = dst_root / rel
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(skill_md.parent, dst)
        staged.append(str(rel))
    return staged


def stage_scripts(home: Path, repo: Path = REPO_ROOT) -> list[str]:
    src_root = repo / "scripts"
    dst_root = home / "scripts"
    dst_root.mkdir(parents=True, exist_ok=True)
    staged = []
    if not src_root.is_dir():
        return staged
    for src in src_root.iterdir():
        if src.name.startswith("__") or src.suffix == ".pyc":
            continue
        if src.is_file():
            dst = dst_root / src.name
            shutil.copy2(src, dst)
            if src.suffix in (".sh", ".bash") or src.suffix == ".py":
                dst.chmod(0o755)
            staged.append(src.name)
    return staged


def stage_config(home: Path, repo: Path = REPO_ROOT) -> bool:
    frag_path = repo / "config" / "config.fragment.yaml"
    if not frag_path.exists():
        return False
    fragment = yaml.safe_load(frag_path.read_text()) or {}
    cfg_path = home / "config.yaml"
    current = {}
    if cfg_path.exists():
        current = yaml.safe_load(cfg_path.read_text()) or {}
        _backup(cfg_path)
    merged = deep_merge(current, fragment)
    cfg_path.write_text(yaml.safe_dump(merged, sort_keys=False))
    return True


def stage_data_dirs(home: Path) -> None:
    for sub in ("data/english", "data/interview", "data/cron"):
        (home / sub).mkdir(parents=True, exist_ok=True)


def stage_all(home: Path, repo: Path = REPO_ROOT, force_memory: bool = False) -> dict:
    home.mkdir(parents=True, exist_ok=True)
    report = {
        "home": str(home),
        "memory": stage_memory(home, repo, force_memory),
        "skills": stage_skills(home, repo),
        "scripts": stage_scripts(home, repo),
        "config_merged": stage_config(home, repo),
    }
    stage_soul(home, repo)
    stage_data_dirs(home)
    report["soul"] = (home / "SOUL.md").exists()
    return report


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--home",
        default=os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")),
    )
    parser.add_argument("--force-memory", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    report = stage_all(Path(args.home), REPO_ROOT, args.force_memory)
    print("Staged into", report["home"])
    print("  SOUL.md     :", "ok" if report["soul"] else "missing")
    print("  memory      :", report["memory"] or "kept existing")
    print("  skills      :", ", ".join(report["skills"]) or "none")
    print("  scripts     :", ", ".join(report["scripts"]) or "none")
    print("  config.yaml :", "merged" if report["config_merged"] else "no fragment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
