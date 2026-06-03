#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Turn a list of calendar events into a prioritized daily brief.

Purpose
-------
The ``calendar-assistant`` skill fetches events from Google Calendar (via the
``google-calendar`` MCP server), writes them to a JSON list, and runs this module to
sort them, detect overlaps, find free focus slots, and flag high-priority items
(interviews, deadlines, prep). The rendering logic lives here so it is deterministic
and unit-tested, while the agent focuses on fetching and on adding suggestions.

Event shape (all times ISO 8601, local):
    {"summary": str, "start": "2026-06-02T09:00:00", "end": "...", "location": str?}

Input: JSON list of events on stdin or via ``--file``. Output: Markdown brief.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, time, timedelta
from typing import Sequence

# Keywords that bump an event to "priority" in the brief.
PRIORITY_KEYWORDS = (
    "interview",
    "onsite",
    "screen",
    "deadline",
    "due",
    "submit",
    "1:1",
    "review",
    "exam",
    "presentation",
    "demo",
)


def _parse(dt: str) -> datetime:
    """Parse an ISO datetime, tolerating a trailing 'Z'."""
    return datetime.fromisoformat(dt.replace("Z", "+00:00")).replace(tzinfo=None)


def sort_events(events: Sequence[dict]) -> list[dict]:
    return sorted(events, key=lambda e: _parse(e["start"]))


def is_priority(event: dict) -> bool:
    text = f"{event.get('summary', '')} {event.get('location', '')}".lower()
    return any(k in text for k in PRIORITY_KEYWORDS)


def detect_conflicts(events: Sequence[dict]) -> list[tuple[dict, dict]]:
    """Return pairs of events whose time ranges overlap."""
    ordered = sort_events(events)
    conflicts = []
    for i in range(len(ordered)):
        a_start, a_end = _parse(ordered[i]["start"]), _parse(ordered[i]["end"])
        for j in range(i + 1, len(ordered)):
            b_start, b_end = _parse(ordered[j]["start"]), _parse(ordered[j]["end"])
            if b_start >= a_end:
                break  # ordered by start; no later event can overlap this one
            if a_start < b_end and b_start < a_end:
                conflicts.append((ordered[i], ordered[j]))
    return conflicts


def free_slots(
    events: Sequence[dict],
    day_start: str = "09:00",
    day_end: str = "18:00",
    min_minutes: int = 45,
) -> list[dict]:
    """Find gaps of at least ``min_minutes`` within working hours on the events' day."""
    if not events:
        return []
    ordered = sort_events(events)
    day = _parse(ordered[0]["start"]).date()
    h1, m1 = (int(x) for x in day_start.split(":"))
    h2, m2 = (int(x) for x in day_end.split(":"))
    cursor = datetime.combine(day, time(h1, m1))
    window_end = datetime.combine(day, time(h2, m2))
    slots = []
    for e in ordered:
        e_start, e_end = _parse(e["start"]), _parse(e["end"])
        if e_start > cursor:
            gap = min(e_start, window_end)
            if (gap - cursor) >= timedelta(minutes=min_minutes):
                slots.append({"start": cursor.isoformat(), "end": gap.isoformat()})
        cursor = max(cursor, e_end)
        if cursor >= window_end:
            break
    if cursor < window_end and (window_end - cursor) >= timedelta(minutes=min_minutes):
        slots.append({"start": cursor.isoformat(), "end": window_end.isoformat()})
    return slots


def _fmt_range(start: str, end: str) -> str:
    s, e = _parse(start), _parse(end)
    return f"{s.strftime('%H:%M')}–{e.strftime('%H:%M')}"


def to_brief(events: Sequence[dict], day_start: str = "09:00", day_end: str = "18:00") -> str:
    """Render the full daily brief: agenda, priorities, conflicts, free slots."""
    if not events:
        return "*Today's agenda*\n\n_No events on the calendar today._"
    ordered = sort_events(events)
    day = _parse(ordered[0]["start"]).strftime("%a %b %d")
    lines = [f"*Today's agenda — {day}*", ""]
    for e in ordered:
        flag = "⭐ " if is_priority(e) else ""
        loc = f" @ {e['location']}" if e.get("location") else ""
        lines.append(f"• {_fmt_range(e['start'], e['end'])} {flag}{e.get('summary', '(untitled)')}{loc}")

    priorities = [e for e in ordered if is_priority(e)]
    if priorities:
        lines += ["", "*Don't miss*"]
        lines += [f"• {p.get('summary')} at {_parse(p['start']).strftime('%H:%M')}" for p in priorities]

    conflicts = detect_conflicts(ordered)
    if conflicts:
        lines += ["", "*⚠ Overlaps*"]
        for a, b in conflicts:
            lines.append(f"• {a.get('summary')} vs {b.get('summary')}")

    slots = free_slots(ordered, day_start, day_end)
    if slots:
        lines += ["", "*Free focus slots*"]
        lines += [f"• {_fmt_range(s['start'], s['end'])}" for s in slots]
    return "\n".join(lines)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", help="path to events JSON (default: read stdin)")
    parser.add_argument("--day-start", default="09:00")
    parser.add_argument("--day-end", default="18:00")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    raw = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()
    events = json.loads(raw) if raw.strip() else []
    print(to_brief(events, args.day_start, args.day_end))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
