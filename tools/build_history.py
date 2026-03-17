#!/usr/bin/env python3
"""Build output/history.json from archived run manifests.

Usage:
    uv run python tools/build_history.py

Reads:  output/runs/*/run_manifest.json
Writes: output/history.json
"""

import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
RUNS_DIR = REPO_ROOT / "output" / "runs"
HISTORY_FILE = REPO_ROOT / "output" / "history.json"

KNOWN_REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]


def build_history() -> None:
    # Glob all run manifests and sort by folder name (folder names are chronological timestamps)
    manifest_paths = sorted(RUNS_DIR.glob("*/run_manifest.json"), key=lambda p: p.parent.name)

    regions: dict[str, list] = {r: [] for r in KNOWN_REGIONS}
    run_count = 0

    for manifest_path in manifest_paths:
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        pipeline_id = data.get("pipeline_id", "")
        run_timestamp = data.get("run_timestamp", "")
        raw_regions = data.get("regions", {})

        run_count += 1

        for region, region_data in raw_regions.items():
            if region not in regions:
                regions[region] = []

            entry = {
                "timestamp": run_timestamp,
                "pipeline_id": pipeline_id,
                "severity": region_data.get("severity", ""),
                "vacr_usd": region_data.get("vacr_usd", 0),
                "status": region_data.get("status", ""),
                "admiralty": region_data.get("admiralty", ""),
                "velocity": region_data.get("velocity", ""),
                "dominant_pillar": region_data.get("dominant_pillar", ""),
            }
            regions[region].append(entry)

    # Entries within each region are already chronological (manifests were sorted by folder name),
    # but sort by timestamp string as a safety net.
    for region in regions:
        regions[region].sort(key=lambda e: e["timestamp"])

    history = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_count": run_count,
        "regions": regions,
    }

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")

    region_count = len([r for r in regions.values() if r])
    print(f"History written to output/history.json ({run_count} runs, {region_count} regions)")


if __name__ == "__main__":
    build_history()
