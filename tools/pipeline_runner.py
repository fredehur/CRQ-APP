#!/usr/bin/env python3
"""Pipeline runner — Phase 0 initialization and configuration.

Usage:
    uv run python tools/pipeline_runner.py init [--window 7d] [--mock]

Writes: output/pipeline/run_config.json
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()

OUTPUT_ROOT = Path("output")


def init(window: str = "7d", mock: bool | None = None) -> dict:
    """Initialize pipeline run — validate env, write run_config.json."""
    # Determine OSINT mode
    if mock is None:
        mock = os.environ.get("OSINT_LIVE", "").lower() != "true"
    osint_mode = "mock" if mock else "live"

    # Determine Seerist availability
    seerist_available = bool(os.environ.get("SEERIST_API_KEY"))

    # Determine Scribe enrichment
    scribe_enrichment = seerist_available and window not in ("1d",)

    # Load last run timestamp
    last_run_timestamp = None
    history_path = OUTPUT_ROOT / "pipeline" / "history.json"
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
            runs = history.get("runs", [])
            if runs:
                last_run_timestamp = runs[-1].get("timestamp")
        except Exception:
            pass

    config = {
        "window": window,
        "osint_mode": osint_mode,
        "seerist_available": seerist_available,
        "scribe_enrichment": scribe_enrichment,
        "last_run_timestamp": last_run_timestamp,
        "written_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # Write run_config.json
    out_dir = OUTPUT_ROOT / "pipeline"
    out_dir.mkdir(parents=True, exist_ok=True)
    config_path = out_dir / "run_config.json"
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[pipeline_runner] init — mode={osint_mode}, window={window}, seerist={'yes' if seerist_available else 'no'}, scribe={'yes' if scribe_enrichment else 'no'}", file=sys.stderr)
    return config


def main():
    args = sys.argv[1:]
    if not args or args[0] != "init":
        print("Usage: pipeline_runner.py init [--window 7d] [--mock]", file=sys.stderr)
        sys.exit(1)

    window = "7d"
    mock = None
    if "--window" in args:
        idx = args.index("--window")
        if idx + 1 < len(args):
            window = args[idx + 1]
    if "--mock" in args:
        mock = True

    config = init(window=window, mock=mock)
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
