import pytest
from datetime import datetime, timezone
from pathlib import Path
from tools.source_librarian.snapshot import (
    ScenarioResult, Snapshot, SourceEntry, write_snapshot
)


def _make_snap(register_id: str, output_dir: Path) -> tuple[Snapshot, Path]:
    snap = Snapshot(
        register_id=register_id,
        run_id="run-orig",
        intent_hash="aabbccdd",
        started_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 20, 10, 1, tzinfo=timezone.utc),
        tavily_status="ok",
        firecrawl_status="ok",
        scenarios=[
            ScenarioResult(scenario_id="WP-001", scenario_name="Intrusion",
                           status="ok", sources=[]),
            ScenarioResult(scenario_id="WP-002", scenario_name="Ransomware",
                           status="no_authoritative_coverage", sources=[]),
        ],
    )
    path = write_snapshot(snap, output_dir=output_dir)
    return snap, path


def test_merge_replaces_target_scenario(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path)
    orig, _ = _make_snap("wind_test", tmp_path)

    new_result = ScenarioResult(
        scenario_id="WP-002",
        scenario_name="Ransomware",
        status="ok",
        sources=[
            SourceEntry(
                url="https://dragos.com/report",
                title="OT Year in Review",
                publisher="dragos.com",
                publisher_tier="T1",
                published_date="2026-01-10",
                discovered_by=["tavily"],
                score=0.92,
                summary="Vestas incident covered",
                figures=["$4.1M"],
                scrape_status="ok",
            )
        ],
    )

    from tools.source_librarian.snapshot_merge import merge_scenario_result
    merged = merge_scenario_result("wind_test", new_result, output_dir=tmp_path)

    wp2 = next(s for s in merged.scenarios if s.scenario_id == "WP-002")
    assert wp2.status == "ok"
    assert len(wp2.sources) == 1

    wp1 = next(s for s in merged.scenarios if s.scenario_id == "WP-001")
    assert wp1.status == "ok"

    # intent_hash preserved from original
    assert merged.intent_hash == orig.intent_hash
    assert len(merged.scenarios) == 2


def test_merge_writes_new_file_preserves_old(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path)
    orig, orig_path = _make_snap("wind_test", tmp_path)

    new_result = ScenarioResult(scenario_id="WP-001", scenario_name="Intrusion",
                                status="ok", sources=[])

    from tools.source_librarian.snapshot_merge import merge_scenario_result
    merge_scenario_result("wind_test", new_result, output_dir=tmp_path)

    snapshots = sorted(tmp_path.glob("wind_test_*.json"))
    assert len(snapshots) == 2   # original preserved + new written
    assert orig_path in snapshots


def test_merge_raises_when_no_base_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path)
    new_result = ScenarioResult(scenario_id="WP-001", scenario_name="X",
                                status="ok", sources=[])

    from tools.source_librarian.snapshot_merge import merge_scenario_result
    with pytest.raises(FileNotFoundError, match="No base snapshot"):
        merge_scenario_result("no_register", new_result, output_dir=tmp_path)


def test_merge_raises_when_scenario_not_in_base(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path)
    _make_snap("wind_test", tmp_path)
    new_result = ScenarioResult(scenario_id="WP-999", scenario_name="X",
                                status="ok", sources=[])

    from tools.source_librarian.snapshot_merge import merge_scenario_result
    with pytest.raises(KeyError, match="WP-999"):
        merge_scenario_result("wind_test", new_result, output_dir=tmp_path)
