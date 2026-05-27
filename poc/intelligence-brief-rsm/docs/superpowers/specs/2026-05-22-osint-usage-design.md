# OSINT Usage — Agent Enrichment + Brief Integration — Design

**Date:** 2026-05-22
**Slice:** `poc/seerist-rsm`
**Status:** Draft for review — **revision 2** (enrichment moved from a baked-in
Anthropic API call to a provider-agnostic Copilot-agent step; API path optional)

## Goal

Make the OSINT physical pillar a useful, low-noise, first-class layer serving
three roles vs Seerist's structured event feed: **macro/strategic context**,
**corroboration** of Seerist events, and **early warning**.

## Why this revision

The pipeline's LLM work (analyst, formatter) runs **through the Copilot agent**
(Copilot Enterprise models), not an API key. OSINT enrichment must follow the
same pattern: a **provider-agnostic agent step**, not a subprocess Anthropic
call. The API-based enrichment (rev 1, commit `2115235`) is **retained as an
optional `--enrich-api` path** for headless/CI use "later"; it is no longer the
default, and `ANTHROPIC_API_KEY` is no longer an OSINT-required key.

## Live-run findings this addresses (unchanged from rev 1)

- **Noise** — region *code* `"MED"` → Tavily returns "medical"/US junk.
- **No substance** — scraped body discarded; only title kept.
- **Not wired in** — analyst prompt + manifest didn't surface OSINT.

## Architecture

Three pieces: a **raw collector** (deterministic), a **provider-agnostic
enrichment agent step** (the new locus of judgment), and **manifest/prompt
wiring**.

### 1. Collector → raw signals only (deterministic, no LLM)

`tools/osint_physical_collector.py` default path:
- **Geographic queries** — `REGION_QUERY_TERMS` maps the code to a geographic
  phrase (`MED → "Mediterranean (Italy, Spain, Greece, Turkey, Morocco,
  Egypt)"`); queries `"{geo} {topic} 2026"` for unrest/conflict/maritime/disaster.
- **Scrape + truncated excerpt** — Firecrawl main content, middle-truncated
  (`_truncate`, ~3000 chars) and retained as `content_excerpt`.
- Writes **raw** `osint_physical_signals.json`: every scraped item as a signal
  (`signal_id`, `title`, `url`, `outlet`, `published_at`, `content_excerpt`,
  `pillar`), `source_provenance: "tavily+firecrawl"`. **No** `summary`,
  `corroborates_event`, relevance-drop, or `dropped_count` yet — those come from
  the enrichment step.
- **Required live keys: `TAVILY_API_KEY` + `FIRECRAWL_API_KEY`** only.
- **Optional `--enrich-api`** — runs the rev-1 in-process enrichment
  (`_enrich`/`_call_llm`, Anthropic Haiku) and emits the enriched shape directly.
  Only this path requires `ANTHROPIC_API_KEY` (guarded). For headless/CI; not the
  default.

### 2. Enrichment as a provider-agnostic agent step

