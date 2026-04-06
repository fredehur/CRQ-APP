# Phase P — Python Orchestration Layer

**Date:** 2026-03-28
**Status:** Planned (not started)
**Goal:** Replace markdown-driven orchestration (run-crq.md) with deterministic Python. Intelligence stays in agents. Infrastructure moves to code.

---

## Problem Statement

The pipeline orchestration currently lives in `run-crq.md` — a markdown document that Opus reads and follows as instructions. This means:

- Orchestration correctness depends on Claude reading prose accurately every run
- Retry logic, fan-out, fan-in, and circuit breakers are described in text, not enforced in code
- The pipeline cannot be unit tested — only end-to-end tested
- Failures produce wrong output, not stack traces
- A human with Claude Code open is required to run the pipeline

**What we are NOT changing:**
- Agent prompts (gatekeeper, regional analyst, global builder, validator, RSM formatter)
- Stop hooks (jargon, source attribution, schema, arithmetic validators)
- File-as-state pattern (agents still read/write JSON files)
- The intelligence design (Admiralty, three pillars, scenario coupling, VaCR boundary)
- Mock/live OSINT mode toggle

---

## Target Architecture

```
pipeline/
├── orchestrator.py          # Main entry point — asyncio pipeline
├── phases/
│   ├── phase0_init.py       # Validate inputs, load footprint, detect OSINT mode
│   ├── phase1_regional.py   # asyncio.gather() fan-out × 5 regions
│   ├── phase2_velocity.py   # trend_analyzer.py wrapper
│   ├── phase3_diff.py       # report_differ.py wrapper
│   ├── phase4_global.py     # global-builder-agent → validator loop
│   ├── phase5_export.py     # dashboard + PDF + PPTX
│   └── phase6_finalize.py   # manifest + archive + history
├── agents/
│   ├── base.py              # Shared: call Claude API, retry, invoke stop hook
│   ├── gatekeeper.py        # accept(signals) -> GatekeeperDecision
│   ├── regional_analyst.py  # accept(decision, signals) -> RegionalBrief
│   ├── global_builder.py    # accept(briefs, trend) -> GlobalReport
│   ├── global_validator.py  # accept(report) -> ValidationResult
│   └── rsm_formatter.py     # accept(signals) -> RSMBrief
└── models/
    ├── signals.py           # GeoSignals, CyberSignals, YoutubeSignals
    ├── decisions.py         # GatekeeperDecision, ValidationResult
    ├── report.py            # RegionalBrief, GlobalReport, RSMBrief
    └── manifest.py          # RunManifest, RegionStatus
```

---

## Implementation Tasks

### Task 1 — Pydantic models (no behaviour change)

Create `pipeline/models/` with typed Pydantic models for every JSON contract:

- `GeoSignals`, `CyberSignals`, `YoutubeSignals` — from existing JSON schemas
- `GatekeeperDecision` — from `gatekeeper_decision.json`
- `RegionData` — from `data.json`
- `GlobalReport` — from `global_report.json`
- `RunManifest` — from `run_manifest.json`

**Test:** Load every existing mock fixture through its Pydantic model. All must parse without error.
**Commit:** `feat(P-1): Pydantic models for all data contracts`

---

### Task 2 — Agent base layer

Create `pipeline/agents/base.py`:

```python
async def call_agent(
    prompt: str,
    model: str,
    stop_hook: Callable[[str], HookResult] | None = None,
    max_retries: int = 3,
) -> str:
    for attempt in range(max_retries):
        response = await claude(prompt, model=model)
        if stop_hook is None:
            return response
        result = stop_hook(response)
        if result.passed:
            return response
        if attempt == max_retries - 1:
            # Circuit breaker — force accept with warning logged
            audit_log(f"CIRCUIT_BREAKER: {result.violations}")
            return response
        prompt = inject_violations(prompt, result.violations)
    raise RuntimeError("unreachable")
```

Stop hooks become Python functions (wrapping existing `.py` auditors via subprocess or direct import).

**Test:** Mock Claude API, verify retry logic fires on hook failure, circuit breaker at attempt 3.
**Commit:** `feat(P-2): Agent base layer with retry + circuit breaker`

---

### Task 3 — Gatekeeper agent

Create `pipeline/agents/gatekeeper.py`:

```python
async def run_gatekeeper(region: str, signals_path: Path) -> GatekeeperDecision:
    signals = load_signals(signals_path)
    prompt = build_gatekeeper_prompt(signals)
    response = await call_agent(prompt, model="claude-haiku-4-5-20251001")
    decision = parse_gatekeeper_decision(response)
    write_gatekeeper_decision(region, decision)
    return decision
```

Prompt content = extracted verbatim from `gatekeeper-agent.md` (no change to intelligence).

