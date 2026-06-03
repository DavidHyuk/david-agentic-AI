#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Pull live, real-world interview-trend signal for the interview-prep skill.

Why
---
The seeded ``question-bank.md`` is static, so drills drift away from what Staff/
Senior MLE candidates are actually asked *this month*. This module is the
deterministic data layer (same philosophy as ``papers_digest.py``): it gathers
fresh, high-signal material from free, no-auth public sources and hands the LLM a
ranked "trend brief" to ground each drill in. The LLM adds judgement on top; the
fetching/ranking stays here so it is testable and cheap.

Sources (all free, no API key):
  * Hacker News (Algolia API) — discourse on system design / ML interviews / hiring.
  * GitHub search API        — trending interview-prep repos + hot ML tooling.
  * Subscribe-Papers DB      — frontier-pillar grounding (reuses papers_digest).

Design
------
Network fetches are isolated from parsing/ranking so the suite can run offline with
fixtures. Every source degrades gracefully: a network or parse failure yields an
empty list for that source instead of crashing the drill.

Usage:
  python interview_trends.py --mode brief                    # fetch all, cache, print
  python interview_trends.py --mode brief --pillar system_design
  python interview_trends.py --mode show                     # print last cached brief
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DEFAULT_CACHE_PATH = os.path.expanduser("~/.hermes/data/interview/trends.json")
DEFAULT_PAPERS_DB = "/home/david/workspace/Subscribe-Papers/data/papers.db"

HN_ENDPOINT = "https://hn.algolia.com/api/v1/search"
GITHUB_ENDPOINT = "https://api.github.com/search/repositories"

# Per-pillar query plan. Each pillar pulls from the source(s) that carry the best
# signal for it. Keep queries tight so results stay on-topic.
PILLAR_QUERIES: dict[str, dict] = {
    "system_design": {
        "hn": ["system design interview", "ML system design", "scalable architecture"],
        "github": ["system design interview"],
    },
    "ml_depth": {
        "hn": ["LLM training", "model quantization", "distributed training"],
        "github": ["LLM from scratch", "machine learning interview"],
    },
    "coding": {
        "hn": ["coding interview patterns", "leetcode"],
        "github": ["coding interview", "leetcode patterns"],
    },
    "behavioral": {
        "hn": ["staff engineer", "engineering leadership", "tech lead promotion"],
        "github": [],
    },
    "frontier": {
        "hn": ["LLM agents", "multimodal model", "AI reasoning"],
        "github": ["awesome LLM"],
        "papers": True,  # also pull recent items from the Subscribe-Papers DB
    },
}

_USER_AGENT = "david-agentic-ai/interview-trends (+https://github.com/)"