Mirrors the existing analyst/formatter request-file pattern. New prompt
`prompts/rsm_osint_enrichment.md` (provider-agnostic). When OSINT is on,
`poc_runner` writes `osint_enrich_request.md` (the prompt + paths to the raw
`osint_physical_signals.json` and the day's `seerist_signals.json`). The Copilot
agent runs it and **rewrites `osint_physical_signals.json` enriched**:
- per kept signal: add `summary` (1–2 sentence factual digest of
  `content_excerpt`) and `corroborates_event` (a Seerist `signal_id` it supports,
  or null);
- **drop** off-region/off-topic items, recording them in `osint_dropped.json`
  with a `relevance_reason`;
- set top-level `dropped_count`; set `seerist_unavailable: true` if the Seerist
  file was absent (corroboration not attempted).

The agent does **not** assign `severity` or brief-section `role` — those remain
the analyst's job (single judgment layer). The enrichment is *hygiene + linking*.

Uses whatever Copilot Enterprise model is selected — **no API key**.

### 3. poc_runner phase split + manifest/prompt wiring

- **Split `phase_collect`** into:
  - *collect signals* — seerist collect, raw OSINT collect (when `--osint`), poi
    proximity. When OSINT is on, write `osint_enrich_request.md`.
  - *build manifest + analyst_request* — runs **after** enrichment so the
    manifest inlines the **enriched** OSINT.
- **`build_rsm_inputs`** inlines the enriched OSINT into the manifest under
  `osint_physical` and surfaces a one-line OSINT summary in `manifest_summary`
  (unchanged from rev 1).
- **Analyst prompt** consumes `osint_physical` and routes by content
  (macro→SITUATION/PHYSICAL, corroboration→cite with the linked Seerist event +
  raise confidence, early-warning→EARLY WARNING), citing OSINT by `signal_id`,
  assigning severity/section itself (unchanged from rev 1).

### `crq_run.py` flow

```
collect   → seerist + raw OSINT (+ osint_enrich_request.md when --osint)
[agent]   → run osint_enrich_request → enriched osint_physical_signals.json
analyze   → build manifest (inlines enriched OSINT) + analyst_request
[agent]   → analyst: claims.json + analyst_report.md
prep      → formatter_request
[agent]   → formatter: brief.md
render    → email.html
```

The OSINT enrich pause only occurs when OSINT is on; otherwise `collect` flows
straight into `analyze`. `crq_run` prints an "AGENT STEP REQUIRED" for the
enrichment exactly as it does for analyst/formatter.

## Keys

- **OSINT-required (default):** `TAVILY_API_KEY` + `FIRECRAWL_API_KEY`. Fail
  loudly if absent when OSINT is on (both `collect()` and `poc_runner` guards).
- **`ANTHROPIC_API_KEY`:** required **only** for the optional `--enrich-api`
  headless path. Revert `.env.example` / `setup.prompt.md` / `README` to "OSINT
  needs Tavily + Firecrawl; Anthropic only for the optional --enrich-api path."

## Error handling

- OSINT-on + missing Tavily/Firecrawl (live) → fail loudly.
- `--enrich-api` + missing ANTHROPIC → fail loudly (that path only).
- Enrichment agent step: if the agent can't write (rare), the raw signals remain
  and the analyst still has titles+excerpts — degraded but not broken.
- Seerist file absent at enrichment time → `seerist_unavailable: true`,
  corroboration skipped.
- All Firecrawl scrapes fail / Tavily empty → raw `signals: []`; enrichment
  no-ops; analyst's no-OSINT framing applies.

## Testing

- **Collector (raw, default)** — geographic query mapping (no raw code in
  query); truncation applied; raw signals shape (no summary/corroborates_event);
  Tavily/Firecrawl required, ANTHROPIC **not** required.
- **`--enrich-api` path** — the rev-1 enrichment tests (mocked anthropic) move
  behind this flag; assert ANTHROPIC required only here.
- **poc_runner split** — `--osint` writes `osint_enrich_request.md`; manifest is
  built after enrichment (the enriched file is what gets inlined).
- **Builder inlining + analyst wiring** — unchanged from rev 1 (still valid).
- **`prompts/rsm_osint_enrichment.md`** — static check: instructs drop/summary/
  corroboration, the JSON/output shape, and "do not assign severity/role".
- Live end-to-end (real Tavily/Firecrawl + Copilot-model enrichment) is the
  operator acceptance step.

## Migration from rev 1 (commit 2115235)

- Make the in-process enrichment conditional on `--enrich-api` (default off);
  collector emits raw otherwise.
- Remove `ANTHROPIC_API_KEY` from `REQUIRED_LIVE_KEYS` and the `poc_runner
  --osint` guard's default; gate it behind `--enrich-api`.
- Add `prompts/rsm_osint_enrichment.md` + `osint_enrich_request.md` writing.
- Split `poc_runner.phase_collect`; reorder `crq_run` to insert the enrich pause.
- Revert the ANTHROPIC-required doc edits to "optional, --enrich-api only".
- Keep: geo queries, truncation, dropped audit, corroboration concept, manifest
  inlining, analyst wiring, the (now optional) `_enrich`/`_call_llm` code + tests.

## Out of scope

- The parent's full 3-LLM target-centric loop.
- Cyber-pillar OSINT.
- A non-Anthropic API enrichment backend (e.g. GitHub Models) — the agent path
  covers Copilot Enterprise; the API path stays Anthropic for now.

## Files touched

`tools/osint_physical_collector.py` (raw default + `--enrich-api` gate),
`tools/poc_runner.py` (phase split + enrich-request + key-guard change),
`tools/crq_run.py` (enrich pause in the flow), `prompts/rsm_osint_enrichment.md`
(new), `.github/prompts/create-skill.prompt.md` (crq-run template gains the
enrich step), `.env.example` / `.github/prompts/setup.prompt.md` / `README.md`
(ANTHROPIC back to optional), `prompts/rsm_regional_analyst_daily.md` (unchanged
from rev 1), plus tests under `tests/`.
