"""Unit tests for tools/firecrawl_scraper.py."""
import os
import sys
import time
import random
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import firecrawl_scraper
from firecrawl_scraper import scrape_urls, _truncate


class TestTruncate(unittest.TestCase):
    def test_short_content_unchanged(self):
        text = "hello world"
        assert _truncate(text) == text

    def test_exactly_at_limit_unchanged(self):
        text = "x" * 12_000
        assert _truncate(text) == text

    def test_long_content_middle_truncated(self):
        # 12,200 chars: first 6100 'A', last 6100 'B'
        text = "A" * 6_100 + "B" * 6_100
        result = _truncate(text)
        assert "[…truncated…]" in result
        assert result.startswith("A" * 6_000)
        assert result.endswith("B" * 6_000)
        assert len(result) < len(text)

    def test_truncation_marker_appears_once(self):
        text = "Z" * 20_000
        result = _truncate(text)
        assert result.count("[…truncated…]") == 1


class TestMockMode(unittest.TestCase):
    def setUp(self):
        os.environ["OSINT_MOCK"] = "1"

    def tearDown(self):
        os.environ.pop("OSINT_MOCK", None)

    def test_happy_path_returns_fulltext(self):
        fixture = {
            "https://example.com/article": {
                "markdown": "Full article text about wind energy threats",
                "title": "Wind Energy Threat Report",
                "status": "ok",
            }
        }
        with patch.object(firecrawl_scraper, "_load_mock_fixture", return_value=fixture):
            result = scrape_urls(
                ["https://example.com/article"],
                {"https://example.com/article": "short snippet"},
                {"https://example.com/article": 0.9},
                region="apac",
            )
        assert len(result) == 1
        assert result[0]["source_type"] == "fulltext"
        assert result[0]["content"] == "Full article text about wind energy threats"
        assert result[0]["title"] == "Wind Energy Threat Report"
        assert result[0]["tavily_score"] == 0.9
        assert result[0]["url"] == "https://example.com/article"

    def test_failed_fixture_falls_back_to_snippet(self):
        fixture = {
            "https://example.com/paywalled": {
                "markdown": "",
                "title": "Paywalled Article",
                "status": "failed",
            }
        }
        with patch.object(firecrawl_scraper, "_load_mock_fixture", return_value=fixture):
            result = scrape_urls(
                ["https://example.com/paywalled"],
                {"https://example.com/paywalled": "tavily snippet text"},
                {"https://example.com/paywalled": 0.5},
            )
        assert result[0]["source_type"] == "snippet"
        assert result[0]["content"] == "tavily snippet text"

    def test_unknown_url_returns_snippet_placeholder(self):
        with patch.object(firecrawl_scraper, "_load_mock_fixture", return_value={}):
            result = scrape_urls(
                ["https://unknown.com/article"],
                {"https://unknown.com/article": "fallback snippet"},
                {"https://unknown.com/article": 0.3},
            )
        assert result[0]["source_type"] == "snippet"
        assert result[0]["content"] == "fallback snippet"

    def test_empty_url_list_returns_empty(self):
        result = scrape_urls([], {}, {}, region="apac")
        assert result == []

    def test_input_order_preserved_in_mock(self):
        fixture = {
            f"https://example.com/{i}": {
                "markdown": f"content {i}", "title": f"T{i}", "status": "ok"
            }
            for i in range(5)
        }
        urls = [f"https://example.com/{i}" for i in range(5)]
        with patch.object(firecrawl_scraper, "_load_mock_fixture", return_value=fixture):
            result = scrape_urls(urls, {u: "" for u in urls}, {u: 0.5 for u in urls})
        assert [r["url"] for r in result] == urls


class TestLiveModeValidation(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OSINT_MOCK", None)
        os.environ.pop("FIRECRAWL_API_KEY", None)

    def test_missing_api_key_raises_environment_error(self):
        with self.assertRaises(EnvironmentError) as ctx:
            scrape_urls(
                ["https://example.com"],
                {"https://example.com": "snippet"},
                {"https://example.com": 0.8},
            )
        assert "FIRECRAWL_API_KEY" in str(ctx.exception)

    def test_empty_url_list_does_not_require_key(self):
        result = scrape_urls([], {}, {})
        assert result == []


class TestRetryLogic(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OSINT_MOCK", None)
        os.environ["FIRECRAWL_API_KEY"] = "test-key"

    def tearDown(self):
        os.environ.pop("FIRECRAWL_API_KEY", None)

    def test_retry_once_then_succeed(self):
        side_effects = [None, ("Full article markdown", "Article Title")]
        with patch("firecrawl_scraper._call_firecrawl", side_effect=side_effects) as mock_call:
            result = scrape_urls(
                ["https://example.com"],
                {"https://example.com": "snippet"},
                {"https://example.com": 0.8},
            )
        assert result[0]["source_type"] == "fulltext"
        assert result[0]["content"] == "Full article markdown"
        assert result[0]["title"] == "Article Title"
        assert mock_call.call_count == 2

    def test_retry_twice_then_fallback_to_snippet(self):
        with patch("firecrawl_scraper._call_firecrawl", return_value=None) as mock_call:
            result = scrape_urls(
                ["https://example.com"],
                {"https://example.com": "tavily snippet fallback"},
                {"https://example.com": 0.7},
            )
        assert result[0]["source_type"] == "snippet"
        assert result[0]["content"] == "tavily snippet fallback"
        assert mock_call.call_count == 2

    def test_successful_first_attempt_no_retry(self):
        with patch("firecrawl_scraper._call_firecrawl", return_value=("content", "title")) as mock_call:
            result = scrape_urls(
                ["https://example.com"],
                {"https://example.com": "snippet"},
                {"https://example.com": 0.9},
            )
        assert result[0]["source_type"] == "fulltext"
        assert mock_call.call_count == 1

    def test_input_order_preserved_with_concurrency(self):
        urls = [f"https://example.com/{i}" for i in range(5)]

        def fake_call(url, api_key):
            return (f"content for {url}", f"title {url}")

        with patch("firecrawl_scraper._call_firecrawl", side_effect=fake_call):
            result = scrape_urls(
                urls,
                {u: "" for u in urls},
                {u: 0.5 for u in urls},
            )
        assert [r["url"] for r in result] == urls

    def test_all_urls_scraped_concurrently_preserve_order(self):
        urls = [f"https://example.com/{i}" for i in range(5)]

        def fake_call(url, api_key):
            time.sleep(random.uniform(0, 0.01))
            return (f"content for {url}", "title")

        with patch("firecrawl_scraper._call_firecrawl", side_effect=fake_call):
            result = scrape_urls(
                urls,
                {u: "" for u in urls},
                {u: float(i) for i, u in enumerate(urls)},
            )
        for i, (url, item) in enumerate(zip(urls, result)):
            assert item["url"] == url, f"Position {i}: expected {url}, got {item['url']}"


if __name__ == "__main__":
    unittest.main()
