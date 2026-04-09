import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.register_validator import build_register_queries

SCENARIO_WIND_RANSOMWARE = {
    "scenario_id": "s1",
    "scenario_name": "Ransomware",
    "search_tags": ["ot_systems", "wind_turbine", "scada"],
}

REGISTER_WIND = {
    "company_context": "wind power energy operator",
    "scenarios": [],
}

SCENARIO_INSIDER = {
    "scenario_id": "s2",
    "scenario_name": "Insider misuse",
    "search_tags": [],
}

REGISTER_GENERIC = {
    "company_context": "energy sector",
    "scenarios": [],
}


def test_build_register_queries_returns_typed_dicts():
    result = build_register_queries(SCENARIO_WIND_RANSOMWARE, REGISTER_WIND)
    assert isinstance(result["financial"], list)
    assert isinstance(result["probability"], list)
    for entry in result["financial"] + result["probability"]:
        assert "query" in entry, f"missing 'query' in {entry}"
        assert "tier" in entry, f"missing 'tier' in {entry}"
        assert "tier_label" in entry, f"missing 'tier_label' in {entry}"
        assert isinstance(entry["tier"], int)
        assert 1 <= entry["tier"] <= 4


def test_wind_turbine_query_has_tier_1():
    result = build_register_queries(SCENARIO_WIND_RANSOMWARE, REGISTER_WIND)
    tiers = [e["tier"] for e in result["financial"]]
    assert 1 in tiers, f"Expected tier-1 (asset-specific) query in wind+OT scenario; got tiers: {tiers}"


def test_non_ot_scenario_has_no_tier_1():
    result = build_register_queries(SCENARIO_INSIDER, REGISTER_GENERIC)
    tiers = [e["tier"] for e in result["financial"]]
    assert 1 not in tiers, f"Non-OT scenario should not have tier-1 queries; got: {tiers}"


def test_best_tier_is_lowest_number():
    result = build_register_queries(SCENARIO_WIND_RANSOMWARE, REGISTER_WIND)
    tiers = [e["tier"] for e in result["financial"]]
    assert min(tiers) == 1


from unittest.mock import patch


def _fake_search(query, max_results=4):
    return [{
        "title": "Fake Wind Ransomware Report",
        "url": "https://example.com/report",
        "content": "The average ransomware cost was $3.5 million in 2024. Annual incident rate is 12% for energy operators.",
    }]


def test_phase2_figures_carry_evidence_tier():
    from tools.register_validator import phase2_osint_search
    with patch("tools.register_validator._search_web", side_effect=_fake_search):
        fin_figs, prob_figs = phase2_osint_search(SCENARIO_WIND_RANSOMWARE, REGISTER_WIND)
    all_figs = fin_figs + prob_figs
    assert all_figs, "Expected at least one figure extracted"
    for fig in all_figs:
        assert "evidence_tier" in fig, f"figure missing evidence_tier: {fig}"
        assert isinstance(fig["evidence_tier"], int)
        assert 1 <= fig["evidence_tier"] <= 4


from tools.register_validator import compute_evidence_ceiling


def test_evidence_ceiling_returns_tier1_label_when_tier1_present():
    sources = [
        {"evidence_tier": 1, "context_tag": "asset_specific"},
        {"evidence_tier": 4, "context_tag": "general"},
    ]
    tier, label = compute_evidence_ceiling(sources)
    assert tier == 1
    assert "Asset-specific" in label


def test_evidence_ceiling_returns_tier4_when_only_general():
    sources = [
        {"evidence_tier": 4, "context_tag": "general"},
        {"evidence_tier": 4, "context_tag": "general"},
    ]
    tier, label = compute_evidence_ceiling(sources)
    assert tier == 4
    assert "General" in label


def test_evidence_ceiling_returns_tier4_when_no_sources():
    tier, label = compute_evidence_ceiling([])
    assert tier == 4


def test_validate_scenario_output_shape():
    from tools.register_validator import compute_evidence_ceiling, _EVIDENCE_TIER_LABELS
    sources_tier2 = [{"evidence_tier": 2, "context_tag": "general"}]
    tier, label = compute_evidence_ceiling(sources_tier2)
    assert tier == 2
    assert label == _EVIDENCE_TIER_LABELS[2]
