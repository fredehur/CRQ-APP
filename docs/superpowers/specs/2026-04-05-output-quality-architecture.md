# Output Quality Architecture — Claim-First Grounding
**Date:** 2026-04-05
**Status:** Spec approved — awaiting master build plan completion before implementation
**Depends on:** `2026-04-05-master-build-plan.md` (must ship first)

---

## Problem Statement

The CRQ pipeline produces intelligence outputs that can contain ungrounded claims — statements the analyst writes from training data rather than from collected signals. The current quality gates (jargon auditor, source attribution hook) catch language violations but do not verify that each claim traces back to a collected, URL-backed source. Two compounding failure modes:

1. **Traceability**: A board member or CISO asks "where did this come from?" and there is no answer — the sourcing chain breaks somewhere between Tavily result → synthesis → analyst prose.
2. **Analytical drift**: The analyst reasons loosely from thin signals, inflates confidence, or imports threat actor names from training data rather than from what was actually collected.

These compound: thin signals give the analyst cover to drift.

---

## Design Principle

**Validate claims before they become prose.**

Separate analytical work (claim formation) from communication work (prose rendering). Enforce grounding on the structured intermediate artifact — not on the rendered brief. The brief is a rendering of pre-validated, grounded claims, not a source of truth.

---

## Architecture Overview

```
Collection
  research_collector.py → geo_signals.json + cyber_signals.json
    [NEW] each lead_indicator: signal_id + source_url

  [NEW] Collection quality gate
    < 3 grounded indicators per pillar → thin_collection: true in gatekeeper_decision.json

Gatekeeper
  gatekeeper-agent → gatekeeper_decision.json
    [minor] records which signal_ids triggered escalation
    reads thin_collection flag → caps Admiralty at C if true

Regional Analyst (two-step)
  Step 1 — Claim formation
    reads signal files → writes claims.json (schema-enforced)
    fact claims require signal_ids — schema rejects empty

  Step 2 — Prose rendering
    reads validated claims.json → writes report.md
    may not introduce facts not present in claims.json

  [NEW] Stop hook: grounding-validator.py
    deterministic JSON check — no prose parsing
    fail: fact claim with no signal_ids
    fail: signal_id not found in signal files
    emit: grounding score to system_trace.log

Global Builder
  inherits grounded regional data — no new changes required

Outputs
  CISO docx — confidence zones visible (Confirmed / Assessed / Analyst judgment)
  Board PDF / PPTX — confidence zones hidden, prose reflects them naturally
  RSM brief — unchanged
```

---

## Section 1 — Data Contract: signal files

### Change in research_collector.py

Each `lead_indicator` in `geo_signals.json` and `cyber_signals.json` gains two new fields at synthesis time:

```json
{
  "lead_indicators": [
    {
      "signal_id": "apac-geo-001",
      "indicator": "IRGC-affiliated groups escalating statements threatening energy transit...",
      "source_name": "Astaara / West P&I",
      "source_url": "https://astaara.com/..."
    }
  ]
}
```

**signal_id format:** `{region}-{pillar}-{sequence}` — e.g. `apac-geo-001`. Stable within a run, not across runs. Generated sequentially by the synthesiser as it processes Tavily results.

**source_url:** Moves from the file-level `sources` array (current) to the **indicator level**. Traceability requires knowing which URL backs which specific indicator, not just which URLs appeared somewhere in the collection.

### Collection quality gate (new pre-analyst check)

After `research_collector.py` exits, before gatekeeper runs:

- Count `lead_indicators` with non-empty `source_url` per pillar
- Write result to `output/regional/{region}/collection_quality.json` (new file — separate from `gatekeeper_decision.json`)
- Gatekeeper reads `collection_quality.json` as an input and factors `thin_collection` into its Admiralty rating decision
- After gatekeeper exits, the orchestrator enforces the Admiralty cap in code (same pattern as `enrich_region_data` in the master build plan) — the agent is not trusted to enforce it

