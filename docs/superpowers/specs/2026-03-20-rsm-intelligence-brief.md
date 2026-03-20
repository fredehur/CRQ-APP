# RSM Intelligence Brief — Design Spec

**Date:** 2026-03-20
**Status:** Design approved, awaiting implementation plan
**Phase:** L (follows Phase K)

---

## Overview

This spec defines a new stakeholder delivery layer for the AeroGrid CRQ Intelligence Pipeline. It introduces a **Regional Security Manager (RSM) brief** — a push-delivered intelligence product formatted for ex-military field security professionals, separate from the existing board/CISO output path.

This is the first implementation of a broader **audience delivery architecture** that enables any stakeholder type to receive intelligence in the right format, at the right time, via the right channel — without modifying the intelligence production core.

---

## Persona

**Who:** Regional Security Managers — one per region (APAC, AME, LATAM, MED, NCE).

**Background:** Ex-military. Deep regional knowledge. Fluent in intelligence formats (SITREP, INTSUM). Responsible for physical security of AeroGrid personnel, manufacturing sites, and service operations in their region. Covers both physical/geopolitical threats and cyber awareness.

**What they need:**
1. **Delta** — what changed since last week. They know the baseline; don't rebuild it from scratch.
2. **Horizon** — signals they may have missed. Pre-media anomalies, weak signals before they become news.

**What they don't need:** narrative built up from zero context, VaCR financials at the detail level (they care about operational impact, not dollar exposure), SOC language, corporate prose.

---

## Products

### Primary: Weekly INTSUM

- **Cadence:** Every Monday, 07:00 local time per region
- **Read time:** ~3 minutes
- **Delivery:** Email push
- **Format:** SITREP/INTSUM monospace style

**Sections:**

```
AEROWIND // {REGION} INTSUM // WK{week}-{year}
PERIOD: {from} – {to} | PULSE: {prev}→{curr} ({delta}) | ADM: {admiralty} | PRIORITY SCENARIO: {scenario} #{rank}

█ SITUATION
One sentence. Overall posture. What changed since last INTSUM.

█ PHYSICAL & GEOPOLITICAL
Bulleted EventsAI events, delta only (new since last INTSUM).
Format: ▪ [CATEGORY][SEVERITY] Location — Description. Operational implication.
Categories: UNREST · CONFLICT · TERRORISM · CRIME · TRAVEL · MARITIME · POLITICAL · DISASTER

█ CYBER
Bulleted cyber signals, new or changed since last INTSUM.
Format: ▪ [TYPE][SEVERITY] Scope — Description. AeroGrid relevance (if any confirmed).
Sourced from: existing cyber_collector pipeline + Seerist +Cyber addon.

█ EARLY WARNING (PRE-MEDIA)
HotspotsAI anomalies. Signals before media coverage. Numbered watch priority.
Format: ▪ ⚡ Location — Description. Score {score}. Category: {category}. {N}hr watch.

█ ASSESSMENT
2–4 sentences. LLM-written. What do these signals mean for AeroGrid operations specifically?
Which sites, shipments, or personnel are in the exposure window?
Distinguish confirmed from assessed. No cyber jargon. No budget advice.

█ WATCH LIST — WK{next}
3–5 bullet items. What to monitor next week and why.

---
Reply: ACCURATE · OVERSTATED · UNDERSTATED · FALSE POSITIVE | AeroGrid Intelligence // {REGION} RSM
```

### Exception: Flash Alert

- **Trigger:** Threshold-based, any time (see Routing section)
- **Read time:** ~60 seconds
- **Delivery:** Email push, immediate on trigger
- **Format:** Abbreviated SITREP

