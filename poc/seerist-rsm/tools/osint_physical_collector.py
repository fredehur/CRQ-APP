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
    geo = _geo_terms(region)
    return [f"{geo} {topic} 2026" for topic in _OSINT_TOPICS]


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
            "outlet": item.get("source", ""),
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


def _collect_raw(region: str) -> list[dict]:
    """Search (geo queries) -> scrape (truncated excerpt). Returns raw signal dicts."""
    scraped: list[dict] = []
    for q in _build_queries(region):
        hits = _tavily_search(q, max_results=5)
        for hit in hits:
            try:
                extracted = _firecrawl_extract(hit.get("url", ""))
            except Exception as e:
                print(f"[osint_physical] extract failed for {hit.get('url', '')} — {e}", file=sys.stderr)
                continue
            if not extracted:
                continue
            scraped.append({
                "title": hit.get("title", ""),
                "url": hit.get("url", ""),
                "source": hit.get("source", ""),
                "published_date": hit.get("published_date", ""),
                "content": _truncate(extracted.get("content", "")),
                "location": extracted.get("location") or {},
            })
    signals = []
    for i, item in enumerate(scraped, start=1):
        signals.append({
            "signal_id": f"osint:physical:{region.lower()}-{i:03d}",
            "title": item["title"],
            "url": item["url"],
            "outlet": item["source"],
            "published_at": item["published_date"],
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
            "title": s["title"], "url": s["url"], "source": s["outlet"],
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
