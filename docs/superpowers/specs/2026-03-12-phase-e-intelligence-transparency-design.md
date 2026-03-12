# Phase E — Intelligence Transparency & Live Observability
**Date:** 2026-03-12
**Status:** Approved

---

## Context

Phases A–D-2 are complete and merged to `main`. The pipeline produces correct outputs in mock mode. The gap: stakeholders cannot see *why* the system made its decisions or *what intelligence* backed them up. The data exists on disk — it is not surfaced.

This phase is purely additive. No existing agent logic, routing, hook auditors, or signal file schemas change.

**Design principle:** Surface existing data first (E-1). Add new data collection second (E-2). Add live infrastructure last (E-3). Each sub-phase is independently releasable.

---

## Architecture

```
E-1  Decision Transparency    build_dashboard.py + export tools read existing JSON (no new files)
E-2  Intelligence Provenance  collectors write intelligence_sources.json + fixtures + dashboard + exports
E-3  Live Telemetry           send_event.py + server.py /internal/event + SSE → dashboard live strip
```

Data flow after E-2:

```
geo_collector.py   ──► geo_signals.json               (existing, unchanged)
                   ──► intelligence_sources.json        (new — geo_sources array)

cyber_collector.py ──► cyber_signals.json              (existing, unchanged)
                   ──► intelligence_sources.json        (appends cyber_sources array)

gatekeeper_decision.json  ──► build_dashboard.py        (E-1: now surfaced)
scenario_map.json         ──► build_dashboard.py        (E-1: now surfaced)
intelligence_sources.json ──► build_dashboard.py        (E-2: new)
                          ──► export_pdf.py             (E-2: new)
                          ──► export_pptx.py            (E-2: new)
```

No SQLite. No new servers until E-3. No changes to agent files or signal file schemas.

---

## E-1 — Decision Transparency

### What changes

- `tools/build_dashboard.py` — reads `gatekeeper_decision.json` per region (already reads `data.json` from same directory); injects fields into Jinja template
- `tools/export_pdf.py` — adds one "Basis of assessment" field per region section from `gatekeeper_decision.rationale`
- `tools/export_pptx.py` — same one-line addition per region slide

### Data surfaced (already written by pipeline, not yet shown)

From `output/regional/{region}/gatekeeper_decision.json`:
- `decision` (ESCALATE / MONITOR / CLEAR)
- `admiralty.rating` (e.g., "B2")
- `scenario_match` (e.g., "System intrusion")
- `dominant_pillar` (e.g., "Geopolitical")
- `rationale` (one-sentence assessment)

From `output/regional/{region}/scenario_map.json`:
- `financial_rank` (1–9)
- `confidence` (high / medium / low)

### Dashboard rendering

Each region card gains a "Decision Intelligence" block:

```
┌─ APAC  [ESCALATED]  Admiralty: B2  ────────────────────────┐
│  System intrusion · Financial rank #3 · Confidence: HIGH    │
│  "State-sponsored APT activity confirmed via geo and cyber   │
│   signal corroboration."                                     │
│  Primary driver: Geopolitical                                │
└──────────────────────────────────────────────────────────────┘
```

CLEAR and MONITOR regions render the same block explaining why they were not escalated. Clear signals are as valuable as alerts.

### Graceful degradation

If `gatekeeper_decision.json` is absent (pre-D2 archived runs), the block is omitted silently. No errors.

### No new tests required

Existing tests cover `build_dashboard.py` output. A single assertion that the decision block renders when `gatekeeper_decision.json` is present is sufficient.

---

## E-2 — Intelligence Provenance

### New file

`output/regional/{region}/intelligence_sources.json` — written by `geo_collector.py` and `cyber_collector.py`. One file per region, two sections.

### Schema

```json
{
  "region": "APAC",
  "collected_at": "2026-03-12T14:23:01Z",
  "geo_sources": [
    {
      "title": "South China Sea tensions drive supply chain restructuring",
      "snippet": "Multinational manufacturers are accelerating diversification away from single-region dependencies. Wind energy components face significant exposure.",
      "url": "https://example.com/article-1",
      "published_date": "2026-03-10"
    }
  ],
  "cyber_sources": [
    {
      "title": "APT campaign targets APAC OT manufacturing networks",
      "snippet": "Security researchers documented new intrusion campaigns targeting wind turbine control systems and predictive maintenance platforms.",
      "url": "https://example.com/article-2",
      "published_date": "2026-03-08"
    }
  ]
}
```

### Collector changes

Both `geo_collector.py` and `cyber_collector.py` already hold the raw source array from `osint_search.py` before building the aggregate summary. The change: serialize it to `intelligence_sources.json` as an additional write after the signal file. Signal file schemas (`geo_signals.json`, `cyber_signals.json`) are unchanged — agents reading them are unaffected.

`geo_collector.py` writes the file with `geo_sources` only.
`cyber_collector.py` reads the file if it exists and appends `cyber_sources`, or creates it fresh.

### Mock fixtures

Add `{region}_sources.json` to `data/mock_osint_fixtures/` for all 5 regions (APAC, AME, LATAM, MED, NCE). Each file contains 2–3 realistic fake entries per source type. In mock mode, collectors populate `intelligence_sources.json` from these fixtures instead of live search results.

