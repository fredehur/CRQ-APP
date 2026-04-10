"""Tests for extract_sections.py — deterministic section extraction."""
import json
import pytest
from pathlib import Path


def test_group_bullets_by_section():
    """Bullets route to correct sections.json arrays."""
    from tools.extract_sections import _group_bullets

    bullets = [
        {"text": "Intel finding 1", "section": "intel", "paragraph": "why"},
        {"text": "Intel finding 2", "section": "intel", "paragraph": "why"},
        {"text": "Adversary activity", "section": "adversary", "paragraph": "how"},
        {"text": "Impact assessment", "section": "impact", "paragraph": "sowhat"},
        {"text": "Watch indicator", "section": "watch", "paragraph": "sowhat"},
    ]

    grouped = _group_bullets(bullets)
    assert len(grouped["intel_bullets"]) == 2
    assert len(grouped["adversary_bullets"]) == 1
    assert len(grouped["impact_bullets"]) == 1
    assert len(grouped["watch_bullets"]) == 1


def test_group_claims_by_pillar():
    """Claims group into signal_clusters by pillar."""
    from tools.extract_sections import _group_claims_by_pillar

    claims = [
        {"claim_id": "apac-001", "pillar": "geopolitical", "text": "Geo claim", "signal_ids": ["osint:tavily:apac-geo-001"]},
        {"claim_id": "apac-002", "pillar": "cyber", "text": "Cyber claim", "signal_ids": ["osint:tavily:apac-cyber-001"]},
        {"claim_id": "apac-003", "pillar": "geopolitical", "text": "Geo claim 2", "signal_ids": ["osint:tavily:apac-geo-002"]},
    ]

    clusters = _group_claims_by_pillar(claims)
    assert len(clusters["geopolitical"]) == 2
    assert len(clusters["cyber"]) == 1


def test_action_bullets_lookup():
    """Action bullets come from lookup table, not from analyst."""
    from tools.extract_sections import _get_action_bullets

    bullets = _get_action_bullets("Ransomware", "APAC")
    assert len(bullets) >= 1
    assert all(isinstance(b, str) for b in bullets)


def test_extract_metadata_from_claims():
    """Metadata fields copy from claims.json header."""
    from tools.extract_sections import _extract_metadata

    claims_data = {
        "primary_scenario": "Ransomware",
        "financial_rank": 1,
        "signal_type": "Trend",
        "threat_actor": "Volt Typhoon",
    }

    meta = _extract_metadata(claims_data)
    assert meta["primary_scenario"] == "Ransomware"
    assert meta["financial_rank"] == 1
    assert meta["signal_type"] == "Trend"
    assert meta["threat_actor"] == "Volt Typhoon"
