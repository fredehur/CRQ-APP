# CRQ Platform — Roadmap Design
**Date:** 2026-03-10
**Status:** Approved

---

## Context

The pipeline is complete and coherent in mock mode. Phases A (Web App), B (Agent Architecture), and C (Export Polish) are done. This document defines the build sequence for everything remaining — prioritized by architectural integrity first, intelligence quality second, observability third, and UI/UX last.

The Disler framework is the architectural north star: Unix CLI pipes, filesystem as state, zero chatbot behavior, hostile auditing. Every phase must reinforce this — not dilute it.

---

## Phase D-0 — Close Agentic Gaps (Pre-work)

**Do this before anything else. Estimated: ~1 hour.**

### 1. `global-validator-agent.md`

A haiku devil's advocate agent. Read-only — never writes. Challenges the global-builder's output before the pipeline advances.

- Checks: Admiralty rating consistency across regions, VaCR arithmetic, scenario mappings plausible
- Decision: `exit(0)` approve / `exit(2)` rewrite (max 2 cycles, then force-approve via circuit breaker)
- Wired as a second agent call in run-crq.md Phase 4, after global-builder completes

### 2. Verify mock feeds

All 5 `data/mock_threat_feeds/{region}_feed.json` files must have:
- `geo_signals` (object with `summary` and `lead_indicators`)
- `cyber_signals` (object with `summary`, `threat_vector`, `target_assets`)
- `dominant_pillar` (string)

These become the `--mock` fixture data for the OSINT tool chain. If any region is missing these fields, add them now.

---

## Phase D-1 — OSINT Tool Chain (Mock-First)

**Approach: Build bottom-up. Every tool works in `--mock` mode before any real search is wired.**

```
osint_search.py          ← search primitive (--mock / DDG / Tavily)
    ↓
geo_collector.py         ← geo queries → output/regional/{region}/geo_signals.json
    ↓
cyber_collector.py       ← geo_signals input → output/regional/{region}/cyber_signals.json
    ↓
scenario_mapper.py       ← noise filter → output/regional/{region}/scenario_map.json
```

### `tools/osint_search.py REGION QUERY [--mock]`

Single search primitive. One interface, three backends:
- `--mock`: reads fixture from `data/mock_threat_feeds/{region}_feed.json`
- No flag + no Tavily key: DuckDuckGo (free, no key)
- No flag + `TAVILY_API_KEY` set: Tavily API

Returns: `[{title, snippet, url, published_date}]` as JSON to stdout.

**Tavily is a one-line swap** — adding the key is all that changes.

### `tools/geo_collector.py REGION [--mock]`

Calls `osint_search.py` with geopolitical queries:
- `"{region} geopolitical instability 2026"`
- `"{region} sanctions elections conflict trade"`

Structures results into `geo_signals.json`:
```json
{
  "region": "APAC",
  "summary": "...",
  "lead_indicators": ["...", "..."],
  "source_urls": ["..."],
  "collected_at": "..."
}
```

Writes to: `output/regional/{region}/geo_signals.json`

### `tools/cyber_collector.py REGION [--mock]`

Takes `geo_signals.json` as input (reads from filesystem — Disler pattern).
Cross-references `data/master_scenarios.json` to identify which cyber threats the geo conditions predict.
Queries: `"{region} {predicted_threat_type} cyber attack 2026"`

Writes to: `output/regional/{region}/cyber_signals.json`:
```json
{
  "region": "APAC",
  "threat_vector": "...",
  "target_assets": ["..."],
  "scenario_prediction": "System intrusion",
  "source_urls": ["..."],
  "collected_at": "..."
}
```

### `tools/scenario_mapper.py REGION [--mock]`

Reads both `geo_signals.json` and `cyber_signals.json`.
Cross-references `data/master_scenarios.json` — if a signal doesn't map to a scenario, discard it.
Determines dominant pillar, scenario match, Admiralty credibility hint.

Writes to: `output/regional/{region}/scenario_map.json`:
```json
{
  "region": "APAC",
  "scenario_match": "System intrusion",
  "financial_rank": 3,
  "dominant_pillar": "Geopolitical",
  "admiralty_hint": "B2",
  "signal_count": 4,
  "noise_discarded": 1
}
```

---

## Phase D-2 — Wire It In

**Update the pipeline to consume the new tool chain.**

### `gatekeeper-agent.md`

Replace: reads `{region}_feed.json` directly
With: reads `geo_signals.json`, `cyber_signals.json`, `scenario_map.json`

Mock feeds become cache/fallback only — still used when `--mock` is passed.

### `run-crq.md` Phase 1

Add before gatekeeper, for each region:
```
uv run python tools/geo_collector.py {REGION} [--mock]
uv run python tools/cyber_collector.py {REGION} [--mock]
uv run python tools/scenario_mapper.py {REGION} [--mock]
```

Then gatekeeper runs as before — but now reads real (or mock) signal files instead of hardcoded feeds.

---

## Phase E — Observability Layer

**Build after D-2 is fully working. Purely additive — nothing in the existing architecture changes.**

Based on `phase5-observability.md`.

### What it adds

| Feature | Before | After |
|---|---|---|
| Agent identity | None | Unique `agent_id` + `session_id` per run |
| State visibility | Retry files only | Full event log in SQLite |
| Failure diagnosis | Guess from output | Exact hook, exact failure, exact retry count |
| Audit trail | Pass/fail on final output | Every tool call, hook event, and retry captured |

