#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Prepare one transcript-backed English Goal Podcast lesson per local day.

The helper keeps network retrieval and daily assignment state deterministic for
the ``english-podcast-coach`` skill. It downloads English YouTube captions with
yt-dlp, preserves the source JSON3 file, writes a timestamped plain-text
transcript, and never marks an episode delivered until the agent explicitly
does so.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Sequence


DEFAULT_CHANNEL_URL = "https://www.youtube.com/@EnglishGoalPodcast/videos"
EXPECTED_CHANNEL_ID = "UC8oq85HHmW3BDhYWc1YcsIA"
DEFAULT_DATA_DIR = Path.home() / ".hermes" / "data" / "english-podcast"
DEFAULT_PLAYLIST_LIMIT = 500
MIN_TRANSCRIPT_WORDS = 50

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _atomic_write_json(path: Path, document: dict[str, Any]) -> None:
    """Replace a JSON document atomically without exposing a partial state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "assignments": {}}
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(
        document.get("assignments"), dict
    ):
        raise ValueError(f"Invalid podcast state; existing file preserved: {path}")
    return document


def _run_yt_dlp(
    arguments: Sequence[str],
    *,
    timeout: int,
    runner: Runner = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    configured = os.environ.get("ENGLISH_PODCAST_YT_DLP", "").strip()
    executable = configured or shutil.which("yt-dlp")
    command = (
        [executable, *arguments]
        if executable
        else [sys.executable, "-m", "yt_dlp", *arguments]
    )
    try:
        result = runner(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "yt-dlp is missing; run: python3 -m pip install -r requirements.txt"
        ) from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        if "No module named yt_dlp" in detail or "No such file or directory" in detail:
            detail = "yt-dlp is missing; run: python3 -m pip install -r requirements.txt"
        raise RuntimeError(detail or f"yt-dlp exited with {result.returncode}")
    return result


def fetch_channel_entries(
    channel_url: str,
    *,
    limit: int = DEFAULT_PLAYLIST_LIMIT,
    runner: Runner = subprocess.run,
) -> list[dict[str, Any]]:
    """Return newest-first videos from the configured channel."""
    result = _run_yt_dlp(
        [
            "--flat-playlist",
            "--playlist-end",
            str(limit),
            "--dump-single-json",
            "--no-warnings",
            channel_url,
        ],
        timeout=120,
        runner=runner,
    )
    document = json.loads(result.stdout)
    channel_id = str(document.get("channel_id") or "")
    if channel_id != EXPECTED_CHANNEL_ID:
        raise RuntimeError(
            "Configured YouTube handle did not resolve to the expected "
            f"English Goal Podcast channel ({EXPECTED_CHANNEL_ID})"
        )
    entries: list[dict[str, Any]] = []
    for raw in document.get("entries") or []:
        video_id = str(raw.get("id") or "").strip()
        if not video_id:
            continue
        entries.append(
            {
                "id": video_id,
                "title": str(raw.get("title") or video_id),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "duration": raw.get("duration"),
            }
        )
    if not entries:
        raise RuntimeError(f"No videos found at channel: {channel_url}")
    return entries


def select_unassigned(
    entries: Sequence[dict[str, Any]], state: dict[str, Any]
) -> list[dict[str, Any]]:
    """Keep channel order while excluding videos already assigned to a day."""
    assigned = {
        str(item.get("video_id"))
        for item in state.get("assignments", {}).values()
        if isinstance(item, dict) and item.get("video_id")
    }
    return [entry for entry in entries if entry["id"] not in assigned]


def timestamp(milliseconds: int | float) -> str:
    total_seconds = max(0, int(float(milliseconds) / 1000))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def json3_cues(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract non-empty caption cues from yt-dlp's JSON3 subtitle format."""
    cues: list[dict[str, Any]] = []
    for event in document.get("events") or []:
        segments = event.get("segs") or []
        raw = "".join(str(segment.get("utf8") or "") for segment in segments)
        text = " ".join(raw.replace("\n", " ").split())
        if not text:
            continue
        cues.append(
            {
                "start_ms": int(event.get("tStartMs") or 0),
                "duration_ms": int(event.get("dDurationMs") or 0),
                "text": text,
            }
        )
    return cues


