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

        def search(self, query, max_results=None, search_depth=None):
            captured["query"] = query
            captured["max_results"] = max_results
            return {"results": [{"title": "T", "url": "http://x", "content": "C", "published_date": "2026-05-01"}]}

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
        metadata = {"location": {"name": "Rabat"}}

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
    assert out["content"] == "# content" and out["location"] == {"name": "Rabat"}


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
