#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Query the Hermes paper catalog and emit a compact Markdown digest.

Purpose
-------
This is the deterministic, zero-LLM data layer behind the ``papers-digest`` Hermes
skill. The skill runs this script to pull recent / recommended LLM & LVM papers
collected by ``papers_ingest.py``, then layers its own analysis and
interview-relevance commentary on top of the structured output. The schema stays
compatible with the legacy Subscribe-Papers database during migration.

Keeping the data extraction in a standalone, importable module (rather than inline
in the skill prompt) means it is testable, cheap to run on a schedule, and easy to
maintain as the paper-catalog schema evolves.

Usage
-----
    python papers_digest.py --mode recommended --days 4 --limit 8
    python papers_digest.py --mode recent --days 2 --keywords LLM LVM agent
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_DB_PATH = os.path.expanduser("~/.hermes/data/papers/papers.db")
LEGACY_DB_PATH = "/home/david/workspace/Subscribe-Papers/data/papers.db"

# Topics David cares about for Staff/Senior MLE interviews + research interests.
DEFAULT_KEYWORDS: tuple[str, ...] = (
    "LLM",
    "LVM",
    "vision",
    "multimodal",
    "vision-language",
    "VLM",
    "agent",
    "browser agent",
    "web agent",
    "computer use",
    "MCP",
    "GRPO",
    "reasoning",
    "RAG",
    "fine-tuning",
)


def connect(db_path: str) -> sqlite3.Connection:
    """Open the papers DB strictly read-only with row access by column name."""
    path = Path(db_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"papers database not found at {db_path}")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
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
        # Older Subscribe-Papers schemas have no popularity signal.  Preserve the
        # meaning of "trending" as the latest available items instead of returning
        # an empty digest solely because the database has not been updated recently.
        rows = conn.execute(
            """
            SELECT * FROM papers
            ORDER BY COALESCE(published_date, created_at, '') DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
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


def query_recommended(
    conn: sqlite3.Connection, days: int = 4, limit: int = 10
) -> list[dict]:
    """Return fresh papers ranked by personal relevance, then HF popularity."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    if not _has_column(conn, "papers", "relevance_score"):
        return query_recent(conn, days=days, limit=limit)
    rows = conn.execute(
        """
        SELECT * FROM papers
        WHERE COALESCE(published_date, created_at, '') >= ?
        ORDER BY COALESCE(relevance_score, 0) DESC,
                 COALESCE(upvotes, 0) DESC,
                 COALESCE(published_date, created_at, '') DESC
        LIMIT ?
        """,
        (cutoff, limit),
    ).fetchall()
    return [dict(row) for row in rows]


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
    days: int = 4,
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
        elif mode == "recommended":
            papers = query_recommended(conn, days=days, limit=max(limit * 3, limit))
            heading = f"Recommended papers (last {days}d)"
        else:
            papers = query_trending(conn, limit=max(limit * 3, limit))
            heading = "Trending papers"
        papers = filter_keywords(papers, keywords)[:limit]
        return to_markdown(papers, heading)
    finally:
        conn.close()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    runtime_default = DEFAULT_DB_PATH if os.path.exists(DEFAULT_DB_PATH) else LEGACY_DB_PATH
    parser.add_argument("--db", default=os.environ.get("PAPERS_DB_PATH", runtime_default))
    parser.add_argument(
        "--mode",
        choices=["recommended", "trending", "recent"],
        default="recommended",
    )
    parser.add_argument("--days", type=int, default=4)
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
