#!/usr/bin/env python3
"""Deterministic section extraction — replaces analyst agent Steps 6-8.

Reads claims.json (with bullets array) + scenario_map.json.
Writes signal_clusters.json, sections.json, and updates data.json.

Usage:
    uv run python tools/extract_sections.py REGION
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

OUTPUT_ROOT = Path("output")

# Action bullets lookup — keyed by scenario name.
# Previously hardcoded in analyst prompt, now in Python.
ACTION_BULLETS = {
    "Ransomware": [
        "Validate offline backup integrity for turbine control systems",
        "Test OT network segmentation between enterprise and SCADA environments",
        "Brief regional service teams on phishing indicators targeting engineering credentials",
    ],
    "System intrusion": [
        "Audit privileged access to predictive maintenance algorithm repositories",
        "Review network monitoring coverage for lateral movement indicators in OT zones",
        "Validate endpoint detection coverage on engineering workstations",
    ],
    "Accidental disclosure": [
        "Review data classification policies for proprietary turbine design documents",
        "Audit third-party contractor access to sensitive IP repositories",
        "Validate DLP controls on engineering file shares and collaboration platforms",
    ],
    "Insider misuse": [
        "Review access logs for unusual data exfiltration patterns from IP repositories",
        "Audit privileged user activity on blade design and manufacturing systems",
        "Brief HR and security teams on insider threat indicators relevant to departing personnel",
    ],
    "Supply chain compromise": [
        "Audit software update verification procedures for industrial automation systems",
        "Review third-party vendor security assessment schedules",
        "Validate code signing and integrity checks on OT firmware updates",
    ],
}

# Signal type labels
SIGNAL_TYPE_LABELS = {
    "Confirmed Incident": "Confirmed Incident",
    "Emerging Pattern": "Emerging Pattern",
    "Trend": "Emerging Pattern",
    "Confirmed Incident + Emerging Pattern": "Confirmed Incident + Emerging Pattern",
}

# Status labels from dominant_pillar
STATUS_LABELS = {
    "Geopolitical": "[ESCALATED — GEO-LED]",
    "Cyber": "[ESCALATED — CYBER-LED]",
    "Business": "[ESCALATED — BUSINESS-LED]",
}


def _group_bullets(bullets: list[dict]) -> dict:
    """Group bullets by section into sections.json arrays."""
    groups = {
        "intel_bullets": [],
        "adversary_bullets": [],
        "impact_bullets": [],
        "watch_bullets": [],
    }
    section_map = {
        "intel": "intel_bullets",
        "adversary": "adversary_bullets",
        "impact": "impact_bullets",
        "watch": "watch_bullets",
    }
    for b in bullets:
        key = section_map.get(b.get("section", ""), "intel_bullets")
        groups[key].append(b["text"])
    return groups


def _group_claims_by_pillar(claims: list[dict]) -> dict:
    """Group claims into signal clusters by pillar."""
    clusters = {}
    for c in claims:
        pillar = c.get("pillar", "unknown")
        clusters.setdefault(pillar, [])
        clusters[pillar].append({
            "claim_id": c["claim_id"],
            "text": c["text"],
            "signal_ids": c.get("signal_ids", []),
            "confidence": c.get("confidence", "Assessed"),
        })
    return clusters


def _get_action_bullets(scenario: str, region: str) -> list[str]:
    """Lookup action bullets by scenario name."""
    return ACTION_BULLETS.get(scenario, [
        f"Review regional threat posture for {region} in light of current intelligence",
        "Brief senior leadership on emerging risk indicators",
    ])


def _extract_metadata(claims_data: dict) -> dict:
    """Extract metadata fields from claims.json header."""
    return {
        "primary_scenario": claims_data.get("primary_scenario", ""),
        "financial_rank": claims_data.get("financial_rank", 0),
        "signal_type": claims_data.get("signal_type", ""),
        "threat_actor": claims_data.get("threat_actor", ""),
    }


def extract(region: str) -> None:
    """Run extraction for a region."""
    region = region.upper()
    base = OUTPUT_ROOT / "regional" / region.lower()

    claims_path = base / "claims.json"
    data_path = base / "data.json"

    if not claims_path.exists():
        print(f"[extract_sections] No claims.json for {region} — skipping", file=sys.stderr)
        return

    claims_data = json.loads(claims_path.read_text(encoding="utf-8"))
    claims = claims_data.get("claims", [])
    bullets = claims_data.get("bullets", [])

    # 1. Build signal_clusters.json
    clusters = _group_claims_by_pillar(claims)
    clusters_path = base / "signal_clusters.json"
    clusters_path.write_text(json.dumps(clusters, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[extract_sections] wrote {clusters_path}", file=sys.stderr)

    # 2. Build sections.json
    grouped = _group_bullets(bullets)

    # Add action bullets from lookup
    scenario = claims_data.get("primary_scenario", "")
    grouped["action_bullets"] = _get_action_bullets(scenario, region)

    # Add labels
    meta = _extract_metadata(claims_data)
    dominant_pillar = ""
    if data_path.exists():
        data = json.loads(data_path.read_text(encoding="utf-8"))
        dominant_pillar = data.get("dominant_pillar", "")

    signal_type = meta.get("signal_type", "Emerging Pattern")
    grouped["signal_type_label"] = SIGNAL_TYPE_LABELS.get(signal_type, signal_type)
    grouped["status_label"] = STATUS_LABELS.get(dominant_pillar, "[ESCALATED]")

    sections_path = base / "sections.json"
    sections_path.write_text(json.dumps(grouped, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[extract_sections] wrote {sections_path}", file=sys.stderr)

    # 3. Update data.json with metadata from claims
    if data_path.exists():
        data = json.loads(data_path.read_text(encoding="utf-8"))
        data["primary_scenario"] = meta["primary_scenario"]
        data["financial_rank"] = meta["financial_rank"]
        data["signal_type"] = meta["signal_type"]
        data["threat_actor"] = meta["threat_actor"]
        data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[extract_sections] updated {data_path}", file=sys.stderr)


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: extract_sections.py REGION", file=sys.stderr)
        sys.exit(1)
    extract(args[0])


if __name__ == "__main__":
    main()
