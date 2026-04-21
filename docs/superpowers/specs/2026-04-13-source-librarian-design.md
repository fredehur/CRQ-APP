# Source Librarian — Design Spec

**Date:** 2026-04-13
**Status:** Approved for implementation plan
**Scope:** New per-run research tool that builds a curated reading list of authoritative sources per risk-register scenario, surfaced inside the Risk Register tab in the app.

---

## 1. Purpose

`source_librarian` is a per-run research tool that produces a curated reading list of up to 10 authoritative sources per scenario, for each risk register. Its only job:

> "Here are the reports to read so you can sanity-check these VaCR numbers yourself."

**Explicit non-goals:**
- No verdict calculation (no `affirms / challenges / insufficient`)
- No VaCR recalculation
- No persistent source library or database accumulation (the existing `sources.db` is for regional OSINT, not benchmark validation)
- No per-run figure aggregation (individual figures are captured on each source card, not combined into benchmarks)

It replaces the current `register_validator.py` approach for benchmark source discovery. The existing validator stays in place for anything else that depends on it.

---

## 2. Architecture

Seven-layer pipeline, one direction, no shared state between runs beyond what's committed to git.

```
┌─────────────────────────────────────────────────────────────┐
│ 1. INTENT YAML (committed to git)                           │
│    data/research_intents/<register>.yaml                    │
│    Bootstrapped ONCE via Haiku from register JSON;          │
│    human-edited; never auto-regenerated.                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. QUERY GEN — pure template fill, no LLM                   │
│    Per scenario, two query sets:                            │
│    - NEWS set (for Tavily): "{threat} {asset} attack {yr}"  │
│    - DOC  set (for Firecrawl): "{threat} {asset} report pdf"│
│    ~4 queries per engine per scenario                       │
│    Uses threat_terms[0], asset_terms[0], industry_terms[0]  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. DISCOVERY — differentiated queries, parallel execution   │
│    - Tavily /search  (topic=news, days=730)  ← NEWS set     │
│    - Firecrawl /search                        ← DOC set     │
│    Merge + dedupe by URL.                                   │
│    Graceful degrade:                                        │
│      tavily_failed   → continue with Firecrawl only         │
│      firecrawl_failed→ continue with Tavily only            │
│      both_failed     → scenario status="engines_down"       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. RANK — filter then score                                 │
│    STEP A: Drop all T4 candidates (unknown publishers)      │
│    STEP B: Score survivors                                  │
│      score = 0.6*authority_tier + 0.25*recency              │
│            + 0.15*query_match                               │
│      authority: T1=1.0, T2=0.7, T3=0.4                      │
│      recency:   exp decay, half-life 18 months              │
│      query_match: term hits in title+snippet, normalized    │
│    STEP C: Keep top min(10, n_survivors)                    │
│    Empty case → status="no_authoritative_coverage" with     │
│    diagnostics (candidates_discovered, top_rejected).       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. SCRAPE — scrape-once-cite-many                           │
│    URL-keyed content cache per run.                         │
│    Firecrawl /scrape each unique URL once.                  │
│    Graceful degrade:                                        │
│      scrape_failed → keep url+title, drop markdown+summary, │
│      mark entry scrape_status="failed"                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. SUMMARIZE — Haiku per (scenario × source) pair           │
│    Prompt: "For scenario [X], what does this source say?    │
│             Return 2 sentences + any USD/$ or % figures."   │
│    Same URL can be summarized multiple times across         │
│    scenarios — relevance differs.                           │
│    Graceful degrade:                                        │
│      rate_limited → 3x retry with backoff                   │
│      still failing → source kept with summary=null          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. OUTPUT + SERVE                                           │
│    output/research/<register>_<YYYY-MM-DD-HHMM>_<hash8>.json│
│    Stop hook validates schema before completion.            │
│    FastAPI:                                                 │
│      POST /api/research/run?register=X                      │
│      GET  /api/research/<register>/status/<run_id>          │
│      GET  /api/research/<register>/latest                   │
│    UI: Risk Register tab → scenario detail panel →          │
│        Reading list block (per selected scenario).          │
│    Client polls /status every 5s while running.             │
└─────────────────────────────────────────────────────────────┘
```

**Cost per run** (18 scenarios across both registers):

| Item | Volume | Cost |
|---|---|---|
| Tavily searches | 18 × 4 NEWS queries ≈ 72 | ~$0.60 |
| Firecrawl searches | 18 × 4 DOC queries ≈ 72 | ~$0.40 |
| Firecrawl scrapes | ~60-80 unique URLs | ~$0.40 |
| Haiku summaries | ~180 pairs | ~$0.36 |
| **Total** | | **~$1.75** |

