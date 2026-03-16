#!/usr/bin/env python3
"""OSINT search primitive — returns raw search results as JSON array to stdout.

Usage:
    osint_search.py REGION QUERY --type geo|cyber [--mock]

Backends (selected automatically):
  --mock              loads fixture from data/mock_osint_fixtures/{region}_{type}.json
  TAVILY_API_KEY set  Tavily Search API (paid, higher quality)
  default             DuckDuckGo (free, no key required)
"""
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
VALID_TYPES = {"geo", "cyber"}
VALID_WINDOWS = {"1d", "7d", "30d", "90d"}


def parse_args(argv):
    if len(argv) < 2:
        print("Usage: osint_search.py REGION QUERY --type geo|cyber [--mock] [--window 1d|7d|30d|90d]", file=sys.stderr)
        sys.exit(1)

    region = argv[0].upper()
    query = argv[1]
    type_ = None
    mock = False
    window = None

    i = 2
    while i < len(argv):
        if argv[i] == "--type" and i + 1 < len(argv):
            type_ = argv[i + 1]
            i += 2
        elif argv[i] == "--mock":
            mock = True
            i += 1
        elif argv[i] == "--window" and i + 1 < len(argv):
            window = argv[i + 1]
            i += 2
        else:
            i += 1

    if region not in VALID_REGIONS:
        print(f"[osint_search] invalid region '{region}'. Valid: {sorted(VALID_REGIONS)}", file=sys.stderr)
        sys.exit(1)

    if type_ is None:
        print("[osint_search] --type geo|cyber is required", file=sys.stderr)
        sys.exit(1)

    if type_ not in VALID_TYPES:
        print(f"[osint_search] invalid type '{type_}'. Valid: geo, cyber", file=sys.stderr)
        sys.exit(1)

    if window is not None and window not in VALID_WINDOWS:
        print(f"[osint_search] invalid window '{window}'. Valid: {sorted(VALID_WINDOWS)}", file=sys.stderr)
        sys.exit(1)

    return region, query, type_, mock, window


def load_fixture(region, type_):
    path = f"data/mock_osint_fixtures/{region.lower()}_{type_}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _ddg_timelimit(window):
    """Map --window value to DDG timelimit char."""
    return {"1d": "d", "7d": "w", "30d": "m", "90d": "y"}.get(window)


def search_ddg(query: str, max_results: int = 8, window: str = None) -> list[dict]:
    """DuckDuckGo backend — free, no API key required."""
    try:
        from duckduckgo_search import DDGS
        timelimit = _ddg_timelimit(window) if window else None
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, timelimit=timelimit))
        return [
            {
                "title": r.get("title", ""),
                "summary": r.get("body", ""),
                "url": r.get("href", ""),
                "published_date": "",
            }
            for r in results
        ]
    except Exception as e:
        print(f"[osint_search] DDG search failed: {e}", file=sys.stderr)
        return []


def search_tavily(query: str, max_results: int = 8, window: str = None) -> list[dict]:
    """Tavily backend — requires TAVILY_API_KEY env var."""
    try:
        import httpx
        api_key = os.environ["TAVILY_API_KEY"]
        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        }
        if window:
            days_map = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}
            payload["days"] = days_map[window]
        resp = httpx.post(
            "https://api.tavily.com/search",
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "title": r.get("title", ""),
                "summary": r.get("content", ""),
                "url": r.get("url", ""),
                "published_date": r.get("published_date", ""),
            }
            for r in data.get("results", [])
        ]
    except Exception as e:
        print(f"[osint_search] Tavily search failed: {e}", file=sys.stderr)
        return []


def main():
    region, query, type_, mock, window = parse_args(sys.argv[1:])

    if mock:
        articles = load_fixture(region, type_)
    elif os.environ.get("TAVILY_API_KEY"):
        articles = search_tavily(query, window=window)
    else:
        articles = search_ddg(query, window=window)

    sys.stdout.buffer.write(json.dumps(articles, ensure_ascii=False).encode("utf-8") + b"\n")


if __name__ == "__main__":
    main()
