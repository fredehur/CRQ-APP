"""Tests for tools/source_librarian/scraper.py — Firecrawl /scrape with cache."""
from pathlib import Path
from unittest.mock import MagicMock

FIX = Path(__file__).parent / "fixtures"


def _make_doc(markdown: str, title: str = ""):
    doc = MagicMock()
    doc.markdown = markdown
    doc.metadata = MagicMock()
    doc.metadata.title = title
    return doc


def test_scrape_url_returns_markdown_and_title():
    from tools.source_librarian.scraper import scrape_url
    md = (FIX / "firecrawl_scrape_dragos.md").read_text()
    client = MagicMock()
    client.scrape.return_value = _make_doc(md, title="OT Year in Review 2024")
    result = scrape_url(client, "https://dragos.com/r")
    assert result.status == "ok"
    assert "68% YoY" in result.markdown
    assert result.title == "OT Year in Review 2024"


def test_scrape_url_failure_returns_failed_status():
    from tools.source_librarian.scraper import scrape_url
    client = MagicMock()
    client.scrape.side_effect = RuntimeError("boom")
    result = scrape_url(client, "https://x.test/y")
    assert result.status == "failed"
    assert result.markdown is None


def test_scrape_url_empty_markdown_returns_failed():
    from tools.source_librarian.scraper import scrape_url
    client = MagicMock()
    client.scrape.return_value = _make_doc("   ", title="empty")
    result = scrape_url(client, "https://x.test/y")
    assert result.status == "failed"


def test_scrape_cache_only_calls_client_once_per_url():
    from tools.source_librarian.scraper import ScrapeCache
    client = MagicMock()
    client.scrape.return_value = _make_doc("# text", title="t")
    cache = ScrapeCache(client)
    cache.get("https://dragos.com/r")
    cache.get("https://dragos.com/r")
    cache.get("https://dragos.com/r")
    assert client.scrape.call_count == 1


def test_scrape_cache_stores_failed_results():
    from tools.source_librarian.scraper import ScrapeCache
    client = MagicMock()
    client.scrape.side_effect = RuntimeError("nope")
    cache = ScrapeCache(client)
    r1 = cache.get("https://x.test/y")
    r2 = cache.get("https://x.test/y")
    assert r1.status == "failed"
    assert r2.status == "failed"
    assert client.scrape.call_count == 1
