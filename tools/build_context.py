"""tools/build_context.py — Phase M: Regional Footprint Context Builder

CLI:
    uv run python tools/build_context.py APAC
    uv run python tools/build_context.py --gatekeeper-summary
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── Constants (monkeypatched in tests) ─────────────────────────────────────
FOOTPRINT_FILE = Path("data/regional_footprint.json")
OUTPUT_DIR = Path("output")
KNOWN_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}


# ── Public API ──────────────────────────────────────────────────────────────

def build_gatekeeper_summary(region_data: dict, region: str) -> str:
    """Return a single-line footprint summary for gatekeeper context injection."""
    headcount = f"{region_data.get('headcount', 0):,}"
    sites = region_data.get("sites", [])
    site_strs = [
        f"{s['name'].split()[0]} ({s['type']}, {s['criticality'].upper()})"
        for s in sites
    ]
    sites_part = ", ".join(site_strs) if site_strs else "no sites listed"
    return f"{region} footprint: {headcount} staff | Sites: {sites_part}"


def build_context(region: str) -> None:
    """Read regional_footprint.json, write context_block.txt for agent injection.

    Exit codes:
        0 — success (including region absent from file — writes empty block)
        1 — bad region name or missing footprint file
    """
    if region not in KNOWN_REGIONS:
        print(f"ERROR: Unknown region '{region}'. Must be one of {sorted(KNOWN_REGIONS)}", file=sys.stderr)
        sys.exit(1)

    if not FOOTPRINT_FILE.exists():
        print(f"ERROR: Footprint file not found: {FOOTPRINT_FILE}", file=sys.stderr)
        sys.exit(1)

    footprint = json.loads(FOOTPRINT_FILE.read_text(encoding="utf-8"))

    out_dir = OUTPUT_DIR / "regional" / region.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "context_block.txt"

    if region not in footprint:
        print(f"WARNING: Region '{region}' not found in {FOOTPRINT_FILE} — writing empty context block.", file=sys.stderr)
        out_path.write_text("", encoding="utf-8")
        print(f"Context block written (empty): {out_path}")
        return

    data = footprint[region]
    block = _format_context_block(data, region)
    out_path.write_text(block, encoding="utf-8")
    print(f"Context block written: {out_path}")


def build_all_gatekeeper_summaries() -> None:
    """Print one gatekeeper summary line per region (all 5). Captured by orchestrator."""
    if not FOOTPRINT_FILE.exists():
        print(f"ERROR: Footprint file not found: {FOOTPRINT_FILE}", file=sys.stderr)
        sys.exit(1)

    footprint = json.loads(FOOTPRINT_FILE.read_text(encoding="utf-8"))
    for region in sorted(KNOWN_REGIONS):
        if region in footprint:
            print(build_gatekeeper_summary(footprint[region], region))
        else:
            print(f"{region} footprint: no data")


# ── Private formatting ──────────────────────────────────────────────────────

def _format_context_block(data: dict, region: str) -> str:
    lines = [f"[REGIONAL FOOTPRINT — {region}]"]
    lines.append(f"Summary: {data.get('summary', '')}")
    lines.append(f"Headcount: {data.get('headcount', 0):,}")
    lines.append("")

    sites = data.get("sites", [])
    if sites:
        lines.append("Sites:")
        for s in sites:
            lines.append(f"  - {s['name']} ({s['country']}) — {s['type']}, {s['criticality'].upper()}")
    lines.append("")

    crown = data.get("crown_jewels", [])
    if crown:
        lines.append(f"Crown Jewels: {' | '.join(crown)}")

    deps = data.get("supply_chain_dependencies", [])
    if deps:
        lines.append(f"Supply Chain Dependencies: {' | '.join(deps)}")

    contracts = data.get("key_contracts", [])
    if contracts:
        lines.append(f"Key Contracts: {' | '.join(contracts)}")

    notes = data.get("notes", "").strip()
    if notes:
        lines.append("")
        lines.append("Notes:")
        lines.append(notes)

    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Build regional footprint context blocks")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("region", nargs="?", help="Region code (APAC, AME, LATAM, MED, NCE)")
    group.add_argument("--gatekeeper-summary", action="store_true",
                       help="Print one-line summary per region for gatekeeper injection")
    args = parser.parse_args()

    if args.gatekeeper_summary:
        build_all_gatekeeper_summaries()
    else:
        build_context(args.region.upper())


if __name__ == "__main__":
    main()
