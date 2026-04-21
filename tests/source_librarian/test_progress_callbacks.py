"""Tests for run_snapshot on_progress callback and scenario_id isolation."""
import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

FIX = Path(__file__).parent / "fixtures"


def _clients():
    tavily = MagicMock()
    tavily.search.return_value = json.loads((FIX / "tavily_search_response.json").read_text())
    firecrawl = MagicMock()
    firecrawl.search.return_value = json.loads((FIX / "firecrawl_search_response.json").read_text())
    doc = MagicMock()
    doc.markdown = (FIX / "firecrawl_scrape_dragos.md").read_text()
    doc.metadata = MagicMock()
    doc.metadata.title = "OT Year in Review 2024"
    firecrawl.scrape.return_value = doc
    haiku = MagicMock()
    haiku.messages.create.return_value = MagicMock(content=[MagicMock(text="Cost $4.1M")])
    return tavily, firecrawl, haiku


def _stage_intent_dir(tmp_path):
    d = tmp_path / "research_intents"
    d.mkdir()
    (d / "wind_test.yaml").write_text((FIX / "intent_wind_minimal.yaml").read_text())
    (d / "publishers.yaml").write_text((FIX / "publishers_minimal.yaml").read_text())
    return d


def test_on_progress_called_per_scenario(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.intents.INTENTS_DIR", _stage_intent_dir(tmp_path))
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path / "out")
    tavily, firecrawl, haiku = _clients()

    events = []
    from tools.source_librarian import run_snapshot
    run_snapshot(
        "wind_test",
        on_progress=lambda d: events.append(d),
        tavily_client=tavily,
        firecrawl_client=firecrawl,
        haiku_client=haiku,
        today=date(2026, 4, 20),
    )

    stages = {e["stage"] for e in events}
    assert "discovery" in stages

    disc_events = [e for e in events if e["stage"] == "discovery"]
    assert len(disc_events) == 2   # one per scenario (wind_test has WP-001 and WP-002)
    for e in disc_events:
        assert e["status"] == "done"
        assert e["counts"]["discovery"]["total"] == 2


def test_scenario_id_returns_single_scenario(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.intents.INTENTS_DIR", _stage_intent_dir(tmp_path))
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path / "out")
    tavily, firecrawl, haiku = _clients()

    from tools.source_librarian import run_snapshot
    snap = run_snapshot(
        "wind_test",
        scenario_id="WP-001",
        tavily_client=tavily,
        firecrawl_client=firecrawl,
        haiku_client=haiku,
        today=date(2026, 4, 20),
    )

    assert len(snap.scenarios) == 1
    assert snap.scenarios[0].scenario_id == "WP-001"


def test_scenario_id_skips_write_to_disk(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.intents.INTENTS_DIR", _stage_intent_dir(tmp_path))
    out_dir = tmp_path / "out"
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", out_dir)
    tavily, firecrawl, haiku = _clients()

    from tools.source_librarian import run_snapshot
    run_snapshot(
        "wind_test",
        scenario_id="WP-001",
        tavily_client=tavily,
        firecrawl_client=firecrawl,
        haiku_client=haiku,
        today=date(2026, 4, 20),
    )

    assert not out_dir.exists() or not list(out_dir.glob("*.json"))


def test_unknown_scenario_id_raises(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr("tools.source_librarian.intents.INTENTS_DIR", _stage_intent_dir(tmp_path))
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path / "out")
    tavily, firecrawl, haiku = _clients()

    from tools.source_librarian import run_snapshot
    with pytest.raises(KeyError, match="WP-999"):
        run_snapshot(
            "wind_test",
            scenario_id="WP-999",
            tavily_client=tavily,
            firecrawl_client=firecrawl,
            haiku_client=haiku,
        )
