#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Ingest arXiv and Hugging Face paper metadata into a local SQLite catalog.

Purpose
-------
This is the operational boundary between public paper sources and Hermes. It
collects metadata only, records source/run provenance, and never invokes an LLM
or downloads PDFs. Hermes consumes the resulting database read-only through
``papers_digest.py``.

The script is standalone so it can run from ``~/.hermes/scripts/`` under a
systemd timer. On its first run it can preserve the existing Subscribe-Papers
catalog by importing it into the new runtime database.

Usage
-----
    python papers_ingest.py
    python papers_ingest.py --source arxiv --arxiv-limit 200
    python papers_ingest.py --status
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_DB_PATH = os.path.expanduser("~/.hermes/data/papers/papers.db")
DEFAULT_LEGACY_DB_PATH = "/home/david/workspace/Subscribe-Papers/data/papers.db"
DEFAULT_CATEGORIES: tuple[str, ...] = ("cs.AI", "cs.CL", "cs.LG", "cs.CV")

ARXIV_API = "https://export.arxiv.org/api/query"
HF_DAILY_PAPERS_API = "https://huggingface.co/api/daily_papers"
USER_AGENT = "david-agentic-ai/papers-ingest (personal research assistant)"

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"

# The score is a deterministic pre-filter, not the final recommendation. Hermes
# adds personal judgement only after the small candidate set has been retrieved.
INTEREST_TERMS: tuple[tuple[str, int], ...] = (
    ("browser agent", 10),
    ("web agent", 10),
    ("computer use", 10),
    ("model context protocol", 10),
    ("mcp", 8),
    ("vision-language", 8),
    ("vision language", 8),
    ("large vision model", 8),
    ("multimodal", 7),
    ("multi-modal", 7),
    ("video generation", 7),
    ("tool use", 7),
    ("tool calling", 7),
    ("grpo", 7),
    ("reinforcement learning", 5),
    ("reasoning", 5),
    ("retrieval augmented", 5),
    ("rag", 4),
    ("large language model", 4),
    ("llm", 4),
    ("vision model", 4),
    ("vlm", 4),
    ("agent", 3),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_space(value: str | None) -> str:
    return " ".join((value or "").split())


def canonical_arxiv_id(value: str) -> str:
    """Return an arXiv identifier without URL, PDF suffix, or version suffix."""
    paper_id = (value or "").strip().rstrip("/")
    if "/abs/" in paper_id:
        paper_id = paper_id.split("/abs/", 1)[1]
    elif "/pdf/" in paper_id:
        paper_id = paper_id.split("/pdf/", 1)[1]
    paper_id = paper_id.removesuffix(".pdf")
    return re.sub(r"v\d+$", "", paper_id)


def relevance_score(title: str, abstract: str) -> int:
    """Score David's current LLM/LVM/agent interests using bounded term matches."""
    haystack = f"{title} {abstract}".lower()
    score = 0
    for term, weight in INTEREST_TERMS:
        pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        if re.search(pattern, haystack):
            score += weight
    return score


def _merge_sources(existing: str | None, incoming: str) -> str:
    known_order = ("arXiv", "HuggingFace", "Legacy")
    sources = {part for part in (existing or "").split("+") if part}
    sources.add(incoming)
    ordered = [source for source in known_order if source in sources]
    ordered.extend(sorted(sources - set(known_order)))
    return "+".join(ordered)


def _json_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if not value:
        return []
    try:
        decoded = json.loads(str(value))
        if isinstance(decoded, list):
            return [str(item) for item in decoded if str(item)]
    except (json.JSONDecodeError, TypeError):
        pass
    return [part.strip() for part in str(value).split(",") if part.strip()]


def connect(db_path: str) -> sqlite3.Connection:
    """Open the writable catalog, creating its parent and schema as needed."""
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    ensure_schema(conn)
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the v2 catalog and add v2 columns when pointed at a legacy DB."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS papers (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            published_date TEXT,
            authors TEXT,
            abstract TEXT,
            pdf_path TEXT,
            full_text TEXT,
            analysis_methodology TEXT,
            analysis_novelty TEXT,
            analysis_flaws TEXT,
            upvotes INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT,
            pdf_url TEXT,
            primary_category TEXT,
            categories TEXT DEFAULT '[]',
            relevance_score INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS paper_sources (
            paper_id TEXT NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT,
            popularity INTEGER DEFAULT 0,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            PRIMARY KEY (paper_id, source),
            FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ingestion_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL,
            source_counts TEXT DEFAULT '{}',
            inserted_count INTEGER DEFAULT 0,
            updated_count INTEGER DEFAULT 0,
            unchanged_count INTEGER DEFAULT 0,
            errors TEXT DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS ingestion_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        """
    )
    additions = {
        "updated_at": "TEXT",
        "pdf_url": "TEXT",
        "primary_category": "TEXT",
        "categories": "TEXT DEFAULT '[]'",
        "relevance_score": "INTEGER DEFAULT 0",
    }
    existing = _columns(conn, "papers")
    for name, declaration in additions.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE papers ADD COLUMN {name} {declaration}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_papers_published "
        "ON papers(published_date DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_papers_relevance "
        "ON papers(relevance_score DESC, published_date DESC)"
    )
    conn.commit()


def _request_bytes(url: str, timeout: int = 20, retries: int = 3) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/atom+xml"},
    )
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # network failures are summarized in run history
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def parse_arxiv_feed(payload: bytes) -> list[dict]:
    """Normalize an arXiv Atom response into catalog records."""
    root = ET.fromstring(payload)
    papers: list[dict] = []
    for entry in root.findall(f"{ATOM}entry"):
        raw_id = entry.findtext(f"{ATOM}id", "")
        paper_id = canonical_arxiv_id(raw_id)
        title = normalize_space(entry.findtext(f"{ATOM}title", ""))
        if not paper_id or not title:
            continue
        categories = [
            node.attrib.get("term", "")
            for node in entry.findall(f"{ATOM}category")
            if node.attrib.get("term")
        ]
        authors = [
            normalize_space(node.findtext(f"{ATOM}name", ""))
            for node in entry.findall(f"{ATOM}author")
        ]
        links = {
            node.attrib.get("rel", ""): node.attrib.get("href", "")
            for node in entry.findall(f"{ATOM}link")
        }
        primary = entry.find(f"{ARXIV}primary_category")
        primary_category = primary.attrib.get("term", "") if primary is not None else ""
        published = entry.findtext(f"{ATOM}published", "")
        updated = entry.findtext(f"{ATOM}updated", "")
        papers.append(
            {
                "id": paper_id,
                "source": "arXiv",
                "title": title,
                "url": links.get("alternate") or f"https://arxiv.org/abs/{paper_id}",
                "source_url": links.get("alternate") or f"https://arxiv.org/abs/{paper_id}",
                "pdf_url": links.get("related") or f"https://arxiv.org/pdf/{paper_id}.pdf",
                "published_date": published[:10],
                "updated_at": updated,
                "authors": ", ".join(author for author in authors if author),
                "abstract": normalize_space(entry.findtext(f"{ATOM}summary", "")),
                "primary_category": primary_category,
                "categories": categories,
                "upvotes": 0,
            }
        )
    return papers


def fetch_arxiv(
    categories: Sequence[str] = DEFAULT_CATEGORIES,
    limit: int = 200,
    timeout: int = 20,
) -> list[dict]:
    query = " OR ".join(f"cat:{category}" for category in categories)
    params = {
        "search_query": query,
        "start": "0",
        "max_results": str(limit),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    payload = _request_bytes(
        f"{ARXIV_API}?{urllib.parse.urlencode(params)}", timeout=timeout
    )
    return parse_arxiv_feed(payload)


def parse_hf_daily_papers(payload: bytes, limit: int = 50) -> list[dict]:
    """Normalize Hugging Face Daily Papers JSON into catalog records."""
    data = json.loads(payload.decode("utf-8"))
    papers: list[dict] = []
    for item in data if isinstance(data, list) else []:
        info = item.get("paper") or {}
        paper_id = canonical_arxiv_id(str(info.get("id") or ""))
        title = normalize_space(info.get("title"))
        if not paper_id or not title:
            continue
        raw_authors = info.get("authors") or []
        authors = [
            normalize_space(author.get("name") if isinstance(author, dict) else str(author))
            for author in raw_authors
        ]
        published = str(item.get("publishedAt") or info.get("publishedAt") or "")
        upvotes = int(info.get("upvotes") or item.get("upvotes") or 0)
        papers.append(
            {
                "id": paper_id,
                "source": "HuggingFace",
                "title": title,
                "url": f"https://huggingface.co/papers/{paper_id}",
                "source_url": f"https://huggingface.co/papers/{paper_id}",
                "pdf_url": f"https://arxiv.org/pdf/{paper_id}.pdf",
                "published_date": published[:10],
                "updated_at": published,
                "authors": ", ".join(author for author in authors if author),
                "abstract": normalize_space(info.get("summary")),
                "primary_category": "",
                "categories": [],
                "upvotes": upvotes,
            }
        )
    papers.sort(key=lambda paper: paper["upvotes"], reverse=True)
    return papers[:limit]


def fetch_huggingface(limit: int = 50, timeout: int = 20) -> list[dict]:
    payload = _request_bytes(HF_DAILY_PAPERS_API, timeout=timeout)
    return parse_hf_daily_papers(payload, limit=limit)


def _prefer(incoming: str | None, existing: str | None, force: bool) -> str:
    incoming = incoming or ""
    existing = existing or ""
    return incoming if incoming and (force or not existing) else existing


def upsert_paper(conn: sqlite3.Connection, paper: dict) -> str:
    """Merge one record and source observation; return insert/update/unchanged."""
    paper_id = canonical_arxiv_id(str(paper.get("id") or ""))
    if not paper_id or not normalize_space(paper.get("title")):
        raise ValueError("paper requires a valid id and title")

    incoming_source = str(paper.get("source") or "Legacy")
    existing_row = conn.execute(
        "SELECT * FROM papers WHERE id = ?", (paper_id,)
    ).fetchone()
    existing = dict(existing_row) if existing_row else {}
    arxiv_is_authoritative = incoming_source == "arXiv"

    existing_categories = _json_list(existing.get("categories"))
    categories = sorted(set(existing_categories + _json_list(paper.get("categories"))))
    title = _prefer(
        normalize_space(paper.get("title")), existing.get("title"), arxiv_is_authoritative
    )
    abstract = _prefer(
        normalize_space(paper.get("abstract")),
        existing.get("abstract"),
        arxiv_is_authoritative,
    )
    authors = _prefer(paper.get("authors"), existing.get("authors"), arxiv_is_authoritative)
    url = _prefer(paper.get("url"), existing.get("url"), arxiv_is_authoritative)
    published_values = [
        value
        for value in (existing.get("published_date"), paper.get("published_date"))
        if value
    ]
    published_date = min(published_values) if published_values else ""
    updated_values = [
        value for value in (existing.get("updated_at"), paper.get("updated_at")) if value
    ]
    source = _merge_sources(existing.get("source"), incoming_source)
    upvotes = max(int(existing.get("upvotes") or 0), int(paper.get("upvotes") or 0))
    now = utc_now()

    merged = {
        "id": paper_id,
        "source": source,
        "title": title,
        "url": url,
        "published_date": published_date,
        "authors": authors,
        "abstract": abstract,
        "pdf_path": _prefer(paper.get("pdf_path"), existing.get("pdf_path"), False),
        "full_text": _prefer(paper.get("full_text"), existing.get("full_text"), False),
        "analysis_methodology": _prefer(
            paper.get("analysis_methodology"), existing.get("analysis_methodology"), False
        ),
        "analysis_novelty": _prefer(
            paper.get("analysis_novelty"), existing.get("analysis_novelty"), False
        ),
        "analysis_flaws": _prefer(
            paper.get("analysis_flaws"), existing.get("analysis_flaws"), False
        ),
        "upvotes": upvotes,
        "created_at": existing.get("created_at") or paper.get("created_at") or now,
        "updated_at": max(updated_values) if updated_values else now,
        "pdf_url": _prefer(paper.get("pdf_url"), existing.get("pdf_url"), arxiv_is_authoritative),
        "primary_category": _prefer(
            paper.get("primary_category"),
            existing.get("primary_category"),
            arxiv_is_authoritative,
        ),
        "categories": json.dumps(categories, ensure_ascii=False),
        "relevance_score": relevance_score(title, abstract),
    }

    comparable_fields = tuple(key for key in merged if key not in {"id", "updated_at"})
    unchanged = bool(existing) and all(
        (existing.get(key) or "") == (merged.get(key) or "") for key in comparable_fields
    )
    if not existing:
        columns = ", ".join(merged)
        placeholders = ", ".join("?" for _ in merged)
        conn.execute(
            f"INSERT INTO papers ({columns}) VALUES ({placeholders})",
            tuple(merged.values()),
        )
        action = "inserted"
    elif unchanged:
        action = "unchanged"
    else:
        assignments = ", ".join(f"{key} = ?" for key in merged if key != "id")
        values = [merged[key] for key in merged if key != "id"]
        conn.execute(
            f"UPDATE papers SET {assignments} WHERE id = ?",
            (*values, paper_id),
        )
        action = "updated"

    source_url = str(paper.get("source_url") or paper.get("url") or "")
    conn.execute(
        """
        INSERT INTO paper_sources
            (paper_id, source, source_url, popularity, first_seen_at, last_seen_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(paper_id, source) DO UPDATE SET
            source_url = CASE
                WHEN excluded.source_url != '' THEN excluded.source_url
                ELSE paper_sources.source_url
            END,
            popularity = MAX(paper_sources.popularity, excluded.popularity),
            last_seen_at = excluded.last_seen_at
        """,
        (paper_id, incoming_source, source_url, int(paper.get("upvotes") or 0), now, now),
    )
    return action


def upsert_many(conn: sqlite3.Connection, papers: Iterable[dict]) -> dict[str, int]:
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    with conn:
        for paper in papers:
            counts[upsert_paper(conn, paper)] += 1
    return counts


def import_legacy_once(conn: sqlite3.Connection, legacy_db_path: str) -> dict[str, int]:
    """Import the legacy catalog exactly once without modifying its database."""
    legacy_path = Path(legacy_db_path).expanduser().resolve()
    marker = f"legacy-import:{legacy_path}"
    if conn.execute(
        "SELECT 1 FROM ingestion_meta WHERE key = ?", (marker,)
    ).fetchone():
        return {"inserted": 0, "updated": 0, "unchanged": 0}
    if not legacy_path.is_file():
        return {"inserted": 0, "updated": 0, "unchanged": 0}

    source = sqlite3.connect(f"file:{legacy_path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in source.execute("SELECT * FROM papers")]
    finally:
        source.close()

    legacy_root = legacy_path.parent.parent
    normalized: list[dict] = []
    for row in rows:
        pdf_path = row.get("pdf_path") or ""
        if pdf_path and not os.path.isabs(pdf_path):
            pdf_path = str((legacy_root / pdf_path).resolve())
        row["pdf_path"] = pdf_path
        row["source"] = row.get("source") or "Legacy"
        row["source_url"] = row.get("url") or ""
        normalized.append(row)

    counts = upsert_many(conn, normalized)
    with conn:
        conn.execute(
            "INSERT INTO ingestion_meta (key, value) VALUES (?, ?)",
            (marker, json.dumps({"imported_at": utc_now(), "rows": len(rows)})),
        )
    return counts


def _start_run(conn: sqlite3.Connection) -> int:
    with conn:
        cursor = conn.execute(
            "INSERT INTO ingestion_runs (started_at, status) VALUES (?, 'running')",
            (utc_now(),),
        )
    return int(cursor.lastrowid)


def _finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    source_counts: dict[str, int],
    actions: dict[str, int],
    errors: list[str],
) -> None:
    with conn:
        conn.execute(
            """
            UPDATE ingestion_runs
            SET completed_at = ?, status = ?, source_counts = ?,
                inserted_count = ?, updated_count = ?, unchanged_count = ?,
                errors = ?
            WHERE id = ?
            """,
            (
                utc_now(),
                status,
                json.dumps(source_counts, sort_keys=True),
                actions["inserted"],
                actions["updated"],
                actions["unchanged"],
                json.dumps(errors, ensure_ascii=False),
                run_id,
            ),
        )


def ingest(
    db_path: str,
    *,
    sources: Sequence[str] = ("arxiv", "huggingface"),
    categories: Sequence[str] = DEFAULT_CATEGORIES,
    arxiv_limit: int = 200,
    hf_limit: int = 50,
    timeout: int = 20,
    legacy_db_path: str | None = DEFAULT_LEGACY_DB_PATH,
) -> dict:
    """Run configured sources independently and persist a durable run summary."""
    conn = connect(db_path)
    try:
        legacy_counts = {"inserted": 0, "updated": 0, "unchanged": 0}
        if legacy_db_path:
            legacy_counts = import_legacy_once(conn, legacy_db_path)

        run_id = _start_run(conn)
        source_counts: dict[str, int] = {}
        actions = dict(legacy_counts)
        errors: list[str] = []
        fetchers = {
            "arxiv": lambda: fetch_arxiv(categories, arxiv_limit, timeout),
            "huggingface": lambda: fetch_huggingface(hf_limit, timeout),
        }
        successful_sources = 0

        for source_name in sources:
            try:
                papers = fetchers[source_name]()
                source_counts[source_name] = len(papers)
                source_actions = upsert_many(conn, papers)
                for key in actions:
                    actions[key] += source_actions[key]
                successful_sources += 1
            except Exception as exc:
                errors.append(f"{source_name}: {type(exc).__name__}: {exc}")
                source_counts[source_name] = 0

        if not errors:
            status = "success"
        elif successful_sources:
            status = "partial"
        else:
            status = "failed"
        _finish_run(conn, run_id, status, source_counts, actions, errors)
        return {
            "run_id": run_id,
            "status": status,
            "sources": source_counts,
            **actions,
            "errors": errors,
        }
    finally:
        conn.close()


def status(db_path: str) -> dict:
    path = Path(db_path).expanduser()
    if not path.is_file():
        return {"database": str(path), "exists": False}
    conn = connect(str(path))
    try:
        row = conn.execute(
            "SELECT * FROM ingestion_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        paper_count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        latest_paper = conn.execute(
            "SELECT MAX(published_date) FROM papers"
        ).fetchone()[0]
        return {
            "database": str(path),
            "exists": True,
            "papers": paper_count,
            "latest_published_date": latest_paper,
            "last_run": dict(row) if row else None,
        }
    finally:
        conn.close()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.environ.get("PAPERS_DB_PATH", DEFAULT_DB_PATH))
    parser.add_argument(
        "--legacy-db",
        default=os.environ.get("PAPERS_LEGACY_DB_PATH", DEFAULT_LEGACY_DB_PATH),
        help="legacy DB imported once; pass an empty string to disable",
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=("arxiv", "huggingface"),
        dest="sources",
        help="source to run; repeat for both (default: both)",
    )
    parser.add_argument("--category", action="append", dest="categories")
    parser.add_argument("--arxiv-limit", type=int, default=200)
    parser.add_argument("--hf-limit", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--status", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.status:
        print(json.dumps(status(args.db), indent=2, ensure_ascii=False))
        return 0
    result = ingest(
        args.db,
        sources=args.sources or ("arxiv", "huggingface"),
        categories=args.categories or DEFAULT_CATEGORIES,
        arxiv_limit=args.arxiv_limit,
        hf_limit=args.hf_limit,
        timeout=args.timeout,
        legacy_db_path=args.legacy_db or None,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
