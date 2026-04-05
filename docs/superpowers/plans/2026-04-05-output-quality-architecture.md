# Implementation Plan — Output Quality Architecture
**Date:** 2026-04-05
**Spec:** `docs/superpowers/specs/2026-04-05-output-quality-architecture.md`
**Status:** Ready to build — execute AFTER master build plan ships
**Depends on:** `2026-04-05-master-build-plan.md` complete

---

## Team Structure

- **Orchestrator: Opus** — coordinate, enforce boundaries, validate. Never writes code.
- **Builder A: Sonnet** — Phase 1 (signal_ids + collection_quality.json)
- **Builder B: Sonnet** — Phase 2 (claims.json + two-step analyst prompt)
- **Builder C: Sonnet** — Phase 3 (grounding-validator.py)
- **Builder D: Sonnet** — Phase 4 (collection quality gate — parallel to B/C)
- **Validator: Sonnet** — cross-check all changes against spec done criteria

Execution order: A → B + D (parallel) → C → Validator

---

## Phase 1 — Signal IDs in Signal Files
**Owner:** Builder A | **Prerequisite for:** all other phases

### Task 1-1: Add signal_id generation to research_collector.py

**File:** `tools/research_collector.py`

At the synthesis step where `lead_indicators` are extracted from Tavily results, assign each indicator a `signal_id`:

```python
def _generate_signal_id(region: str, pillar: str, sequence: int) -> str:
    return f"{region.lower()}-{pillar.lower()}-{sequence:03d}"
```

Apply to every `lead_indicator` dict at extraction time. Also ensure `source_url` is written at the indicator level (not just the file-level `sources` array). Each indicator should have:
- `signal_id` — generated sequentially
- `source_url` — the URL of the Tavily result that produced this indicator (empty string `""` if unavailable, never omitted)
- `source_name` — domain-derived name (already partially implemented)

**Verification:** Run `uv run python tools/research_collector.py --region APAC --mock` and confirm `geo_signals.json` lead_indicators each have `signal_id` and `source_url` fields.

### Task 1-2: Add signal_id generation to mock collectors

**Files:** `tools/geo_collector.py`, `tools/cyber_collector.py`

These run in mock mode (`OSINT_LIVE=false`). Apply the same `_generate_signal_id()` function to fixture-based lead_indicators. Import or copy the function.

The grounding validator will skip signal_id resolution (check 3) when `OSINT_LIVE=false` — but signal_ids must still be present for the analyst to cite. Without them, the analyst has nothing to reference in claims.json.

**Verification:** Confirm mock signal files have `signal_id` on each indicator after a mock run.

### Task 1-3: Write collection_quality.json after collection

