# OSINT Collector — Noise Reduction Implementation Plan

> **Execution:** Built via the `/prime-dev` blueprint — orchestrator (Opus) owns ALL Bash; Builders (Sonnet, no Bash) write files and report `files_written` + `verify`; Validator (Sonnet, read-only) checks fidelity. Steps use checkbox (`- [ ]`).

**Goal:** Cut pre-enrichment noise in the OSINT physical collector. The live MED run produced 14 raw signals where ~43% were Medicare/healthcare semantic collisions, ~14% were US-domestic, and most had empty `published_at` / a URL stored in the `outlet` field. Fix these at the search and scrape layers so the enrichment agent gets high-signal raw data instead of doing damage control.

**Architecture:** All changes in `tools/osint_physical_collector.py`. Per-country queries replace the regional umbrella; Tavily call upgrades to `topic="news"` + `days=7` + `search_depth="advanced"` + `exclude_domains` + score pre-filter; raw signal shape gets a real `outlet` name (URL→publication map), a `published_at` fallback from Firecrawl metadata, broken-scrape filtering, and drops the unused `location` field.

**Tech Stack:** Python 3.11 + uv, pytest. Tavily/Firecrawl mocked in tests.

Source review: in-context review from 2026-05-25 (see prior message). Paths relative to `poc/seerist-rsm/`.

---

## File structure

- `tools/osint_physical_collector.py` — restructure `_build_queries`, upgrade `_tavily_search`, harden `_collect_raw`, normalize raw shape.
- `tests/test_osint_physical.py` + `tests/test_osint_enrichment.py` — new + adjusted tests.

---

## Task 1: Per-country queries with topic-specific negative terms

**Files:**
- Modify: `tools/osint_physical_collector.py`
- Test: `tests/test_osint_physical.py`

The current umbrella query `"Mediterranean (Italy, Spain, Greece, Turkey, Morocco, Egypt) unrest protest 2026"` produces weak relevance. Split into per-country queries with topic-specific negative terms.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_osint_physical.py
def test_build_queries_uses_per_country_not_umbrella():
    qs = opc._build_queries("MED")
    # MED has 6+ countries → at least 6 queries; current returns 4
    assert len(qs) >= 6
    # No umbrella term — each query names a specific country
    assert not any("Mediterranean" in q for q in qs)
    # Country names appear
    joined = " | ".join(qs)
    for c in ("Italy", "Spain", "Greece", "Turkey", "Morocco", "Egypt"):
        assert c in joined, f"missing country in queries: {c}"


def test_build_queries_includes_negative_terms_for_med_collision():
    qs = opc._build_queries("MED")
    # at least one MED query must exclude Medicare/healthcare to break the semantic collision
    assert any("-Medicare" in q or "-healthcare" in q for q in qs)


