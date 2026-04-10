#!/usr/bin/env python3
"""Threshold evaluator — determines which audiences get which products.

Usage:
    threshold_evaluator.py [--force-weekly] [--check-flash]

Reads:  output/regional/{region}/seerist_signals.json
        output/regional/{region}/region_delta.json
        data/audience_config.json
        data/aerowind_sites.json
Writes: output/routing_decisions.json
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")
from tools.config import ROUTING_PATH as _ROUTING_PATH

OUTPUT_ROOT = Path("output")
AUDIENCE_CONFIG_PATH = Path("data/audience_config.json")
SITES_PATH = Path("data/aerowind_sites.json")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _nearest_site_km(lat: float, lon: float, sites: list, region: str) -> float:
    """Minimum distance from (lat, lon) to any AeroGrid site in the region."""
    region_sites = [s for s in sites if s["region"] == region]
    if not region_sites:
        return float("inf")
    return min(_haversine_km(lat, lon, s["lat"], s["lon"]) for s in region_sites)


def _brief_path(audience_key: str, region: str, product: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    region_lower = region.lower()
    if product == "weekly_intsum":
        return f"output/regional/{region_lower}/rsm_brief_{region_lower}_{today}.md"
    else:
        return f"output/regional/{region_lower}/rsm_flash_{region_lower}_{ts}.md"


def evaluate(force_weekly: bool = False, check_flash: bool = True) -> dict:
    config = json.loads(AUDIENCE_CONFIG_PATH.read_text(encoding="utf-8"))
    sites = json.loads(SITES_PATH.read_text(encoding="utf-8"))["sites"]

    decisions = []

    for audience_key, audience in config.items():
        formatter = audience.get("formatter_agent", "rsm-formatter-agent")
        for region in audience.get("regions", []):
            region_lower = region.lower()
            seerist_path = OUTPUT_ROOT / "regional" / region_lower / "seerist_signals.json"
            delta_path = OUTPUT_ROOT / "regional" / region_lower / "region_delta.json"

            seerist = json.loads(seerist_path.read_text(encoding="utf-8")) if seerist_path.exists() else {}
            delta = json.loads(delta_path.read_text(encoding="utf-8")) if delta_path.exists() else {}

            products = audience.get("products", {})

            # Weekly INTSUM — always triggered when force_weekly=True or cadence=monday
            if "weekly_intsum" in products and force_weekly:
                decisions.append({
                    "audience": audience_key,
                    "region": region,
                    "product": "weekly_intsum",
                    "triggered": True,
                    "trigger_reason": "weekly cadence",
                    "formatter_agent": formatter,
                    "brief_path": _brief_path(audience_key, region, "weekly_intsum"),
                    "delivered": False,
                })

            # Flash — threshold evaluation
            if "flash" in products and check_flash:
                flash_cfg = products["flash"]["threshold"]
                score_min = flash_cfg.get("hotspot_score_min", 0.85)
                proximity_km = flash_cfg.get("site_proximity_km", 100)
                severity_min = flash_cfg.get("event_severity_min", 4)
                trigger_cats = set(flash_cfg.get("categories", ["Conflict", "Terrorism", "Unrest"]))

                triggered = False
                trigger_reason = ""

                # Check new hotspots
                for hotspot in delta.get("hotspots_new", []):
                    score = hotspot.get("deviation_score", 0)
                    if score >= score_min:
                        lat = hotspot.get("lat") or hotspot.get("location", {}).get("lat")
                        lon = hotspot.get("lon") or hotspot.get("location", {}).get("lon")
                        if lat is not None and lon is not None:
                            dist = _nearest_site_km(lat, lon, sites, region)
                            if dist <= proximity_km:
                                triggered = True
                                trigger_reason = f"HotspotsAI score {score} >= {score_min}, {hotspot.get('location', {}).get('name', 'unknown')}, {dist:.0f}km from nearest site"
                                break

                # Check new high-severity events in trigger categories
                if not triggered:
                    for event in delta.get("events_new", []):
                        if event.get("severity", 0) >= severity_min and event.get("category") in trigger_cats:
                            loc = event.get("location", {})
                            lat = loc.get("lat")
                            lon = loc.get("lon")
                            if lat is not None and lon is not None:
                                dist = _nearest_site_km(lat, lon, sites, region)
                                if dist <= proximity_km:
                                    triggered = True
                                    trigger_reason = f"EventsAI {event.get('category')} severity {event.get('severity')}, {loc.get('name', 'unknown')}"
                                    break
                            else:
                                # No coords — trigger on category + severity alone
                                triggered = True
                                trigger_reason = f"EventsAI {event.get('category')} severity {event.get('severity')}, {loc.get('name', 'unknown')} (no coords)"
                                break

                # Check osint_signals.json for direct AeroGrid targeting
                if not triggered:
                    cyber_path = OUTPUT_ROOT / "regional" / region_lower / "osint_signals.json"
                    if cyber_path.exists():
                        try:
                            cyber = json.loads(cyber_path.read_text(encoding="utf-8"))
                            if cyber.get("aerowind_targeted") is True:
                                triggered = True
                                trigger_reason = "cyber signal: direct AeroGrid targeting confirmed"
                        except (json.JSONDecodeError, OSError):
                            pass

                if triggered:
                    decisions.append({
                        "audience": audience_key,
                        "region": region,
                        "product": "flash",
                        "triggered": True,
                        "trigger_reason": trigger_reason,
                        "formatter_agent": formatter,
                        "brief_path": _brief_path(audience_key, region, "flash"),
                        "delivered": False,
                    })

    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "decisions": decisions,
    }
    out_path = _ROUTING_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[threshold_evaluator] wrote {out_path} — {len(decisions)} decisions", file=sys.stderr)
    return output


def main():
    args = sys.argv[1:]
    force_weekly = "--force-weekly" in args or "--weekly" in args
    check_flash = "--check-flash" in args or "--force-weekly" not in args
    evaluate(force_weekly=force_weekly, check_flash=check_flash)


if __name__ == "__main__":
    main()
