# tests/test_extract_sections_source_split.py
"""Tests for source metadata, headline pass-through, and extract() integration."""
import json
import pytest
from pathlib import Path


# --- Fixtures ---

def _make_seerist(hotspots=None, verified=None, avg_delta=0.0):
    return {
        "situational": {
            "events": [],
            "verified_events": verified or [],
            "breaking_news": [],
            "news": [],
        },
        "analytical": {
            "hotspots": hotspots or [],
            "pulse": {"region_summary": {"avg_delta": avg_delta}},
        },
    }


def _make_osint(sources=None, signal_type="Emerging Pattern"):
    return {
        "dominant_pillar": "geo",
        "signal_type": signal_type,
        "sources": sources or [],
        "lead_indicators": [],
    }


def _make_claims(why_summary="Why headline", how_summary="How headline",
                 so_what_summary="So what headline"):
    return {
        "region": "APAC",
        "convergence_assessment": {"category": "CONVERGE", "rationale": "Test"},
        "why_summary": why_summary,
        "how_summary": how_summary,
        "so_what_summary": so_what_summary,
        "claims": [],
    }


# --- Source metadata tests ---

def test_seerist_metadata_high_strength_with_hotspot():
    from tools.extract_sections import _build_source_metadata
    seerist = _make_seerist(hotspots=[
        {"signal_id": "seerist:hotspot:apac-001", "anomaly_flag": True, "location": "Taipei"},
    ])
    osint = _make_osint(sources=[{"name": "Reuters", "url": "https://reuters.com"}])
    meta = _build_source_metadata(seerist, osint)
    assert meta["seerist"]["strength"] == "high"
    assert "Taipei" in meta["seerist"]["hotspots"][0]


def test_seerist_metadata_none_when_empty():
    from tools.extract_sections import _build_source_metadata
    meta = _build_source_metadata({}, {})
    assert meta["seerist"]["strength"] == "none"
    assert meta["seerist"]["hotspots"] == []


def test_osint_metadata_source_count_and_names():
    from tools.extract_sections import _build_source_metadata
    osint = _make_osint(sources=[
        {"name": "Reuters", "url": "https://reuters.com"},
        {"name": "Mandiant", "url": "https://mandiant.com"},
    ])
    meta = _build_source_metadata({}, osint)
    assert meta["osint"]["source_count"] == 2
    assert "Reuters" in meta["osint"]["sources"]
    assert "Mandiant" in meta["osint"]["sources"]


def test_osint_metadata_deduplicates_sources():
    from tools.extract_sections import _build_source_metadata
    osint = _make_osint(sources=[
        {"name": "Reuters", "url": "https://reuters.com"},
        {"name": "Reuters", "url": "https://reuters.com/other"},
    ])
    meta = _build_source_metadata({}, osint)
    assert meta["osint"]["source_count"] == 1


# --- Headline pass-through tests ---

def test_brief_headlines_extracted_from_summary_fields():
    from tools.extract_sections import _extract_brief_headlines
    claims_data = _make_claims(
        why_summary="PLA drills elevate cross-strait risk",
        how_summary="APT actors targeting OT networks",
        so_what_summary="Taipei manufacturing faces disruption risk",
    )
    h = _extract_brief_headlines(claims_data)
    assert h["why"] == "PLA drills elevate cross-strait risk"
    assert h["how"] == "APT actors targeting OT networks"
    assert h["so_what"] == "Taipei manufacturing faces disruption risk"


def test_brief_headlines_default_to_empty_string_when_absent():
    from tools.extract_sections import _extract_brief_headlines
    h = _extract_brief_headlines({})
    assert h["why"] == ""
    assert h["how"] == ""
    assert h["so_what"] == ""


# --- Integration test: extract() writes new fields to disk ---

def test_extract_writes_source_metadata_and_headlines(tmp_path, monkeypatch):
    import tools.extract_sections as es
    monkeypatch.setattr(es, "OUTPUT_ROOT", tmp_path / "output")

    region_dir = tmp_path / "output" / "regional" / "apac"
    region_dir.mkdir(parents=True)

    (region_dir / "claims.json").write_text(json.dumps(_make_claims(
        why_summary="Why test",
        how_summary="How test",
        so_what_summary="So what test",
    )))
    (region_dir / "seerist_signals.json").write_text(json.dumps(_make_seerist(
        hotspots=[{"signal_id": "seerist:hotspot:apac-001", "anomaly_flag": True, "location": "Taipei"}]
    )))
    (region_dir / "osint_signals.json").write_text(json.dumps(_make_osint(
        sources=[{"name": "Reuters", "url": "https://reuters.com"}]
    )))
    (region_dir / "data.json").write_text(json.dumps({"dominant_pillar": "geo"}))

    es.extract("APAC")

    sections = json.loads((region_dir / "sections.json").read_text())
    assert "source_metadata" in sections
    assert sections["source_metadata"]["seerist"]["strength"] == "high"
    assert sections["source_metadata"]["osint"]["source_count"] == 1
    assert "brief_headlines" in sections
    assert sections["brief_headlines"]["why"] == "Why test"
    assert sections["brief_headlines"]["how"] == "How test"
    assert sections["brief_headlines"]["so_what"] == "So what test"