# --------------------------------------------------------------------------- #
# Network layer (isolated so tests never touch it)                            #
# --------------------------------------------------------------------------- #
def _http_get_json(url: str, timeout: int = 10) -> dict:
    """GET a URL and parse JSON. Raises on any failure (caller handles)."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _unix_days_ago(days: int) -> int:
    return int(datetime.now(timezone.utc).timestamp()) - days * 86400


def fetch_hn(query: str, min_points: int = 20, days: int = 365, limit: int = 5,
             timeout: int = 10) -> list[dict]:
    """Fetch popular-and-recent HN stories for a query. Returns raw Algolia hits.

    Uses a points threshold (quality) plus a recency window (freshness). Network
    or parse failures return an empty list so a drill never breaks on a bad fetch.
    """
    params = {
        "query": query,
        "tags": "story",
        "numericFilters": f"points>{min_points},created_at_i>{_unix_days_ago(days)}",
        "hitsPerPage": str(limit),
    }
    url = f"{HN_ENDPOINT}?{urllib.parse.urlencode(params)}"
    try:
        return _http_get_json(url, timeout).get("hits", [])
    except Exception:
        return []


def fetch_github(query: str, min_stars: int = 50, days: int = 180, limit: int = 5,
                 timeout: int = 10) -> list[dict]:
    """Fetch recently-active, well-starred repos for a query. Returns raw items."""
    pushed_after = datetime.fromtimestamp(_unix_days_ago(days), tz=timezone.utc).strftime("%Y-%m-%d")
    q = f"{query} stars:>{min_stars} pushed:>{pushed_after}"
    params = {"q": q, "sort": "stars", "order": "desc", "per_page": str(limit)}
    url = f"{GITHUB_ENDPOINT}?{urllib.parse.urlencode(params)}"
    try:
        return _http_get_json(url, timeout).get("items", [])
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Pure parse / normalize / rank layer (offline-testable)                      #
# --------------------------------------------------------------------------- #
def normalize_hn(hits: list[dict]) -> list[dict]:
    """Map raw HN hits to the common trend-item shape."""
    out = []
    for h in hits:
        title = (h.get("title") or "").strip()
        if not title:
            continue
        object_id = h.get("objectID", "")
        out.append({
            "source": "hn",
            "title": title,
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={object_id}",
            "score": int(h.get("points") or 0),
            "date": (h.get("created_at") or "")[:10],
            "extra": f"{h.get('num_comments') or 0} comments",
        })
    return out


def normalize_github(items: list[dict]) -> list[dict]:
    """Map raw GitHub repo items to the common trend-item shape."""
    out = []
    for r in items:
        name = (r.get("full_name") or "").strip()
        if not name:
            continue
        out.append({
            "source": "github",
            "title": name,
            "url": r.get("html_url") or "",
            "score": int(r.get("stargazers_count") or 0),
            "date": (r.get("pushed_at") or "")[:10],
            "extra": (r.get("description") or "").strip()[:120],
        })
    return out


def normalize_papers(papers: list[dict]) -> list[dict]:
    """Map Subscribe-Papers rows to the common trend-item shape (frontier pillar)."""
    out = []
    for p in papers:
        title = (p.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "source": "paper",
            "title": title,
            "url": p.get("url") or "",
            "score": int(p.get("upvotes") or 0),
            "date": (p.get("published_date") or p.get("created_at") or "")[:10],
            "extra": "arXiv/HF",
        })
    return out


def rank_items(items: list[dict], limit: int = 6) -> list[dict]:
    """De-duplicate, then interleave sources so no single source dominates.

    GitHub star counts dwarf HN points and paper upvotes, so a global score sort
    would bury fresh discourse under canonical repos. Instead we sort *within* each
    source by score (newest as tiebreak) and round-robin across sources, which keeps
    a healthy mix of "what to study" (repos), "what's discussed" (HN), and "what's
    new" (papers) in the top slots.
    """
    by_source: dict[str, list[dict]] = {}
    seen: set[str] = set()
    for it in items:
        key = it["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        by_source.setdefault(it["source"], []).append(it)

    for bucket in by_source.values():
        bucket.sort(key=lambda x: (x["score"], x["date"]), reverse=True)

    interleaved: list[dict] = []
    buckets = list(by_source.values())
    i = 0
    while len(interleaved) < limit and any(i < len(b) for b in buckets):
        for b in buckets:
            if i < len(b):
                interleaved.append(b[i])
                if len(interleaved) >= limit:
                    break
        i += 1
    return interleaved


# --------------------------------------------------------------------------- #
# Orchestration                                                               #
# --------------------------------------------------------------------------- #
def _fetch_recent_papers(db_path: str, days: int, limit: int) -> list[dict]:
    """Best-effort pull of recent papers via papers_digest (frontier pillar)."""
    try:
        import papers_digest  # staged alongside this script in ~/.hermes/scripts/
        conn = papers_digest.connect(db_path)
        try:
            rows = papers_digest.query_recent(conn, days=days, limit=limit)
            return papers_digest.filter_keywords(rows, papers_digest.DEFAULT_KEYWORDS)
        finally:
            conn.close()
    except Exception:
        return []


def build_pillar_trends(pillar: str, *, per_source: int = 4, top: int = 6,
                        papers_db: str = DEFAULT_PAPERS_DB) -> list[dict]:
    """Gather + rank trend items for a single pillar."""
    plan = PILLAR_QUERIES.get(pillar, {})
    collected: list[dict] = []
    for q in plan.get("hn", []):
        collected += normalize_hn(fetch_hn(q, limit=per_source))
    for q in plan.get("github", []):
        collected += normalize_github(fetch_github(q, limit=per_source))
    if plan.get("papers"):
        collected += normalize_papers(_fetch_recent_papers(papers_db, days=7, limit=per_source))
    return rank_items(collected, limit=top)


def build_trend_brief(pillars: list[str] | None = None,
                      papers_db: str = DEFAULT_PAPERS_DB) -> dict:
    """Build the full trend brief across the requested pillars (default: all)."""
    pillars = pillars or list(PILLAR_QUERIES.keys())
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pillars": {p: build_pillar_trends(p, papers_db=papers_db) for p in pillars},
    }


def save_cache(path: str, brief: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(brief, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_cache(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["brief", "show"], default="brief")
    parser.add_argument("--pillar", default=None,
                        help="limit to one pillar (e.g. system_design); default = all")
    parser.add_argument("--cache", default=os.environ.get("INTERVIEW_TRENDS_CACHE", DEFAULT_CACHE_PATH))
    parser.add_argument("--papers-db", default=os.environ.get("PAPERS_DB", DEFAULT_PAPERS_DB))
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    if args.mode == "show":
        print(json.dumps(load_cache(args.cache), indent=2, ensure_ascii=False))
        return 0
    pillars = [args.pillar] if args.pillar else None
    brief = build_trend_brief(pillars, papers_db=args.papers_db)
    save_cache(args.cache, brief)
    print(json.dumps(brief, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
