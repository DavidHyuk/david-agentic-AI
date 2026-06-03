#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Query the Subscribe-Papers SQLite database and emit a Markdown digest.

Purpose
-------
This is the deterministic, zero-LLM data layer behind the ``papers-digest`` Hermes
skill. The skill runs this script to pull recent / trending LLM & LVM papers out of
the existing Subscribe-Papers database, then layers its own analysis and
interview-relevance commentary on top of the structured output.

Keeping the data extraction in a standalone, importable module (rather than inline
in the skill prompt) means it is testable, cheap to run on a schedule, and easy to
maintain as the Subscribe-Papers schema evolves.

Usage
-----
    python papers_digest.py --mode trending --limit 8
    python papers_digest.py --mode recent --days 2 --keywords LLM LVM agent
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

DEFAULT_DB_PATH = "/home/david/workspace/Subscribe-Papers/data/papers.db"

# Topics David cares about for Staff/Senior MLE interviews + research interests.
DEFAULT_KEYWORDS: tuple[str, ...] = (
    "LLM",
    "LVM",
    "vision",
    "multimodal",
    "agent",
    "reasoning",
    "RAG",
    "fine-tuning",
)


def connect(db_path: str) -> sqlite3.Connection:
    """Open the papers DB read-only-ish with row access by column name."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"papers database not found at {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    return column in cols


def query_recent(
    conn: sqlite3.Connection, days: int = 2, limit: int = 10
) -> list[dict]:
    """Return papers published within the last ``days`` days, newest first.

    Falls back to ``created_at`` ordering when ``published_date`` is missing/empty.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        """
        SELECT * FROM papers
        WHERE COALESCE(published_date, created_at, '') >= ?
        ORDER BY COALESCE(published_date, created_at, '') DESC
        LIMIT ?
        """,
        (cutoff, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def query_trending(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """Return the most upvoted papers (Hugging Face popularity signal)."""
    if not _has_column(conn, "papers", "upvotes"):
        return query_recent(conn, days=7, limit=limit)
    rows = conn.execute(
        """
        SELECT * FROM papers
        ORDER BY COALESCE(upvotes, 0) DESC,
                 COALESCE(published_date, created_at, '') DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def filter_keywords(papers: Iterable[dict], keywords: Sequence[str]) -> list[dict]:
    """Keep papers whose title or abstract mentions any keyword (case-insensitive).

    An empty keyword list is treated as "no filter" and returns papers unchanged.
    """
    kws = [k.lower() for k in keywords if k.strip()]
    if not kws:
        return list(papers)
    out = []
    for p in papers:
        haystack = f"{p.get('title', '')} {p.get('abstract', '')}".lower()
        if any(k in haystack for k in kws):
            out.append(p)
    return out


def _short(text: str | None, length: int = 280) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


def to_markdown(papers: Sequence[dict], title: str) -> str:
    """Render a compact, WhatsApp-friendly Markdown digest of the papers."""
    if not papers:
        return f"*{title}*\n\n_No matching papers found._"
    lines = [f"*{title}* ({len(papers)})", ""]
    for i, p in enumerate(papers, 1):
        upv = p.get("upvotes")
        badge = f" · ⬆ {upv}" if upv else ""
        date = p.get("published_date") or p.get("created_at") or ""
        date = str(date)[:10]
        lines.append(f"{i}. *{_short(p.get('title'), 160)}*{badge}")
        meta = " · ".join(x for x in [date, p.get("source", "")] if x)
        if meta:
            lines.append(f"   {meta}")
        if p.get("abstract"):
            lines.append(f"   {_short(p.get('abstract'))}")
        if p.get("url"):
            lines.append(f"   {p['url']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_digest(
    db_path: str,
    mode: str = "trending",
    days: int = 2,
    limit: int = 10,
    keywords: Sequence[str] | None = None,
) -> str:
    """End-to-end: connect, query, filter, render. Returns Markdown."""
    keywords = list(DEFAULT_KEYWORDS) if keywords is None else list(keywords)
    conn = connect(db_path)
    try:
        if mode == "recent":
            papers = query_recent(conn, days=days, limit=max(limit * 3, limit))
            heading = f"Recent papers (last {days}d)"
        else:
            papers = query_trending(conn, limit=max(limit * 3, limit))
            heading = "Trending papers"
        papers = filter_keywords(papers, keywords)[:limit]
        return to_markdown(papers, heading)
    finally:
        conn.close()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.environ.get("PAPERS_DB_PATH", DEFAULT_DB_PATH))
    parser.add_argument("--mode", choices=["trending", "recent"], default="trending")
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--keywords", nargs="*", default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        print(build_digest(args.db, args.mode, args.days, args.limit, args.keywords))
    except FileNotFoundError as exc:
        print(f"[error] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