**Why not write to `gatekeeper_decision.json` directly:** That file is created by the gatekeeper agent, not pre-existing. Writing to it before the agent runs and having the agent overwrite it is a race condition. The canonical pattern in this pipeline is: code writes inputs, agents transform them, code enforces constraints on outputs.

This fixes the known P1-2 bug (cyber indicators returning 0) by making it a named, visible state rather than a silent failure that the analyst papers over with training data.

### Mock mode compatibility

In mock mode (`OSINT_LIVE=false`), signal files come from `geo_collector.py` / `cyber_collector.py`, not `research_collector.py`. These do not go through the signal_id generation path.

**Fix:** Mock collectors must generate signal_ids from fixture data using the same `{region}-{pillar}-{sequence}` format. Alternatively, the grounding validator skips the signal_id resolution check (check 3) when `OSINT_LIVE=false`. Either approach is acceptable — the latter is faster to ship.

**Files changed:**
- `tools/research_collector.py` — signal_id generation + source_url per indicator
- `tools/geo_collector.py` + `tools/cyber_collector.py` — signal_id generation from fixtures (if mock-compat path chosen)
- `.claude/commands/run-crq.md` — collection quality gate step wired before gatekeeper

---

## Section 2 — claims.json (new canonical analytical artifact)

New file: `output/regional/{region}/claims.json`

Replaces `signal_clusters.json` as the analytical source of truth. Written by the analyst in Step 1 before any prose. Validator-enforced at runtime by `grounding-validator.py` — no separate JSON Schema file is required. "Schema-enforced" in this spec means the validator will reject non-compliant files and trigger a retry.

### Schema

```json
{
  "region": "APAC",
  "timestamp": "2026-04-05T...",
  "claims": [
    {
      "claim_id": "apac-001",
      "claim_type": "fact",
      "pillar": "cyber",
      "text": "IRGC-affiliated groups maintain active campaigns against industrial control systems",
      "signal_ids": ["apac-cyber-003"],
      "source_urls": ["https://trellix.com/..."],
      "confidence": "Confirmed",
      "paragraph": "how"
    },
    {
      "claim_id": "apac-002",
      "claim_type": "assessment",
      "pillar": "geopolitical",
      "text": "APAC advanced manufacturing supply chains represent a documented state collection priority",
      "signal_ids": ["apac-geo-001", "apac-geo-002"],
      "source_urls": [],
      "confidence": "Assessed",
      "paragraph": "why"
    },
    {
      "claim_id": "apac-003",
      "claim_type": "estimate",
      "pillar": "cyber",
      "text": "China-centric IP theft vector requires further collection before confidence can be elevated",
      "signal_ids": [],
      "source_urls": [],
      "confidence": "Analyst judgment",
      "paragraph": "how"
    }
  ]
}
```

### Schema rules (enforced, not aspirational)

| claim_type | signal_ids | source_urls | When to use |
|---|---|---|---|
| `fact` | **required, non-empty** | recommended | Named actor/incident with a collected source |
| `assessment` | recommended | optional | Pattern inferred from multiple signals |
| `estimate` | empty allowed | empty allowed | Explicit gap acknowledgment or forward-looking inference |

The grounding validator rejects any `fact` claim with empty `signal_ids`. This is the structural enforcement — the analyst cannot write a confirmed statement without citing a signal.

### paragraph field

Routes claims to the correct brief section during prose rendering:
- `why` → Geopolitical Driver paragraph
- `how` → Cyber Vector paragraph
- `sowhat` → Business Impact paragraph

### Relation to signal_clusters.json

`claims.json` supersedes `signal_clusters.json` as the analytical registry. `signal_clusters.json` is retained for the source registry pipeline (cited flag, appearance tracking) but is no longer the primary traceability artifact.

---

## Section 3 — Two-step regional analyst

Same agent invocation, two sequential `Write` calls.

