"""Each new stop-hook check is a callable function exit-coded 0 (pass) or 2 (fail)."""
import importlib.util
import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / ".claude" / "hooks" / "validators" / "rsm-brief-context-checks.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("rsm_brief_context_checks", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GOOD_WEEKLY = """AEROWIND // MED INTSUM // WK15-2026
PERIOD: 2026-04-07 – 2026-04-14 | PRIORITY SCENARIO: Port disruption #2 | PULSE: 3.0→2.6 (-0.4) | ADM: B2

█ SITUATION
DEVELOPING: Port of Casablanca closure widening.
Labour unrest near Casablanca operations escalated this week.

█ AEROWIND EXPOSURE
▪ Casablanca Wind Farm Operations [MAJOR · 47 personnel, 8 expat]
   ├─ Strike action, Port of Casablanca — 3km, severity HIGH, ✓ verified, 4 sources
   └─ Consequence: Inbound nacelle shipments delayed; downstream site in NCE at risk.

█ PHYSICAL & GEOPOLITICAL
▪ [Labour][HIGH] Port of Casablanca — Strike action.

█ CYBER
No new signals.

█ EARLY WARNING (PRE-MEDIA)
▪ ⚡ Casablanca outskirts — labour unrest. Score 0.91. 48hr watch.

█ ASSESSMENT
Evidenced: confirmed strike at Port of Casablanca. Assessed: 4-6 day disruption window probable.

█ WATCH LIST — WK16
▪ Port reopening timing — escalation if closure exceeds 5 days.
▪ Spread to other Moroccan ports — escalation if Tangier or Agadir sees sympathy action.
▪ Customer ONEE Morocco PPA exposure.

REFERENCES
[1] Morocco Q2 2026 outlook — Seerist 2026-04-10

---
Reply: ACCURATE · OVERSTATED · UNDERSTATED · FALSE POSITIVE | AeroGrid Intelligence // MED RSM
"""


@pytest.fixture
def good_brief(tmp_path):
    p = tmp_path / "rsm_brief_med_2026-04-14.md"
    p.write_text(GOOD_WEEKLY, encoding="utf-8")
    return p


def _allowed_med():
    return ["Casablanca Wind Farm Operations", "Palermo Offshore Ops", "Malaga Service Hub"]


def _med_personnel():
    return {
        "Casablanca Wind Farm Operations": {"personnel": 47, "expat": 8},
        "Palermo Offshore Ops": {"personnel": 210, "expat": 14},
        "Malaga Service Hub": {"personnel": 18, "expat": 1},
    }


def test_good_weekly_passes_all_checks(good_brief):
    mod = _load_module()
    failures = mod.run_all_checks(
        good_brief, region="MED",
        allowed_sites=_allowed_med(),
        site_personnel=_med_personnel(),
        cadence="weekly",
        scribe_texts=[],
    )
    assert failures == [], f"unexpected failures: {failures}"


def test_invented_site_name_fails(good_brief):
    mod = _load_module()
    text = good_brief.read_text(encoding="utf-8") + "\n▪ Marseille Distribution Center [STANDARD · 30 personnel]\n"
    good_brief.write_text(text, encoding="utf-8")
    failures = mod.run_all_checks(
        good_brief, region="MED",
        allowed_sites=_allowed_med(),
        site_personnel=_med_personnel(),
        cadence="weekly",
        scribe_texts=[],
    )
    assert any("site name" in f.lower() for f in failures)


def test_wrong_personnel_count_fails(good_brief):
    mod = _load_module()
    text = good_brief.read_text(encoding="utf-8").replace(
        "47 personnel, 8 expat", "320 personnel, 18 expat"
    )
    good_brief.write_text(text, encoding="utf-8")
    failures = mod.run_all_checks(
        good_brief, region="MED",
        allowed_sites=_allowed_med(),
        site_personnel=_med_personnel(),
        cadence="weekly",
        scribe_texts=[],
    )
    assert any("personnel" in f.lower() for f in failures)


def test_cross_region_body_fails(good_brief):
    mod = _load_module()
    text = good_brief.read_text(encoding="utf-8").replace(
        "downstream site in NCE", "downstream site Hamburg Manufacturing Hub"
    )
    good_brief.write_text(text, encoding="utf-8")
    failures = mod.run_all_checks(
        good_brief, region="MED",
        allowed_sites=_allowed_med(),
        site_personnel=_med_personnel(),
        cadence="weekly",
        scribe_texts=[],
    )
    assert any("site name" in f.lower() for f in failures)


def test_quoted_scribe_fails(good_brief):
    mod = _load_module()
    scribe = "Casablanca port action follows the same pattern as the Feb 2025 strike — expect 4-6 day disruption window if previous trajectory holds."
    text = good_brief.read_text(encoding="utf-8").replace(
        "Evidenced: confirmed strike at Port of Casablanca. Assessed: 4-6 day disruption window probable.",
        scribe
    )
    good_brief.write_text(text, encoding="utf-8")
    failures = mod.run_all_checks(
        good_brief, region="MED",
        allowed_sites=_allowed_med(),
        site_personnel=_med_personnel(),
        cadence="weekly",
        scribe_texts=[scribe],
    )
    assert any("scribe" in f.lower() for f in failures)


def test_daily_with_assessment_section_fails(tmp_path):
    mod = _load_module()
    daily_with_assessment = """AEROWIND // MED DAILY // 2026-04-14Z
PULSE: 2.6 (▼ 0.6) | ADM: B2 | NEW: 1 EVT · 0 HOT · 0 CYB

█ SITUATION
Labour action escalating.

█ AEROWIND EXPOSURE
▪ Casablanca Wind Farm Operations [MAJOR · 47 personnel, 8 expat]
   └─ Consequence: Inbound shipments delayed.

█ ASSESSMENT
This is a long-form weekly assessment that should not appear in daily.

---
Reply: ACKNOWLEDGED | AeroGrid Intelligence // MED RSM
"""
    p = tmp_path / "rsm_daily_med_2026-04-14.md"
    p.write_text(daily_with_assessment, encoding="utf-8")
    failures = mod.run_all_checks(
        p, region="MED",
        allowed_sites=_allowed_med(),
        site_personnel=_med_personnel(),
        cadence="daily",
        scribe_texts=[],
    )
    assert any("cadence" in f.lower() for f in failures)


def test_long_consequence_fails(good_brief):
    mod = _load_module()
    long_conseq = "Consequence: " + " ".join([
        "This is sentence one and it is quite long.",
        "This is sentence two adding more detail.",
        "This is sentence three pushing past the cap.",
    ])
    text = good_brief.read_text(encoding="utf-8").replace(
        "Consequence: Inbound nacelle shipments delayed; downstream site in NCE at risk.",
        long_conseq
    )
    good_brief.write_text(text, encoding="utf-8")
    failures = mod.run_all_checks(
        good_brief, region="MED",
        allowed_sites=_allowed_med(),
        site_personnel=_med_personnel(),
        cadence="weekly",
        scribe_texts=[],
    )
    assert any("consequence" in f.lower() for f in failures)
