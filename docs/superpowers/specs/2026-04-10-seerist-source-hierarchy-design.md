# Seerist Source Hierarchy Design

**Goal:** Enforce Seerist as the primary intelligence source and OSINT as supporting context, with deterministic upstream scoring replacing agent judgment about source quality.

**Architecture:** Pre-analyst Python scoring step derives `seerist_strength` and `collection_lag` into `collection_quality.json`. Gatekeeper reads a pre-computed flag and applies a single rule. Analyst agent writes claims anchored on Seerist `signal_ids` with OSINT adding recency and named specifics. Stop hook validates the hierarchy is reflected in claims — not just declared. Tier is derived from `signal_id` prefix, never self-declared.

**Tech Stack:** Python (`collection_gate.py`, `tools/seerist_strength.py`) · Haiku (gatekeeper) · Sonnet (analyst) · Stop hook (regional-analyst-stop.py)

---

## Source Hierarchy

Three roles, signal_id-derived tiers:

| Source | signal_id prefix | Confidence | Role |
|---|---|---|---|
| Seerist raw (events, verified_events, hotspots, pulse, risk_ratings) | `seerist:event:*` `seerist:hotspot:*` `seerist:pulse:*` | Confirmed | Primary evidence — must anchor Why/How |
| Seerist Scribe | `seerist:scribe:*` | Assessed | AI synthesis of Seerist data — good for Why framing, not independent |
| OSINT (Tavily) | `osint:tavily:*` | Assessed | Recency + named specifics — extends, never replaces |

**Tier derivation is deterministic.** The stop hook infers tier from `signal_ids` prefix — not from a field the agent writes. The agent cannot misclassify a claim.

**Scribe is Tier 1 Assessed, not excluded.** Scribe generates useful analytical content (country risk assessments, threat framing) but processes Seerist's own data through an AI layer — it is not an independent source. Claims citing `seerist:scribe:*` are valid with confidence "Assessed." They do not satisfy the Tier 1 Confirmed requirement for Why/How anchoring — only `seerist:event:*`, `seerist:hotspot:*`, `seerist:pulse:*` do.

---

## Shared Utility: `tools/seerist_strength.py`

A single function used by both `collection_gate.py` and `regional-analyst-stop.py`. One implementation, two consumers, no inter-file dependency.

```python
# tools/seerist_strength.py

PULSE_DELTA_THRESHOLD = -0.5
# Calibrate as Seerist baseline behavior is observed across regions.
# Seerist pulse runs 0–5. A delta of -0.5 (10% of scale) is a directional signal.
# Tighten toward -0.3 for higher sensitivity; loosen toward -0.7 for lower noise.

def score_seerist_strength(seerist: dict) -> str:
    """
    Returns 'high', 'low', or 'none'.

    HIGH:
      - Any hotspot with anomaly_flag=True
      - Any verified_event present
      - Pulse region_summary avg_delta <= PULSE_DELTA_THRESHOLD

    LOW:
      - Unverified situational events only
      - Pulse delta between PULSE_DELTA_THRESHOLD and 0
      - No hotspot anomaly, no verified events

    NONE:
      - seerist_signals dict is empty, absent, or all signal arrays are empty
    """
    if not seerist:
        return "none"

    sit = seerist.get("situational", {})
    ana = seerist.get("analytical", {})

    # HIGH conditions
    hotspots = ana.get("hotspots", [])
    if any(h.get("anomaly_flag") for h in hotspots):
        return "high"

    verified = sit.get("verified_events", [])
    if verified:
        return "high"

    pulse = ana.get("pulse", {})
    delta = pulse.get("region_summary", {}).get("avg_delta", 0)
    if delta <= PULSE_DELTA_THRESHOLD:
        return "high"

    # LOW conditions
    events = sit.get("events", [])
    if events or (delta < 0):
        return "low"

    return "none"
```

---

## Changes by Component

### 1. `tools/collection_gate.py` — Add `seerist_strength` and `collection_lag`

Import `score_seerist_strength` from `tools/seerist_strength.py`. Add two fields to `collection_quality.json`:

```json
{
  "region": "APAC",
  "thin_collection": false,
  "geo_grounded_count": 3,
  "cyber_grounded_count": 3,
  "threshold": 3,
  "seerist_strength": "high",
  "collection_lag": {
    "detected": false,
    "note": ""
  }
}
```

