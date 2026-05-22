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
    monkeypatch.setattr(opc, "_live_collect", lambda region: {"region": region, "pillar": "physical", "signals": []})
    result = opc.collect("MED", require_live=True)
    assert result["pillar"] == "physical"
    out = tmp_path / "output" / "regional" / "med" / "osint_physical_signals.json"
    assert out.exists()


def test_mock_path_reads_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path / "output")
    result = opc.collect("MED", mock=True)
    assert result["region"].upper() == "MED" or "signals" in result or "pillar" in result
    assert (tmp_path / "output" / "regional" / "med" / "osint_physical_signals.json").exists()


def test_tavily_search_uses_httpx(monkeypatch):
    """_tavily_search posts to Tavily and maps results — no network (httpx stubbed)."""
    monkeypatch.setenv("TAVILY_API_KEY", "k")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"title": "T", "url": "http://x", "content": "C", "published_date": "2026-05-01"}]}

    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp())
    hits = opc._tavily_search("MED unrest", max_results=3)
    assert hits[0]["title"] == "T" and hits[0]["url"] == "http://x" and hits[0]["summary"] == "C"
