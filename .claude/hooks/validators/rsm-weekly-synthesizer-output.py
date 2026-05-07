"""Stop hook: validate rsm-weekly-synthesizer JSON output.

Reads the last assistant message from the transcript (path in
CLAUDE_TRANSCRIPT_PATH), extracts the JSON, validates against
WeeklySynthesisOutput, and runs the jargon filter.
Exit 0 on success; non-zero on failure with a message to stderr.
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from tools.briefs.models import WeeklySynthesisOutput


FORBIDDEN_TERMS = [
    "SOC budget", "blue-team", "red-team", "purple-team",
    "kill chain", "threat intel platform", "TIP", "KPI", "TCO",
]


def main() -> int:
    transcript_path = os.environ.get("CLAUDE_TRANSCRIPT_PATH", "")
    transcript = Path(transcript_path)
    if not transcript.exists():
        print(f"transcript not found: {transcript}", file=sys.stderr)
        return 0  # don't block the run if transcript is missing

    lines = transcript.read_text(encoding="utf-8").splitlines()
    last_text = _extract_last_assistant_text(lines)
    if last_text is None:
        print("no assistant text found in transcript", file=sys.stderr)
        return 0

    try:
        parsed = json.loads(last_text)
    except json.JSONDecodeError as e:
        print(f"output is not valid JSON: {e}", file=sys.stderr)
        return 1

    try:
        out = WeeklySynthesisOutput.model_validate(parsed)
    except Exception as e:
        print(f"output does not match WeeklySynthesisOutput schema: {e}", file=sys.stderr)
        return 1

    # Jargon filter — collect all prose fields
    prose_parts = [out.headline]
    for sn in out.sites_narrative:
        for field in ("standing_notes_synthesis", "pattern_framing", "cyber_callout_text"):
            v = getattr(sn, field)
            if v:
                prose_parts.append(v)
    if out.regional_cyber_standing_notes:
        prose_parts.append(out.regional_cyber_standing_notes)
    prose_parts.extend(out.evidence_why_lines.values())
    prose = " ".join(prose_parts)

    errors: list[str] = []
    for term in FORBIDDEN_TERMS:
        if re.search(r"\b" + re.escape(term) + r"\b", prose, re.IGNORECASE):
            errors.append(f"forbidden jargon: {term!r}")

    if errors:
        print("; ".join(errors), file=sys.stderr)
        return 1

    return 0


def _extract_last_assistant_text(lines: list[str]) -> str | None:
    for line in reversed(lines):
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("role") == "assistant":
            content = ev.get("content", "")
            if isinstance(content, list):
                text = "".join(
                    c.get("text", "") for c in content if c.get("type") == "text"
                )
            else:
                text = str(content)
            # strip code fences if present
            m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
            return m.group(1) if m else text.strip()
    return None


if __name__ == "__main__":
    raise SystemExit(main())
