"""Tests for report_builder.py — data layer."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from report_builder import RegionStatus, RegionEntry, ReportData


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
