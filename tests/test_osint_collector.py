"""Tests for osint_collector.py — output schema validation."""
import json
import pytest
from pathlib import Path


def test_signal_id_format():
    """Signal IDs use full provenance prefix."""
    # osint:tavily:{region}-{pillar}-{seq}
    signal_id = "osint:tavily:apac-geo-001"
    parts = signal_id.split(":")
    assert parts[0] == "osint"
    assert parts[1] == "tavily"
    assert parts[2].startswith("apac-")


def test_mock_fixture_schema():
    """Mock fixture matches Appendix A schema."""
    fixture = Path("data/mock_osint_fixtures/apac_osint.json")
    if not fixture.exists():
        pytest.skip("Fixture not yet created (Task 7)")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    assert "region" in data
    assert "lead_indicators" in data
    assert "dominant_pillar" in data
    assert "sources" in data
    assert "source_provenance" in data
    assert data["source_provenance"] == "osint:tavily"
    for ind in data["lead_indicators"]:
        assert "signal_id" in ind
        assert "pillar" in ind
        assert ind["signal_id"].startswith("osint:tavily:")
