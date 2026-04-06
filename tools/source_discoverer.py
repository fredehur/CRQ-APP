#!/usr/bin/env python3
"""Source discoverer — search-driven discovery of unknown benchmark sources.

Usage:
    source_discoverer.py [--mock]

Reads:  data/master_scenarios.json  (scenario names)
        data/validation_sources.json  (to skip already-known URLs)
Writes: output/validation_candidates.json
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()

from tools.config import VALIDATION_CANDIDATES_JSON

MASTER_SCENARIOS_PATH = Path("data/master_scenarios.json")
SOURCES_PATH = Path("data/validation_sources.json")
CANDIDATES_PATH = VALIDATION_CANDIDATES_JSON
CURRENT_YEAR = datetime.now().year

# Top-4 scenarios by financial rank — keeps query count reasonable
TOP_SCENARIOS = ["Ransomware", "Accidental disclosure", "System intrusion", "Insider misuse"]
SECTOR_ANGLES = ["manufacturing", "energy", "wind energy", "ICS OT"]


def _search_ddg(query: str) -> list[dict]:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=8))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in results
        ]
    except Exception as e:
        print(f"[discoverer] DDG search failed for '{query}': {e}", file=sys.stderr)
        return []


def _has_dollar_figure(text: str) -> bool:
    return bool(re.search(r"\$[\d,.]+\s*[MBKmb]?", text))


def _estimate_year(text: str) -> int | None:
    years = re.findall(r"\b(202[3-9]|203[0-9])\b", text)
    if years:
        return int(max(set(years), key=years.count))
    return None


def discover(mock: bool = False) -> list[dict]:
    known_urls = set()
    if SOURCES_PATH.exists():
        data = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
        known_urls = {s["url"].rstrip("/") for s in data.get("sources", [])}

    candidates = []
    seen_urls = set()

    if mock:
        print("[discoverer] mock mode — writing empty candidates", file=sys.stderr)
        return []

    for scenario in TOP_SCENARIOS:
        for sector in SECTOR_ANGLES:
            query = f'"{scenario}" financial impact cost report {CURRENT_YEAR} {sector}'
            print(f"[discoverer] searching: {query}", file=sys.stderr)
            results = _search_ddg(query)

            for r in results:
                url = r["url"].rstrip("/")
                if url in known_urls or url in seen_urls:
                    continue
                seen_urls.add(url)

                combined = r["title"] + " " + r["snippet"]
                has_dollar = _has_dollar_figure(combined)

                candidate = {
                    "title": r["title"],
                    "url": r["url"],
                    "snippet": r["snippet"][:500],
                    "estimated_year": _estimate_year(combined),
                    "has_dollar_figure": has_dollar,
                    "scenario_tags": [scenario],
                    "sector_tags": [sector],
                    "suggested_admiralty_reliability": "C",
                    "status": "pending_review",
                }
                candidates.append(candidate)

    return candidates


def run(mock: bool = False) -> None:
    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)

    candidates = discover(mock=mock)

    # Filter: only keep candidates with dollar figures or high-value sources
    qualifying = [c for c in candidates if c["has_dollar_figure"]]

    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mock": mock,
        "total_searched": len(candidates),
        "candidates": qualifying,
    }

    CANDIDATES_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(
        f"[discoverer] done — {len(qualifying)} qualifying candidates from {len(candidates)} results",
        file=sys.stderr,
    )


def main():
    mock = "--mock" in sys.argv
    run(mock=mock)


if __name__ == "__main__":
    main()