Per single-register run: roughly half that (~$0.90).

---

## 3. Intent YAML Format

The intent yaml is the only control surface that matters. It lives in git. Edits are reviewed and committed.

**Per-register file: `data/research_intents/<register_id>.yaml`**

```yaml
register_id: wind_power_plant
register_name: AeroGrid Wind Power Plant
industry: renewable_energy
sub_industry: wind_power_generation
geography:
  primary: [europe, north_america]
  secondary: [apac]

scenarios:
  WP-001:
    name: "System intrusion into OT/SCADA"
    threat_terms: [system intrusion, OT compromise, SCADA breach, ICS intrusion]
    asset_terms: [wind turbine, SCADA, OT network, HMI, PLC]
    industry_terms: [wind farm, renewable energy, power generation, utility]
    time_focus_years: 3
    notes: |
      Focus on documented OT intrusions in wind/renewable, not generic IT
      breaches. Stuxnet-era sources are too old to be useful.

  WP-002:
    name: "Ransomware on OT/SCADA"
    threat_terms: [ransomware, wiper, extortion, LockBit, BlackCat]
    asset_terms: [wind turbine SCADA, OT network, engineering workstation]
    industry_terms: [renewable energy, wind power, utility, power generation]
    time_focus_years: 2
    notes: |
      Vestas 2021 and Nordex 2022 are canonical. Prefer cost-per-incident
      and recovery-time reporting.
  # ... WP-003 through WP-009

query_modifiers:
  news_set:
    - "{threat} {asset} attack {year}"
    - "{threat} incident {industry} {year}"
    - "{industry} {threat} 2024 2025 report"
    - "{threat} {asset} {industry}"
  doc_set:
    - "{threat} {asset} report pdf"
    - "{industry} {threat} assessment study"
    - "{threat} {asset} impact cost analysis"
    - "{industry} cyber threat landscape {year}"
```

**Template fill rules:**
- `{threat}` → `scenario.threat_terms[0]`
- `{asset}` → `scenario.asset_terms[0]`
- `{industry}` → `scenario.industry_terms[0]`
- `{year}` → derived from `time_focus_years` (e.g. 2 → "2024 2025")
- Remaining terms (index 1+) are there for the optional `--llm-queries` debug path, which cross-joins via LLM. Default path never uses them.

**Shared file: `data/research_intents/publishers.yaml`**

```yaml
tiers:
  T1:  # primary research & government
    - dragos.com
    - mandiant.com
    - cisa.gov
    - ibm.com/security
    - verizon.com/business/resources/reports
    - marsh.com
    - enisa.europa.eu
    - ncsc.gov.uk
    - sans.org
  T2:  # sector vendors & specialized firms
    - claroty.com
    - armis.com
    - nozominetworks.com
    - kaspersky.com/ics-cert
    - waterfall-security.com
  T3:  # general cyber press (recency boosts these)
    - bleepingcomputer.com
    - therecord.media
    - securityweek.com
    - darkreading.com
  # T4 is implicit: anything not listed is T4 and is filtered out at rank step
```

**Publisher matching:** prefix-based. `ibm.com/security` matches any URL whose host+path starts with that string. Plain domain entries (`dragos.com`) match any URL on that host.

**Validation:** a pydantic model in `intents.py` validates every load. A missing `threat_terms` or unknown field fails fast with a clear error. The stop hook also re-validates the snapshot's `intent_hash` field to catch stale snapshots.

**Bootstrap:** `python -m tools.source_librarian --bootstrap <register>` reads `data/registers/<register>.json`, feeds scenario names + descriptions + existing `search_tags` to Haiku, and writes an initial yaml. The user edits it and commits. Bootstrap never runs as part of `run_snapshot`.

---

## 4. Pipeline Code Layout

```
tools/
├── source_librarian/
│   ├── __init__.py      # public API: run_snapshot(register_id) -> Snapshot
│   ├── __main__.py      # CLI entry: python -m tools.source_librarian
│   ├── intents.py       # yaml load + pydantic models
│   ├── queries.py       # template fill for news_set / doc_set
│   ├── discovery.py     # Tavily + Firecrawl /search, dedupe, degrade
│   ├── ranker.py        # authority filter + scoring + top-10 selection
│   ├── scraper.py       # Firecrawl /scrape with URL-keyed cache
│   ├── summarizer.py    # Haiku per (scenario × source), figure extraction
│   ├── snapshot.py      # output JSON builder + schema validator
│   └── bootstrap.py     # Haiku-driven intent yaml generator (one-shot)

data/research_intents/
├── publishers.yaml
├── wind_power_plant.yaml
└── aerogrid_enterprise.yaml

output/research/
└── <register>_<YYYY-MM-DD-HHMM>_<hash8>.json
```

