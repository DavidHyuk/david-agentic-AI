# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for papers_digest.py against a synthetic Subscribe-Papers DB."""
import sqlite3
from datetime import datetime, timedelta, timezone

import papers_digest as pd


def _make_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE papers (id TEXT PRIMARY KEY, source TEXT, title TEXT, url TEXT,
           published_date TEXT, authors TEXT, abstract TEXT, pdf_path TEXT,
           full_text TEXT, analysis_methodology TEXT, analysis_novelty TEXT,
           analysis_flaws TEXT, upvotes INTEGER DEFAULT 0,
           created_at TEXT DEFAULT CURRENT_TIMESTAMP)"""
    )
    for r in rows:
        conn.execute(
            "INSERT INTO papers (id, source, title, url, published_date, abstract, upvotes) "
            "VALUES (?,?,?,?,?,?,?)",
            (r["id"], r.get("source", "arxiv"), r["title"], r["url"],
             r["published_date"], r.get("abstract", ""), r.get("upvotes", 0)),
        )
    conn.commit()
    conn.close()


def _sample_rows():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    old = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    return [
        {"id": "1", "title": "Scaling LVMs for video", "url": "http://a/1",
         "published_date": today, "abstract": "A large vision model.", "upvotes": 120},
        {"id": "2", "title": "A new LLM agent framework", "url": "http://a/2",
         "published_date": today, "abstract": "Agentic reasoning.", "upvotes": 80},
        {"id": "3", "title": "Protein folding advances", "url": "http://a/3",
         "published_date": old, "abstract": "Biology, no NLP here.", "upvotes": 5},
    ]


def test_query_trending_orders_by_upvotes(tmp_path):
    db = tmp_path / "papers.db"
    _make_db(db, _sample_rows())
    conn = pd.connect(str(db))
    top = pd.query_trending(conn, limit=3)
    conn.close()
    assert [p["id"] for p in top] == ["1", "2", "3"]


def test_query_recent_filters_by_date(tmp_path):
    db = tmp_path / "papers.db"
    _make_db(db, _sample_rows())
    conn = pd.connect(str(db))
    recent = pd.query_recent(conn, days=2, limit=10)
    conn.close()
    ids = {p["id"] for p in recent}
    assert ids == {"1", "2"}  # the 30-day-old paper is excluded


def test_query_recommended_falls_back_for_legacy_schema(tmp_path):
    db = tmp_path / "papers.db"
    _make_db(db, _sample_rows())
    conn = pd.connect(str(db))
    recommended = pd.query_recommended(conn, days=2, limit=10)
    conn.close()
    assert {paper["id"] for paper in recommended} == {"1", "2"}


def test_filter_keywords_matches_title_and_abstract():
    papers = [
        {"title": "Scaling LVMs", "abstract": "vision"},
        {"title": "Protein folding", "abstract": "biology"},
    ]
    kept = pd.filter_keywords(papers, ["lvm", "agent"])
    assert len(kept) == 1 and kept[0]["title"] == "Scaling LVMs"


def test_filter_keywords_empty_returns_all():
    papers = [{"title": "x", "abstract": "y"}]
    assert pd.filter_keywords(papers, []) == papers


def test_build_digest_end_to_end(tmp_path):
    db = tmp_path / "papers.db"
    _make_db(db, _sample_rows())
    md = pd.build_digest(str(db), mode="trending", limit=5,
                         keywords=["llm", "lvm", "agent"])
    assert "Scaling LVMs for video" in md
    assert "Protein folding" not in md   # filtered out by keywords
    assert "http://a/1" in md


def test_missing_db_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        pd.connect(str(tmp_path / "nope.db"))


def test_connect_is_read_only(tmp_path):
    import pytest

    db = tmp_path / "papers.db"
    _make_db(db, _sample_rows())
    conn = pd.connect(str(db))
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM papers")
    conn.close()


def test_trending_without_upvotes_column_falls_back(tmp_path):
    db = tmp_path / "p.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE papers (id TEXT, title TEXT, url TEXT, "
                 "published_date TEXT, abstract TEXT, created_at TEXT)")
    conn.execute("INSERT INTO papers VALUES ('1','LLM thing','u','2026-06-01','a','2026-06-01')")
    conn.commit(); conn.close()
    conn = pd.connect(str(db))
    # Should not raise even though 'upvotes' is absent.
    res = pd.query_trending(conn, limit=5)
    conn.close()
    assert len(res) == 1
