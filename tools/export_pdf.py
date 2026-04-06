# tools/export_pdf.py
"""
Renders the board PDF report using Playwright + Jinja2.

Usage:
    uv run python tools/export_pdf.py [output.pdf]
    Defaults to output/board_report.pdf if no argument given.
"""
import sys
import tempfile
import os
from pathlib import Path

import jinja2
from playwright.sync_api import sync_playwright

# Allow running from project root or tools/
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, str(Path(__file__).parent.parent))
from report_builder import build
from tools.config import BOARD_PDF_PATH

TEMPLATE_DIR  = Path(__file__).parent / "templates"
TEMPLATE_NAME = "report.html.j2"
DEFAULT_OUT   = str(BOARD_PDF_PATH)


def export(output_path: str = DEFAULT_OUT) -> None:
    data = build()

    # Render HTML
    loader = jinja2.FileSystemLoader(str(TEMPLATE_DIR))
    env    = jinja2.Environment(loader=loader, autoescape=True)
    html   = env.get_template(TEMPLATE_NAME).render(data=data)

    # Write to temp file (NamedTemporaryFile avoids path collisions)
    with tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8"
    ) as tmp:
        tmp.write(html)
        tmp_path = tmp.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page    = browser.new_page()
            page.goto(Path(tmp_path).as_uri())  # cross-platform URI (file:///C:/... on Windows)
            page.pdf(
                path=output_path,
                format="A4",
                print_background=True,
            )
            browser.close()
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass

    print(f"PDF exported: {output_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    export(out)