def test_build_queries_other_regions_unchanged_shape():
    # APAC/AME/LATAM/NCE keep umbrella behavior (no country split yet) but the
    # function must still return a non-empty list and reference the region geo term
    for r in ("APAC", "AME", "LATAM", "NCE"):
        qs = opc._build_queries(r)
        assert qs, f"empty queries for {r}"
        assert any(any(tok in q for tok in opc._geo_terms(r).split()) for q in qs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_osint_physical.py -k "per_country or negative_terms" -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `tools/osint_physical_collector.py`:

(a) Add a per-country mapping above `REGION_QUERY_TERMS`:

```python
REGION_COUNTRIES = {
    "MED": ["Italy", "Spain", "Greece", "Turkey", "Morocco", "Egypt", "Tunisia", "Libya"],
    # Other regions keep umbrella behavior for now (per-country fan-out comes later).
}

REGION_NEGATIVE_TERMS = {
    # MED collides hard with "Medicare"/"medical" in US news. Strip them at search time.
    "MED": "-Medicare -healthcare -insurance",
}
```

(b) Rewrite `_build_queries`:

```python
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
```

(c) Drop `max_results` for `_tavily_search` calls in `_collect_raw` from 5 to 3 (more queries × fewer results each = better coverage with similar credit usage). This is in `_collect_raw`:

```python
hits = _tavily_search(q, max_results=3)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_osint_physical.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/osint_physical_collector.py tests/test_osint_physical.py
git commit -m "feat(osint): per-country queries + negative terms break MED/Medicare collision"
```

---

## Task 2: Tavily upgrades — news topic + recency + advanced + exclude_domains + score gate

**Files:**
- Modify: `tools/osint_physical_collector.py`
- Test: `tests/test_osint_physical.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_osint_physical.py
def test_tavily_search_uses_news_recency_advanced(monkeypatch):
    captured = {}
    class FakeClient:
        def __init__(self, api_key): pass
        def search(self, query, **kwargs):
            captured.update(kwargs)
            captured["query"] = query
            return {"results": []}
    monkeypatch.setattr("tavily.TavilyClient", FakeClient)
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    opc._tavily_search("Italy unrest 2026")
    assert captured.get("topic") == "news"
    assert captured.get("days") == 7
    assert captured.get("search_depth") == "advanced"


def test_tavily_search_includes_exclude_domains(monkeypatch):
    captured = {}
    class FakeClient:
        def __init__(self, api_key): pass
        def search(self, query, **kwargs):
            captured.update(kwargs)
            return {"results": []}
    monkeypatch.setattr("tavily.TavilyClient", FakeClient)
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    opc._tavily_search("anything")
    exclude = captured.get("exclude_domains") or []
    # Known noise domains from the 2026-05-22 live run
    for d in ("medicare2026.healthplan.org", "health-isac.org", "aha.org", "directrelief.org"):
        assert d in exclude, f"exclude_domains missing {d}"


def test_collect_raw_drops_low_score_results(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(opc, "_build_queries", lambda region: ["q"])
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=3: [
        {"title": "Good", "url": "http://a", "source": "http://a", "published_date": "", "summary": "", "score": 0.82},
        {"title": "Junk", "url": "http://b", "source": "http://b", "published_date": "", "summary": "", "score": 0.15},
    ])
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {"content": "C" * 500, "location": {}})
    sigs = opc._collect_raw("MED")
    # Only the high-score item kept
    assert len(sigs) == 1
    assert sigs[0]["url"] == "http://a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_osint_physical.py -k "news_recency or exclude_domains or low_score" -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

(a) Add a module-level constant block above `_tavily_search`:

```python
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
```

(b) Replace the `_tavily_search` body:

```python
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
```

(c) In `_collect_raw`, pre-filter on score before the scrape call:

```python
    scraped: list[dict] = []
    for q in _build_queries(region):
        hits = _tavily_search(q, max_results=3)
        for hit in hits:
            if (hit.get("score") or 0.0) < TAVILY_SCORE_FLOOR:
                continue
            try:
                extracted = _firecrawl_extract(hit.get("url", ""))
            except Exception as e:
                print(f"[osint_physical] extract failed for {hit.get('url', '')} — {e}", file=sys.stderr)
                continue
            ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_osint_physical.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/osint_physical_collector.py tests/test_osint_physical.py
git commit -m "feat(osint): Tavily news topic + recency + score gate + exclude_domains"
```

---

## Task 3: Raw shape cleanup — real outlet name, published_at fallback, broken-scrape filter, drop location

**Files:**
- Modify: `tools/osint_physical_collector.py`
- Test: `tests/test_osint_physical.py` + `tests/test_osint_enrichment.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_osint_physical.py
def test_outlet_name_maps_known_domains():
    assert opc._outlet_name("https://www.npr.org/2026/05/01/x") == "NPR"
    assert opc._outlet_name("https://www.reuters.com/world/eu/x") == "Reuters"
    assert opc._outlet_name("https://en.wikipedia.org/wiki/X") == "Wikipedia"
    assert opc._outlet_name("https://www.aljazeera.com/news/x") == "Al Jazeera"
    # Unknown domain falls back to the bare domain (no scheme, no www)
    assert opc._outlet_name("https://obscure.example.com/x") == "obscure.example.com"
    # Bad input
    assert opc._outlet_name("") == ""
    assert opc._outlet_name(None) == ""


def test_collect_raw_uses_outlet_name_not_url(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(opc, "_build_queries", lambda region: ["q"])
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=3: [
        {"title": "Article", "url": "https://www.npr.org/2026/01/x", "source": "https://www.npr.org/2026/01/x",
         "published_date": "", "summary": "", "score": 0.9}
    ])
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {"content": "C" * 500, "metadata": {}})
    sigs = opc._collect_raw("MED")
    assert sigs[0]["outlet"] == "NPR"
    assert sigs[0]["outlet"] != sigs[0]["url"]


