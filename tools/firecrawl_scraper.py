#!/usr/bin/env python3
"""Firecrawl scraper — depth layer for OSINT collection.

Wraps Firecrawl /scrape. Returns one ScrapedItem per input URL — always.
Failed scrapes fall back to the Tavily snippet tagged source_type: "snippet".

Public interface:
    scrape_urls(urls, tavily_snippets, tavily_scores, region=None) -> list[ScrapedItem]
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

_MAX_CHARS = 12_000
_HEAD_CHARS = 6_000
_TAIL_CHARS = 6_000
_TRUNCATION_MARKER = "\n\n[…truncated…]\n\n"
_TIMEOUT_MS = 30_000   # Firecrawl expects milliseconds
_MAX_WORKERS = 5

_REPO_ROOT = Path(__file__).resolve().parent.parent


class ScrapedItem(TypedDict):
    url: str
    title: str
    source_type: str        # "fulltext" | "snippet"
    content: str
    tavily_score: float


def _truncate(text: str) -> str:
    """Middle-truncate text longer than _MAX_CHARS characters."""
    if len(text) <= _MAX_CHARS:
        return text
    return text[:_HEAD_CHARS] + _TRUNCATION_MARKER + text[-_TAIL_CHARS:]


def _load_mock_fixture(region: str) -> dict:
    """Load Firecrawl mock fixture for a region key (e.g. 'apac', 'vacr')."""
    import json
    fixture_path = _REPO_ROOT / "data" / "mock_osint_fixtures" / f"firecrawl_{region.lower()}.json"
    try:
        return json.loads(fixture_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("[firecrawl_scraper] no fixture at %s", fixture_path)
        return {}


def _scrape_one_mock(
    url: str,
    fixture: dict,
    tavily_snippet: str,
    tavily_score: float,
) -> ScrapedItem:
    entry = fixture.get(url)
    if entry is None:
        return ScrapedItem(
            url=url, title="", source_type="snippet",
            content=tavily_snippet, tavily_score=tavily_score,
        )
    if entry.get("status") == "failed" or not (entry.get("markdown") or "").strip():
        return ScrapedItem(
            url=url, title=entry.get("title", ""), source_type="snippet",
            content=tavily_snippet, tavily_score=tavily_score,
        )
    return ScrapedItem(
        url=url,
        title=entry.get("title", ""),
        source_type="fulltext",
        content=_truncate(entry["markdown"]),
        tavily_score=tavily_score,
    )


def _call_firecrawl(url: str, api_key: str) -> tuple[str, str] | None:
    """One Firecrawl HTTP call. Returns (markdown, title) or None on any failure."""
    try:
        from firecrawl import FirecrawlApp
    except ImportError as exc:
        raise ImportError("firecrawl-py not installed. Run: uv add firecrawl-py") from exc
    try:
        app = FirecrawlApp(api_key=api_key)
        result = app.scrape_url(
            url,
            params={
                "onlyMainContent": True,
                "formats": ["markdown"],
                "timeout": _TIMEOUT_MS,
            },
        )
        markdown = (result.get("markdown") or "").strip()
        if not markdown:
            return None
        title = (result.get("metadata") or {}).get("title", "")
        return markdown, title
    except Exception as exc:
        logger.warning("[firecrawl_scraper] scrape failed for %s: %s", url, exc)
        return None


def _scrape_one_live(
    url: str,
    api_key: str,
    tavily_snippet: str,
    tavily_score: float,
) -> ScrapedItem:
    """Scrape once, retry once on failure, fall back to snippet."""
    result = _call_firecrawl(url, api_key)
    if result is None:
        logger.warning("[firecrawl_scraper] retry for %s", url)
        result = _call_firecrawl(url, api_key)
    if result is None:
        logger.warning("[firecrawl_scraper] falling back to snippet for %s", url)
        return ScrapedItem(
            url=url, title="", source_type="snippet",
            content=tavily_snippet, tavily_score=tavily_score,
        )
    markdown, title = result
    return ScrapedItem(
        url=url, title=title, source_type="fulltext",
        content=_truncate(markdown), tavily_score=tavily_score,
    )


def scrape_urls(
    urls: list[str],
    tavily_snippets: dict[str, str],
    tavily_scores: dict[str, float],
    region: str | None = None,
) -> list[ScrapedItem]:
    """Scrape a list of URLs. Returns one ScrapedItem per input URL — always.

    Mock mode (OSINT_MOCK=1): reads fixtures from data/mock_osint_fixtures/.
    Live mode: calls Firecrawl /scrape concurrently via ThreadPoolExecutor.

    Args:
        urls: URLs to scrape, in priority order.
        tavily_snippets: url -> snippet, used as fallback content on failure.
        tavily_scores: url -> Tavily relevance score, stored on ScrapedItem.
        region: Region key for fixture lookup ("apac", "ame", etc.) or None for VaCR.
    """
    if not urls:
        return []

    use_mock = os.environ.get("OSINT_MOCK", "").strip().lower() in ("1", "true")

    if use_mock:
        fixture = _load_mock_fixture(region or "vacr")
        return [
            _scrape_one_mock(
                url,
                fixture,
                tavily_snippets.get(url, ""),
                tavily_scores.get(url, 0.0),
            )
            for url in urls
        ]

    api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError(
            "FIRECRAWL_API_KEY is not set. "
            "Set it in .env or pass --mock to use fixture mode."
        )

    results: dict[str, ScrapedItem] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {
            pool.submit(
                _scrape_one_live,
                url,
                api_key,
                tavily_snippets.get(url, ""),
                tavily_scores.get(url, 0.0),
            ): url
            for url in urls
        }
        for future in as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception as exc:
                logger.warning("[firecrawl_scraper] unexpected future error for %s: %s", url, exc)
                results[url] = ScrapedItem(
                    url=url, title="", source_type="snippet",
                    content=tavily_snippets.get(url, ""),
                    tavily_score=tavily_scores.get(url, 0.0),
                )

    return [results[url] for url in urls]   # restore input order