**Public API:**

```python
# tools/source_librarian/__init__.py
def run_snapshot(register_id: str, *, debug: bool = False) -> Snapshot: ...
def get_latest_snapshot(register_id: str) -> Snapshot | None: ...
def list_snapshots(register_id: str) -> list[Path]: ...
```

**Core types (pydantic, in `snapshot.py`):**

```python
class SourceEntry(BaseModel):
    url: str
    title: str
    publisher: str
    publisher_tier: Literal["T1", "T2", "T3"]
    published_date: str | None
    discovered_by: list[Literal["tavily", "firecrawl"]]
    score: float
    summary: str | None
    figures: list[str]
    scrape_status: Literal["ok", "failed", "skipped"]

class ScenarioResult(BaseModel):
    scenario_id: str
    scenario_name: str
    status: Literal["ok", "no_authoritative_coverage", "engines_down"]
    sources: list[SourceEntry]
    diagnostics: dict | None   # populated on non-ok status

class Snapshot(BaseModel):
    register_id: str
    run_id: str                # UUID
    intent_hash: str           # sha256 of intent yaml, first 8 chars in filename
    started_at: datetime
    completed_at: datetime | None
    tavily_status: Literal["ok", "failed", "disabled"]
    firecrawl_status: Literal["ok", "failed"]
    scenarios: list[ScenarioResult]
    debug: dict | None         # rejected_candidates when ?debug=1
```

**Execution flow (pseudocode):**

```python
def run_snapshot(register_id, debug=False):
    intent = load_intent(register_id)              # raises on schema fail
    publishers = load_publishers()
    query_plan = build_queries(intent)             # deterministic

    scrape_cache: dict[str, str] = {}
    engine_status = EngineStatus()

    # Discovery (parallel per scenario)
    candidates = {
        sid: discover(queries, engine_status)
        for sid, queries in query_plan.items()
    }

    # Rank (pure)
    selected = {
        sid: rank_and_select(cands, publishers)
        for sid, cands in candidates.items()
    }

    # Scrape unique URLs once
    unique_urls = {s.url for sources in selected.values() for s in sources}
    for url in unique_urls:
        scrape_cache[url] = scrape_with_retry(url)

    # Summarize per (scenario × source)
    for sid, sources in selected.items():
        for src in sources:
            md = scrape_cache.get(src.url)
            if md:
                src.summary, src.figures = summarize(
                    scenario=intent.scenarios[sid], markdown=md
                )

    snapshot = build_snapshot(intent, selected, engine_status, debug=debug)
    snapshot.validate()
    write_snapshot(snapshot)
    return snapshot
```

**Testability:** each layer takes its HTTP client via dependency injection. `ranker.py` is 100% pure functions. Only `run_snapshot()` knows about the whole pipeline.

---

## 5. FastAPI Integration

Thin wrapper. The server delegates all work to `run_snapshot()` and stores run state in an in-memory dict.

```python
# server.py (additions)
from tools.source_librarian import run_snapshot, get_latest_snapshot

_research_runs: dict[str, dict] = {}

@app.post("/api/research/run")
async def start_research(register: str, background: BackgroundTasks):
    run_id = str(uuid.uuid4())
    _research_runs[run_id] = {
        "status": "running",
        "register": register,
        "phase": "starting",
        "scenarios_complete": 0,
        "scenarios_total": 0,
    }
    background.add_task(_execute_research, run_id, register)
    return {"run_id": run_id}

def _execute_research(run_id: str, register: str):
    try:
        snapshot = run_snapshot(register)
        _research_runs[run_id] = {
            "status": "complete",
            "snapshot": snapshot.model_dump(),
        }
    except Exception as e:
        _research_runs[run_id] = {"status": "failed", "error": str(e)}

@app.get("/api/research/{register}/status/{run_id}")
async def research_status(register: str, run_id: str):
    return _research_runs.get(run_id, {"status": "unknown"})

@app.get("/api/research/{register}/latest")
async def research_latest(register: str):
    snap = get_latest_snapshot(register)
    return snap.model_dump() if snap else {"snapshot": None}
```

**Limitations acknowledged:**
- In-memory run state is lost on server restart (mid-flight runs appear as "unknown" after restart). Acceptable for a single-user tool.
- 5s polling is simple but not multi-user safe. If the app grows to multiple users, switch to Server-Sent Events.

