# Firecrawl Integration — Two-Stage OSINT Collection

**Status:** Design approved, ready for implementation plan
**Date:** 2026-04-12
**Supersedes:** `docs/superpowers/plans/2026-04-11-firecrawl-integration.md` (scope outline)

## Problem

The OSINT pipeline synthesizes intelligence from Tavily search *snippets* (~200 characters each). The LLM never sees the full article body, which limits:

- **Lead indicator quality** — synthesis is working from previews, not primary sources
- **Source verification** — can't distinguish a primary report (CISA advisory, SEC filing) from an aggregator parroting it
- **Structured extraction** — threat actor, sector, date fields must be inferred from thin context

VaCR benchmark research (`vacr_researcher.py`) hits the same wall when trying to verify monetary loss figures and probability estimates against primary sources.

## Solution

Add Firecrawl as a **depth layer** alongside Tavily. Tavily continues to discover URLs; Firecrawl scrapes full main-content markdown from a selected subset, which is then fed into the existing synthesis prompts.

| Stage | Tool | Purpose |
|-------|------|---------|
| 1. Discovery | Tavily (existing) | Find ranked URLs per hypothesis |
| 2. Deep extraction | Firecrawl (new) | Scrape top URLs → full article markdown |
| 3. Synthesis | Existing LLM call | Builds signals payload from mixed full-text + snippet input |

## Scope

**In scope:**
- `tools/osint_collector.py` — main regional OSINT pipeline
- `tools/vacr_researcher.py` — VaCR benchmark research

**Explicitly out of scope:**
- `tools/discover.py` — topic discovery only needs snippets
- `tools/deep_research.py` — already uses GPT Researcher for full-text
- Dashboard UI changes — internal scratchpad fields only in this phase

## Architecture

### New module: `tools/firecrawl_scraper.py`

Thin wrapper around Firecrawl `/scrape`. Single responsibility: take a list of URLs, return a list of scraped article records. Owns retry logic, truncation, mock-mode dispatch, and fallback behavior.

**Public interface:**

```python
def scrape_urls(
    urls: list[str],
    tavily_snippets: dict[str, str],  # url → snippet, used for fallback
    region: str | None = None,         # for mock fixture lookup
) -> list[ScrapedItem]
```

Returns one `ScrapedItem` per input URL — always. A failed scrape returns a record tagged `source_type: "snippet"` with the Tavily snippet as content; a successful scrape returns a record tagged `source_type: "fulltext"`.

### Updated module: `tools/osint_search.py`

New function `scrape_top_results(urls, snippets, region)` — delegates to `firecrawl_scraper.scrape_urls`. Lives in `osint_search.py` so callers keep a single import surface for search-related helpers.

### Updated consumers

**`tools/osint_collector.py`:**
- `assess_gaps` (LLM Call 2) prompt extended to emit an optional `depth_needed: [hypothesis_id, ...]` field alongside its existing output.
- Between gap-fill search and `synthesize_signals` (LLM Call 3), a new scrape stage:
  1. Select baseline URLs: top 2 Tavily results across all hypotheses for the region.
  2. Select gap-triggered URLs: for each hypothesis in `depth_needed`, top results from that hypothesis's own Tavily set, up to 3 per hypothesis.
  3. Deduplicate, apply per-region ceiling of 5, call `scrape_top_results`.
- `synthesize_signals` prompt now receives a list of scraped items (fulltext + snippet mixed) instead of raw Tavily snippets. Prompt gets a one-line note explaining the `source_type` tag.
- Writes `firecrawl_stats` block into `output/regional/{region}/osint_scratchpad.json`.

**`tools/vacr_researcher.py`:**
- After each Tavily query returns, scrape top 3 URLs before synthesis. No gap tier, no per-region concept — simpler call site.
- Uses the same `firecrawl_scraper.scrape_urls` wrapper.

## Data contracts

### `ScrapedItem` shape

