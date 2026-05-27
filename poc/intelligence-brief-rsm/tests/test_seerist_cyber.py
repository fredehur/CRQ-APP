"""Cyber collector — keyword filter + Seerist Analysis endpoint, merged signals."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools import seerist_collector


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_WATCHLIST = {
    "threat_actor_groups": [
        {
            "name": "MEDUSA",
            "aliases": ["MEDUSA Ransomware"],
            "regions": ["MED", "NCE"],
            "sectors": ["general"],
            "notes": "Ransomware crew.",
        },
        {
            "name": "Sandworm",
            "aliases": ["BlackEnergy", "Voodoo Bear", "TeleBots"],
            "regions": ["NCE", "MED"],
            "sectors": ["energy"],
            "notes": "Russian GRU Unit 74455.",
        },
        {
            "name": "APT28",
            "aliases": ["Fancy Bear", "Sofacy", "Forest Blizzard"],
            "regions": ["MED", "NCE", "AME"],
            "sectors": ["energy"],
            "notes": "Russian GRU.",
        },
    ]
}


def _make_fake_client(news=None, hotspots=None, cyber_docs=None):
    """Build a MagicMock SeeristClient."""
    fake = MagicMock()
    fake.get_pulse.return_value = {}
    fake.get_events.return_value = []
    fake.get_verified_events.return_value = []
    fake.get_breaking_events.return_value = []
    fake.get_news.return_value = news or []
    fake.get_hotspots.return_value = hotspots or []
    fake.get_analysis_reports.return_value = []
    fake.get_risk_ratings.return_value = {}
    fake.search_poi.return_value = []
    fake.get_cyber_analysis.return_value = cyber_docs or []
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = None
    return fake


def _live_collect_patched(monkeypatch, news=None, hotspots=None, cyber_docs=None, watchlist=None):
    """Run _live_collect with injected watchlist, news, hotspots, and analysis docs."""
    wl_data = watchlist if watchlist is not None else _WATCHLIST

    def _fake_read_text(self, **kw):
        name = self.name
        if name == "cyber_watchlist.json":
            return json.dumps(wl_data)
        if name == "aerowind_sites.json":
            return json.dumps({"sites": []})
        raise FileNotFoundError(self)

    monkeypatch.setattr(Path, "read_text", _fake_read_text)
    monkeypatch.setattr(Path, "exists", lambda self: self.name == "cyber_watchlist.json")

    fake_client = _make_fake_client(news=news, hotspots=hotspots, cyber_docs=cyber_docs)
    with patch("tools.seerist_client.SeeristClient.create", return_value=fake_client), \
         patch("tools.seerist_client.REGION_COUNTRIES", {"MED": ["IT", "ES"]}):
        return seerist_collector._live_collect("MED", window_days=7)


# ---------------------------------------------------------------------------
# Test 1 — blocks always present (updated summary shape)
# ---------------------------------------------------------------------------

def test_cyber_signals_block_present_when_analysis_returns_empty(monkeypatch):
    """cyber_signals and cyber_summary are always present — even with no matches at all."""
    result = _live_collect_patched(monkeypatch, news=[], hotspots=[], cyber_docs=[])

    assert "cyber_signals" in result
    assert "cyber_summary" in result
    assert result["cyber_signals"] == []

    summary = result["cyber_summary"]
    assert summary["matched_count"] == 0
    assert summary["scanned_news"] == 0
    assert summary["scanned_hotspots"] == 0
    assert summary["scanned_analysis"] == 0
    assert summary["region"] == "MED"
    assert "sources_used" in summary


# ---------------------------------------------------------------------------
# Test 2 — analysis documents normalized correctly
# ---------------------------------------------------------------------------

def test_cyber_signals_normalized_from_analysis_documents(monkeypatch):
    """Two analysis docs → two cyber_signals with source_type='analysis' and correct fields."""
    doc1 = {
        "id": "wod-doc-001",
        "properties": {
            "id": "wod-doc-001",
            "title": "MEDUSA ransomware targets Italian energy sector",
            "sanitizedSummary": "MEDUSA claimed responsibility for an attack on an Italian utility.",
            "publishedDate": "2026-05-17T10:00:00Z",
            "riskCategories": ["53bd26cf-58fb-4ce9-8d04-e239f40d6710"],
            "severity": 4,
        },
    }
    doc2 = {
        "id": "wod-doc-002",
        "properties": {
            "id": "wod-doc-002",
            "title": "Sandworm targeting wind operators across Northern Europe",
            "summary": "GRU-linked Sandworm group has begun reconnaissance of wind energy OT networks.",
            "publishedDate": "2026-05-16T08:00:00Z",
            "riskCategories": [
                "53bd26cf-58fb-4ce9-8d04-e239f40d6710",
                "d49316b4-45f5-4337-b69b-0b4ee12d3db7",
            ],
        },
    }

    result = _live_collect_patched(monkeypatch, cyber_docs=[doc1, doc2])
    signals = result["cyber_signals"]

    assert len(signals) == 2

    s1 = signals[0]
    assert s1["source_type"] == "analysis"
    assert s1["title"] == "MEDUSA ransomware targets Italian energy sector"
    assert "MEDUSA claimed" in s1["summary"]
    assert s1["published_date"] == "2026-05-17T10:00:00Z"
    assert s1["severity"] == 4
    assert s1["original_id"] == "wod-doc-001"
    assert len(s1["risk_categories"]) == 1
    assert "MEDUSA" in s1["relevant_actors"]
    assert s1["matched_keywords"] == []  # analysis docs are category-filtered, not keyword-filtered

    s2 = signals[1]
    assert s2["source_type"] == "analysis"
    assert s2["title"] == "Sandworm targeting wind operators across Northern Europe"
    assert s2["severity"] == 3  # missing severity → floor default
    assert s2["original_id"] == "wod-doc-002"
    assert len(s2["risk_categories"]) == 2
    assert "Sandworm" in s2["relevant_actors"]

    summary = result["cyber_summary"]
    assert summary["matched_count"] == 2
    assert summary["scanned_analysis"] == 2
    assert "seerist:analysis" in summary["sources_used"]


# ---------------------------------------------------------------------------
# Test 3 — watchlist surfaces threat_actor_context
# ---------------------------------------------------------------------------

def test_threat_actor_context_loaded_from_watchlist(monkeypatch):
    """_live_collect populates analytical.threat_actor_context from cyber_watchlist.json."""
    result = _live_collect_patched(monkeypatch, cyber_docs=[])

    tac = result["analytical"]["threat_actor_context"]
    assert "MEDUSA" in tac
    assert "Sandworm" in tac
    assert "APT28" in tac
    assert "BlackEnergy" in tac
    assert "Fancy Bear" in tac
    assert "MEDUSA Ransomware" in tac


# ---------------------------------------------------------------------------
# Test 4 — NEW: keyword-filtered news item appears in cyber_signals
# ---------------------------------------------------------------------------

def test_cyber_signals_include_keyword_matched_news(monkeypatch):
    """A news item whose title matches a cyber keyword appears as source_type='news'."""
    news_item = {
        "signal_id": "seerist:news:med-001",
        "title": "Ransomware group MEDUSA hits Italian energy firm",
        "severity": 4,
        "timestamp": "2026-05-18T08:00:00Z",
    }
    result = _live_collect_patched(monkeypatch, news=[news_item], hotspots=[], cyber_docs=[])

    signals = result["cyber_signals"]
    assert len(signals) == 1

    sig = signals[0]
    assert sig["source_type"] == "news"
    assert sig["title"] == news_item["title"]
    assert sig["original_id"] == "seerist:news:med-001"
    assert sig["severity"] == 4

    kws_lower = [k.lower() for k in sig["matched_keywords"]]
    assert any("ransomware" in k for k in kws_lower)
    assert any("medusa" in k for k in kws_lower)
    assert "MEDUSA" in sig["relevant_actors"]

    summary = result["cyber_summary"]
    assert summary["matched_count"] == 1
    assert summary["scanned_news"] == 1
    assert summary["scanned_analysis"] == 0
    assert "keyword:news" in summary["sources_used"]


# ---------------------------------------------------------------------------
# Test 5 — NEW: analysis docs and keyword-filtered items merge; dedup on title
# ---------------------------------------------------------------------------

def test_cyber_signals_dedupe_across_sources(monkeypatch):
    """Same title in both analysis doc and news item → only one entry; analysis wins."""
    shared_title = "MEDUSA ransomware targets Italian energy sector"

    analysis_doc = {
        "id": "wod-doc-001",
        "properties": {
            "id": "wod-doc-001",
            "title": shared_title,
            "sanitizedSummary": "MEDUSA analysis body.",
            "publishedDate": "2026-05-17T10:00:00Z",
            "riskCategories": ["53bd26cf-58fb-4ce9-8d04-e239f40d6710"],
            "severity": 4,
        },
    }
    news_item = {
        "signal_id": "seerist:news:med-001",
        "title": shared_title,  # same title — should be deduped
        "severity": 2,
        "timestamp": "2026-05-17T09:00:00Z",
    }

    result = _live_collect_patched(
        monkeypatch, news=[news_item], hotspots=[], cyber_docs=[analysis_doc]
    )
    signals = result["cyber_signals"]

    # Only one entry — deduped
    assert len(signals) == 1
    # Analysis source wins
    assert signals[0]["source_type"] == "analysis"
    assert signals[0]["severity"] == 4
    assert signals[0]["original_id"] == "wod-doc-001"

    summary = result["cyber_summary"]
    assert summary["matched_count"] == 1


# ---------------------------------------------------------------------------
# Test 6 — NEW: scanned_analysis count reflects endpoint return size
# ---------------------------------------------------------------------------

def test_cyber_summary_scanned_analysis_count(monkeypatch):
    """scanned_analysis in cyber_summary equals the number of docs returned by the endpoint."""
    docs = [
        {
            "id": f"wod-doc-{i:03d}",
            "properties": {
                "id": f"wod-doc-{i:03d}",
                "title": f"Cyber analysis document {i}",
                "publishedDate": "2026-05-17T10:00:00Z",
            },
        }
        for i in range(5)
    ]

    result = _live_collect_patched(monkeypatch, cyber_docs=docs)

    summary = result["cyber_summary"]
    assert summary["scanned_analysis"] == 5
    # All 5 docs produce signals (distinct titles, no keyword filter needed for analysis)
    assert summary["matched_count"] == 5
    assert len(result["cyber_signals"]) == 5