```
⚡ AEROWIND // {REGION} FLASH // {DATE} {TIME}Z
TRIGGER: {trigger description} | ADM: {admiralty}

DEVELOPING SITUATION
One paragraph. What is happening, where, when first detected.

AEROWIND EXPOSURE
Which AeroGrid sites, personnel, or shipments are in the impact window.
Distance to nearest AeroGrid asset if relevant.

ACTION
Current advisory. No advisory / Personnel advisory / Site advisory.
Next update: {interval} or if situation escalates.

---
Reply: ACKNOWLEDGED · REQUEST ESCALATION · FALSE POSITIVE
```

---

## Architecture

### Design Principle

The intelligence production core (gatekeeper → analyst → builder → validator) is **unchanged**. This spec adds a parallel RSM delivery path that shares signal collection infrastructure but branches into its own routing, formatting, and delivery flow.

Every step follows the Disler filesystem-as-state pattern: each tool reads files, writes files, and does one thing.

### New Tools

#### `data/region_country_map.json` (new data file)

Maps pipeline region codes to Seerist country codes. Used by `seerist_collector.py`.

```json
{
  "APAC": ["CN", "AU", "TW", "JP", "SG", "KR", "IN"],
  "AME":  ["US", "CA", "MX"],
  "LATAM":["BR", "CL", "CO", "AR", "PE"],
  "MED":  ["IT", "ES", "GR", "TR", "MA", "EG"],
  "NCE":  ["DE", "PL", "DK", "SE", "NO", "FI"]
}
```

#### `tools/seerist_collector.py REGION`

Calls Seerist REST API for the region's countries (see `data/region_country_map.json`).

Fetches:
- `EventsAI` — events in last `--window` days (default 7d), all categories
- `HotspotsAI` — active anomalies, all categories
- `PulseAI` — current stability score + 29 sub-category ratings

Writes: `output/regional/{region}/seerist_signals.json`

Schema:
```json
{
  "region": "APAC",
  "window_days": 7,
  "pulse": {
    "score": 51,
    "score_prev": 58,
    "delta": -7,
    "security_risk": "High",
    "political_risk": "Medium",
    "sub_categories": {"border_tension": "High"}
  },
  "events": [
    {
      "event_id": "...",
      "category": "Unrest",
      "severity": 3,
      "title": "Kaohsiung dockworker strike",
      "location": {"name": "Kaohsiung, TW", "lat": 22.6, "lon": 120.3, "country_code": "TW"},
      "timestamp": "2026-03-19T08:00:00Z",
      "verified": true,
      "source_count": 12
    }
  ],
  "hotspots": [
    {
      "hotspot_id": "...",
      "location": {"name": "Taipei industrial district", "country_code": "TW"},
      "deviation_score": 0.87,
      "category_hint": "Unrest",
      "detected_at": "2026-03-19T14:00:00Z"
    }
  ],
  "collected_at": "2026-03-20T05:00:00Z"
}
```

Requires: `SEERIST_API_KEY` in `.env`. Falls back to mock fixture at `data/mock_osint_fixtures/{region}_seerist.json` if key absent or `--mock` flag set.

#### `tools/delta_computer.py REGION`

Reads current `seerist_signals.json` and previous run's `seerist_signals.json` (from `output/latest/regional/{region}/seerist_signals.json`). Computes explicit delta: new events, resolved events, pulse score change, new hotspots.

**Cold-start / first-run behavior:** If no previous `seerist_signals.json` exists in `output/latest/`, `delta_computer.py` writes a delta with empty `events_new`, `events_resolved`, `hotspots_new`, `hotspots_resolved` and `pulse_delta: null`. The formatter agent treats a null pulse_delta as "no prior baseline — first run." This is not an error condition; it exits 0.

Writes: `output/regional/{region}/region_delta.json`

Schema:
```json
{
  "region": "APAC",
  "period_from": "2026-03-13T05:00:00Z",
  "period_to": "2026-03-20T05:00:00Z",
  "pulse_delta": -7,
  "events_new": [...],
  "events_resolved": [...],
  "hotspots_new": [...],
  "hotspots_resolved": [...]
}
```

