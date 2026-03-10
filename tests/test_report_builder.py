"""Tests for report_builder.py — data layer."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from report_builder import RegionStatus, RegionEntry, ReportData, _parse_pillars, build


def test_region_status_values():
    assert RegionStatus.ESCALATED == "escalated"
    assert RegionStatus.MONITOR == "monitor"
    assert RegionStatus.CLEAR == "clear"


def test_region_entry_is_dataclass():
    entry = RegionEntry(
        name="APAC", status=RegionStatus.ESCALATED,
        vacr=18_500_000.0, admiralty="B2", velocity="stable",
        severity="HIGH", scenario_match="System intrusion",
        why_text="geo text", how_text="cyber text", so_what_text="biz text",
    )
    assert entry.name == "APAC"
    assert entry.status == RegionStatus.ESCALATED
    assert entry.vacr == 18_500_000.0


def test_report_data_derived_counts():
    regions = [
        RegionEntry("APAC", RegionStatus.ESCALATED, 18_500_000, "B2", "stable", "HIGH", "Sys", "w", "h", "s"),
        RegionEntry("AME",  RegionStatus.ESCALATED, 22_000_000, "A1", "accelerating", "CRITICAL", "Ransomware", "w", "h", "s"),
        RegionEntry("MED",  RegionStatus.MONITOR,    4_200_000, "C3", "stable", "MEDIUM", "Insider", None, None, None),
        RegionEntry("LATAM",RegionStatus.CLEAR,      0,         "A1", "unknown", "LOW", None, None, None, None),
        RegionEntry("NCE",  RegionStatus.CLEAR,      0,         "A1", "unknown", "LOW", None, None, None, None),
    ]
    data = ReportData(
        run_id="crq-test-001", timestamp="2026-03-10T08:00:00Z",
        total_vacr=44_700_000.0,
        exec_summary="Two regions at risk.",
        escalated_count=2, monitor_count=1, clear_count=2,
        regions=regions, monitor_regions=["MED"],
    )
    assert data.escalated_count == 2
    assert data.monitor_count == 1
    assert data.clear_count == 2


def test_parse_pillars_designed_headers():
    md = """# APAC Brief

## Why — Geopolitical Driver
State actors targeting supply chain.

## How — Cyber Vector
OT network intrusion attempts.

## So What — Business Impact
$18.5M at risk.
"""
    why, how, so_what = _parse_pillars(md)
    assert "State actors" in why
    assert "OT network" in how
    assert "$18.5M" in so_what


def test_parse_pillars_legacy_headers():
    """Backward compat with old agent output that uses different headers."""
    md = """# APAC Brief

## Situation Overview
State actors targeting supply chain.

## Risk Context and Empirical Baseline
OT network intrusion attempts.

## Board-Level Implication
$18.5M at risk.
"""
    why, how, so_what = _parse_pillars(md)
    assert "State actors" in why
    assert "OT network" in how
    assert "$18.5M" in so_what


def test_parse_pillars_unrecognised_returns_full_text():
    md = "Just a plain report with no headers."
    why, how, so_what = _parse_pillars(md)
    assert "plain report" in why
    assert how is None
    assert so_what is None


def test_build_from_mock_output(mock_output):
    data = build(output_dir=str(mock_output))

    assert data.run_id == "crq-test-001"
    assert data.total_vacr == 44_700_000.0
    assert data.escalated_count == 2
    assert data.monitor_count == 1
    assert data.clear_count == 2
    assert len(data.regions) == 5


def test_build_escalated_regions_have_pillar_text(mock_output):
    data = build(output_dir=str(mock_output))
    apac = next(r for r in data.regions if r.name == "APAC")
    assert apac.status == RegionStatus.ESCALATED
    assert apac.why_text is not None
    assert "State-sponsored" in apac.why_text
    assert apac.how_text is not None
    assert apac.so_what_text is not None


def test_build_clear_regions_have_no_pillar_text(mock_output):
    data = build(output_dir=str(mock_output))
    latam = next(r for r in data.regions if r.name == "LATAM")
    assert latam.status == RegionStatus.CLEAR
    assert latam.why_text is None
    assert latam.how_text is None


def test_build_graceful_when_report_md_missing(mock_output):
    """build() should not raise if report.md is absent for an escalated region."""
    (mock_output / "regional" / "ame" / "report.md").unlink()
    data = build(output_dir=str(mock_output))
    ame = next(r for r in data.regions if r.name == "AME")
    assert ame.status == RegionStatus.ESCALATED
    assert ame.why_text is None  # graceful — no crash
