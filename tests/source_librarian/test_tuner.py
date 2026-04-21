"""Tests for run_autotune — termination, budget enforcement, in-memory isolation."""
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import shutil, pytest

FIX = Path(__file__).parent / "fixtures"


def _base_no_cov_snap(scenario_id="WP-001"):
    from tools.source_librarian.snapshot import ScenarioResult, Snapshot
    return Snapshot(
        register_id="wind_test", run_id="r0", intent_hash="aabb1122",
        started_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 20, 10, 1, tzinfo=timezone.utc),
        tavily_status="ok", firecrawl_status="ok",
        scenarios=[ScenarioResult(
            scenario_id=scenario_id, scenario_name="Accidental disclosure",
            status="no_authoritative_coverage", sources=[],
            diagnostics={"candidates_discovered": 4, "top_rejected": [
                {"url": "https://ex.com", "title": "X", "reason": "wrong tier"}
            ]},
        )],
    )


def _ok_snap():
    from tools.source_librarian.snapshot import ScenarioResult, Snapshot
    return Snapshot(
        register_id="wind_test", run_id="r1", intent_hash="aabb1122",
        started_at=datetime(2026, 4, 20, 10, 2, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 20, 10, 3, tzinfo=timezone.utc),
        tavily_status="ok", firecrawl_status="ok",
        scenarios=[ScenarioResult(scenario_id="WP-001", scenario_name="X",
                                   status="ok", sources=[])],
    )


def _mock_diff():
    return {"add_threat_terms": ["OT ransomware energy"], "remove_threat_terms": [],
            "add_asset_terms": [], "remove_asset_terms": [],
            "add_industry_terms": [], "remove_industry_terms": [],
            "reasoning": "terms too narrow"}


def _setup_intent(tmp_path, monkeypatch):
    d = tmp_path / "research_intents"
    d.mkdir()
    shutil.copy(FIX / "intent_wind_minimal.yaml", d / "wind_test.yaml")
    monkeypatch.setattr("tools.source_librarian.intents.INTENTS_DIR", d)
    monkeypatch.setattr("tools.source_librarian.tuning_log.TUNING_LOG_DIR", tmp_path / "tlog")
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path / "out")


def test_autotune_found_on_first_success(tmp_path, monkeypatch):
    _setup_intent(tmp_path, monkeypatch)
    with patch("tools.source_librarian.tuner._call_tuner_agent", return_value=_mock_diff()), \
         patch("tools.source_librarian.tuner._call_validator_agent",
               return_value={"verdict": "approved", "reason": "ok"}), \
         patch("tools.source_librarian.tuner._run_discovery_for_scenario",
               return_value=_ok_snap()):
        from tools.source_librarian.tuner import run_autotune
        result = run_autotune("wind_test", "WP-001", base_snapshot=_base_no_cov_snap())

    assert result.outcome == "found"
    assert result.iterations_used == 1
    assert result.winning_diff is not None


def test_autotune_exhausted_after_max_iterations(tmp_path, monkeypatch):
    _setup_intent(tmp_path, monkeypatch)
    with patch("tools.source_librarian.tuner._call_tuner_agent", return_value=_mock_diff()), \
         patch("tools.source_librarian.tuner._call_validator_agent",
               return_value={"verdict": "approved", "reason": "ok"}), \
         patch("tools.source_librarian.tuner._run_discovery_for_scenario",
               return_value=_base_no_cov_snap()):
        from tools.source_librarian.tuner import run_autotune
        result = run_autotune("wind_test", "WP-001", base_snapshot=_base_no_cov_snap(),
                              max_iterations=3)

    assert result.outcome == "exhausted"
    assert result.iterations_used == 3


def test_autotune_cancelled_immediately(tmp_path, monkeypatch):
    _setup_intent(tmp_path, monkeypatch)
    cancel = threading.Event()
    cancel.set()

    with patch("tools.source_librarian.tuner._call_tuner_agent", return_value=_mock_diff()), \
         patch("tools.source_librarian.tuner._call_validator_agent",
               return_value={"verdict": "approved", "reason": "ok"}), \
         patch("tools.source_librarian.tuner._run_discovery_for_scenario",
               return_value=_base_no_cov_snap()):
        from tools.source_librarian.tuner import run_autotune
        result = run_autotune("wind_test", "WP-001", base_snapshot=_base_no_cov_snap(),
                              cancel_event=cancel)

    assert result.outcome == "cancelled"
    assert result.iterations_used == 0


def test_autotune_yaml_on_disk_never_mutated(tmp_path, monkeypatch):
    _setup_intent(tmp_path, monkeypatch)
    yaml_path = tmp_path / "research_intents" / "wind_test.yaml"
    original = yaml_path.read_text()

    with patch("tools.source_librarian.tuner._call_tuner_agent",
               return_value={**_mock_diff(), "add_threat_terms": ["INJECTED_TERM"]}), \
         patch("tools.source_librarian.tuner._call_validator_agent",
               return_value={"verdict": "approved", "reason": "ok"}), \
         patch("tools.source_librarian.tuner._run_discovery_for_scenario",
               return_value=_base_no_cov_snap()):
        from tools.source_librarian.tuner import run_autotune
        run_autotune("wind_test", "WP-001", base_snapshot=_base_no_cov_snap(), max_iterations=1)

    assert yaml_path.read_text() == original
    assert "INJECTED_TERM" not in yaml_path.read_text()
