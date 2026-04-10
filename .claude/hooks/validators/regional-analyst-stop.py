#!/usr/bin/env python3
"""
Regional analyst stop hook — fires when regional-analyst-agent session ends.

Discovers which region was just processed by finding the most recently
modified report.md, then runs all quality gates:
  1. jargon-auditor           — no CVEs, IPs, SOC language, budget advice
  2. source-attribution-auditor — evidenced claims must cite named sources
  3. claims-schema-validator  — convergence_assessment present, bullets field
                                on every claim, ≥2 watch-paragraph claims
  4. seerist-hierarchy        — first why-claim Seerist-anchored, substantive signals covered

This hook fires on EVERY invocation of regional-analyst-agent regardless
of whether it was spawned by run-crq, crq-region, or any other caller.

Exit 0 = all gates passed (agent session allowed to end cleanly)
Exit 2 = gate failed (orchestrator receives failure, triggers rewrite)
"""
import json
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BASE))
from tools.regional_analyst_stop_gate4 import validate_seerist_hierarchy  # noqa: E402
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


def validate_claims_schema(region: str) -> tuple[bool, list[str]]:
    """
    Gate 3: Validate claims.json schema contract.

    Rules (must all pass):
    - Top-level 'convergence_assessment' with 'category' and 'rationale'
    - Every claim has a non-empty 'bullets' field
    - At least 2 claims with paragraph == 'watch'
    """
    claims_path = REGIONAL / region / "claims.json"
    if not claims_path.exists():
        return False, ["claims.json not found"]

    try:
        data = json.loads(claims_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, [f"claims.json is not valid JSON: {e}"]

    violations = []

    # Rule 1: convergence_assessment
    ca = data.get("convergence_assessment")
    if not ca:
        violations.append("Missing top-level 'convergence_assessment'")
    else:
        if not ca.get("category"):
            violations.append("convergence_assessment.category is missing or empty")
        if not ca.get("rationale"):
            violations.append("convergence_assessment.rationale is missing or empty")

    # Rule 2: every claim has 'bullets'
    claims = data.get("claims", [])
    missing_bullets = [
        c.get("claim_id", f"index-{i}")
        for i, c in enumerate(claims)
        if not c.get("bullets")
    ]
    if missing_bullets:
        violations.append(
            f"Claims missing 'bullets' field: {', '.join(missing_bullets)}"
        )

    # Rule 3: at least 2 watch-paragraph claims
    watch_claims = [c for c in claims if c.get("paragraph") == "watch"]
    if len(watch_claims) < 2:
        violations.append(
            f"Need ≥2 claims with paragraph='watch', found {len(watch_claims)}"
        )

    return len(violations) == 0, violations


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

    # Gate 3: Claims schema validation
    passed, violations = validate_claims_schema(region)
    if not passed:
        print(f"CLAIMS SCHEMA AUDIT FAILED [{region.upper()}]:")
        for v in violations:
            print(f"  - {v}")
        print(
            "\nREQUIRED FIXES:\n"
            "  1. Add top-level convergence_assessment {{category, rationale}} to claims.json\n"
            "  2. Add 'bullets' field to every claim (intel_bullets / adversary_bullets / impact_bullets / watch_bullets)\n"
            "  3. Add ≥2 claims with paragraph='watch' and bullets='watch_bullets' for forward-looking indicators"
        )
        sys.exit(2)

    # Gate 4: Seerist hierarchy
    hier_passed, hier_violations = validate_seerist_hierarchy(region)
    if not hier_passed:
        print(f"SEERIST HIERARCHY AUDIT FAILED [{region.upper()}]:")
        for v in hier_violations:
            print(f"  - {v}")
        print(
            "\nREQUIRED FIXES:\n"
            "  1. First why-paragraph claim must cite a seerist:event/hotspot/pulse signal_id\n"
            "  2. Every hotspot anomaly and verified event must have a corresponding claim\n"
            "  3. Read seerist_signals.json FIRST and build your risk picture from Seerist signals"
        )
        sys.exit(2)

    print(f"REGIONAL STOP HOOK: all gates passed for {region.upper()}.")
    sys.exit(0)


if __name__ == "__main__":
    main()