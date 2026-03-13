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

gatekeeper_decision.json  ──► build_dashboard.py        (E-1: now read + surfaced)
scenario_map.json         ──► build_dashboard.py        (E-1: now read + surfaced — new read)
intelligence_sources.json ──► build_dashboard.py        (E-2: new)
                          ──► export_pdf.py             (E-2: new)
                          ──► export_pptx.py            (E-2: new)
```

No SQLite. No new servers until E-3. No changes to agent files or signal file schemas.

---

## E-1 — Decision Transparency

### What changes

- `tools/build_dashboard.py` — **new reads**: `gatekeeper_decision.json` and `scenario_map.json` per region (currently reads `data.json` only from each region directory); injects fields into Jinja template
- `tools/export_pdf.py` — adds "Basis of assessment" label + `gatekeeper_decision.rationale` value per region section
- `tools/export_pptx.py` — same one-line addition per region slide

### Data surfaced

**From `output/regional/{region}/gatekeeper_decision.json`** (written by gatekeeper-agent, not yet read by dashboard):
- `decision` (ESCALATE / MONITOR / CLEAR)
- `admiralty.rating` (e.g., "B2")
- `scenario_match` (e.g., "System intrusion")
- `dominant_pillar` (e.g., "Geopolitical")
- `rationale` (one-sentence assessment)

**From `output/regional/{region}/scenario_map.json`** (written by scenario_mapper.py, not yet read by dashboard):
- `financial_rank` (integer 1–9)
- `confidence` ("high" / "medium" / "low")

Note: `scenario_map.json` is currently not read by `build_dashboard.py`. Reading it is a real new code addition, not passive surfacing.

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

CLEAR and MONITOR regions render the same block, explaining why they were not escalated ("No top-4 financial impact scenario identified. Physical threat ranks #6."). Clear signals are as valuable as alerts.

### Graceful degradation

If `gatekeeper_decision.json` or `scenario_map.json` is absent (pre-D2 archived runs), the Decision Intelligence block is omitted silently.

### Tests

- `build_dashboard.py` renders Decision Intelligence block when `gatekeeper_decision.json` is present (use a test fixture file — do not depend on a prior pipeline run)
- `build_dashboard.py` omits block gracefully when file is absent
- `export_pdf.py` renders "Basis of assessment" when `gatekeeper_decision.json` is present (test fixture)
- `export_pdf.py` runs without exception when file is absent
- `export_pptx.py` — same two tests as PDF

---

## E-2 — Intelligence Provenance

### New file per region

`output/regional/{region}/intelligence_sources.json` — written by `geo_collector.py` (geo_sources array) and then extended by `cyber_collector.py` (cyber_sources array). Sequential write within a region; the collectors are always called in order geo → cyber by `run-crq.md` step 1.

### Schema

```json
{
  "region": "APAC",
  "collected_at": "2026-03-12T14:23:01Z",
  "geo_sources": [
    {
      "title": "South China Sea tensions drive supply chain restructuring",
      "snippet": "Multinational manufacturers are accelerating diversification away from single-region dependencies.",
      "url": "https://example.com/article-1",
      "published_date": "2026-03-10",
      "source": "Financial Times Asia",
      "mock": false
    }
  ],
  "cyber_sources": [
    {
      "title": "APT campaign targets APAC OT manufacturing networks",
      "snippet": "Security researchers documented new intrusion campaigns targeting wind turbine control systems.",
      "url": "https://example.com/article-2",
      "published_date": "2026-03-08",
      "source": "Reuters",
      "mock": false
    }
  ]
}
```

All source entries include: `title`, `snippet`, `published_date`, `source` (publication name), `url` (null in mock mode), `mock` (bool). In live mode `url` is populated and `mock` is false. In mock mode `url` is null, `mock` is true.

### Collector changes (scope clarification)

`osint_search.py` returns `[{title, snippet, url, published_date}]` — a raw article list. Currently, each collector's `collect()` function passes this list into a normalizer that produces the aggregate summary and then discards the raw list. The `collect()` return value is the normalized dict only.

**Required change:** modify `collect()` in both collectors to return a tuple `(normalized_dict, raw_sources_list)`. The calling code writes `normalized_dict` to the signal file (unchanged) and writes `raw_sources_list` to `intelligence_sources.json` (new).

`raw_sources_list` is the **post-deduplication** article list — the same list that is passed to `normalize()`. Both collectors currently call `run_search()` twice (two queries) and deduplicate before normalizing. The sources list written to `intelligence_sources.json` reflects the deduplicated union, consistent with what the normalized summary was built from.

This is a real implementation change to both collector functions, not a trivial side-effect write.

**Write sequence within a region (always sequential, enforced by run-crq.md):**
1. `geo_collector.py` writes `intelligence_sources.json` with `geo_sources` array only.
2. `cyber_collector.py` reads the file, merges in `cyber_sources`, writes the updated file.

**Guard:** `cyber_collector.py` checks that the file it reads contains a `geo_sources` key before merging. If absent (out-of-order invocation outside the pipeline), it logs a warning to `system_trace.log` and writes only `cyber_sources`. This prevents silent data loss.

### Mock mode

In mock mode, `osint_search.py` dumps the fixture file directly to stdout without transformation. The existing fixture format is `{title, summary, source, date}` — where `source` is a publication name (e.g., "Financial Times Asia"), not a URL.

**No fixture migration required.** The collectors map the fixture fields to the `intelligence_sources.json` schema on write:

| Fixture field | `intelligence_sources.json` field |
|---|---|
| `title` | `title` |
| `summary` | `snippet` |
| `source` | `source` (publication name, kept as-is) |
| `date` | `published_date` |

There is no `url` field in mock mode. The `intelligence_sources.json` entries in mock mode omit `url` or set it to `null`. The dashboard renders `source` (publication name) as the link label with no href in mock mode. A `"mock": true` flag is added to each source entry so the dashboard can render the "MOCK" badge.

### Dashboard rendering

Each region card gains a collapsible "Intelligence Sources" section below the Decision Intelligence block. Geo and cyber sources listed in separate sub-sections. Each source: title (linked if URL is real), snippet, date. In mock mode, a "MOCK" badge appears per source. Section absent if `intelligence_sources.json` does not exist.

### Export rendering

**PDF** — "Sources Consulted" appendix page. Table: Region | Title | Date. Snippets omitted (space constrained). Escalated regions only.

**PPTX** — identical appendix slide with the same condensed table.

### Tests

- `geo_collector.py` in mock mode: `intelligence_sources.json` written with `geo_sources` array, correct field names
- `cyber_collector.py` in mock mode: `intelligence_sources.json` extended with `cyber_sources` array, `geo_sources` preserved
- `cyber_collector.py` guard: file without `geo_sources` key → warns and writes `cyber_sources` only, no exception
- Schema validation: required keys present, arrays non-empty in mock mode
- Empty source array: collector writes file with empty array, no crash
- Signal files unchanged after E-2 collector runs (`geo_signals.json` and `cyber_signals.json` content identical to pre-E-2)

---

## E-3 — Live Pipeline Telemetry

### New tool: `tools/send_event.py`

Fire-and-forget HTTP POST to `http://localhost:8000/internal/event`. Silently swallows connection errors. Also appends to `output/system_trace.log` via `audit_logger.py` as fallback — this is the only log write for hook-originated events (there are no duplicate `audit_logger.py` calls in `run-crq.md` for the same agent lifecycle events, so no duplication occurs).