### Dashboard rendering

Each region card gains a collapsible "Intelligence Sources" section below the Decision Intelligence block. Geo and cyber sources listed in separate sub-sections. Each source shows: title (linked if URL is real), snippet, and date. In mock mode, a small "MOCK" badge appears on each source. Section is absent if `intelligence_sources.json` does not exist.

### Export rendering

**PDF** — "Sources Consulted" appendix page. Table format: Region | Title | Date. Snippets omitted (space constrained). Escalated regions only.

**PPTX** — identical appendix slide with the same condensed table.

### Tests

- `geo_collector.py` in mock mode writes `intelligence_sources.json` with `geo_sources` array
- `cyber_collector.py` in mock mode appends `cyber_sources` to existing file
- Schema validation: required keys present, arrays non-empty in mock mode
- Graceful handling of empty source arrays (collector writes file with empty arrays, no crash)
- Signal files (`geo_signals.json`, `cyber_signals.json`) are unchanged after E-2 collector runs

---

## E-3 — Live Pipeline Telemetry

### New tool: `tools/send_event.py`

Fire-and-forget HTTP POST to `http://localhost:8000/internal/event`. Silently swallows connection errors — never blocks the pipeline whether or not the server is running.

CLI usage (called from hook scripts):
```bash
uv run python tools/send_event.py <EVENT_TYPE> <AGENT_ID> '<JSON_PAYLOAD>'
```

Example:
```bash
uv run python tools/send_event.py AGENT_START "regional-APAC" '{"region":"APAC","phase":"collecting"}'
```

Also appends the event to `output/system_trace.log` via `audit_logger.py` — hook events are always logged to the flat file regardless of whether the server is running.

### `server.py` change

One new endpoint:

```
POST /internal/event
Body: { "event_type": str, "agent_id": str, "payload": dict }
→ puts to event_queue → SSE broadcast to all connected dashboard clients
```

The existing `event_queue` and SSE endpoint already handle this pattern. No structural changes to `server.py`.

### Hook scripts

Three new scripts in `.claude/hooks/`:

| Script | Trigger | Event fired |
|---|---|---|
| `subagent-start.sh` | `subagent_start` hook | `AGENT_START` with region from agent name |
| `subagent-stop.sh` | `subagent_stop` hook | `AGENT_STOP` with region + exit code |
| `tool-failure.sh` | `post_tool_use_failure` hook | `TOOL_FAILURE` with tool name + error |

Each script: extracts relevant fields from hook environment variables, calls `send_event.py`, exits 0 (never blocks).

### Dashboard live strip

A status strip above the region cards, visible only during an active pipeline run. Each region shows its current state: `PENDING → COLLECTING → ANALYZING → ESCALATED / MONITOR / CLEAR`. Driven purely by SSE events — no polling. Strip collapses after `PIPELINE_COMPLETE` event is received.

### Graceful degradation

If `server.py` is not running (CLI-only pipeline mode):
- `send_event.py` fails silently
- Hook scripts exit 0
- `system_trace.log` still receives all events via `audit_logger.py`
- Dashboard shows the static post-run state as it does today

### Tests

- `send_event.py` handles connection refused without raising
- `send_event.py` logs to `system_trace.log` regardless of server availability
- `/internal/event` endpoint puts event to `event_queue` and returns 200

---

## File Change Summary

### E-1 (no new files)
- `tools/build_dashboard.py` — read + render `gatekeeper_decision.json` and `scenario_map.json` per region
- `tools/export_pdf.py` — add "Basis of assessment" field
- `tools/export_pptx.py` — add "Basis of assessment" field

### E-2
- `tools/geo_collector.py` — write `intelligence_sources.json` (geo_sources)
- `tools/cyber_collector.py` — append `intelligence_sources.json` (cyber_sources)
- `tools/build_dashboard.py` — render "Intelligence Sources" collapsible section
- `tools/export_pdf.py` — add "Sources Consulted" appendix
- `tools/export_pptx.py` — add "Sources Consulted" appendix slide
- `data/mock_osint_fixtures/` — add `{region}_sources.json` × 5
- `tests/` — new test file for intelligence_sources schema and collector behaviour

### E-3
- `tools/send_event.py` — new: fire-and-forget POST + log fallback
- `server.py` — add `POST /internal/event` endpoint
- `.claude/hooks/subagent-start.sh` — new
- `.claude/hooks/subagent-stop.sh` — new
- `.claude/hooks/tool-failure.sh` — new
- `static/index.html` — live status strip (SSE consumer)
- `tests/` — send_event and endpoint tests

---

## Definition of Done

- E-1: Dashboard shows Decision Intelligence block for all 5 regions; PDF/PPTX include basis of assessment; all existing tests pass
- E-2: Collectors write `intelligence_sources.json` in mock mode; dashboard renders collapsible sources; exports include appendix; new tests pass
- E-3: Hook fires → `system_trace.log` updated; dashboard live strip shows region states during pipeline run; send_event fails silently when server is offline