`collection_lag.detected` is set deterministically:
- `seerist_strength = "none"` AND OSINT has ≥1 lead_indicator → `detected: true`, `note: "OSINT signals present but Seerist has no corroborating data — assess as early indicator pending confirmation"`
- All other cases → `detected: false`, `note: ""`

The analyst reads `collection_lag` from this file. It is not a field the analyst sets.

---

### 2. `.claude/agents/gatekeeper-agent.md` — Single escalation rule

Read `seerist_strength` from `collection_quality.json`. Apply one rule:

```
seerist_strength = "high" or "low"  → Normal ESCALATE / MONITOR / CLEAR logic applies
seerist_strength = "none"           → Cap at MONITOR regardless of OSINT signals
```

`gatekeeper_decision.json` — `seerist_absent` field always present:

```json
{
  "region": "APAC",
  "decision": "MONITOR",
  "seerist_absent": true,
  "seerist_absent_reason": "seerist_strength=none — OSINT alone insufficient for ESCALATE"
}
```

When `seerist_strength` is high or low:
```json
{
  "seerist_absent": false,
  "seerist_absent_reason": ""
}
```

Field always present. No conditional schema.

---

### 3. `.claude/agents/regional-analyst-agent.md` — Seerist-first reading order

**Step 1 rewrite — explicit reading sequence:**

```
Step 1a — Read seerist_signals.json FIRST.
  This is the established intelligence picture. Build your risk assessment from:
  - situational.verified_events → confirmed regional incidents
  - analytical.hotspots (anomaly_flag=True) → live geospatial anomalies
  - analytical.pulse (delta, trend_direction) → directional trajectory
  - analytical.risk_ratings → country-level assessments
  Everything else layers on top of this.

Step 1b — Read analytical.scribe.
  AI synthesis of Seerist data. Use for Why paragraph country framing.
  Claims citing scribe use confidence "Assessed" and signal_ids "seerist:scribe:NNN".
  Scribe is not independent of Seerist raw data — do not treat it as corroboration.

Step 1c — Read collection_quality.json.
  Read seerist_strength and collection_lag fields. These are pre-computed.
  If collection_lag.detected = true: your brief must surface the caveat in So What.

Step 1d — Read osint_signals.json.
  Layer recency and named specifics on top of the Seerist picture:
  named threat actors, court cases, publication statistics, breaking events
  not yet absorbed by Seerist. OSINT extends — it does not anchor.
```

**Why paragraph rule:**
> "The Why paragraph opens with what Seerist is showing. Your first Why claim must cite a `seerist:event:*`, `seerist:hotspot:*`, or `seerist:pulse:*` signal_id when `seerist_strength` is high or low. Use OSINT to name actors, cite cases, and add specificity after the Seerist anchor."

**How paragraph rule:**
> "If Seerist has verified events or hotspot anomalies relevant to cyber activity, those lead. OSINT provides named threat actors and historical precedent. If Seerist is silent on cyber, state it plainly — then use OSINT as best available evidence with explicit caveats."

**collection_lag caveat (So What):**
> "If `collection_lag.detected = true`, close So What with: 'Note: current Seerist data does not yet corroborate these OSINT signals. The assessment is based on early indicators and should be treated as pending confirmation.'"

**Quality checklist additions:**
- [ ] First `paragraph='why'` claim cites a `seerist:event:*`, `seerist:hotspot:*`, or `seerist:pulse:*` signal_id when `seerist_strength` is high or low
- [ ] Every substantive Seerist signal (verified event, hotspot with anomaly_flag=True) has a corresponding claim citing its signal_id
- [ ] `collection_lag` caveat surfaced in So What when `detected=true`

---

### 4. `claims.json` — convergence_assessment unchanged, collection_lag read from file

`convergence_assessment` retains its 4 categories. No new category.

`collection_lag` is read from `collection_quality.json` — the analyst does not set it. The analyst's only obligation is to surface the caveat in prose when `detected=true`.

Top-level claims.json structure unchanged from current schema except `collection_lag` is no longer written by the analyst:

```json
{
  "region": "APAC",
  "generated_at": "2026-04-10T13:00:00Z",
  "convergence_assessment": {
    "category": "CONVERGE",
    "rationale": "Seerist Taipei industrial district hotspot anomaly (deviation_score 0.87) corroborated by OSINT IP theft trend indicators pointing to same geographic cluster."
  },
  "claims": [...]
}
```

