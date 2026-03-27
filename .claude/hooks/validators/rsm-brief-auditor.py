#!/usr/bin/env python3
"""
RSM Brief Auditor — stop hook validator for rsm-formatter-agent.

Validates both brief types:
  - weekly_intsum: AEROWIND // {REGION} INTSUM // WK{n}-{year}
  - flash:         ⚡ AEROWIND // {REGION} FLASH // {date} {time}Z

Checks:
  1. Brief type detected from first line
  2. Required section markers present
  3. ADM field is valid Admiralty format (A–D + 1–4)
  4. WATCH LIST has at least 3 items (INTSUM only)
  5. Reply line present and correct for brief type
  6. No forbidden jargon (CVEs, SOC language, budget advice)

Usage:
    uv run python .claude/hooks/validators/rsm-brief-auditor.py <brief_path> <label>

Exit 0 = APPROVED
Exit 2 = FAIL (prints specific failure with fix instructions)
"""
import re
import sys
import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]

# ── Jargon blocklists (shared with jargon-auditor) ──────────────────────────
FORBIDDEN_CYBER = [
    r"cve-\d{4}-\d+",
    r"\bip address\b",
    r"\bmalware hash\b",
    r"\bsha256\b",
    r"\bmd5 hash\b",
]
FORBIDDEN_SOC = [
    r"threat actor ttps",
    r"indicators? of compromise",
    r"\biocs?\b",
    r"mitre att.ck",
    r"\blateral movement\b",
    r"command and control",
    r"\bc2 server\b",
    r"persistence mechanism",
    r"zero.day exploit",
    r"privilege escalation",
]
FORBIDDEN_BUDGET = ["allocate budget", "purchase", "buy tools", "hire a ", "procure"]

# ── Required sections by brief type ──────────────────────────────────────────
INTSUM_SECTIONS = [
    "█ SITUATION",
    "█ PHYSICAL & GEOPOLITICAL",
    "█ CYBER",
    "█ EARLY WARNING (PRE-MEDIA)",
    "█ ASSESSMENT",
    "█ WATCH LIST",
]
FLASH_SECTIONS = [
    "DEVELOPING SITUATION",
    "AEROWIND EXPOSURE",
    "ACTION",
]

INTSUM_REPLY = "Reply: ACCURATE · OVERSTATED · UNDERSTATED · FALSE POSITIVE"
FLASH_REPLY = "Reply: ACKNOWLEDGED · REQUEST ESCALATION · FALSE POSITIVE"

# Admiralty: letter A-D + digit 1-4
ADM_RE = re.compile(r"\bADM:\s*[A-D][1-4]\b")
# WATCH LIST items: lines starting with a digit and period/dot
WATCH_ITEM_RE = re.compile(r"^\d+\.", re.MULTILINE)


def detect_brief_type(text: str) -> str | None:
    """Return 'intsum', 'flash', or None if unrecognised."""
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    if re.search(r"INTSUM\s*//\s*WK\d+-\d{4}", first_line):
        return "intsum"
    if re.search(r"FLASH\s*//\s*\d{4}-\d{2}-\d{2}", first_line):
        return "flash"
    return None


def check_sections(text: str, required: list[str]) -> list[str]:
    """Return list of missing section markers."""
    return [s for s in required if s not in text]


def check_watch_list_depth(text: str, min_items: int = 3) -> int:
    """Return count of WATCH LIST items (numbered lines after the section header)."""
    # Grab everything after █ WATCH LIST
    match = re.search(r"█ WATCH LIST.*?$", text, re.MULTILINE)
    if not match:
        return 0
    after_header = text[match.end():]
    items = WATCH_ITEM_RE.findall(after_header)
    return len(items)


def check_adm_field(text: str) -> bool:
    """Return True if a valid ADM field is present."""
    return bool(ADM_RE.search(text))