```python
{
  "url": "https://example.com/article",
  "title": "...",
  "source_type": "fulltext" | "snippet",
  "content": "<markdown body or Tavily snippet>",
  "hypothesis_id": "...",           # which hypothesis this supports (osint_collector only)
  "tavily_score": 0.87,             # preserved for ranking
}
```

### `firecrawl_stats` in `osint_scratchpad.json`

```json
{
  "firecrawl_stats": {
    "attempted": 5,
    "succeeded": 4,
    "fell_back": 1,
    "total_tokens": 11823
  }
}
```

### `depth_needed` in `assess_gaps` output

```json
{
  "gap_summary": "...",
  "gap_queries": [...],
  "depth_needed": ["H1", "H3"]
}
```

Optional field — empty list is valid. Backward-compatible with older cached assessments.

## Scrape strategy

**Selection (osint_collector):**
- **Baseline floor:** always scrape top 2 URLs per region (highest Tavily relevance across all hypotheses).
- **Gap-triggered extras:** up to 3 additional URLs per hypothesis flagged in `depth_needed`.
- **Per-region circuit breaker:** soft ceiling of 5 scrapes per region. Not a cost guard — a sanity check to catch loops.

**Selection (vacr_researcher):**
- Top 3 URLs per Tavily query, every query. Simpler workflow, no gap logic.

**Placement:** single scrape stage, executed between Tavily gap-fill and `synthesize_signals`. `assess_gaps` continues to run on snippets — it's a coarse pass and doesn't need full text.

## Content handling

**Firecrawl call parameters:**
- Endpoint: `/scrape`
- `onlyMainContent: true` (strip nav, ads, boilerplate)
- `formats: ["markdown"]`
- Timeout: 30 seconds per URL
- Retry: once on timeout, 5xx, or Cloudflare challenge

**Per-article truncation:**
- 3,000-token soft cap per article
- Middle-truncation: keep first ~1,500 tokens + last ~1,500 tokens with a `[…truncated…]` marker between
- Token counting via `tiktoken` (transitive dep through Anthropic SDK)

**Synthesis input size:**
- Max per region: 5 articles × 3k tokens = 15k tokens of scraped content
- Comfortably within Sonnet's context window; no hard total cap required

**Prompt note appended to `synthesize_signals`:**

> Items marked `source_type: "snippet"` are short previews (~200 chars). Items marked `source_type: "fulltext"` are main-content extracts up to 3k tokens. Weight primary sources more heavily when both are available.

## Error handling

| Failure | Behavior |
|---------|----------|
| URL timeout / 5xx / Cloudflare | Retry once, then fall back to Tavily snippet, tagged `source_type: "snippet"`. WARN log with URL + reason. |
| All URLs in a region fail | Region degrades to snippet-only synthesis. No hard fail. |
| `FIRECRAWL_API_KEY` missing in live mode | `validate_env.py` catches early with: *"set FIRECRAWL_API_KEY or pass --mock"*. If somehow missed, `firecrawl_scraper.py` raises on first call. |
| Firecrawl SDK install missing | Import-time failure with install hint. |
| Per-region ceiling hit | Remaining gap-triggered scrapes skipped silently. |

The pipeline never hard-fails because of Firecrawl. Worst case it degrades to today's snippet-only behavior.

## Mock mode

**Fixture files** under `data/mock_osint_fixtures/`:
- `firecrawl_apac.json`
- `firecrawl_ame.json`
- `firecrawl_latam.json`
- `firecrawl_med.json`
- `firecrawl_nce.json`
- `firecrawl_vacr.json` (shared across VaCR researcher queries)

**Fixture shape:**

```json
{
  "https://example.com/article": {
    "markdown": "<body>",
    "title": "Article title",
    "status": "ok"
  },
  "https://example.com/paywalled": {
    "markdown": "",
    "title": "",
    "status": "failed"
  }
}
```

