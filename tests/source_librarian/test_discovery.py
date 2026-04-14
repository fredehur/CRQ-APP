"""Tests for tools/source_librarian/discovery.py — search engines + dedupe."""
import json
from pathlib import Path
from unittest.mock import MagicMock

FIX = Path(__file__).parent / "fixtures"


def _tavily_payload():
    return json.loads((FIX / "tavily_search_response.json").read_text())


def _firecrawl_payload():
    return json.loads((FIX / "firecrawl_search_response.json").read_text())


def test_tavily_search_normalizes_results():
    from tools.source_librarian.discovery import tavily_search
    client = MagicMock()
    client.search.return_value = _tavily_payload()
    out = tavily_search(client, ["wind ransomware 2024"])
    assert len(out) == 3
    assert out[0]["url"].startswith("https://www.dragos.com")
    assert out[0]["discovered_by"] == ["tavily"]
    assert out[0]["snippet"].startswith("Wind operators")
    assert out[0]["published_date"] == "2024-09-15"


def test_firecrawl_search_normalizes_results():
    from tools.source_librarian.discovery import firecrawl_search
    client = MagicMock()
    client.search.return_value = _firecrawl_payload()
    out = firecrawl_search(client, ["wind ransomware report pdf"])
    assert len(out) == 2
    assert out[0]["discovered_by"] == ["firecrawl"]
    assert out[0]["title"] == "OT Year in Review 2024 (PDF)"
    assert out[1]["url"].endswith("wind-advisory.pdf")
    assert out[1]["published_date"] == "2025-03-01"


def test_discover_for_scenario_merges_and_dedupes():
    from tools.source_librarian.discovery import discover_for_scenario, EngineStatus
    tavily = MagicMock()
    tavily.search.return_value = _tavily_payload()
    fc = MagicMock()
    fc.search.return_value = _firecrawl_payload()
    status = EngineStatus()
    cands = discover_for_scenario(
        news_queries=["wind ransomware 2024"],
        doc_queries=["wind ransomware report pdf"],
        tavily_client=tavily,
        firecrawl_client=fc,
        status=status,
    )
    urls = [c["url"] for c in cands]
    dragos_count = sum(1 for u in urls if "dragos.com" in u)
    assert dragos_count == 1
    dragos = next(c for c in cands if "dragos.com" in c["url"])
    assert set(dragos["discovered_by"]) == {"tavily", "firecrawl"}
    assert status.tavily == "ok"
    assert status.firecrawl == "ok"


def test_discover_tavily_failure_continues_with_firecrawl():
    from tools.source_librarian.discovery import discover_for_scenario, EngineStatus
    tavily = MagicMock()
    tavily.search.side_effect = RuntimeError("tavily down")
    fc = MagicMock()
    fc.search.return_value = _firecrawl_payload()
    status = EngineStatus()
    cands = discover_for_scenario(
        news_queries=["q"], doc_queries=["q"],
        tavily_client=tavily, firecrawl_client=fc, status=status,
    )
    assert status.tavily == "failed"
    assert status.firecrawl == "ok"
    assert len(cands) == 2


def test_discover_firecrawl_failure_continues_with_tavily():
    from tools.source_librarian.discovery import discover_for_scenario, EngineStatus
    tavily = MagicMock()
    tavily.search.return_value = _tavily_payload()
    fc = MagicMock()
    fc.search.side_effect = RuntimeError("fc down")
    status = EngineStatus()
    cands = discover_for_scenario(
        news_queries=["q"], doc_queries=["q"],
        tavily_client=tavily, firecrawl_client=fc, status=status,
    )
    assert status.tavily == "ok"
    assert status.firecrawl == "failed"
    assert len(cands) == 3


def test_discover_both_engines_disabled_returns_empty():
    from tools.source_librarian.discovery import discover_for_scenario, EngineStatus
    status = EngineStatus()
    status.tavily = "disabled"
    cands = discover_for_scenario(
        news_queries=["q"], doc_queries=["q"],
        tavily_client=None, firecrawl_client=None, status=status,
    )
    assert cands == []
    assert status.firecrawl == "failed"
