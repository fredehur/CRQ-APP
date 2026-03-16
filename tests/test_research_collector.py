"""Tests for research_collector.py — target-centric OSINT collection loop."""
import json
import pytest


REQUIRED_TOP_LEVEL = {"region", "collected_at", "working_theory", "collection", "conclusion"}
REQUIRED_WORKING_THEORY = {"scenario_name", "vacr_usd", "hypothesis", "active_topics", "geo_queries", "cyber_queries"}
REQUIRED_COLLECTION = {"pass_1_result_count", "gap_assessment", "gaps_identified", "pass_2_queries", "pass_2_result_count", "total_result_count"}
REQUIRED_CONCLUSION = {"theory_confirmed", "confidence_rationale", "suggested_admiralty", "signal_type", "dominant_pillar"}


def validate_scratchpad(data: dict) -> list[str]:
    """Returns list of schema violations. Empty list = valid."""
    errors = []
    for key in REQUIRED_TOP_LEVEL:
        if key not in data:
            errors.append(f"Missing top-level key: {key}")
    if "working_theory" in data:
        for key in REQUIRED_WORKING_THEORY:
            if key not in data["working_theory"]:
                errors.append(f"Missing working_theory.{key}")
    if "collection" in data:
        for key in REQUIRED_COLLECTION:
            if key not in data["collection"]:
                errors.append(f"Missing collection.{key}")
    if "conclusion" in data:
        for key in REQUIRED_CONCLUSION:
            if key not in data["conclusion"]:
                errors.append(f"Missing conclusion.{key}")
    return errors


def test_validate_scratchpad_passes_valid_data():
    valid = {
        "region": "AME",
        "collected_at": "2026-03-16T10:00:00Z",
        "working_theory": {
            "scenario_name": "Wind Farm Telemetry Disruption",
            "vacr_usd": 22000000,
            "hypothesis": "Test hypothesis",
            "active_topics": [],
            "geo_queries": ["geo query 1"],
            "cyber_queries": ["cyber query 1"],
        },
        "collection": {
            "pass_1_result_count": 4,
            "gap_assessment": "3 sources found",
            "gaps_identified": [],
            "pass_2_queries": [],
            "pass_2_result_count": 0,
            "total_result_count": 4,
        },
        "conclusion": {
            "theory_confirmed": True,
            "confidence_rationale": "Corroborated.",
            "suggested_admiralty": "B2",
            "signal_type": "trend",
            "dominant_pillar": "Cyber",
        },
    }
    assert validate_scratchpad(valid) == []


def test_validate_scratchpad_catches_missing_keys():
    errors = validate_scratchpad({"region": "AME"})
    assert any("collected_at" in e for e in errors)
    assert any("working_theory" in e for e in errors)
    assert any("collection" in e for e in errors)
    assert any("conclusion" in e for e in errors)


import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import patch, MagicMock


def test_mock_mode_calls_geo_and_cyber_collectors():
    """In mock mode, research_collector delegates to geo_collector + cyber_collector."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        from tools.research_collector import run_mock_mode
        run_mock_mode("AME")
        calls = [str(c) for c in mock_run.call_args_list]
        assert any("geo_collector" in c for c in calls)
        assert any("cyber_collector" in c for c in calls)


def test_form_working_theory_structure():
    """form_working_theory returns dict with required keys including geo_queries and cyber_queries."""
    crq_data = {
        "AME": [{"scenario_name": "Wind Farm Telemetry & Maintenance Disruption", "value_at_cyber_risk_usd": 22000000}]
    }
    topics = [
        {"id": "ot-ics-cyber-attacks", "label": "OT/ICS Cyber Attacks", "regions": ["AME"], "active": True},
        {"id": "other-topic", "label": "Other", "regions": ["APAC"], "active": True},
    ]
    company_profile = {"industry": "Wind Energy", "crown_jewels": ["turbine designs"]}

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "hypothesis": "AME carries $22M exposure in wind telemetry...",
        "geo_queries": ["AME energy policy instability 2026", "Americas wind regulation 2026"],
        "cyber_queries": ["AME wind farm cyber attack 2026", "Americas OT ICS ransomware 2026"],
    }))]

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        from tools.research_collector import form_working_theory
        result = form_working_theory("AME", crq_data, topics, company_profile)

    assert result["scenario_name"] == "Wind Farm Telemetry & Maintenance Disruption"
    assert result["vacr_usd"] == 22000000
    assert "hypothesis" in result
    assert "geo_queries" in result and isinstance(result["geo_queries"], list)
    assert "cyber_queries" in result and isinstance(result["cyber_queries"], list)
    assert len(result["geo_queries"]) >= 2
    assert len(result["cyber_queries"]) >= 2
    # Only AME-scoped active topics
    assert all(t["id"] == "ot-ics-cyber-attacks" for t in result["active_topics"])
