# OSINT Usage — Smart Enrichment + Brief Integration — Design

**Date:** 2026-05-22
**Slice:** `poc/seerist-rsm`
**Status:** Draft for review (after independent design review)

## Goal

Make the OSINT physical pillar a genuinely useful, first-class layer in the
daily brief, serving three roles relative to Seerist's structured event feed:

1. **Macro / strategic context** — region-wide developments Seerist's site-event
   feed misses (e.g. the Strait-of-Hormuz shipping disruption surfaced in the
   live run).
2. **Corroboration** — open-source confirmation of a same-day Seerist event,
   letting the analyst raise confidence/Admiralty.
3. **Early warning** — emerging issues not yet in Seerist.

## Why this is needed (live-run findings)

A live run exposed three blockers the current collector + wiring leave open:

- **Noise.** Queries use the region *code* (`"MED"`), which Tavily reads as
  "medical" — the run returned US Medicare/hurricane/health-sector junk; only
  ~5 of 14 hits were MED-relevant.
- **No substance.** The scraped article body is discarded
  (`osint_physical_collector._live_collect` keeps only title/url); `severity` is
  always 0, `location`/`published_at` empty. The analyst can only see a title.
- **Not wired in.** `prompts/rsm_regional_analyst_daily.md` has **zero**
  references to `osint_physical_signals`; `build_rsm_inputs` passes it only as a
  path string (never inlined, unlike `poi_proximity`). So even when present,
  nothing instructs the analyst to read or use it.

## Architecture

A 3-stage "smart collector" inside `tools/osint_physical_collector.py`, plus a
builder change to surface the result and a prompt change to consume it.

### Stage 1 — Search with geographic terms

Map the region code to a geographic query phrase so Tavily stops returning
"medical"/US noise:

```
REGION_QUERY_TERMS = {
  "MED":   "Mediterranean (Italy, Spain, Greece, Turkey, Morocco, Egypt)",
  "APAC":  "Asia-Pacific",
  "AME":   "Africa & Middle East",
  "LATAM": "Latin America",
  "NCE":   "Northern & Central Europe",
}
```

Queries become e.g. `"{geo_terms} unrest protest 2026"` for the four physical
topics (unrest, conflict/terrorism, maritime, disaster). This kills most noise
at the source.

### Stage 2 — Scrape, retain a truncated excerpt

Firecrawl `scrape(...)` (v4 SDK, per the OSINT live-fix) extracts main content.
**Retain a truncated excerpt** on each signal — mirror the parent's
`firecrawl_scraper._truncate` (middle-truncate to ~`_MAX_CHARS`, e.g. 3000 chars)
so the later LLM call cannot blow past context/cost. Per-URL Firecrawl failures
remain tolerated (skip that URL, continue).

### Stage 3 — One LLM enrichment pass (Anthropic Haiku)

A single `claude-haiku-4-5-20251001` call per region (reuse the parent's
`_call_llm` JSON-fence-strip + validation pattern), given: the truncated
excerpts **and** the day's Seerist events (read from
`output/regional/<region>/seerist_signals.json` if present). It emits, per item:

- `relevant` (bool) + `relevance_reason` — **noise filter**; only relevant items
  survive into the signals list.
- `summary` — 1–2 sentence factual digest of the body (the substance the
  analyst actually uses).
- `corroborates_event` — the Seerist `signal_id` this item supports, or `null`
  (a **candidate** the analyst confirms; not a hard claim).

**Deliberately NOT emitted by the collector:** `severity` and the brief-section
`role`. Those are the analyst's judgment (the analyst already assigns severity
with pillar anchors and decides early-warning framing). Keeping them out avoids
two layers assigning conflicting numbers — the collector does *collection
hygiene + linking*; the analyst remains the single judgment layer.

If `seerist_signals.json` is absent (e.g. standalone `osint_physical_collector.py
MED` outside `poc_runner`), set a top-level `seerist_unavailable: true` and skip
corroboration — so "not attempted" is distinguishable from "no overlap found".

### Output

`output/regional/<region>/osint_physical_signals.json` — signals gain
`summary`, `corroborates_event`, `content_excerpt`; top-level
`seerist_unavailable` and `dropped_count`. A sibling
`output/regional/<region>/osint_dropped.json` records dropped items **with their
`relevance_reason`** (audit trail — so an over-aggressive filter is visible, not
silent).

### Builder + prompt wiring (the consumer side)

