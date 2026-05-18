#!/usr/bin/env python3
"""Normalize body citations and synthesize the APPENDIX — SOURCES section.

The formatter writes brief.md with `[<claim_id>]` body cites (e.g. `[med-001]`
or `[med-001, med-002]`). This tool walks the brief in document order, assigns
each unique claim_id a sequential number `[1]`, `[2]`, ..., rewrites every
citation bracket accordingly, and appends a synthesized `█ APPENDIX — SOURCES`
block listing each numbered entry against its claim text + signal_ids.

This is pure deterministic code (per agent-boundary-principles.md: numbering,
state management, and schema validation are code territory — never agent
territory). The formatter cites by claim_id (judgment); code does the math.

Idempotent: if the brief already contains `█ APPENDIX`, no-op.

Usage:
    uv run python tools/normalize_citations.py BRIEF_MD CLAIMS_JSON --out OUT_MD
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# A citation bracket: `[<claim_id>]` or `[<id_1>, <id_2>, ...]`.
# Claim IDs are lowercase, hyphenated tokens like `med-001`, `med-cyb-002`.
# This regex deliberately matches ONLY brackets whose contents are
# comma-separated claim-id-shaped tokens — it will not match severity bands
# (`[CRITICAL · sev 6 · ...]`), surface chips (`[OT/ICS]`), or site row meta
# (`[CROWN_JEWEL · 47 personnel, 8 expat]`).
_CLAIM_ID_TOKEN = r"[a-z]+(?:-[a-z0-9]+)+"
_CITATION_BRACKET_RE = re.compile(
    rf"\[({_CLAIM_ID_TOKEN}(?:\s*,\s*{_CLAIM_ID_TOKEN})*)\]"
)

# Source type labels derived from the signal_id namespace prefix.
_SOURCE_TYPE_LABELS = {
    "seerist:cyber": "Seerist analysis",
    "seerist:verified": "Seerist verified event",
    "seerist:hotspot": "Seerist hotspot",
    "seerist:events_ai": "Seerist AI event",
    "seerist:events": "Seerist event",
    "seerist:pulse": "Seerist pulse",
    "osint": "OSINT",
}

APPENDIX_HEADER = "█ APPENDIX — SOURCES"


class NormalizationError(Exception):
    pass


def _source_type_label(signal_id: str) -> str:
    """Map a signal_id prefix to a human label for the appendix."""
    for prefix, label in _SOURCE_TYPE_LABELS.items():
        if signal_id.startswith(prefix + ":"):
            return label
    return "signal"


def _claim_snippet(claim: dict, max_len: int = 140) -> str:
    """Short prose tag for an appendix entry — first sentence or trimmed text."""
    body = (claim.get("text") or claim.get("headline") or "").strip()
    if not body:
        return claim.get("claim_id", "(no text)")
    # Prefer first sentence if it fits; otherwise truncate at word boundary.
    first_sentence = re.split(r"(?<=[.!?])\s+", body, maxsplit=1)[0]
    if len(first_sentence) <= max_len:
        return first_sentence
    truncated = body[:max_len].rsplit(" ", 1)[0]
    return truncated + "..."


def _format_appendix_entry(number: int, claim: dict) -> str:
    """One `[N] snippet — sig1; sig2 (Source type)` line."""
    snippet = _claim_snippet(claim)
    signal_ids = claim.get("signal_ids") or []
    if signal_ids:
        sig_blob = "; ".join(signal_ids)
        label = _source_type_label(signal_ids[0])
        return f"[{number}] {snippet} — {sig_blob} ({label})"
    return f"[{number}] {snippet} — (no signal_id; analyst estimate)"


def _load_claims(claims_path: Path) -> dict[str, dict]:
    doc = json.loads(claims_path.read_text(encoding="utf-8"))
    claims = doc.get("claims") if isinstance(doc, dict) else doc
    if not isinstance(claims, list):
        raise NormalizationError(
            f"{claims_path}: expected a list of claims (or {{'claims': [...]}})"
        )
    by_id: dict[str, dict] = {}
    for c in claims:
        cid = c.get("claim_id")
        if not cid:
            continue
        by_id[cid] = c
    return by_id


def normalize(brief_text: str, claims_by_id: dict[str, dict]) -> str:
    """Return the brief with body cites renumbered and APPENDIX appended.

    Idempotent: if `█ APPENDIX` is already present, returns input unchanged.
    Raises NormalizationError if the body cites a claim_id absent from claims.
    """
    if APPENDIX_HEADER.split(" — ")[0] in brief_text:
        # Already normalized (APPENDIX header present).
        return brief_text

    id_to_number: dict[str, int] = {}
    ordered_ids: list[str] = []
    missing: list[str] = []

    def _renumber(match: re.Match) -> str:
        inner = match.group(1)
        tokens = [t.strip() for t in inner.split(",")]
        numbers: list[str] = []
        for tok in tokens:
            if tok not in claims_by_id:
                missing.append(tok)
                # Keep token verbatim so the error message can point at it.
                numbers.append(f"?{tok}?")
                continue
            if tok not in id_to_number:
                id_to_number[tok] = len(ordered_ids) + 1
                ordered_ids.append(tok)
            numbers.append(str(id_to_number[tok]))
        return "[" + ", ".join(numbers) + "]"

    rewritten_body = _CITATION_BRACKET_RE.sub(_renumber, brief_text)

    if missing:
        raise NormalizationError(
            "Body cites claim_ids not present in claims.json: "
            f"{sorted(set(missing))}. Known claim_ids: {sorted(claims_by_id)}."
        )

    # Build appendix section.
    appendix_lines = [APPENDIX_HEADER]
    if ordered_ids:
        for n, cid in enumerate(ordered_ids, start=1):
            appendix_lines.append(_format_appendix_entry(n, claims_by_id[cid]))
    else:
        appendix_lines.append("No sources cited this window.")

    appendix_block = "\n".join(appendix_lines) + "\n"

    # Append with a single blank line separator before APPENDIX.
    sep = "" if rewritten_body.endswith("\n\n") else (
        "\n" if rewritten_body.endswith("\n") else "\n\n"
    )
    return rewritten_body + sep + appendix_block


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("brief_md", type=Path, help="Path to brief.md (formatter output)")
    p.add_argument("claims_json", type=Path, help="Path to claims.json (analyst output)")
    p.add_argument(
        "--out", type=Path, default=None,
        help="Output path (default: overwrite brief_md in place)",
    )
    args = p.parse_args()

    brief_text = args.brief_md.read_text(encoding="utf-8")
    claims_by_id = _load_claims(args.claims_json)

    try:
        normalized = normalize(brief_text, claims_by_id)
    except NormalizationError as e:
        print(f"[normalize_citations] FAIL: {e}", file=sys.stderr)
        return 1

    out = args.out or args.brief_md
    out.write_text(normalized, encoding="utf-8")
    print(f"[normalize_citations] OK: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
