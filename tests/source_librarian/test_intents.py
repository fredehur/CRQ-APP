"""Tests for tools/source_librarian/intents.py — yaml loading + validation."""
from pathlib import Path

import pytest
from pydantic import ValidationError

FIX = Path(__file__).parent / "fixtures"


def test_load_intent_returns_pydantic_model():
    from tools.source_librarian.intents import load_intent_file
    intent = load_intent_file(FIX / "intent_wind_minimal.yaml")
    assert intent.register_id == "wind_test"
    assert "WP-001" in intent.scenarios
    sc = intent.scenarios["WP-001"]
    assert sc.name == "System intrusion into OT/SCADA"
    assert sc.threat_terms[0] == "system intrusion"
    assert sc.time_focus_years == 3


def test_load_intent_yaml_text_round_trip():
    from tools.source_librarian.intents import load_intent_file
    intent = load_intent_file(FIX / "intent_wind_minimal.yaml")
    assert "register_id: wind_test" in intent.raw_yaml


def test_load_intent_missing_threat_terms_fails(tmp_path):
    from tools.source_librarian.intents import load_intent_file
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "register_id: bad\n"
        "register_name: Bad\n"
        "industry: x\n"
        "sub_industry: y\n"
        "geography: {primary: [], secondary: []}\n"
        "scenarios:\n"
        "  X-001:\n"
        "    name: oops\n"
        "    asset_terms: [a]\n"
        "    industry_terms: [b]\n"
        "    time_focus_years: 1\n"
        "    notes: ''\n"
        "query_modifiers: {news_set: ['{threat}'], doc_set: ['{threat}']}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_intent_file(bad)


def test_load_publishers_returns_matcher():
    from tools.source_librarian.intents import load_publishers_file
    pubs = load_publishers_file(FIX / "publishers_minimal.yaml")
    assert pubs.tier_for("https://dragos.com/2024-yir") == "T1"
    assert pubs.tier_for("https://www.dragos.com/2024-yir") == "T1"  # www stripped
    assert pubs.tier_for("https://www.ibm.com/security/data-breach") == "T1"
    assert pubs.tier_for("https://www.ibm.com/cloud") is None  # ibm.com alone is not T1
    assert pubs.tier_for("https://claroty.com/blog/x") == "T2"
    assert pubs.tier_for("https://bleepingcomputer.com/news") == "T3"
    assert pubs.tier_for("https://random-blog.example/post") is None


def test_publishers_publisher_label():
    from tools.source_librarian.intents import load_publishers_file
    pubs = load_publishers_file(FIX / "publishers_minimal.yaml")
    assert pubs.publisher_for("https://www.dragos.com/r") == "dragos.com"
    assert pubs.publisher_for("https://www.ibm.com/security/x") == "ibm.com/security"
