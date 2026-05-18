"""validate_brief.py — site-name discipline + personnel match + cyber content check."""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


GOOD_BRIEF = """AEROWIND // MED DAILY // 2026-05-17Z
PULSE: 6.2 | ADM: B2 | NEW: 1 EVT · 0 HOT · 1 CYB

█ SITUATION
Quiet day.

█ AEROWIND EXPOSURE
▪ Palermo [CROWN_JEWEL · 120 personnel, 8 expat]
   └─ No new events within radius this period.

█ PHYSICAL & GEOPOLITICAL — LAST 24H
No new events.

█ CYBER — ACTIVE EXPOSURE
THREATS ACTIVE: MEDUSA · Sandworm + 3 others (full list watched)

- [OT/ICS] [MED · sev 3 · Probable] MEDUSA ransomware group claimed responsibility for Italian energy firm breach affecting 2 substations in Sicily. [1]

█ EARLY WARNING — NEW
No new anomalies.

█ WATCH — NEXT 72H
- No new physical or operational watch items for the next 72 hours.

█ APPENDIX — SOURCES
[1] MEDUSA ransomware group claimed Italian energy firm breach. — seerist:cyber:med-001 (Seerist analysis)
"""


def _write_pair(tmp_path: Path, brief_text: str) -> tuple[Path, Path]:
    brief = tmp_path / "brief.md"
    brief.write_text(brief_text, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "region": "MED",
        "cadence": "daily",
        "site_registry": [
            {"site_id": "med-pal", "name": "Palermo",
             "personnel_count": 120, "expat_count": 8, "criticality": "crown_jewel"},
            {"site_id": "med-mal", "name": "Malaga",
             "personnel_count": 85, "expat_count": 4, "criticality": "tier_one"},
            {"site_id": "med-cas", "name": "Casablanca",
             "personnel_count": 40, "expat_count": 2, "criticality": "tier_two"},
        ],
    }))
    return brief, manifest


