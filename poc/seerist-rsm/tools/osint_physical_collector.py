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


def _live_collect(region: str) -> dict:
    """Tavily search + Firecrawl deep extraction for physical-pillar signals.

    Mirrors tools/osint_collector.py for the cyber pillar — same APIs, same
    shape, different category filters.
    """
    try:
        from tools.osint_collector import (
            _tavily_search,
            _firecrawl_extract,
        )
    except ImportError:
        print("[osint_physical] osint_collector helpers unavailable — falling back to mock",
              file=sys.stderr)
        return _mock_collect(region)

    if not os.environ.get("TAVILY_API_KEY"):
        print("[osint_physical] no TAVILY_API_KEY — falling back to mock", file=sys.stderr)
        return _mock_collect(region)

    queries = [
        f"{region} unrest protest 2026",
        f"{region} terrorism attack 2026",
        f"{region} maritime shipping disruption 2026",
        f"{region} natural disaster 2026",
    ]

    raw_signals = []
    for q in queries:
        try:
            hits = _tavily_search(q, max_results=5)
            for hit in hits:
                extracted = _firecrawl_extract(hit.get("url", ""))
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
        except Exception as e:
            print(f"[osint_physical] query failed: {q} — {e}", file=sys.stderr)

    return {
        "region": region,
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pillar": "physical",
        "signals": raw_signals,
        "source_provenance": "tavily+firecrawl",
    }


def collect(region: str, mock: bool = True) -> dict:
    region = region.upper()
    if region not in VALID_REGIONS:
        raise ValueError(f"invalid region '{region}' — must be one of {VALID_REGIONS}")

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
        print("Usage: osint_physical_collector.py REGION [--mock]", file=sys.stderr)
        sys.exit(1)
    region = args[0].upper()
    mock = "--mock" in args or not os.environ.get("TAVILY_API_KEY")
    try:
        collect(region, mock=mock)
    except (ValueError, FileNotFoundError) as e:
        print(f"[osint_physical] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
