# Tavily Research API — VaCR Benchmark Researcher Integration

**Date:** 2026-04-13 (rev 2 — grounded in real API inspection)
**Status:** Approved — pending Tavily plan upgrade
**Scope:** `tools/vacr_researcher.py` + `pyproject.toml` only.

---

## Problem

`vacr_researcher.py` currently runs a 3-step pipeline per scenario:

1. **Tavily Search** (httpx REST call) → raw snippets (~200 chars each)
2. **Haiku extraction** — LLM extracts financial/probability figures from snippets
3. **Sonnet reasoning** — LLM produces supports/challenges/inconclusive verdict

Step 2 is working from the same thin snippet context that the OSINT pipeline identified as a quality limit. Haiku sees 200-character previews, not primary source text.

---

## Solution

Replace steps 1 and 2 with a single **Tavily Research API** call that synthesises primary sources and returns structured figures via `output_schema`, then feed those figures into the existing Sonnet reasoning step unchanged.

```
BEFORE:  Tavily Search (snippets) → Haiku extraction → Sonnet reasoning
AFTER:   Tavily Research (output_schema → structured_output) → Sonnet reasoning
```

---

## Prerequisites

### 1. Tavily plan upgrade (blocker)
The Research API is gated behind a higher-tier Tavily plan. The current plan raises `ForbiddenError: This request exceeds your plan's set usage limit` on any `research()` call. Upgrade at app.tavily.com before implementation begins.

### 2. Add `tavily-python` dependency
`osint_search.py` currently calls the Tavily REST API directly via `httpx` — the SDK is not installed. Add it:

```bash
uv add tavily-python
```

Confirmed version: `tavily-python==0.7.23` contains `.research()` and `.get_research()`.

---

## Architecture

**Files changed:** `tools/vacr_researcher.py`, `pyproject.toml`

**Deleted from `vacr_researcher.py`:**
- `search_tavily()` helper
- `EXTRACTION_PROMPT` constant
- All Haiku client code (`HAIKU_MODEL`, Haiku `anthropic.Anthropic()` call)

**Unchanged everywhere:**
- `REASONING_PROMPT` and Sonnet reasoning call
- `vacr_research.json` output schema
- `register_validator.py`, `server.py`, SSE streaming, all UI code

---

## The Research Call

### SDK pattern (confirmed by source inspection)

`research()` is **async-submit** — it returns immediately with a `request_id`. You must poll `get_research(request_id)` until `status == "completed"`.

```python
from tavily import TavilyClient

client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

# Submit
task = client.research(
    input=query,
    model="mini",
    output_schema=OUTPUT_SCHEMA,
)
request_id = task["request_id"]

# Poll
import time
deadline = time.time() + 180  # 3-minute hard limit
while time.time() < deadline:
    result = client.get_research(request_id)
    if result["status"] == "completed":
        figures = result["structured_output"]["figures"]  # schema result lives here
        break
    logger.info("[vacr_researcher] research status=%s, waiting...", result["status"])
    time.sleep(5)
else:
    raise TimeoutError(f"Tavily research timed out after 180s (request_id={request_id})")
```

### Query shape

One combined query per scenario covering both dimensions:

```python
query = (
    f"{incident_type} financial cost incident rate probability "
    f"{sector} sector renewable energy operator USD 2024 2025"
)
```

**Risk:** a merged query may produce strong financial figures but weak probability data (different vocabulary domains). If this proves out during testing, split into two queries and `asyncio.gather()` them — see Parallelisation section.

### output_schema

```python
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "figures": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["dimension", "note", "raw_quote", "source_name", "source_url"],
                "properties": {
                    "dimension":              {"type": "string", "enum": ["financial", "probability"]},
                    "cost_low_usd":           {"type": ["number", "null"]},
                    "cost_median_usd":        {"type": ["number", "null"]},
                    "cost_high_usd":          {"type": ["number", "null"]},
                    "probability_low_pct":    {"type": ["number", "null"]},
                    "probability_median_pct": {"type": ["number", "null"]},
                    "probability_high_pct":   {"type": ["number", "null"]},
                    "note":        {"type": "string"},
                    "raw_quote":   {"type": "string"},
                    "source_name": {"type": "string"},
                    "source_url":  {"type": "string"}
                }
            }
        }
    },
    "required": ["figures"]
}
```

Schema matches the figure format Haiku currently extracts — the `REASONING_PROMPT` receives the same `findings_text` it always has.

**Note:** `output_schema` compliance is treated as a contract with the API. If `result["structured_output"]` is absent or malformed, the scenario raises an explicit error rather than degrading silently.

### Model

`"mini"` — faster (30-60s vs 60-120s for `"pro"`), targeted efficiency. Switch to `"pro"` if financial figure coverage proves thin after initial runs.

---

## Parallelisation

With 8 scenarios × 30-60s each, sequential execution takes 4-8 minutes. Use `AsyncTavilyClient` + `asyncio.gather()` to run all scenarios in parallel:

```python
from tavily import AsyncTavilyClient
import asyncio

async def research_scenario(client, scenario):
    task = await client.research(input=build_query(scenario), model="mini", output_schema=OUTPUT_SCHEMA)
    # ... poll async ...

async def run_all(scenarios):
    async with AsyncTavilyClient(api_key=...) as client:
        results = await asyncio.gather(*[research_scenario(client, s) for s in scenarios], return_exceptions=True)
    return results
```

Failed scenarios surface as exceptions in the results list — other scenarios complete normally.

---

## Error Handling

No fallback to search+Haiku. Failures are explicit:

- **API error / plan limit** → `ForbiddenError` propagates, scenario marked `"status": "error"` in `vacr_research.json`
- **Timeout (>180s)** → `TimeoutError`, same treatment
- **Missing `structured_output`** → `KeyError` with a descriptive message logged
- **Individual scenario failure** → other scenarios in the parallel batch complete normally (via `return_exceptions=True`)

The analyst sees failed scenarios in the UI and re-runs them.

---

## Cost

Research API credits are significantly higher than Search. Estimate before the first production run. With `mini` model and parallel calls, budget per validate-register run = `N_scenarios × research_credit_cost`. Log `result.get("usage", {})` per call for visibility.

---

## Files Changed

| File | Change |
|---|---|
| `tools/vacr_researcher.py` | Replace search + Haiku with `TavilyClient.research()` + polling wrapper; add `AsyncTavilyClient` parallel execution; delete `search_tavily()`, `EXTRACTION_PROMPT`, Haiku imports |
| `pyproject.toml` | Add `tavily-python>=0.7.23` |

## Files Unchanged

| File | Reason |
|---|---|
| `tools/register_validator.py` | Not involved in per-scenario research |
| `server.py` | SSE streaming and API endpoints unchanged |
| `REASONING_PROMPT` | Receives same `findings_text` format |
| `output/pipeline/vacr_research.json` schema | Output contract unchanged |