- **`tools/rsm_input_builder.py`** — **inline** the enriched OSINT signals into
  the manifest (load the JSON, as it already does for `poi_proximity`), and
  surface a one-line OSINT summary in `manifest_summary` so the analyst sees it
  in the prepended manifest. Today it is only a path string in `optional`.
- **`prompts/rsm_regional_analyst_daily.md`** — add `osint_physical_signals` to
  the typed-inputs table and instruct the analyst to:
  - use `summary` items as **macro/strategic context** in SITUATION / PHYSICAL &
    GEOPOLITICAL;
  - when an item has `corroborates_event`, **cite it alongside that Seerist
    event** and may raise confidence/Admiralty;
  - route genuinely emerging items to **EARLY WARNING**;
  - **cite OSINT items by their `signal_id`** (`osint:physical:<region>-NNN`) —
    explicitly permitted; these flow through `claims.json` → `normalize_citations`
    → the APPENDIX exactly like Seerist signal_ids (verified working in the live
    brief test). The analyst assigns severity and section per its own anchors.

## Keys

`ANTHROPIC_API_KEY` is promoted to the **OSINT-required tier** alongside
`TAVILY_API_KEY` + `FIRECRAWL_API_KEY`. Guard in **both**
`osint_physical_collector.collect()` (`REQUIRED_LIVE_KEYS`) and
`poc_runner.phase_collect` (the `--osint --require-live` guard) — fail loudly if
absent. Update `.env.example`, `setup.prompt.md`, and `README` (which currently
frame ANTHROPIC as optional / not-needed-for-/crq-run).

## Data flow

```
phase_collect (osint on):
  seerist_collector  → output/regional/<r>/seerist_signals.json   (events)
  osint_physical_collector --require-live:
     Tavily (geo queries) → Firecrawl (truncated excerpt)
     → Haiku enrichment (excerpts + seerist events)
     → osint_physical_signals.json (relevant only) + osint_dropped.json
  build_rsm_inputs  → inlines enriched OSINT into the manifest
  → analyst (Copilot agent) reads OSINT, routes by content, cites signal_ids
  → prep-format → formatter → render
```

## Error handling

- OSINT-on + any of TAVILY/FIRECRAWL/ANTHROPIC missing (live) → fail loudly
  (both guards).
- Enrichment LLM returns bad JSON → `_call_llm` raises `ValueError` → surfaced;
  do not silently emit unenriched signals.
- All Firecrawl scrapes fail / Tavily returns nothing → write an empty
  `signals: []` with `seerist_unavailable`/`dropped_count` context (a clean
  "quiet OSINT" result, not a crash); the analyst's existing
  no-OSINT-this-period framing applies.
- `seerist_signals.json` absent → `seerist_unavailable: true`, corroboration
  skipped.

## Testing

- **Query mapping** — `REGION_QUERY_TERMS` produces geographic phrases (no raw
  region code in the Tavily query). Deterministic.
- **Truncation** — excerpts capped at the limit before the LLM call.
- **Enrichment (LLM mocked)** — assert the prompt includes the Seerist events and
  the excerpts; assert the parsed schema (relevant/summary/corroborates_event),
  that non-relevant items are dropped, and that dropped items land in
  `osint_dropped.json` with reasons.
- **Key guard** — OSINT-on + missing ANTHROPIC (and Tavily/Firecrawl) → fail
  loudly, in both `collect()` and `phase_collect`.
- **Builder inlining** — `build_rsm_inputs` loads enriched OSINT into the
  manifest and `manifest_summary` mentions it.
- **`seerist_unavailable`** — standalone run with no Seerist file sets the flag
  and skips corroboration.
- Live end-to-end remains an operator acceptance step (real keys + network).

## Out of scope

- The parent's full 3-LLM "target-centric" loop (working theory → search → gap
  assessment → synthesis). A single enrichment pass is sufficient here; graduate
  later only if relevance/quality demands it.
- Cyber-pillar OSINT (this is the physical pillar only).
- Automatic Admiralty recalculation — the analyst adjusts confidence by judgment.

## Files touched

`tools/osint_physical_collector.py` (3-stage enrichment, query map, truncation,
ANTHROPIC guard), `tools/rsm_input_builder.py` (inline enriched OSINT +
summary), `prompts/rsm_regional_analyst_daily.md` (typed input + routing
instructions), `tools/poc_runner.py` (ANTHROPIC in the `--osint` guard),
`.env.example` / `setup.prompt.md` / `README.md` (ANTHROPIC required for OSINT),
plus tests under `tests/`.
