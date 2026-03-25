"""Shared pytest fixtures — creates a minimal mock output tree in a temp dir."""
import json
import pytest


REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]

MOCK_MANIFEST = {
    "pipeline_id": "crq-test-001",
    "client": "AeroGrid Wind Solutions",
    "run_timestamp": "2026-03-10T08:00:00Z",
    "status": "complete",
    "total_vacr_exposure_usd": 44700000,
    "regions": {
        "APAC": {"status": "escalated", "severity": "HIGH", "vacr_usd": 18500000,
                 "admiralty": "B2", "velocity": "stable", "dominant_pillar": "Geopolitical"},
        "AME":  {"status": "escalated", "severity": "CRITICAL", "vacr_usd": 22000000,
                 "admiralty": "A1", "velocity": "accelerating", "dominant_pillar": "Cyber"},
        "LATAM":{"status": "clear",    "severity": "LOW",      "vacr_usd": 0,
                 "admiralty": "A1", "velocity": "unknown", "dominant_pillar": None},
        "MED":  {"status": "monitor",  "severity": "MEDIUM",   "vacr_usd": 4200000,
                 "admiralty": "C3", "velocity": "stable", "dominant_pillar": "Geopolitical"},
        "NCE":  {"status": "clear",    "severity": "LOW",      "vacr_usd": 0,
                 "admiralty": "A1", "velocity": "unknown", "dominant_pillar": None},
    }
}

MOCK_GLOBAL_REPORT = {
    "total_vacr_exposure": 44700000,
    "executive_summary": "Two regions are at elevated risk. Total exposure is $44.7M.",
    "regional_threats": [
        {"region": "APAC", "scenario": "System intrusion", "vacr_usd": 18500000,
         "admiralty_rating": "B2", "velocity": "stable"},
        {"region": "AME", "scenario": "Ransomware", "vacr_usd": 22000000,
         "admiralty_rating": "A1", "velocity": "accelerating"},
    ],
    "monitor_regions": ["MED"],
}

MOCK_DATA_JSONS = {
    "APAC":  {"region": "APAC",  "status": "escalated", "severity": "HIGH",
              "vacr_exposure_usd": 18500000, "admiralty": "B2", "velocity": "stable",
              "primary_scenario": "System intrusion", "dominant_pillar": "Geopolitical"},
    "AME":   {"region": "AME",   "status": "escalated", "severity": "CRITICAL",
              "vacr_exposure_usd": 22000000, "admiralty": "A1", "velocity": "accelerating",
              "primary_scenario": "Ransomware", "dominant_pillar": "Cyber"},
    "LATAM": {"region": "LATAM", "status": "clear",     "severity": "LOW",
              "vacr_exposure_usd": 0, "admiralty": "A1", "velocity": "unknown",
              "primary_scenario": None, "dominant_pillar": None},
    "MED":   {"region": "MED",   "status": "monitor",   "severity": "MEDIUM",
              "vacr_exposure_usd": 4200000, "admiralty": "C3", "velocity": "stable",
              "primary_scenario": "Insider misuse", "dominant_pillar": "Geopolitical"},
    "NCE":   {"region": "NCE",   "status": "clear",     "severity": "LOW",
              "vacr_exposure_usd": 0, "admiralty": "A1", "velocity": "unknown",
              "primary_scenario": None, "dominant_pillar": None},
}

APAC_REPORT_MD = """# APAC Regional Executive Brief

## Why — Geopolitical Driver
State-sponsored groups in the South China Sea corridor are targeting supply chain access.

## How — Cyber Vector
System intrusion attempts targeting OT networks at blade manufacturing plants.

## So What — Business Impact
$18,500,000 at risk. Disruption threatens 75% of AeroGrid's manufacturing revenue. Watch for further escalation if diplomatic tensions intensify.
"""

AME_REPORT_MD = """# AME Regional Executive Brief

## Why — Geopolitical Driver
Ransomware groups exploiting North American energy sector during regulatory transition.

## How — Cyber Vector
Double-extortion ransomware targeting backup systems and operational databases.

## So What — Business Impact
$22,000,000 at risk. Service delivery continuity for 25% of global operations at stake. Continued monitoring of threat actor activity is warranted.
"""


@pytest.fixture
def mock_output(tmp_path):
    """Create a minimal mock output/ tree under tmp_path. Returns the root path."""
    # run_manifest.json
    (tmp_path / "run_manifest.json").write_text(
        json.dumps(MOCK_MANIFEST), encoding="utf-8"
    )
    # global_report.json
    (tmp_path / "global_report.json").write_text(
        json.dumps(MOCK_GLOBAL_REPORT), encoding="utf-8"
    )
    # regional data
    for region, data in MOCK_DATA_JSONS.items():
        region_dir = tmp_path / "regional" / region.lower()
        region_dir.mkdir(parents=True)
        (region_dir / "data.json").write_text(json.dumps(data), encoding="utf-8")

    # escalated report.md files
    (tmp_path / "regional" / "apac" / "report.md").write_text(
        APAC_REPORT_MD, encoding="utf-8"
    )
    (tmp_path / "regional" / "ame" / "report.md").write_text(
        AME_REPORT_MD, encoding="utf-8"
    )
    return tmp_path
