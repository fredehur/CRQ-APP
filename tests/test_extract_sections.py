"""Tests for extract_sections.py — deterministic section extraction."""
import json
import pytest
from pathlib import Path


def test_group_claims_into_bullets_by_bullets_field():
    """Claims with bullets field route to correct sections.json arrays."""
    from tools.extract_sections import _group_claims_into_bullets

    claims = [
        {"text": "Intel finding 1", "bullets": "intel_bullets", "paragraph": "why"},
        {"text": "Intel finding 2", "bullets": "intel_bullets", "paragraph": "why"},
        {"text": "Adversary activity", "bullets": "adversary_bullets", "paragraph": "how"},
        {"text": "Impact assessment", "bullets": "impact_bullets", "paragraph": "sowhat"},
        {"text": "Watch indicator", "bullets": "watch_bullets", "paragraph": "watch"},
    ]

    grouped = _group_claims_into_bullets(claims)
    assert len(grouped["intel_bullets"]) == 2
    assert len(grouped["adversary_bullets"]) == 1
    assert len(grouped["impact_bullets"]) == 1
    assert len(grouped["watch_bullets"]) == 1


def test_group_claims_into_bullets_legacy_paragraph_fallback():
    """Legacy claims (no bullets field) fall back to paragraph-based routing."""
    from tools.extract_sections import _group_claims_into_bullets

    claims = [
        {"text": "Why claim", "paragraph": "why"},
        {"text": "How claim", "paragraph": "how"},
        {"text": "SoWhat claim", "paragraph": "sowhat"},
        {"text": "Watch claim", "paragraph": "watch"},
    ]

    grouped = _group_claims_into_bullets(claims)
    assert len(grouped["intel_bullets"]) == 1
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


def test_extract_metadata_prefers_data_json():
    """data.json values take precedence over claims.json top-level fields."""
    from tools.extract_sections import _extract_metadata

    claims_data = {
        "primary_scenario": "Ransomware",
        "financial_rank": 1,
        "signal_type": "Trend",
        "threat_actor": "Volt Typhoon",
    }
    data = {
        "primary_scenario": "System intrusion",
        "financial_rank": 3,
        "signal_type": "Event",
        "threat_actor": "APT41",
    }

    meta = _extract_metadata(claims_data, data)
    assert meta["primary_scenario"] == "System intrusion"
    assert meta["financial_rank"] == 3
    assert meta["signal_type"] == "Event"
    assert meta["threat_actor"] == "APT41"


def test_signal_type_label_mapping():
    """SIGNAL_TYPE_LABELS maps all three analyst values to display strings."""
    from tools.extract_sections import SIGNAL_TYPE_LABELS

    assert SIGNAL_TYPE_LABELS["Event"] == "Confirmed Incident"
    assert SIGNAL_TYPE_LABELS["Trend"] == "Emerging Pattern"
    assert SIGNAL_TYPE_LABELS["Mixed"] == "Confirmed Incident + Emerging Pattern"