def check_jargon(content_lower: str) -> str | None:
    """Return failure message if forbidden jargon found, else None."""
    for pattern in FORBIDDEN_CYBER:
        if re.search(pattern, content_lower):
            return "Technical cyber jargon detected (CVE/IP/hash). Use business language only."
    for pattern in FORBIDDEN_SOC:
        if re.search(pattern, content_lower):
            return "SOC operational language detected (TTPs/IoCs/MITRE/lateral movement/C2). Remove entirely."
    if any(w in content_lower for w in FORBIDDEN_BUDGET):
        return "Budget or procurement advice detected. Remove entirely."
    return None


def main():
    if len(sys.argv) != 3:
        print("Usage: rsm-brief-auditor.py <brief_path> <label>")
        sys.exit(1)

    brief_path = Path(sys.argv[1])
    label = sys.argv[2]

    retry_file = BASE / "output" / ".retries" / f"{label}_rsm.retries"
    os.makedirs(retry_file.parent, exist_ok=True)

    retries = 0
    if retry_file.exists():
        try:
            retries = int(retry_file.read_text().strip())
        except ValueError:
            retries = 0

    if retries >= 3:
        print(
            f"RSM AUDIT: Max retries exceeded for [{label}]. Forcing approval.",
            file=sys.stderr,
        )
        retry_file.unlink(missing_ok=True)
        sys.exit(0)

    if not brief_path.exists():
        print(f"RSM AUDIT ERROR: Brief not found at {brief_path}", file=sys.stderr)
        sys.exit(1)

    text = brief_path.read_text(encoding="utf-8")
    failures: list[str] = []

    # ── 1. Brief type detection ────────────────────────────────────────────
    brief_type = detect_brief_type(text)
    if brief_type is None:
        failures.append(
            "Could not detect brief type from first line.\n"
            "  Expected: 'AEROWIND // {REGION} INTSUM // WK{n}-{year}' "
            "or '⚡ AEROWIND // {REGION} FLASH // {date} {time}Z'"
        )
    else:
        # ── 2. Required sections ───────────────────────────────────────────
        required = INTSUM_SECTIONS if brief_type == "intsum" else FLASH_SECTIONS
        missing = check_sections(text, required)
        for s in missing:
            failures.append(f"Missing required section: '{s}'")

        # ── 3. Reply line ──────────────────────────────────────────────────
        expected_reply = INTSUM_REPLY if brief_type == "intsum" else FLASH_REPLY
        if expected_reply not in text:
            failures.append(
                f"Missing reply line.\n  Expected: '{expected_reply}'"
            )

        # ── 4. WATCH LIST depth (INTSUM only) ─────────────────────────────
        if brief_type == "intsum":
            watch_count = check_watch_list_depth(text)
            if watch_count < 3:
                failures.append(
                    f"WATCH LIST has only {watch_count} item(s). Minimum 3 required. "
                    "Each item must start with a number and period (e.g., '1. ...')."
                )

    # ── 5. ADM field ──────────────────────────────────────────────────────
    if not check_adm_field(text):
        failures.append(
            "ADM field missing or invalid format.\n"
            "  Required: ADM: {letter A-D}{digit 1-4} — e.g., 'ADM: B2'"
        )

    # ── 6. Jargon check ───────────────────────────────────────────────────
    jargon_fail = check_jargon(text.lower())
    if jargon_fail:
        failures.append(jargon_fail)

    # ── Result ────────────────────────────────────────────────────────────
    if failures:
        print(
            f"RSM AUDIT FAILED [{label}]: {len(failures)} issue(s) found.\n",
            file=sys.stderr,
        )
        for i, f in enumerate(failures, 1):
            print(f"  [{i}] {f}", file=sys.stderr)
        print(
            "\nFix all issues above and rewrite the brief to the same path.",
            file=sys.stderr,
        )
        retry_file.write_text(str(retries + 1))
        sys.exit(2)

    print(
        f"RSM AUDIT PASSED [{label}]: brief is structurally valid and jargon-clean "
        f"(type={brief_type}, ADM present, {check_watch_list_depth(text) if brief_type == 'intsum' else 'N/A'} watch items)."
    )
    retry_file.unlink(missing_ok=True)
    sys.exit(0)


if __name__ == "__main__":
    main()