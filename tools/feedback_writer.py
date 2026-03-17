"""CLI tool to write/append analyst feedback for a pipeline run.

Usage:
    uv run python tools/feedback_writer.py <run_id> <region> <rating> [--note "text"] [--analyst "name"]
    uv run python tools/feedback_writer.py --summarize
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

VALID_RATINGS = {"accurate", "overstated", "understated", "false_positive"}
VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE", "global"}


def _find_run_folder(run_id: str) -> Path | None:
    """Return the run folder whose run_manifest.json has matching pipeline_id."""
    runs_dir = REPO_ROOT / "output" / "runs"
    if not runs_dir.exists():
        return None
    for folder in sorted(runs_dir.iterdir()):
        if not folder.is_dir():
            continue
        manifest_path = folder / "run_manifest.json"
        if manifest_path.exists():
            try:
                m = json.loads(manifest_path.read_text(encoding="utf-8"))
                if m.get("pipeline_id") == run_id:
                    return folder
            except (json.JSONDecodeError, OSError):
                continue
    return None


def _write_feedback(run_id: str, region: str, rating: str, note: str, analyst: str) -> None:
    """Append one feedback entry to the run's feedback.json."""
    if region not in VALID_REGIONS:
        print(f"ERROR: Invalid region '{region}'. Must be one of: {', '.join(sorted(VALID_REGIONS))}", file=sys.stderr)
        sys.exit(1)
    if rating not in VALID_RATINGS:
        print(f"ERROR: Invalid rating '{rating}'. Must be one of: {', '.join(sorted(VALID_RATINGS))}", file=sys.stderr)
        sys.exit(1)

    folder = _find_run_folder(run_id)
    if folder is None:
        print(f"ERROR: Run not found: {run_id}", file=sys.stderr)
        sys.exit(1)

    entry = {
        "region": region,
        "rating": rating,
        "note": note,
        "analyst": analyst,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    fb_path = folder / "feedback.json"
    existing = json.loads(fb_path.read_text(encoding="utf-8")) if fb_path.exists() else []
    existing.append(entry)

    import os
    tmp = fb_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, fb_path)

    print(f"Feedback recorded for {region} [{rating}] in run {run_id}")


def _summarize() -> None:
    """Print a compact summary of feedback from the most recent run. Prints nothing if no feedback."""
    runs_dir = REPO_ROOT / "output" / "runs"
    if not runs_dir.exists():
        sys.exit(0)

    folders = sorted(f for f in runs_dir.iterdir() if f.is_dir())
    if not folders:
        sys.exit(0)

    # Most recent = last alphabetically (timestamp-named folders sort chronologically)
    for folder in reversed(folders):
        fb_path = folder / "feedback.json"
        if not fb_path.exists():
            continue
        try:
            entries = json.loads(fb_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not entries:
            continue

        # Get run_id from manifest
        run_id = folder.name
        manifest_path = folder / "run_manifest.json"
        if manifest_path.exists():
            try:
                m = json.loads(manifest_path.read_text(encoding="utf-8"))
                run_id = m.get("pipeline_id", folder.name)
            except (json.JSONDecodeError, OSError):
                pass

        parts = []
        for e in entries:
            region = e.get("region", "?")
            rating = e.get("rating", "?")
            note = e.get("note", "")
            if note:
                parts.append(f'{region}={rating} ("{note}")')
            else:
                parts.append(f"{region}={rating}")

        print(f"Prior run feedback ({run_id}): {', '.join(parts)}")
        sys.exit(0)

    # No feedback found in any run
    sys.exit(0)


def main() -> None:
    # Handle --summarize before building the full argparse tree
    if "--summarize" in sys.argv:
        _summarize()
        return

    parser = argparse.ArgumentParser(
        description="Write analyst feedback for a pipeline run.",
        usage="%(prog)s <run_id> <region> <rating> [--note TEXT] [--analyst NAME]",
    )
    parser.add_argument("run_id", help="Pipeline run ID (e.g. crq-2026-03-16T171249Z)")
    parser.add_argument("region", help=f"Region: {', '.join(sorted(VALID_REGIONS))}")
    parser.add_argument("rating", help=f"Rating: {', '.join(sorted(VALID_RATINGS))}")
    parser.add_argument("--note", default="", help="Optional free-text note")
    parser.add_argument("--analyst", default="anonymous", help="Analyst name (default: anonymous)")

    args = parser.parse_args()
    _write_feedback(args.run_id, args.region, args.rating, args.note, args.analyst)


if __name__ == "__main__":
    main()
