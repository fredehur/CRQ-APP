# tests/test_export_pptx.py
"""Tests for export_pptx.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import pytest
from pptx import Presentation
from pptx.presentation import Presentation as PresentationClass
from report_builder import build
import export_pptx as ep


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


def test_pptx_region_slides_contain_admiralty(mock_output):
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    # Slides 2 = exec, 3 = APAC, 4 = AME, 5 = appendix
    apac_slide = prs.slides[2]
    all_text = " ".join(
        shape.text for shape in apac_slide.shapes if shape.has_text_frame
    )
    assert "B2" in all_text  # APAC admiralty