### Step 1 — Claim formation (analytical work)

**Prompt constraint added to regional-analyst-agent.md:**

> "Before writing any prose, write `claims.json` using the Write tool. Each claim must be grounded in the signal files you have read. A `fact` claim with empty `signal_ids` violates the schema and will be rejected by the validator. If you cannot cite a `signal_id` from the signal files, the claim must be typed `assessment` or `estimate`. You may not use threat actor names, incident descriptions, or capability claims that do not appear in the signal files."

The claim formation step is constrained to what exists in the signal files. Training-data knowledge of threat actors is not a valid source for a `fact` claim.

### Step 2 — Prose rendering (communication work)

**Prompt constraint added:**

> "Read `claims.json`. Write `report.md` using only the claims in that file. The prose renders the claims — it does not create new ones. You may not introduce a fact in the prose that does not have a corresponding `fact` or `assessment` claim in `claims.json`. `estimate` claims surface as explicit caveats or gap acknowledgments."

Confidence zones in prose are natural outputs of claim_type:
- `fact` claims → declarative statements, inline source citations
- `assessment` claims → hedged language: "assessed to", "indicates that", "consistent with"
- `estimate` claims → explicit gap framing: "requires further collection", "cannot be confirmed"

### Stop hook targeting

If the stop hook fails on `claims.json` validation, the retry prompt targets the claims file — not the prose. The analyst rewrites the specific fact claim that failed, not the entire brief.

### Known limitation — prose cannot be structurally constrained

The grounding validator runs after both writes and enforces claim integrity (no phantom signal_ids, no ungrounded fact claims). It cannot verify that `report.md` introduced no new facts beyond what is in `claims.json` — that would require prose parsing, which is explicitly excluded from this design. The constraint in the prose rendering prompt ("you may not introduce facts not in claims.json") is behavioural, not structural. This is a known gap, not an implementation oversight. The validator catches the most dangerous failure mode (phantom citations); the prose constraint catches the remainder with high but not guaranteed reliability.

---

## Section 4 — Grounding validator (new stop hook)

**File:** `.claude/hooks/validators/grounding-validator.py`

Runs after regional-analyst-agent exits, before global-builder-agent starts.

### Checks (deterministic — no prose parsing, no LLM judge)

1. `claims.json` exists and parses as valid JSON
2. Every `fact` claim has `signal_ids` non-empty
3. Every `signal_id` referenced in claims exists as an indicator in `geo_signals.json` or `cyber_signals.json`
4. No `source_url` in claims appears in `data/blocked_urls.txt`
5. At least one claim per paragraph (`why`, `how`, `sowhat`)

### Emits (logged, not fail conditions)

- Claim type distribution: `{fact: N, assessment: N, estimate: N}` and ratio `fact_claims / total_claims` — written to `system_trace.log` as grounding score
- Orphaned signal_ids: indicators collected but not cited in any claim
- Orphaned signal_ids: indicators collected but not cited in any claim

### Fail conditions

| Condition | Action |
|---|---|
| `claims.json` missing | FAIL — agent did not write Step 1 |
| `fact` claim with empty `signal_ids` | FAIL — rewrite claims |
| `signal_id` not found in signal files | FAIL — phantom citation |
| All claims are `estimate` AND region is ESCALATED | FAIL — escalated regions require at least one grounded fact or assessment |

**Max retries: 3** (consistent with existing jargon auditor pattern). On 3rd retry, force-approve with warning logged — same pattern as current auditors.

---

## Section 5 — Collection quality gate

**Where:** Wired into `run-crq.md` and `server.py` after `research_collector.py` exits, before gatekeeper agent runs.

**Logic (Python, added to research_collector.py or as a standalone check):**

