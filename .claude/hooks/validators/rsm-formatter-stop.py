#!/usr/bin/env python3
"""
RSM formatter stop hook — fires when rsm-formatter-agent session ends.

Discovers the most recently modified RSM brief (rsm_*.md) across all regional
output directories within the last 5 minutes, then runs the RSM brief auditor.

This hook fires on EVERY invocation of rsm-formatter-agent regardless
of whether it was spawned by rsm_dispatcher.py, notifier.py, or any other caller.

Exit 0 = audit passed (agent session allowed to end cleanly)
Exit 2 = audit failed (orchestrator receives failure, triggers rewrite)
"""
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]
REGIONAL = BASE / "output" / "regional"
REGIONS = ["apac", "ame", "latam", "med", "nce"]


def find_recent_rsm_brief(max_age_seconds: int = 300) -> Path | None:
    """Return the RSM brief path most recently modified (within max_age_seconds)."""
    now = time.time()
    candidates = []
    for region in REGIONS:
        region_dir = REGIONAL / region
        if not region_dir.is_dir():
            continue
        for brief in region_dir.glob("rsm_*.md"):
            mtime = brief.stat().st_mtime
            age = now - mtime
            if age <= max_age_seconds:
                candidates.append((mtime, brief))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def derive_label(brief_path: Path) -> str:
    """Derive a stable circuit-breaker label from the brief filename."""
    # e.g. rsm_brief_ame_2026-03-25 → rsm_brief_ame_2026-03-25
    return brief_path.stem


def run_check(script: str, *args) -> int:
    """Run a validator script and return its exit code."""
    result = subprocess.run(
        ["uv", "run", "python", str(BASE / ".claude" / "hooks" / "validators" / script), *args],
        cwd=str(BASE),
    )
    return result.returncode


def parse_brief_filename(brief_path: Path) -> tuple[str, str]:
    """rsm_brief_med_2026-04-14.md → ('MED', 'weekly')
    rsm_daily_med_2026-04-14.md → ('MED', 'daily')
    rsm_flash_med_2026-04-14T10-30Z.md → ('MED', 'flash')"""
    parts = brief_path.stem.split("_")
    if len(parts) < 3:
        return ("UNKNOWN", "weekly")
    kind = parts[1]
    region = parts[2].upper()
    cadence = {"brief": "weekly", "daily": "daily", "flash": "flash"}.get(kind, "weekly")
    return (region, cadence)


def main():
    brief_path = find_recent_rsm_brief()

    if brief_path is None:
        print("RSM STOP HOOK: no recent rsm_*.md found — skipping audit.")
        sys.exit(0)

    label = derive_label(brief_path)
    rel_path = brief_path.relative_to(BASE)
    region, cadence = parse_brief_filename(brief_path)
    print(f"RSM STOP HOOK: auditing {rel_path} (region={region}, cadence={cadence})")

    auditor_exit = run_check("rsm-brief-auditor.py", str(rel_path), label)
    if auditor_exit != 0:
        sys.exit(auditor_exit)

    context_exit = run_check("rsm-brief-context-checks.py", str(rel_path), region, cadence)
    sys.exit(context_exit)


if __name__ == "__main__":
    main()