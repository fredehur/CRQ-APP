#!/usr/bin/env python3
"""Build output/history.json from archived run manifests + per-region data.json files.

Usage:
    uv run python tools/build_history.py

Reads:  output/runs/{folder}/run_manifest.json
        output/runs/{folder}/regional/{region}/data.json  (optional — enriches entries)
Writes: output/history.json  (atomic)
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
RUNS_DIR = REPO_ROOT / "output" / "runs"
HISTORY_FILE = REPO_ROOT / "output" / "history.json"

KNOWN_REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]

_SEV_SCORE = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}


def _severity_score(severity: str) -> int:
    return _SEV_SCORE.get((severity or "").upper(), 0)


def _read_json_safe(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _compute_drift(regions: dict) -> dict:
    """For each region, count consecutive runs (newest first) with same primary_scenario."""
    drift = {}
    for region, entries in regions.items():
        if not entries:
            continue
        rev = list(reversed(entries))
        current = rev[0].get("primary_scenario")
        if not current:
            continue
        count = 1
        for entry in rev[1:]:
            if entry.get("primary_scenario") == current:
                count += 1
            else:
                break
        if count >= 2:
            drift[region] = {
                "current_scenario": current,
                "consecutive_runs": count,
                "note": f"{region}: {current} for {count} consecutive runs",
            }
    return drift


def build_history() -> None:
    manifest_paths = sorted(
        RUNS_DIR.glob("*/run_manifest.json"),
        key=lambda p: p.parent.name,
    )

    regions: dict = {r: [] for r in KNOWN_REGIONS}

    for manifest_path in manifest_paths:
        manifest = _read_json_safe(manifest_path)
        if manifest is None:
            continue

        folder = manifest_path.parent.name
        run_id = manifest.get("pipeline_id", folder)
        run_timestamp = manifest.get("run_timestamp", "")
        raw_regions = manifest.get("regions", {})

        for region in KNOWN_REGIONS:
            # Try to enrich from data.json first
            data_json_path = manifest_path.parent / "regional" / region.lower() / "data.json"
            djson = _read_json_safe(data_json_path) or {}

            # Fallback to manifest regions entry
            mregion = raw_regions.get(region, {})

            severity = djson.get("severity") or mregion.get("severity") or ""
            vacr_usd = djson.get("vacr_exposure_usd") or mregion.get("vacr_usd") or 0
            status = djson.get("status") or mregion.get("status") or "clear"
            timestamp = djson.get("timestamp") or run_timestamp

            entry = {
                "run_id": run_id,
                "run_folder": folder,
                "timestamp": timestamp,
                "status": status,
                "severity": severity,
                "severity_score": _severity_score(severity),
                "vacr_usd": vacr_usd,
                "primary_scenario": djson.get("primary_scenario") or None,
                "velocity": djson.get("velocity") or None,
                "dominant_pillar": djson.get("dominant_pillar") or None,
                "signal_type": djson.get("signal_type") or None,
                "financial_rank": djson.get("financial_rank") or None,
            }
            regions[region].append(entry)

    # Sort each region oldest→newest
    for region in regions:
        regions[region].sort(key=lambda e: e["timestamp"])

    drift = _compute_drift(regions)

    history = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regions": regions,
        "drift": drift,
    }

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = HISTORY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, HISTORY_FILE)

    n_runs = max((len(v) for v in regions.values()), default=0)
    n_regions = len([r for r in regions.values() if r])
    print(f"History written: {n_runs} runs, {n_regions} regions")


if __name__ == "__main__":
    build_history()
