#!/usr/bin/env python3
"""RSM brief context checks — deterministic post-write validation.

Adds the new checks introduced by the RSM context-and-coverage spec on top of
the existing rsm-brief-auditor.py:

  - site name discipline (no off-region or invented sites)
  - personnel count match against aerowind_sites.json
  - cross-region body discipline (no naming sites in other regions)
  - daily cadence short-circuit (no ASSESSMENT/WATCH LIST in daily)
  - no quoted Seerist scribe text
  - AEROWIND EXPOSURE consequence line <= 2 sentences

Usage:
  rsm-brief-context-checks.py <brief_path> <region> <cadence>

Exit codes:
  0 - all checks pass
  2 - one or more checks failed (failure list printed to stderr)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SITES_PATH = REPO_ROOT / "data" / "aerowind_sites.json"
ALL_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
DAILY_FORBIDDEN_SECTIONS = ["█ ASSESSMENT", "█ WATCH LIST", "REFERENCES"]
CONSEQUENCE_MAX_SENTENCES = 2


def _load_sites_for_region(region: str) -> tuple[list[str], dict[str, dict]]:
    sites = json.loads(SITES_PATH.read_text(encoding="utf-8"))["sites"]
    region_sites = [s for s in sites if s["region"] == region.upper()]
    allowed = [s["name"] for s in region_sites]
    personnel = {
        s["name"]: {
            "personnel": s.get("personnel_count", 0),
            "expat": s.get("expat_count", 0),
        }
        for s in region_sites
    }
    return allowed, personnel


def _load_other_region_site_names(region: str) -> list[str]:
    sites = json.loads(SITES_PATH.read_text(encoding="utf-8"))["sites"]
    return [s["name"] for s in sites if s["region"] != region.upper()]


def _scribe_texts_for_region(region: str) -> list[str]:
    fixture = REPO_ROOT / "data" / "mock_osint_fixtures" / f"{region.lower()}_seerist.json"
    if not fixture.exists():
        return []
    data = json.loads(fixture.read_text(encoding="utf-8"))
    return [s.get("text", "") for s in data.get("analytical", {}).get("scribe", []) if s.get("text")]


# -- individual checks -------------------------------------------------------

def check_site_name_discipline(brief_text: str, allowed_sites: list[str], region: str) -> list[str]:
    """No site name from any other region; AeroGrid sites named must be in `allowed_sites`."""
    failures = []
    other_sites = _load_other_region_site_names(region)
    for name in other_sites:
        if re.search(rf"\b{re.escape(name)}\b", brief_text):
            failures.append(f"Off-region site name in body: '{name}'")
    # Also flag any site named in the AEROWIND EXPOSURE pattern that isn't in allowed_sites.
    # Pattern: `▪ {Site Name} [{CRITICALITY} · {N} personnel...]`
    pattern = re.compile(
        r"▪\s+([A-Z][^\[\n]+?)\s+\[[A-Z_]+\s*·\s*\d+\s+personnel"
    )
    allowed_set = set(allowed_sites)
    for m in pattern.finditer(brief_text):
        claimed = m.group(1).strip()
        if claimed not in allowed_set:
            failures.append(f"Invented site name in AEROWIND EXPOSURE block: '{claimed}'")
    return failures


def check_personnel_count_match(brief_text: str, site_personnel: dict[str, dict]) -> list[str]:
    """Every '<N> personnel' line attributed to a known site must match the registry value."""
    failures = []
    pattern = re.compile(
        r"▪\s+([A-Z][^\[\n]+?)\s+\[[A-Z_]+\s*·\s*(\d+)\s+personnel(?:,\s*(\d+)\s+expat)?\]"
    )
    for m in pattern.finditer(brief_text):
        site_name = m.group(1).strip()
        claimed_personnel = int(m.group(2))
        claimed_expat = int(m.group(3)) if m.group(3) else None
        truth = site_personnel.get(site_name)
        if not truth:
            continue
        if claimed_personnel != truth["personnel"]:
            failures.append(
                f"Personnel mismatch for '{site_name}': brief says {claimed_personnel}, "
                f"registry says {truth['personnel']}"
            )
        if claimed_expat is not None and claimed_expat != truth["expat"]:
            failures.append(
                f"Expat count mismatch for '{site_name}': brief says {claimed_expat}, "
                f"registry says {truth['expat']}"
            )
    return failures


def check_cadence_sections(brief_text: str, cadence: str) -> list[str]:
    """Daily must NOT contain weekly-only sections."""
    if cadence != "daily":
        return []
    failures = []
    for forbidden in DAILY_FORBIDDEN_SECTIONS:
        if forbidden in brief_text:
            failures.append(f"Cadence violation: '{forbidden}' present in daily brief")
    return failures


def check_no_quoted_scribe(brief_text: str, scribe_texts: list[str]) -> list[str]:
    """Brief body must not contain any verbatim string >= 40 chars from scribe entries."""
    failures = []
    for text in scribe_texts:
        if not text or len(text) < 40:
            continue
        snippet = text.strip()[:80]
        if snippet in brief_text:
            failures.append(f"Quoted Seerist scribe text detected: '{snippet[:60]}...'")
    return failures


def check_consequence_length(brief_text: str) -> list[str]:
    """Each `Consequence:` line is <= 2 sentences."""
    failures = []
    for m in re.finditer(r"Consequence:\s+(.+)", brief_text):
        line = m.group(1).strip()
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
        if len(sentences) > CONSEQUENCE_MAX_SENTENCES:
            failures.append(
                f"Consequence line exceeds {CONSEQUENCE_MAX_SENTENCES} sentences: "
                f"'{line[:80]}...'"
            )
    return failures


def check_daily_empty_stub(brief_text: str, cadence: str) -> list[str]:
    """If daily AND header shows NEW: 0 EVT · 0 HOT · 0 CYB, brief must be the stub form."""
    if cadence != "daily":
        return []
    if "NEW: 0 EVT · 0 HOT · 0 CYB" not in brief_text:
        return []
    failures = []
    if "Nothing to escalate. Next check 24h." not in brief_text:
        failures.append(
            "Daily empty-stub mismatch: NEW=0 but stub footer 'Nothing to escalate. Next check 24h.' missing"
        )
    if "█ AEROWIND EXPOSURE" in brief_text:
        failures.append(
            "Daily empty-stub violation: full sections present despite zero new signals"
        )
    return failures


def run_all_checks(
    brief_path: Path,
    region: str,
    allowed_sites: list[str],
    site_personnel: dict[str, dict],
    cadence: str,
    scribe_texts: list[str],
) -> list[str]:
    text = brief_path.read_text(encoding="utf-8")
    failures = []
    failures += check_site_name_discipline(text, allowed_sites, region)
    failures += check_personnel_count_match(text, site_personnel)
    failures += check_cadence_sections(text, cadence)
    failures += check_no_quoted_scribe(text, scribe_texts)
    failures += check_consequence_length(text)
    failures += check_daily_empty_stub(text, cadence)
    return failures


def main():
    args = sys.argv[1:]
    if len(args) < 3:
        print("Usage: rsm-brief-context-checks.py <brief_path> <region> <cadence>", file=sys.stderr)
        sys.exit(1)
    brief_path = Path(args[0])
    region = args[1].upper()
    cadence = args[2].lower()

    if region not in ALL_REGIONS:
        print(f"invalid region '{region}'", file=sys.stderr)
        sys.exit(1)
    if cadence not in {"daily", "weekly", "flash"}:
        print(f"invalid cadence '{cadence}'", file=sys.stderr)
        sys.exit(1)

    if not brief_path.exists():
        print(f"brief not found: {brief_path}", file=sys.stderr)
        sys.exit(1)

    allowed, personnel = _load_sites_for_region(region)
    scribe = _scribe_texts_for_region(region)

    failures = run_all_checks(
        brief_path,
        region=region,
        allowed_sites=allowed,
        site_personnel=personnel,
        cadence=cadence,
        scribe_texts=scribe,
    )

    if failures:
        print(f"RSM CONTEXT CHECKS FAILED ({len(failures)} issue(s)):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(2)
    print("RSM CONTEXT CHECKS PASSED", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
