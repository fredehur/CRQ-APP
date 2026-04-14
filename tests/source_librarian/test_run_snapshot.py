"""End-to-end test for run_snapshot() with fully mocked external clients."""
import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

FIX = Path(__file__).parent / "fixtures"


def _tavily_payload():
    return json.loads((FIX / "tavily_search_response.json").read_text())


def _firecrawl_search_payload():
    return json.loads((FIX / "firecrawl_search_response.json").read_text())


def _firecrawl_scrape_doc():
    md = (FIX / "firecrawl_scrape_dragos.md").read_text()
    doc = MagicMock()
    doc.markdown = md
    doc.metadata = MagicMock()
    doc.metadata.title = "OT Year in Review 2024"
    return doc


def _haiku_resp():
    resp = MagicMock()
    resp.content = [MagicMock(text="Wind operators saw 68% YoY increase. Mean cost reached $4.1M.")]
    return resp


def _stage_intent_dir(tmp_path: Path) -> Path:
    """Copy minimal intent + publishers fixtures into a tmp dir under register_id 'wind_test'."""
    d = tmp_path / "research_intents"
    d.mkdir()
    (d / "wind_test.yaml").write_text((FIX / "intent_wind_minimal.yaml").read_text(), encoding="utf-8")
    (d / "publishers.yaml").write_text((FIX / "publishers_minimal.yaml").read_text(), encoding="utf-8")
    return d


def test_run_snapshot_end_to_end(tmp_path, monkeypatch):
    intent_dir = _stage_intent_dir(tmp_path)
    monkeypatch.setattr("tools.source_librarian.intents.INTENTS_DIR", intent_dir)
    output_dir = tmp_path / "research_out"
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", output_dir)

    tavily_client = MagicMock()
    tavily_client.search.return_value = _tavily_payload()
    firecrawl_client = MagicMock()
    firecrawl_client.search.return_value = _firecrawl_search_payload()
    firecrawl_client.scrape.return_value = _firecrawl_scrape_doc()
    haiku_client = MagicMock()
    haiku_client.messages.create.return_value = _haiku_resp()

    from tools.source_librarian import run_snapshot
    snap = run_snapshot(
        register_id="wind_test",
        tavily_client=tavily_client,
        firecrawl_client=firecrawl_client,
        haiku_client=haiku_client,
        today=date(2026, 4, 14),
    )

    assert snap.register_id == "wind_test"
    assert snap.tavily_status == "ok"
    assert snap.firecrawl_status == "ok"
    assert snap.completed_at is not None
    assert len(snap.scenarios) == 2
    assert {s.scenario_id for s in snap.scenarios} == {"WP-001", "WP-002"}
    for sc in snap.scenarios:
        assert sc.status in ("ok", "no_authoritative_coverage")
        if sc.status == "ok":
            for src in sc.sources:
                assert src.publisher_tier in ("T1", "T2", "T3")

    written = list(output_dir.glob("wind_test_*.json"))
    assert len(written) == 1

    # Each unique URL should be scraped exactly once total across all scenarios
    unique_called_urls = {call.args[0] for call in firecrawl_client.scrape.call_args_list}
    assert len(unique_called_urls) == firecrawl_client.scrape.call_count


def test_run_snapshot_both_engines_failed_marks_engines_down(tmp_path, monkeypatch):
    intent_dir = _stage_intent_dir(tmp_path)
    monkeypatch.setattr("tools.source_librarian.intents.INTENTS_DIR", intent_dir)
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path / "out2")

    tavily_client = MagicMock()
    tavily_client.search.side_effect = RuntimeError("tavily down")
    firecrawl_client = MagicMock()
    firecrawl_client.search.side_effect = RuntimeError("firecrawl down")
    haiku_client = MagicMock()

    from tools.source_librarian import run_snapshot
    snap = run_snapshot(
        register_id="wind_test",
        tavily_client=tavily_client,
        firecrawl_client=firecrawl_client,
        haiku_client=haiku_client,
        today=date(2026, 4, 14),
    )

    assert snap.tavily_status == "failed"
    assert snap.firecrawl_status == "failed"
    for sc in snap.scenarios:
        assert sc.status == "engines_down"
        assert sc.sources == []