### Components

- `tools/identity.py` — session_id + agent_id generation
- `tools/send_event.py` — HTTP POST to obs server (silently swallows errors — never blocks pipeline)
- `tools/obs_server.py` — lightweight Python HTTP server + SQLite WAL
- `output/obs.db` — immutable event log, queryable by session_id

### Integration points (minimal changes to existing files)

- `jargon-auditor.py`: add one `send_event.py` call after pass/fail decision
- `run-crq.md` Phase 0: set `CRQ_SESSION_ID`, start obs_server in background

### Event schema

```json
{
  "event_id": "uuid",
  "session_id": "session_1741478400_a3f9c1",
  "agent_id": "regional-APAC_b72e4f1a",
  "event_type": "AuditResult",
  "region": "APAC",
  "status": "PASSED",
  "payload": {},
  "timestamp": "2026-03-10T14:23:01Z"
}
```

---

## Phase F-1 — Output Quality Fixes

**Fast wins. No architectural changes — just tighten what already exists.**

These are gaps identified after reviewing live pipeline output:

### 1. Admiralty rating completeness

`admiralty` is `null` in `run_manifest.json` for AME, MED, and NCE. The gatekeeper is not populating this field consistently. Fix: audit `gatekeeper-agent.md` prompt to require an Admiralty rating on every decision (escalated and clear), and update `write_gatekeeper_decision.py` to validate the field is non-null before writing.

### 2. Clear region summaries

LATAM and NCE get `"No credible threat identified. Region operating within normal risk parameters."` — a copy-paste placeholder. The gatekeeper should write a brief 1-sentence confidence statement citing the dominant signal that led to the CLEAR decision (e.g. "No credible top-4 financial impact scenario active. Geo signals stable, no state-aligned cyber activity detected."). This costs one prompt line in `gatekeeper-agent.md`.

### 3. Trend line

"Trend: — No history" appears on every region because there is no run-to-run comparison. Fix: `build_dashboard.py` and `export_pdf.py` should compare current VaCR to the previous archived run (read from `output/runs/` sorted by timestamp). Simple delta: `▲$2.1M` or `▼$0.5M` or `—`. No new agents needed.

### 4. `dominant_pillar` null for clear regions

Not critical, but worth populating so downstream consumers have a consistent schema. The gatekeeper already determines dominant pillar — it should write it even for CLEAR decisions.

---

## Phase F-2 — Dashboard Rework

**Requires dedicated design session. Full rebuild of `static/index.html` and `static/app.js`.**

### Problems with current dashboard

| Issue | Impact |
|---|---|
| Region cards show only severity + VaCR + scenario | E-1 data (rationale, admiralty, confidence, financial_rank) and E-2 data (sources) never appear in the live app |
| "View Brief" opens raw markdown in a `whitespace-pre-wrap` modal | Unreadable for stakeholders |
| Log panel consumes 1/3 of screen permanently | Developer telemetry in a board-facing tool |
| Executive summary buried below region cards | Most important content shown last |
| Clear regions say only "No active threats" | No signal quality, no confidence, no Admiralty |
| Mode selector ("Tools / Full LLM") visible on main UI | Dev concern — not relevant to stakeholders |
| No navigation | No path to PDF report, PPTX, historical runs |
| All 5 cards same size, no visual hierarchy | Critical/High regions need more visual weight |

### Design goals

- **Information density:** Cards should surface all available intelligence — rationale, Admiralty, confidence, dominant pillar, top source
- **Hierarchy:** Escalated regions rendered larger and first; CLEAR regions as compact status badges in a separate row
- **Rendered briefs:** Replace raw-text modal with rendered markdown (use `marked.js` CDN — zero build tooling)
- **Executive summary at top:** Prominent, above the fold, not hidden below cards
- **Log panel as drawer:** Collapsible side panel or tab — not permanently open
- **Navigation bar:** Overview | Reports | History tabs — no page reload, just section switching
- **Remove dev controls from main view:** Mode selector moved to a settings/debug panel

### Layout sketch

```
┌─────────────────────────────────────────────────────┐
│ Header: Logo + client name + nav tabs (Overview / Reports / History) + Run button │
├─────────────────────────────────────────────────────┤
│ KPI strip: Total VaCR | Escalated | Monitor | Clear | Last Run | Trend  │
├─────────────────────────────────────────────────────┤
│ Executive Summary (full width, prominent)           │
├─────────────────────────────────────────────────────┤
│ Escalated Regions (large cards, left-to-right by severity)              │
│ [AME CRITICAL $22M]   [APAC HIGH $18.5M]   [MED MEDIUM $4.2M]          │
├─────────────────────────────────────────────────────┤
│ Clear Regions (compact row of status chips)         │
│ [LATAM ✓ Clear A1]   [NCE ✓ Clear]                  │
├─────────────────────────────────────────────────────┤
│ [Live Event Log — collapsible drawer at bottom]     │
└─────────────────────────────────────────────────────┘
```

### Rich card content (escalated)

Each escalated card surfaces:
- Severity badge + VaCR (current)
- **Scenario** + financial rank (e.g. "Ransomware — Rank #1 globally")
- **Admiralty rating** with tooltip
- **Confidence** level
- **Dominant pillar** (Geo / Cyber)
- **Rationale** (1–2 sentence gatekeeper decision basis)
- **Top source** headline (from E-2 `intelligence_sources.json`)
- "Read Full Brief" → rendered markdown panel (marked.js)
- "View Sources" → collapsible source list

