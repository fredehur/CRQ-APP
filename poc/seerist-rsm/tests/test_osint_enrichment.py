# tests/test_osint_enrichment.py
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import osint_physical_collector as opc  # noqa: E402


def test_geo_terms_maps_code_to_geography():
    assert "Mediterranean" in opc._geo_terms("MED")
    assert opc._geo_terms("med") == opc._geo_terms("MED")


def test_build_queries_use_geo_not_raw_code():
    qs = opc._build_queries("MED")
    # MED now fans out per-country — at least 6 queries (8 countries × 4 topics)
    assert len(qs) >= 6
    # the raw region code must NOT appear as a standalone query token
    assert not any(q.startswith("MED ") for q in qs)
    # country names used instead of umbrella
    joined = " | ".join(qs)
    for c in ("Italy", "Spain", "Greece", "Turkey", "Morocco", "Egypt"):
        assert c in joined, f"missing country in queries: {c}"


def test_truncate_short_text_unchanged():
    assert opc._truncate("hello", 100) == "hello"
    assert opc._truncate("", 100) == ""
    assert opc._truncate(None, 100) == ""


def test_truncate_long_text_middle_elided_and_capped():
    text = "A" * 5000 + "B" * 5000
    out = opc._truncate(text, 1000)
    assert len(out) <= 1000 + 40  # cap + marker slack
    assert out.startswith("A") and out.endswith("B")
    assert "truncated" in out


def test_load_seerist_events_present(tmp_path):
    reg = tmp_path / "regional" / "med"
    reg.mkdir(parents=True)
    (reg / "seerist_signals.json").write_text(json.dumps({
        "situational": {"events": [
            {"signal_id": "seerist:event:med-0043", "title": "Port strike", "category": "Labour"}
        ]}
    }), encoding="utf-8")
    events, unavailable = opc._load_seerist_events("MED", output_root=tmp_path)
    assert unavailable is False
    assert events[0]["signal_id"] == "seerist:event:med-0043"
    assert events[0]["category"] == "Labour"


def test_load_seerist_events_absent(tmp_path):
    events, unavailable = opc._load_seerist_events("MED", output_root=tmp_path)
    assert unavailable is True
    assert events == []


def test_apply_enrichment_keeps_relevant_drops_rest():
    scraped = [
        {"title": "Hormuz shipping disruption", "url": "http://a", "source": "http://a",
         "published_date": "2026-05-20", "content": "body A"},
        {"title": "US Medicare 2026 plans", "url": "http://b", "source": "http://b",
         "published_date": "", "content": "body B"},
    ]
    verdicts = [
        {"index": 0, "relevant": True, "relevance_reason": "MED maritime",
         "summary": "Hormuz disruption reroutes MED freight.", "corroborates_event": None},
        {"index": 1, "relevant": False, "relevance_reason": "US Medicare, not MED physical risk"},
    ]
    signals, dropped = opc._apply_enrichment("MED", scraped, verdicts)
    assert len(signals) == 1 and len(dropped) == 1
    s = signals[0]
    assert s["signal_id"] == "osint:physical:med-001"
    assert s["summary"].startswith("Hormuz")
    assert s["content_excerpt"] == "body A"
    assert s["corroborates_event"] is None
    assert dropped[0]["url"] == "http://b" and "Medicare" in dropped[0]["relevance_reason"]


def test_apply_enrichment_missing_verdict_drops_item():
    scraped = [{"title": "x", "url": "http://x", "source": "", "published_date": "", "content": "c"}]
    signals, dropped = opc._apply_enrichment("MED", scraped, [])
    assert signals == [] and len(dropped) == 1


def test_apply_enrichment_corroboration_link_preserved():
    scraped = [{"title": "Casablanca port strike confirmed", "url": "http://c", "source": "http://c",
                "published_date": "", "content": "c"}]
    verdicts = [{"index": 0, "relevant": True, "relevance_reason": "MED",
                 "summary": "Confirms Casablanca port strike.",
                 "corroborates_event": "seerist:event:med-0043"}]
    signals, _ = opc._apply_enrichment("MED", scraped, verdicts)
    assert signals[0]["corroborates_event"] == "seerist:event:med-0043"


def test_call_llm_strips_fences_and_parses(monkeypatch):
    import types
    captured = {}

    class FakeBlock:
        text = "```json\n{\"items\": [{\"index\": 0, \"relevant\": true}]}\n```"

    class FakeResp:
        content = [FakeBlock()]

    class FakeMessages:
        def create(self, **kw):
            captured.update(kw)
            return FakeResp()

    class FakeClient:
        def __init__(self, *a, **k):
            self.messages = FakeMessages()

    fake = types.ModuleType("anthropic")
    fake.Anthropic = FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    out = opc._call_llm("prompt text")
    assert out == {"items": [{"index": 0, "relevant": True}]}
    assert captured["model"] == "claude-haiku-4-5-20251001"