**File:** `tools/research_collector.py` (or new `tools/collection_gate.py` — builder's choice)

After signal files are written, run quality check and write `output/regional/{region}/collection_quality.json`:

```python
def check_collection_quality(region: str) -> dict:
    geo = load_json(f"output/regional/{region}/geo_signals.json")
    cyber = load_json(f"output/regional/{region}/cyber_signals.json")

    geo_grounded = sum(1 for i in geo.get("lead_indicators", []) if i.get("source_url"))
    cyber_grounded = sum(1 for i in cyber.get("lead_indicators", []) if i.get("source_url"))

    thin = geo_grounded < 3 or cyber_grounded < 3
    result = {
        "region": region.upper(),
        "thin_collection": thin,
        "geo_grounded_count": geo_grounded,
        "cyber_grounded_count": cyber_grounded,
        "threshold": 3
    }
    write_json(f"output/regional/{region}/collection_quality.json", result)
    return result
```

### Task 1-4: Wire collection gate into run-crq.md and server.py

**Files:** `.claude/commands/run-crq.md`, `server.py`

Add Phase 1.5 between collection and gatekeeper:
1. Run collection quality check → writes `collection_quality.json`
2. Gatekeeper agent reads `collection_quality.json` as an input
3. After gatekeeper exits, orchestrator reads `gatekeeper_decision.json` — if `collection_quality.thin_collection == true` AND Admiralty is rated above C, downgrade to C in code and log the override

**Admiralty cap enforcement (code, not agent):**
```python
def _get_admiralty_reliability(gd: dict) -> str:
    """Handle both nested dict and plain string admiralty formats."""
    adm = gd.get("admiralty", "C")
    if isinstance(adm, dict):
        return adm.get("reliability", "C")
    return str(adm)[0] if adm else "C"

def enforce_admiralty_cap(region: str):
    cq = load_json(f"output/regional/{region}/collection_quality.json")
    gd = load_json(f"output/regional/{region}/gatekeeper_decision.json")
    if cq.get("thin_collection") and _get_admiralty_reliability(gd) < "C":
        # admiralty is a nested dict — update both reliability and rating
        if isinstance(gd.get("admiralty"), dict):
            gd["admiralty"]["reliability"] = "C"
            gd["admiralty"]["rating"] = f"C{gd['admiralty'].get('credibility', '3')}"
        else:
            gd["admiralty"] = "C3"
        gd["admiralty_cap_reason"] = "thin_collection — auto-capped by orchestrator"
        write_json(f"output/regional/{region}/gatekeeper_decision.json", gd)
```

**Verification:**
- Mock run with a region that has < 3 indicators → `collection_quality.json` shows `thin_collection: true`
- Gatekeeper decision shows `admiralty_cap_reason` if applicable

### Phase 1 Done Criteria
- [ ] Each `lead_indicator` in geo/cyber signal files has `signal_id` (format: `{region}-{pillar}-{NNN}`) and `source_url`
- [ ] Both `research_collector.py` (live) and mock collectors generate signal_ids
- [ ] `collection_quality.json` written per region after every collection run
- [ ] `thin_collection: true` when < 3 grounded indicators per pillar
- [ ] Admiralty capped at C in code when `thin_collection: true`

---

## Phase 2 — claims.json + Two-Step Analyst
**Owner:** Builder B | **Prerequisite for:** Phase 3 | **Parallel with:** Phase 4

### Task 2-1: Define claims.json schema documentation

Document the expected schema at the top of `regional-analyst-agent.md` (inline, not a separate file). The agent needs to know the schema to write it correctly. Include the full example from the spec.

### Task 2-2: Update regional-analyst-agent.md — two-step prompt

**File:** `.claude/agents/regional-analyst-agent.md`

**STEP 1 (new — insert before current STEP 2):** Claim formation

Add a new step after LOAD CONTEXT:

```
## STEP 2 — WRITE CLAIMS (before any prose)

Before writing the brief, write `output/regional/{region_lower}/claims.json`
using the Write tool.

Rules:
- claim_type "fact": signal_ids must be non-empty. Cite the signal_id from
  the signal files. If you cannot cite a signal_id, use "assessment" instead.
- claim_type "assessment": signal_ids recommended. Use when inferring a pattern
  from multiple signals without a single named source.
- claim_type "estimate": signal_ids empty. Use only for explicit gap
  acknowledgments or forward-looking inferences.
- You may not use threat actor names or incident descriptions that do not
  appear in the signal files, even if you know them from general knowledge.
  If a threat actor is not in the signals, it is not in the claims.
- paragraph field: "why" / "how" / "sowhat" — route each claim to the
  correct brief section.

Write every substantive claim as a claim entry. Aim for 6–10 claims per region.
```

**STEP 3 (existing brief writing step — retitled):** Prose rendering

Add constraint to existing brief-writing step:

```
Read claims.json before writing the brief. The prose renders the claims in
claims.json — it does not create new ones. You may not introduce a fact in
the prose that does not have a corresponding "fact" or "assessment" claim
in claims.json. "estimate" claims surface as explicit caveats or gap
acknowledgments in the prose.
```

**Verification:** Run a mock pipeline for one region. Confirm:
- `claims.json` is written before `report.md`
- Each claim has the required fields
- No `fact` claim has empty `signal_ids`

### Task 2-3: Update gatekeeper-agent.md to read collection_quality.json

**File:** `.claude/agents/gatekeeper-agent.md`

Add to LOAD CONTEXT:
```
Read `output/regional/{region_lower}/collection_quality.json` if present.
If `thin_collection: true`, factor this into your Admiralty rating —
the source basis is limited. Note the collection gap in your rationale.
```

### Phase 2 Done Criteria
- [ ] `claims.json` written per region by analyst before `report.md`
- [ ] Schema matches spec: `claim_id`, `claim_type`, `pillar`, `text`, `signal_ids`, `confidence`, `paragraph` (no `source_urls` — derived at render time)
- [ ] No `fact` claim has empty `signal_ids` in a successful run
- [ ] Analyst prompt has two explicit steps: claim formation then prose rendering
- [ ] Gatekeeper reads `collection_quality.json` and notes thin_collection in rationale
- [ ] `signal_clusters.json` is **retained unchanged** in this phase — deprecation is a future cleanup pass after claims.json is stable

---

## Phase 3 — Grounding Validator Stop Hook
**Owner:** Builder C | **Prerequisite:** Phase 2 complete

### Task 3-1: Write grounding-validator.py

**File:** `.claude/hooks/validators/grounding-validator.py`

```python
"""
Grounding validator — deterministic check of claims.json integrity.
Runs as stop hook after regional-analyst-agent exits.

Guard: if gatekeeper_decision.json shows decision != "ESCALATE", exit 0 immediately.

Checks:
0. claims.json.mtime < report.md.mtime — if report.md was written first,
   the two-step order was violated (fail with explicit message)
1. claims.json exists and is valid JSON
2. Every fact claim has non-empty signal_ids
3. Every signal_id in claims exists in geo/cyber_signals.json
   (skipped when research_scratchpad.json is absent — absence = mock mode;
    do NOT use os.environ OSINT_LIVE — env vars are unreliable in hook
    subprocess context; research_scratchpad.json presence is the canonical
    live/mock signal in this pipeline)
4. At least one claim per paragraph (why, how, sowhat)
   — estimate claims count as valid (they explicitly signal absence)
5. If all claims are estimate AND region is ESCALATED → FAIL

Emits to system_trace.log:
- Claim type distribution {fact: N, assessment: N, estimate: N}
- fact_claims / total_claims ratio (grounding score)
- Orphaned signal_ids (collected but not cited)
"""
```

Follow the existing `jargon-auditor.py` pattern for:
- Retry file at `output/.retries/{label}.retries`
- Max 3 retries then force-approve with warning
- Exit codes: 0 = pass, 1 = fail

### Task 3-2: Wire grounding-validator as Stop hook in regional-analyst-agent.md

**File:** `.claude/agents/regional-analyst-agent.md`

Update the `hooks` frontmatter:
```yaml
hooks:
  Stop:
    - type: command
      command: "uv run python .claude/hooks/validators/regional-analyst-stop.py"
    - type: command
      command: "uv run python .claude/hooks/validators/grounding-validator.py"
```

Pass region as argument or read from claims.json — builder to decide cleanest approach given how existing stop hooks receive context.

### Phase 3 Done Criteria
- [ ] `grounding-validator.py` exists and passes on a valid claims.json
- [ ] Validator fails when a `fact` claim has empty `signal_ids`
- [ ] Validator fails when a `signal_id` doesn't exist in signal files (live mode)
- [ ] Validator passes in mock mode regardless of signal_id resolution
- [ ] Grounding score written to `system_trace.log`
- [ ] Wired as Stop hook in `regional-analyst-agent.md`
- [ ] Max 3 retries pattern followed

---

## Phase 4 — Collection Quality Gate (standalone)
**Owner:** Builder D | **Parallel with:** Phases 2 and 3 | **Prerequisite:** Phase 1

Phase 4 is the extraction of collection gate logic into a clean, testable utility. Phase 1 wires the gate inline; Phase 4 ensures it's robust and well-integrated.

### Task 4-1: Extract collection gate into tools/collection_gate.py

**File:** `tools/collection_gate.py` (new)

Move the `check_collection_quality()` function from wherever Builder A placed it in Phase 1 into a dedicated module. Add:
- CLI entry point: `uv run python tools/collection_gate.py {region}` — prints result, exits 0/1
- Logging to `output/system_trace.log`
- Threshold configurable via env var `COLLECTION_QUALITY_THRESHOLD` (default 3)

### Task 4-2: Update run-crq.md to call collection_gate.py cleanly

Ensure the Phase 1 inline wiring calls `tools/collection_gate.py` as the canonical source. No duplicate logic.

### Phase 4 Done Criteria
- [ ] `tools/collection_gate.py` exists with CLI entry point
- [ ] Threshold is configurable
- [ ] Result logged to `system_trace.log`
- [ ] `run-crq.md` calls `collection_gate.py`, not inline code

---

## Validation Pass
**Owner:** Validator | **After:** All phases complete

Cross-check all changes against the spec done criteria:

```
From spec:
[ ] Each lead_indicator in geo/cyber signal files has signal_id and source_url
[ ] claims.json written per region by analyst before report.md
[ ] No fact claim in claims.json has empty signal_ids
[ ] Every signal_id in claims.json resolves to an indicator in the signal files
[ ] grounding-validator.py blocks on phantom signal_ids and ungrounded facts
[ ] thin_collection: true written to collection_quality.json when < 3 grounded indicators
[ ] Admiralty capped at C when thin_collection: true
[ ] Grounding score emitted to system_trace.log per region per run
[ ] Pipeline runs end-to-end in mock mode without errors
[ ] Pipeline runs end-to-end in live mode (OSINT_LIVE=true) without errors
```

Run mock pipeline (`/run-crq`) and inspect all five regions:
- All `claims.json` files written and valid
- No `fact` claims with empty `signal_ids`
- `collection_quality.json` present per region
- `system_trace.log` contains grounding scores

---

## Execution Order Summary

```
Phase 1 (Builder A) — sequential, must complete first
  ↓
Phase 2 (Builder B) ──────────── parallel ──────────── Phase 4 (Builder D)
  ↓
Phase 3 (Builder C)
  ↓
Validation (Validator)
  ↓
TeamDelete
```

---

## What Is NOT in Scope

- Updating `report_builder.py` to read from `claims.json` instead of parsing prose (deferred cleanup — noted in spec)
- Dashboard changes
- Global builder changes (inherits grounded data automatically)
- CISO docx confidence zone display (deferred — requires UX decision on label format)