def _run_validate(brief: Path, manifest: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "tools/validate_brief.py", str(brief), str(manifest)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_clean_brief_passes(tmp_path):
    brief, manifest = _write_pair(tmp_path, GOOD_BRIEF)
    r = _run_validate(brief, manifest)
    assert r.returncode == 0, r.stderr


def test_out_of_registry_site_rejected(tmp_path):
    bad = GOOD_BRIEF.replace("Palermo", "Genoa")
    brief, manifest = _write_pair(tmp_path, bad)
    r = _run_validate(brief, manifest)
    assert r.returncode != 0
    assert "Genoa" in r.stderr


def test_personnel_mismatch_rejected(tmp_path):
    bad = GOOD_BRIEF.replace("120 personnel, 8 expat", "200 personnel, 8 expat")
    brief, manifest = _write_pair(tmp_path, bad)
    r = _run_validate(brief, manifest)
    assert r.returncode != 0
    assert "personnel" in r.stderr.lower()


def test_empty_cyber_section_rejected(tmp_path):
    bad = GOOD_BRIEF.replace(
        "THREATS ACTIVE: MEDUSA · Sandworm + 3 others (full list watched)\n\n"
        "- [OT/ICS] [MED · sev 3 · Probable] MEDUSA ransomware group claimed responsibility for Italian energy firm breach affecting 2 substations in Sicily. [1]",
        "",
    )
    # Also drop the now-orphan appendix entry so the failure is the cyber check
    bad = bad.replace(
        "[1] MEDUSA ransomware group claimed Italian energy firm breach. — seerist:cyber:med-001 (Seerist analysis)\n",
        "No sources cited this window.\n",
    )
    brief, manifest = _write_pair(tmp_path, bad)
    r = _run_validate(brief, manifest)
    assert r.returncode != 0
    assert "cyber" in r.stderr.lower()


def test_missing_section_header_rejected(tmp_path):
    bad = GOOD_BRIEF.replace("█ WATCH — NEXT 72H\n", "")
    brief, manifest = _write_pair(tmp_path, bad)
    r = _run_validate(brief, manifest)
    assert r.returncode != 0
    assert "watch" in r.stderr.lower()


def test_missing_appendix_rejected(tmp_path):
    bad = GOOD_BRIEF.replace("█ APPENDIX — SOURCES\n", "").replace(
        "[1] MEDUSA ransomware group claimed Italian energy firm breach. — seerist:cyber:med-001 (Seerist analysis)\n",
        "",
    )
    brief, manifest = _write_pair(tmp_path, bad)
    r = _run_validate(brief, manifest)
    assert r.returncode != 0
    assert "appendix" in r.stderr.lower()


def test_orphan_body_cite_rejected(tmp_path):
    """Body cites [7] but APPENDIX only has [1] — bijection fails."""
    bad = GOOD_BRIEF.replace("Sicily. [1]", "Sicily. [7]")
    brief, manifest = _write_pair(tmp_path, bad)
    r = _run_validate(brief, manifest)
    assert r.returncode != 0
    assert "[7]" in r.stderr or "appendix" in r.stderr.lower()


def test_unused_appendix_entry_rejected(tmp_path):
    """APPENDIX has [1] and [2] but body only cites [1] — bijection fails."""
    bad = GOOD_BRIEF.replace(
        "[1] MEDUSA ransomware group claimed Italian energy firm breach. — seerist:cyber:med-001 (Seerist analysis)\n",
        "[1] MEDUSA ransomware group claimed Italian energy firm breach. — seerist:cyber:med-001 (Seerist analysis)\n"
        "[2] Stale unused entry — seerist:cyber:med-002 (Seerist analysis)\n",
    )
    brief, manifest = _write_pair(tmp_path, bad)
    r = _run_validate(brief, manifest)
    assert r.returncode != 0
    assert "[2]" in r.stderr or "cited" in r.stderr.lower()


def test_reply_taxonomy_in_body_rejected(tmp_path):
    bad = GOOD_BRIEF.replace(
        "█ WATCH — NEXT 72H\n- No new physical or operational watch items for the next 72 hours.",
        "█ WATCH — NEXT 72H\n- No new physical or operational watch items for the next 72 hours.\nReply: USEFUL · NOISE · MISSED CONTEXT · FALSE POSITIVE",
    )
    brief, manifest = _write_pair(tmp_path, bad)
    r = _run_validate(brief, manifest)
    assert r.returncode != 0
    assert "reply taxonomy" in r.stderr.lower()


_APPENDIX_QUIET = (
    "\n█ APPENDIX — SOURCES\n"
    "No sources cited this window.\n"
)
_APPENDIX_TWO_PHYS_CYB = (
    "\n█ APPENDIX — SOURCES\n"
    "[1] Port strike disrupts inbound shipments. — seerist:verified:med-001 (Seerist verified event)\n"
    "[2] MEDUSA wind-sector campaign. — seerist:cyber:med-011 (Seerist analysis)\n"
)


def test_clean_site_one_liner_format_accepted(tmp_path):
    """v1.1 formatter produces `▪ Name [CRIT · Np / N expat(s)] — clean. prose`.
    Validator must accept this format and still enforce personnel/expat counts."""
    v11_brief = """AEROWIND // MED DAILY // 2026-05-17Z
PULSE: 6.2 | ADM: B2 | NEW: 0 EVT · 0 HOT · 0 CYB

█ SITUATION
Quiet day across MED.

█ AEROWIND EXPOSURE
▪ Palermo [CROWN JEWEL · 120p / 8 expats] — clean. No events within radius this period.
▪ Malaga [TIER ONE · 85p / 4 expats] — clean. Routine posture.
▪ Casablanca [TIER TWO · 40p / 2 expats] — clean. No activity.

█ PHYSICAL & GEOPOLITICAL — LAST 24H
No new events.

█ CYBER — ACTIVE EXPOSURE
THREATS ACTIVE: Sandworm · APT28 + 0 others (full list watched)

No new sector or facility-bound cyber findings this window.

█ EARLY WARNING — NEW
No new anomalies.

█ WATCH — NEXT 72H
Routine posture. No action required today.
""" + _APPENDIX_QUIET
    brief, manifest = _write_pair(tmp_path, v11_brief)
    r = _run_validate(brief, manifest)
    assert r.returncode == 0, r.stderr


def test_aerowind_exposure_with_cyber_subrow_accepted(tmp_path):
    """Format D: site has both physical and facility-bound cyber sub-rows."""
    brief_text = """AEROWIND // MED DAILY // 2026-05-17Z
PULSE: 6.2 | ADM: B2 | NEW: 1 EVT · 0 HOT · 2 CYB

█ SITUATION
Port disruption and facility-targeted cyber activity detected near Palermo.

█ AEROWIND EXPOSURE
▪ Palermo [CROWN_JEWEL · 120 personnel, 8 expat]
   ├─ Physical: Port strike blocks inbound blade shipments — 24-48h delay. [1]
   └─ Cyber: OT network scanning detected from external IP cluster; no confirmed intrusion. [2]

█ PHYSICAL & GEOPOLITICAL — LAST 24H
- [MED · sev 3 · Confirmed] Port of Palermo worker strike enters day two — inbound cargo delayed. [1]

█ CYBER — ACTIVE EXPOSURE
THREATS ACTIVE: MEDUSA · Sandworm · APT28 + 2 others (full list watched)

- [OT/ICS] [HIGH · sev 4 · Probable] MEDUSA campaign targeting wind-sector SCADA networks. [2]

█ EARLY WARNING — NEW
No new anomalies.

█ WATCH — NEXT 72H
1. Confirm patch posture on Palermo OT systems with site IT lead by EOD.
2. Verify Palermo port reopening window — first ship cleared at 06:00 local.
""" + _APPENDIX_TWO_PHYS_CYB
    brief, manifest = _write_pair(tmp_path, brief_text)
    r = _run_validate(brief, manifest)
    assert r.returncode == 0, r.stderr


def test_cyber_section_with_threats_active_strip_accepted(tmp_path):
    """CYBER section with only THREATS ACTIVE strip + fallback sentinel passes validator."""
    brief_text = """AEROWIND // MED DAILY // 2026-05-17Z
PULSE: 6.2 | ADM: B2 | NEW: 0 EVT · 0 HOT · 0 CYB

█ SITUATION
Quiet day across MED.

█ AEROWIND EXPOSURE
▪ Palermo [CROWN_JEWEL · 120 personnel, 8 expat]
   └─ No new events within radius this period.

█ PHYSICAL & GEOPOLITICAL — LAST 24H
No new events.

█ CYBER — ACTIVE EXPOSURE
THREATS ACTIVE: Sandworm · MuddyWater · MEDUSA · OilRig + 2 others (full list watched)

No new sector or facility-bound cyber findings this window.

█ EARLY WARNING — NEW
No new anomalies.

█ WATCH — NEXT 72H
1. No operator action required for the next 24h.
""" + _APPENDIX_QUIET
    brief, manifest = _write_pair(tmp_path, brief_text)
    r = _run_validate(brief, manifest)
    assert r.returncode == 0, r.stderr
