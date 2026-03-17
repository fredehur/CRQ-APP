"""Tests for tools/deep_research.py"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path


@pytest.fixture
def tmp_output(tmp_path, monkeypatch):
    """Redirect BASE output path."""
    import tools.deep_research as dr
    monkeypatch.setattr(dr, "OUTPUT", tmp_path / "output")
    (tmp_path / "output" / "regional" / "apac").mkdir(parents=True)
    return tmp_path


def test_depth_config_quick():
    from tools.deep_research import DEPTH_CONFIG
    cfg = DEPTH_CONFIG["quick"]
    assert cfg["max_subtopics"] == 2
    assert cfg["report_type"] == "summary_report"


def test_depth_config_standard():
    from tools.deep_research import DEPTH_CONFIG
    cfg = DEPTH_CONFIG["standard"]
    assert cfg["max_subtopics"] == 3
    assert cfg["report_type"] == "research_report"


def test_depth_config_deep():
    from tools.deep_research import DEPTH_CONFIG
    cfg = DEPTH_CONFIG["deep"]
    assert cfg["max_subtopics"] == 5


def test_build_query_geo():
    from tools.deep_research import build_query
    q = build_query("APAC", "geo")
    assert "APAC" in q
    assert "wind" in q.lower() or "energy" in q.lower() or "geopolit" in q.lower()


def test_build_query_cyber():
    from tools.deep_research import build_query
    q = build_query("AME", "cyber")
    assert "AME" in q or "America" in q
    assert "cyber" in q.lower() or "OT" in q or "threat" in q.lower()


def test_extract_geo_signals_returns_schema():
    from tools.deep_research import _validate_geo_signals
    valid = {
        "summary": "test summary",
        "lead_indicators": ["a", "b"],
        "dominant_pillar": "Geopolitical",
        "matched_topics": []
    }
    assert _validate_geo_signals(valid) == valid


def test_extract_geo_signals_rejects_missing_key():
    from tools.deep_research import _validate_geo_signals
    with pytest.raises(ValueError):
        _validate_geo_signals({"summary": "x"})  # missing required keys


def test_extract_cyber_signals_returns_schema():
    from tools.deep_research import _validate_cyber_signals
    valid = {
        "summary": "test",
        "threat_vector": "phishing",
        "target_assets": ["OT systems"],
        "matched_topics": []
    }
    assert _validate_cyber_signals(valid) == valid


def test_cli_requires_region_and_type(capsys):
    """CLI with no args should exit non-zero."""
    import sys
    import tools.deep_research as dr
    with pytest.raises(SystemExit) as exc:
        dr.cli_main([])
    assert exc.value.code != 0


@pytest.mark.anyio
async def test_run_deep_research_writes_output(tmp_output):
    """Mock GPT Researcher + extraction, verify output file written."""
    import tools.deep_research as dr

    mock_report = "# Test Report\n\nSouth China Sea tensions rising."

    expected_geo = {
        "summary": "Test summary",
        "lead_indicators": ["indicator 1"],
        "dominant_pillar": "Geopolitical",
        "matched_topics": []
    }

    with patch("tools.deep_research.GPTResearcher") as MockGPT, \
         patch("tools.deep_research._extract_with_haiku", new=AsyncMock(return_value=expected_geo)):

        instance = AsyncMock()
        instance.conduct_research = AsyncMock(return_value=[])
        instance.write_report = AsyncMock(return_value=mock_report)
        instance.get_source_urls = MagicMock(return_value=["https://example.com"])
        MockGPT.return_value = instance

        result = await dr.run_deep_research("APAC", "geo", depth="quick")

    assert result["summary"] == "Test summary"
    out_path = tmp_output / "output" / "regional" / "apac" / "geo_signals.json"
    assert out_path.exists()
    saved = json.loads(out_path.read_text())
    assert saved["summary"] == "Test summary"
