#!/usr/bin/env python3
"""OSINT physical-pillar signal collector — mirrors osint_collector.py.

Usage:
    uv run python tools/osint_physical_collector.py REGION [--mock]

Writes: output/regional/{region}/osint_physical_signals.json

Pillar = "physical": unrest, conflict, terrorism, crime, travel, maritime,
political, disaster. Distinct from cyber pillar handled by osint_collector.py.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = REPO_ROOT / "output"
FIXTURES_DIR = REPO_ROOT / "data" / "mock_osint_fixtures"


def _mock_collect(region: str) -> dict:
    fixture = FIXTURES_DIR / f"{region.lower()}_osint_physical.json"
    if not fixture.exists():
        raise FileNotFoundError(f"Mock fixture not found: {fixture}")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    data["collected_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return data


def _field(obj, name):
    """Read a field from a result that may be a dict or a typed SDK object."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """Tavily search via the official tavily-python SDK. Requires TAVILY_API_KEY.

    Uses the pinned SDK (which handles auth correctly) rather than hand-rolled
    HTTP. Errors propagate so an auth/SDK failure fails the run loudly instead of
    yielding an empty brief.
    """
    from tavily import TavilyClient

    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    resp = client.search(query, max_results=max_results, search_depth="basic")
    results = _field(resp, "results") or []
    return [
        {
            "title": _field(r, "title") or "",
            "url": _field(r, "url") or "",
            "source": _field(r, "url") or "",
            "published_date": _field(r, "published_date") or "",
            "summary": _field(r, "content") or "",
        }
        for r in results
    ]


def _firecrawl_extract(url: str) -> dict | None:
    """Firecrawl main-content extract via firecrawl-py v4. Requires FIRECRAWL_API_KEY.

    v4 SDK: `Firecrawl(api_key=...).scrape(url, formats=["markdown"],
    only_main_content=True)` returns a Document (attribute access). Field reads
    go through `_field` to tolerate dict-vs-object differences across v4 point
    releases. Returns {content, location} or None on empty extraction.
    """
    if not url:
        return None
    from firecrawl import Firecrawl

    app = Firecrawl(api_key=os.environ["FIRECRAWL_API_KEY"])
    doc = app.scrape(url, formats=["markdown"], only_main_content=True)
    markdown = (_field(doc, "markdown") or "").strip()
    if not markdown:
        return None
    location = _field(_field(doc, "metadata"), "location") or {}
    return {"content": markdown, "location": location}


def _live_collect(region: str) -> dict:
    """Tavily search + Firecrawl deep extraction for physical-pillar signals.

    Region-keyed queries (no site/org context), so this is safe in both
    org-grounded and region-guided runs. The key guard lives in collect().

    Tavily errors propagate (an auth/SDK failure fails the run loudly rather than
    silently producing an empty brief). Per-URL Firecrawl failures are tolerated
    — one unscrapable page should not abort the whole collection.
    """
    queries = [
        f"{region} unrest protest 2026",
        f"{region} terrorism attack 2026",
        f"{region} maritime shipping disruption 2026",
        f"{region} natural disaster 2026",
    ]

    raw_signals = []
    for q in queries:
        hits = _tavily_search(q, max_results=5)
        for hit in hits:
            try:
                extracted = _firecrawl_extract(hit.get("url", ""))
            except Exception as e:
                print(f"[osint_physical] extract failed for {hit.get('url', '')} — {e}", file=sys.stderr)
                continue
            if not extracted:
                continue
            raw_signals.append({
                "signal_id": f"osint:physical:{region.lower()}-{len(raw_signals) + 1:03d}",
                "title": hit.get("title", ""),
                "category": "physical",
                "pillar": "physical",
                "severity": 0,
                "location": extracted.get("location") or {},
                "url": hit.get("url", ""),
                "outlet": hit.get("source", ""),
                "source_count": 1,
                "published_at": hit.get("published_date", ""),
            })

    return {
        "region": region,
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pillar": "physical",
        "signals": raw_signals,
        "source_provenance": "tavily+firecrawl",
    }


REQUIRED_LIVE_KEYS = ("TAVILY_API_KEY", "FIRECRAWL_API_KEY")


def collect(region: str, mock: bool = True, require_live: bool = False) -> dict:
    region = region.upper()
    if region not in VALID_REGIONS:
        raise ValueError(f"invalid region '{region}' — must be one of {VALID_REGIONS}")

    # Live-only guard: if OSINT is requested live, fail loudly when the keys are
    # absent rather than silently falling back to mock fixtures.
    if require_live:
        missing = [k for k in REQUIRED_LIVE_KEYS if not os.environ.get(k)]
        if missing:
            raise ValueError(
                f"OSINT requested live but missing key(s): {', '.join(missing)}. "
                "Set them in .env, or run the pipeline without OSINT."
            )
        mock = False

    data = _mock_collect(region) if mock else _live_collect(region)

    out_dir = OUTPUT_ROOT / "regional" / region.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "osint_physical_signals.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[osint_physical] wrote {out_path}", file=sys.stderr)
    return data


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: osint_physical_collector.py REGION [--mock] [--require-live]", file=sys.stderr)
        sys.exit(1)
    region = args[0].upper()
    require_live = "--require-live" in args
    if require_live:
        mock = False  # collect() guards the keys and fails loudly if absent
    else:
        mock = "--mock" in args or not os.environ.get("TAVILY_API_KEY")
    try:
        collect(region, mock=mock, require_live=require_live)
    except (ValueError, FileNotFoundError) as e:
        print(f"[osint_physical] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