def test_collect_raw_falls_back_to_firecrawl_published_at(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(opc, "_build_queries", lambda region: ["q"])
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=3: [
        {"title": "T", "url": "http://a", "source": "http://a",
         "published_date": "", "summary": "", "score": 0.9}
    ])
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {
        "content": "C" * 500,
        "metadata": {"publishedTime": "2026-05-21T10:00:00Z"},
    })
    sigs = opc._collect_raw("MED")
    assert sigs[0]["published_at"] == "2026-05-21T10:00:00Z"


def test_collect_raw_drops_broken_scrapes(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(opc, "_build_queries", lambda region: ["q"])
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=3: [
        {"title": "Home", "url": "http://a", "source": "http://a", "published_date": "", "summary": "", "score": 0.9},
        {"title": "", "url": "http://b", "source": "http://b", "published_date": "", "summary": "", "score": 0.9},
        {"title": "Real Article", "url": "http://c", "source": "http://c", "published_date": "", "summary": "", "score": 0.9},
    ])
    # First two have valid content but bad titles; the real one has enough content
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {"content": "C" * 500, "metadata": {}})
    sigs = opc._collect_raw("MED")
    assert len(sigs) == 1
    assert sigs[0]["title"] == "Real Article"


def test_collect_raw_drops_short_content(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(opc, "_build_queries", lambda region: ["q"])
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=3: [
        {"title": "T", "url": "http://a", "source": "http://a", "published_date": "", "summary": "", "score": 0.9}
    ])
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {"content": "tiny", "metadata": {}})
    sigs = opc._collect_raw("MED")
    assert sigs == []


def test_collect_raw_no_location_field(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(opc, "_build_queries", lambda region: ["q"])
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=3: [
        {"title": "Article", "url": "http://a", "source": "http://a", "published_date": "", "summary": "", "score": 0.9}
    ])
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {"content": "C" * 500, "metadata": {}})
    sigs = opc._collect_raw("MED")
    # location field was always empty {} — drop it from the raw shape
    assert "location" not in sigs[0]
```

Also update `tests/test_osint_enrichment.py::test_live_collect_raw_default_no_enrichment` so its `_firecrawl_extract` mock returns the new metadata-bearing dict shape (`{"content": ..., "metadata": {}}`), not the old `{"content": ..., "location": {}}`. The assertion `assert len(s["content_excerpt"]) <= 3100` and the `"summary" not in s and "corroborates_event" not in s` checks stay.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_osint_physical.py tests/test_osint_enrichment.py -k "outlet_name or outlet_not_url or published_at or broken_scrapes or short_content or no_location" -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

(a) Add an `_outlet_name` helper above `_collect_raw`:

```python
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


def _outlet_name(url: str | None) -> str:
    """Map a URL to a human-readable publication name. Unknown domains fall back
    to the bare domain (no scheme, no www)."""
    if not url:
        return ""
    import re
    m = re.match(r"https?://([^/]+)", url)
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


CONTENT_MIN_CHARS = 200
BROKEN_TITLES = {"", "home", "homepage", "404", "not found"}
```

(b) Update `_firecrawl_extract` to keep `metadata` (not just `location`) on the returned dict:

```python
def _firecrawl_extract(url: str) -> dict | None:
    """Firecrawl main-content extract via firecrawl-py v4. Requires FIRECRAWL_API_KEY.
    Returns {content, metadata} or None on empty extraction."""
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
```

(c) Rewrite the signal-building loop in `_collect_raw` to (i) skip broken titles, (ii) skip short content, (iii) compute outlet name, (iv) fall back to Firecrawl metadata for published_at, (v) drop the `location` field:

```python
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
```

(d) Update the `--enrich-api` path in `_live_collect` so it reshapes the new raw signals into what `_enrich`/`_apply_enrichment` expect (the existing code already does this via `for s in _collect_raw(region)`). The rebuilt scraped list there uses `s["outlet"]` as `source`; that's now a publication name, not a URL. Update the rebuild to use `s["url"]` for the `source` field (which the enrichment path treats as URL):

```python
    scraped = [
        {
            "title": s["title"], "url": s["url"], "source": s["url"],
            "published_date": s["published_at"], "content": s["content_excerpt"],
        }
        for s in _collect_raw(region)
    ]
