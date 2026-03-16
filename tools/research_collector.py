#!/usr/bin/env python3
"""Target-centric OSINT research collector.

Usage:
    uv run python tools/research_collector.py <REGION> [--mock]

Mock mode: delegates to geo_collector.py + cyber_collector.py (unchanged behaviour).
Live mode: 3-pass target-centric loop using Anthropic API.

Writes (live mode only):
    output/regional/{region}/research_scratchpad.json  — audit trail
    output/regional/{region}/geo_signals.json          — same schema as geo_collector
    output/regional/{region}/cyber_signals.json        — same schema as cyber_collector
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
REPO_ROOT = Path(__file__).resolve().parent.parent


def run_mock_mode(region: str) -> None:
    """Delegate to existing collectors unchanged."""
    for collector in ("geo_collector", "cyber_collector"):
        subprocess.run(
            [sys.executable, f"tools/{collector}.py", region, "--mock"],
            check=True,
            cwd=REPO_ROOT,
        )


def run_live_mode(region: str) -> None:
    """Target-centric collection loop — 3 LLM calls."""
    raise NotImplementedError("Live mode not yet implemented")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: research_collector.py <REGION> [--mock]", file=sys.stderr)
        sys.exit(1)

    region = sys.argv[1].upper()
    if region not in VALID_REGIONS:
        print(f"Invalid region: {region}. Valid: {VALID_REGIONS}", file=sys.stderr)
        sys.exit(1)

    mock = "--mock" in sys.argv

    if mock:
        run_mock_mode(region)
    else:
        run_live_mode(region)


if __name__ == "__main__":
    main()
