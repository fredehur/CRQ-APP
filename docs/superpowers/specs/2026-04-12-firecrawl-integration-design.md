# Firecrawl Integration — Two-Stage OSINT Collection

**Status:** Design approved, ready for implementation plan
**Date:** 2026-04-12 (rev 2, after self-critique pass)
**Supersedes:** `docs/superpowers/plans/2026-04-11-firecrawl-integration.md` (scope outline)

## Problem

The OSINT pipeline synthesizes intelligence from Tavily search *snippets* (~200 characters each). The LLM never sees the full article body, which limits:

- **Lead indicator quality** — synthesis works from previews, not primary sources
- **Source verification** — can't distinguish a primary report (CISA advisory, SEC filing) from an aggregator parroting it
- **Structured extraction** — threat actor, sector, date fields must be inferred from thin context

`tools/vacr_researcher.py` hits the same wall verifying monetary loss figures against primary sources.

## Solution

Add Firecrawl as a **depth layer** alongside Tavily. Tavily continues to discover URLs; Firecrawl scrapes full main-content markdown from the top-scoring subset, which is then fed into the existing synthesis prompts.

| Stage | Tool | Purpose |
|-------|------|---------|
| 1. Discovery | Tavily (existing) | Find ranked URLs per hypothesis |
| 2. Deep extraction | Firecrawl (new) | Scrape top URLs → full article markdown |
| 3. Synthesis | Existing LLM call | Builds signals from mixed full-text + snippet input |

## Scope

**In scope:**
- `tools/osint_collector.py` — main regional OSINT pipeline
- `tools/vacr_researcher.py` — VaCR benchmark research

**Explicitly out of scope:**
- `tools/discover.py` — topic discovery only needs snippets
- `tools/deep_research.py` — already uses GPT Researcher for full-text
- Dashboard UI changes — internal scratchpad fields only in this phase

## Prerequisite

`tools/osint_search.py::search_tavily` currently strips the Tavily `score` field from each result. Without score, "top N by relevance" is undefined. **Fix first, in a small isolated change** — add `"score": r.get("score", 0.0)` to the returned dict. This lands before the Firecrawl work and is the ordering foundation for every scrape-selection decision downstream.

## Architecture

### New module: `tools/firecrawl_scraper.py`

Thin standalone wrapper around Firecrawl `/scrape`. Imported **directly** by `osint_collector.py` and `vacr_researcher.py` — no delegator layer in `osint_search.py` (which is a subprocess CLI, not an importable library).

**Public interface:**

```python
def scrape_urls(
    urls: list[str],
    tavily_snippets: dict[str, str],  # url → snippet, used for fallback
    region: str | None = None,         # for mock fixture lookup
) -> list[ScrapedItem]
```

Returns one `ScrapedItem` per input URL — always. A failed scrape returns a record tagged `source_type: "snippet"` with the Tavily snippet as content; a successful scrape returns a record tagged `source_type: "fulltext"`.

**Concurrency:** scrapes run in parallel via `ThreadPoolExecutor(max_workers=5)`. Sequential scraping of 5 URLs × 5 regions at 30s/URL ceiling would dominate pipeline latency; parallel brings it back under a minute.

**Owns:** retry logic, truncation, mock-mode dispatch, fallback behavior.

### Consumer integration

**`tools/osint_collector.py`** — single new scrape stage between Tavily gap-fill and `synthesize_signals`:

1. Collect URLs from pass 1 + pass 2 Tavily results.
2. Filter through existing `_is_junk_url` / `_BLOCKED_URLS` / `_JUNK_DOMAINS` — junk must not hit Firecrawl.
3. Sort descending by Tavily `score`.
4. Take top 5 (per-region ceiling).
5. Call `firecrawl_scraper.scrape_urls(top5, snippet_lookup, region)`.
6. Feed the returned `ScrapedItem` list into `synthesize_signals` **instead of** the existing `snippets_text[:20]` slice. The 5-item scraped list is the new synthesis input.
7. Write `firecrawl_stats` block into `output/regional/{region}/osint_scratchpad.json`.