CLI usage (called from hook scripts):
```bash
uv run python tools/send_event.py <EVENT_TYPE> <AGENT_ID> '<JSON_PAYLOAD>'
```

### `server.py` change

One new endpoint:

```
POST /internal/event
Body: { "event_type": str, "agent_id": str, "payload": dict }
→ puts to event_queue → SSE broadcast to all connected dashboard clients
```

The existing `event_queue` and SSE infrastructure already handle this pattern.

### Hooks

**Claude Code's hook system** supports four event types: `PreToolUse`, `PostToolUse`, `Stop`, `Notification`. There is no `subagent_start` hook. The design uses the hooks that actually exist:

| Goal | Claude Code hook | Implementation |
|---|---|---|
| Agent completion telemetry | `Stop` hook | Hook script fires `AGENT_STOP` with agent name + exit code. Registered in `.claude/settings.json` alongside existing jargon/json auditor Stop hooks. |
| Tool failure telemetry | `PostToolUse` hook | Hook script checks exit code; if non-zero, fires `TOOL_FAILURE`. |
| Agent start telemetry | No hook available | `AGENT_START` events are logged via direct `audit_logger.py` calls added to `run-crq.md` before each agent delegation — not via hooks. |

Hook scripts live in `.claude/hooks/` and are registered by adding new `Stop` and `PostToolUse` entries to `.claude/settings.json`. There are no pre-existing Stop hooks in `settings.json` — these are new entries. Each script: extracts fields from hook environment variables, calls `send_event.py`, exits 0.

