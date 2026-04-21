"""Pure-function ranker: filter T4, score, select top-N."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from .intents import Publishers
from .snapshot import SourceEntry

_AUTHORITY_WEIGHT = 0.6
_RECENCY_WEIGHT = 0.25
_QUERY_WEIGHT = 0.15
_RECENCY_HALF_LIFE_MONTHS = 18
_UNKNOWN_DATE_RECENCY = 0.3


@dataclass
class Selection:
    status: str  # "ok" | "no_authoritative_coverage"
    sources: list[SourceEntry]
    diagnostics: Optional[dict] = None


def authority_score(tier: str) -> float:
    return {"T1": 1.0, "T2": 0.7, "T3": 0.4}.get(tier, 0.0)


def recency_score(published_date: Optional[str], today: Optional[date] = None) -> float:
    if not published_date:
        return _UNKNOWN_DATE_RECENCY
    today = today or date.today()
    try:
        pub = datetime.strptime(published_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return _UNKNOWN_DATE_RECENCY
    months = (today.year - pub.year) * 12 + (today.month - pub.month)
    if months <= 0:
        return 1.0
    return math.exp(-math.log(2) * months / _RECENCY_HALF_LIFE_MONTHS)


def query_match_score(title: str, snippet: str, query_terms: list[str]) -> float:
    if not query_terms:
        return 0.0
    haystack = f"{title} {snippet}".lower()
    hits = sum(1 for t in query_terms if t.lower() in haystack)
    return min(1.0, hits / len(query_terms))


def _composite(tier: str, published_date: Optional[str], title: str, snippet: str,
               query_terms: list[str], today: date) -> float:
    return round(
        _AUTHORITY_WEIGHT * authority_score(tier)
        + _RECENCY_WEIGHT * recency_score(published_date, today=today)
        + _QUERY_WEIGHT * query_match_score(title, snippet, query_terms),
        4,
    )


def _dedupe(candidates: list[dict]) -> list[dict]:
    by_url: dict[str, dict] = {}
    for c in candidates:
        url = c["url"]
        if url in by_url:
            merged = by_url[url]
            engines = set(merged.get("discovered_by", [])) | set(c.get("discovered_by", []))
            merged["discovered_by"] = sorted(engines)
        else:
            by_url[url] = {**c, "discovered_by": list(c.get("discovered_by", []))}
    return list(by_url.values())


def rank_and_select(
    candidates: list[dict],
    publishers: Publishers,
    query_terms: list[str],
    top_n: int = 10,
    max_seeded: int = 3,
    today: Optional[date] = None,
) -> Selection:
    """Rank and select top-N sources.

    max_seeded caps how many pre-seeded (discovered_by=['seed']) entries appear in
    the final list so that recent Tavily/Firecrawl results always have room.
    """
    today = today or date.today()
    deduped = _dedupe(candidates)

    survivors: list[tuple[float, SourceEntry]] = []
    rejected: list[dict] = []

    for c in deduped:
        tier = publishers.tier_for(c["url"])
        if tier is None:
            rejected.append({
                "url": c["url"],
                "title": c.get("title", ""),
                "reason": "publisher_not_in_allowlist",
            })
            continue
        score = _composite(
            tier,
            c.get("published_date"),
            c.get("title", ""),
            c.get("snippet", ""),
            query_terms,
            today,
        )
        publisher = publishers.publisher_for(c["url"]) or ""
        entry = SourceEntry(
            url=c["url"],
            title=c.get("title", ""),
            publisher=publisher,
            publisher_tier=tier,
            published_date=c.get("published_date"),
            discovered_by=c.get("discovered_by", []),
            score=score,
            summary=None,
            figures=[],
            scrape_status="skipped",
        )
        survivors.append((score, entry))

    if not survivors:
        return Selection(
            status="no_authoritative_coverage",
            sources=[],
            diagnostics={
                "candidates_discovered": len(deduped),
                "top_rejected": rejected[:10],
            },
        )

    survivors.sort(key=lambda pair: pair[0], reverse=True)

    # Apply seed cap: keep top max_seeded seeded entries, then fill with discovered
    selected: list[SourceEntry] = []
    seeded_count = 0
    for _, entry in survivors:
        if len(selected) >= top_n:
            break
        is_seed = entry.discovered_by == ["seed"]
        if is_seed:
            if seeded_count >= max_seeded:
                continue
            seeded_count += 1
        selected.append(entry)

    return Selection(status="ok", sources=selected, diagnostics=None)
