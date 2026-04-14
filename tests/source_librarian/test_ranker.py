"""Tests for tools/source_librarian/ranker.py — pure scoring + selection."""
from datetime import date
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def _cand(url, title="t", snippet="", published_date=None, discovered_by=("tavily",)):
    return {
        "url": url,
        "title": title,
        "snippet": snippet,
        "published_date": published_date,
        "discovered_by": list(discovered_by),
    }


def test_authority_score_per_tier():
    from tools.source_librarian.ranker import authority_score
    assert authority_score("T1") == 1.0
    assert authority_score("T2") == 0.7
    assert authority_score("T3") == 0.4


def test_recency_score_decays_over_time():
    from tools.source_librarian.ranker import recency_score
    today = date(2026, 4, 14)
    assert recency_score("2026-04-01", today=today) > 0.95
    halfway = recency_score("2024-10-01", today=today)
    assert 0.45 < halfway < 0.55  # ~18-month half-life
    assert recency_score("2018-01-01", today=today) < 0.1
    assert recency_score(None, today=today) == 0.3


def test_query_match_score_counts_term_hits():
    from tools.source_librarian.ranker import query_match_score
    title = "Wind farm OT ransomware report 2024"
    snippet = "Ransomware in renewable energy"
    score = query_match_score(title, snippet, query_terms=["ransomware", "wind", "ot"])
    assert 0 < score <= 1.0


def test_rank_filters_t4_then_scores_then_selects_top_n():
    from tools.source_librarian.intents import load_publishers_file
    from tools.source_librarian.ranker import rank_and_select
    pubs = load_publishers_file(FIX / "publishers_minimal.yaml")
    today = date(2026, 4, 14)
    candidates = [
        _cand("https://dragos.com/2024-yir",       title="OT YiR 2024", snippet="ransomware wind", published_date="2025-09-01"),
        _cand("https://claroty.com/team82",        title="Wind report",  snippet="ot",            published_date="2025-06-01"),
        _cand("https://bleepingcomputer.com/x",    title="news",         snippet="wind",          published_date="2025-12-01"),
        _cand("https://random-blog.example/post",  title="blog",         snippet="wind",          published_date="2025-12-01"),
    ]
    selection = rank_and_select(
        candidates,
        publishers=pubs,
        query_terms=["ransomware", "wind", "ot"],
        top_n=10,
        today=today,
    )
    assert selection.status == "ok"
    assert len(selection.sources) == 3
    tiers = [s.publisher_tier for s in selection.sources]
    assert tiers == ["T1", "T2", "T3"]
    for s in selection.sources:
        assert 0 <= s.score <= 1.0


def test_rank_caps_at_top_n():
    from tools.source_librarian.intents import load_publishers_file
    from tools.source_librarian.ranker import rank_and_select
    pubs = load_publishers_file(FIX / "publishers_minimal.yaml")
    candidates = [
        _cand(f"https://dragos.com/r{i}", title=f"Report {i}", published_date="2025-01-01")
        for i in range(15)
    ]
    selection = rank_and_select(candidates, publishers=pubs, query_terms=["wind"], top_n=10)
    assert len(selection.sources) == 10


def test_rank_empty_after_filter_returns_no_authoritative_coverage():
    from tools.source_librarian.intents import load_publishers_file
    from tools.source_librarian.ranker import rank_and_select
    pubs = load_publishers_file(FIX / "publishers_minimal.yaml")
    candidates = [
        _cand("https://random-blog.example/a", title="x", published_date="2025-01-01"),
        _cand("https://random-blog.example/b", title="y", published_date="2025-01-01"),
    ]
    selection = rank_and_select(candidates, publishers=pubs, query_terms=["wind"], top_n=10)
    assert selection.status == "no_authoritative_coverage"
    assert selection.sources == []
    assert selection.diagnostics is not None
    assert selection.diagnostics["candidates_discovered"] == 2
    assert "top_rejected" in selection.diagnostics
    assert len(selection.diagnostics["top_rejected"]) == 2


def test_rank_dedupes_candidates_by_url():
    from tools.source_librarian.intents import load_publishers_file
    from tools.source_librarian.ranker import rank_and_select
    pubs = load_publishers_file(FIX / "publishers_minimal.yaml")
    candidates = [
        _cand("https://dragos.com/r1", title="OT", published_date="2025-01-01", discovered_by=("tavily",)),
        _cand("https://dragos.com/r1", title="OT", published_date="2025-01-01", discovered_by=("firecrawl",)),
    ]
    selection = rank_and_select(candidates, publishers=pubs, query_terms=["ot"], top_n=10)
    assert len(selection.sources) == 1
    assert set(selection.sources[0].discovered_by) == {"tavily", "firecrawl"}