---

### 5. `.claude/hooks/validators/regional-analyst-stop.py` — Gate 4

Gate 4 is self-contained. It derives `seerist_strength` directly from `seerist_signals.json` using the shared utility — no dependency on `collection_quality.json` having been written correctly.

```python
def validate_seerist_hierarchy(region: str) -> tuple[bool, list[str]]:
    """
    Gate 4: Enforce Seerist-first source hierarchy.

    Reads seerist_signals.json directly (via shared seerist_strength utility).
    Does not depend on collection_quality.json.

    Rules:
    A. If seerist_strength HIGH or LOW:
       - First claim with paragraph='why' must contain a seerist:event/hotspot/pulse signal_id
       - Every hotspot with anomaly_flag=True must have a corresponding claim citing its signal_id
       - Every verified_event must have a corresponding claim citing its signal_id

    B. If seerist_strength NONE:
       - Skip hierarchy check (no Seerist signals to enforce)
       - Log: "seerist_strength=none — hierarchy check skipped"
       - Exit 0

    C. If seerist_signals.json absent:
       - Skip gracefully, exit 0
    """
```

**Rule A detail — "every substantive signal must appear as a claim":**

The gate collects all signal_ids from:
- `analytical.hotspots` where `anomaly_flag=True`
- `situational.verified_events`

Then checks that each signal_id appears in at least one claim's `signal_ids` array. Missing signal_id = violation. This replaces the arbitrary "≥2 claims" threshold — the required count comes from the data, not a hardcoded number.

Exit 2 on any violation with the exact missing signal_ids listed.

---

## Data Flow (updated)

```
seerist_collector.py     → seerist_signals.json
osint_collector.py       → osint_signals.json
scribe_enrichment.py     → appends seerist_signals.json (analytical.scribe)

collection_gate.py       → collection_quality.json
  imports seerist_strength.py → seerist_strength: high|low|none
  derives collection_lag      → detected: true|false, note

gatekeeper-agent         → reads collection_quality.json (seerist_strength)
                           applies single escalation cap rule
                         → gatekeeper_decision.json (seerist_absent always present)

regional-analyst-agent   → reads seerist first, scribe second, collection_quality third, osint fourth
                         → claims.json (convergence_assessment, Seerist-anchored Why/How claims)
                         → report.md (collection_lag caveat in So What when detected=true)
                         → data.json (primary_scenario, signal_type, threat_actor)

regional-analyst-stop.py → Gate 1: jargon audit
                           Gate 2: source attribution
                           Gate 3: claims schema (convergence_assessment, bullets, watch claims)
                           Gate 4: Seerist hierarchy
                             imports seerist_strength.py directly
                             checks first why-claim is seerist-anchored
                             checks every anomaly hotspot + verified event has a claim

extract_sections.py      → signal_clusters.json + sections.json
```

---

## Files Created / Modified

| File | Change |
|---|---|
| `tools/seerist_strength.py` | **NEW** — shared scoring utility, `PULSE_DELTA_THRESHOLD` constant |
| `tools/collection_gate.py` | Import seerist_strength, add `seerist_strength` + `collection_lag` to output |
| `.claude/agents/gatekeeper-agent.md` | Read `seerist_strength`, single cap rule, `seerist_absent` always in output |
| `.claude/agents/regional-analyst-agent.md` | Seerist-first reading order, collection_lag caveat, checklist additions |
| `.claude/hooks/validators/regional-analyst-stop.py` | Gate 4: self-contained hierarchy validation via shared utility |

No changes to: `osint_collector.py`, `seerist_collector.py`, `scribe_enrichment.py`, `extract_sections.py`, `scenario_mapper.py`, `global-builder-agent`.

---

## What This Delivers

A brief written under this design will:

1. Open Why with a Seerist signal (hotspot, pulse, verified event) — not an OSINT statistic
2. Have every Seerist hotspot anomaly and verified event represented as a named claim
3. Use Scribe for country framing with correct "Assessed" confidence — not as independent corroboration
4. Explicitly caveat when Seerist is silent and OSINT is carrying the assessment
5. Never ESCALATE on OSINT alone — gatekeeper caps at MONITOR when `seerist_strength=none`
6. Have all guarantees enforced by deterministic Python (stop hook + collection_gate) — not agent compliance
7. Have tier derivable by any downstream consumer from `signal_id` prefix — no self-declared fields