```

(e) Update `_apply_enrichment` (signal-building branch around line 116) — the enriched `outlet` field needs to come from `_outlet_name`, not from `item.get("source")` which is now a URL:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_osint_physical.py tests/test_osint_enrichment.py -q`
Expected: PASS (all). Check no regressions in the rev-2 raw-default test and enrich-api test.

- [ ] **Step 5: Commit**

```bash
git add tools/osint_physical_collector.py tests/test_osint_physical.py tests/test_osint_enrichment.py
git commit -m "feat(osint): real outlet names, published_at fallback, broken-scrape filter; drop location"
```

---

## Task 4: Enrichment prompt — surface new fields, document the cross-region maritime convention

**Files:**
- Modify: `prompts/rsm_osint_enrichment.md`

The agent enrichment prompt currently mentions `outlet` and `published_at` as inputs but does not call out that they are now populated reliably, nor does it tell the agent how to handle cross-region maritime signals (Hormuz → MED via Suez routing). Add one short paragraph to the prompt rules.

- [ ] **Step 1: Edit the prompt**

In `prompts/rsm_osint_enrichment.md`, add to the Rules section (after the existing "corroborates_event" bullet):

```markdown
- **Cross-region maritime is in-scope when it cascades.** Strait of Hormuz / Suez
  Canal / Bab-el-Mandeb disruption affects MED shipping even though the incident
  is in AME. Keep these items and use `corroborates_event` to link to any MED-side
  Seerist event (e.g., a Suez backlog notice). If no MED-side cascade is observable,
  drop the item with `relevance_reason: "off-region; no MED cascade"`.
- **Outlet attribution:** `outlet` now contains a publication name (NPR, Reuters,
  Wikipedia, etc.), not a URL. Use it verbatim in `summary` when attribution helps.
- **Date:** `published_at` is best-effort — empty when both Tavily and Firecrawl
  return no date. Do not invent dates.
```

- [ ] **Step 2: Static check**

Run: `python -c "t=open('prompts/rsm_osint_enrichment.md',encoding='utf-8').read(); assert 'Cross-region maritime' in t and 'Suez' in t and 'outlet' in t.lower(); print('enrichment prompt OK')"`
Expected: `enrichment prompt OK`.

- [ ] **Step 3: Commit**

```bash
git add prompts/rsm_osint_enrichment.md
git commit -m "docs(osint): enrichment prompt — cross-region maritime cascade + new outlet/date semantics"
```

---

## Task 5: Full verification (orchestrator)

**Files:** none

- [ ] **Step 1: OSINT suites**

Run: `python -m pytest tests/test_osint_enrichment.py tests/test_osint_physical.py -q`
Expected: PASS.

- [ ] **Step 2: No regressions across the full truststore-independent suite**

Run: `python -m pytest tests/test_osint_enrichment.py tests/test_osint_physical.py tests/test_crq_run.py tests/test_no_org_context.py tests/test_validate_brief.py tests/test_render_brief_html.py tests/test_normalize_citations.py tests/test_seerist_collector.py -q`
Expected: PASS (all).

- [ ] **Step 3: Compile**

Run: `python -m py_compile tools/osint_physical_collector.py && echo OK`
Expected: `OK`.

- [ ] **Step 4: Live spot-check (operator)**

The operator (separately) re-runs the live MED OSINT collect and inspects the
output count + the proportion of Medicare/healthcare titles. Expected outcome:
visible noise from the 2026-05-22 baseline (43% Medicare) drops to near-zero;
total kept signals may shrink (fewer false positives), and `outlet` shows
publication names rather than URLs.

---

## Notes for the implementer

- **All edits in one file** (`tools/osint_physical_collector.py`) plus its tests and the enrichment prompt. No changes to `poc_runner.py`, `crq_run.py`, or the analyst/formatter prompts.
- **Network/Tavily/Firecrawl mocked in tests** — never call live.
- **Per-country fan-out only for MED in this pass.** APAC/AME/LATAM/NCE keep the umbrella `_geo_terms` for now; they can be expanded in a follow-up once we have similar live-run data to anchor the country lists.
- **Score floor 0.4** is a defensible default — most Tavily news results above 0.4 are on-topic; below tends to be tangential. Tunable.
- **`exclude_domains` is a known-noise allowlist**, not an opinion on the publisher. We add to it when a domain *demonstrably* pollutes results across multiple regions.
- **The enrichment agent is still the final filter** — these are upstream improvements that reduce its workload, not replace it.