---

## 6. UI Surface — Risk Register Tab, Scenario Detail Panel

The reading list lives inside the Risk Register tab, attached to the currently selected scenario.

```
┌─ Risk Register ────────────────────────────────────────────────────┐
│  [Register bar: AeroGrid Wind Power Plant ▾]                       │
│  ┌─── Scenario list ───┬──── Scenario detail (selected) ──────────┐│
│  │ WP-001 Intrusion    │  WP-002 — Ransomware on OT/SCADA         ││
│  │ WP-002 Ransomware ●│                                            ││
│  │ ...                 │  ┌─ Current VaCR ────────────────────┐   ││
│  │                     │  │ Financial:  $8.4M                  │   ││
│  │                     │  │ Probability: 0.18/yr               │   ││
│  │                     │  └────────────────────────────────────┘   ││
│  │                     │                                            ││
│  │                     │  ┌─ Reading list (for benchmarking) ──┐   ││
│  │                     │  │ 10 sources · est. 2h 45m           │   ││
│  │                     │  │ Last refreshed 2026-04-13 14:22    │   ││
│  │                     │  │                 [↻ Refresh list]   │   ││
│  │                     │  │                                    │   ││
│  │                     │  │  ① Dragos — 2024 OT YiR    T1·.92 │   ││
│  │                     │  │    "Wind operators saw 68% YoY     │   ││
│  │                     │  │     increase; recovery 14 days."   │   ││
│  │                     │  │    Figures: 68%, 14 days           │   ││
│  │                     │  │    [Open →]                        │   ││
│  │                     │  │  ... 9 more                        │   ││
│  │                     │  └────────────────────────────────────┘   ││
│  └─────────────────────┴───────────────────────────────────────────┘│
└────────────────────────────────────────────────────────────────────┘
```

**Per-source card fields:**

| Field | Source | Display |
|---|---|---|
| Rank number | ranker | Top-left circle |
| Publisher | snapshot | Bold, header |
| Title | snapshot | Header after publisher |
| Tier + score | snapshot | Right-aligned badge |
| Summary | summarizer | Italic, 2-3 lines |
| Figures | summarizer | Pill chips |
| Published date | snapshot | Footer |
| Discovered by | snapshot | Footer ("Tavily", "Firecrawl", or both) |
| Open source | constructed | Opens `src.url` in a new tab |
| Scenario notes | intents | Tooltip on scenario header (ⓘ icon) |

**Empty scenario state** (e.g. WP-008 defacement has no T1-T3 coverage): accordion closed by default, ⚠ badge and diagnostic text. Click to expand → shows top 3 rejected candidates with tier and score so the user can decide whether to widen the allowlist.

**Refresh UX:**
- Single **↻ Refresh list** button. Kicks off a full-register snapshot (all 9 scenarios).
- Button state: **Refreshing… 4/9** driven by 5s polling against `/status/<run_id>`.
- When complete, the UI re-renders from `/latest`.
- On failure, inline error with retry button.

**Frontend data flow (`static/app.js`):**

```javascript
// 1. User selects scenario → _selectScenario(id)
// 2. Detail panel renders VaCR block + scenario notes (existing)
// 3. NEW: call loadResearchForScenario(register_id, scenario_id)
//      → GET /api/research/<register>/latest
//      → filter snapshot.scenarios to the selected one
//      → render reading list block
// 4. If no snapshot: "No reading list yet — click Refresh to generate"
// 5. If scenario.status === "no_authoritative_coverage": render diagnostic
```

**What the UI does NOT do:**
- No inline yaml editing (edit the file in a terminal)
- No cross-register comparison
- No export-to-PDF (working document, not a deliverable)
- No "mark as read" state

---

## 7. Testing Strategy

**File layout:**
```
tests/source_librarian/
├── fixtures/
│   ├── tavily_response.json
│   ├── firecrawl_search.json
│   ├── firecrawl_scrape_dragos.md
│   ├── firecrawl_scrape_ibm.md
│   ├── haiku_summary_ok.json
│   └── intent_wind_minimal.yaml
├── test_intents.py
├── test_queries.py
├── test_ranker.py
├── test_discovery.py
├── test_scraper.py
├── test_summarizer.py
├── test_snapshot.py
└── test_integration.py
```

**Per-layer focus:**

