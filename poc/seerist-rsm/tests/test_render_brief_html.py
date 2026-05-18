"""HTML brief renderer — section parsing + site-name discipline."""
import json
from pathlib import Path

from tools import render_brief_html


SAMPLE_BRIEF = """AEROWIND // MED DAILY // 2026-05-17Z
PULSE: 6.2 (▲ +0.3) | ADM: B2 | NEW: 3 EVT · 1 HOT · 1 CYB

█ SITUATION
Quiet night across MED with one new incident near Palermo.

█ AEROWIND EXPOSURE
▪ Palermo [CROWN_JEWEL · 120 personnel, 8 expat]
   ├─ Port strike escalates — 2.1km, severity MED, , 4 sources
   └─ Consequence: Inbound shipments delayed 24-48h.

█ PHYSICAL & GEOPOLITICAL — LAST 24H
▪ [UNREST][MED] Palermo — Port strike escalates.

█ CYBER — ACTIVE EXPOSURE
THREATS ACTIVE: MEDUSA · Sandworm + 3 others (full list watched)

- [OT/ICS] [MED · sev 3 · Probable] MEDUSA ransomware group claimed responsibility for Italian energy firm breach affecting 2 substations in Sicily. [med-cyb-001]

█ EARLY WARNING — NEW
No new anomalies.

█ WATCH — NEXT 72H
- Italian spring labour calendar active — Palermo–Hamburg tower-segment corridor potentially exposed.
"""


def test_render_returns_html_with_all_section_headers(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text(SAMPLE_BRIEF, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "region": "MED",
        "cadence": "daily",
        "site_registry": [
            {"site_id": "med-pal", "name": "Palermo"},
            {"site_id": "med-mal", "name": "Malaga"},
            {"site_id": "med-cas", "name": "Casablanca"},
        ],
    }))

    html = render_brief_html.render(brief, manifest, subject="TEST")

    for header in ["SITUATION", "AEROWIND EXPOSURE",
                   "PHYSICAL &amp; GEOPOLITICAL",
                   "EARLY WARNING", "WATCH"]:
        assert header in html, f"missing section header: {header}"
    # CYBER section always renders as a full block with heading
    assert "CYBER — ACTIVE EXPOSURE" in html, "missing CYBER — ACTIVE EXPOSURE section heading"
    assert "Palermo" in html
    assert "<html" in html


def test_render_rejects_out_of_registry_site_name(tmp_path):
    """If the brief mentions a site name not in the manifest's site_registry,
    render() raises a ValueError — anti-hallucination guard at render time."""
    brief = tmp_path / "brief.md"
    bad_brief = SAMPLE_BRIEF.replace("Palermo", "Genoa")  # Genoa not in MED registry
    brief.write_text(bad_brief, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "region": "MED",
        "cadence": "daily",
        "site_registry": [
            {"site_id": "med-pal", "name": "Palermo"},
            {"site_id": "med-mal", "name": "Malaga"},
            {"site_id": "med-cas", "name": "Casablanca"},
        ],
    }))

    import pytest
    with pytest.raises(ValueError, match="Genoa"):
        render_brief_html.render(brief, manifest, subject="TEST")


def test_render_extracts_pulse_admiralty_counters_from_strip(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text(SAMPLE_BRIEF, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "region": "MED",
        "cadence": "daily",
        "site_registry": [{"site_id": "med-pal", "name": "Palermo"}],
    }))

    html = render_brief_html.render(brief, manifest, subject="TEST")
    assert "6.2" in html and "▲ +0.3" in html
    assert "B2" in html
    assert "3 EVT" in html and "1 HOT" in html and "1 CYB" in html


CRITICAL_BRIEF = """AEROWIND // MED DAILY // 2026-05-17Z
PULSE: elevated-watch | ADM: B2 | NEW: 1 EVT · 0 HOT · 0 CYB

█ SITUATION
Overview line.

█ PHYSICAL & GEOPOLITICAL — LAST 24H
- [CRITICAL · sev 6 · Confirmed] Bomb threat at Palermo port — facility within 5 km. [med-crit-001]

█ AEROWIND EXPOSURE
▪ Palermo [CROWN_JEWEL · 120 personnel, 8 expat]
   └─ Consequence: Evacuation protocol activated.

█ CYBER — ACTIVE EXPOSURE
THREATS ACTIVE: none

- [OT/ICS] [LOW · sev 1 · Possible] No new signals this window. [med-cyb-001]

█ EARLY WARNING — NEW
No new anomalies.

█ WATCH — NEXT 72H
Monitor port situation.
"""

OT_ICS_BRIEF = """AEROWIND // MED DAILY // 2026-05-17Z
PULSE: elevated-watch | ADM: B2 | NEW: 0 EVT · 0 HOT · 1 CYB

█ SITUATION
Overview line.

█ PHYSICAL & GEOPOLITICAL — LAST 24H
No new physical signals.

█ AEROWIND EXPOSURE
▪ Palermo [CROWN_JEWEL · 120 personnel, 8 expat]
   └─ Clean window.

█ CYBER — ACTIVE EXPOSURE
THREATS ACTIVE: APT28

- [OT/ICS] [MED · sev 3 · Probable] ICS breach pattern confirmed against European energy. [med-cyb-002]

█ EARLY WARNING — NEW
No new anomalies.

█ WATCH — NEXT 72H
Watch ICS exposure.
"""


def test_severity_color_applied_to_bullet_band(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text(CRITICAL_BRIEF, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "region": "MED",
        "cadence": "daily",
        "site_registry": [{"site_id": "med-pal", "name": "Palermo"}],
    }))

    html = render_brief_html.render(brief, manifest, subject="TEST")
    assert "#b91c1c" in html, "CRITICAL severity color not found in rendered HTML"
    assert "CRITICAL" in html, "CRITICAL band text not found in rendered HTML"


def test_surface_tag_chip_rendered(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text(OT_ICS_BRIEF, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "region": "MED",
        "cadence": "daily",
        "site_registry": [{"site_id": "med-pal", "name": "Palermo"}],
    }))

    html = render_brief_html.render(brief, manifest, subject="TEST")
    assert "#dbeafe" in html, "OT/ICS chip background color not found in rendered HTML"
    assert "OT/ICS" in html, "OT/ICS surface tag text not found in rendered HTML"
