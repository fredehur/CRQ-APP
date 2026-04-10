"""Tests for Gate 4 — Seerist hierarchy enforcement in regional-analyst-stop.py."""
import json
import pytest
from pathlib import Path


def _write_seerist(tmp_path, region, seerist_data):
    p = tmp_path / "output" / "regional" / region
    p.mkdir(parents=True, exist_ok=True)
    (p / "seerist_signals.json").write_text(json.dumps(seerist_data))


def _write_claims(tmp_path, region, claims_data):
    p = tmp_path / "output" / "regional" / region
    p.mkdir(parents=True, exist_ok=True)
    (p / "claims.json").write_text(json.dumps(claims_data))


def _seerist_with_hotspot_anomaly():
    return {
        "situational": {"events": [], "verified_events": [], "breaking_news": [], "news": []},
        "analytical": {
            "hotspots": [{"signal_id": "seerist:hotspot:apac-001", "anomaly_flag": True}],
            "pulse": {"region_summary": {"avg_delta": 0.0}},
        },
    }


def _seerist_with_verified_event():
    return {
        "situational": {
            "events": [],
            "verified_events": [{"signal_id": "seerist:event:apac-v001", "title": "Confirmed"}],
            "breaking_news": [],
            "news": [],
        },
        "analytical": {"hotspots": [], "pulse": {"region_summary": {"avg_delta": 0.0}}},
    }


def _seerist_empty():
    return {
        "situational": {"events": [], "verified_events": [], "breaking_news": [], "news": []},
        "analytical": {"hotspots": [], "pulse": {"region_summary": {"avg_delta": 0.0}}},
    }


def _claims_with_seerist_why(hotspot_id="seerist:hotspot:apac-001"):
    return {
        "region": "APAC",
        "convergence_assessment": {"category": "CONVERGE", "rationale": "Test"},
        "claims": [
            {
                "claim_id": "apac-001",
                "paragraph": "why",
                "bullets": "intel_bullets",
                "signal_ids": [hotspot_id],
                "claim_type": "fact",
                "pillar": "geopolitical",
                "text": "Test claim",
                "confidence": "Confirmed",
            },
            {
                "claim_id": "apac-002",
                "paragraph": "watch",
                "bullets": "watch_bullets",
                "signal_ids": [],
                "claim_type": "estimate",
                "pillar": "geopolitical",
                "text": "Watch indicator",
                "confidence": "Analyst judgment",
            },
            {
                "claim_id": "apac-003",
                "paragraph": "watch",
                "bullets": "watch_bullets",
                "signal_ids": [],
                "claim_type": "estimate",
                "pillar": "geopolitical",
                "text": "Watch indicator 2",
                "confidence": "Analyst judgment",
            },
        ],
    }


def _claims_with_osint_why_only():
    return {
        "region": "APAC",
        "convergence_assessment": {"category": "CONVERGE", "rationale": "Test"},
        "claims": [
            {
                "claim_id": "apac-001",
                "paragraph": "why",
                "bullets": "intel_bullets",
                "signal_ids": ["osint:tavily:apac-geo-001"],  # OSINT only — no seerist:
                "claim_type": "fact",
                "pillar": "geopolitical",
                "text": "OSINT claim",
                "confidence": "Assessed",
            },
            {
                "claim_id": "apac-002",
                "paragraph": "watch",
                "bullets": "watch_bullets",
                "signal_ids": [],
                "claim_type": "estimate",
                "pillar": "geopolitical",
                "text": "Watch",
                "confidence": "Analyst judgment",
            },
            {
                "claim_id": "apac-003",
                "paragraph": "watch",
                "bullets": "watch_bullets",
                "signal_ids": [],
                "claim_type": "estimate",
                "pillar": "geopolitical",
                "text": "Watch 2",
                "confidence": "Analyst judgment",
            },
        ],
    }


def test_gate4_passes_when_first_why_claim_cites_seerist(tmp_path, monkeypatch):
    import tools.regional_analyst_stop_gate4 as g4
    monkeypatch.setattr(g4, "REGIONAL", tmp_path / "output" / "regional")

    _write_seerist(tmp_path, "apac", _seerist_with_hotspot_anomaly())
    _write_claims(tmp_path, "apac", _claims_with_seerist_why())

    passed, violations = g4.validate_seerist_hierarchy("apac")
    assert passed, violations


def test_gate4_fails_when_first_why_claim_is_osint_only(tmp_path, monkeypatch):
    import tools.regional_analyst_stop_gate4 as g4
    monkeypatch.setattr(g4, "REGIONAL", tmp_path / "output" / "regional")

    _write_seerist(tmp_path, "apac", _seerist_with_hotspot_anomaly())
    _write_claims(tmp_path, "apac", _claims_with_osint_why_only())

    passed, violations = g4.validate_seerist_hierarchy("apac")
    assert not passed
    assert any("first why-paragraph claim" in v for v in violations)


def test_gate4_fails_when_hotspot_signal_id_missing_from_claims(tmp_path, monkeypatch):
    """Every hotspot anomaly signal_id must appear in at least one claim."""
    import tools.regional_analyst_stop_gate4 as g4
    monkeypatch.setattr(g4, "REGIONAL", tmp_path / "output" / "regional")

    _write_seerist(tmp_path, "apac", _seerist_with_hotspot_anomaly())
    # Claims cite a different seerist signal_id — not the hotspot
    claims = _claims_with_seerist_why(hotspot_id="seerist:hotspot:apac-999")  # wrong id
    _write_claims(tmp_path, "apac", claims)

    passed, violations = g4.validate_seerist_hierarchy("apac")
    assert not passed
    assert any("seerist:hotspot:apac-001" in v for v in violations)


def test_gate4_fails_when_verified_event_missing_from_claims(tmp_path, monkeypatch):
    """Every verified_event signal_id must appear in at least one claim."""
    import tools.regional_analyst_stop_gate4 as g4
    monkeypatch.setattr(g4, "REGIONAL", tmp_path / "output" / "regional")

    _write_seerist(tmp_path, "apac", _seerist_with_verified_event())
    # Claims don't cite the verified event
    claims = _claims_with_seerist_why(hotspot_id="seerist:scribe:apac-001")
    _write_claims(tmp_path, "apac", claims)

    passed, violations = g4.validate_seerist_hierarchy("apac")
    assert not passed
    assert any("seerist:event:apac-v001" in v for v in violations)


def test_gate4_skips_gracefully_when_seerist_none(tmp_path, monkeypatch):
    import tools.regional_analyst_stop_gate4 as g4
    monkeypatch.setattr(g4, "REGIONAL", tmp_path / "output" / "regional")

    _write_seerist(tmp_path, "apac", _seerist_empty())
    _write_claims(tmp_path, "apac", _claims_with_osint_why_only())

    passed, violations = g4.validate_seerist_hierarchy("apac")
    assert passed  # seerist_strength=none → skip hierarchy check
    assert violations == []


def test_gate4_skips_gracefully_when_seerist_file_absent(tmp_path, monkeypatch):
    import tools.regional_analyst_stop_gate4 as g4
    monkeypatch.setattr(g4, "REGIONAL", tmp_path / "output" / "regional")

    # No seerist file written — only claims
    p = tmp_path / "output" / "regional" / "apac"
    p.mkdir(parents=True, exist_ok=True)
    _write_claims(tmp_path, "apac", _claims_with_osint_why_only())

    passed, violations = g4.validate_seerist_hierarchy("apac")
    assert passed