### Output structure — meaningful information hierarchy

The dashboard should present intelligence in the order a board member reads it, not in the order the pipeline produces it:

```
1. Global posture (KPIs + executive summary)   ← what's the headline?
2. Active threats by priority (escalated cards) ← where is the money at risk?
3. Decision basis (rationale + admiralty)        ← why do we believe this?
4. Evidence (sources consulted)                  ← what signals led here?
5. Clear regions (signal health, not just absence) ← what did we rule out and why?
6. Pipeline audit trail (collapsible)            ← how was this produced?
```

Each section answers a different question for a different audience:
- **Sections 1–2:** Board — headline risk, dollar exposure
- **Sections 3–4:** CISO / risk committee — decision quality, source credibility
- **Section 5:** Regional ops — their region was checked, what was found
- **Section 6:** Audit / compliance — pipeline provenance

The current dashboard collapses sections 1–6 into a flat card grid with a log panel — no hierarchy, no progression, no audience awareness. The rework should impose this reading order explicitly via layout and visual weight.

---

## Phase F-3 — Intelligence Quality Rework

**Must be completed before F-2 (dashboard). There is no point polishing a UI around weak output.**

### Mission restatement

> Collect geopolitical and cyber OSINT → identify events and trends that threaten business delivery → couple them to the CRQ scenario register → produce output a senior intelligence analyst would sign off on.

The pipeline structure is correct. The intelligence reasoning and output quality are not yet at this standard. This phase fixes both.

---

### Step 1: Agent chain exploration ✅ Done

**Assessment completed 2026-03-13. Findings below — these drove Steps 2–5.**

For each agent, assessed: role clarity, context quality, model fit, output contract, failure modes.

#### Verdicts

