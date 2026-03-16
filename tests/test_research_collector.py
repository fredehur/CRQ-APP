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
