# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for interview_trends.py: normalization, source-diverse ranking, cache,
and pillar orchestration with the network layer stubbed out (no live calls)."""
import interview_trends as it


# --- normalization ---------------------------------------------------------- #
def test_normalize_hn_shape_and_url_fallback():
    hits = [
        {"title": "Sys design guide", "url": "https://x.com/a", "points": 900,
         "created_at": "2026-05-01T00:00:00Z", "num_comments": 12, "objectID": "1"},
        {"title": "No-url story", "points": 50, "created_at": "2026-04-01T00:00:00Z",
         "num_comments": 3, "objectID": "42"},
    ]
    out = it.normalize_hn(hits)
    assert out[0]["source"] == "hn"
    assert out[0]["score"] == 900
    assert out[0]["date"] == "2026-05-01"
    # missing url falls back to the HN item permalink
    assert out[1]["url"] == "https://news.ycombinator.com/item?id=42"


def test_normalize_drops_empty_titles():
    assert it.normalize_hn([{"points": 10, "title": ""}]) == []
    assert it.normalize_github([{"stargazers_count": 10, "full_name": ""}]) == []


def test_normalize_github_shape():
    items = [{"full_name": "a/b", "html_url": "https://github.com/a/b",
              "stargazers_count": 1234, "pushed_at": "2026-06-01T00:00:00Z",
              "description": "x" * 200}]
    out = it.normalize_github(items)
    assert out[0]["source"] == "github" and out[0]["score"] == 1234
    assert len(out[0]["extra"]) <= 120  # description truncated


def test_normalize_papers_shape():
    out = it.normalize_papers([{"title": "Paper A", "url": "http://arxiv/1",
                                "upvotes": 7, "published_date": "2026-06-02"}])
    assert out[0]["source"] == "paper" and out[0]["score"] == 7


# --- ranking ---------------------------------------------------------------- #
def test_rank_dedups_by_title():
    items = [
        {"source": "hn", "title": "Same", "score": 10, "date": "2026-01-01"},
        {"source": "github", "title": "same", "score": 99, "date": "2026-01-02"},
    ]
    assert len(it.rank_items(items, limit=6)) == 1


def test_rank_interleaves_sources_not_pure_score():
    # GitHub scores dwarf HN; a pure score sort would bury all HN items.
    items = (
        [{"source": "github", "title": f"g{i}", "score": 100000 + i, "date": "2026-01-01"} for i in range(5)]
        + [{"source": "hn", "title": f"h{i}", "score": 100 + i, "date": "2026-01-01"} for i in range(5)]
    )
    top = it.rank_items(items, limit=4)
    sources = {x["source"] for x in top}
    assert sources == {"github", "hn"}, "both sources must appear in the top slots"
    # interleave starts with the highest-scoring bucket head, alternating
    assert top[0]["source"] != top[1]["source"]


def test_rank_respects_limit():
    items = [{"source": "hn", "title": f"t{i}", "score": i, "date": "2026-01-01"} for i in range(20)]
    assert len(it.rank_items(items, limit=6)) == 6


# --- orchestration (network stubbed) --------------------------------------- #
def test_build_pillar_trends_without_network(monkeypatch):
    monkeypatch.setattr(it, "fetch_hn",
                        lambda q, **k: [{"title": f"hn::{q}", "points": 30,
                                         "created_at": "2026-05-01T00:00:00Z",
                                         "objectID": "1", "num_comments": 1}])
    monkeypatch.setattr(it, "fetch_github",
                        lambda q, **k: [{"full_name": f"gh/{q}", "stargazers_count": 80,
                                         "html_url": "https://github.com/gh", "pushed_at": "2026-05-02T00:00:00Z",
                                         "description": "d"}])
    monkeypatch.setattr(it, "_fetch_recent_papers", lambda *a, **k: [])
    out = it.build_pillar_trends("coding", top=6)
    assert out and all("title" in x for x in out)
    assert {x["source"] for x in out} == {"hn", "github"}


def test_unknown_pillar_returns_empty(monkeypatch):
    monkeypatch.setattr(it, "fetch_hn", lambda q, **k: [])
    monkeypatch.setattr(it, "fetch_github", lambda q, **k: [])
    assert it.build_pillar_trends("does_not_exist") == []


def test_fetch_failure_degrades_to_empty(monkeypatch):
    # Simulate a network error inside the JSON getter; fetch_* must swallow it.
    def boom(*a, **k):
        raise OSError("network down")
    monkeypatch.setattr(it, "_http_get_json", boom)
    assert it.fetch_hn("anything") == []
    assert it.fetch_github("anything") == []


# --- cache ------------------------------------------------------------------ #
def test_cache_roundtrip(tmp_path):
    path = str(tmp_path / "sub" / "trends.json")
    brief = {"generated_at": "now", "pillars": {"coding": []}}
    it.save_cache(path, brief)
    assert it.load_cache(path) == brief


def test_load_missing_cache_returns_empty(tmp_path):
    assert it.load_cache(str(tmp_path / "nope.json")) == {}