`synthesize_signals` prompt gets a one-line note explaining the `source_type` tag. `assess_gaps` is **unchanged** — it continues to run on snippets, which is fine for coarse gap detection.

**`tools/vacr_researcher.py`** — inline scrape inside `_search_web`. After each Tavily call returns, sort results by score, take top 3, scrape, and replace each result's `content` field with the scraped markdown (snippet fallback on failure). `vacr_researcher.py` has its own inline Tavily wrapper (it does not share `osint_search.py`), so the integration lives inline there.

## Data contracts

### `ScrapedItem` shape

```python
{
  "url": "https://example.com/article",
  "title": "...",
  "source_type": "fulltext" | "snippet",
  "content": "<markdown body or Tavily snippet>",
  "tavily_score": 0.87,   # preserved for ranking in consumers
}
```

### `firecrawl_stats` in `osint_scratchpad.json`

```json
{
  "firecrawl_stats": {
    "attempted": 5,
    "succeeded": 4,
    "fell_back": 1
  }
}
```

No `total_tokens` — speculative. Add later if we actually want it.

## Scrape strategy

**`osint_collector`:** single stage. Top 5 URLs per region by Tavily score, junk-filtered, scraped in parallel. Ceiling of 5 is a hard slice, not a loop guard.

**`vacr_researcher`:** top 3 URLs per Tavily query, every query. Simpler workflow.

**Placement:** single scrape stage, executed between Tavily gap-fill and `synthesize_signals`.

## Content handling

**Firecrawl call parameters:**
- Endpoint: `/scrape`
- `onlyMainContent: true` (strip nav, ads, boilerplate)
- `formats: ["markdown"]`
- Timeout: 30 seconds per URL
- Retry: once on timeout, 5xx, or Cloudflare challenge

**Per-article truncation:**
- Character-based soft cap: 12,000 characters (~3k tokens at 4 chars/token)
- Middle-truncation: keep first 6k chars + last 6k chars with `[…truncated…]` marker between
- No `tiktoken` dependency — char count is close enough for synthesis prompting

**Synthesis input size:**
- Max per region: 5 articles × ~12k chars ≈ 60k chars (~15k tokens)
- Well inside Sonnet's context window

**Prompt note appended to `synthesize_signals`:**

> Items marked `source_type: "snippet"` are short previews (~200 chars). Items marked `source_type: "fulltext"` are main-content extracts up to ~3k tokens. Weight primary sources more heavily when both are available.

## Error handling

| Failure | Behavior |
|---------|----------|
| URL timeout / 5xx / Cloudflare | Retry once, then fall back to Tavily snippet, tagged `source_type: "snippet"`. WARN log with URL + reason. |
| All URLs in a region fail | Region degrades to snippet-only synthesis. No hard fail. |
| `FIRECRAWL_API_KEY` missing in live mode | `validate_env.py` warns early. If somehow missed, `firecrawl_scraper.py` raises on first call. |
| Firecrawl SDK install missing | Import-time failure with install hint. |

The pipeline never hard-fails because of Firecrawl. Worst case it degrades to today's snippet-only behavior.

## Mock mode

**Fixture files** under `data/mock_osint_fixtures/`:
- `firecrawl_apac.json`, `firecrawl_ame.json`, `firecrawl_latam.json`, `firecrawl_med.json`, `firecrawl_nce.json`
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

A `"failed"` entry deterministically exercises the retry + snippet fallback path. Unknown URLs return a synthetic snippet-tagged placeholder so tests don't blow up when fixture URLs drift.

**Dispatch:** `firecrawl_scraper.py` checks the existing `OSINT_MOCK` env var (same flag Tavily mock uses). Mock path reads fixtures; live path calls the Firecrawl SDK.

**Important mock-mode caveat:** `osint_collector.run_mock_mode` bypasses the entire pipeline and reads `{region}_osint.json` directly as the final output. Firecrawl has **no role** in that path. The Firecrawl mock fixtures only activate when running the real pipeline with `OSINT_MOCK=1` set (so Tavily, LLM calls, and Firecrawl all read fixtures while the pipeline code executes normally).

