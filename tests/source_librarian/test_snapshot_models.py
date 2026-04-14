"""Tests for tools/source_librarian/snapshot.py — pydantic data models."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError


def test_source_entry_minimal_fields():
    from tools.source_librarian.snapshot import SourceEntry
    entry = SourceEntry(
        url="https://dragos.com/report",
        title="OT YiR 2024",
        publisher="dragos.com",
        publisher_tier="T1",
        published_date="2024-09-01",
        discovered_by=["tavily"],
        score=0.92,
        summary=None,
        figures=[],
        scrape_status="ok",
    )
    assert entry.publisher_tier == "T1"
    assert entry.scrape_status == "ok"


def test_source_entry_rejects_bad_tier():
    from tools.source_librarian.snapshot import SourceEntry
    with pytest.raises(ValidationError):
        SourceEntry(
            url="https://x.test/y",
            title="t",
            publisher="x.test",
            publisher_tier="T9",  # invalid
            published_date=None,
            discovered_by=["tavily"],
            score=0.5,
            summary=None,
            figures=[],
            scrape_status="ok",
        )


def test_scenario_result_ok_status():
    from tools.source_librarian.snapshot import ScenarioResult
    sr = ScenarioResult(
        scenario_id="WP-001",
        scenario_name="Intrusion",
        status="ok",
        sources=[],
        diagnostics=None,
    )
    assert sr.status == "ok"
    assert sr.sources == []


def test_snapshot_round_trip_json():
    from tools.source_librarian.snapshot import (
        SourceEntry, ScenarioResult, Snapshot,
    )
    snap = Snapshot(
        register_id="wind_power_plant",
        run_id="11111111-2222-3333-4444-555555555555",
        intent_hash="abcdef12",
        started_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 14, 12, 5, tzinfo=timezone.utc),
        tavily_status="ok",
        firecrawl_status="ok",
        scenarios=[
            ScenarioResult(
                scenario_id="WP-001",
                scenario_name="Intrusion",
                status="ok",
                sources=[
                    SourceEntry(
                        url="https://dragos.com/r",
                        title="OT YiR",
                        publisher="dragos.com",
                        publisher_tier="T1",
                        published_date="2024-09-01",
                        discovered_by=["tavily"],
                        score=0.91,
                        summary="Wind operators saw 68% YoY increase.",
                        figures=["68%"],
                        scrape_status="ok",
                    )
                ],
                diagnostics=None,
            )
        ],
        debug=None,
    )
    serialized = snap.model_dump_json()
    parsed = Snapshot.model_validate_json(serialized)
    assert parsed.register_id == "wind_power_plant"
    assert parsed.scenarios[0].sources[0].score == 0.91


def test_intent_hash_helper_is_stable():
    from tools.source_librarian.snapshot import intent_hash
    h1 = intent_hash("threat_terms: [a, b]\nasset_terms: [c]\n")
    h2 = intent_hash("threat_terms: [a, b]\nasset_terms: [c]\n")
    assert h1 == h2
    assert len(h1) == 8
    assert h1 != intent_hash("threat_terms: [different]\n")


def test_snapshot_filename_format():
    from tools.source_librarian.snapshot import snapshot_filename
    name = snapshot_filename("wind_power_plant", datetime(2026, 4, 14, 14, 22), "abcdef12")
    assert name == "wind_power_plant_2026-04-14-1422_abcdef12.json"
