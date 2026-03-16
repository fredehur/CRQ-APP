"""Assembles output/run_manifest.json from all regional data.json files."""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from config import REGIONS


def build_manifest(window_used=None):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_slug = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")

    regions_summary = {}
    total_vacr = 0

    for region in REGIONS:
        data_path = f"output/regional/{region.lower()}/data.json"
        if os.path.exists(data_path):
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)
            vacr = data.get("vacr_exposure_usd", 0)
            total_vacr += vacr
            regions_summary[region] = {
                "status": data.get("status", "unknown"),
                "severity": data.get("severity", "LOW"),
                "vacr_usd": vacr,
                "admiralty": data.get("admiralty", None),
                "velocity": data.get("velocity", "unknown"),
                "dominant_pillar": data.get("dominant_pillar", None),
            }
        else:
            regions_summary[region] = {
                "status": "missing",
                "severity": "UNKNOWN",
                "vacr_usd": 0,
                "admiralty": None,
                "velocity": "unknown",
                "dominant_pillar": None,
            }

    manifest = {
        "pipeline_id": f"crq-{date_slug}",
        "client": "AeroGrid Wind Solutions",
        "run_timestamp": timestamp,
        "status": "complete",
        "window_used": window_used or "unspecified",
        "total_vacr_exposure_usd": total_vacr,
        "regions": regions_summary,
        "outputs": {
            "global_report_json": "global_report.json",
            "global_report_md": "global_report.md",
            "dashboard_html": "dashboard.html",
            "board_report_pdf": "board_report.pdf",
            "board_report_pptx": "board_report.pptx",
            "system_trace": "system_trace.log",
            "trend_brief": "trend_brief.json",
        },
    }

    out_path = "output/run_manifest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Wrote {out_path} — {len(REGIONS)} regions, total VaCR: ${total_vacr:,.0f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Assemble run_manifest.json")
    parser.add_argument("--window", choices=["1d", "7d", "30d", "90d"], default=None,
                        help="Date window used for OSINT collection")
    args = parser.parse_args()
    build_manifest(window_used=args.window)
