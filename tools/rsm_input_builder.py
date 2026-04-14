"""
tools/rsm_input_builder.py

Assembles the RSM agent input manifest with explicit fallbacks.
Code owns the fallback routing. Agent owns the writing.

Usage:
    from tools.rsm_input_builder import build_rsm_inputs, manifest_summary
    manifest = build_rsm_inputs("APAC", cadence="daily")
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

VALID_CADENCES = {"daily", "weekly", "flash"}
NOTABLE_DATE_HORIZON_DAYS = 7


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _filter_sites_to_region(sites_doc, region: str) -> list:
    if not sites_doc:
        return []
    return [s for s in sites_doc.get("sites", []) if s.get("region") == region.upper()]


def _filter_notable_dates(sites: list, horizon_days: int = NOTABLE_DATE_HORIZON_DAYS) -> list:
    today = datetime.now(timezone.utc).date()
    cutoff = today + timedelta(days=horizon_days)
    out = []
    for site in sites:
        for nd in site.get("notable_dates", []) or []:
            try:
                d = datetime.strptime(nd["date"], "%Y-%m-%d").date()
            except (ValueError, KeyError):
                continue
            if today <= d <= cutoff:
                out.append({
                    "site_id": site["site_id"],
                    "site_name": site["name"],
                    "date": nd["date"],
                    "event": nd.get("event", ""),
                    "risk": nd.get("risk", ""),
                })
    return out


def _previous_incidents_per_site(sites: list) -> list:
    out = []
    for site in sites:
        for inc in site.get("previous_incidents", []) or []:
            out.append({
                "site_id": site["site_id"],
                "site_name": site["name"],
                "date": inc.get("date", ""),
                "type": inc.get("type", ""),
                "summary": inc.get("summary", ""),
                "outcome": inc.get("outcome", ""),
            })
    return out


def build_rsm_inputs(region: str, cadence: str = "weekly", output_dir: str = "output") -> dict:
    """Build the input manifest for rsm-formatter-agent.

    Args:
        region: APAC | AME | LATAM | MED | NCE
        cadence: daily | weekly | flash

    Raises:
        ValueError: if cadence is not one of VALID_CADENCES
        FileNotFoundError: if a required input is missing
    """
    if cadence not in VALID_CADENCES:
        raise ValueError(
            f"invalid cadence '{cadence}' — must be one of {VALID_CADENCES}"
        )

    _PROJECT_ROOT = Path(__file__).parent.parent
    region_lower = region.lower()
    base = _PROJECT_ROOT / output_dir / "regional" / region_lower
    data_dir = _PROJECT_ROOT / "data"

    # ── Required inputs ──────────────────────────────────────────────────────
    osint_path = base / "osint_signals.json"
    data_path = base / "data.json"

    required = {
        "osint_signals": str(osint_path) if osint_path.exists() else None,
        "data_json": str(data_path) if data_path.exists() else None,
    }

    missing_required = [k for k, v in required.items() if v is None]
    if missing_required:
        raise FileNotFoundError(
            f"RSM input builder: required files missing for {region}: {missing_required}"
        )

    # ── Optional inputs ─────────────────────────────────────────────────────
    seerist_path = base / "seerist_signals.json"
    delta_path = base / "region_delta.json"
    sites_path = data_dir / "aerowind_sites.json"
    audience_path = data_dir / "audience_config.json"
    osint_physical_path = base / "osint_physical_signals.json"
    poi_proximity_path = base / "poi_proximity.json"

    optional = {
        "seerist_signals": str(seerist_path) if seerist_path.exists() else None,
        "region_delta": str(delta_path) if delta_path.exists() else None,
        "aerowind_sites": str(sites_path) if sites_path.exists() else None,
        "audience_config": str(audience_path) if audience_path.exists() else None,
        "osint_physical_signals": str(osint_physical_path) if osint_physical_path.exists() else None,
        "poi_proximity": str(poi_proximity_path) if poi_proximity_path.exists() else None,
    }

    fallback_flags = {k: v is None for k, v in optional.items()}

    fallback_instructions: dict = {}
    if fallback_flags["seerist_signals"]:
        fallback_instructions["seerist_signals"] = (
            "seerist_signals.json is absent. Use osint_signals.json for "
            "the PHYSICAL & GEOPOLITICAL section."
        )
    if fallback_flags["region_delta"]:
        fallback_instructions["region_delta"] = (
            "region_delta.json is absent. Write 'No comparative data for this period.' "
            "in SITUATION. Write 'No pre-media anomalies detected this period.' in EARLY WARNING."
        )
    if fallback_flags["aerowind_sites"]:
        fallback_instructions["aerowind_sites"] = (
            "aerowind_sites.json is absent. Refer to 'AeroGrid regional operations' generically."
        )
    if fallback_flags["audience_config"]:
        fallback_instructions["audience_config"] = (
            "audience_config.json is absent. Address brief to 'Regional Security Manager' generically."
        )
    if fallback_flags["osint_physical_signals"]:
        fallback_instructions["osint_physical_signals"] = (
            "osint_physical_signals.json is absent. Skip the physical-OSINT layer "
            "and rely on Seerist events for PHYSICAL & GEOPOLITICAL."
        )
    if fallback_flags["poi_proximity"]:
        fallback_instructions["poi_proximity"] = (
            "poi_proximity.json is absent. Write "
            "'No site-specific proximity data this period.' in AEROWIND EXPOSURE."
        )

    # ── Site registry filtered to this region ────────────────────────────────
    sites_doc = _load_json(sites_path)
    region_sites = _filter_sites_to_region(sites_doc, region)
    notable_dates = _filter_notable_dates(region_sites)
    previous_incidents = _previous_incidents_per_site(region_sites)

    # ── poi_proximity inline (if present) ────────────────────────────────────
    poi_proximity = _load_json(poi_proximity_path) if poi_proximity_path.exists() else None

    # ── brief_headlines from sections.json ───────────────────────────────────
    sections_path = base / "sections.json"
    brief_headlines: dict = {}
    sections_doc = _load_json(sections_path)
    if isinstance(sections_doc, dict):
        brief_headlines = sections_doc.get("brief_headlines", {}) or {}

    # ── cross_regional_watch (weekly only) ───────────────────────────────────
    cross_regional_watch: list = []
    if cadence == "weekly":
        gr_path = _PROJECT_ROOT / output_dir / "pipeline" / "global_report.json"
        gr = _load_json(gr_path)
        if isinstance(gr, dict):
            patterns = gr.get("cross_regional_patterns", []) or []
            region_upper = region.upper()
            cross_regional_watch = [
                p for p in patterns
                if isinstance(p, dict)
                and (region_upper in p.get("regions", []) or p.get("scope") == "global")
            ]

    return {
        "region": region.upper(),
        "cadence": cadence,
        "required": required,
        "optional": optional,
        "fallback_flags": fallback_flags,
        "fallback_instructions": fallback_instructions,
        "brief_headlines": brief_headlines,
        "cross_regional_watch": cross_regional_watch,
        "site_registry": region_sites,
        "notable_dates": notable_dates,
        "previous_incidents": previous_incidents,
        "poi_proximity": poi_proximity,
    }


def manifest_summary(manifest: dict) -> str:
    """Return a human-readable summary for prepending to the agent task prompt."""
    lines = [
        f"RSM INPUT MANIFEST — {manifest['region']} — CADENCE: {manifest['cadence'].upper()}"
    ]

    lines.append("\nRequired inputs (all present):")
    for k, v in manifest["required"].items():
        lines.append(f"  {k}: {v}")

    lines.append("\nOptional inputs:")
    for k, v in manifest["optional"].items():
        status = "ABSENT — fallback active" if manifest["fallback_flags"][k] else f"present: {v}"
        lines.append(f"  {k}: {status}")

    if manifest["fallback_instructions"]:
        lines.append("\nFallback instructions for agent:")
        for k, instr in manifest["fallback_instructions"].items():
            lines.append(f"  [{k}] {instr}")

    sites = manifest.get("site_registry", [])
    if sites:
        names = [s["name"] for s in sites]
        lines.append(f"\nAllowed site names ({len(names)}): {', '.join(names)}")
        lines.append(
            "  ANTI-HALLUCINATION: you may NOT name any AeroGrid site outside this list."
        )

    nd = manifest.get("notable_dates", [])
    if nd:
        lines.append("\nNotable dates (next 7 days):")
        for item in nd:
            lines.append(f"  [{item['date']}] {item['site_name']} — {item['event']} ({item['risk']})")

    pi = manifest.get("previous_incidents", [])
    if pi:
        lines.append("\nPrevious incidents (per-site history):")
        for item in pi:
            lines.append(f"  [{item['date']}] {item['site_name']} — {item['summary']} → {item['outcome']}")

    poi = manifest.get("poi_proximity")
    if poi:
        n_within = sum(len(s["events_within_radius"]) for s in poi.get("events_by_site_proximity", []))
        n_cascades = len(poi.get("cascading_impact_warnings", []))
        lines.append(
            f"\nPOI proximity: {n_within} event(s) within site radii, "
            f"{n_cascades} cascade(s)"
        )

    bh = manifest.get("brief_headlines", {})
    if any(bh.values()):
        lines.append("\nBrief headlines:")
        for k, v in bh.items():
            if v:
                lines.append(f"  {k}: {v}")

    cw = manifest.get("cross_regional_watch", [])
    if cw:
        lines.append(f"\nCross-regional watch: {len(cw)} pattern(s)")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    region = sys.argv[1] if len(sys.argv) > 1 else "APAC"
    cadence = sys.argv[2] if len(sys.argv) > 2 else "weekly"
    manifest = build_rsm_inputs(region, cadence=cadence)
    print(manifest_summary(manifest))
