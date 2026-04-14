"""Firecrawl /scrape wrapper with per-run URL-keyed cache."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TIMEOUT_MS = 30_000


@dataclass
class ScrapeResult:
    status: str  # "ok" | "failed"
    markdown: Optional[str]
    title: str


def scrape_url(client: Any, url: str) -> ScrapeResult:
    """Scrape one URL via Firecrawl. Returns ScrapeResult with status."""
    try:
        doc = client.scrape(
            url,
            formats=["markdown"],
            only_main_content=True,
            timeout=_TIMEOUT_MS,
        )
    except Exception as exc:
        logger.warning("[source_librarian] scrape failed for %s: %s", url, exc)
        return ScrapeResult(status="failed", markdown=None, title="")

    markdown = (getattr(doc, "markdown", None) or "").strip()
    if not markdown:
        return ScrapeResult(status="failed", markdown=None, title="")

    metadata = getattr(doc, "metadata", None)
    title = ""
    if metadata is not None:
        title = getattr(metadata, "title", "") or ""
    return ScrapeResult(status="ok", markdown=markdown, title=title)


class ScrapeCache:
    """URL-keyed cache for one snapshot run. Failed results are also cached
    so we never retry the same URL within a run."""

    def __init__(self, client: Any):
        self._client = client
        self._cache: dict[str, ScrapeResult] = {}

    def get(self, url: str) -> ScrapeResult:
        if url not in self._cache:
            self._cache[url] = scrape_url(self._client, url)
        return self._cache[url]

    def all_unique_count(self) -> int:
        return len(self._cache)
