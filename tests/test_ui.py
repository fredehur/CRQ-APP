"""
Playwright e2e tests for the analyst dashboard.

NOTE: These tests require a live server at http://localhost:8000.
They are NOT run in CI (no server available) — deferred to integration testing.
To run locally:
  1. Start the server: uv run python server.py
  2. In a separate terminal: uv run pytest tests/test_ui.py -v
"""
import pytest
from playwright.sync_api import sync_playwright, expect

pytestmark = pytest.mark.skip(
    reason="Playwright browser not installed — run 'playwright install chromium' first"
)


BASE = "http://localhost:8000"


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto(BASE)
        pg.wait_for_load_state("networkidle")
        yield pg
        browser.close()


def test_header_renders(page):
    """Header logo and nav tabs visible."""
    expect(page.locator("text=// CRQ ANALYST")).to_be_visible()
    expect(page.locator("#nav-overview")).to_be_visible()
    expect(page.locator("#nav-reports")).to_be_visible()
    expect(page.locator("#nav-history")).to_be_visible()


def test_split_pane_visible_on_overview(page):
    """Split pane visible on overview tab; left and right panels present."""
    page.click("#nav-overview")
    expect(page.locator("#left-panel")).to_be_visible()
    expect(page.locator("#right-panel")).to_be_visible()


def test_window_selector_present(page):
    """Window selector and run button present in header."""
    expect(page.locator("#window-select")).to_be_visible()
    expect(page.locator("#btn-run-all")).to_be_visible()


def test_region_rows_rendered(page):
    """All 5 region rows are present in the left panel."""
    region_list = page.locator("#region-list")
    for r in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        expect(region_list.get_by_text(r)).to_be_visible()


def test_reports_tab_switches(page):
    """Clicking Reports tab hides overview and shows reports content."""
    page.click("#nav-reports")
    expect(page.locator("#tab-reports")).to_be_visible()
    expect(page.locator("#tab-overview")).to_be_hidden()


def test_history_tab_switches(page):
    """Clicking History tab shows history content."""
    page.click("#nav-history")
    expect(page.locator("#tab-history")).to_be_visible()


def test_overview_tab_returns(page):
    """Clicking Overview tab restores split pane."""
    page.click("#nav-overview")
    expect(page.locator("#split-pane")).to_be_visible()
