"""
Playwright e2e tests for the Reports V2 ledger tab.

NOTE: These tests require a live server at http://localhost:8001.
They are NOT run in CI — deferred to integration testing.
To run locally:
  1. Start the server: uv run python server.py
  2. Install browser: playwright install chromium
  3. In a separate terminal: uv run pytest tests/ui/test_reports_ledger.py -v
"""
import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.skip(
    reason="Playwright browser not installed — run 'playwright install chromium' first"
)

BASE = "http://localhost:8001"


def test_reports_ledger_renders_seven_rows(page):
    page.goto(f"{BASE}/#reports")
    page.wait_for_selector(".table--ledger")
    rows = page.locator(".table--ledger tbody tr[data-audience-id]")
    expect(rows).to_have_count(7)


def test_reports_ledger_empty_row_has_empty_pill(page):
    page.goto(f"{BASE}/#reports")
    page.wait_for_selector(".table--ledger")
    empty_pill = page.locator(".pill--status-empty").first
    expect(empty_pill).to_be_visible()


def test_reports_regenerate_sends_post(page):
    page.goto(f"{BASE}/#reports")
    page.wait_for_selector(".table--ledger")
    with page.expect_request(lambda r: "/regenerate" in r.url and r.method == "POST"):
        page.locator("button", has_text="Regenerate").first.click()


def test_version_menu_opens_and_outside_click_closes(page):
    page.goto(f"{BASE}/#reports")
    page.wait_for_selector(".table--ledger")
    trigger = page.locator(".row-actions__menu-trigger").first
    trigger.click()
    menu = page.locator(".popover").first
    expect(menu).to_be_visible()
    page.locator("body").click(position={"x": 10, "y": 10})
    expect(menu).not_to_be_visible()


def test_version_menu_closes_on_escape(page):
    page.goto(f"{BASE}/#reports")
    page.wait_for_selector(".table--ledger")
    trigger = page.locator(".row-actions__menu-trigger").first
    trigger.click()
    menu = page.locator(".popover").first
    expect(menu).to_be_visible()
    page.keyboard.press("Escape")
    expect(menu).not_to_be_visible()
