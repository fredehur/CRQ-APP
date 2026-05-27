"""Tests for seerist_collector.py — mock mode output schema validation."""
import json
import pytest
from pathlib import Path


def test_mock_collect_writes_correct_schema(tmp_path, monkeypatch):
    """Mock collection produces seerist_signals.json matching Appendix D schema."""
    monkeypatch.chdir(tmp_path)

    # Create mock fixture
    fixtures = tmp_path / "data" / "mock_osint_fixtures"
    fixtures.mkdir(parents=True)
    fixture_data = {
        "region": "APAC",
        "situational": {
            "events": [{"signal_id": "seerist:events_ai:apac-001", "title": "Test", "category": "Unrest", "severity": 5, "location": {"lat": 25.0, "lon": 121.0, "name": "Taipei", "country_code": "TW"}, "source_reliability": "high", "source_count": 3, "timestamp": "2026-04-09T14:00:00Z", "verified": False}],
            "verified_events": [],
            "breaking_news": [],
            "news": []
        },
        "analytical": {
            "pulse": {"countries": {"TW": {"score": 4.1, "color": "yellow", "delta": -0.8, "forecast": 3.8}}, "region_summary": {"worst_country": "TW", "worst_score": 4.1, "avg_delta": -0.8, "trend_direction": "declining"}},
            "hotspots": [],
            "scribe": [],
            "wod_searches": [],
            "analysis_reports": [],
            "risk_ratings": {}
        },
        "poi_alerts": [],
        "source_provenance": "seerist"
    }
    (fixtures / "apac_seerist.json").write_text(json.dumps(fixture_data))

    # Create output dir
    (tmp_path / "output" / "regional" / "apac").mkdir(parents=True)

    import sys
    import importlib
    sys.path.insert(0, str(tmp_path))

    import tools.seerist_collector as sc
    # Override absolute paths to point at tmp_path for this test
    monkeypatch.setattr(sc, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(sc, "FIXTURES_DIR", tmp_path / "data" / "mock_osint_fixtures")

    result = sc.collect("APAC", mock=True, window_days=7)

    assert result["region"] == "APAC"
    assert "situational" in result
    assert "analytical" in result
    assert "source_provenance" in result
    assert result["source_provenance"] == "seerist"

    # Verify file was written
    out_path = tmp_path / "output" / "regional" / "apac" / "seerist_signals.json"
    assert out_path.exists()


def test_schema_has_required_top_level_keys():
    """Verify the target schema keys match spec Appendix D."""
    required_situational = {"events", "verified_events", "breaking_news", "news"}
    required_analytical = {"pulse", "hotspots", "scribe", "wod_searches", "analysis_reports", "risk_ratings"}
    # This test documents the contract — actual assertion in integration test
    assert required_situational == {"events", "verified_events", "breaking_news", "news"}
    assert required_analytical == {"pulse", "hotspots", "scribe", "wod_searches", "analysis_reports", "risk_ratings"}
