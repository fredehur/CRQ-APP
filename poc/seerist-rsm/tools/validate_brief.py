#!/usr/bin/env python3
"""Local pre-send validator for the RSM daily brief.

Replaces the parent repo's .claude/hooks/validators/rsm-formatter-stop.py,
which is intentionally absent from this slice. Run by poc_runner.py before
render — non-zero exit blocks the render output.

Scope of the site-name discipline check:
    STRICT: AEROWIND facility names (the rows formatted as `▪ Name [...]`
            in AEROWIND EXPOSURE) must match the manifest's site_registry
            exactly. An invented facility name is a hallucination and gets
            rejected.
    LENIENT: Geographic, port, city, and country names appearing in
             narrative prose (SITUATION, consequence lines, WATCH — NEXT 72H)
             are allowed — those mirror real-world events the brief is
             describing. For example, "reroute via Genoa not viable" is
             fine even if Genoa is not an AEROWIND facility, because it
             refers to a port, not a facility we operate.

Usage:
    uv run python tools/validate_brief.py BRIEF_MD MANIFEST_JSON
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = [
    "SITUATION",
    "AEROWIND EXPOSURE",
    "PHYSICAL & GEOPOLITICAL",
    "CYBER",
    "EARLY WARNING",
    "WATCH",  # matches "WATCH — NEXT 72H"
]

_SITE_ROW_RE = re.compile(
    r"^▪\s+(?P<name>[A-Za-z][\w \-]+?)\s+"
    r"\[(?P<crit>[A-Z][A-Z _]+)\s*·\s*"
    r"(?P<personnel>\d+)(?:p|\s+personnel)"
    r"(?:[,\s/]+(?P<expat>\d+)\s+expats?)?"
    r"\]",
    re.M,
)


class ValidationError(Exception):
    pass


def _check_sections(brief: str) -> None:
    for header in REQUIRED_SECTIONS:
        if header == "WATCH":
            if "█ WATCH — NEXT 72H" not in brief:
                raise ValidationError("Missing required section: WATCH — NEXT 72H")
        elif f"█ {header}" not in brief:
            raise ValidationError(f"Missing required section: {header}")


_REPLY_TAXONOMY_TOKENS = ["USEFUL", "NOISE", "MISSED CONTEXT", "FALSE POSITIVE"]
_REPLY_TAXONOMY_RE = re.compile(
    r"USEFUL.{0,80}NOISE.{0,80}MISSED CONTEXT.{0,80}FALSE POSITIVE",
    re.DOTALL | re.IGNORECASE,
)


def _check_no_reply_taxonomy(brief: str) -> None:
    if _REPLY_TAXONOMY_RE.search(brief):
        raise ValidationError(
            "reply taxonomy must not appear in brief body (template injects it)"
        )


def _check_cyber_section_has_content(brief: str) -> None:
    """Reject if the CYBER section is empty (heading only, no content)."""
    match = re.search(r"█ CYBER[^\n]*\n(.*?)(?=█|\Z)", brief, re.DOTALL)
    if not match:
        raise ValidationError("CYBER section not found")
    body = match.group(1).strip()
    if not body:
        raise ValidationError(
            "CYBER section is empty — must contain at least one bullet or prose line"
        )


def _check_site_discipline(brief: str, manifest: dict) -> None:
    registered = {s["name"]: s for s in manifest.get("site_registry", [])}
    mentioned = list(_SITE_ROW_RE.finditer(brief))

    if not mentioned and manifest.get("site_registry"):
        # No EXPOSURE rows at all — OK on a quiet day if an explicit sentinel is present.
        # v1: "No new events within radius"; v1.1 clean-site: "— clean."
        if "No new events within radius" not in brief and "— clean." not in brief:
            raise ValidationError(
                "AEROWIND EXPOSURE has no site rows and no 'No new events' or '— clean.' line. "
                "Brief is ambiguous about whether sites have exposure."
            )
        return

    illegal = []
    mismatches = []
    for m in mentioned:
        name = m.group("name").strip()
        if name not in registered:
            illegal.append(name)
            continue
        site = registered[name]
        personnel = int(m.group("personnel"))
        if personnel != site.get("personnel_count", -1):
            mismatches.append(
                f"{name}: brief says {personnel} personnel, registry says {site.get('personnel_count')}"
            )
        expat = m.group("expat")
        if expat is not None:
            expat_int = int(expat)
            if expat_int != site.get("expat_count", -1):
                mismatches.append(
                    f"{name}: brief says {expat_int} expat, registry says {site.get('expat_count')}"
                )

    if illegal:
        raise ValidationError(
            f"Brief mentions site names outside registry: {sorted(set(illegal))}. "
            f"Allowed: {sorted(registered)}"
        )
    if mismatches:
        raise ValidationError("Personnel/expat count mismatches: " + "; ".join(mismatches))


def main() -> int:
    p = argparse.ArgumentParser(description="Validate an RSM daily brief before HTML render.")
    p.add_argument("brief_md", type=Path, help="Path to brief.md")
    p.add_argument("manifest_json", type=Path, help="Path to _rsm_manifest_daily.json")
    args = p.parse_args()

    brief = args.brief_md.read_text(encoding="utf-8")
    manifest = json.loads(args.manifest_json.read_text(encoding="utf-8"))

    try:
        _check_sections(brief)
        _check_no_reply_taxonomy(brief)
        _check_cyber_section_has_content(brief)
        _check_site_discipline(brief, manifest)
    except ValidationError as e:
        print(f"[validate_brief] FAIL: {e}", file=sys.stderr)
        return 1

    print(f"[validate_brief] OK: {args.brief_md}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
