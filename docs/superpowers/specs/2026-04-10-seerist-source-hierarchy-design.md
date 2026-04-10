# Seerist Source Hierarchy Design

**Goal:** Enforce Seerist as the primary intelligence source and OSINT as supporting context, with deterministic upstream scoring replacing agent judgment about source quality.

**Architecture:** Pre-analyst Python scoring step derives `seerist_strength` into `collection_quality.json`. Gatekeeper reads a pre-computed flag and applies a single rule. Analyst agent writes claims anchored on Seerist `signal_ids` with OSINT adding recency and named specifics. Stop hook validates the hierarchy is reflected in claims — not just declared.

**Tech Stack:** Python (`collection_gate.py`) · Haiku (gatekeeper) · Sonnet (analyst) · Stop hook (regional-analyst-stop.py)

---

## Source Hierarchy

Three roles, two enforcement tiers:

| Source | Role | Generates claims? | Enforcement |
|---|---|---|---|
| Seerist raw (events, verified_events, pulse, hotspots, risk_ratings) | Primary evidence | Yes — must anchor Why/How | signal_id format `seerist:*` |
| Seerist Scribe | Narrative framing only | No standalone claims | Reading input, shapes prose |
| OSINT (Tavily) | Recency + named specifics | Yes — supporting | signal_id format `osint:*` |

**Tier derivation is deterministic.** The stop hook infers claim tier from `signal_ids` — not from a self-declared field the agent writes. A claim with `seerist:hotspot:apac-001` in `signal_ids` is Tier 1. A claim with only `osint:tavily:apac-geo-001` is Tier 2. The agent cannot misclassify a claim by labelling it incorrectly.

**Scribe is framing, not evidence.** Seerist Scribe processes Seerist's own data through an AI layer — it is not an independent source. The analyst reads Scribe to understand country context and frame the Why paragraph. Scribe does not generate citable claims. This is enforced by instruction, not by schema.

---

## Changes by Component

### 1. `tools/collection_gate.py` — Add `seerist_strength` scoring

`collection_gate.py` already runs before the gatekeeper and writes `collection_quality.json`. Add a `seerist_strength` field computed deterministically from `seerist_signals.json`:

```python
def score_seerist_strength(seerist: dict) -> str:
    """
    Returns 'high', 'low', or 'none'.
    HIGH: hotspot anomaly_flag=True OR verified_events ≥ 1 OR pulse delta ≤ -0.5
    LOW:  unverified events only OR pulse delta between -0.5 and 0
    NONE: seerist_signals.json absent, empty, or all fields empty
    """
```

Output added to `collection_quality.json`:
```json
{
  "region": "APAC",
  "thin_collection": false,
  "geo_grounded_count": 3,
  "cyber_grounded_count": 3,
  "threshold": 3,
  "seerist_strength": "high"
}
```

No agent judgment involved. Pure Python. Gatekeeper reads this pre-computed value.

---

### 2. `.claude/agents/gatekeeper-agent.md` — Single escalation rule

Replace the current ambiguous CLEAR/ESCALATE routing logic with a rule that reads `seerist_strength` from `collection_quality.json`:

```
seerist_strength = "high" or "low"  → Apply normal ESCALATE / MONITOR / CLEAR logic
seerist_strength = "none"           → Cap at MONITOR regardless of OSINT strength
                                      Write reason to gatekeeper_decision.json:
                                      "seerist_absent: OSINT alone insufficient for ESCALATE"
```

Haiku reads one field, applies one rule. No analytical judgment about source quality or recency gaps required.

**Why not a hard block?** OSINT-only ESCALATE is theoretically valid in a recency gap scenario — a confirmed breaking incident hasn't reached Seerist yet. Capping at MONITOR is the safe default. The `collection_lag` field (see analyst section below) surfaces the recency gap in the brief without suppressing it entirely.

`gatekeeper_decision.json` schema addition:
```json
{
  "seerist_absent": true,
  "seerist_absent_reason": "seerist_strength=none — escalation capped at MONITOR"
}
```
Field is omitted when `seerist_strength` is high or low.

---

### 3. `.claude/agents/regional-analyst-agent.md` — Seerist-first reading and collection_lag

**Reading order (explicit instruction, Step 1 rewrite):**

```
Step 1a — Read seerist_signals.json FIRST.
  Build the risk picture from Seerist data before reading anything else:
  - situational.events and verified_events → confirmed regional activity
  - analytical.hotspots (anomaly_flag=True) → live geospatial anomalies
  - analytical.pulse (delta, trend_direction) → directional risk trajectory
  - analytical.risk_ratings → country-level assessments
  This is the established intelligence picture. Everything else layers on top.

Step 1b — Read analytical.scribe.
  Use for country narrative framing and Why paragraph context.
  Do NOT generate claims from Scribe. It processes Seerist's own data — it is
  not an independent source.

Step 1c — Read osint_signals.json.
  Layer recency and named specifics on top of the Seerist picture:
  - Named threat actors, court cases, publication statistics
  - Events from the last 24-72h not yet absorbed by Seerist
  OSINT extends the established picture. It does not replace it.
```

