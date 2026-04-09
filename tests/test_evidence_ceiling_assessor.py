import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

MOCK_REGISTER_VALIDATION = {
    "register_id": "wind_power_plant",
    "scenarios": [
        {
            "scenario_id": "s1",
            "scenario_name": "Ransomware",
            "financial": {
                "evidence_ceiling_label": "General industry evidence",
                "analyst_baseline_load_bearing": True,
                "verdict": "challenges",
            },
            "probability": {
                "evidence_ceiling_label": "Sector-specific evidence",
                "analyst_baseline_load_bearing": False,
                "verdict": "supports",
            },
        },
        {
            "scenario_id": "s2",
            "scenario_name": "Insider misuse",
            "financial": {
                "evidence_ceiling_label": "Asset-specific evidence",
                "analyst_baseline_load_bearing": False,
                "verdict": "supports",
            },
            "probability": {
                "evidence_ceiling_label": "Asset-specific evidence",
                "analyst_baseline_load_bearing": False,
                "verdict": "supports",
            },
        },
    ],
}


def test_assessor_flags_load_bearing_scenarios():
    from tools.evidence_ceiling_assessor import assess_evidence_ceilings
    result = assess_evidence_ceilings(MOCK_REGISTER_VALIDATION)
    assert "warnings" in result
    assert "summary" in result
    warning_texts = " ".join(w["message"] for w in result["warnings"])
    assert "Ransomware" in warning_texts
    assert "financial" in warning_texts.lower() or "Financial" in warning_texts


def test_assessor_no_warnings_when_all_specific():
    from tools.evidence_ceiling_assessor import assess_evidence_ceilings
    validation_clean = {
        "register_id": "test",
        "scenarios": [MOCK_REGISTER_VALIDATION["scenarios"][1]],
    }
    result = assess_evidence_ceilings(validation_clean)
    assert result["warnings"] == []


def test_assessor_summary_counts():
    from tools.evidence_ceiling_assessor import assess_evidence_ceilings
    result = assess_evidence_ceilings(MOCK_REGISTER_VALIDATION)
    s = result["summary"]
    assert s["total_dimensions"] == 4
    assert s["load_bearing_count"] == 1
    assert s["best_ceiling_tier"] == 1


def test_assessor_critical_severity_for_load_bearing():
    from tools.evidence_ceiling_assessor import assess_evidence_ceilings
    result = assess_evidence_ceilings(MOCK_REGISTER_VALIDATION)
    critical_warnings = [w for w in result["warnings"] if w["severity"] == "critical"]
    assert len(critical_warnings) == 1
    assert critical_warnings[0]["scenario"] == "Ransomware"
    assert critical_warnings[0]["dimension"] == "financial"


def test_assessor_advisory_for_general_with_baseline():
    from tools.evidence_ceiling_assessor import assess_evidence_ceilings
    validation = {
        "register_id": "test",
        "scenarios": [{
            "scenario_id": "s3",
            "scenario_name": "DoS attack",
            "financial": {
                "evidence_ceiling_label": "General industry evidence",
                "analyst_baseline_load_bearing": False,  # has baseline
                "verdict": "supports",
            },
            "probability": {
                "evidence_ceiling_label": "Sector-specific evidence",
                "analyst_baseline_load_bearing": False,
                "verdict": "supports",
            },
        }],
    }
    result = assess_evidence_ceilings(validation)
    # Should have 1 advisory (general but has baseline), no critical
    assert len(result["warnings"]) == 1
    assert result["warnings"][0]["severity"] == "advisory"
    assert result["summary"]["load_bearing_count"] == 0
