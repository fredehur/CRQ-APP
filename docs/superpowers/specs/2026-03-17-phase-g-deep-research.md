# Phase G — Deep Research via GPT Researcher

**Date:** 2026-03-17
**Status:** Approved for implementation
**Builds on:** Phase G-0 (osint_topics.json shared registry), existing OSINT tool chain

---

## Problem

The current OSINT collectors (`geo_collector.py`, `cyber_collector.py`) do shallow web search — 3–5 results, headlines and snippets only. For board-level risk intelligence this is a meaningful quality gap. A human analyst would spend 30+ minutes reading full articles across 20+ sources before writing a brief. The pipeline currently spends ~3 seconds.

GPT Researcher bridges this gap: it autonomously generates sub-queries, scrapes and reads full article content across 20–30 sources, and synthesises a research report. This spec defines how to wire it into the pipeline as a configurable deep research mode.

---

## Goals

1. Provide a `tools/deep_research.py` shared module that wraps GPT Researcher with the project's Claude + Tavily config
2. Allow any pipeline run to opt into deep research via `--deep` flag on `run-crq`
3. Support `--deep-scope=escalated|all` — run deep on escalated regions only, or all five
4. Support `--depth=quick|standard|deep` — controls research time/cost per region
5. Stream research progress to the existing Agent Activity Console via SSE
6. Explicitly solve output parsing: GPT Researcher markdown → structured signal JSON via Claude Haiku extraction
7. Make `tools/discover.py` (Config tab discovery feature) a consumer of `deep_research.py`

---

## Out of Scope

- NotebookLM audio briefing (parked, Phase F-5)
- Regional analyst mid-analysis enrichment via MCP (Phase H+)
- YouTube transcript collector (Phase H)
- Replacing the mock mode — `--mock` remains unchanged

---

## Architecture

### Shared Module Pattern

`tools/deep_research.py` is the single place where:
- GPT Researcher is configured (Claude models, Tavily key, scraper limits)
- The `on_progress` callback is wired to SSE
- The markdown-to-JSON extraction step lives
- `asyncio.run()` wrappers are defined

Every tool that needs deep research imports from it. No duplication.

### Pipeline Flow (with `--deep`)

```
Phase 1 — Shallow pass (always, fast):
  geo_collector.py REGION      → geo_signals.json   (3-5 results, seconds)
  cyber_collector.py REGION    → cyber_signals.json  (3-5 results, seconds)
  gatekeeper-agent             → ESCALATE / MONITOR / CLEAR

Phase 2 — Deep pass (conditional):
  if ESCALATE (or --deep-scope=all):
    deep_research.py REGION geo   → overwrites geo_signals.json  (rich, 2-10 min)
    deep_research.py REGION cyber → overwrites cyber_signals.json (rich, 2-10 min)

Phase 3 — Analysis (unchanged):
  regional-analyst-agent reads enriched signals → report.md + data.json
```

The shallow gatekeeper pass stays fast. Deep research only runs where it matters (or everywhere if the user opts in).

### Tool as Standalone CLI

`deep_research.py` is a proper replacement collector, not a flag on existing tools:

```bash
uv run python tools/deep_research.py APAC geo   --depth=standard
uv run python tools/deep_research.py APAC cyber --depth=quick
uv run python tools/deep_research.py APAC topics  # for discover.py
```

Output: always writes to the same schema as the existing collector it replaces. Drop-in substitution.

---

## Config

### Environment Variables

```bash
# Required for deep research
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...

# LLM slots (GPT Researcher format: "provider:model")
SMART_LLM=anthropic:claude-sonnet-4-6
FAST_LLM=anthropic:claude-haiku-4-5-20251001

# Scraper controls
MAX_SCRAPER_WORKERS=5          # default 5; reduce on slow connections
SCRAPER_RATE_LIMIT_DELAY=2.0   # seconds between requests (default 2.0 = ~30/min)
```

### Depth Presets

| `--depth` | `max_subtopics` | `report_type` | Est. time/region |
|---|---|---|---|
| `quick` | 2 | `summary_report` | ~2 min |
| `standard` (default) | 3 | `research_report` | ~5 min |
| `deep` | 5 | `research_report` | ~10 min |

### Scope Presets

| `--deep-scope` | Regions researched |
|---|---|
| `escalated` (default) | Only ESCALATE regions from gatekeeper pass |
| `all` | All 5 regions regardless of gatekeeper decision |

---

## deep_research.py — Module Design

### Responsibilities

1. Configure GPT Researcher with Claude backend
2. Run research for a given query + type (geo / cyber / topics)
3. Stream progress events via callback → SSE
4. Parse GPT Researcher markdown output → structured JSON via Haiku extraction
5. Write output to correct path (`output/regional/{region}/{type}_signals.json`)

### Core Functions

```python
async def run_deep_research(
    region: str,
    signal_type: str,            # "geo" | "cyber" | "topics"
    depth: str = "standard",     # "quick" | "standard" | "deep"
    on_progress=None,            # async callback(message: str)
) -> dict:
    """
    Run deep research for a region + signal type.
    Returns structured signals dict (same schema as existing collectors).
    Writes output file directly.
    """
```

### Progress Callback → SSE

GPT Researcher's `conduct_research(on_progress=cb)` emits step events. We map them:

```python
async def _make_progress_handler(region: str, signal_type: str, emit_fn):
    async def handler(message: str):
        await emit_fn("deep_research", {
            "region": region,
            "type": signal_type,
            "message": message,
        })
    return handler
```

