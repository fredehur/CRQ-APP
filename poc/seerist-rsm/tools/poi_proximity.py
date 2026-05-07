"""tools/poi_proximity.py — pure code: event→site proximity + dependency cascade.

Two public functions:
    compute_proximity(region) -> {region, computed_at, events_by_site_proximity[]}
    compute_cascade(region)   -> {region, computed_at, cascading_impact_warnings[]}

Writes (when called as CLI): output/regional/{region}/poi_proximity.json (combined dict).

No LLM. Pure haversine + dict traversal. Fully unit-testable.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITES_PATH = REPO_ROOT / "data" / "aerowind_sites.json"
FIXTURES_DIR = REPO_ROOT / "data" / "mock_osint_fixtures"
OUTPUT_ROOT = REPO_ROOT / "output"

# Events farther than the radius but still in this band are surfaced as
# "outside radius but relevant" — gives the RSM regional context without spam.
EVENTS_OUTSIDE_RELEVANCE_KM = 500
CASCADE_MAX_DEPTH = 2

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}


# ── geometry ─────────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ── data loaders ─────────────────────────────────────────────────────────────

def _load_sites() -> list[dict]:
    return json.loads(SITES_PATH.read_text(encoding="utf-8"))["sites"]


def _load_seerist(region: str, fixtures_only: bool = False) -> dict:
    """Read seerist signals: prefer pipeline output, fall back to fixture if absent or fixtures_only."""
    if not fixtures_only:
        live = OUTPUT_ROOT / "regional" / region.lower() / "seerist_signals.json"
        if live.exists():
            return json.loads(live.read_text(encoding="utf-8"))
    fixture = FIXTURES_DIR / f"{region.lower()}_seerist.json"
    if fixture.exists():
        return json.loads(fixture.read_text(encoding="utf-8"))
    return {"situational": {"events": [], "verified_events": [], "breaking_news": []},
            "analytical": {"hotspots": []}, "poi_alerts": []}


def _load_osint_physical(region: str, fixtures_only: bool = False) -> dict:
    if not fixtures_only:
        live = OUTPUT_ROOT / "regional" / region.lower() / "osint_physical_signals.json"
        if live.exists():
            return json.loads(live.read_text(encoding="utf-8"))
    return {"signals": []}


# ── proximity ────────────────────────────────────────────────────────────────

def _all_events_with_coords(seerist: dict, osint_physical: dict) -> list[dict]:
    """Flatten every coordinate-bearing event from all sources into one list."""
    out: list[dict] = []
    sit = seerist.get("situational", {})
    verified_ids = {v.get("linked_event_id") for v in sit.get("verified_events", [])}

    for ev in sit.get("events", []):
        loc = ev.get("location") or {}
        if "lat" not in loc or "lon" not in loc:
            continue
        out.append({
            "signal_id": ev["signal_id"],
            "title": ev.get("title", ""),
            "category": ev.get("category", ""),
            "severity": ev.get("severity", 0),
            "lat": loc["lat"],
            "lon": loc["lon"],
            "source_count": ev.get("source_count", 0),
            "verified": ev.get("verified", False) or ev["signal_id"] in verified_ids,
            "source": "seerist:event",
        })

    for bn in sit.get("breaking_news", []):
        loc = bn.get("location") or {}
        if "lat" not in loc or "lon" not in loc:
            continue
        out.append({
            "signal_id": bn["signal_id"],
            "title": bn.get("title", ""),
            "category": "Breaking",
            "severity": 0,
            "lat": loc["lat"],
            "lon": loc["lon"],
            "source_count": bn.get("source_count", 0),
            "verified": False,
            "source": "seerist:breaking",
        })

    for hs in seerist.get("analytical", {}).get("hotspots", []):
        loc = hs.get("location") or {}
        if "lat" not in loc or "lon" not in loc:
            continue
        out.append({
            "signal_id": hs["signal_id"],
            "title": hs.get("category_hint", "anomaly"),
            "category": "Hotspot",
            "severity": int(hs.get("deviation_score", 0) * 5),
            "lat": loc["lat"],
            "lon": loc["lon"],
            "source_count": 0,
            "verified": False,
            "source": "seerist:hotspot",
        })

    for sig in osint_physical.get("signals", []):
        loc = sig.get("location") or {}
        if "lat" not in loc or "lon" not in loc:
            continue
        out.append({
            "signal_id": sig["signal_id"],
            "title": sig.get("title", ""),
            "category": sig.get("category", ""),
            "severity": sig.get("severity", 0),
            "lat": loc["lat"],
            "lon": loc["lon"],
            "source_count": sig.get("source_count", 0),
            "verified": False,
            "source": "osint:physical",
        })

    return out


def compute_proximity(region: str, fixtures_only: bool = False) -> dict:
    region = region.upper()
    if region not in VALID_REGIONS:
        raise ValueError(f"invalid region: {region}")

    sites = [s for s in _load_sites() if s["region"] == region]
    seerist = _load_seerist(region, fixtures_only=fixtures_only)
    osint_physical = _load_osint_physical(region, fixtures_only=fixtures_only)
    events = _all_events_with_coords(seerist, osint_physical)

    by_site = []
    for site in sites:
        if "lat" not in site or "lon" not in site:
            continue
        within = []
        outside = []
        for ev in events:
            d = round(haversine_km(site["lat"], site["lon"], ev["lat"], ev["lon"]), 1)
            row = {
                "signal_id": ev["signal_id"],
                "title": ev["title"],
                "category": ev["category"],
                "severity": ev["severity"],
                "distance_km": d,
                "source_count": ev["source_count"],
                "verified": ev["verified"],
                "source": ev["source"],
            }
            if d <= site["poi_radius_km"]:
                within.append(row)
            elif d <= EVENTS_OUTSIDE_RELEVANCE_KM:
                outside.append(row)

        within.sort(key=lambda r: r["distance_km"])
        outside.sort(key=lambda r: r["distance_km"])

        by_site.append({
            "site_id": site["site_id"],
            "site": site["name"],
            "region": site["region"],
            "personnel": site.get("personnel_count", 0),
            "expat": site.get("expat_count", 0),
            "criticality": site.get("criticality", "standard"),
            "radius_km": site["poi_radius_km"],
            "events_within_radius": within,
            "events_outside_radius_but_relevant": outside,
        })

    by_site.sort(key=lambda s: (
        {"crown_jewel": 0, "major": 1, "standard": 2}.get(s["criticality"], 3),
        -len(s["events_within_radius"]),
    ))

    return {
        "region": region,
        "computed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "events_by_site_proximity": by_site,
    }


# ── cascade ──────────────────────────────────────────────────────────────────

def _build_dependency_graph(sites: list[dict]) -> dict[str, dict]:
    """site_id → {region, feeds_into:[site_id...]}"""
    return {
        s["site_id"]: {
            "region": s.get("region", ""),
            "feeds_into": list(s.get("feeds_into") or []),
        }
        for s in sites
    }


def _walk_downstream(start: str, graph: dict, max_depth: int = CASCADE_MAX_DEPTH) -> set[str]:
    """BFS downstream from `start`, capped at max_depth, cycle-safe.
    Returns the set of visited site_ids INCLUDING `start`."""
    visited = {start}
    frontier = [(start, 0)]
    while frontier:
        node, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        for child in graph.get(node, {}).get("feeds_into", []):
            if child not in visited:
                visited.add(child)
                frontier.append((child, depth + 1))
    return visited


def compute_cascade(region: str, fixtures_only: bool = False) -> dict:
    region = region.upper()
    if region not in VALID_REGIONS:
        raise ValueError(f"invalid region: {region}")

    all_sites = _load_sites()
    graph = _build_dependency_graph(all_sites)
    sites_by_id = {s["site_id"]: s for s in all_sites}

    proximity = compute_proximity(region, fixtures_only=fixtures_only)

    warnings = []
    for site_block in proximity["events_by_site_proximity"]:
        if not site_block["events_within_radius"]:
            continue
        trigger_id = site_block["site_id"]
        downstream = _walk_downstream(trigger_id, graph) - {trigger_id}
        if not downstream:
            continue
        for ev in site_block["events_within_radius"]:
            for ds_id in downstream:
                ds_site = sites_by_id.get(ds_id, {})
                warnings.append({
                    "trigger_site_id": trigger_id,
                    "trigger_signal_id": ev["signal_id"],
                    "downstream_site_ids": [ds_id],
                    "downstream_region": ds_site.get("region", ""),
                    "dependency": ds_site.get("produces", ""),
                    "estimated_delay_days": None,
                })
            break  # one cascade per trigger site; first event is highest-priority by sort

    return {
        "region": region,
        "computed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cascading_impact_warnings": warnings,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def write_proximity_file(region: str, fixtures_only: bool = False) -> Path:
    proximity = compute_proximity(region, fixtures_only=fixtures_only)
    cascade = compute_cascade(region, fixtures_only=fixtures_only)
    combined = {
        "region": proximity["region"],
        "computed_at": proximity["computed_at"],
        "events_by_site_proximity": proximity["events_by_site_proximity"],
        "cascading_impact_warnings": cascade["cascading_impact_warnings"],
    }
    out_dir = OUTPUT_ROOT / "regional" / region.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "poi_proximity.json"
    out_path.write_text(json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: poi_proximity.py REGION [--mock]", file=sys.stderr)
        sys.exit(1)
    region = args[0].upper()
    fixtures_only = "--mock" in args
    path = write_proximity_file(region, fixtures_only=fixtures_only)
    print(f"[poi_proximity] wrote {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