No LLM. Pure file diff. Deterministic.

#### `tools/threshold_evaluator.py`

Reads all `seerist_signals.json` and `region_delta.json` files + `audience_config.json` + `data/aerowind_sites.json` (AeroGrid site locations).

For each audience in `audience_config.json`, evaluates whether their trigger threshold is met.

Writes: `output/routing_decisions.json`

```json
{
  "generated_at": "...",
  "decisions": [
    {
      "audience": "rsm_apac",
      "region": "APAC",
      "product": "weekly_intsum",
      "triggered": true,
      "trigger_reason": "weekly cadence",
      "formatter_agent": "rsm-formatter-agent",
      "brief_path": "output/regional/apac/rsm_brief_apac_2026-03-20.md",
      "delivered": false
    },
    {
      "audience": "rsm_apac",
      "region": "APAC",
      "product": "flash",
      "triggered": true,
      "trigger_reason": "HotspotsAI score 0.87 >= 0.85 threshold, Taipei industrial district",
      "formatter_agent": "rsm-formatter-agent",
      "brief_path": "output/regional/apac/rsm_flash_apac_20260319T1423Z.md",
      "delivered": false
    }
  ]
}
```

`brief_path` is written by `threshold_evaluator.py` using a deterministic naming convention — the formatter agent writes to this exact path. `notifier.py` reads `brief_path` directly; no path discovery needed.

RSM Flash triggers:
- HotspotsAI `deviation_score >= 0.85` AND AeroGrid site within 100km
- EventsAI event `severity >= 4` (HIGH) in categories: Conflict, Terrorism, Unrest
- Cyber signal classified as direct AeroGrid targeting (not regional/sector-level)

No LLM. Pure threshold evaluation against config.

#### `data/audience_config.json` (new data file)

Control plane for all stakeholder delivery. New stakeholders are config, not code.

```json
{
  "rsm_apac": {
    "label": "APAC Regional Security Manager",
    "formatter_agent": "rsm-formatter-agent",
    "regions": ["APAC"],
    "products": {
      "weekly_intsum": {
        "cadence": "monday",
        "time_local": "07:00",
        "timezone": "Asia/Singapore"
      },
      "flash": {
        "threshold": {
          "hotspot_score_min": 0.85,
          "site_proximity_km": 100,
          "event_severity_min": 4,
          "categories": ["Conflict", "Terrorism", "Unrest"]
        }
      }
    },
    "delivery": {
      "channel": "email",
      "recipients": ["rsm-apac@aerowind.com"]
    }
  }
}
```

#### `data/region_country_map.json` — see definition above (new data file, create alongside seerist_collector.py in L-1)

#### `data/aerowind_sites.json` (new data file)

AeroGrid physical site locations for proximity evaluation in threshold_evaluator.

```json
{
  "sites": [
    {"name": "Kaohsiung Manufacturing Hub", "region": "APAC", "country": "TW", "lat": 22.6, "lon": 120.3, "type": "manufacturing"},
    {"name": "Shanghai Service Hub", "region": "APAC", "country": "CN", "lat": 31.2, "lon": 121.5, "type": "service"},
    ...
  ]
}
```

#### `tools/notifier.py ROUTING_DECISIONS_PATH`

Reads `output/routing_decisions.json`. For each triggered decision, reads the corresponding brief file and delivers via the configured channel.

Initial adapters: `email` only (SMTP via `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` in `.env`).
Future adapters: `teams`, `slack`, `sms` — each is a pluggable function in `notifier.py`.

Writes: `output/delivery_log.json` — append-mode delivery audit trail.

`delivery_log.json` schema (one JSON object per line, JSONL):
```json
{"timestamp": "2026-03-20T05:12:03Z", "audience": "rsm_apac", "region": "APAC", "product": "weekly_intsum", "channel": "email", "recipient": "rsm-apac@aerowind.com", "brief_path": "output/regional/apac/rsm_brief_apac_2026-03-20.md", "status": "delivered|failed", "error": null}
```

