"""Haiku per (scenario × source) — 2-sentence summary + figure extraction."""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
_MAX_RETRIES = 3
_BASE_BACKOFF_S = 1.0
_MARKDOWN_CHAR_LIMIT = 8000

_PROMPT_TEMPLATE = """\
You are summarizing a cybersecurity research source for a risk analyst.

Scenario: {scenario_name}
Analyst notes: {scenario_notes}

Read the source below and answer in EXACTLY 2 sentences:
- Sentence 1: what does this source say about the scenario?
- Sentence 2: cite any USD or % figures relevant to the scenario.

Source:
{markdown}
"""

# $123, $1.5M, $4.1 billion, $9,800,000, 68%, 12.5%
_FIGURE_RE = re.compile(
    r"(\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|trillion|M|B|K))?|\d+(?:\.\d+)?%)",
    re.IGNORECASE,
)


def extract_figures(text: str) -> list[str]:
    """Return all unique $/percent figures found in text, in order of first appearance."""
    seen: list[str] = []
    for m in _FIGURE_RE.finditer(text or ""):
        token = m.group(0).strip()
        if token and token not in seen:
            seen.append(token)
    return seen


def _trim_to_two_sentences(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=2)
    return " ".join(parts[:2]).strip()


def _is_rate_limit(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    return "rate" in name or "rate_limit" in str(exc).lower() or "429" in str(exc)


def summarize_pair(
    client: Any,
    scenario_name: str,
    scenario_notes: str,
    markdown: str,
) -> tuple[Optional[str], list[str]]:
    """Call Haiku once per (scenario × source). Returns (summary, figures).
    On unrecoverable failure: returns (None, [])."""
    prompt = _PROMPT_TEMPLATE.format(
        scenario_name=scenario_name,
        scenario_notes=scenario_notes or "(none)",
        markdown=(markdown or "")[:_MARKDOWN_CHAR_LIMIT],
    )

    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            text = (resp.content[0].text or "").strip()
            if not text:
                return None, []
            summary = _trim_to_two_sentences(text)
            figures = extract_figures(summary)
            return summary, figures
        except Exception as exc:
            last_exc = exc
            if _is_rate_limit(exc) and attempt < _MAX_RETRIES - 1:
                time.sleep(_BASE_BACKOFF_S * (2 ** attempt))
                continue
            logger.warning("[source_librarian] Haiku summarize failed: %s", exc)
            return None, []
    logger.warning("[source_librarian] Haiku exhausted retries: %s", last_exc)
    return None, []