The SSE `deep_research` event is handled by the existing Agent Activity Console in `app.js`.

### Output Parsing — The Critical Step

GPT Researcher returns a markdown string. The pipeline expects structured JSON. This is a non-trivial conversion that must be explicit:

```python
async def _extract_signals_from_report(
    report_markdown: str,
    sources: list,
    region: str,
    signal_type: str,  # "geo" | "cyber"
) -> dict:
    """
    Call Claude Haiku with the research report + extraction prompt.
    Returns dict matching geo_signals.json / cyber_signals.json schema.
    """
    prompt = EXTRACTION_PROMPTS[signal_type].format(
        region=region,
        report=report_markdown[:8000],  # cap tokens
        sources=json.dumps(sources[:10], indent=2),
    )
    # Claude Haiku call → structured JSON response
    # Parse and validate against schema
    # Return signals dict
```

**Extraction prompts** are defined as constants in `deep_research.py`, not inline strings. They instruct Haiku to extract signals in the exact schema format, cite sources, and classify signal type (Event/Trend/Mixed).

### Async Handling

All GPT Researcher operations are async. The existing CLI tool pattern is sync. Bridge:

```python
def main():
    """CLI entry point — sync wrapper around async core."""
    import asyncio
    result = asyncio.run(run_deep_research(
        region=sys.argv[1].upper(),
        signal_type=sys.argv[2],
        depth=sys.argv[3] if len(sys.argv) > 3 else "standard",
    ))
    print(json.dumps(result, indent=2))
```

---

## run-crq.md Integration

New flags passed through to the pipeline:

```
/run-crq --deep                    # deep on escalated regions, standard depth
/run-crq --deep --deep-scope=all   # deep on all regions
/run-crq --deep --depth=quick      # fast deep research
/run-crq --deep --depth=deep       # thorough deep research
```

Pipeline logic change (Phase 2, after gatekeeper fan-in):

```
if --deep flag set:
    for each region where status == "escalated" (or all if --deep-scope=all):
        run deep_research.py REGION geo  --depth={depth}
        run deep_research.py REGION cyber --depth={depth}
    (these overwrite the shallow collector outputs)
proceed to regional-analyst-agent (reads enriched signals)
```

---

## discover.py — Consumer

`tools/discover.py` imports `deep_research.py` and uses it for on-demand Config tab discovery:

```bash
uv run python tools/discover.py topics "OT cyber attacks energy sector"
uv run python tools/discover.py sources "geopolitical risk wind energy APAC"
```

Returns JSON array of suggested topics or YouTube channels, rendered inline in the Config tab with Add buttons. Uses `--depth=quick` by default (2 min max for interactive use).

---

## Agent Activity Console — New Events

New SSE event type `deep_research` added to `app.js`:

```js
es.addEventListener('deep_research', e => {
  const d = JSON.parse(e.data);
  const pct = _deepResearchProgress[d.region]?.[d.type] ?? 0;
  appendConsoleEntry(
    `<span style="color:#79c0ff;font-size:10px">[deep] ${esc(d.region)} ${esc(d.type)} — ${esc(d.message)}</span>`
  );
});
```

Progress messages from GPT Researcher's step events map to human-readable status lines:
- `research_plan` step → "generating sub-queries..."
- `research` step → "searching sources..."
- `think` step → "synthesising..."
- Extraction step (our code) → "extracting signals..."

---

## Installation

```bash
uv add gpt-researcher
```

Add to `pyproject.toml` dependencies. No other install steps — GPT Researcher uses existing `TAVILY_API_KEY` and `ANTHROPIC_API_KEY` env vars.

---

## Files Created / Modified

| File | Action | Purpose |
|---|---|---|
| `tools/deep_research.py` | Create | Shared GPT Researcher wrapper + extraction |
| `tools/discover.py` | Create | Config tab discovery agent (imports deep_research) |
| `.claude/commands/run-crq.md` | Modify | Add `--deep`, `--deep-scope`, `--depth` flags |
| `server.py` | Modify | Add `/api/discover/topics`, `/api/discover/sources`, `/api/discover/suggestions` endpoints |
| `tools/suggest_config.py` | Create | Post-run suggestions writer |
| `static/app.js` | Modify | Handle `deep_research` SSE events in Agent Console |
| `.env.example` | Modify | Document `SMART_LLM`, `FAST_LLM`, `MAX_SCRAPER_WORKERS`, `SCRAPER_RATE_LIMIT_DELAY` |

---

## Decisions Log

| Decision | Choice | Reason |
|---|---|---|
| LLM backend | Claude (not Tavily hosted) | Claude controls synthesis quality and persona |
| Models | `claude-sonnet-4-6` (SMART), `claude-haiku-4-5-20251001` (FAST) | Aligned with existing pipeline models |
| Integration pattern | Standalone CLI tool, not `--deep` flag on existing collectors | Clean substitution, single responsibility |
| Default scope | `escalated` only | Protects pipeline runtime for most runs |
| Default depth | `standard` (3 subtopics, ~5 min) | Balanced quality vs speed |
| Output parsing | Explicit Haiku extraction step | GPT Researcher markdown → JSON is non-trivial, must be owned |
| NotebookLM | Not in this phase | Browser automation + rate limits; keep for audio briefing use case |
| Async | `asyncio.run()` wrapper in CLI entry point | GPT Researcher is async-only; existing pipeline is sync CLI |