def _caption_preference(path: Path) -> tuple[int, str]:
    name = path.name
    if ".en-orig." in name:
        return (0, name)
    if ".en." in name:
        return (1, name)
    return (2, name)


def download_transcript(
    video: dict[str, Any],
    data_dir: Path,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Download captions and create a compact manifest plus readable transcript."""
    captions_dir = data_dir / "captions"
    transcripts_dir = data_dir / "transcripts"
    metadata_dir = data_dir / "metadata"
    for directory in (captions_dir, transcripts_dir, metadata_dir):
        directory.mkdir(parents=True, exist_ok=True)

    video_id = str(video["id"])
    output_template = str(captions_dir / "%(id)s.%(ext)s")
    _run_yt_dlp(
        [
            "--no-playlist",
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            "en-orig,en",
            "--sub-format",
            "json3",
            "--write-info-json",
            "--no-warnings",
            "--output",
            output_template,
            str(video["url"]),
        ],
        timeout=180,
        runner=runner,
    )
    caption_paths = sorted(
        captions_dir.glob(f"{video_id}.en*.json3"), key=_caption_preference
    )
    if not caption_paths:
        raise RuntimeError(f"No downloadable English captions for {video_id}")
    caption_path = caption_paths[0]
    caption_document = json.loads(caption_path.read_text(encoding="utf-8"))
    cues = json3_cues(caption_document)
    word_count = sum(len(cue["text"].split()) for cue in cues)
    if word_count < MIN_TRANSCRIPT_WORDS:
        raise RuntimeError(
            f"English transcript for {video_id} is unexpectedly short ({word_count} words)"
        )

    info_path = captions_dir / f"{video_id}.info.json"
    info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    resolved_channel_id = str(info.get("channel_id") or "")
    if resolved_channel_id and resolved_channel_id != EXPECTED_CHANNEL_ID:
        raise RuntimeError(
            f"Downloaded video {video_id} does not belong to the expected channel"
        )
    transcript_path = transcripts_dir / f"{video_id}.txt"
    title = str(info.get("title") or video.get("title") or video_id)
    url = str(info.get("webpage_url") or video["url"])
    language = "en-orig" if ".en-orig." in caption_path.name else "en"
    automatic_languages = info.get("automatic_captions") or {}
    caption_kind = "automatic" if language in automatic_languages else "provided"
    header = [
        f"Title: {title}",
        f"Source: {url}",
        f"Channel: {info.get('channel') or 'English Goal Podcast'}",
        f"Captions: YouTube {'automatic ' if caption_kind == 'automatic' else ''}captions ({language})",
        "",
    ]
    transcript_path.write_text(
        "\n".join(header)
        + "\n".join(f"[{timestamp(cue['start_ms'])}] {cue['text']}" for cue in cues)
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "video_id": video_id,
        "title": title,
        "url": url,
        "channel": str(info.get("channel") or "English Goal Podcast"),
        "channel_id": resolved_channel_id,
        "upload_date": info.get("upload_date"),
        "duration_seconds": info.get("duration") or video.get("duration"),
        "caption_language": language,
        "caption_kind": caption_kind,
        "caption_path": str(caption_path.resolve()),
        "transcript_path": str(transcript_path.resolve()),
        "word_count": word_count,
        "prepared_at": datetime.now().astimezone().isoformat(),
    }
    _atomic_write_json(metadata_dir / f"{video_id}.json", manifest)
    info_path.unlink(missing_ok=True)
    return manifest


def _existing_manifest(data_dir: Path, assignment: dict[str, Any]) -> dict[str, Any] | None:
    video_id = str(assignment.get("video_id") or "")
    metadata_path = data_dir / "metadata" / f"{video_id}.json"
    if not metadata_path.exists():
        return None
    manifest = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not Path(str(manifest.get("transcript_path") or "")).is_file():
        return None
    return {**manifest, "lesson_date": assignment.get("lesson_date")}


def prepare_daily(
    data_dir: Path,
    *,
    lesson_date: str,
    channel_url: str = DEFAULT_CHANNEL_URL,
    playlist_limit: int = DEFAULT_PLAYLIST_LIMIT,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Idempotently assign and download one transcript for ``lesson_date``."""
    data_dir.mkdir(parents=True, exist_ok=True)
    state_path = data_dir / "state.json"
    lock_path = data_dir / "state.lock"
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _load_state(state_path)
        existing = state["assignments"].get(lesson_date)
        if isinstance(existing, dict):
            manifest = _existing_manifest(data_dir, existing)
            if manifest is not None:
                return manifest

        entries = fetch_channel_entries(
            channel_url, limit=playlist_limit, runner=runner
        )
        candidates = select_unassigned(entries, state)
        errors: list[str] = []
        for video in candidates:
            try:
                manifest = download_transcript(video, data_dir, runner=runner)
            except (RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"{video['id']}: {exc}")
                continue
            assignment = {
                "lesson_date": lesson_date,
                "video_id": manifest["video_id"],
                "title": manifest["title"],
                "url": manifest["url"],
                "prepared_at": manifest["prepared_at"],
                "delivered_at": None,
            }
            state["assignments"][lesson_date] = assignment
            state["channel_url"] = channel_url
            _atomic_write_json(state_path, state)
            return {**manifest, "lesson_date": lesson_date}
        detail = "; ".join(errors[:3]) or "all listed videos were already assigned"
        raise RuntimeError(f"Could not prepare a transcript-backed episode: {detail}")


def mark_delivered(data_dir: Path, video_id: str, lesson_date: str) -> dict[str, Any]:
    """Record that the composed daily lesson used the assigned transcript."""
    state_path = data_dir / "state.json"
    lock_path = data_dir / "state.lock"
    data_dir.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _load_state(state_path)
        assignment = state["assignments"].get(lesson_date)
        if not isinstance(assignment, dict) or assignment.get("video_id") != video_id:
            raise ValueError(
                f"{video_id} is not the assigned episode for {lesson_date}"
            )
        if not assignment.get("delivered_at"):
            assignment["delivered_at"] = datetime.now().astimezone().isoformat()
            _atomic_write_json(state_path, state)
        return assignment


def status(data_dir: Path) -> dict[str, Any]:
    state = _load_state(data_dir / "state.json")
    assignments = state.get("assignments", {})
    return {
        "channel_url": state.get("channel_url", DEFAULT_CHANNEL_URL),
        "assignment_count": len(assignments),
        "delivered_count": sum(
            1
            for item in assignments.values()
            if isinstance(item, dict) and item.get("delivered_at")
        ),
        "latest": assignments[max(assignments)] if assignments else None,
        "transcript_count": len(list((data_dir / "transcripts").glob("*.txt"))),
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("ENGLISH_PODCAST_DATA_DIR", DEFAULT_DATA_DIR)),
    )
    parser.add_argument("--channel-url", default=DEFAULT_CHANNEL_URL)
    parser.add_argument("--date", default=date.today().isoformat())
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="download today's assigned transcript")
    prepare.add_argument("--playlist-limit", type=int, default=DEFAULT_PLAYLIST_LIMIT)
    delivered = subparsers.add_parser("mark", help="mark today's lesson delivered")
    delivered.add_argument("--video-id", required=True)
    subparsers.add_parser("status", help="show local assignment and transcript counts")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    data_dir = args.data_dir.expanduser().resolve()
    if args.command == "prepare":
        result = prepare_daily(
            data_dir,
            lesson_date=args.date,
            channel_url=args.channel_url,
            playlist_limit=args.playlist_limit,
        )
    elif args.command == "mark":
        result = mark_delivered(data_dir, args.video_id, args.date)
    else:
        result = status(data_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
