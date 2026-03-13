"""Tests for E-1 Decision Transparency."""
import json
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MOCK_GK_DECISION = {
    "decision": "ESCALATE",
    "admiralty": {"rating": "B2"},
    "scenario_match": "System intrusion",
    "dominant_pillar": "Geopolitical",
    "rationale": "State-sponsored APT activity confirmed via geo and cyber signal corroboration.",
}

MOCK_SCENARIO_MAP = {
    "financial_rank": 3,
    "confidence": "high",
    "top_scenario": "System intrusion",
}


def _add_gatekeeper_files(mock_output, regions=("APAC",)):
    """Add gatekeeper_decision.json and scenario_map.json to the mock output tree."""
    for region in regions:
        region_dir = mock_output / "regional" / region.lower()
        region_dir.mkdir(parents=True, exist_ok=True)
        (region_dir / "gatekeeper_decision.json").write_text(
            json.dumps(MOCK_GK_DECISION), encoding="utf-8"
        )
        (region_dir / "scenario_map.json").write_text(
            json.dumps(MOCK_SCENARIO_MAP), encoding="utf-8"
        )


def test_report_builder_loads_rationale(mock_output):
    """RegionEntry.rationale is populated when gatekeeper_decision.json is present."""
    _add_gatekeeper_files(mock_output, regions=("APAC",))
    from tools.report_builder import build
    data = build(output_dir=str(mock_output))
    apac = next(r for r in data.regions if r.name == "APAC")
    assert apac.rationale == MOCK_GK_DECISION["rationale"]
    assert apac.financial_rank == MOCK_SCENARIO_MAP["financial_rank"]
    assert apac.confidence == MOCK_SCENARIO_MAP["confidence"]


def test_report_builder_rationale_absent_graceful(mock_output):
    """RegionEntry.rationale is None when gatekeeper_decision.json is absent — no exception."""
    from tools.report_builder import build
    data = build(output_dir=str(mock_output))
    apac = next(r for r in data.regions if r.name == "APAC")
    assert apac.rationale is None
    assert apac.financial_rank is None


def test_export_pptx_runs_without_gatekeeper(mock_output, tmp_path):
    """export_pptx.py builds a Presentation without crashing when gatekeeper files are absent."""
    from tools.report_builder import build
    from tools.export_pptx import build_presentation
    data = build(output_dir=str(mock_output))
    prs = build_presentation(data)
    out = tmp_path / "test.pptx"
    prs.save(str(out))
    assert out.exists()


def test_decision_intelligence_block_present(mock_output):
    """decision_intelligence_block() returns non-empty HTML when gatekeeper data present."""
    _add_gatekeeper_files(mock_output, regions=("APAC",))
    from tools.build_dashboard import decision_intelligence_block
    gk = {
        "APAC": MOCK_GK_DECISION,
    }
    sm = {
        "APAC": MOCK_SCENARIO_MAP,
    }
    result = decision_intelligence_block("APAC", gk, sm)
    assert result != ""
    assert "ESCALATE" in result
    assert "State-sponsored APT" in result


def test_decision_intelligence_block_absent():
    """decision_intelligence_block() returns '' when gatekeeper data absent."""
    from tools.build_dashboard import decision_intelligence_block
    result = decision_intelligence_block("APAC", {}, {})
    assert result == ""
