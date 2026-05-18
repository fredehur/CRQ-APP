"""normalize_citations.py — claim_id → [N] renumbering + APPENDIX synthesis."""
import json
from pathlib import Path

import pytest

from tools import normalize_citations
from tools.normalize_citations import NormalizationError, normalize


def _claims(*entries: dict) -> dict[str, dict]:
    return {c["claim_id"]: c for c in entries}


SINGLE_CITE_BRIEF = """AEROWIND // MED DAILY // 2026-05-17Z
PULSE: 6.2 | ADM: B2 | NEW: 1 EVT · 0 HOT · 0 CYB

█ SITUATION
Quiet day.

█ AEROWIND EXPOSURE
▪ Palermo [CROWN_JEWEL · 120 personnel, 8 expat]
   └─ Port disruption continues. [med-001]

█ PHYSICAL & GEOPOLITICAL — LAST 24H
- [MED · sev 3 · Confirmed] Port of Palermo strike enters day two. [med-001]

█ CYBER — ACTIVE EXPOSURE
THREATS ACTIVE: none

No new cyber findings.

█ EARLY WARNING — NEW
No new anomalies.

█ WATCH — NEXT 72H
- Watch port reopening window.
"""


def test_single_claim_renumbered_and_appendix_synthesized():
    claims = _claims({
        "claim_id": "med-001",
        "text": "Port of Palermo worker strike enters day two; inbound cargo delayed.",
        "signal_ids": ["seerist:verified:med-001"],
    })
    out = normalize(SINGLE_CITE_BRIEF, claims)
    # Split off appendix; body should contain exactly 2 cites of [1]
    body, _appendix = out.split("█ APPENDIX — SOURCES", 1)
    assert body.count("[1]") == 2, f"expected 2 cites of [1] in body, saw:\n{body}"
    assert "[med-001]" not in out, "claim_id should be replaced by number"
    # APPENDIX synthesized with the claim
    assert "█ APPENDIX — SOURCES" in out
    assert "[1] Port of Palermo worker strike" in out
    assert "seerist:verified:med-001" in out
    assert "(Seerist verified event)" in out


def test_multi_cite_bracket_renumbered_inline():
    brief = SINGLE_CITE_BRIEF.replace("[med-001]", "[med-001, med-002]")
    claims = _claims(
        {"claim_id": "med-001", "text": "Strike day two.", "signal_ids": ["seerist:verified:med-001"]},
        {"claim_id": "med-002", "text": "Inbound cargo delayed 24-48h.", "signal_ids": ["seerist:verified:med-002"]},
    )
    out = normalize(brief, claims)
    assert "[1, 2]" in out, f"multi-cite should compress to [1, 2]:\n{out}"
    # Two appendix entries
    assert "[1]" in out and "[2]" in out
    assert "[1] Strike day two." in out
    assert "[2] Inbound cargo delayed" in out


def test_repeated_claim_id_gets_same_number():
    brief = """AEROWIND // MED DAILY // 2026-05-17Z
PULSE: 6.2 | ADM: B2 | NEW: 1 EVT · 0 HOT · 0 CYB

█ SITUATION
Two bullets cite the same claim.

█ AEROWIND EXPOSURE
▪ Palermo [CROWN_JEWEL · 120 personnel, 8 expat]
   └─ See [med-001]. Same source again: [med-001].

█ PHYSICAL & GEOPOLITICAL — LAST 24H
- [MED · sev 3 · Confirmed] Strike. [med-001]

█ CYBER — ACTIVE EXPOSURE
THREATS ACTIVE: none

No new cyber findings.

█ EARLY WARNING — NEW
No new anomalies.

█ WATCH — NEXT 72H
- Watch.
"""
    claims = _claims({"claim_id": "med-001", "text": "Strike.", "signal_ids": ["seerist:verified:med-001"]})
    out = normalize(brief, claims)
    # All three body cites should be [1] — appendix has only one entry
    body, appendix = out.split("█ APPENDIX — SOURCES")
    assert body.count("[1]") == 3
    assert appendix.count("\n[1]") == 1 or appendix.startswith("\n[1]")


def test_non_citation_brackets_are_left_alone():
    """Severity bands, surface chips, and site row meta must not be rewritten."""
    claims = _claims({"claim_id": "med-001", "text": "Strike.", "signal_ids": ["seerist:verified:med-001"]})
    out = normalize(SINGLE_CITE_BRIEF, claims)
    # These should survive the rewrite untouched
    assert "[CROWN_JEWEL · 120 personnel, 8 expat]" in out
    assert "[MED · sev 3 · Confirmed]" in out


def test_unknown_claim_id_raises():
    brief = SINGLE_CITE_BRIEF.replace("[med-001]", "[med-phantom]")
    claims = _claims({"claim_id": "med-001", "text": "x", "signal_ids": ["seerist:verified:med-001"]})
    with pytest.raises(NormalizationError, match="med-phantom"):
        normalize(brief, claims)


def test_idempotent_on_already_normalized_brief():
    """Running normalize twice should be a no-op — second call returns input."""
    claims = _claims({"claim_id": "med-001", "text": "Strike.", "signal_ids": ["seerist:verified:med-001"]})
    once = normalize(SINGLE_CITE_BRIEF, claims)
    twice = normalize(once, claims)
    assert once == twice


def test_no_cites_in_body_produces_empty_appendix_sentinel():
    quiet_brief = """AEROWIND // MED DAILY // 2026-05-17Z
PULSE: 6.2 | ADM: B2 | NEW: 0 EVT · 0 HOT · 0 CYB

█ SITUATION
Nothing to report.

█ AEROWIND EXPOSURE
▪ Palermo [CROWN_JEWEL · 120 personnel, 8 expat] — clean. No events within radius.

█ PHYSICAL & GEOPOLITICAL — LAST 24H
No new events.

█ CYBER — ACTIVE EXPOSURE
THREATS ACTIVE: none

No new findings.

█ EARLY WARNING — NEW
No new anomalies.

█ WATCH — NEXT 72H
- Routine posture.
"""
    out = normalize(quiet_brief, {})
    assert "█ APPENDIX — SOURCES" in out
    assert "No sources cited this window." in out


def test_source_type_label_derivation():
    """Each signal_id prefix maps to a human label in the appendix entry."""
    fixtures = [
        ("seerist:cyber:med-0", "Seerist analysis"),
        ("seerist:verified:med-1", "Seerist verified event"),
        ("seerist:hotspot:med-2", "Seerist hotspot"),
        ("seerist:events_ai:med-3", "Seerist AI event"),
        ("osint:rss:med-4", "OSINT"),
    ]
    for sig, label in fixtures:
        brief = SINGLE_CITE_BRIEF
        claims = _claims({"claim_id": "med-001", "text": "x", "signal_ids": [sig]})
        out = normalize(brief, claims)
        assert label in out, f"expected label {label!r} for signal {sig!r} in:\n{out}"


def test_multiple_signal_ids_per_claim_joined():
    """When a claim has multiple signal_ids, the appendix joins them with '; '."""
    claims = _claims({
        "claim_id": "med-001",
        "text": "Nakba Day rallies in 12 cities.",
        "signal_ids": ["seerist:verified:med-014", "seerist:verified:med-015", "seerist:verified:med-016"],
    })
    out = normalize(SINGLE_CITE_BRIEF, claims)
    assert "seerist:verified:med-014; seerist:verified:med-015; seerist:verified:med-016" in out
