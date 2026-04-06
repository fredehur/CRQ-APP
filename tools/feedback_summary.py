"""Aggregate analyst feedback across all archived runs into feedback_trends.json.

Usage:
    uv run python tools/feedback_summary.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.config import FEEDBACK_TRENDS_PATH

REPO_ROOT = Path(__file__).parent.parent

VALID_RATINGS = ("accurate", "overstated", "understated", "false_positive")


def _empty_summary() -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_runs_with_feedback": 0,
        "total_ratings": 0,
        "by_region": {},
        "by_rating": {r: 0 for r in VALID_RATINGS},
        "recent_notes": [],
    }


def _collect_feedback() -> tuple[list[tuple[str, list[dict]]], int]:
    """Return (list of (run_id, entries) pairs, total_runs_with_feedback)."""
    runs_dir = REPO_ROOT / "output" / "runs"
    if not runs_dir.exists():
        return [], 0

    results = []
    for folder in sorted(runs_dir.iterdir()):
        if not folder.is_dir():
            continue
        fb_path = folder / "feedback.json"
        if not fb_path.exists():
            continue
        try:
            entries = json.loads(fb_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(entries, list) or not entries:
            continue

        # Resolve run_id from manifest
        run_id = folder.name
        manifest_path = folder / "run_manifest.json"
        if manifest_path.exists():
            try:
                m = json.loads(manifest_path.read_text(encoding="utf-8"))
                run_id = m.get("pipeline_id", folder.name)
            except (json.JSONDecodeError, OSError):
                pass

        results.append((run_id, entries))

    return results, len(results)


def build_summary() -> dict:
    """Build the feedback_trends.json data structure."""
    all_feedback, total_runs = _collect_feedback()

    if total_runs == 0:
        return _empty_summary()

    summary = _empty_summary()
    summary["total_runs_with_feedback"] = total_runs

    # Collect all entries with their run_id for recent_notes
    all_entries_with_run: list[tuple[str, dict]] = []

    for run_id, entries in all_feedback:
        for entry in entries:
            region = entry.get("region", "unknown")
            rating = entry.get("rating", "unknown")

            summary["total_ratings"] += 1

            # by_rating
            if rating in summary["by_rating"]:
                summary["by_rating"][rating] += 1

            # by_region
            if region not in summary["by_region"]:
                summary["by_region"][region] = {r: 0 for r in VALID_RATINGS}
                summary["by_region"][region]["total"] = 0
                summary["by_region"][region]["accuracy_rate"] = None

            if rating in summary["by_region"][region]:
                summary["by_region"][region][rating] += 1
            summary["by_region"][region]["total"] += 1

            total = summary["by_region"][region]["total"]
            accurate = summary["by_region"][region]["accurate"]
            summary["by_region"][region]["accuracy_rate"] = accurate / total if total > 0 else None

            all_entries_with_run.append((run_id, entry))

    # recent_notes: entries with non-empty note, newest first, max 10
    noted = [
        (run_id, e) for run_id, e in all_entries_with_run
        if e.get("note")
    ]
    noted.sort(key=lambda x: x[1].get("submitted_at", ""), reverse=True)

    summary["recent_notes"] = [
        {
            "run_id": run_id,
            "region": e.get("region", ""),
            "rating": e.get("rating", ""),
            "note": e.get("note", ""),
            "analyst": e.get("analyst", ""),
            "submitted_at": e.get("submitted_at", ""),
        }
        for run_id, e in noted[:10]
    ]

    return summary


def main() -> None:
    summary = build_summary()

    out_path = REPO_ROOT / FEEDBACK_TRENDS_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tmp = out_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, out_path)

    if summary["total_runs_with_feedback"] == 0:
        print("No feedback found — empty summary written")
    else:
        print(f"Feedback summary written to {FEEDBACK_TRENDS_PATH}")


if __name__ == "__main__":
    main()