```python
def check_collection_quality(region: str) -> dict:
    geo = load_json(f"output/regional/{region}/geo_signals.json")
    cyber = load_json(f"output/regional/{region}/cyber_signals.json")

    geo_grounded = sum(1 for i in geo.get("lead_indicators", []) if i.get("source_url"))
    cyber_grounded = sum(1 for i in cyber.get("lead_indicators", []) if i.get("source_url"))

    thin = geo_grounded < 3 or cyber_grounded < 3
    return {
        "thin_collection": thin,
        "geo_grounded_count": geo_grounded,
        "cyber_grounded_count": cyber_grounded
    }
```

Result written to `gatekeeper_decision.json` as `collection_quality` field.

**Downstream effects:**
- Gatekeeper: if `thin_collection: true`, cap Admiralty at C regardless of signal content
- Regional analyst: if `thin_collection: true`, must include at least one `estimate` claim acknowledging the gap — validator checks for this
- System trace: collection quality metrics logged per region per run

---

## Sequencing and Dependencies

```
Master build plan (ships first — already in progress)
  → report_builder.py extraction layer
  → exporters as pure renderers
  → RSM resilient fallback

This plan (ships after master build)
  Phase 1 — signal_ids in signal files (research_collector.py)
  Phase 2 — claims.json schema + two-step analyst prompt
  Phase 3 — grounding-validator.py stop hook
  Phase 4 — collection quality gate
```

Phase 1 is a prerequisite for all others. Phase 2 must precede Phase 3 — the grounding validator cannot be written or tested until claims.json exists. Phase 4 (collection quality gate) is independent and can run in parallel with Phase 2 or 3.

Correct order: 1 → 2 → 3, with 4 parallel to any phase after 1.

### Future alignment with master build plan

`report_builder.py` (master build) extracts `intel_bullets`, `adversary_bullets` etc. by parsing prose sentences from `report.md`. Once `claims.json` lands, this extraction can be simplified: read claim text from `claims.json` by `paragraph` field rather than parsing prose. This is not required for correctness — both approaches produce the same output — but it removes fragile regex logic from `report_builder.py`. Deferred to a cleanup pass after this plan ships.

---

## Files Changed

| File | Change | Phase |
|---|---|---|
| `tools/research_collector.py` | signal_id generation + source_url per indicator + collection quality gate logic | 1 |
| `tools/geo_collector.py` + `tools/cyber_collector.py` | signal_id generation from fixtures (mock mode compat) | 1 |
| `.claude/commands/run-crq.md` | collection quality gate + `collection_quality.json` write wired before gatekeeper | 1 |
| `server.py` | same as run-crq.md + orchestrator Admiralty cap enforcement after gatekeeper exits | 1 |
| `.claude/agents/regional-analyst-agent.md` | two-step prompt (claims.json then report.md) | 2 |
| `output/regional/{region}/claims.json` | new artifact (written by agent) | 2 |
| `output/regional/{region}/collection_quality.json` | new artifact (written by collection gate code) | 1 |
| `.claude/hooks/validators/grounding-validator.py` | new stop hook | 3 (after Phase 2) |
| `.claude/agents/regional-analyst-agent.md` | wire grounding-validator as Stop hook | 3 (after Phase 2) |

---

## Done Criteria

- [ ] Each `lead_indicator` in geo/cyber signal files has `signal_id` and `source_url`
- [ ] `claims.json` written per region by the analyst before `report.md`
- [ ] No `fact` claim in `claims.json` has empty `signal_ids`
- [ ] Every `signal_id` in `claims.json` resolves to an indicator in the signal files
- [ ] `grounding-validator.py` blocks on phantom signal_ids and ungrounded facts
- [ ] `thin_collection: true` written to `gatekeeper_decision.json` when < 3 grounded indicators per pillar
- [ ] Admiralty capped at C when `thin_collection: true`
- [ ] Grounding score emitted to `system_trace.log` per region per run
- [ ] Pipeline runs end-to-end in mock mode without errors
- [ ] Pipeline runs end-to-end in live mode (`OSINT_LIVE=true`) without errors
