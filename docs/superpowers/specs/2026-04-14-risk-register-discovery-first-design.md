# Risk Register UI Redesign + Self-Healing Source Discovery

**Date:** 2026-04-14
**Status:** Draft — pending user review
**Supersedes:** original Source Librarian reading list block (shipped 2026-04-14, commit `2173c2d`)
**Related:** `docs/superpowers/plans/2026-04-14-source-librarian-implementation.md` (the pipeline this UI surfaces)

---

## 1. Why

Source Librarian shipped with a reading list block at position 7/7 in the scenario detail pane of the Risk Register tab. Evaluation against the live UI (2026-04-14) found that discovery — the centerpiece of the feature — is structurally buried:

- Reading list is the last section of the scenario detail; on a 900px viewport it sits below the fold
- The left-hand scenario list has no column signaling whether a scenario has coverage
- The REFRESH button lives inside each scenario card but the operation runs the whole register
- The empty state tells the user nothing about what the feature does or how long it takes
- Errors use `alert()` modals; progress during runs shows only a meaningless tick counter
- When a scenario lands in `no_authoritative_coverage`, the analyst's only recourse is to manually edit an intent yaml

This spec redesigns the Risk Register to put discovery first, wires stage-aware progress into the refresh flow, and adds a self-healing auto-tune loop that proposes intent yaml modifications when coverage fails — all actions logged to a long-term JSONL memory.

**Non-goals.** This spec does not change the Source Librarian pipeline itself (`tools/source_librarian/__init__.py::run_snapshot`), does not redesign any other tab (Overview, Reports, Source Library, Pipeline, Run Log), and does not touch the VaCR numbers or their computation.

---

## 2. Design

### 2.1 Layout — discovery-first