**Test:** Mock Claude response, assert `GatekeeperDecision` parses correctly, assert file written.
**Commit:** `feat(P-3): Gatekeeper agent as typed Python function`

---

### Task 4 — Regional analyst agent

Create `pipeline/agents/regional_analyst.py`:

```python
async def run_regional_analyst(
    region: str,
    decision: GatekeeperDecision,
    signals_path: Path,
) -> RegionalBrief:
    ...
```

Stop hook: invoke `jargon-auditor.py` + `source-attribution-auditor.py` as Python functions.

**Test:** Mock Claude response with jargon, assert retry fires, assert clean response accepted.
**Commit:** `feat(P-4): Regional analyst agent with stop hooks`

---

### Task 5 — Phase 1 fan-out

Create `pipeline/phases/phase1_regional.py`:

```python
async def run_phase1(regions: list[str], osint_mode: str) -> dict[str, RegionResult]:
    tasks = [run_region_pipeline(r, osint_mode) for r in regions]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {r: res for r, res in zip(regions, results)}
```

Each `run_region_pipeline` = collect signals → gatekeeper → [if ESCALATE] analyst.

**Test:** All 5 regions run in parallel, verify independent failure doesn't block others.
**Commit:** `feat(P-5): Phase 1 asyncio fan-out — 5 regions parallel`

---

### Task 6 — Global builder + validator loop

Create `pipeline/phases/phase4_global.py`:

```python
async def run_phase4() -> GlobalReport:
    report = await run_global_builder()
    for _ in range(2):
        result = await run_global_validator(report)
        if result.status == "APPROVED":
            return report
        report = await run_global_builder(violations=result.failures)
    audit_log("CIRCUIT_BREAKER: global validator — force approve")
    return report
```

**Test:** Validator returns REWRITE once, builder called twice, second response accepted.
**Commit:** `feat(P-6): Global builder + validator retry loop`

---

### Task 7 — Main orchestrator + POST /api/run

Create `pipeline/orchestrator.py`:

```python
async def run_pipeline(config: PipelineConfig) -> RunResult:
    await run_phase0(config)
    await run_phase1(REGIONS, config.osint_mode)
    await run_phase2()
    await run_phase3()
    await run_phase4()
    await run_phase5()
    await run_phase6()
```

Add `POST /api/run` to `server.py`:

```python
@app.post("/api/run")
async def trigger_run(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_pipeline, PipelineConfig())
    return {"status": "started"}
```

**Test:** POST /api/run returns 200, pipeline state transitions from idle → running → complete.
**Commit:** `feat(P-7): Main orchestrator + POST /api/run endpoint`

---

### Task 8 — Retire run-crq.md orchestration

- Keep `run-crq.md` as a thin wrapper that calls `POST /api/run` and tails SSE
- Remove all orchestration prose from it (phases, retry logic, circuit breakers)
- Keep `.claude/agents/` prompts untouched — they become the prompt content in Python agents

**Commit:** `feat(P-8): retire markdown orchestration — run-crq.md delegates to API`

---

## What stays the same

| Component | Status |
|-----------|--------|
| Agent prompts (gatekeeper, analyst, builder, validator, RSM) | Unchanged — extracted into Python |
| Stop hook validators (jargon, schema, arithmetic) | Unchanged — invoked as Python functions |
| File-as-state (agents read/write JSON files) | Unchanged |
| OSINT collectors (geo, cyber, youtube, research) | Unchanged |
| Exporters (PDF, PPTX, dashboard) | Unchanged |
| All existing tests | Unchanged + new unit tests added |

---

## Effort Estimate

| Task | Effort |
|------|--------|
| P-1: Pydantic models | ~2h |
| P-2: Agent base layer | ~2h |
| P-3: Gatekeeper | ~1h |
| P-4: Regional analyst | ~2h |
| P-5: Phase 1 fan-out | ~2h |
| P-6: Global builder + validator | ~2h |
| P-7: Orchestrator + API | ~3h |
| P-8: Retire run-crq.md | ~1h |
| **Total** | **~15h (2 focused days)** |

---

## When to do this

**Not yet.** Do Phase I (Analyst Feedback Loop) and Phase J (Historical Intelligence Charts) first on the current prototype.

**Trigger conditions for starting Phase P:**
1. First time a pipeline run fails in a way that's hard to diagnose (wrong output, missing region, skipped phase)
2. You're about to show this to a real client or external stakeholder
3. You want to schedule pipeline runs via cron (requires `POST /api/run` to exist)
4. The orchestration prompt in `run-crq.md` exceeds Opus's reliable context window

The current system is good enough to keep building product on. Phase P is an infrastructure investment, not a feature. Do it when the prototype ceiling is actually limiting you.
