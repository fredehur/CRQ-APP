"""Tests for research_collector.py — target-centric OSINT collection loop."""
import json
import pytest


REQUIRED_TOP_LEVEL = {"region", "collected_at", "working_theory", "collection", "conclusion"}
REQUIRED_WORKING_THEORY = {"scenario_name", "vacr_usd", "hypothesis", "active_topics", "geo_queries", "cyber_queries"}
REQUIRED_COLLECTION = {"pass_1_result_count", "gap_assessment", "gaps_identified", "pass_2_queries", "pass_2_result_count", "total_result_count"}
REQUIRED_CONCLUSION = {"theory_confirmed", "confidence_rationale", "suggested_admiralty", "signal_type", "dominant_pillar"}


def validate_scratchpad(data: dict) -> list[str]:
    """Returns list of schema violations. Empty list = valid."""
    errors = []
    for key in REQUIRED_TOP_LEVEL:
        if key not in data:
            errors.append(f"Missing top-level key: {key}")
    if "working_theory" in data:
        for key in REQUIRED_WORKING_THEORY:
            if key not in data["working_theory"]:
                errors.append(f"Missing working_theory.{key}")
    if "collection" in data:
        for key in REQUIRED_COLLECTION:
            if key not in data["collection"]:
                errors.append(f"Missing collection.{key}")
    if "conclusion" in data:
        for key in REQUIRED_CONCLUSION:
            if key not in data["conclusion"]:
                errors.append(f"Missing conclusion.{key}")
    return errors


def test_validate_scratchpad_passes_valid_data():
    valid = {
        "region": "AME",
        "collected_at": "2026-03-16T10:00:00Z",
        "working_theory": {
            "scenario_name": "Wind Farm Telemetry Disruption",
            "vacr_usd": 22000000,
            "hypothesis": "Test hypothesis",
            "active_topics": [],
            "geo_queries": ["geo query 1"],
            "cyber_queries": ["cyber query 1"],
        },
        "collection": {
            "pass_1_result_count": 4,
            "gap_assessment": "3 sources found",
            "gaps_identified": [],
            "pass_2_queries": [],
            "pass_2_result_count": 0,
            "total_result_count": 4,
        },
        "conclusion": {
            "theory_confirmed": True,
            "confidence_rationale": "Corroborated.",
            "suggested_admiralty": "B2",
            "signal_type": "trend",
            "dominant_pillar": "Cyber",
        },
    }
    assert validate_scratchpad(valid) == []


def test_validate_scratchpad_catches_missing_keys():
    errors = validate_scratchpad({"region": "AME"})
    assert any("collected_at" in e for e in errors)
    assert any("working_theory" in e for e in errors)
    assert any("collection" in e for e in errors)
    assert any("conclusion" in e for e in errors)


import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import patch, MagicMock