| Layer | Test focus |
|---|---|
| intents | bad yaml → clear error; good yaml → parsed model |
| queries | `{threat}` expands; `{year}` respects `time_focus_years` |
| ranker | T4 filtered; score math; variable list length; empty-scenario diagnostic |
| discovery | Tavily+Firecrawl merge, URL dedupe, each degrade path |
| scraper | scrape-once cache; scrape_failed graceful degrade |
| summarizer | figure extraction regex; 2-sentence limit; Haiku retry |
| snapshot | pydantic schema; intent hash stability |
| integration | run_snapshot() against minimal intent → valid snapshot |

**Critical edge cases:**
1. Tavily 0 results, Firecrawl 10 → status=ok, discovered_by=["firecrawl"]
2. Tavily disabled (no API key) → tavily_status="disabled"
3. All candidates T4 → status="no_authoritative_coverage", diagnostics populated
4. Two scenarios cite same URL → scraped once, summarized twice
5. Haiku rate-limit on summary #4 → retries, then source kept with summary=null
6. Same intent, two runs same day → two snapshots (different HHMM)
7. Intent edited mid-day → new intent_hash in filename, both snapshots preserved

**What is NOT tested automatically:**
- Real API calls (cost + flakiness; manual QA with live credentials)
- FastAPI endpoints (thin wrappers; manual curl)
- Frontend rendering (visual QA via running app on :8001)

---

## 8. Stop Hook Validator

**File:** `.claude/hooks/validators/source-librarian-auditor.py`

Runs on every `source_librarian` agent stop. Enforces:

```
1. output/research/<register>_<date>_<hash>.json exists
2. JSON validates against Snapshot pydantic model
3. run_metadata.completed_at is not null
4. run_metadata.intent_hash matches current yaml hash
5. Every scenario in intents appears in snapshot.scenarios
6. For every scenario with status="ok":
     - at least 1 source
     - every source has url + title + publisher_tier
7. For every scenario with status="no_authoritative_coverage":
     - diagnostics.candidates_discovered > 0
8. tavily_status in {ok, failed, disabled}
9. firecrawl_status in {ok, failed}
10. If both engines failed: every scenario.status == "engines_down"
```

Hook exits non-zero with a specific failure list on any violation. The agent is forced into self-correction — it does not claim completion by exiting 0 on a malformed snapshot.

---

## 9. Graceful Degrade Matrix

| Failure | Behavior |
|---|---|
| Tavily API key missing | `tavily_status="disabled"`, Firecrawl runs alone |
| Tavily HTTP error | `tavily_status="failed"`, Firecrawl runs alone, logged |
| Firecrawl HTTP error on /search | `firecrawl_status="failed"`, Tavily runs alone, logged |
| Both engines fail | every scenario `status="engines_down"`, snapshot still written |
| Firecrawl /scrape fails on one URL | source kept with `scrape_status="failed"`, no summary |
| Haiku rate-limited | 3x retry with exponential backoff; then `summary=null` |
| Haiku API error | source kept with `summary=null`, `figures=[]` |
| Intent yaml malformed | fail fast at load with clear error, no snapshot written |
| Stop hook schema validation fails | agent self-correction loop, snapshot not accepted |

---

## 10. Out-of-Scope for v1

These are deliberately deferred:
- Authority learning from user feedback ("this source was useful/not")
- Per-user reading progress / bookmarks
- Export-to-markdown briefing document
- Cross-register shared reading list (when a source applies to scenarios in both registers, it's independently scored in each — no global dedupe)
- Semantic reranking via embedding similarity
- The `--llm-queries` debug path (scaffolded but not wired in v1)
- Multi-user concurrency safety for the FastAPI endpoints

Any of these are candidates for a v2 spec if v1 lands well.

---

## 11. Open Questions (none blocking implementation)

- Exact authority-tier weights may need tuning after first real run. Current `0.6/0.25/0.15` is a starting point.
- Publisher allowlist is seeded manually; may need quarterly review as new vendors emerge.
- Intent yaml bootstrap prompt for Haiku is not specified here — it's a one-shot prompt in `bootstrap.py` that the implementation plan will flesh out.

---

## 12. Acceptance Criteria

This spec is considered complete when:
- [ ] Both registers have `data/research_intents/<register>.yaml` committed
- [ ] `publishers.yaml` committed with T1-T3 tiers
- [ ] `tools/source_librarian/` package exists with all 9 modules
- [ ] `tests/source_librarian/` passes against mocked clients
- [ ] `python -m tools.source_librarian --register wind_power_plant` produces a valid snapshot
- [ ] `POST /api/research/run` + `GET /api/research/.../latest` endpoints respond correctly
- [ ] Risk Register tab renders a reading list for the selected scenario
- [ ] Stop hook validator catches malformed snapshots and forces correction
