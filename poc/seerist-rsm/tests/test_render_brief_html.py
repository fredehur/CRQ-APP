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

- [OT/ICS] [MED · sev 3 · Probable] MEDUSA ransomware group claimed responsibility for Italian energy firm breach affecting 2 substations in Sicily. [1]

█ EARLY WARNING — NEW
No new anomalies.

█ WATCH — NEXT 72H
- Italian spring labour calendar active — Palermo–Hamburg tower-segment corridor potentially exposed.

█ APPENDIX — SOURCES
[1] MEDUSA ransomware group claimed responsibility for Italian energy firm breach. — seerist:cyber:med-001 (Seerist analysis)
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
                   "EARLY WARNING", "WATCH",
                   "APPENDIX"]:
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
- [CRITICAL · sev 6 · Confirmed] Bomb threat at Palermo port — facility within 5 km. [1]

█ AEROWIND EXPOSURE
▪ Palermo [CROWN_JEWEL · 120 personnel, 8 expat]
   └─ Consequence: Evacuation protocol activated.

█ CYBER — ACTIVE EXPOSURE
THREATS ACTIVE: none

- [OT/ICS] [LOW · sev 1 · Possible] No new signals this window. [2]

█ EARLY WARNING — NEW
No new anomalies.

█ WATCH — NEXT 72H
Monitor port situation.

█ APPENDIX — SOURCES
[1] Bomb threat at Palermo port. — seerist:verified:med-001 (Seerist verified event)
[2] Quiet cyber window. — seerist:cyber:med-001 (Seerist analysis)
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

- [OT/ICS] [MED · sev 3 · Probable] ICS breach pattern confirmed against European energy. [1]

█ EARLY WARNING — NEW
No new anomalies.

█ WATCH — NEXT 72H
Watch ICS exposure.

█ APPENDIX — SOURCES
[1] ICS breach pattern confirmed against European energy. — seerist:cyber:med-002 (Seerist analysis)
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
    # Match the OT/ICS-specific chip text color (#1e40af) to disambiguate from
    # the EVT stat-strip chip which also uses #dbeafe background.
    assert "color:#1e40af" in html, "OT/ICS chip text color not found in rendered HTML"
    assert "OT/ICS" in html, "OT/ICS surface tag text not found in rendered HTML"
    # Plain bracketed `[OT/ICS]` must NOT survive — it should have been wrapped in a chip span.
    assert "[OT/ICS]" not in html, "surface tag should be wrapped in chip, not plain text"


def test_body_citation_becomes_superscript_anchor(tmp_path):
    """A body `[1]` cite renders as a superscript link to `#ref-1`."""
    brief = tmp_path / "brief.md"
    brief.write_text(OT_ICS_BRIEF, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "region": "MED",
        "cadence": "daily",
        "site_registry": [{"site_id": "med-pal", "name": "Palermo"}],
    }))

    html = render_brief_html.render(brief, manifest, subject="TEST")
    # Superscript span wraps the linked citation number
    assert "<sup" in html, "no <sup> wrapper for body cite"
    assert 'href="#ref-1"' in html, "body cite should link to #ref-1"


def test_appendix_entries_have_anchor_ids(tmp_path):
    """Each `[N] ...` entry in APPENDIX renders with `id=\"ref-N\"` so body
    cites can jump to it via the anchor."""
    brief = tmp_path / "brief.md"
    brief.write_text(CRITICAL_BRIEF, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "region": "MED",
        "cadence": "daily",
        "site_registry": [{"site_id": "med-pal", "name": "Palermo"}],
    }))

    html = render_brief_html.render(brief, manifest, subject="TEST")
    assert 'id="ref-1"' in html, "appendix entry [1] missing anchor id"
    assert 'id="ref-2"' in html, "appendix entry [2] missing anchor id"
    # The entry text itself comes through
    assert "Bomb threat at Palermo port" in html


def test_multi_cite_renders_two_linked_numbers(tmp_path):
    """`[1, 2]` in body renders as two anchored numbers inside one <sup>."""
    brief_text = CRITICAL_BRIEF.replace("[1]", "[1, 2]")
    brief = tmp_path / "brief.md"
    brief.write_text(brief_text, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "region": "MED",
        "cadence": "daily",
        "site_registry": [{"site_id": "med-pal", "name": "Palermo"}],
    }))

    html = render_brief_html.render(brief, manifest, subject="TEST")
    assert 'href="#ref-1"' in html and 'href="#ref-2"' in html
    # Both anchors should appear inside the same superscript wrapper somewhere
    assert "<sup" in html