A `"failed"` entry deterministically exercises the retry + snippet fallback path. Unknown URLs return a synthetic snippet-tagged placeholder so tests don't blow up when new fixture URLs are missing.

**Dispatch:** `firecrawl_scraper.py` checks the existing `OSINT_MOCK` env var (same flag Tavily mock uses). Mock path reads fixtures; live path calls the Firecrawl SDK. The `--mock` flag on collectors flips the env var.

## Env & config

- `FIRECRAWL_API_KEY` added to `.env.example`
- `validate_env.py` adds an optional Firecrawl key check — warn in live mode if missing, silent in mock mode
- No new top-level config file. Defaults (timeouts, caps, truncation) live as constants in `firecrawl_scraper.py`

## Observability

- **Tool trace hook** (`.claude/hooks/telemetry/`) — Firecrawl calls piggyback on existing tool tracing; no new hook required.
- **Scratchpad stats** — `firecrawl_stats` block per region in `osint_scratchpad.json` (attempted, succeeded, fell_back, total_tokens). Visible in the dashboard debug panel, useful for spotting degradation days without reading logs.
- **Log level** — WARN on retry and fallback, INFO on successful scrape batches.
- **No dashboard UI changes** in this phase.

## Tests

Three test additions:

1. **`tests/test_firecrawl_scraper.py` (new)** — unit tests for the wrapper:
   - Happy path: URL → fulltext `ScrapedItem`
   - Retry-once-then-succeed path
   - Retry-once-then-fall-back-to-snippet path
   - Middle-truncation on a 10k-token article
   - Mock-mode fixture loading (known URL, unknown URL, `"failed"` URL)
   - Missing API key in live mode raises cleanly

2. **`tests/test_osint_collector.py` (extend)** — integration test:
   - Full mock run produces signals with a mix of `fulltext` and `snippet` items
   - `depth_needed: ["H1"]` triggers extra scrapes on that hypothesis's URLs
   - Per-region ceiling of 5 is honored
   - `firecrawl_stats` scratchpad block is written

3. **`tests/test_vacr_researcher.py` (extend)** — VaCR happy path:
   - Mock run scrapes top 3 per query, fulltext flows into synthesis

## Rollout

1. **Build + test against mock fixtures** — no API key needed, all tests green
2. **Single-region live dry run** — `/crq-region APAC` against real Firecrawl; verify `firecrawl_stats`, inspect synthesized signal quality
3. **Full `/run-crq`** — daily run across all regions once dry run looks clean
4. **No feature flag** — rollout controlled by presence of `FIRECRAWL_API_KEY`. Unsetting the key reverts to snippet-only behavior without any code change.

## Files affected

**New:**
- `tools/firecrawl_scraper.py`
- `tests/test_firecrawl_scraper.py`
- `data/mock_osint_fixtures/firecrawl_{apac,ame,latam,med,nce,vacr}.json`

**Modified:**
- `tools/osint_search.py` — add `scrape_top_results` delegator
- `tools/osint_collector.py` — add scrape stage, extend `assess_gaps` prompt, write `firecrawl_stats`
- `tools/vacr_researcher.py` — scrape top 3 per query before synthesis
- `tools/validate_env.py` — optional Firecrawl key check
- `.env.example` — add `FIRECRAWL_API_KEY`
- `tests/test_osint_collector.py` — integration tests
- `tests/test_vacr_researcher.py` — integration tests

## Open questions

None — all 8 scope questions from the brainstorm outline resolved.

## References

- [Firecrawl vs Tavily comparison](https://www.firecrawl.dev/alternatives/firecrawl-vs-tavily)
- [Firecrawl docs — scrape](https://docs.firecrawl.dev/features/scrape)
- [Firecrawl GitHub](https://github.com/firecrawl/firecrawl)
- Brainstorm outline: `docs/superpowers/plans/2026-04-11-firecrawl-integration.md`
- Memory note: `project-firecrawl-integration.md`
