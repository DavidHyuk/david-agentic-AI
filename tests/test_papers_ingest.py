# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Offline tests for the standalone arXiv/Hugging Face ingestion service."""
import json
import sqlite3

import papers_ingest as pi


ARXIV_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2607.12345v2</id>
    <updated>2026-07-24T10:00:00Z</updated>
    <published>2026-07-23T09:00:00Z</published>
    <title>
      A Browser Agent for Multimodal Tasks
    </title>
    <summary>We study computer use with a vision-language model.</summary>
    <author><name>Ada Lovelace</name></author>
    <author><name>Alan Turing</name></author>
    <category term="cs.AI"/>
    <category term="cs.CL"/>
    <arxiv:primary_category term="cs.AI"/>
    <link rel="alternate" href="https://arxiv.org/abs/2607.12345v2"/>
    <link rel="related" href="https://arxiv.org/pdf/2607.12345v2"/>
  </entry>
</feed>
"""


def test_canonical_arxiv_id_removes_urls_pdf_and_version():
    assert pi.canonical_arxiv_id("https://arxiv.org/abs/2607.12345v3") == "2607.12345"
    assert pi.canonical_arxiv_id("https://arxiv.org/pdf/cs/0110053v1.pdf") == "cs/0110053"


def test_parse_arxiv_feed_keeps_abstract_and_categories():
    papers = pi.parse_arxiv_feed(ARXIV_FEED)
    assert len(papers) == 1
    paper = papers[0]
    assert paper["id"] == "2607.12345"
    assert paper["title"] == "A Browser Agent for Multimodal Tasks"
    assert paper["authors"] == "Ada Lovelace, Alan Turing"
    assert paper["primary_category"] == "cs.AI"
    assert paper["categories"] == ["cs.AI", "cs.CL"]
    assert "vision-language" in paper["abstract"]


def test_parse_hf_daily_papers_orders_by_upvotes_and_limits():
    payload = json.dumps(
        [
            {
                "publishedAt": "2026-07-24T00:00:00Z",
                "paper": {
                    "id": "2607.10000",
                    "title": "Less popular",
                    "summary": "An LLM.",
                    "authors": [{"name": "A"}],
                    "upvotes": 2,
                },
            },
            {
                "publishedAt": "2026-07-25T00:00:00Z",
                "paper": {
                    "id": "2607.20000v1",
                    "title": "More popular",
                    "summary": "A web agent.",
                    "authors": [{"name": "B"}],
                    "upvotes": 20,
                },
            },
        ]
    ).encode()
    papers = pi.parse_hf_daily_papers(payload, limit=1)
    assert [paper["id"] for paper in papers] == ["2607.20000"]
    assert papers[0]["upvotes"] == 20


def test_relevance_score_prioritizes_browser_agent():
    high = pi.relevance_score("A Browser Agent", "Computer use with a VLM")
    low = pi.relevance_score("Protein Folding", "A biology benchmark")
    assert high > low
    assert low == 0


def test_upsert_deduplicates_sources_and_preserves_hf_popularity(tmp_path):
    conn = pi.connect(str(tmp_path / "papers.db"))
    hf = {
        "id": "2607.12345",
        "source": "HuggingFace",
        "title": "HF title",
        "url": "https://huggingface.co/papers/2607.12345",
        "source_url": "https://huggingface.co/papers/2607.12345",
        "published_date": "2026-07-24",
        "abstract": "A browser agent.",
        "upvotes": 42,
    }
    arxiv = pi.parse_arxiv_feed(ARXIV_FEED)[0]
    assert pi.upsert_paper(conn, hf) == "inserted"
    assert pi.upsert_paper(conn, arxiv) == "updated"
    conn.commit()

    row = dict(conn.execute("SELECT * FROM papers").fetchone())
    sources = conn.execute(
        "SELECT source FROM paper_sources ORDER BY source"
    ).fetchall()
    conn.close()
    assert row["source"] == "arXiv+HuggingFace"
    assert row["title"] == "A Browser Agent for Multimodal Tasks"
    assert row["upvotes"] == 42
    assert [source["source"] for source in sources] == ["HuggingFace", "arXiv"]


def _make_legacy_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE papers (
            id TEXT PRIMARY KEY, source TEXT NOT NULL, title TEXT NOT NULL,
            url TEXT NOT NULL, published_date TEXT, authors TEXT, abstract TEXT,
            pdf_path TEXT, full_text TEXT, analysis_methodology TEXT,
            analysis_novelty TEXT, analysis_flaws TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, upvotes INTEGER DEFAULT 0
        )"""
    )
    conn.execute(
        """INSERT INTO papers
           (id, source, title, url, published_date, abstract, pdf_path, upvotes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "2501.00001",
            "HuggingFace",
            "Legacy LLM paper",
            "https://huggingface.co/papers/2501.00001",
            "2025-01-01",
            "An agent paper.",
            "data/pdfs/2501.00001.pdf",
            9,
        ),
    )
    conn.commit()
    conn.close()


def test_import_legacy_once_preserves_rows_and_normalizes_pdf_path(tmp_path):
    legacy_root = tmp_path / "legacy"
    (legacy_root / "data").mkdir(parents=True)
    legacy_db = legacy_root / "data" / "papers.db"
    _make_legacy_db(legacy_db)
    conn = pi.connect(str(tmp_path / "new" / "papers.db"))

    first = pi.import_legacy_once(conn, str(legacy_db))
    second = pi.import_legacy_once(conn, str(legacy_db))
    row = dict(conn.execute("SELECT * FROM papers").fetchone())
    conn.close()
    assert first["inserted"] == 1
    assert second == {"inserted": 0, "updated": 0, "unchanged": 0}
    assert row["upvotes"] == 9
    assert row["pdf_path"] == str(legacy_root / "data/pdfs/2501.00001.pdf")


def test_connect_upgrades_a_legacy_schema_in_place(tmp_path):
    db = tmp_path / "legacy.db"
    _make_legacy_db(db)
    conn = pi.connect(str(db))
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(papers)")}
    conn.close()
    assert {"relevance_score", "categories", "updated_at"} <= columns


def test_ingest_records_partial_source_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(pi, "fetch_arxiv", lambda *args: pi.parse_arxiv_feed(ARXIV_FEED))

    def fail_hf(*args):
        raise TimeoutError("offline")

    monkeypatch.setattr(pi, "fetch_huggingface", fail_hf)
    db = tmp_path / "papers.db"
    result = pi.ingest(str(db), legacy_db_path=None)
    state = pi.status(str(db))
    assert result["status"] == "partial"
    assert result["inserted"] == 1
    assert state["papers"] == 1
    assert state["last_run"]["status"] == "partial"


def test_status_reports_missing_database(tmp_path):
    result = pi.status(str(tmp_path / "missing.db"))
    assert result["exists"] is False
