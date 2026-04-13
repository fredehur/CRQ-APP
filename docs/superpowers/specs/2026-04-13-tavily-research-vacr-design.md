# Tavily Research API — VaCR Benchmark Researcher Integration

**Date:** 2026-04-13
**Status:** Approved
**Scope:** `tools/vacr_researcher.py` only — no changes to `register_validator.py`, `server.py`, Sonnet reasoning prompt, or output schema.

---

## Problem

`vacr_researcher.py` currently runs a 3-step pipeline per scenario:

1. **Tavily Search** (httpx REST call) → raw snippets (~200 chars each)
2. **Haiku extraction** — LLM extracts financial/probability figures from snippets
3. **Sonnet reasoning** — LLM produces supports/challenges/inconclusive verdict

Step 2 is working from the same thin snippet context that the OSINT pipeline already identified as a quality limit. The Haiku extraction sees 200-character previews, not primary source text — the same problem Firecrawl solved for OSINT collection.

---

## Solution

Replace steps 1 and 2 with a single **Tavily Research API** call that returns structured figures derived from full primary-source text, then feed those figures into the existing Sonnet reasoning step unchanged.

```
BEFORE:  Tavily Search → Haiku extraction → Sonnet reasoning
AFTER:   Tavily Research (output_schema) → Sonnet reasoning
```

---

## Architecture

**Single file change:** `tools/vacr_researcher.py`

**Deleted from the file:**
- `search_tavily()` helper function
- `EXTRACTION_PROMPT` constant
- All Haiku client code (`haiku_client`, `HAIKU_MODEL` import)

**Unchanged everywhere:**
- `REASONING_PROMPT` and Sonnet reasoning call
- `vacr_research.json` output schema
- `register_validator.py`
- `server.py` and SSE progress streaming
- All UI code

The `TavilyClient` from `tavily-python` (already a dependency via `osint_search.py`) gains a `.research()` call. No new packages required.

---

## The Research Call

### Query shape

One combined query per scenario covering both dimensions:

```python
query = (
    f"{incident_type} financial cost incident rate probability "
    f"{sector} sector renewable energy operator USD 2024 2025"
)
```

One call per scenario (not separate financial/probability queries). The research API performs multi-angle synthesis internally across both dimensions.

### output_schema

Pass a JSON Schema so Tavily returns structured figures directly — no LLM extraction step needed on our side:

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
                    "dimension": {
                        "type": "string",
                        "enum": ["financial", "probability"]
                    },
                    "cost_low_usd":          {"type": ["number", "null"]},
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

The schema matches the figure format Haiku currently extracts, so the `REASONING_PROMPT` receives the same `findings_text` it always has — zero changes to the reasoning step.

### Model

`"mini"` — faster (30-60s vs 60-120s for `"pro"`), targeted efficiency, sufficient for financial benchmark lookups across energy sector sources.

### Polling

Simple polling at 5-second intervals up to a 3-minute hard timeout:

```python
client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
result = client.research(query, model="mini", output_schema=OUTPUT_SCHEMA)
# If SDK exposes only the raw async endpoint (request_id), implement a thin
# polling wrapper: submit → poll get_research(request_id) every 5s → return on "completed"
figures = result["figures"]
```

Progress is logged via `logger.info()` during the wait — existing SSE stream forwards these to the UI automatically. No changes to the streaming infrastructure.

---

## Error Handling

No fallback path. If the research call fails (timeout, API error, malformed schema response), the exception propagates:

- The scenario is written to `vacr_research.json` with `"status": "error"` and an `"error"` field containing the message.
- The UI shows the scenario as failed — the analyst sees it explicitly and re-runs.
- No silent degradation to lower-quality data.

**Hard timeout:** 3 minutes. If Tavily hasn't responded, raise `TimeoutError`.

---

## Latency

Current per-scenario time: ~8s (Tavily search ~3s + Haiku extraction ~5s).
New per-scenario time: 30-120s (Tavily Research `mini` model).

This is acceptable because:
- `validate-register` is an on-demand workflow triggered from the UI, not part of the real-time pipeline.
- The UI already shows a live progress bar with SSE streaming.
- With the `mini` model and a focused query, most runs should land in the 30-60s range.

---

## Files Changed

| File | Change |
|---|---|
| `tools/vacr_researcher.py` | Replace search + Haiku extraction with `TavilyClient.research()` call; delete `search_tavily()`, `EXTRACTION_PROMPT`, Haiku imports |

## Files Unchanged

| File | Reason |
|---|---|
| `tools/register_validator.py` | Not involved in per-scenario research |
| `server.py` | SSE streaming and API endpoints unchanged |
| `REASONING_PROMPT` (in vacr_researcher.py) | Receives same `findings_text` format |
| `output/pipeline/vacr_research.json` schema | Output contract unchanged |
| All tests referencing output format | No schema changes |
