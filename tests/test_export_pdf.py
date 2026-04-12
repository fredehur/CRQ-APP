# tests/test_export_pdf.py
"""Smoke tests: template renders without error and contains expected content."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import jinja2
from report_builder import build


TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "tools", "templates", "report.html.j2"
)


def _render(mock_output):
    data = build(output_dir=str(mock_output))
    loader = jinja2.FileSystemLoader(os.path.dirname(TEMPLATE_PATH))
    env = jinja2.Environment(loader=loader, autoescape=True)
    tmpl = env.get_template("report.html.j2")
    return tmpl.render(data=data)


def test_template_renders_without_error(mock_output):
    html = _render(mock_output)
    assert len(html) > 500


def test_template_contains_brand_color(mock_output):
    html = _render(mock_output)
    assert "#1e3a5f" in html


def test_template_contains_pipeline_id(mock_output):
    html = _render(mock_output)
    assert "crq-test-001" in html


def test_template_does_not_contain_vacr_ui_elements(mock_output):
    """CISO brief must not render VaCR KPI labels or columns."""
    html = _render(mock_output)
    assert "Total Value at Cyber Risk" not in html
    assert "TOTAL VaCR" not in html
    assert "VaCR Exposure" not in html
    assert ">VaCR<" not in html  # column header


def test_template_contains_escalated_regions(mock_output):
    html = _render(mock_output)
    assert "APAC" in html
    assert "AME" in html


def test_template_uses_seven_section_intel_layout(mock_output):
    """Region layout uses the 7-section intel structure (intel-section + section-heading CSS classes)."""
    html = _render(mock_output)
    assert "intel-section" in html
    assert "section-heading" in html


def test_template_confidence_label_in_table(mock_output):
    """Exec summary table must show Confidence column header."""
    html = _render(mock_output)
    assert "Confidence" in html
    assert "Admiralty" not in html   # raw Admiralty code label must not appear in CISO brief


def test_template_cover_no_vacr_block(mock_output):
    html = _render(mock_output)
    assert "cover-vacr" not in html
