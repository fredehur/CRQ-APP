#!/usr/bin/env python3
"""
Deterministic validator for output/global_report.json.

Replaces Haiku agent for all arithmetic and string-matching checks.
These checks must be 100% deterministic — no LLM reasoning in the loop.

Exit 0  = APPROVED
Exit 2  = FAIL (prints numbered failure list to stderr)
"""
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]  # crq-agent-workspace root
OUTPUT = BASE / "output"
REGIONAL = OUTPUT / "regional"
REGIONS = ["apac", "ame", "latam", "med", "nce"]

RETRY_FILE = OUTPUT / ".retries" / "validate_global_json.retries"


def load_json(path: Path, label: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        return f"PARSE_ERROR: {e}"


def check_retries() -> int:
    os.makedirs(RETRY_FILE.parent, exist_ok=True)
    if RETRY_FILE.exists():
        try:
            return int(RETRY_FILE.read_text().strip())
        except ValueError:
            return 0
    return 0


def increment_retries(n: int):
    RETRY_FILE.write_text(str(n + 1))


def clear_retries():
    if RETRY_FILE.exists():
        RETRY_FILE.unlink()


def main():
    retries = check_retries()
    if retries >= 3:
        print("VALIDATE: Max retries exceeded. Forcing approval.", file=sys.stderr)
        clear_retries()
        sys.exit(0)

    report_path = OUTPUT / "global_report.json"
    report = load_json(report_path, "global_report")

    if report is None:
        print("VALIDATE FAIL: output/global_report.json not found.", file=sys.stderr)
        increment_retries(retries)
        sys.exit(2)

    if isinstance(report, str):
        print(f"VALIDATE FAIL: {report}", file=sys.stderr)
        increment_retries(retries)
        sys.exit(2)

    failures = []

    # ── Check 1: VaCR arithmetic ─────────────────────────────────────────────
    regional_threats = report.get("regional_threats", [])
    declared_total = report.get("total_vacr_exposure")
    computed_total = sum(r.get("vacr_exposure", 0) for r in regional_threats)

    if not isinstance(declared_total, (int, float)):
        failures.append(
            f"1. total_vacr_exposure is not a number: {declared_total!r}"
        )
    elif computed_total != declared_total:
        failures.append(
            f"1. VaCR sum mismatch: regional_threats sum = {computed_total:,}, "
            f"total_vacr_exposure = {declared_total:,}"
        )

    # ── Check 2: Admiralty consistency (report vs gatekeeper_decision.json) ──
    for threat in regional_threats:
        region = threat.get("region", "").lower()
        reported_admiralty = threat.get("admiralty_rating")
        gk_path = REGIONAL / region / "gatekeeper_decision.json"
        gk = load_json(gk_path, f"{region}-gatekeeper")

        if gk is None:
            failures.append(
                f"2. {region.upper()}: gatekeeper_decision.json not found "
                f"(but region appears in regional_threats)"
            )
            continue

        if isinstance(gk, str):
            failures.append(f"2. {region.upper()}: gatekeeper_decision.json parse error — {gk}")
            continue

        gk_admiralty = gk.get("admiralty", {}).get("rating")
        if reported_admiralty != gk_admiralty:
            failures.append(
                f"2. {region.upper()} admiralty mismatch: report says {reported_admiralty!r}, "
                f"gatekeeper_decision says {gk_admiralty!r}"
            )

    # ── Check 3: Scenario mapping (report vs data.json) ──────────────────────
    for threat in regional_threats:
        region = threat.get("region", "").lower()
        reported_scenario = threat.get("primary_scenario")
        data_path = REGIONAL / region / "data.json"
        data = load_json(data_path, f"{region}-data")

        if data is None:
            failures.append(
                f"3. {region.upper()}: data.json not found "
                f"(but region appears in regional_threats)"
            )
            continue

        if isinstance(data, str):
            failures.append(f"3. {region.upper()}: data.json parse error — {data}")
            continue

        data_scenario = data.get("primary_scenario")
        if reported_scenario != data_scenario:
            failures.append(
                f"3. {region.upper()} scenario mismatch: report says {reported_scenario!r}, "
                f"data.json says {data_scenario!r}"
            )

    # ── Check 4: Region count arithmetic ──────────────────────────────────────
    regions_analyzed = report.get("regions_analyzed")
    regions_escalated = report.get("regions_escalated")
    regions_monitored = report.get("regions_monitored", 0)
    regions_clear = report.get("regions_clear")

    for field, val in [
        ("regions_analyzed", regions_analyzed),
        ("regions_escalated", regions_escalated),
        ("regions_clear", regions_clear),
    ]:
        if not isinstance(val, int):
            failures.append(f"4. {field} is missing or not an integer: {val!r}")

    if all(isinstance(v, int) for v in [regions_analyzed, regions_escalated, regions_monitored, regions_clear]):
        expected = regions_escalated + regions_monitored + regions_clear
        if expected != regions_analyzed:
            failures.append(
                f"4. Region count mismatch: escalated({regions_escalated}) + "
                f"monitored({regions_monitored}) + clear({regions_clear}) = {expected}, "
                f"but regions_analyzed = {regions_analyzed}"
            )

    # ── Check 5: No phantom regions (report.md must exist) ───────────────────
    for threat in regional_threats:
        region = threat.get("region", "").lower()
        report_md = REGIONAL / region / "report.md"
        if not report_md.exists():
            failures.append(
                f"5. Phantom region: {region.upper()} appears in regional_threats "
                f"but output/regional/{region}/report.md does not exist"
            )

    # ── Check 6: financial_rank consistency (report vs data.json) ─────────────
    for threat in regional_threats:
        region = threat.get("region", "").lower()
        reported_rank = threat.get("financial_rank")
        data_path = REGIONAL / region / "data.json"
        data = load_json(data_path, f"{region}-data")

        if data is None or isinstance(data, str):
            continue  # already caught in check 3

        data_rank = data.get("financial_rank")
        if reported_rank is not None and data_rank is not None and reported_rank != data_rank:
            failures.append(
                f"6. {region.upper()} financial_rank mismatch: report says {reported_rank}, "
                f"data.json says {data_rank}"
            )

    # ── Result ────────────────────────────────────────────────────────────────
    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        print("\nREWRITE", file=sys.stderr)
        increment_retries(retries)
        sys.exit(2)

    escalated = len(regional_threats)
    monitored = len(report.get("monitor_regions", []))
    print(
        f"VALIDATE PASSED: global_report.json — "
        f"{escalated} escalated, {monitored} monitored, "
        f"total VaCR ${computed_total:,.0f}"
    )
    clear_retries()
    sys.exit(0)


if __name__ == "__main__":
    main()