### Dashboard live strip

A status strip above the region cards, visible only during an active pipeline run. Each region: `PENDING → COLLECTING → ANALYZING → ESCALATED / MONITOR / CLEAR`. Driven purely by SSE — no polling. Strip collapses after `PIPELINE_COMPLETE` event.

### Graceful degradation

If `server.py` is not running:
- `send_event.py` fails silently
- Hook scripts exit 0, pipeline continues
- `system_trace.log` receives all events via `audit_logger.py`
- Dashboard shows static post-run state

### Tests

- `send_event.py` handles `ConnectionRefusedError` without raising
- `send_event.py` writes to `system_trace.log` regardless of server availability
- `POST /internal/event` puts event to `event_queue`, returns 200

---

## File Change Summary

### E-1 (no new files)
- `tools/build_dashboard.py` — new reads of `gatekeeper_decision.json` and `scenario_map.json` per region; render Decision Intelligence block
- `tools/export_pdf.py` — add "Basis of assessment" field; graceful absence handling
- `tools/export_pptx.py` — same

### E-2
- `tools/geo_collector.py` — modify `collect()` to return raw source list; write `intelligence_sources.json`
- `tools/cyber_collector.py` — same modification; read-merge-write `intelligence_sources.json` with guard
- `tools/build_dashboard.py` — render "Intelligence Sources" collapsible section
- `tools/export_pdf.py` — "Sources Consulted" appendix
- `tools/export_pptx.py` — "Sources Consulted" appendix slide
- `data/mock_osint_fixtures/{region}_geo.json` × 5 — no changes needed (existing flat arrays already compatible)
- `data/mock_osint_fixtures/{region}_cyber.json` × 5 — no changes needed
- `tests/test_intelligence_sources.py` — new test file

### E-3
- `tools/send_event.py` — new: fire-and-forget POST + trace log fallback
- `server.py` — add `POST /internal/event` endpoint
- `.claude/hooks/agent-stop.sh` — new: `Stop` hook → `AGENT_STOP` event
- `.claude/hooks/tool-failure.sh` — new: `PostToolUse` hook → `TOOL_FAILURE` event
- `.claude/settings.json` — register new hooks alongside existing Stop hooks
- `.claude/commands/run-crq.md` — add `AGENT_START` log calls before each agent delegation
- `static/index.html` — live status strip (SSE consumer)
- `tests/test_send_event.py` — new test file

---

## Definition of Done

**E-1:** Dashboard renders Decision Intelligence block for all 5 regions (present/absent file both handled). PDF and PPTX include "Basis of assessment". All existing 42 tests pass. 5 new tests pass.

**E-2:** Collectors write `intelligence_sources.json` in mock mode with correct schema. Dashboard renders collapsible sources section. PDF and PPTX include "Sources Consulted" appendix. Signal file schemas unchanged (verified by test). New tests pass.

**E-3:** `AGENT_START` events appear in `system_trace.log` during pipeline run. `AGENT_STOP` events appear in log and reach `event_queue` when server is running. Dashboard live strip shows region states during run. `send_event.py` fails silently when server is offline (verified by test).