def test_call_llm_bad_json_raises(monkeypatch):
    import types

    class FakeBlock:
        text = "not json"

    class FakeResp:
        content = [FakeBlock()]

    class FakeClient:
        def __init__(self, *a, **k):
            self.messages = type("M", (), {"create": lambda self, **kw: FakeResp()})()

    fake = types.ModuleType("anthropic")
    fake.Anthropic = FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    with pytest.raises(ValueError, match="non-JSON"):
        opc._call_llm("prompt")


def test_enrich_builds_prompt_with_events_and_items(monkeypatch):
    captured = {}
    monkeypatch.setattr(opc, "_call_llm", lambda prompt, **k: captured.update(prompt=prompt) or {"items": [{"index": 0, "relevant": True, "summary": "s"}]})
    scraped = [{"title": "Hormuz", "url": "http://a", "content": "body"}]
    events = [{"signal_id": "seerist:event:med-0043", "title": "Port strike", "category": "Labour"}]
    items = opc._enrich("MED", scraped, events)
    assert items[0]["index"] == 0
    assert "seerist:event:med-0043" in captured["prompt"]
    assert "Hormuz" in captured["prompt"]


def test_live_collect_chains_search_scrape_enrich(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    # seerist events present
    reg = tmp_path / "regional" / "med"; reg.mkdir(parents=True)
    (reg / "seerist_signals.json").write_text(json.dumps({"situational": {"events": []}}), encoding="utf-8")
    # stub search + scrape + enrich (no network/LLM)
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=3: [
        {"title": "Hormuz disruption", "url": "http://a", "source": "http://a", "published_date": "", "summary": "", "score": 0.9}
    ])
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {"content": "C" * 9000, "metadata": {}})
    monkeypatch.setattr(opc, "_enrich", lambda region, scraped, events: [
        {"index": i, "relevant": (i == 0), "relevance_reason": "r", "summary": "Hormuz reroute.", "corroborates_event": None}
        for i in range(len(scraped))
    ])
    # rev-2: must pass enrich_api=True to exercise the enriched path
    data = opc._live_collect("MED", enrich_api=True)
    assert data["pillar"] == "physical"
    assert data["seerist_unavailable"] is False
    assert len(data["signals"]) >= 1
    assert data["signals"][0]["signal_id"].startswith("osint:physical:med-")
    # excerpt is truncated, not the full 9000 chars
    assert len(data["signals"][0]["content_excerpt"]) <= 3100
    assert "dropped_count" in data
    # dropped audit file written
    assert (tmp_path / "regional" / "med" / "osint_dropped.json").exists()


def test_collect_require_live_needs_anthropic(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setenv("TAVILY_API_KEY", "t")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "f")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        opc.collect("MED", require_live=True, enrich_api=True)


def test_live_collect_raw_default_no_enrichment(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=3: [
        {"title": "Hormuz disruption", "url": "http://a", "source": "http://a", "published_date": "", "summary": "", "score": 0.9}
    ])
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {"content": "C" * 9000, "metadata": {}})
    # _enrich must NOT be called in raw mode
    monkeypatch.setattr(opc, "_enrich", lambda *a, **k: (_ for _ in ()).throw(AssertionError("enrich called in raw mode")))
    data = opc._live_collect("MED")  # raw default
    assert data["source_provenance"] == "tavily+firecrawl"
    s = data["signals"][0]
    assert s["signal_id"].startswith("osint:physical:med-")
    assert "summary" not in s and "corroborates_event" not in s
    assert len(s["content_excerpt"]) <= 3100  # truncated


def test_collect_raw_requires_only_tavily_firecrawl(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setenv("TAVILY_API_KEY", "t")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "f")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(opc, "_live_collect", lambda region, enrich_api=False: {"region": region, "signals": []})
    # raw require_live must NOT raise for missing ANTHROPIC
    opc.collect("MED", require_live=True)  # no exception


def test_collect_enrich_api_requires_anthropic(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setenv("TAVILY_API_KEY", "t")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "f")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        opc.collect("MED", require_live=True, enrich_api=True)


from tools.rsm_input_builder import build_rsm_inputs, manifest_summary  # noqa: E402


def _seed(output_dir: Path, region: str = "med"):
    reg = output_dir / "regional" / region
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "osint_signals.json").write_text("{}", encoding="utf-8")
    (reg / "data.json").write_text("{}", encoding="utf-8")
    return reg


def test_builder_inlines_osint(tmp_path):
    reg = _seed(tmp_path)
    (reg / "osint_physical_signals.json").write_text(json.dumps({
        "pillar": "physical", "seerist_unavailable": False, "dropped_count": 2,
        "signals": [{"signal_id": "osint:physical:med-001", "summary": "Hormuz reroute.",
                     "corroborates_event": "seerist:event:med-0043"}],
    }), encoding="utf-8")
    m = build_rsm_inputs("MED", "daily", output_dir=str(tmp_path))
    assert isinstance(m.get("osint_physical"), dict)
    assert m["osint_physical"]["signals"][0]["signal_id"] == "osint:physical:med-001"
    summary = manifest_summary(m)
    assert "OSINT physical" in summary


def test_builder_osint_absent_is_none(tmp_path):
    _seed(tmp_path)
    m = build_rsm_inputs("MED", "daily", output_dir=str(tmp_path))
    assert m.get("osint_physical") is None