**Why paragraph rule:**
> "The Why paragraph must lead with what Seerist is showing. Open with the pulse direction, a hotspot anomaly, or a verified event — then use OSINT to name the actors, cite the cases, and add specificity."

**How paragraph rule:**
> "The How paragraph describes adversary activity. If Seerist has verified events or hotspot anomalies, those are your lead. OSINT provides named threat actors and historical precedent. If Seerist is silent on cyber activity, say so — then use OSINT as the best available evidence with appropriate caveats."

**collection_lag field (new top-level claims.json field):**

When OSINT has active signals but `seerist_strength = "none"`, set `collection_lag.detected = true`:

```json
"collection_lag": {
  "detected": true,
  "note": "OSINT signals indicate active threat activity not yet reflected in Seerist pulse, events, or hotspots. Assess as early indicator pending Seerist corroboration."
}
```

When `seerist_strength` is high or low, set `collection_lag.detected = false` with empty note.

This field is always present in claims.json. The brief template surfaces the note as an explicit caveat when `detected = true`.

**OSINT-first prohibition (quality checklist addition):**
- [ ] Why paragraph leads with a Seerist signal (pulse, hotspot, verified event) when `seerist_strength` is high or low — not with an OSINT statistic
- [ ] `collection_lag` field present in claims.json at top level

---

### 4. `claims.json` — convergence_assessment unchanged, collection_lag added

`convergence_assessment` retains its 4 categories exactly as designed. No OSINT LEAD category. The recency gap scenario is captured by `collection_lag`, not by convergence — they measure different things:

- **convergence_assessment**: do two sources agree on the same threat?
- **collection_lag**: has one source not yet absorbed what the other is showing?

Top-level claims.json structure:
```json
{
  "region": "APAC",
  "generated_at": "2026-04-10T13:00:00Z",
  "convergence_assessment": {
    "category": "CONVERGE",
    "rationale": "Seerist hotspot anomaly in Taipei industrial district corroborated by OSINT IP theft trend indicators."
  },
  "collection_lag": {
    "detected": false,
    "note": ""
  },
  "claims": [...]
}
```

---

### 5. `.claude/hooks/validators/regional-analyst-stop.py` — Gate 4

Add Gate 4 after the existing claims schema gate (Gate 3):

```python
def validate_seerist_hierarchy(region: str) -> tuple[bool, list[str]]:
    """
    Gate 4: Enforce Seerist-first source hierarchy.

    Rules:
    - collection_lag field present in claims.json
    - If seerist_strength HIGH or LOW:
        - ≥2 claims in Why (paragraph='why') or How (paragraph='how') must contain
          a signal_id starting with 'seerist:'
    - If seerist_strength NONE:
        - collection_lag.detected must be True
    """
    quality_path = REGIONAL / region / "collection_quality.json"
    claims_path = REGIONAL / region / "claims.json"
    ...
```

Exit 2 on failure with actionable error messages naming which claims are missing Seerist signal_ids.

---

## Data Flow (updated)

```
seerist_collector.py     → seerist_signals.json
osint_collector.py       → osint_signals.json
scribe_enrichment.py     → appends to seerist_signals.json (analytical.scribe)
collection_gate.py       → collection_quality.json  ← NEW: seerist_strength field
gatekeeper-agent         → reads seerist_strength, applies single rule
                         → gatekeeper_decision.json
regional-analyst-agent   → reads Seerist first, Scribe second, OSINT third
                         → claims.json (convergence_assessment + collection_lag)
                         → report.md (Seerist-anchored Why/How)
regional-analyst-stop.py → Gate 1: jargon
                           Gate 2: source attribution
                           Gate 3: claims schema (convergence_assessment, bullets, watch claims)
                           Gate 4: Seerist hierarchy (seerist: signal_ids in Why/How)
extract_sections.py      → signal_clusters.json + sections.json
```

---

## Files Modified

| File | Change |
|---|---|
| `tools/collection_gate.py` | Add `seerist_strength` scoring + write to collection_quality.json |
| `.claude/agents/gatekeeper-agent.md` | Read `seerist_strength`, apply single escalation cap rule |
| `.claude/agents/regional-analyst-agent.md` | Seerist-first reading order, Scribe framing rule, collection_lag field, OSINT-first prohibition in checklist |
| `.claude/hooks/validators/regional-analyst-stop.py` | Gate 4: Seerist hierarchy validation |

No changes to: `osint_collector.py`, `seerist_collector.py`, `scribe_enrichment.py`, `extract_sections.py`, `scenario_mapper.py`, `gatekeeper-agent` stop hooks, `global-builder-agent`.

---

## What This Delivers

A brief written under this design will:
1. Open Why with what Seerist is showing — not an OSINT statistic
2. Name the Seerist hotspot, pulse delta, or verified event before citing ASPI or Dark Reading
3. Explicitly caveat when Seerist is silent and OSINT is carrying the assessment
4. Never ESCALATE on OSINT alone — Seerist must corroborate or the gatekeeper caps at MONITOR
5. Have those guarantees enforced deterministically by the stop hook — not reliant on agent compliance
