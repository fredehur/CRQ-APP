#!/usr/bin/env python3
"""
Regional analyst stop hook — fires when regional-analyst-agent session ends.

Discovers which region was just processed by finding the most recently
modified report.md, then runs both quality gates:
  1. jargon-auditor    — no CVEs, IPs, SOC language, budget advice
  2. source-attribution-auditor — evidenced claims must cite named sources

This hook fires on EVERY invocation of regional-analyst-agent regardless
of whether it was spawned by run-crq, crq-region, or any other caller.

Exit 0 = all gates passed (agent session allowed to end cleanly)
Exit 2 = gate failed (orchestrator receives failure, triggers rewrite)
"""
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]
REGIONAL = BASE / "output" / "regional"
REGIONS = ["apac", "ame", "latam", "med", "nce"]


def find_recent_region(max_age_seconds: int = 300) -> str | None:
    """Return the region whose report.md was most recently modified (within max_age_seconds)."""
    now = time.time()
    candidates = []
    for region in REGIONS:
        report = REGIONAL / region / "report.md"
        if report.exists():
            mtime = report.stat().st_mtime
            age = now - mtime
            if age <= max_age_seconds:
                candidates.append((mtime, region))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def run_check(script: str, *args) -> int:
    """Run a validator script and return its exit code."""
    result = subprocess.run(
        ["uv", "run", "python", str(BASE / ".claude" / "hooks" / "validators" / script), *args],
        cwd=str(BASE),
    )
    return result.returncode


def main():
    region = find_recent_region()

    if region is None:
        # No recently modified report.md found — agent may have run for a CLEAR region
        # or report was already written long ago. Skip gracefully.
        print("REGIONAL STOP HOOK: no recent report.md found — skipping audits.")
        sys.exit(0)

    report_path = f"output/regional/{region}/report.md"
    print(f"REGIONAL STOP HOOK: auditing {region.upper()} — {report_path}")

    # Gate 1: Jargon audit
    jargon_exit = run_check("jargon-auditor.py", report_path, region)
    if jargon_exit != 0:
        sys.exit(jargon_exit)

    # Gate 2: Source attribution audit
    src_exit = run_check("source-attribution-auditor.py", report_path, region, region)
    if src_exit != 0:
        sys.exit(src_exit)

    print(f"REGIONAL STOP HOOK: all gates passed for {region.upper()}.")
    sys.exit(0)


if __name__ == "__main__":
    main()