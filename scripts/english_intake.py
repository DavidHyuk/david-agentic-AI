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
from datetime import date, datetime, timedelta, timezone
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


def sessions_for_current_week(
    sessions: Sequence[dict], today: str | None = None
) -> list[dict]:
    """Return dated sessions from Monday through the reference day."""
    reference = date.fromisoformat(today) if today else date.today()
    week_start = reference - timedelta(days=reference.weekday())
    selected = []
    for session in sessions:
        raw_date = session.get("date")
        if not raw_date:
            match = re.match(r"(20\d{2}-\d{2}-\d{2})", session["session_id"])
            raw_date = match.group(1) if match else None
        if not raw_date:
            continue
        try:
            session_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        if week_start <= session_date <= reference:
            selected.append(session)
    return selected


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
    """Return only unprocessed files, including later files in the same session."""
    done = set(state.get("processed", []))
    processed_files = set(state.get("processed_files", []))
    fresh: list[dict] = []
    for session in sessions:
        # A legacy state has session IDs but no file snapshots. The CLI migrates
        # that state before calling this function. Keep this fallback so library
        # callers still preserve the old no-duplicate behavior.
        if "processed_files" not in state and session["session_id"] in done:
            continue
        candidate = dict(session)
        candidate["audio"] = [
            path for path in session["audio"] if _file_token(path) not in processed_files
        ]
        candidate["corrections"] = [
            path
            for path in session["corrections"]
            if _file_token(path) not in processed_files
        ]
        if candidate["audio"] or candidate["corrections"]:
            fresh.append(candidate)
    return fresh


def _file_token(path: str) -> str:
    """Identify one file version so modified files can be processed again."""
    absolute = os.path.abspath(path)
    try:
        stat = os.stat(absolute)
    except OSError:
        return absolute
    return f"{absolute}|{stat.st_size}|{stat.st_mtime_ns}"


def migrate_legacy_state(state: dict, sessions: Sequence[dict]) -> bool:
    """Snapshot files from legacy processed sessions exactly once.

    Older state tracked only a date/session ID. Recording the files that exist at
    upgrade time lets a later Kakao message in that same date become fresh without
    reprocessing historical lesson material.
    """
    if "processed_files" in state:
        return False
    done = set(state.get("processed", []))
    state["processed_files"] = sorted(
        _file_token(path)
        for session in sessions
        if session["session_id"] in done
        for path in (*session["audio"], *session["corrections"])
    )
    return True


def mark_processed(state: dict, sessions: Sequence[dict]) -> dict:
    done = set(state.get("processed", []))
    done.update(s["session_id"] for s in sessions)
    state["processed"] = sorted(done)
    processed_files = set(state.get("processed_files", []))
    processed_files.update(
        _file_token(path)
        for session in sessions
        for path in (*session["audio"], *session["corrections"])
    )
    state["processed_files"] = sorted(processed_files)
    return state


def save_from_telegram(file_path: str, lessons_dir: str) -> str:
    """Copy a file received via Telegram into lessons_dir and return the destination path.

    The file is placed under a subfolder named by today's date (YYYY-MM-DD) so
    english_intake.py groups it correctly as a session.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    dest_dir = os.path.join(os.path.expanduser(lessons_dir), today)
    os.makedirs(dest_dir, exist_ok=True)
    filename = os.path.basename(file_path)
    dest = os.path.join(dest_dir, filename)
    import shutil
    shutil.copy2(file_path, dest)
    return dest


def save_text_feedback(
    text: str, lessons_dir: str, session_id: str | None = None, source: str = "feedback"
) -> str:
    """Save a pasted feedback message as a scannable correction text file.

    Chat platforms deliver text without a local file path.  Saving the raw text in
    the normal lesson-folder layout lets the existing intake state and SRS workflow
    process it without a platform-specific branch.
    """
    if not text or not text.strip():
        raise ValueError("feedback text must not be empty")
    session = session_id or datetime.now().strftime("%Y-%m-%d")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", session):
        raise ValueError("session_id may contain only letters, numbers, _ and -")
    safe_source = re.sub(r"[^A-Za-z0-9_-]+", "-", source).strip("-") or "feedback"
    dest_dir = os.path.join(os.path.expanduser(lessons_dir), session)
    os.makedirs(dest_dir, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S%f")
    dest = os.path.join(dest_dir, f"{safe_source}-{stamp}.txt")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(text.strip() + "\n")
    return dest


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lessons-dir", default=os.environ.get("ENGLISH_LESSONS_DIR", DEFAULT_LESSONS_DIR))
    parser.add_argument("--state", default=os.environ.get("ENGLISH_STATE_PATH", DEFAULT_STATE_PATH))
    parser.add_argument("--mark", action="store_true", help="mark the new sessions as processed")
    parser.add_argument(
        "--week",
        action="store_true",
        help="also include all dated sessions from the current Monday through today",
    )
    parser.add_argument("--save-file", default=None, metavar="FILE",
                        help="save a file received via Telegram into lessons_dir and exit")
    parser.add_argument("--save-text", default=None, metavar="TEXT",
                        help="save pasted feedback text into lessons_dir and exit")
    parser.add_argument("--session-id", default=None, metavar="ID",
                        help="optional session id for --save-text (default: today)")
    parser.add_argument("--source", default="feedback", help="source label for --save-text")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.save_file:
        dest = save_from_telegram(args.save_file, args.lessons_dir)
        print(json.dumps({"saved": dest}))
        return 0

    if args.save_text is not None:
        dest = save_text_feedback(args.save_text, args.lessons_dir, args.session_id, args.source)
        print(json.dumps({"saved": dest}))
        return 0

    sessions = scan_sessions(args.lessons_dir)
    state = load_state(args.state)
    migrated = migrate_legacy_state(state, sessions)
    fresh = new_sessions(sessions, state)
    if args.mark and fresh:
        mark_processed(state, fresh)
    if migrated or (args.mark and fresh):
        save_state(args.state, state)
    result = {"lessons_dir": args.lessons_dir, "new_sessions": fresh}
    if args.week:
        result["week_sessions"] = sessions_for_current_week(sessions)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
