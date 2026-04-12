# tests/test_export_pptx.py
"""Tests for export_pptx.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import pytest
from pptx import Presentation
from pptx.presentation import Presentation as PresentationClass
from report_builder import build, RegionEntry
import export_pptx as ep


def _region_with_all_bullets() -> RegionEntry:
    """Minimal RegionEntry with populated bullets so build_region renders all 5 labels."""
    return RegionEntry(
        name="APAC",
        status="escalated",
        admiralty="B2",
        velocity="stable",
        severity="HIGH",
        scenario_match="System intrusion",
        dominant_pillar="GEO",
        signal_type="cyber",
        confidence_label="High",
        threat_characterisation="State-directed threat",
        top_sources=["Reuters"],
        why_text="why",
        how_text="how",
        so_what_text="so what",
        threat_actor="APT-Test",
        signal_type_label="Confirmed Incident",
        intel_bullets=["intel finding alpha"],
        adversary_bullets=["adversary activity bravo"],
        impact_bullets=["impact for aerogrid charlie"],
        watch_bullets=["watch item delta"],
        action_bullets=["recommended action echo"],
        source_quality=None,
    )


def test_build_pptx_returns_presentation(mock_output, tmp_path):
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    assert isinstance(prs, PresentationClass)


def test_pptx_slide_count_matches_structure(mock_output, tmp_path):
    """Cover + Exec Summary + 2 escalated regions + Appendix = 5 slides."""
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    assert len(prs.slides) == 5


def test_pptx_saves_to_file(mock_output, tmp_path):
    data = build(output_dir=str(mock_output))
    out = str(tmp_path / "test_report.pptx")
    ep.export(output_path=out, output_dir=str(mock_output))
    assert os.path.exists(out)
    assert os.path.getsize(out) > 10_000  # non-trivial file


def test_pptx_cover_slide_has_title(mock_output):
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    cover = prs.slides[0]
    title_texts = [shape.text for shape in cover.shapes if shape.has_text_frame]
    assert any("Global Cyber Risk" in t for t in title_texts)


def test_pptx_region_slides_contain_confidence(mock_output):
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    # Slides: 0=cover, 1=exec summary, 2=APAC, 3=AME, 4=appendix
    apac_slide = prs.slides[2]
    all_text = " ".join(
        shape.text for shape in apac_slide.shapes if shape.has_text_frame
    )
    assert "Confidence:" in all_text  # CISO layout sub-header shows confidence
    assert "B2" not in all_text       # admiralty must not appear in new layout


def test_pptx_cover_no_vacr(mock_output):
    """Cover slide must not contain VaCR dollar amount or label."""
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    cover = prs.slides[0]
    all_text = " ".join(shape.text for shape in cover.shapes if shape.has_text_frame)
    assert "VaCR" not in all_text
    assert "TOTAL VALUE AT CYBER RISK" not in all_text


def test_pptx_exec_summary_no_vacr_column(mock_output):
    """Exec summary slide must not contain VaCR column header or badge."""
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    exec_slide = prs.slides[1]
    all_text = " ".join(shape.text for shape in exec_slide.shapes if shape.has_text_frame)
    assert "VaCR" not in all_text
    assert "TOTAL VaCR" not in all_text


def test_pptx_region_slide_uses_new_intel_layout():
    """build_region renders all 5 intelligence row labels when bullets are populated."""
    prs = Presentation()
    ep.build_region(prs, _region_with_all_bullets())
    slide = prs.slides[0]
    all_text = " ".join(shape.text for shape in slide.shapes if shape.has_text_frame)
    assert "INTEL FINDINGS" in all_text
    assert "ADVERSARY ACTIVITY" in all_text
    assert "IMPACT FOR AEROGRID" in all_text
    assert "WATCH FOR" in all_text
    assert "RECOMMENDED ACTION" in all_text
