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

from tools.seerist_strength import score_seerist_strength

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
    "Event": "Confirmed Incident",
    "Confirmed Incident": "Confirmed Incident",
    "Trend": "Emerging Pattern",
    "Emerging Pattern": "Emerging Pattern",
    "Mixed": "Confirmed Incident + Emerging Pattern",
    "Confirmed Incident + Emerging Pattern": "Confirmed Incident + Emerging Pattern",
}

# Status labels from dominant_pillar
STATUS_LABELS = {
    "Geopolitical": "[ESCALATED — GEO-LED]",
    "Cyber": "[ESCALATED — CYBER-LED]",
    "Business": "[ESCALATED — BUSINESS-LED]",
}


def _group_claims_into_bullets(claims: list[dict]) -> dict:
    """Group claim texts into sections.json bullet arrays.

    Reads the `bullets` field on each claim (new format) or falls back
    to deriving from the `paragraph` field (legacy format).
    """
    groups: dict[str, list[str]] = {
        "intel_bullets": [],
        "adversary_bullets": [],
        "impact_bullets": [],
        "watch_bullets": [],
    }
    # Paragraph → bullets mapping for legacy claims without `bullets` field
    paragraph_map = {
        "why": "intel_bullets",
        "how": "adversary_bullets",
        "sowhat": "impact_bullets",
        "watch": "watch_bullets",
    }
    for c in claims:
        text = c.get("text", "")
        if not text:
            continue
        # New format: explicit bullets field
        target = c.get("bullets")
        if not target:
            # Legacy: derive from paragraph
            target = paragraph_map.get(c.get("paragraph", ""), "intel_bullets")
        if target in groups:
            groups[target].append(text)
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


def _build_source_metadata(seerist: dict, osint: dict) -> dict:
    """Build structured source metadata for Overview boxes.

    Reads seerist_signals.json and osint_signals.json directly — not from claims.
    Seerist box: strength level, anomaly hotspot names, pulse delta, verified event count.
    OSINT box: deduplicated source names, count, signal type.
    """
    strength = score_seerist_strength(seerist)
    ana = seerist.get("analytical", {})
    sit = seerist.get("situational", {})

    hotspots_enriched: list[dict] = []
    for h in ana.get("hotspots", []):
        if not h.get("anomaly_flag"):
            continue
        loc = h.get("location", "")
        if isinstance(loc, dict):
            loc = loc.get("name", "")
        label = loc or h.get("signal_id", "?")
        hotspots_enriched.append({
            "label": label,
            "category": h.get("category_hint", ""),
            "deviation_score": round(float(h.get("deviation_score", 0.0)), 1),
            "timestamp": str(h.get("timestamp", "")),
        })
    pulse_delta = ana.get("pulse", {}).get("region_summary", {}).get("avg_delta", 0.0)
    verified_count = len(sit.get("verified_events", []))

    raw_sources = osint.get("sources", [])
    seen_names: set[str] = set()
    unique_sources: list[str] = []
    for s in raw_sources:
        name = s.get("name", "")
        if name and name not in seen_names:
            seen_names.add(name)
            unique_sources.append(name)

    return {
        "seerist": {
            "strength": strength,
            "hotspots": hotspots_enriched,
            "pulse_delta": pulse_delta,
            "verified_event_count": verified_count,
        },
        "osint": {
            "source_count": len(unique_sources),
            "sources": unique_sources,
            "signal_type": osint.get("signal_type", ""),
        },
    }


def _extract_brief_headlines(claims_data: dict) -> dict:
    """Pass through analyst-written summary fields as brief_headlines.

    Reads why_summary, how_summary, so_what_summary from claims.json top level.
    Returns empty strings if any field is absent — never None.
    """
    return {
        "why": claims_data.get("why_summary", ""),
        "how": claims_data.get("how_summary", ""),
        "so_what": claims_data.get("so_what_summary", ""),
    }


def _extract_metadata(claims_data: dict, data: dict | None = None) -> dict:
    """Extract metadata fields — data.json is authoritative (analyst writes it in Step 6).

    Claims.json top-level fields are a fallback for future formats.
    """
    d = data or {}
    return {
        "primary_scenario": d.get("primary_scenario") or claims_data.get("primary_scenario", ""),
        "financial_rank": d.get("financial_rank") or claims_data.get("financial_rank", 0),
        "signal_type": d.get("signal_type") or claims_data.get("signal_type", ""),
        "threat_actor": d.get("threat_actor") or claims_data.get("threat_actor", ""),
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

    # 1. Build signal_clusters.json
    clusters = _group_claims_by_pillar(claims)
    clusters_path = base / "signal_clusters.json"
    clusters_path.write_text(json.dumps(clusters, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[extract_sections] wrote {clusters_path}", file=sys.stderr)

    # 2. Build sections.json — read data.json first for authoritative analyst fields
    data: dict = {}
    if data_path.exists():
        data = json.loads(data_path.read_text(encoding="utf-8"))
    dominant_pillar = data.get("dominant_pillar", "")
    meta = _extract_metadata(claims_data, data)

    grouped = _group_claims_into_bullets(claims)
    grouped["action_bullets"] = _get_action_bullets(meta["primary_scenario"], region)

    signal_type = meta.get("signal_type", "Emerging Pattern")
    grouped["signal_type_label"] = SIGNAL_TYPE_LABELS.get(signal_type, signal_type)
    grouped["status_label"] = STATUS_LABELS.get(dominant_pillar, "[ESCALATED]")

    # Load signal files for source metadata
    seerist: dict = {}
    osint: dict = {}
    seerist_path = base / "seerist_signals.json"
    osint_path = base / "osint_signals.json"
    if seerist_path.exists():
        try:
            seerist = json.loads(seerist_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    if osint_path.exists():
        try:
            osint = json.loads(osint_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    grouped["source_metadata"] = _build_source_metadata(seerist, osint)
    grouped["brief_headlines"] = _extract_brief_headlines(claims_data)

    sections_path = base / "sections.json"
    sections_path.write_text(json.dumps(grouped, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[extract_sections] wrote {sections_path}", file=sys.stderr)

    # 3. Update data.json — backfill only fields not already set by the analyst
    if data_path.exists():
        for field in ("primary_scenario", "financial_rank", "signal_type", "threat_actor"):
            if not data.get(field) and meta.get(field):
                data[field] = meta[field]
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