def test_mock_mode_calls_geo_and_cyber_collectors():
    """In mock mode, research_collector delegates to geo_collector + cyber_collector."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        from tools.research_collector import run_mock_mode
        run_mock_mode("AME")
        calls = [str(c) for c in mock_run.call_args_list]
        assert any("geo_collector" in c for c in calls)
        assert any("cyber_collector" in c for c in calls)


def test_form_working_theory_structure():
    """form_working_theory returns dict with required keys including geo_queries and cyber_queries."""
    crq_data = {
        "AME": [{"scenario_name": "Wind Farm Telemetry & Maintenance Disruption", "value_at_cyber_risk_usd": 22000000}]
    }
    topics = [
        {"id": "ot-ics-cyber-attacks", "label": "OT/ICS Cyber Attacks", "regions": ["AME"], "active": True},
        {"id": "other-topic", "label": "Other", "regions": ["APAC"], "active": True},
    ]
    company_profile = {"industry": "Wind Energy", "crown_jewels": ["turbine designs"]}

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "hypothesis": "AME carries $22M exposure in wind telemetry...",
        "geo_queries": ["AME energy policy instability 2026", "Americas wind regulation 2026"],
        "cyber_queries": ["AME wind farm cyber attack 2026", "Americas OT ICS ransomware 2026"],
    }))]

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        from tools.research_collector import form_working_theory
        result = form_working_theory("AME", crq_data, topics, company_profile)

    assert result["scenario_name"] == "Wind Farm Telemetry & Maintenance Disruption"
    assert result["vacr_usd"] == 22000000
    assert "hypothesis" in result
    assert "geo_queries" in result and isinstance(result["geo_queries"], list)
    assert "cyber_queries" in result and isinstance(result["cyber_queries"], list)
    assert len(result["geo_queries"]) >= 2
    assert len(result["cyber_queries"]) >= 2
    # Only AME-scoped active topics
    assert all(t["id"] == "ot-ics-cyber-attacks" for t in result["active_topics"])


def test_run_search_pass_deduplicates_by_url():
    """run_search_pass deduplicates results sharing the same URL."""
    result_a = json.dumps([
        {"title": "A", "summary": "summary a", "url": "https://example.com/a", "published_date": "2026-01-01"},
        {"title": "B", "summary": "summary b", "url": "https://example.com/b", "published_date": "2026-01-02"},
    ])
    result_b = json.dumps([
        {"title": "B duplicate", "summary": "summary b again", "url": "https://example.com/b", "published_date": "2026-01-02"},
        {"title": "C", "summary": "summary c", "url": "https://example.com/c", "published_date": "2026-01-03"},
    ])

    call_count = 0
    def fake_run(cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        mock = MagicMock()
        mock.stdout = result_a if call_count == 1 else result_b
        mock.returncode = 0
        return mock

    with patch("subprocess.run", side_effect=fake_run):
        from tools.research_collector import run_search_pass
        results = run_search_pass("AME", ["query one", "query two"], "geo")

    urls = [r["url"] for r in results]
    assert len(urls) == len(set(urls)), "Duplicate URLs found"
    assert len(results) == 3  # A, B, C — B deduplicated


def test_run_search_pass_includes_type_flag():
    """run_search_pass passes --type flag to osint_search.py."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        from tools.research_collector import run_search_pass
        run_search_pass("AME", ["test query"], "cyber")
        cmd = mock_run.call_args.args[0]
        assert "--type" in cmd
        assert "cyber" in cmd


def test_run_search_pass_skips_failed_queries():
    """run_search_pass skips queries where osint_search returns non-zero."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        from tools.research_collector import run_search_pass
        results = run_search_pass("AME", ["bad query"], "geo")
    assert results == []


def test_assess_gaps_returns_no_gaps_when_sufficient():
    """assess_gaps returns run_pass_2=False when evidence is sufficient."""
    working_theory = {
        "scenario_name": "Wind Farm Telemetry Disruption",
        "vacr_usd": 22000000,
        "hypothesis": "Test hypothesis",
        "active_topics": [],
    }
    results = [
        {"title": f"Result {i}", "summary": f"summary {i}", "url": f"https://ex.com/{i}"}
        for i in range(5)
    ]

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "gap_assessment": "5 sources corroborate the hypothesis. Sufficient coverage.",
        "gaps_identified": [],
        "follow_up_queries": [],
        "follow_up_query_type": "cyber",
        "run_pass_2": False,
    }))]

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        from tools.research_collector import assess_gaps
        result = assess_gaps("AME", working_theory, results)

    assert result["run_pass_2"] is False
    assert result["gaps_identified"] == []


def test_assess_gaps_returns_queries_when_gaps_found():
    """assess_gaps returns run_pass_2=True and follow_up_queries when gaps found."""
    working_theory = {"scenario_name": "Test", "vacr_usd": 0, "hypothesis": "Test", "active_topics": []}
    results = [{"title": "Generic news", "summary": "general politics", "url": "https://ex.com/1"}]

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "gap_assessment": "No wind-sector signal found.",
        "gaps_identified": ["No energy sector specificity"],
        "follow_up_queries": ["wind turbine cyber attack AME 2026"],
        "follow_up_query_type": "cyber",
        "run_pass_2": True,
    }))]

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        from tools.research_collector import assess_gaps
        result = assess_gaps("AME", working_theory, results)

    assert result["run_pass_2"] is True
    assert len(result["follow_up_queries"]) >= 1
    assert result["follow_up_query_type"] in ("geo", "cyber")
