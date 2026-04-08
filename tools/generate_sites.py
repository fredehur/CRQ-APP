"""
generate_sites.py — derive data/aerowind_sites.json from data/regional_footprint.json.

Single source of truth: regional_footprint.json owns all site data (including lat/lon).
This script is a deterministic derivation step — run it before threshold_evaluator.py.

Usage:
    uv run python tools/generate_sites.py
"""
import json
from pathlib import Path

FOOTPRINT_PATH = Path("data/regional_footprint.json")
OUTPUT_PATH    = Path("data/aerowind_sites.json")


def generate() -> None:
    footprint = json.loads(FOOTPRINT_PATH.read_text(encoding="utf-8"))

    sites = []
    for region, data in footprint.items():
        for site in data.get("sites", []):
            lat = site.get("lat")
            lon = site.get("lon")
            if lat is None or lon is None:
                print(f"WARNING: {site['name']} ({region}) missing lat/lon — skipped")
                continue
            sites.append({
                "name":    site["name"],
                "region":  region,
                "country": site.get("country", ""),
                "lat":     lat,
                "lon":     lon,
                "type":    site.get("type", ""),
            })

    OUTPUT_PATH.write_text(
        json.dumps({"sites": sites}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Generated {OUTPUT_PATH} — {len(sites)} sites from {len(footprint)} regions")


if __name__ == "__main__":
    generate()
