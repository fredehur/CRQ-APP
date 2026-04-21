"""Discovery layer: Tavily /search + Firecrawl /search per scenario."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .intents import Publishers

logger = logging.getLogger(__name__)

_TAVILY_DAYS = 730
_TAVILY_MAX_RESULTS = 10
_FIRECRAWL_LIMIT = 10


@dataclass
class EngineStatus:
    tavily: str = "ok"        # "ok" | "failed" | "disabled"
    firecrawl: str = "ok"     # "ok" | "failed"


def tavily_search(client: Any, queries: list[str]) -> list[dict]:
    """Run queries against Tavily /search. Failures bubble up to the caller."""
    results: list[dict] = []
    for q in queries:
        payload = client.search(
            query=q,
            topic="news",
            days=_TAVILY_DAYS,
            max_results=_TAVILY_MAX_RESULTS,
        )
        for r in payload.get("results", []):
            url = r.get("url")
            if not url:
                continue
            results.append({
                "url": url,
                "title": r.get("title", ""),
                "snippet": r.get("content", "") or "",
                "published_date": r.get("published_date"),
                "discovered_by": ["tavily"],
            })
    return results


def firecrawl_search(client: Any, queries: list[str]) -> list[dict]:
    """Run queries against Firecrawl /search. Failures bubble up to the caller."""
    results: list[dict] = []
    for q in queries:
        payload = client.search(query=q, limit=_FIRECRAWL_LIMIT)
        # SDK ≥ v4 returns a SearchData pydantic model; earlier versions returned a dict.
        items = (
            (payload.web or []) + (payload.news or [])
            if hasattr(payload, "web")
            else payload.get("data", [])
        )
        for r in items:
            if hasattr(r, "url"):
                url, title, snippet = r.url, getattr(r, "title", "") or "", getattr(r, "description", "") or ""
                published_date = getattr(r, "publishedDate", None) or getattr(r, "published_date", None)
            else:
                url = r.get("url")
                meta = r.get("metadata") or {}
                title = r.get("title", "") or meta.get("title", "")
                snippet = r.get("description", "") or meta.get("description", "") or ""
                published_date = meta.get("publishedDate") or meta.get("published_date")
            if not url:
                continue
            results.append({
                "url": url,
                "title": title,
                "snippet": snippet,
                "published_date": published_date,
                "discovered_by": ["firecrawl"],
            })
    return results


def seed_candidates(publishers: "Publishers") -> list[dict]:
    """Return candidate dicts for all seeded URLs in the publishers allowlist."""
    return [
        {
            "url": s.url,
            "title": s.title,
            "snippet": s.snippet,
            "published_date": None,
            "discovered_by": ["seed"],
        }
        for s in publishers.seeded
    ]


def _merge_unique(*lists: list[dict]) -> list[dict]:
    by_url: dict[str, dict] = {}
    for lst in lists:
        for c in lst:
            url = c["url"]
            if url in by_url:
                existing = by_url[url]
                engines = set(existing["discovered_by"]) | set(c["discovered_by"])
                existing["discovered_by"] = sorted(engines)
            else:
                by_url[url] = dict(c)
    return list(by_url.values())


def discover_for_scenario(
    news_queries: list[str],
    doc_queries: list[str],
    tavily_client: Optional[Any],
    firecrawl_client: Optional[Any],
    status: EngineStatus,
) -> list[dict]:
    """Run both engines, merge by URL, mutate `status` on failure."""
    tavily_hits: list[dict] = []
    fc_hits: list[dict] = []

    if status.tavily == "disabled" or tavily_client is None:
        if status.tavily != "disabled":
            status.tavily = "failed"
    else:
        try:
            tavily_hits = tavily_search(tavily_client, news_queries)
        except Exception as exc:
            logger.warning("[source_librarian] Tavily search failed: %s", exc)
            status.tavily = "failed"

    if firecrawl_client is None:
        status.firecrawl = "failed"
    else:
        try:
            fc_hits = firecrawl_search(firecrawl_client, doc_queries)
        except Exception as exc:
            logger.warning("[source_librarian] Firecrawl search failed: %s", exc)
            status.firecrawl = "failed"

    return _merge_unique(tavily_hits, fc_hits)
