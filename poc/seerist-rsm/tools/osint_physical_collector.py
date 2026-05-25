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
import re as _re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")
from dotenv import load_dotenv

# Use the OS trust store (e.g. a corporate proxy's CA) for the live Tavily /
# Firecrawl HTTPS calls. Guarded so machines without truststore (or without a
# proxy) still work via the default certifi bundle. Mirrors seerist_client.py.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

load_dotenv()

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = REPO_ROOT / "output"
FIXTURES_DIR = REPO_ROOT / "data" / "mock_osint_fixtures"

REGION_COUNTRIES = {
    "MED": ["Italy", "Spain", "Greece", "Turkey", "Morocco", "Egypt", "Tunisia", "Libya"],
    # Other regions keep umbrella behavior for now (per-country fan-out comes later).
}

REGION_NEGATIVE_TERMS = {
    # MED collides hard with "Medicare"/"medical" in US news. Strip them at search time.
    "MED": "-Medicare -healthcare -insurance",
}

REGION_QUERY_TERMS = {
    "MED": "Mediterranean (Italy, Spain, Greece, Turkey, Morocco, Egypt)",
    "APAC": "Asia-Pacific",
    "AME": "Africa and Middle East",
    "LATAM": "Latin America",
    "NCE": "Northern and Central Europe",
}
_OSINT_TOPICS = [
    "unrest protest",
    "armed conflict terrorism",
    "maritime shipping disruption",
    "natural disaster",
]


def _geo_terms(region: str) -> str:
    return REGION_QUERY_TERMS.get(region.upper(), region)


def _build_queries(region: str) -> list[str]:
    """Per-country fan-out where defined; falls back to the umbrella geo term."""
    countries = REGION_COUNTRIES.get(region.upper())
    negative = REGION_NEGATIVE_TERMS.get(region.upper(), "")
    if countries:
        return [
            f"{country} {topic} 2026 {negative}".strip()
            for country in countries
            for topic in _OSINT_TOPICS
        ]
    geo = _geo_terms(region)
    return [f"{geo} {topic} 2026 {negative}".strip() for topic in _OSINT_TOPICS]


def _truncate(text: str | None, max_chars: int = 3000) -> str:
    """Middle-truncate scraped content so the enrichment LLM call cannot blow
    past context/cost. Mirrors firecrawl_scraper._truncate in the parent repo."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n…[truncated]…\n" + text[-half:]


def _load_seerist_events(region: str, output_root: Path | None = None) -> tuple[list[dict], bool]:
    """Return (events, seerist_unavailable). events is a compact list for the
    enrichment prompt's corroboration step. Absent file → ([], True)."""
    root = output_root or OUTPUT_ROOT
    path = root / "regional" / region.lower() / "seerist_signals.json"
    if not path.exists():
        return [], True
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [], True
    events = [
        {
            "signal_id": e.get("signal_id", ""),
            "title": e.get("title", ""),
            "category": e.get("category", ""),
        }
        for e in doc.get("situational", {}).get("events", [])
    ]
    return events, False