**Register header bar** (replaces today's minimal title row):
- Register name (14px, Plex Sans)
- Subtitle: `{N} scenarios · {snapshot_status}` where status is "no evidence snapshot yet" / "last run 2h ago" / "running — 00:23"
- Snapshot rollup (when a snapshot exists): `■ {ok} ok · ■ {no_cov} no-coverage · ■ {engines_down} engines-down`
- **Stale-intent badge** (conditional): yellow `⚠ INTENT CHANGED — RERUN` pill shown when `snapshot.intent_hash != current_yaml_hash`
- Primary button: `↻ REFRESH ALL SOURCES` (or `↻ GATHER EVIDENCE` in the empty state). Full blue `#1f6feb` with `box-shadow: 0 0 0 1px #58a6ff44` in empty state for extra prominence.

**Scenario list (left column)** — new schema:

| col | # | SCENARIO | SOURCES | IMPACT | PROB |
|---|---|---|---|---|---|
| width | 22 | 1fr | 92 | 60 | 40 |

The SOURCES column renders:
- Up to 3 tier badges (`T1 T1 T2`) — mapped from the scenario's top 3 sources by composite score (same ordering as the Evidence & Sources list). If the scenario has more than 3 sources only the top 3 tiers are shown in the list column; the full list still renders in the detail pane.
- `⚠ NO COV` pill (amber) if `status == "no_authoritative_coverage"`
- `—` dim dash if no snapshot exists for the scenario yet

**Scenario detail (right column)** — new stack order:

1. **Scenario header** — name + ID + description (unchanged structure)
2. **Evidence & Sources** *(NEW — section 1)* — proper 13px section heading, not 9px caps. Tier legend inline on the right of the header. Row format per source:
   - `{n}. {publisher}` as `#58a6ff` link + `— {title}` in body color + right-aligned `T{1|2|3} · {score}` tier badge
   - Summary (italic, 11px, `#8b949e`) indented under the row
   - Figure chips (`$8.2M`, `47 days`, etc.) wrapped below summary
   - Metadata line: `{published_date} · {discovered_by}` dim
3. **Analyst baseline** *(demoted)* — still shows VaCR and probability inputs, but with **cross-check footers** referencing sources from the Evidence block above: `"Cross-checked against Dragos $8.2M median — company figure 36% below sector average."` When no snapshot exists, the footer reads `"No cross-check — run evidence gathering"`.
4. Validation zone and analyst baseline editor remain in their current slots, below the three above.

### 2.2 Refresh flow — stage-aware progress

**Orchestrator change** — `tools/source_librarian/__init__.py::run_snapshot`:
```python
def run_snapshot(
    register_id: str,
    *,
    on_progress: Callable[[dict], None] | None = None,
    scenario_id: str | None = None,
    ...
) -> Snapshot:
```

- `on_progress` is called at each stage transition AND each scenario completion. The callback receives a dict: `{"stage": "discovery"|"scraping"|"summarizing", "scenario_id": sid, "status": "running"|"done", "counts": {"discovery": {"done": N, "total": M}, ...}}`. The `counts` semantics: `done` is the number of scenarios that have completed that stage; `total` is the number of scenarios the run is processing (9 for a register-wide run, 1 for a per-scenario rerun). Callback is optional; tests and CLI pass `None`.
- `scenario_id` when set restricts the pipeline to one scenario AND **skips the final `write_snapshot` call** — the function returns a `Snapshot` object with just that scenario filled in, and the caller is responsible for merging + writing. Used for per-scenario reruns (see 2.3). Full-register runs still write normally.

**Server change** — `server.py`:
- `_research_runs[run_id]` gains `progress: dict` and `lock: threading.Lock`. The BackgroundTask closure passes `on_progress=_make_progress_writer(run_id)` which acquires the lock, deep-updates the progress dict, releases.
- `GET /api/research/{register}/status/{run_id}` returns `{"status": ..., "progress": {...}, "snapshot": ... }`. Progress dict is deep-copied under lock before return.
- Poll cadence: client polls at **2 seconds** (down from 5s) because there's now real movement to render.

**Client change** — `static/app.js`:
- `refreshReadingList(registerId)` parses `stateResp.progress` and updates three things:
  1. Top progress bar in the register header (discovery/scrape/summarize counts + elapsed)
  2. Per-row status chip in the scenario list (`✓ updated Ns ago` / `▸ scraping X/Y…` / `⧗ queued`, with `opacity:0.55` for queued)
  3. Skeleton loaders inside the currently selected scenario's Evidence block for sources still in-flight
- Cancel button: `POST /api/research/cancel?run_id=X` — sets a threading Event the orchestrator checks between stages. Not a hard kill; cooperative.

### 2.3 Per-scenario rerun

**Why** — after editing an intent yaml for one scenario, or after auto-tune applies a diff, the user wants to rerun just that scenario without paying the 60-90s full-register cost.

**Endpoint** — `POST /api/research/run?register=X&scenario=Y` — same handler as the register-wide run, just passes `scenario_id` through.

**Merge logic** (load-bearing — own module `tools/source_librarian/snapshot_merge.py`, own tests):
1. Load latest snapshot for the register via `list_snapshot_paths(register_id)` → `read_snapshot(path)`. If none exists, error — per-scenario rerun requires a base snapshot.
2. Run `run_snapshot(register_id, scenario_id=Y, on_progress=cb)` — pipeline runs discovery/scrape/summarize for one scenario only, returns a `Snapshot` with just that scenario filled in. **Does not write to disk** (see 2.2).
3. Construct merged snapshot: copy original, replace the entry with `scenario_id == Y`, bump `started_at`/`completed_at`. The filename's short hash (the `_<hash8>.json` suffix, recomputed inside `snapshot_filename()`) changes because the content changed; **`intent_hash` stays the same** because the intent yaml didn't change.
4. Write new snapshot file via `write_snapshot()` — preserves the previous file on disk as history.

**UI** — small `↻ rerun this one` link in the Evidence & Sources header, right of `"3 authoritative · 2h ago"`. ~6 lines of JS.

### 2.4 Empty state

Shown when `GET /api/research/{register}/latest` returns `{"snapshot": null}`.

**Register header**: title + `"9 scenarios · no evidence snapshot yet"` subtitle + prominent `↻ GATHER EVIDENCE` CTA.

**Scenario detail**: onboarding card (dashed border) replacing the Evidence & Sources section:
- Title: "No evidence gathered yet"
- Body: *"Source Librarian searches authoritative publishers — **Dragos, CISA, ENISA, IBM X-Force** and others in your allowlist — and extracts figures that let you cross-check VaCR and probability against real incident data."*
- Pipeline explanation (on the `border-left` block): "1. Tavily + Firecrawl search all 9 scenarios. 2. Ranker picks top 3 T1/T2 sources per scenario. 3. Haiku summarizes each source and extracts figures. Typical run: ~60-90 seconds."
- Button: `↻ GATHER EVIDENCE FOR ALL {N} SCENARIOS` (same action as header button)
- Intent yaml path shown in dim mono: `data/research_intents/{register_id}.yaml`
- **No cost disclosure.**

Analyst baseline card still renders below, with "No cross-check — run evidence gathering" as each number's footer.

### 2.5 Degraded states

Both states replace the Evidence & Sources section in-slot. No `alert()` modals anywhere in the refresh flow.

**`no_authoritative_coverage`** — amber panel (`border-left:3px solid #d29922`, bg `#1a1205`):
- Title: `⚠ No authoritative coverage` + right-aligned `{candidates_discovered} candidates filtered`
- One-paragraph why: *"Tavily and Firecrawl found sources, but none from the T1/T2 publisher allowlist. Common causes: niche scenario, newly-defined threat, or allowlist too restrictive."*
- `REJECTED CANDIDATES (top 3)` list from `diagnostics.top_rejected`: title, publisher, rejection reason
- Action buttons:
  - Primary: `⚡ AUTO-TUNE` (blue, invokes section 2.6)
  - Secondary: `↻ RERUN THIS SCENARIO` (ghost blue)
  - Tertiary: `📋 COPY INTENT PATH` (dim, copies `data/research_intents/{register_id}.yaml` to clipboard)

**`engines_down`** — red panel (`border-left:3px solid #f85149`, bg `#1a0808`):
- Title: `⚠ Discovery engines unavailable` + `last run · {HH:MM}`
- One-paragraph why: *"Neither Tavily nor Firecrawl returned results on the last run. The full register fell through to `engines_down`."*
- Per-engine status rows: `TAVILY | {error_message} | FAILED` badge
- Action buttons: `↻ RETRY NOW`, `VIEW LOGS`

### 2.6 Auto-tune loop — self-healing discovery

**Concept.** When a scenario is in `no_authoritative_coverage`, the user clicks `⚡ AUTO-TUNE`. A loop runs server-side:

```
  detect no-coverage
    → tuner agent analyzes rejected candidates + current intent yaml
    → tuner proposes diff (new threat/asset/industry terms, with reasoning)
    → validator agent gates the diff (schema-valid, on-topic, no hallucinated vocabulary)
    → apply diff to in-memory intent copy
    → rerun discovery + rank for just this scenario
    → verdict: found T1/T2? done. none? loop. budget exhausted? stop.
```

**Budgets (raised per user request):**
- **Iteration count is the primary budget: max 5 iterations.** Each iteration = one tuner call + one validator call + one discovery rerun.
- **Cost is a soft secondary budget: ~$0.50 USD estimated per session.** Cost tracking is approximate — we count Haiku token usage from the SDK response and add a fixed per-iteration estimate for Tavily/Firecrawl calls (we don't have exact billing integration for those). The cost budget acts as a safety net against pathological cases, not a precise meter.
- **Cancellable from UI at any point** via a cooperative `threading.Event` checked between iterations.

**Agents** — two new sub-agents in `.claude/agents/`:

1. **`intent-tuner-agent`** (Haiku)
   - **Input**: current intent yaml for the scenario, the rejected candidates list with reasons, the scenario description, a list of what's been tried in prior iterations this session
   - **Output**: a JSON diff `{add_threat_terms: [...], remove_threat_terms: [...], add_asset_terms: [...], remove_asset_terms: [...], add_industry_terms: [...], remove_industry_terms: [...]}` + a `reasoning` field explaining why
   - **Scope limit (v1):** the diff can ONLY modify the three term lists. It cannot change `time_focus_years`, `query_modifiers`, scenario name, or any other field of the intent yaml. This keeps the tuner's action surface narrow and auditable.
   - **Stop hook**: validates the output is parseable JSON matching the diff schema and that only the six allowed keys appear
   - **Model**: `claude-haiku-4-5-20251001`

2. **`intent-tuner-validator-agent`** (Haiku)
   - **Input**: the proposed diff, the rejected candidates, the scenario description
   - **Output**: `{"verdict": "approved"|"rejected", "reason": "..."}`
   - Rejection criteria: proposed terms are off-topic (checked against scenario description), hallucinated (terms the user hasn't used and that have no clear grounding), duplicative of already-tried terms, or make the query more narrow when the issue was already narrow
   - **Stop hook**: validates verdict is one of the two allowed values
   - **Model**: `claude-haiku-4-5-20251001`

**In-memory diff — the intent yaml on disk is never mutated.** Only the JSONL tuning log records what was tried. If a rerun succeeds, the user can manually promote the winning diff into the canonical yaml.

**Orchestration** — new module `tools/source_librarian/tuner.py`:

```python
def run_autotune(
    register_id: str,
    scenario_id: str,
    *,
    max_iterations: int = 5,
    max_cost_usd: float = 0.50,
    cancel_event: threading.Event | None = None,
    on_progress: Callable[[dict], None] | None = None,
) -> AutoTuneResult:
    """Self-healing discovery loop. Returns on success, budget exhaustion, or cancellation."""
```

Returns an `AutoTuneResult` with: `outcome ∈ {found, exhausted, cancelled}`, `iterations_used`, `cost_usd`, `winning_diff`, `winning_sources`, `log_entries`.

**Endpoint** — `POST /api/research/autotune?register=X&scenario=Y`:
- Kicks off `run_autotune` in BackgroundTask
- Reuses `_research_runs[run_id]` state pattern from section 2.2
- Status endpoint returns the same progress shape plus an `autotune: {iteration, log, cost_usd, budget_remaining}` block

**Client UI** — replaces the no-coverage panel in-place with a live feed:
- Title: `⚡ Auto-tuning intent` + `iteration {N} of 5 · {elapsed}`
- Mono-font timestamped log, one line per event:
  - `[00:02] ▸ Tuner: "scenario name too generic — add 'config leak', 'OT credential exposure'"`
  - `[00:08] ▸ Applied diff · rerunning discovery`
  - `[00:19] ⚠ Still no T1/T2 (4 candidates, 0 T1/T2). Best rejection: ics-cert.us — wrong industry tag`
- Footer: `budget: {N} iter left · ~${cost_usd} spent` + `✕ CANCEL` button

On success: panel transitions to the regular Evidence & Sources populated state showing the sources the tuner found, plus a small "auto-tuned" badge next to the section title.

On exhaustion: panel reverts to no-coverage state with an added line `"Auto-tune ran 5 iterations, none produced T1/T2 sources. See tuning log for history."`

### 2.7 Long-term memory — tuning log

**Location**: `data/research_intents/tuning_log/{register_id}.jsonl`

**Shape** — one line per iteration event (append-only, never rewritten):

```jsonl
{"ts":"2026-04-14T17:34:08Z","register_id":"wind_power_plant","scenario_id":"WP-003","run_id":"autotune-abc123","iteration":2,"event":"proposed","diff":{"add_threat_terms":["config leak","OT credential exposure"],"remove_threat_terms":[],"add_asset_terms":[],"add_industry_terms":[]},"reasoning":"scenario name 'accidental disclosure' too generic for publisher vocabulary","validator_verdict":"approved","cost_usd":0.012}
{"ts":"2026-04-14T17:34:19Z","register_id":"wind_power_plant","scenario_id":"WP-003","run_id":"autotune-abc123","iteration":2,"event":"rerun_result","candidates_discovered":4,"t1_t2_count":0,"best_rejection":{"url":"https://ics-cert.us/...","reason":"wrong industry tag"},"cost_usd":0.031}
{"ts":"2026-04-14T17:34:45Z","register_id":"wind_power_plant","scenario_id":"WP-003","run_id":"autotune-abc123","iteration":3,"event":"succeeded","winning_diff":{...},"sources_found":[{"publisher":"ICS-CERT","tier":"T1","url":"..."}],"total_cost_usd":0.18}
```

**Writer** — new module `tools/source_librarian/tuning_log.py`:

```python
def append_event(register_id: str, event: dict) -> None: ...
def read_log(register_id: str) -> list[dict]: ...  # used only by tests in v1
```

- Directory is created on first write
- Writes are append-only using `open(mode='a')` — no locking needed for single-writer append
- Not surfaced in UI in v1 (deferred — see section 4)

### 2.8 Stale-intent indicator

**When shown**: if `load_intent(register_id).current_hash != latest_snapshot.intent_hash`.

**Where**: small amber pill in the register header, right of the snapshot rollup: `⚠ INTENT CHANGED — RERUN`. **Informational only, not clickable** — the REFRESH button is already in the same header row and is the action. The badge just signals *why* you'd want to click it.

**Implementation**: a new helper `intent_hash_current(register_id) -> str` in `tools/source_librarian/intents.py` (reuses the existing `intent_hash()` function on the raw yaml). The `/api/research/{register}/latest` endpoint returns both `snapshot.intent_hash` and `current_intent_hash` — client compares.

---

## 3. Files touched

### Modified
- `tools/source_librarian/__init__.py` — add `on_progress` and `scenario_id` params to `run_snapshot`; wire progress callbacks at stage transitions and scenario completions
- `tools/source_librarian/intents.py` — add `intent_hash_current(register_id)` helper (thin wrapper)
- `server.py` — extend `_research_runs` with progress + lock; new endpoints `/api/research/autotune`, `/api/research/cancel`, per-scenario variant of `/run`; `/latest` returns `current_intent_hash`
- `static/app.js` — rewrite of scenario list row rendering (new sources column), rewrite of `_renderScenarioDetail` (discovery-first stack order), new progress rendering, new auto-tune live feed rendering, stale badge
- `tests/source_librarian/` — new test files listed below

### New
- `tools/source_librarian/tuner.py` — `run_autotune`, `AutoTuneResult` dataclass, loop state machine
- `tools/source_librarian/tuning_log.py` — JSONL append writer + reader
- `tools/source_librarian/snapshot_merge.py` — per-scenario rerun merge logic (isolated because it's load-bearing and deserves its own tests)
- `.claude/agents/intent-tuner-agent.md` — tuner sub-agent definition
- `.claude/agents/intent-tuner-validator-agent.md` — validator sub-agent definition
- `.claude/hooks/validators/intent-tuner-output.py` — stop hook validating both the tuner diff JSON schema AND the validator verdict JSON schema (single file, two modes based on `INTENT_TUNER_ROLE` env var)
- `tests/source_librarian/test_progress_callbacks.py` — progress callback wiring
- `tests/source_librarian/test_per_scenario_rerun.py` — merge logic including intent_hash preservation
- `tests/source_librarian/test_tuner.py` — loop termination (found, exhausted, cancelled), budget enforcement, in-memory diff isolation (disk yaml unchanged)
- `tests/source_librarian/test_tuning_log.py` — append-only, schema, read-back roundtrip

### Deleted
None.

---

## 4. Explicitly deferred to v2

- **Auto-tune on-by-default** / `auto_tune: true` flag in intent yaml for unattended runs
- **"Auto-tune all no-coverage"** register-level multi-select action
- **Snapshot history dropdown** in the register header (the files already exist on disk at `output/research/*.json`, just not surfaced)
- **Tuning history browser** — searchable UI over the JSONL log, pattern mining ("these term combinations always find Dragos")
- **Bootstrap prompt feedback** — feeding tuning learnings back into `tools/source_librarian/bootstrap.py` so new registers inherit what worked elsewhere
- **In-app intent yaml editor** — the copy-path button is the v1 ceiling; no modal textarea editor
- **Promoting winning diffs to canonical yaml** — user can manually edit after seeing the winning diff in the JSONL; no one-click "save to yaml"

---

## 5. Success criteria

A run is successful if:

1. **Layout** — on a 1440×900 viewport, the Evidence & Sources block is visible above the fold in the scenario detail pane (no scroll needed to find it)
2. **Discovery at-a-glance** — scanning the scenario list, a user can see which scenarios have T1 coverage, which have no coverage, and which haven't been run, without clicking each one
3. **Refresh feels alive** — during a register-wide run, the user sees real per-scenario progress update at least every 2 seconds (not a silent spinner)
4. **Cancellation works** — clicking `✕ CANCEL` during a run stops the loop within 5 seconds and leaves the snapshot file untouched
5. **Per-scenario rerun preserves history** — rerunning WP-001 writes a new snapshot file without touching the existing file on disk, and the merged snapshot has 9 scenarios, not 1
6. **Auto-tune terminates** — for any input, `run_autotune` returns within `max_iterations` iterations, even under adversarial inputs (tuner returning nonsense, validator always rejecting, zero coverage genuinely available). The cost budget acts as a secondary hard stop in case iteration counting is wrong.
7. **Tuning log is append-only** — running auto-tune 10 times produces 10 new sessions in the JSONL file; no existing lines are modified
8. **Stale indicator fires correctly** — editing an intent yaml and reloading the page shows the `⚠ INTENT CHANGED — RERUN` badge; rerunning the register clears it
9. **Stop hooks pass** — tuner and validator sub-agents both have stop hooks that block malformed output
10. **No `alert()` anywhere** — all error paths in the refresh flow render inline panels

---

## 6. Open questions

None remaining at time of writing. All scope cuts have been made:
- Auto-tune scope: **B (live iteration feed)**
- Per-scenario rerun: **included, Option B from brainstorm**
- Stale indicator: **included**
- Manual edit-yaml button: **copy path only, no in-app editor**
- Snapshot history UI: **deferred to v2**
- Tuning knowledge base: **JSONL log persistent forever, no browser UI in v1**

---

## 7. Estimated build size

**~2-3 days** under the CRQ team protocol (Opus orchestrates, Sonnet builds, Sonnet validates, Haiku for tuner/validator). Split across 3 commits:

1. Progress callbacks + stage-aware refresh wiring + per-scenario rerun + merge logic + stale indicator
2. Discovery-first layout rewrite in `app.js` (scenario list sources column, scenario detail stack reorder, cross-check footers, empty/degraded panels)
3. Auto-tune loop (agents, orchestrator, endpoint, live feed UI, JSONL log)
