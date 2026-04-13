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
$22,000,000 at risk. Service delivery continuity for 25% of global operations at stake. North American wind farm service delivery timelines are at risk of disruption.
"""


MOCK_SECTIONS = {
    "APAC": {
        "brief_headlines": {
            "why": "Ransomware campaign targeting APAC energy-sector OT environments — consistent with state-nexus actor TTPs. Supply chain vector identified via three regional vendors — medium confidence, not yet confirmed in AeroGrid environment.",
            "how": "In March 2026, a ransomware group with suspected state-nexus links launched targeted intrusion attempts against energy-sector OT environments across the Asia-Pacific region. Three AeroGrid vendor partners in the region reported anomalous access attempts consistent with the campaign's known TTPs.",
            "so_what": "AeroGrid's APAC turbine control infrastructure may be within the campaign's targeting envelope — immediate offline backup validation is recommended."
        },
        "source_metadata": {
            "osint": {"source_count": 4, "corroboration_tier": "2 corroborated"},
            "seerist": {"verified_event_count": 2}
        },
        "scenario_match": "State-Nexus OT Ransomware Campaign",
        "dominant_pillar": "CYBER",
        "admiralty": "B2",
        "corroboration_tier": "2 corroborated",
        "action_bullets": [
            "Validate offline backup integrity for turbine control systems",
            "Review vendor access controls with regional ops teams"
        ],
        "watch_bullets": [
            "Monitor for further OT-targeting indicators in APAC energy sector",
            "Track vendor partner security posture across three identified firms"
        ],
        "intel_bullets": [
            "Three AeroGrid vendor partners reported anomalous access attempts [B2]",
            "Campaign TTPs consistent with known state-nexus group tooling [C3]"
        ],
        "why_text": "Emerging ransomware pattern in APAC energy sector.",
        "how_text": "Ransomware group launched intrusion attempts in March 2026.",
        "so_what_text": "OT infrastructure may be within targeting envelope."
    },
    "AME": {
        "brief_headlines": {
            "why": "",
            "how": "",
            "so_what": ""
        },
        "source_metadata": {
            "osint": {"source_count": 2, "corroboration_tier": "1 corroborated"},
            "seerist": {"verified_event_count": 1}
        },
        "scenario_match": "Supply Chain Disruption — Gulf",
        "dominant_pillar": "GEO",
        "admiralty": "C3",
        "corroboration_tier": "1 corroborated",
        "action_bullets": ["Review vendor access controls with regional ops teams"],
        "watch_bullets": ["Track Gulf supply chain exposure"],
        "intel_bullets": [],
        "why_text": "Supply chain disruption risk elevated in Gulf region.",
        "how_text": "Geopolitical tensions affecting logistics routes.",
        "so_what_text": "Procurement timelines may be affected."
    },
    "MED": {
        "brief_headlines": {
            "why": "State-nexus ransomware campaign extending into Mediterranean energy infrastructure — same actor TTPs as APAC cluster.",
            "how": "The same ransomware campaign identified in APAC has been observed probing Mediterranean energy infrastructure in April 2026. Two confirmed intrusion attempts against regional grid operators.",
            "so_what": "AeroGrid MED operations share infrastructure topology with confirmed targets — escalation response aligned with APAC track."
        },
        "source_metadata": {
            "osint": {"source_count": 3, "corroboration_tier": "2 corroborated"},
            "seerist": {"verified_event_count": 1}
        },
        "scenario_match": "State-Nexus OT Ransomware Campaign",
        "dominant_pillar": "CYBER",
        "admiralty": "B2",
        "corroboration_tier": "2 corroborated",
        "action_bullets": [
            "Validate offline backup integrity for turbine control systems",
            "Brief senior leadership on emerging risk indicators"
        ],
        "watch_bullets": ["Monitor Mediterranean grid operator targeting"],
        "intel_bullets": ["Two confirmed intrusion attempts against MED grid operators [B2]"],
        "why_text": "MED energy infrastructure probed by same ransomware actor.",
        "how_text": "Intrusion attempts observed in April 2026.",
        "so_what_text": "MED operations share topology with confirmed targets."
    }
}


@pytest.fixture
def mock_output(tmp_path):
    """Create a minimal mock output/ tree under tmp_path.

    Matches the canonical pipeline layout:
      tmp_path/pipeline/run_manifest.json
      tmp_path/pipeline/global_report.json
      tmp_path/regional/{region}/data.json
      tmp_path/regional/{region}/report.md  (escalated regions)

    Returns tmp_path/pipeline — the value passed as output_dir to build().
    """
    pipeline_dir = tmp_path / "pipeline"
    pipeline_dir.mkdir()

    # pipeline-level files
    (pipeline_dir / "run_manifest.json").write_text(
        json.dumps(MOCK_MANIFEST), encoding="utf-8"
    )
    (pipeline_dir / "global_report.json").write_text(
        json.dumps(MOCK_GLOBAL_REPORT), encoding="utf-8"
    )

    # regional data (sibling of pipeline/, not nested inside it)
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

    # Write sections.json for regions that have brief_headlines
    for region in ["APAC", "AME", "MED"]:
        region_dir = tmp_path / "regional" / region.lower()
        region_dir.mkdir(parents=True, exist_ok=True)
        (region_dir / "sections.json").write_text(json.dumps(MOCK_SECTIONS[region]))

    return pipeline_dir