def _apply_enrichment(region: str, scraped: list[dict], verdicts: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split scraped items into kept signals (relevant) and dropped items, using
    the LLM verdicts (keyed by index). Re-numbers kept signal_ids 001..N."""
    by_index = {v.get("index"): v for v in verdicts}
    signals: list[dict] = []
    dropped: list[dict] = []
    seq = 0
    for i, item in enumerate(scraped):
        v = by_index.get(i, {"relevant": False, "relevance_reason": "no enrichment verdict"})
        if not v.get("relevant"):
            dropped.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "relevance_reason": v.get("relevance_reason", ""),
            })
            continue
        seq += 1
        signals.append({
            "signal_id": f"osint:physical:{region.lower()}-{seq:03d}",
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "outlet": _outlet_name(item.get("url", "")),
            "published_at": item.get("published_date", ""),
            "content_excerpt": item.get("content", ""),
            "summary": v.get("summary", ""),
            "corroborates_event": v.get("corroborates_event"),
            "pillar": "physical",
            "category": "physical",
        })
    return signals, dropped


def _call_llm(prompt: str, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 2048) -> dict:
    """One Anthropic call; strip markdown fences; parse JSON. Mirrors the parent
    osint_collector._call_llm. Raises ValueError on non-JSON."""
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    text = _re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=_re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"enrichment LLM returned non-JSON: {text[:200]!r}") from exc


def _enrich(region: str, scraped: list[dict], seerist_events: list[dict]) -> list[dict]:
    """Build the enrichment prompt (truncated items + seerist events) and return
    the per-item verdicts list."""
    items_txt = "\n\n".join(
        f"[{i}] {it.get('title', '')} ({it.get('url', '')})\n{it.get('content', '')[:1500]}"
        for i, it in enumerate(scraped)
    ) or "(no items)"
    ev_txt = "\n".join(
        f"- {e['signal_id']}: {e['title']} ({e['category']})" for e in (seerist_events or [])
    ) or "(none available)"
    geo = _geo_terms(region)
    prompt = f"""You are filtering OSINT physical-risk search results for the {region} region ({geo}).

SEERIST EVENTS TODAY (for corroboration):
{ev_txt}

OSINT ITEMS (index, title, url, content excerpt):
{items_txt}

For EACH item, decide if it is genuinely relevant to {region} PHYSICAL risk
(unrest, armed conflict/terrorism, maritime/shipping disruption, natural
disaster affecting the region). Drop items that are off-region or off-topic
(e.g. US-domestic, healthcare/Medicare, generic explainers).

Return ONLY JSON (no markdown fences):
{{"items": [
  {{"index": <int>, "relevant": <bool>, "relevance_reason": "<short>",
    "summary": "<1-2 sentence factual summary of the item body>",
    "corroborates_event": "<a SEERIST signal_id from the list above that this item supports, or null>"}}
]}}
Include one object per OSINT item index. summary/corroborates_event may be omitted when relevant is false."""
    result = _call_llm(prompt)
    return result.get("items", [])


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


# Domains observed dominating the MED live run with US-healthcare / Medicare /
# disaster-prep noise that triggers on "Med-" stem. Permanent allowlist exclude.
TAVILY_EXCLUDE_DOMAINS = [
    "medicare2026.healthplan.org",
    "health-isac.org",
    "aha.org",
    "directrelief.org",
    "files.asprtracie.hhs.gov",
    "societyfordisastermedicineandpublichealthinc.wildapricot.org",
    "automotivelogistics.media",  # niche industry blog, low news value
]

# Tavily relevance score floor — drop garbage before paying for Firecrawl scrape.
TAVILY_SCORE_FLOOR = 0.4


def _tavily_search(query: str, max_results: int = 3) -> list[dict]:
    """Tavily news search via the official tavily-python SDK. Requires TAVILY_API_KEY.

    Uses topic="news" + days=7 + search_depth="advanced" + exclude_domains for the
    daily-brief use case. Errors propagate so an auth/SDK failure fails the run
    loudly instead of yielding an empty brief.
    """
    from tavily import TavilyClient

    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    resp = client.search(
        query,
        max_results=max_results,
        topic="news",
        days=7,
        search_depth="advanced",
        exclude_domains=TAVILY_EXCLUDE_DOMAINS,
    )
    results = _field(resp, "results") or []
    return [
        {
            "title": _field(r, "title") or "",
            "url": _field(r, "url") or "",
            "source": _field(r, "url") or "",
            "published_date": _field(r, "published_date") or "",
            "summary": _field(r, "content") or "",
            "score": _field(r, "score") or 0.0,
        }
        for r in results
    ]


def _firecrawl_extract(url: str) -> dict | None:
    """Firecrawl main-content extract via firecrawl-py v4. Requires FIRECRAWL_API_KEY.

    v4 SDK: `Firecrawl(api_key=...).scrape(url, formats=["markdown"],
    only_main_content=True)` returns a Document (attribute access). Field reads
    go through `_field` to tolerate dict-vs-object differences across v4 point
    releases. Returns {content, metadata} or None on empty extraction.
    """
    if not url:
        return None
    from firecrawl import Firecrawl

    app = Firecrawl(api_key=os.environ["FIRECRAWL_API_KEY"])
    doc = app.scrape(url, formats=["markdown"], only_main_content=True)
    markdown = (_field(doc, "markdown") or "").strip()
    if not markdown:
        return None
    metadata = _field(doc, "metadata") or {}
    return {"content": markdown, "metadata": metadata}


OUTLET_NAME_MAP = {
    "npr.org": "NPR",
    "reuters.com": "Reuters",
    "apnews.com": "AP",
    "bbc.com": "BBC",
    "bbc.co.uk": "BBC",
    "aljazeera.com": "Al Jazeera",
    "ft.com": "Financial Times",
    "wsj.com": "WSJ",
    "nytimes.com": "New York Times",
    "washingtonpost.com": "Washington Post",
    "theguardian.com": "The Guardian",
    "lemonde.fr": "Le Monde",
    "elpais.com": "El País",
    "spiegel.de": "Der Spiegel",
    "wikipedia.org": "Wikipedia",
    "breakingdefense.com": "Breaking Defense",
    "seavantage.com": "Sea Vantage",
    "dni.gov": "US DNI",
    "bloomberg.com": "Bloomberg",
}

CONTENT_MIN_CHARS = 200
BROKEN_TITLES = {"", "home", "homepage", "404", "not found"}


def _outlet_name(url: str | None) -> str:
    """Map a URL to a human-readable publication name. Unknown domains fall back
    to the bare domain (no scheme, no www)."""
    if not url:
        return ""
    m = _re.match(r"https?://([^/]+)", url)
    if not m:
        return ""
    host = m.group(1).lower()
    if host.startswith("www."):
        host = host[4:]
    # Match longest suffix in the map
    for suffix, name in sorted(OUTLET_NAME_MAP.items(), key=lambda kv: -len(kv[0])):
        if host == suffix or host.endswith("." + suffix):
            return name
    return host


def _collect_raw(region: str) -> list[dict]:
    """Search (geo queries) -> scrape (truncated excerpt). Returns raw signal dicts.
    Filters: Tavily score floor, broken titles, short content."""
    scraped: list[dict] = []
    for q in _build_queries(region):
        hits = _tavily_search(q, max_results=3)
        for hit in hits:
            if (hit.get("score") or 0.0) < TAVILY_SCORE_FLOOR:
                continue
            title = (hit.get("title") or "").strip()
            if title.lower() in BROKEN_TITLES:
                continue
            try:
                extracted = _firecrawl_extract(hit.get("url", ""))
            except Exception as e:
                print(f"[osint_physical] extract failed for {hit.get('url', '')} — {e}", file=sys.stderr)
                continue
            if not extracted:
                continue
            content = extracted.get("content", "")
            if len(content) < CONTENT_MIN_CHARS:
                continue
            metadata = extracted.get("metadata") or {}
            published_at = (
                hit.get("published_date")
                or _field(metadata, "publishedTime")
                or _field(metadata, "article:published_time")
                or _field(metadata, "dc.date")
                or ""
            )
            scraped.append({
                "title": title,
                "url": hit.get("url", ""),
                "outlet": _outlet_name(hit.get("url", "")),
                "published_at": published_at,
                "content": _truncate(content),
            })
    signals = []
    for i, item in enumerate(scraped, start=1):
        signals.append({
            "signal_id": f"osint:physical:{region.lower()}-{i:03d}",
            "title": item["title"],
            "url": item["url"],
            "outlet": item["outlet"],
            "published_at": item["published_at"],
            "content_excerpt": item["content"],
            "pillar": "physical",
            "category": "physical",
        })
    return signals


def _live_collect(region: str, enrich_api: bool = False) -> dict:
    """Default: RAW signals (no LLM). enrich_api=True: in-process Haiku enrichment
    (optional/headless path); the normal flow enriches via the Copilot agent."""
    base = {
        "region": region,
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pillar": "physical",
        "source_provenance": "tavily+firecrawl",
    }
    if not enrich_api:
        base["signals"] = _collect_raw(region)
        return base

    # Optional in-process enrichment (kept for headless/CI use).
    # Rebuild scraped items with the same shape _enrich/_apply_enrichment expect.
    scraped = [
        {
            "title": s["title"], "url": s["url"], "source": s["url"],
            "published_date": s["published_at"], "content": s["content_excerpt"],
        }
        for s in _collect_raw(region)
    ]
    seerist_events, seerist_unavailable = _load_seerist_events(region)
    verdicts = _enrich(region, scraped, seerist_events) if scraped else []
    signals, dropped = _apply_enrichment(region, scraped, verdicts)

    # dropped-items audit trail (so over-aggressive filtering is visible)
    out_dir = OUTPUT_ROOT / "regional" / region.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "osint_dropped.json").write_text(
        json.dumps({"region": region, "dropped": dropped}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    base.update({
        "seerist_unavailable": seerist_unavailable,
        "dropped_count": len(dropped),
        "signals": signals,
        "source_provenance": "tavily+firecrawl+haiku",
    })
    return base


REQUIRED_LIVE_KEYS = ("TAVILY_API_KEY", "FIRECRAWL_API_KEY")
ENRICH_API_KEYS = ("ANTHROPIC_API_KEY",)


def collect(region: str, mock: bool = True, require_live: bool = False, enrich_api: bool = False) -> dict:
    region = region.upper()
    if region not in VALID_REGIONS:
        raise ValueError(f"invalid region '{region}' — must be one of {VALID_REGIONS}")

    # Live-only guard: if OSINT is requested live, fail loudly when the keys are
    # absent rather than silently falling back to mock fixtures. ANTHROPIC is only
    # required on the optional --enrich-api path.
    if require_live:
        needed = REQUIRED_LIVE_KEYS + (ENRICH_API_KEYS if enrich_api else ())
        missing = [k for k in needed if not os.environ.get(k)]
        if missing:
            raise ValueError(
                f"OSINT requested live but missing key(s): {', '.join(missing)}. "
                "Set them in .env, or run the pipeline without OSINT."
            )
        mock = False

    data = _mock_collect(region) if mock else _live_collect(region, enrich_api=enrich_api)

    out_dir = OUTPUT_ROOT / "regional" / region.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "osint_physical_signals.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[osint_physical] wrote {out_path}", file=sys.stderr)
    return data


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: osint_physical_collector.py REGION [--mock] [--require-live] [--enrich-api]", file=sys.stderr)
        sys.exit(1)
    region = args[0].upper()
    require_live = "--require-live" in args
    enrich_api = "--enrich-api" in args
    if require_live:
        mock = False  # collect() guards the keys and fails loudly if absent
    else:
        mock = "--mock" in args or not os.environ.get("TAVILY_API_KEY")
    try:
        collect(region, mock=mock, require_live=require_live, enrich_api=enrich_api)
    except (ValueError, FileNotFoundError) as e:
        print(f"[osint_physical] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
