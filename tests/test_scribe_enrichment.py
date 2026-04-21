"""Tests for scribe_enrichment.py — query construction logic."""
import json

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


def test_watchlist_actor_picked_up(monkeypatch, tmp_path):
    """Actor listed in cyber_watchlist.json (but not hardcoded) is detected."""
    import tools.scribe_enrichment as se

    watchlist_path = tmp_path / "cyber_watchlist.json"
    watchlist_path.write_text(json.dumps({
        "threat_actor_groups": [
            {"name": "APT40", "aliases": ["BRONZE MOHAWK"], "motivation": "espionage"}
        ]
    }), encoding="utf-8")
    monkeypatch.setattr(se, "WATCHLIST_FILE", watchlist_path)

    osint = {"dominant_pillar": "Cyber", "lead_indicators": [
        {"text": "Reports of APT40 reconnaissance against regional grid operators"}
    ]}
    actor = se._extract_actor_if_clean(osint)
    assert actor == "APT40"


def test_watchlist_missing_does_not_crash(monkeypatch, tmp_path):
    """Absent watchlist file falls back to hardcoded set without error."""
    import tools.scribe_enrichment as se
    monkeypatch.setattr(se, "WATCHLIST_FILE", tmp_path / "does_not_exist.json")

    osint = {"dominant_pillar": "Cyber", "lead_indicators": [
        {"text": "Volt Typhoon activity observed"}
    ]}
    actor = se._extract_actor_if_clean(osint)
    assert actor == "Volt Typhoon"  # hardcoded fallback still works
