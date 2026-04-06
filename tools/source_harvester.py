#!/usr/bin/env python3
"""Source harvester — fetches content from known validation source registry.

Usage:
    source_harvester.py [--mock]

Reads:  data/validation_sources.json
Writes: output/validation_cache/{source_id}/{YYYY-MM-DD}.json
        Updates last_checked in data/validation_sources.json

Tiered fetch strategy (tries in order, stops at first success):
  Tier A — urllib.request GET on source URL
  Tier B — DDG search: "{name} {year} {scenario} cost"
  Tier C — DDG search: "{name} {year} filetype:pdf"
"""
import json
import os
import sqlite3
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()

from tools.config import VALIDATION_CACHE_DIR

SOURCES_PATH = Path("data/validation_sources.json")
CACHE_ROOT = VALIDATION_CACHE_DIR
TODAY = date.today().isoformat()
CURRENT_YEAR = date.today().year


def _search_ddg(query: str) -> str:
    """Run a DDG search via osint_search.py workaround using duckduckgo_search directly."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        return " ".join(r.get("body", "") + " " + r.get("title", "") for r in results)
    except Exception as e:
        print(f"[harvester] DDG search failed for '{query}': {e}", file=sys.stderr)
        return ""


def _fetch_url(url: str) -> str:
    """Tier A — simple HTTP GET."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read(50_000)
            return raw.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[harvester] URL fetch failed for {url}: {e}", file=sys.stderr)
        return ""


def harvest_source(source: dict, mock: bool) -> dict:
    source_id = source["id"]
    cache_dir = CACHE_ROOT / source_id
    cache_file = cache_dir / f"{TODAY}.json"

    if cache_file.exists():
        print(f"[harvester] {source_id} already cached for {TODAY}, skipping", file=sys.stderr)
        return json.loads(cache_file.read_text(encoding="utf-8"))

    cache_dir.mkdir(parents=True, exist_ok=True)

    entry = {
        "source_id": source_id,
        "fetched_date": TODAY,
        "publication_year": None,
        "admiralty": {
            "reliability": source["admiralty_reliability"],
            "credibility": "2",
            "rating": f"{source['admiralty_reliability']}2",
        },
        "mock": mock,
        "raw_text": "",
        "benchmarks": [],
    }

    if mock:
        print(f"[harvester] mock mode — stub cache for {source_id}", file=sys.stderr)
        cache_file.write_text(json.dumps(entry, indent=2), encoding="utf-8")
        return entry

    raw_text = ""

    # Tier A — direct URL fetch
    print(f"[harvester] Tier A fetch: {source['url']}", file=sys.stderr)
    raw_text = _fetch_url(source["url"])
    print(f"[harvester] Tier A result: {len(raw_text)} chars for {source_id}", file=sys.stderr)

    # Tier B — search fallback
    if len(raw_text) < 200:
        scenario = source["scenario_tags"][0] if source["scenario_tags"] else "cyber incident"
        query = f"{source['name']} {CURRENT_YEAR} {scenario} cost"
        print(f"[harvester] Tier B search: {query}", file=sys.stderr)
        raw_text = _search_ddg(query)
        print(f"[harvester] Tier B result: {len(raw_text)} chars for {source_id}", file=sys.stderr)

    # Tier C — PDF search fallback
    if len(raw_text) < 200:
        query = f"{source['name']} {CURRENT_YEAR} filetype:pdf"
        print(f"[harvester] Tier C search: {query}", file=sys.stderr)
        raw_text = _search_ddg(query)
        print(f"[harvester] Tier C result: {len(raw_text)} chars for {source_id}", file=sys.stderr)

    # Try to detect publication year from text
    import re
    years = re.findall(r"\b(202[3-9]|203[0-9])\b", raw_text)
    if years:
        entry["publication_year"] = int(max(set(years), key=years.count))

    entry["raw_text"] = raw_text[:20_000]  # cap at 20k chars
    cache_file.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    print(f"[harvester] cached {source_id} → {cache_file} ({len(raw_text)} chars)", file=sys.stderr)
    return entry


def run(mock: bool = False) -> None:
    if not SOURCES_PATH.exists():
        print(f"[harvester] sources registry not found: {SOURCES_PATH}", file=sys.stderr)
        sys.exit(1)

    sources_data = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    sources = sources_data.get("sources", [])
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for source in sources:
        harvest_source(source, mock)
        source["last_checked"] = now_iso
        if not source.get("last_new_content"):
            cache_file = CACHE_ROOT / source["id"] / f"{TODAY}.json"
            if cache_file.exists():
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                if data.get("raw_text"):
                    source["last_new_content"] = TODAY

    # Update last_checked in registry
    SOURCES_PATH.write_text(json.dumps(sources_data, indent=2), encoding="utf-8")
    print(f"[harvester] done — {len(sources)} sources processed", file=sys.stderr)


GOVERNMENT_SOURCE_IDS = {"enisa-threat-landscape", "cisa-advisory"}

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'sources.db')


def upsert_benchmark_sources(db_path: str = DB_PATH) -> int:
    """Upsert benchmark sources from validation_sources.json into sources.db."""
    if not SOURCES_PATH.exists():
        print("[harvester] validation_sources.json not found, skipping DB upsert", file=sys.stderr)
        return 0

    sources_data = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    sources = sources_data.get("sources", [])
    today = date.today().isoformat()

    conn = sqlite3.connect(db_path)
    count = 0

    for source in sources:
        sid = source.get("id", "")
        url = source.get("url", "")
        name = source.get("name", "")
        if not sid or not url:
            continue

        domain = urlparse(url).netloc.lower().removeprefix("www.")
        source_type = "government" if sid in GOVERNMENT_SOURCE_IDS else "industry"

        # Check if source already exists
        existing = conn.execute(
            "SELECT id, appearance_count FROM sources_registry WHERE id = ?",
            (sid,),
        ).fetchone()

        if existing is None:
            conn.execute(
                """
                INSERT INTO sources_registry
                    (id, url, name, domain, source_type, credibility_tier,
                     collection_type, junk, blocked, first_seen, last_seen,
                     appearance_count, cited_count)
                VALUES (?, ?, ?, ?, ?, 'A', 'benchmark', 0, 0, ?, ?, 1, 0)
                """,
                (sid, url, name, domain, source_type, today, today),
            )
        else:
            conn.execute(
                """
                UPDATE sources_registry
                   SET last_seen = ?, appearance_count = appearance_count + 1,
                       collection_type = 'benchmark'
                 WHERE id = ?
                """,
                (today, sid),
            )
        count += 1

    conn.commit()
    conn.close()
    print(f"[harvester] upserted {count} benchmark sources into sources.db", file=sys.stderr)
    return count


def main():
    mock = "--mock" in sys.argv
    run(mock=mock)
    if not mock:
        upsert_benchmark_sources()


if __name__ == "__main__":
    main()
