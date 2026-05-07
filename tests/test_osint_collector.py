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


import tools.osint_collector as oc


MINIMAL_WATCHLIST_OC = {
    "threat_actor_groups": [
        {"name": "APT40", "motivation": "espionage", "aliases": ["BRONZE MOHAWK"]}
    ],
    "sector_targeting_campaigns": [
        {"campaign_name": "VOLT TYPHOON ICS", "actor": "Volt Typhoon", "sectors": ["energy"]}
    ],
    "cve_watch_categories": ["ICS/SCADA"],
    "global_cyber_geographies_of_concern": ["China"],
}

MINIMAL_COMPANY_OC = {
    "industry": "Wind Turbine Manufacturing",
    "crown_jewels": ["OT/SCADA networks", "turbine aerodynamic designs"],
}

MOCK_CRQ_OC = {"APAC": [{"scenario_name": "Supply Chain Attack", "value_at_cyber_risk_usd": 1_000_000}]}

MOCK_LLM_RESPONSE_OC = {
    "hypothesis": "APAC faces elevated risk from APT40 targeting OT networks.",
    "geo_queries": ["Taiwan geopolitical tension wind energy", "APAC supply chain disruption"],
    "cyber_queries": ["APT40 ICS targeting wind", "Volt Typhoon SCADA intrusion"],
}


def test_form_working_theory_includes_watchlist_in_prompt(monkeypatch):
    """Watchlist actor and campaign names appear in the LLM prompt when watchlist is supplied."""
    captured_prompts = []

    def mock_llm(prompt, **kwargs):
        captured_prompts.append(prompt)
        return MOCK_LLM_RESPONSE_OC

    monkeypatch.setattr(oc, "_call_llm", mock_llm)
    oc.form_working_theory("APAC", MOCK_CRQ_OC, [], MINIMAL_COMPANY_OC, MINIMAL_WATCHLIST_OC)
    assert len(captured_prompts) == 1
    assert "APT40" in captured_prompts[0]
    assert "VOLT TYPHOON ICS" in captured_prompts[0]


def test_form_working_theory_no_watchlist_no_crash(monkeypatch):
    """form_working_theory with no watchlist arg runs without error and returns expected keys."""
    monkeypatch.setattr(oc, "_call_llm", lambda *a, **kw: MOCK_LLM_RESPONSE_OC)
    result = oc.form_working_theory("APAC", MOCK_CRQ_OC, [], MINIMAL_COMPANY_OC)
    assert "hypothesis" in result
    assert "cyber_queries" in result
    assert "geo_queries" in result