## Env & config

- `FIRECRAWL_API_KEY` added to `.env.example`
- `validate_env.py` adds an optional Firecrawl key check — warn in live mode if missing, silent in mock mode
- No new top-level config file. Defaults (timeouts, caps, truncation) live as constants in `firecrawl_scraper.py`

## Observability

- **Tool trace hook** — Firecrawl calls piggyback on existing tool tracing; no new hook required
- **Scratchpad stats** — `firecrawl_stats` per region in `osint_scratchpad.json` (attempted, succeeded, fell_back)
- **Log level** — WARN on retry and fallback, INFO on successful scrape batches
- **No dashboard UI changes** in this phase

## Tests

**`tests/test_firecrawl_scraper.py` (new)** — unit tests only:

- Happy path: URL → fulltext `ScrapedItem`
- Retry-once-then-succeed path
- Retry-once-then-fall-back-to-snippet path
- Char-based middle-truncation on a 20k-char article
- Mock-mode fixture loading (known URL, unknown URL, `"failed"` URL)
- Missing API key in live mode raises cleanly
- `ThreadPoolExecutor` parallelism returns results in input order

**No integration test expansion.** `osint_collector.run_mock_mode` bypasses the pipeline entirely, so an end-to-end mocked run exercises none of the new code. The real smoke test is the live single-region dry run in rollout step 2.

## Rollout

1. **Prereq merge** — `osint_search.py` score preservation, isolated
2. **Build + test against mock fixtures** — no API key needed, unit tests green
3. **Single-region live dry run** — `/crq-region APAC` against real Firecrawl; verify `firecrawl_stats`, inspect synthesized signal quality
4. **Full `/run-crq`** — daily run across all regions once dry run looks clean
5. **No feature flag** — rollout controlled by presence of `FIRECRAWL_API_KEY`. Unsetting the key reverts to snippet-only behavior without any code change.

## Files affected

**New:**
- `tools/firecrawl_scraper.py`
- `tests/test_firecrawl_scraper.py`
- `data/mock_osint_fixtures/firecrawl_{apac,ame,latam,med,nce,vacr}.json`

**Modified:**
- `tools/osint_search.py` — **prereq:** preserve Tavily `score` field in returned dict
- `tools/osint_collector.py` — add scrape stage before `synthesize_signals`, feed scraped items into prompt, write `firecrawl_stats`
- `tools/vacr_researcher.py` — inline scrape in `_search_web` after Tavily returns
- `tools/validate_env.py` — optional Firecrawl key check
- `.env.example` — add `FIRECRAWL_API_KEY`

## Dropped from rev 1 (and why)

- **`depth_needed` tier in `assess_gaps`** — single-stage top-5-by-score is simpler and covers the same ground
- **`hypothesis_id` field on `ScrapedItem`** — no multi-tier selection means no need for hypothesis binding
- **`total_tokens` in scratchpad stats** — speculative; add later if it proves useful
- **Delegator function in `osint_search.py`** — `osint_search` is a subprocess CLI, not an importable lib. Consumers import `firecrawl_scraper` directly
- **`tiktoken` middle-truncation** — `tiktoken` is not a transitive dep of `anthropic`; char-based truncation is close enough
- **Integration test expansion** — mock-mode pipeline bypass makes it a dead end; unit tests + live dry run cover it
- **Global per-run scrape ceiling** — daily cadence, well-funded; per-region ceiling (5) is enough

## Open questions

None.

## References

- [Firecrawl vs Tavily comparison](https://www.firecrawl.dev/alternatives/firecrawl-vs-tavily)
- [Firecrawl docs — scrape](https://docs.firecrawl.dev/features/scrape)
- [Firecrawl GitHub](https://github.com/firecrawl/firecrawl)
- Brainstorm outline: `docs/superpowers/plans/2026-04-11-firecrawl-integration.md`
- Memory note: `project-firecrawl-integration.md`
