"""osint_physical_collector — require_live guard + mock path + self-contained primitives."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import osint_physical_collector as opc  # noqa: E402


def test_require_live_fails_loudly_when_keys_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path / "output")
    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        opc.collect("MED", require_live=True)


def test_require_live_passes_when_keys_present_then_uses_live(tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "x")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "y")
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path / "output")
    # stub the live collector so no real HTTP happens
    monkeypatch.setattr(opc, "_live_collect", lambda region, enrich_api=False: {"region": region, "pillar": "physical", "signals": []})
    result = opc.collect("MED", require_live=True)
    assert result["pillar"] == "physical"
    out = tmp_path / "output" / "regional" / "med" / "osint_physical_signals.json"
    assert out.exists()


def test_mock_path_reads_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path / "output")
    result = opc.collect("MED", mock=True)
    assert result["region"].upper() == "MED" or "signals" in result or "pillar" in result
    assert (tmp_path / "output" / "regional" / "med" / "osint_physical_signals.json").exists()


def test_tavily_search_uses_sdk(monkeypatch):
    """_tavily_search uses the tavily-python SDK (TavilyClient.search) and maps results."""
    import types
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    captured = {}

    class FakeClient:
        def __init__(self, api_key=None):
            captured["key"] = api_key

        def search(self, query, max_results=None, **kwargs):
            captured["query"] = query
            captured["max_results"] = max_results
            return {"results": [{"title": "T", "url": "http://x", "content": "C", "published_date": "2026-05-01", "score": 0.9}]}

    fake = types.ModuleType("tavily")
    fake.TavilyClient = FakeClient
    monkeypatch.setitem(sys.modules, "tavily", fake)

    hits = opc._tavily_search("MED unrest", max_results=3)
    assert captured["key"] == "k" and captured["max_results"] == 3
    assert hits[0]["title"] == "T" and hits[0]["url"] == "http://x" and hits[0]["summary"] == "C"


def test_firecrawl_extract_uses_v4_scrape(monkeypatch):
    """_firecrawl_extract uses firecrawl-py v4: Firecrawl().scrape(formats=, only_main_content=)
    with attribute access on the returned Document."""
    import types
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")
    captured = {}

    class FakeDoc:
        markdown = "# content"
        metadata = {"publishedTime": "2026-05-01T10:00:00Z"}

    class FakeApp:
        def __init__(self, api_key=None):
            captured["key"] = api_key

        def scrape(self, url, formats=None, only_main_content=None):
            captured.update(url=url, formats=formats, only_main_content=only_main_content)
            return FakeDoc()

    fake = types.ModuleType("firecrawl")
    fake.Firecrawl = FakeApp
    monkeypatch.setitem(sys.modules, "firecrawl", fake)

    out = opc._firecrawl_extract("http://x")
    assert captured["formats"] == ["markdown"] and captured["only_main_content"] is True
    assert out["content"] == "# content" and out["metadata"] == {"publishedTime": "2026-05-01T10:00:00Z"}


def test_firecrawl_extract_empty_returns_none(monkeypatch):
    import types
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")

    class FakeDoc:
        markdown = ""
        metadata = {}

    class FakeApp:
        def __init__(self, api_key=None):
            pass

        def scrape(self, url, formats=None, only_main_content=None):
            return FakeDoc()

    fake = types.ModuleType("firecrawl")
    fake.Firecrawl = FakeApp
    monkeypatch.setitem(sys.modules, "firecrawl", fake)

    assert opc._firecrawl_extract("http://x") is None


# ── Task 1: per-country queries ──────────────────────────────────────────────

def test_build_queries_uses_per_country_not_umbrella():
    qs = opc._build_queries("MED")
    # MED has 6+ countries → at least 6 queries; current returns 4
    assert len(qs) >= 6
    # No umbrella term — each query names a specific country
    assert not any("Mediterranean" in q for q in qs)
    # Country names appear
    joined = " | ".join(qs)
    for c in ("Italy", "Spain", "Greece", "Turkey", "Morocco", "Egypt"):
        assert c in joined, f"missing country in queries: {c}"


def test_build_queries_includes_negative_terms_for_med_collision():
    qs = opc._build_queries("MED")
    # at least one MED query must exclude Medicare/healthcare to break the semantic collision
    assert any("-Medicare" in q or "-healthcare" in q for q in qs)


def test_build_queries_per_country_fanout_all_regions():
    """All five regions use per-country fan-out (not umbrella terms)."""
    for r in ("MED", "NCE", "APAC", "AME", "LATAM"):
        qs = opc._build_queries(r)
        assert qs, f"empty queries for {r}"
        # at least one country from each region's list must appear in the joined queries
        joined = " | ".join(qs)
        for country in opc.REGION_COUNTRIES[r]:
            assert country in joined, f"{r}: missing country {country} in queries"
        # at least 4 topics × however many countries → >=4 queries
        assert len(qs) >= 4 * len(opc.REGION_COUNTRIES[r])


def test_build_queries_negative_terms_per_region():
    """Each region has at least one targeted negative term to break semantic collisions."""
    expected_negatives = {
        "MED":   "-Medicare",
        "NCE":   "-NICE",
        "APAC":  "-CES",
        "AME":   "-AME",
        "LATAM": "-airlines",
    }
    for r, neg in expected_negatives.items():
        qs = opc._build_queries(r)
        assert any(neg in q for q in qs), f"{r}: missing negative term {neg}"


# ── Task 2: Tavily news + recency + advanced + exclude_domains + score ───────

def test_tavily_search_uses_news_recency_advanced(monkeypatch):
    import types
    captured = {}
    class FakeClient:
        def __init__(self, api_key): pass
        def search(self, query, **kwargs):
            captured.update(kwargs)
            captured["query"] = query
            return {"results": []}
    fake = types.ModuleType("tavily")
    fake.TavilyClient = FakeClient
    monkeypatch.setitem(sys.modules, "tavily", fake)
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    opc._tavily_search("Italy unrest 2026")
    assert captured.get("topic") == "news"
    assert captured.get("days") == 7
    assert captured.get("search_depth") == "advanced"


def test_tavily_search_includes_exclude_domains(monkeypatch):
    import types
    captured = {}
    class FakeClient:
        def __init__(self, api_key): pass
        def search(self, query, **kwargs):
            captured.update(kwargs)
            return {"results": []}
    fake = types.ModuleType("tavily")
    fake.TavilyClient = FakeClient
    monkeypatch.setitem(sys.modules, "tavily", fake)
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    opc._tavily_search("anything")
    exclude = captured.get("exclude_domains") or []
    # Known noise domains from the 2026-05-22 live run
    for d in ("medicare2026.healthplan.org", "health-isac.org", "aha.org", "directrelief.org"):
        assert d in exclude, f"exclude_domains missing {d}"


def test_collect_raw_drops_low_score_results(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(opc, "_build_queries", lambda region: ["q"])
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=3: [
        {"title": "Good", "url": "http://a", "source": "http://a", "published_date": "", "summary": "", "score": 0.82},
        {"title": "Junk", "url": "http://b", "source": "http://b", "published_date": "", "summary": "", "score": 0.15},
    ])
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {"content": "C" * 500, "metadata": {}})
    sigs = opc._collect_raw("MED")
    # Only the high-score item kept
    assert len(sigs) == 1
    assert sigs[0]["url"] == "http://a"


# ── Task 3: raw shape cleanup ─────────────────────────────────────────────────

def test_outlet_name_maps_known_domains():
    assert opc._outlet_name("https://www.npr.org/2026/05/01/x") == "NPR"
    assert opc._outlet_name("https://www.reuters.com/world/eu/x") == "Reuters"
    assert opc._outlet_name("https://en.wikipedia.org/wiki/X") == "Wikipedia"
    assert opc._outlet_name("https://www.aljazeera.com/news/x") == "Al Jazeera"
    # Unknown domain falls back to the bare domain (no scheme, no www)
    assert opc._outlet_name("https://obscure.example.com/x") == "obscure.example.com"
    # Bad input
    assert opc._outlet_name("") == ""
    assert opc._outlet_name(None) == ""


def test_collect_raw_uses_outlet_name_not_url(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(opc, "_build_queries", lambda region: ["q"])
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=3: [
        {"title": "Article", "url": "https://www.npr.org/2026/01/x", "source": "https://www.npr.org/2026/01/x",
         "published_date": "", "summary": "", "score": 0.9}
    ])
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {"content": "C" * 500, "metadata": {}})
    sigs = opc._collect_raw("MED")
    assert sigs[0]["outlet"] == "NPR"
    assert sigs[0]["outlet"] != sigs[0]["url"]


def test_collect_raw_falls_back_to_firecrawl_published_at(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(opc, "_build_queries", lambda region: ["q"])
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=3: [
        {"title": "T", "url": "http://a", "source": "http://a",
         "published_date": "", "summary": "", "score": 0.9}
    ])
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {
        "content": "C" * 500,
        "metadata": {"publishedTime": "2026-05-21T10:00:00Z"},
    })
    sigs = opc._collect_raw("MED")
    assert sigs[0]["published_at"] == "2026-05-21T10:00:00Z"


def test_collect_raw_drops_broken_scrapes(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(opc, "_build_queries", lambda region: ["q"])
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=3: [
        {"title": "Home", "url": "http://a", "source": "http://a", "published_date": "", "summary": "", "score": 0.9},
        {"title": "", "url": "http://b", "source": "http://b", "published_date": "", "summary": "", "score": 0.9},
        {"title": "Real Article", "url": "http://c", "source": "http://c", "published_date": "", "summary": "", "score": 0.9},
    ])
    # First two have valid content but bad titles; the real one has enough content
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {"content": "C" * 500, "metadata": {}})
    sigs = opc._collect_raw("MED")
    assert len(sigs) == 1
    assert sigs[0]["title"] == "Real Article"


def test_collect_raw_drops_short_content(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(opc, "_build_queries", lambda region: ["q"])
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=3: [
        {"title": "T", "url": "http://a", "source": "http://a", "published_date": "", "summary": "", "score": 0.9}
    ])
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {"content": "tiny", "metadata": {}})
    sigs = opc._collect_raw("MED")
    assert sigs == []


def test_collect_raw_no_location_field(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(opc, "_build_queries", lambda region: ["q"])
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=3: [
        {"title": "Article", "url": "http://a", "source": "http://a", "published_date": "", "summary": "", "score": 0.9}
    ])
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {"content": "C" * 500, "metadata": {}})
    sigs = opc._collect_raw("MED")
    # location field was always empty {} — drop it from the raw shape
    assert "location" not in sigs[0]
