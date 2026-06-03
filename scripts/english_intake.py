#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Detect new English-lesson sessions dropped into a local folder.

Purpose
-------
David's tutor sends, after each lesson, a recording plus written corrections.
Those files land in a local folder (default ``~/english-lessons``). This module
groups the raw files into *sessions*, tracks which sessions have already been
processed, and emits a JSON manifest of *new* sessions for the ``english-practice``
Hermes skill to transcribe, mine for corrections, and feed into spaced repetition.

A session is keyed by:
  * its containing subfolder (if files are organized in per-lesson folders), else
  * a date parsed from the filename (YYYY-MM-DD / YYYYMMDD), else
  * the file's modification date.

Keeping intake here (instead of in the skill prompt) makes "what counts as new"
deterministic, testable, and safe to run repeatedly from cron.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from typing import Sequence

DEFAULT_LESSONS_DIR = os.path.expanduser("~/english-lessons")
DEFAULT_STATE_PATH = os.path.expanduser("~/.hermes/data/english/processed.json")

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac", ".mp4", ".webm"}
TEXT_EXTS = {".txt", ".md", ".docx", ".pdf", ".rtf"}

_DATE_PATTERNS = (
    re.compile(r"(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})"),  # 2026-06-01
    re.compile(r"(20\d{2})(\d{2})(\d{2})"),                 # 20260601
)


def parse_date_from_name(name: str) -> str | None:
    """Extract an ISO date (YYYY-MM-DD) from a filename, or None."""
    for pat in _DATE_PATTERNS:
        m = pat.search(name)
        if m:
            y, mo, d = (int(g) for g in m.groups())
            try:
                return datetime(y, mo, d).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def _classify(path: str) -> str | None:
    ext = os.path.splitext(path)[1].lower()
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in TEXT_EXTS:
        return "correction"
    return None


def _session_key(root: str, dirpath: str, filename: str) -> str:
    """Group files into a session id by subfolder, else filename date, else mtime."""
    rel_dir = os.path.relpath(dirpath, root)
    if rel_dir not in (".", ""):
        return rel_dir.replace(os.sep, "/")
    date = parse_date_from_name(filename)
    if date:
        return date
    mtime = os.path.getmtime(os.path.join(dirpath, filename))
    return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")


def scan_sessions(lessons_dir: str) -> list[dict]:
    """Walk ``lessons_dir`` and group recognized files into lesson sessions.

    Returns a list of dicts: ``{session_id, date, audio[], corrections[]}`` sorted
    by session id. Sessions with neither audio nor corrections are dropped.
    """
    if not os.path.isdir(lessons_dir):
        return []
    sessions: dict[str, dict] = {}
    for dirpath, _dirs, files in os.walk(lessons_dir):
        for fn in sorted(files):
            kind = _classify(fn)
            if kind is None:
                continue
            key = _session_key(lessons_dir, dirpath, fn)
            full = os.path.join(dirpath, fn)
            sess = sessions.setdefault(
                key, {"session_id": key, "date": None, "audio": [], "corrections": []}
            )
            sess["audio" if kind == "audio" else "corrections"].append(full)
            date = parse_date_from_name(fn) or (key if re.match(r"20\d{2}-\d{2}-\d{2}", key) else None)
            if date and not sess["date"]:
                sess["date"] = date
    return [sessions[k] for k in sorted(sessions)]


def load_state(state_path: str) -> dict:
    if os.path.exists(state_path):
        try:
            with open(state_path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass
    return {"processed": []}


def save_state(state_path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    tmp = state_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    os.replace(tmp, state_path)


def new_sessions(sessions: Sequence[dict], state: dict) -> list[dict]:
    """Return sessions whose id is not yet in ``state['processed']``."""
    done = set(state.get("processed", []))
    return [s for s in sessions if s["session_id"] not in done]


def mark_processed(state: dict, sessions: Sequence[dict]) -> dict:
    done = set(state.get("processed", []))
    done.update(s["session_id"] for s in sessions)
    state["processed"] = sorted(done)
    return state


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lessons-dir", default=os.environ.get("ENGLISH_LESSONS_DIR", DEFAULT_LESSONS_DIR))
    parser.add_argument("--state", default=os.environ.get("ENGLISH_STATE_PATH", DEFAULT_STATE_PATH))
    parser.add_argument("--mark", action="store_true", help="mark the new sessions as processed")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    sessions = scan_sessions(args.lessons_dir)
    state = load_state(args.state)
    fresh = new_sessions(sessions, state)
    if args.mark and fresh:
        save_state(args.state, mark_processed(state, fresh))
    print(json.dumps({"lessons_dir": args.lessons_dir, "new_sessions": fresh}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
