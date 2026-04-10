"""Tests for scribe_enrichment.py — query construction logic."""
import pytest


def test_build_enrichment_plan_basic():
    """Enrichment plan has scribe_countries + wod_searches."""
    from tools.scribe_enrichment import build_enrichment_plan

    osint = {"dominant_pillar": "Cyber", "lead_indicators": []}
    scenario_map = {"scenario_match": "Ransomware"}

    plan = build_enrichment_plan(osint, scenario_map, "APAC")

    assert "scribe_countries" in plan
    assert len(plan["scribe_countries"]) <= 2
    assert "wod_searches" in plan
    assert len(plan["wod_searches"]) <= 3

    # First WoD search derived from scenario
    scenario_search = plan["wod_searches"][0]
    assert "ransomware" in scenario_search["query"].lower()
    assert "scenario_map:ransomware" in scenario_search["derived_from"]


def test_build_enrichment_plan_caps_at_3_searches():
    """WoD searches hard-capped at 3."""
    from tools.scribe_enrichment import build_enrichment_plan

    osint = {"dominant_pillar": "Cyber", "lead_indicators": [
        {"text": "APT41 activity", "signal_id": "osint:tavily:apac-cyber-001"}
    ]}
    scenario_map = {"scenario_match": "System intrusion"}

    plan = build_enrichment_plan(osint, scenario_map, "APAC")
    assert len(plan["wod_searches"]) <= 3


def test_build_enrichment_plan_no_scenario():
    """Graceful when no scenario match."""
    from tools.scribe_enrichment import build_enrichment_plan

    osint = {"dominant_pillar": "Geopolitical"}
    scenario_map = {}

    plan = build_enrichment_plan(osint, scenario_map, "AME")
    assert len(plan["wod_searches"]) >= 1  # At least pillar-based search
