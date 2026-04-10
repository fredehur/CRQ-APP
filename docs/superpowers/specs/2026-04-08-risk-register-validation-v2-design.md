# Risk Register Validation V2 — Design Spec

**Date:** 2026-04-08
**Status:** Approved

---

## Problem

The current validation pipeline has two structural failures:

1. **Queries are too narrow at search time** — OT/SCADA/wind terms baked into queries cause misses. "Ransomware industrial control systems" is equally relevant but never surfaced. Context should be applied at extraction, not search.

2. **No scope awareness** — figures from SMB incidents ($500) are treated as equal evidence to enterprise-scale figures. No per-source context label tells the user whether a source is relevant because of the asset type or because of company scale.

3. **Number formatting** — `toLocaleString()` without locale produces `$5.200.000` on European systems.

---

## Solution

### Search Strategy: Three Tracks

**Track 1 — Broad sector query per scenario (replaces Phase 2 OSINT)**
One moderate-breadth query per scenario per dimension. Includes industry + scenario type, omits asset-specific OT terms (those are applied at extraction tagging):
- Financial: `"{scenario} financial cost energy sector renewable operator USD 2024 2025"`
- Probability: `"{scenario} incident rate probability energy sector 2024 2025 annual"`

**Track 2 — Known source refresh (replaces Phase 1)**
For each source in `validation_sources.json` matching the scenario tags, query its domain for the most recent data. Unchanged from current Phase 1 logic.

**Track 3 — Version check (new)**
For each source in `validation_sources.json`, check if a newer edition exists than `edition_year`. Query: `"{source_name} 2025 annual report"`. Runs once per validation run (not per scenario). Returns `version_checks[]` at top level of output.

### Context Tagging at Extraction

Haiku extraction prompts add a `context_tag` field to each figure:
- `"asset_specific"` — source content mentions OT/ICS/SCADA/industrial/wind/turbine
- `"company_scale"` — source content mentions enterprise/large org/>1000 employees/sector-wide
- `"both"` — matches both
- `"general"` — neither (still included, lower weight for Sonnet reasoning)

Tagged at extraction time from source content, not inferred from which query found the figure.

### Plausibility Flag

`scale_floor_usd` = `max(100_000, min(all scenario VaCR figures in register) * 0.05)`

Any extracted figure below `scale_floor_usd` → `smb_scale_flag: true`. Not rejected — included with flag. Sonnet sees flag and weights accordingly.

### INSUFFICIENT Definition

INSUFFICIENT only when: fewer than 2 total quantitative sources found across both tracks. If Track 1 finds figures but no OT-specific figures exist for a scenario, the output notes: `"asset_context_note": "No OT/asset-specific quantitative data found — company-scale sources only."` Verdict proceeds on company-scale sources.

### Number Formatting Fix

All `toLocaleString()` calls in app.js that format USD values → `toLocaleString('en-US')`.

---

## Output Schema Changes

```json
{
  "register_id": "wind_power_plant",
  "validated_at": "...",
  "version_checks": [
    {
      "source_id": "ibm-cost-data-breach",
      "name": "IBM Cost of a Data Breach Report",
      "edition_year": 2024,
      "newer_version_found": true,
      "newer_year": 2025,
      "url": "https://..."
    }
  ],
  "scenarios": [
    {
      "scenario_id": "WP-001",
      "scenario_name": "System intrusion",
      "asset_context_note": "",
      "financial": {
        "vacr_figure_usd": 5200000,
        "verdict": "challenges",
        "benchmark_range_usd": [8000000, 18000000],
        "registered_sources": [
          {
            "name": "Dragos ICS/OT Year in Review 2024",
            "url": "...",
            "figure_usd": 12000000,
            "context_tag": "asset_specific",
            "smb_scale_flag": false,
            "note": "...",
            "raw_quote": "..."
          }
        ],
        "new_sources": [
          {
            "name": "...",
            "url": "...",
            "figure_usd": 4500000,
            "context_tag": "company_scale",
            "smb_scale_flag": false,
            "note": "...",
            "raw_quote": "..."
          }
        ],
        "recommendation": "..."
      },
      "probability": { ... }
    }
  ]
}
```

Sources are split into `registered_sources` (Track 2 — known registry) and `new_sources` (Track 1 — discovered this run).

---

## UI Changes

### Number formatting
All VaCR/benchmark dollar displays use `en-US` locale → `$5,200,000`.

### Two-box source display (per scenario expanded row)
Replace flat source list with two labeled boxes:
- **Registered Sources** — sources from `validation_sources.json`. Shows name, figure, context tag badge. If `version_checks` shows a newer edition → amber `[NEW EDITION]` badge.
- **New Sources** — sources found in Track 1. Shows title (linked), figure, context tag badge, SMB flag if triggered.

### Context tag badges
- `[OT / Asset]` — blue
- `[Enterprise Scale]` — purple
- `[Both]` — green
- `[General]` — grey

---

## Files Changed

| File | Change |
|---|---|
| `tools/register_validator.py` | Refactor queries (Track 1), context tagging in extraction, plausibility flag, Track 3 version check, split output into registered_sources/new_sources |
| `data/validation_sources.json` | Add `edition_year` integer to each source |
| `.claude/hooks/validators/register-validation-auditor.py` | Validate new schema fields |
| `static/app.js` | Number format fix; two-box source UI; context tag badges; version check display |
| `static/index.html` | CSS for context tag badges |
