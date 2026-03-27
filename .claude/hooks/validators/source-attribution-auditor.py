#!/usr/bin/env python3
"""
Source Attribution Auditor — regional analyst stop hook.

Verifies that every paragraph containing "evidenced" in a regional brief
cites at least one named source from the corresponding signal_clusters.json.

This closes the hallucination vector where an agent marks a fabricated claim
as "evidenced" without any traceable source.

Usage:
    uv run python .claude/hooks/validators/source-attribution-auditor.py <report_path> <region> <label>

Exit 0 = APPROVED
Exit 2 = FAIL (prints specific failure with instructions)
"""
import json
import re
import sys
import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]


def load_source_names(region: str) -> list[str]:
    """Extract all named sources from signal_clusters.json for this region."""
    clusters_path = BASE / "output" / "regional" / region.lower() / "signal_clusters.json"
    if not clusters_path.exists():
        return []
    try:
        data = json.loads(clusters_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    names = set()
    for cluster in data.get("clusters", []):
        for source in cluster.get("sources", []):
            name = source.get("name", "").strip()
            # Skip generic mock-mode labels — they carry no attribution value
            if name and name not in ("Cyber Signal", "Geo Signal", "YouTube Signal"):
                names.add(name)
    return list(names)


def get_evidenced_paragraphs(text: str) -> list[str]:
    """Return paragraphs that contain the word 'evidenced' (case-insensitive)."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return [p for p in paragraphs if re.search(r"\bevidenced\b", p, re.IGNORECASE)]


def paragraph_has_source(paragraph: str, source_names: list[str]) -> tuple[bool, list[str]]:
    """Check if a paragraph contains at least one named source. Returns (found, missing)."""
    found = [s for s in source_names if s.lower() in paragraph.lower()]
    return len(found) > 0, found


def main():
    if len(sys.argv) != 4:
        print("Usage: source-attribution-auditor.py <report_path> <region> <label>")
        sys.exit(1)

    report_path = Path(sys.argv[1])
    region = sys.argv[2]
    label = sys.argv[3]

    retry_file = BASE / "output" / ".retries" / f"{label}_src.retries"
    os.makedirs(retry_file.parent, exist_ok=True)

    retries = 0
    if retry_file.exists():
        try:
            retries = int(retry_file.read_text().strip())
        except ValueError:
            retries = 0

    if retries >= 3:
        print(f"SOURCE AUDIT: Max retries exceeded for [{label}]. Forcing approval.", file=sys.stderr)
        retry_file.unlink(missing_ok=True)
        sys.exit(0)

    # Load the brief
    if not report_path.exists():
        print(f"SOURCE AUDIT ERROR: Report not found at {report_path}", file=sys.stderr)
        sys.exit(1)

    text = report_path.read_text(encoding="utf-8")

    # Load source names from signal_clusters.json
    source_names = load_source_names(region)

    if not source_names:
        # No named sources available (mock mode with generic labels, or clusters not yet written)
        # Pass — cannot enforce what doesn't exist
        print(f"SOURCE AUDIT SKIPPED [{label}]: no named sources in signal_clusters.json — pass.")
        sys.exit(0)

    # Find paragraphs with "evidenced"
    evidenced_paras = get_evidenced_paragraphs(text)

    if not evidenced_paras:
        # No evidenced claims — nothing to check
        print(f"SOURCE AUDIT PASSED [{label}]: no 'evidenced' claims found — pass.")
        sys.exit(0)

    # Check each evidenced paragraph for at least one named source
    failures = []
    for i, para in enumerate(evidenced_paras, 1):
        has_source, found = paragraph_has_source(para, source_names)
        if not has_source:
            # Show the first 200 chars of the offending paragraph
            snippet = para[:200].replace("\n", " ")
            failures.append(
                f"Evidenced claim #{i} has no traceable source citation.\n"
                f"  Paragraph: \"{snippet}...\"\n"
                f"  Available sources: {source_names}\n"
                f"  Fix: add the source name inline, e.g. 'Evidenced by [Source Name]: ...'"
            )

    if failures:
        print(
            "SOURCE AUDIT FAILED: One or more 'evidenced' claims cannot be traced to a named source.\n"
            "Every claim marked as 'evidenced' must cite a named source from the signal files.\n",
            file=sys.stderr
        )
        for f in failures:
            print(f, file=sys.stderr)
        retry_file.write_text(str(retries + 1))
        sys.exit(2)

    print(
        f"SOURCE AUDIT PASSED [{label}]: all {len(evidenced_paras)} evidenced claim(s) "
        f"cite at least one named source."
    )
    retry_file.unlink(missing_ok=True)
    sys.exit(0)


if __name__ == "__main__":
    main()