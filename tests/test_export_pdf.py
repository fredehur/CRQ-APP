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
    assert "#104277" in html


def test_template_contains_pipeline_id(mock_output):
    html = _render(mock_output)
    assert "crq-test-001" in html


def test_template_contains_vacr(mock_output):
    html = _render(mock_output)
    assert "44" in html  # $44.7M


def test_template_contains_escalated_regions(mock_output):
    html = _render(mock_output)
    assert "APAC" in html
    assert "AME" in html


def test_template_contains_three_pillar_labels(mock_output):
    html = _render(mock_output)
    assert "Geopolitical Driver" in html
    assert "Cyber Vector" in html
    assert "Business Impact" in html