| Agent | Verdict | Core problem |
|---|---|---|
| `gatekeeper-agent` (haiku) | **REFOCUS** | Output contract broken — admiralty written to `gatekeeper_decision.json` but never propagated to `data.json` by orchestrator |
| `regional-analyst-agent` (sonnet) | **REFOCUS** | Input contract misaligned — spec references `mock_threat_feeds/` (old model, doesn't exist); OSINT pipeline writes `geo_signals.json` instead |
| `global-builder-agent` (sonnet) | **REWRITE** | Required fields (`admiralty_rating`, `velocity`) not reliably available from `data.json` because of upstream propagation failure |
| `global-validator-agent` (haiku) | **KEEP AS-IS** | Correct and well-scoped — finding real bugs, not creating them |
| `scenario_mapper.py` (Python) | **KEEP AS-IS** | Works for its purpose; Step 3 moves scenario coupling responsibility to the analyst |
| Orchestrator `run-crq.md` | **REFOCUS** | Missing propagation step, blind rewrite loops, no OSINT error recovery |

#### Critical finding: admiralty null bug is an orchestrator bug

The root cause is not the gatekeeper — it correctly writes `admiralty` to `gatekeeper_decision.json`. The bug is that `run-crq.md` calls `write_region_data.py` without reading `gatekeeper_decision.json` first to extract and pass `admiralty` into `data.json`. It's a missing pipe — one added step in the orchestrator unblocks the entire downstream chain (global builder, validator, dashboard, PDF).

#### Cross-cutting findings

1. **Propagation gap** — `gatekeeper_decision.json` is written but not consumed. `data.json` is missing `admiralty`, `dominant_pillar`, `rationale` for all regions.
2. **Input contract mismatch** — `regional-analyst-agent.md` was written for the pre-D1 data model (`mock_threat_feeds/`). The OSINT pipeline writes `geo_signals.json` / `cyber_signals.json`. These are incompatible.
3. **Blind rewrite loops** — when the jargon auditor returns `exit(2)`, the orchestrator re-delegates to the agent without passing the failure message. Agent rewrites blind with no feedback on what was wrong.
4. **Scenario coupling in wrong place** — haiku (keyword scorer output) decides the scenario that drives the entire brief. Sonnet analyst never re-examines this. Analytical judgment happens at the cheapest, least-informed point in the chain.

#### Top 3 changes by impact

1. Fix admiralty propagation in `run-crq.md` — one step, unblocks global builder + validator + all downstream consumers
2. Align `regional-analyst-agent.md` input contract to `geo_signals.json` / `cyber_signals.json`
3. Pass jargon auditor failure message back to the rewriting agent

---

### Step 2: Gatekeeper — pure triage

**Current problem:** The gatekeeper does three things: triage (yes/no), scenario coupling (which scenario is this?), and Admiralty rating. Scenario coupling is the analytical core of the product and it's being done by a haiku model reading a keyword-scorer's output — not by an analyst reasoning over evidence.

**Target state:** The gatekeeper's job is binary triage:
- Read `geo_signals.json`, `cyber_signals.json`, `scenario_map.json`
- Answer: *"Is there a credible signal that warrants deeper analysis — yes or no?"*
- Assign Admiralty rating based on signal quality and corroboration
- Write a one-sentence triage rationale
- `scenario_map.json` is used as a hint, not accepted as verdict

The gatekeeper does NOT determine `scenario_match`. That is the analyst's job.

**What changes:** `gatekeeper-agent.md` prompt rewritten. Output schema simplified — `scenario_match` field removed from `gatekeeper_decision.json` (or kept as an advisory hint, clearly labelled as such). Decision remains ESCALATE / MONITOR / CLEAR.

---

### Step 3: Regional analyst — scenario coupling + event/trend classification

**Current problem:** The analyst writes a brief around a scenario that was pre-decided by a keyword scorer. It has no access to the CRQ scenario register and is effectively narrating rather than reasoning.

**Target state:** The analyst is the intelligence engine. It:

1. **Reads all signal files** — `geo_signals.json`, `cyber_signals.json`, `intelligence_sources.json`
2. **Reads the CRQ scenario register** — `data/master_scenarios.json` (given in context)
3. **Reads the company profile** — `data/company_profile.json` (crown jewels, what the org cares about)
4. **Does its own scenario coupling** — reasons over signals and identifies which scenario best describes the threat and why. This is the analytical judgment that was previously delegated to a keyword counter.
5. **Classifies event vs trend** — based on source language and publication dates:
   - **Event** — a specific incident that happened recently ("ransomware hit a turbine manufacturer in Texas last week")
   - **Trend** — a pattern building over time ("ransomware targeting energy manufacturing has been increasing across the sector")
   - **Mixed** — a trend that has materialized into a specific event
   This classification is written as a structured field `signal_type` AND incorporated naturally in the prose.
6. **Writes the brief to analyst standard** (see Step 4)
7. **Updates `data.json`** — after completing the brief, the analyst writes back its `scenario_match`, `signal_type`, and `financial_rank` to the regional `data.json` so downstream consumers have authoritative structured data. This replaces the keyword mapper's output as the source of truth.

**What changes:** `regional-analyst-agent.md` prompt significantly rewritten. Agent now receives `master_scenarios.json` and `company_profile.json` as explicit context. Agent writes `data.json` update at end of task. `signal_type` field added to `data.json` schema.

---

### Step 4: Output quality standard

Every brief produced by the regional analyst and global builder must meet this bar:

**Opening:** Business delivery risk first — not the threat name, not the scenario label.
> "AeroGrid's Americas supply chain faces acute disruption risk..." — not "Ransomware activity detected in AME."

**Body — three required elements:**
1. **What is known** (evidenced from sources): cite specific signals, headlines, or indicators that are factual
2. **What is assessed** (analytical judgment): clearly signalled with language like "assessed," "likely," "consistent with" — not stated as fact
3. **CRQ coupling**: explicitly connect the threat to the scenario register — "this pattern is consistent with the Ransomware scenario ($22M exposure in the CRQ register at financial rank 1)"

**Signal classification:** State clearly whether this is an event, a trend, or both. Brief language should reflect this — "a confirmed incident last week" vs "a sustained and worsening trend."

**Closing:** What the reader should watch for or do — not a summary of what was already said.

**Global builder** synthesis must add intelligence beyond aggregation — the global brief should identify cross-regional patterns, compound risk (multiple regions escalated simultaneously), and the single most important thing the exec team needs to know.

**What changes:** `regional-analyst-agent.md` and `global-builder-agent.md` prompts rewritten with explicit quality instructions and output format examples.

---

### Step 5: Validate output quality on mock data

Run the full pipeline in mock mode after each agent change. Evaluate each brief against the quality standard in Step 4 before moving to the next agent.

The validator checklist for each brief:
- [ ] Opens with business delivery risk, not threat name
- [ ] Distinguishes evidenced facts from analytical assessments
- [ ] Explicitly names the CRQ scenario + financial figure
- [ ] Labels signal as event, trend, or mixed
- [ ] Closes with forward-looking statement
- [ ] Zero technical jargon (jargon-auditor.py must pass)
- [ ] Reads like a senior analyst wrote it, not a risk register entry

Only when mock output consistently passes this checklist is F-3 complete.

---

## Phase F-4 — Live OSINT Upgrade

**The pipeline is already written for live search. This phase turns it on.**

### Current state

`osint_search.py` has three backends, selectable at runtime:
- `--mock` flag → reads `data/mock_osint_fixtures/{region}_{geo|cyber}.json` (current default)
- No flag + no `TAVILY_API_KEY` → DuckDuckGo (free, no key)
- No flag + `TAVILY_API_KEY` set → Tavily Search API (paid, higher quality)

The `run-crq.md` pipeline passes `--mock` to all collector calls. Removing that flag is the only change needed to go live.

### What "live" looks like end-to-end

```
Run pipeline (no --mock)
  → geo_collector.py APAC
      → osint_search.py "APAC geopolitical instability 2026" [DDG or Tavily]
      → returns [{title, snippet, url, published_date}]
      → writes output/regional/apac/geo_signals.json + intelligence_sources.json
  → cyber_collector.py APAC
      → reads geo_signals.json → predicts threat type
      → osint_search.py "APAC system intrusion cyber attack 2026"
      → merges into intelligence_sources.json
  → scenario_mapper.py APAC
      → cross-refs master_scenarios.json → writes scenario_map.json
  → gatekeeper reads real signal files → escalation decision
  → regional-analyst writes brief citing live sources
  → dashboard shows real source headlines + URLs in source cards
```

### Steps to activate

1. **DDG mode (free):** Remove `--mock` from collector calls in `run-crq.md`. DDG has rate limits — add a `time.sleep(1)` between region calls or they'll get blocked.
2. **Tavily mode (better quality):** Set `TAVILY_API_KEY` in `.env`. The osint_search.py backend selection is automatic.
3. **`.env` file** — create one at project root. It's already in `.gitignore`.

### Recommended sequence

Build F-2 (dashboard rework) first on mock data so you can see sources rendering properly. Then activate F-3 to see real OSINT flowing through the same pipeline with real sources populating the source cards.

---

---

## Phase G-0 — Shared OSINT Topic Registry (prerequisite to G and H)

**Locked 2026-03-16. Must be built before G or H.**

### Problem

All three OSINT collectors (`geo_collector.py`, `cyber_collector.py`, `youtube_collector.py`) currently run generic regional queries. There is no shared definition of *what the platform is watching*. Each collector independently decides what to search — no coordination, no convergence.

### Solution: `data/osint_topics.json`

A single shared topic registry consumed by all three collectors. One place to define what the platform tracks. Editorial judgment lives in the data file, not the code.

```json
[
  {
    "id": "iran-us-tensions",
    "label": "Iran–US Escalation",
    "type": "event",
    "keywords": ["Iran", "US sanctions", "Strait of Hormuz", "IRGC", "Persian Gulf"],
    "regions": ["MED", "APAC"],
    "active": true
  },
  {
    "id": "ot-cyber-attacks",
    "label": "OT/ICS Cyber Attacks",
    "type": "trend",
    "keywords": ["OT security", "ICS attack", "SCADA", "operational technology", "industrial control"],
    "regions": ["AME", "NCE", "APAC"],
    "active": true
  }
]
```

**Fields:**
- `id` — stable identifier, referenced in signal output for traceability
- `label` — human-readable name for dashboard display
- `type` — `"event"` or `"trend"` → maps directly to `signal_type` in `data.json`
- `keywords` — used by all three collectors for focused queries
- `regions` — which regional collectors include this topic (a MED-specific topic doesn't pollute APAC)
- `active` — toggle without deleting (deactivated topics are skipped but preserved for audit)

### How each collector uses it

**Existing collectors (retrofit in G-0):**
`geo_collector.py` and `cyber_collector.py` run their current baseline regional scan **plus** one focused query per active topic scoped to that region. Two passes — baseline catches unexpected events, topic queries deepen focus on known ones.

**`youtube_collector.py` (Phase H):**
Uses `osint_topics.json` as its primary query driver. No baseline scan — YouTube search is intentionally topic-focused.

**GPT Researcher (Phase G):**
Topic keywords become the research questions fed to GPT Researcher, replacing generic regional queries entirely.

### Signal convergence payoff

When `geo_collector`, `cyber_collector`, and `youtube_collector` all return hits on `"ot-cyber-attacks"` for AME, the regional analyst sees corroboration across three independent source types. Admiralty rating rises. This is the core value of a shared topic registry.

### Build order for G-0

```
G-0-1  Create data/osint_topics.json           seed with 5–8 tracked topics          ~30 min
G-0-2  Retrofit geo_collector.py               add topic-focused pass per region      ~1 hour
G-0-3  Retrofit cyber_collector.py             add topic-focused pass per region      ~1 hour
G-0-4  Update mock fixtures                    add topic-keyed signals to fixtures    ~1 hour
G-0-5  Update regional-analyst-agent prompt    reference topic IDs in signal output   ~30 min
```

---

## Phase G — Deep OSINT via GPT Researcher

**Depends on:** F-4 complete (live OSINT activated, `--mock` removed from pipeline)
**Goal:** Replace shallow 1–3 result DDG/Tavily searches with multi-step autonomous research producing board-quality intelligence. Same pipeline contract, dramatically better input signal.

---

### What GPT Researcher Does

GPT Researcher is an autonomous Python research agent. Given a research question, it:
1. Decomposes the question into sub-queries
2. Searches 20+ sources in parallel
3. Scrapes and filters content
4. Synthesizes a structured research report

This directly upgrades the two weakest points in the current OSINT chain: breadth (only 1–3 results) and synthesis (raw snippets, no cross-source reasoning).

**Library:** `gpt-researcher` (pip). Async Python. Requires an LLM backend (defaults to OpenAI; can be configured for Claude via `OPENAI_BASE_URL` + `OPENAI_API_KEY` shim or its native Claude config).

---

### Architecture

#### Current OSINT chain (F-4 baseline)

```
geo_collector.py REGION
  → osint_search.py "{region} geopolitical instability 2026"  (1-3 results)
  → geo_signals.json

cyber_collector.py REGION
  → osint_search.py "{region} {predicted_threat} cyber attack 2026"  (1-3 results)
  → cyber_signals.json
```

#### Phase G target state

```
deep_collector.py REGION geo
  → GPTResearcher("{region} geopolitical risk wind energy infrastructure 2026")
  → 20+ sources, synthesized research report
  → LLM extraction step → geo_signals.json  (same schema as today)

deep_collector.py REGION cyber
  → reads geo_signals.json (to inherit predicted threat type)
  → GPTResearcher("{region} {predicted_threat} critical infrastructure cyber threat 2026")
  → 20+ sources, synthesized research report
  → LLM extraction step → cyber_signals.json  (same schema as today)
```

The rest of the pipeline — `scenario_mapper.py`, gatekeeper, analyst, global builder — is **completely unchanged**. Same file contracts, same schemas.

---

### Three Run Modes (final state)

| Flag | Backend | Speed | Cost | Use case |
|---|---|---|---|---|
| `--mock` | Fixture files | ~1s | Free | Dev, CI, demos |
| *(no flag)* | DDG / Tavily | ~10s | Free / low | Daily runs, QA |
| `--deep` | GPT Researcher | ~60–90s/region | OpenAI API | Board runs, high-stakes decisions |

All three modes write the same `geo_signals.json` / `cyber_signals.json` schema. The pipeline is mode-agnostic after the collectors run.

---

### Components to Build

#### G-1 — Dependency + config

**File changes:**
- `pyproject.toml` — add `gpt-researcher` dependency
- `.env.example` — add `OPENAI_API_KEY` (required for GPT Researcher), `GPT_RESEARCHER_LLM` (optional, for Claude override)
- `.gitignore` — already covers `.env`

**GPT Researcher LLM config:** By default uses `gpt-4o`. For Claude:
```python
# in deep_collector.py
import os
os.environ["OPENAI_BASE_URL"] = "https://api.anthropic.com/v1"
os.environ["OPENAI_MODEL_NAME"] = "claude-sonnet-4-6"
```
Or use their native `GPT_RESEARCHER_LLM=anthropic` config if available in the installed version.

---

#### G-2 — `tools/deep_collector.py` (new file)

The core wrapper. Two responsibilities:
1. Run GPT Researcher with a region-appropriate query
2. Extract structured signals from the research report via a second LLM call

**Interface:**
```bash
uv run python tools/deep_collector.py <REGION> <geo|cyber>
# Writes output/regional/{region}/geo_signals.json  OR  cyber_signals.json
# Exits 0 on success, 1 on failure
```

**Geo query template:**
```python
def geo_query(region: str) -> str:
    return (
        f"Geopolitical risk assessment for {region} region affecting wind energy "
        f"and renewable infrastructure in 2026. Focus on: state actor activity, "
        f"trade policy, sanctions, political instability, supply chain disruption, "
        f"regulatory changes affecting manufacturing and service operations."
    )
```

**Cyber query template (reads geo_signals.json first):**
```python
def cyber_query(region: str, predicted_threat: str) -> str:
    return (
        f"Cyber threat intelligence for {region} in 2026, specifically {predicted_threat} "
        f"targeting wind turbine manufacturing, OT/ICS systems, and global service operations. "
        f"Focus on threat actor groups, recent incidents, sector-specific targeting patterns, "
        f"and operational disruption risk."
    )
```

**Extraction step** — after GPT Researcher returns a narrative report, a second LLM call extracts it into the existing JSON schema:

```python
async def extract_geo_signals(region: str, research_report: str) -> dict:
    """Extract structured geo_signals.json from GPT Researcher narrative."""
    prompt = f"""
    Extract structured geopolitical signal data from this research report.
    Return ONLY valid JSON matching this exact schema:
    {{
      "region": "{region}",
      "summary": "2-3 sentence synthesis of key geopolitical drivers",
      "lead_indicators": ["indicator 1", "indicator 2", "indicator 3"],
      "source_urls": ["url1", "url2"],
      "signal_strength": "HIGH|MEDIUM|LOW",
      "collected_at": "<ISO timestamp>"
    }}

    Research report:
    {research_report}
    """
    # Call Claude claude-haiku-4-5-20251001 for extraction (cheap, fast, structured)
    # Parse + validate JSON, raise on schema mismatch
```

**Error handling:**
- If GPT Researcher fails (network, API quota): log to `system_trace.log` and exit 1 — orchestrator falls back to standard live mode
- If extraction step fails to produce valid JSON: retry once, then exit 1
- Never silently degrade to mock — caller must decide fallback behavior

---

#### G-3 — Wire `--deep` into existing collectors

**`tools/geo_collector.py`** — add `--deep` flag:
```python
if args.deep:
    subprocess.run(["uv", "run", "python", "tools/deep_collector.py", region, "geo"])
    sys.exit(0)
# else: existing DDG/Tavily path unchanged
```

**`tools/cyber_collector.py`** — same pattern:
```python
if args.deep:
    subprocess.run(["uv", "run", "python", "tools/deep_collector.py", region, "cyber"])
    sys.exit(0)
```

This keeps the existing code untouched — `--deep` is a short-circuit that delegates and exits.

---

#### G-4 — `run-crq.md` deep mode toggle

Add a `DEEP_OSINT` variable at the top of the orchestrator:

```bash
# Set to "--deep" for board runs, "" for standard live, "--mock" for dev
OSINT_MODE="--mock"
```

Phase 1 collector calls become:
```bash
uv run python tools/geo_collector.py {REGION} $OSINT_MODE
uv run python tools/cyber_collector.py {REGION} $OSINT_MODE
uv run python tools/scenario_mapper.py {REGION} $OSINT_MODE
```

One variable controls all 10 collector calls (5 regions × 2 signal types). Switching modes is a one-line change.

---

#### G-5 — Mock fixtures for deep mode (CI coverage)

GPT Researcher calls cannot run in CI (no API key, too slow). Add `--mock` handling to `deep_collector.py` that reads from:
```
data/mock_osint_fixtures/{region}_deep_geo.json
data/mock_osint_fixtures/{region}_deep_cyber.json
```

These fixtures should contain richer signal content than the standard mock fixtures — representing what GPT Researcher would realistically produce. Create all 10 files (5 regions × 2 types).

The existing test suite (`42 tests passing`) should pass unchanged since `--mock` path in collectors is unmodified.

---

#### G-6 — Dashboard "deep research" provenance badge

When the pipeline ran in `--deep` mode, the dashboard should show a signal quality indicator.

**Implementation:**
- `run-crq.md` writes `"osint_mode": "deep|live|mock"` into `run_manifest.json` at pipeline start
- `build_dashboard.py` reads this field and renders a badge in the KPI strip: `"Deep Research"` (gold), `"Live OSINT"` (blue), `"Mock Data"` (grey)
- Tooltip on the badge explains what mode means

This gives auditors and stakeholders visibility into signal quality without changing the data contract.

---

### LLM Backend Decision

**Recommended: OpenAI GPT-4o (GPT Researcher default)**
- Native integration, no config changes needed beyond `OPENAI_API_KEY`
- Fast, reliable, strong at research synthesis
- Cost: ~$0.05–0.15 per region pair (geo + cyber) = ~$0.50–0.75 per full 5-region run

**Alternative: Configure for Claude**
- Use `claude-sonnet-4-6` for research synthesis
- Requires `OPENAI_BASE_URL` shim or GPT Researcher's native Anthropic config
- Keeps the full stack on Anthropic; slightly more complex setup
- Recommended if Anthropic API is already provisioned for this project

**Decision (locked 2026-03-14):** Use Claude (`claude-sonnet-4-6`) as the GPT Researcher LLM backend. Keeps the full stack on Anthropic. Requires `ANTHROPIC_API_KEY` in `.env` and the GPT Researcher Anthropic config (`LLM_PROVIDER=anthropic`, `SMART_LLM_MODEL=claude-sonnet-4-6`, `FAST_LLM_MODEL=claude-haiku-4-5-20251001`). See GPT Researcher docs for full env var list.

---

### Queries Per Region (Reference)

| Region | Geo query focus | Cyber query focus |
|---|---|---|
| APAC | China-Taiwan tensions, South China Sea, semiconductor supply chain, Japan/South Korea manufacturing | State-sponsored intrusion, supply chain compromise, OT targeting in manufacturing |
| AME | US energy policy, Canada trade, political polarization, grid regulation changes | Ransomware targeting energy sector, CISA advisories, critical infrastructure |
| LATAM | Brazil political risk, Argentina economic instability, copper/lithium supply chain | Financially-motivated cybercrime, weak enforcement environments |
| MED | Turkey-EU relations, North Africa instability, Suez logistics, Southern Europe grid | Insider risk in service operations, state-adjacent hacktivism |
| NCE | Germany energy transition, Nord Stream fallout, Scandinavia wind buildout, Russia posture | Nation-state espionage (Russia/China), Nordic OT targeting, supply chain integrity |

---

### Failure Modes and Mitigations

| Failure | Mitigation |
|---|---|
| GPT Researcher API quota exceeded | Exit 1 → orchestrator logs warning → falls back to standard live mode for that region |
| Extraction LLM produces invalid JSON | Retry once → if still invalid, exit 1 → orchestrator falls back |
| GPT Researcher rate-limits between regions | Add `asyncio.sleep(2)` between region calls in orchestrator |
| Network timeout on source scraping | GPT Researcher has internal timeout; set `max_subtopics=3` to reduce calls on slow networks |
| OpenAI outage | Exit 1 → orchestrator falls back — the pipeline cannot stall waiting for a single tool |

---

### Build Order for Phase G

```
G-1  Dependency + config      pyproject.toml, .env.example              ~30 min
G-2  deep_collector.py        GPT Researcher wrapper + LLM extraction    ~2 hours
G-3  Wire --deep into collectors  geo_collector.py, cyber_collector.py   ~30 min
G-4  run-crq.md toggle        OSINT_MODE variable + collector calls       ~15 min
G-5  Deep mock fixtures        10 fixture files for CI                    ~1 hour
G-6  Dashboard badge           run_manifest.json + build_dashboard.py    ~30 min
```

**Total estimated build time:** ~4–5 hours. G-2 is the critical path.

---

---

## Phase H — YouTube OSINT Collector

**Concept:** Add YouTube transcripts as a first-class OSINT source. Tracks user-defined **topics** (events or trends) across a curated list of approved channels. Feeds into the existing OSINT signal chain — no pipeline changes required downstream.

### Design decisions (locked 2026-03-16)

- **Source model:** Curated approved channels list (`data/youtube_sources.json`) + keyword filter per topic. Editorial judgment lives in the data file, not the code.
- **Topic model:** User defines tracked topics as Event or Trend — e.g. `{ "id": "iran-us-tensions", "type": "event", "keywords": [...], "regions": ["MED", "APAC"] }`. The `type` maps directly to `signal_type` in `data.json`.
- **Extraction:** Claude Haiku LLM call per transcript chunk — keyword scoring is too brittle for conversational content.
- **Volume control:** Max 3 videos per topic per run (ranked by recency then view count). Max 1 video per channel per run. Transcripts over 60 min chunked → summarised to 3 key claims. No new videos in window → logged as "no new signal" (silence is information).
- **Transcript source:** `youtube-transcript-api` Python library (no API key required for public videos). YouTube Data API (free tier) for channel → recent video lookup.

### Data files

```
data/youtube_sources.json    # Approved channel list: [{channel_id, name, credibility_tier, region_focus}]
data/youtube_topics.json     # Tracked topics: [{id, type, keywords, regions}]
```

### New tool

```
tools/youtube_collector.py <REGION> [--mock]
```

Outputs `output/regional/{region}/youtube_signals.json` — same schema as `geo_signals.json` / `cyber_signals.json`.

### Integration point

Regional analyst reads `youtube_signals.json` alongside existing signal files. No gatekeeper changes needed — the analyst already reasons over all signal files holistically.

### Build order for Phase H

```
H-1  Data files           youtube_sources.json + youtube_topics.json + mock fixtures    ~1 hour
H-2  youtube_collector.py Transcript fetch + Haiku extraction + signal schema output    ~2 hours
H-3  Wire into pipeline   regional analyst reads youtube_signals.json                   ~30 min
H-4  run-crq.md toggle    add youtube_collector call per region in Phase 1 fan-out      ~15 min
H-5  Mock fixtures        5 regional youtube_signals.json fixtures for CI               ~1 hour
```

---

## Phase I — Analyst Feedback Loop

**Added 2026-03-17. Priority: high.**

Analysts reading reports have no way to rate signal quality, flag false positives, or note when the gatekeeper got it wrong. Without this, the platform has no signal about whether it's improving over time.

### Design

- Per-run `feedback.json` stored alongside `run_manifest.json` in `output/runs/{timestamp}/`
- Schema: `[{ "region": "AME", "rating": "accurate|overstated|understated|false_positive", "note": "...", "analyst": "...", "timestamp": "..." }]`
- Lightweight UI: thumbs up/down + optional text comment per region card in the dashboard
- FastAPI endpoint: `POST /api/feedback/{run_id}` writes to the run's `feedback.json`
- Pipeline reads prior run's `feedback.json` at startup (Phase 0) and passes it as context to the gatekeeper and analyst agents — "last time you called this ESCALATE, the analyst rated it overstated"
- `tools/feedback_summary.py` aggregates feedback across runs into `output/feedback_trends.json` for meta-review

### Build order

```
I-1  feedback.json schema + FastAPI endpoint                         ~1 hour
I-2  Dashboard UI — rating buttons per region card                   ~1 hour
I-3  Pipeline reads prior feedback — passes to gatekeeper + analyst  ~1 hour
I-4  feedback_summary.py aggregation tool                            ~30 min
```

---

## Phase J — Historical Intelligence Charts

**Added 2026-03-17. Priority: medium.**

6 archived runs exist. The velocity analysis reads them but only outputs a text brief. VaCR over time and severity trend are invisible in the UI — a word ("stable") when it should be a sparkline.

### Design

- `tools/build_history.py` — reads `output/runs/*/run_manifest.json`, emits `output/history.json` with per-region time series: `[{ "timestamp", "severity", "vacr_usd", "status", "primary_scenario" }]`
- Dashboard **History tab** — per-region VaCR sparkline (last 10 runs), severity heatmap calendar, scenario drift view ("AME has been Ransomware for 6 consecutive runs")
- No new dependencies — chart rendering via inline SVG or a minimal library already in scope
- `build_history.py` called at end of Phase 6 (finalize) each pipeline run, after `archive_run.py`

### Build order

```
J-1  build_history.py — reads archived runs, writes history.json      ~1 hour
J-2  Wire into Phase 6 of run-crq.md                                  ~15 min
J-3  Dashboard History tab — sparklines + severity heatmap            ~2 hours
J-4  Scenario drift detection — flag when primary_scenario unchanged  ~30 min
     N consecutive runs ("AME: Ransomware for 6 runs") → note in global brief
```

---

## Phase F-5 — Parked (Longer Horizon)

- **Audience tabs** — Board / CISO / Ops / Sales overlays on same JSON data
- **Interactive analyst chat** — ask follow-ups about pipeline output via Claude API
- **Scheduled runs + digest notifications** — cron + Slack/email summary
- **NotebookLM audio briefing** — podcast-style board briefing (API access required)

---

## Build Order Summary

```
D-0  Close agentic gaps          global-validator-agent + mock feed audit                      ✅ Done
D-1  OSINT tool chain            osint_search → geo → cyber → scenario_mapper                  ✅ Done
D-2  Wire it in                  gatekeeper + run-crq Phase 1                                  ✅ Done
E    Intelligence Transparency   decision basis, sources, live telemetry                        ✅ Done
F-1  Output quality fixes        admiralty completeness, clear summaries, trend                 ✅ Done
F-3  Intelligence quality        agent exploration, scenario coupling, event/trend, brief std   ✅ Done
F-4  Live OSINT                  remove --mock, add Tavily key                                  ✅ Done
G-0  Shared OSINT Topic Registry  osint_topics.json, retrofit geo+cyber collectors, convergence ✅ Done (2026-03-16)
F-2  Analyst dashboard           SIGINT terminal workstation, split-pane, signal clusters       ✅ Done (2026-03-17)
     Research collector          Target-centric OSINT loop — 3 LLM calls, scratchpad            ✅ Done (2026-03-16, PR #3)
     Agent Config tab            Edit topics/sources/prompts from UI                            ✅ Done (2026-03-17)
G    Deep OSINT (GPT Researcher)  deep_research.py, --deep flag, Haiku extraction, discover.py  ✅ Done (2026-03-17)
H    YouTube OSINT Collector      topic/event/trend tracking, curated channels, Haiku extraction  (planned)
I    Analyst Feedback Loop        per-run ratings, pipeline reads prior feedback                  (planned)
J    Historical Intelligence Charts  VaCR sparklines, severity heatmap, scenario drift           (planned)
F-5  Polish (parked)             audience tabs, interactive chat, scheduler
```
