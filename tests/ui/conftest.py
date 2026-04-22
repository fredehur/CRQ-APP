import pytest
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8001"


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()