### New Agent

#### `.claude/agents/rsm-formatter-agent.md`

Model: `sonnet`

Input files (reads):
- `output/regional/{region}/seerist_signals.json`
- `output/regional/{region}/region_delta.json` (dependency: must exist; if missing, agent exits non-zero)
- `output/regional/{region}/cyber_signals.json`
- `data/company_profile.json`
- `data/aerowind_sites.json`
- `data/audience_config.json` (full path — reads the target RSM's region config)

Output:
- `output/regional/{region}/rsm_brief_{region}_{date}.md`
- `output/regional/{region}/rsm_flash_{region}_{timestamp}.md` (when triggered)

**Flash alert invocation chain:** When `threshold_evaluator.py` writes a flash-triggered decision to `routing_decisions.json`, a new tool `tools/rsm_dispatcher.py` reads `routing_decisions.json`, invokes `rsm-formatter-agent` for each undelivered triggered decision (passing the product type: `weekly_intsum` or `flash`), then invokes `notifier.py` once all briefs are written. `rsm_dispatcher.py` is the orchestrator for the RSM path — analogous to how `run-crq.md` orchestrates the board path.

**Mock mode:** In `--mock` mode, `rsm-formatter-agent` reads mock `seerist_signals.json` and a zeroed `region_delta.json`. The agent produces a full brief against mock data. Invoked by test suite as: `uv run python tools/rsm_dispatcher.py --mock --region APAC`.

**Critical design rule — machine section vs LLM section:**

The agent does NOT write the structured facts. It receives them pre-formatted by a prompt template that injects machine-computed values (EventsAI bullets, pulse delta, hotspot flags). The agent writes **only the ASSESSMENT and WATCH LIST sections** — the parts that require reasoning about AeroGrid-specific exposure.

This means:
- Facts section is deterministic (no hallucination risk, no LLM cost)
- LLM cost concentrated on the section that earns its value
- Rewrite cycles only triggered on the interpretation, not the facts

Stop hook: `jargon-auditor.py` — no cyber jargon, no SOC language, no budget advice. Exit 2 = rewrite.

---

## What Does Not Change

The following are **untouched** by this spec:

- `run-crq.md` orchestrator — no phases added or modified
- `gatekeeper-agent.md` — no changes
- `regional-analyst-agent.md` — no changes
- `global-builder-agent.md` — no changes
- `global-validator-agent.md` — no changes
- All existing pipeline tools (`geo_collector.py`, `cyber_collector.py`, etc.)
- `dashboard.html`, `board_report.pdf`, `board_report.pptx` outputs

The RSM path is additive. It reads the same signal files as the existing pipeline but does not modify them.

---

## Integration with Existing Pipeline

The RSM formatter reads `cyber_signals.json` (already written by the existing pipeline) for the Cyber section of the INTSUM. This means:

- In **mock mode**: RSM brief uses the same mock cyber fixtures as the board path
- In **live mode**: RSM brief uses the same cyber OSINT as the board path

Seerist signals are **additive** — they do not replace `geo_signals.json`. The geo collector continues to run for the board/CISO path. The RSM path uses `seerist_signals.json` as its primary physical/geo source.

---

## Scheduling

The RSM path runs on a separate cadence from the weekly pipeline batch:

| Job | Cadence | Trigger |
|-----|---------|---------|
| `seerist_collector.py` (all regions) | Every 6 hours | Cron |
| `delta_computer.py` (all regions) | After each seerist_collector run | Sequential |
| `threshold_evaluator.py` | After each delta_computer run | Sequential |
| Flash delivery (if triggered) | Immediately on threshold breach | Event-driven |
| Weekly INTSUM | Monday 05:00 UTC (formats at 05:00, delivers at 07:00 local per region) | Cron |

Scheduling is handled by a new `tools/scheduler.py` — a lightweight cron wrapper that reads job config from `data/schedule_config.json`. No external dependencies (APScheduler or Python `schedule` library).

`data/schedule_config.json` schema:

```json
{
  "jobs": [
    {
      "id": "seerist_collect_all",
      "command": "uv run python tools/seerist_collector.py {region}",
      "regions": ["APAC", "AME", "LATAM", "MED", "NCE"],
      "cron": "0 */6 * * *",
      "description": "Collect Seerist signals every 6 hours for all regions"
    },
    {
      "id": "rsm_dispatch_flash",
      "command": "uv run python tools/rsm_dispatcher.py --check-flash",
      "regions": null,
      "cron": "30 */6 * * *",
      "description": "Evaluate flash thresholds and dispatch any triggered flash alerts"
    },
    {
      "id": "rsm_dispatch_weekly",
      "command": "uv run python tools/rsm_dispatcher.py --weekly",
      "regions": null,
      "cron": "0 5 * * 1",
      "description": "Generate and deliver weekly INTSUM every Monday at 05:00 UTC"
    }
  ]
}
```

This satisfies the parked Phase F-5 "Scheduled runs" item.

---

## Mock Mode

All new tools support `--mock` flag:
- `seerist_collector.py --mock` → reads `data/mock_osint_fixtures/{region}_seerist.json`
- `threshold_evaluator.py --mock` → evaluates thresholds against mock data
- `notifier.py --mock` → writes to `output/mock_delivery/` instead of sending email

New mock fixtures needed: `{apac|ame|latam|med|nce}_seerist.json`

---

## Dependencies

- `SEERIST_API_KEY` in `.env` (for live mode)
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` in `.env` (for email delivery)
- `geopy` or `haversine` (pip) for site proximity calculation in `threshold_evaluator.py`
- Physical scenario expansion of `mock_crq_database.json` — **parked**, not required for this phase. RSM brief will surface physical events as intelligence without VaCR anchoring until the database is extended.

---

## Build Order

```
L-1  seerist_collector.py + data/region_country_map.json       ~2 hours
     + mock fixtures: {region}_seerist.json (5 regions)
L-2  delta_computer.py (incl. cold-start behavior)             ~1 hour
L-3  data/aerowind_sites.json + data/audience_config.json      ~45 min
     + data/schedule_config.json
L-4  threshold_evaluator.py                                    ~1.5 hours
     (depends on: L-1, L-2, L-3)
L-5  rsm-formatter-agent.md (weekly INTSUM variant)            ~2 hours
     (depends on: L-1, L-2, L-3)
L-6  rsm-formatter-agent.md (flash alert variant)              ~1 hour
     (depends on: L-5)
L-7  rsm_dispatcher.py (orchestrator for RSM path)             ~1 hour
     (depends on: L-4, L-5, L-6)
L-8  notifier.py (email adapter) + delivery_log.json schema    ~1 hour
     (depends on: L-7)
L-9  scheduler.py                                              ~1 hour
     (depends on: L-7, L-8)
L-10 Tests: collectors, delta, threshold, dispatcher mock run  ~2 hours
L-11 Wire into run-crq.md (optional: post-phase-6 INTSUM gen)  ~30 min
```

Total: ~13 hours

---

## Future Extensions (not in scope)

- Physical scenario expansion in `mock_crq_database.json` (VaCR for civil unrest, logistics disruption)
- Additional audience types via `audience_config.json` (CISO escalation notice, board material event notice, ops/sales impact alerts) — no new infrastructure required
- Additional delivery channels in `notifier.py` (Teams webhook, Slack, SMS)
- `data/DiscoverAI` integration for multi-event narrative threading (Seerist DiscoverAI engine)
- Per-RSM feedback loop (reply ACCURATE/OVERSTATED) feeding back into threshold calibration
