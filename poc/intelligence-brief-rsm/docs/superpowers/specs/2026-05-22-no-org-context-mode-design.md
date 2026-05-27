# Region-Guided Intelligence Mode (no-org-context) — Design

**Date:** 2026-05-22
**Slice:** `poc/seerist-rsm` (MED carve of the AeroGrid CRQ pipeline)
**Status:** Approved for implementation (revised after independent design review)

## Goal

Add a pipeline mode in which **the region is the only scoping input**. The
pipeline gathers intelligence for a region's risk landscape (NCE, MED, …) with
**zero org grounding** — no sites, facilities, personnel, footprint, audience,
notable dates, previous incidents, or site-proximity. The output is a genuinely
company-agnostic brief.

### Why (purposes)

1. **Prospect / demo brief** — a shareable regional risk brief for a prospect
   who has not shared their site footprint. Must be safe to send externally.
2. **Pipeline / signal testing** — exercise the Seerist + OSINT collection and
   brief-building path in isolation, without org grounding.

Both reduce to: *region-guided intelligence, no org context.*

### Scope

In scope: the mode end-to-end — a switch threaded through collection,
proximity, manifest building, the analyst/formatter prompts, validation, and
rendering; a renamed exposure section; brand parameterization; and tests.

Out of scope (next spec): the `/install` → `/create-skill` → `/setup` wizard
that will drive this and other toggles. This mode exposes a clean CLI for that
future layer.

## Where org context enters today (verified against code)

Org context reaches the model through **three input surfaces**, not one. The
mode must close all three; emptying the manifest alone is insufficient.

| Surface | Evidence | Mode behavior |
|---|---|---|
| `poi_alerts` in `seerist_signals.json` (the analyst prompt's *authoritative* POI source) | `seerist_collector.py:291-328` builds it from `aerowind_sites.json` (live); `data/mock_osint_fixtures/med_seerist.json:125` ships a baked-in `"facility": "Casablanca Wind Farm Operations"` | Live: skip the facility POI block → `poi_alerts == []`. Mock: strip `data["poi_alerts"]` in `_mock_collect`. |
| `poi_proximity.json` | `poi_proximity.py:20` reads sites. Note: analyst prompt says *do NOT read* this file — so skipping it is belt-and-suspenders, not the real lever | Orchestrator skips the `poi_proximity.py` step. |
| Manifest (`build_rsm_inputs`) | `rsm_input_builder.py:158-203` injects `site_registry`, `notable_dates`, `previous_incidents`, `poi_proximity`, `audience_config`; `manifest_summary` emits the "allowed site names" block | `include_org_context=False` empties these, forces the three org fallbacks on, adds `org_context_included: false`, omits the allowlist block. |

Confirmed during review:
- `data/company_profile.json` is **not consumed** in this slice's
  provider-agnostic path — only a path constant in `config.py:9`; the prompts do
  not read it. (The optional Claude wrapper `.claude/agents/rsm-formatter-agent.md`
  is a latent consumer; out of scope here. One-line caveat only.)
- `data/cyber_watchlist.json` is **global** threat intel
  (`seerist_collector.py` watchlist load; `rsm_input_builder.py:168`), not org
  footprint — retained in both modes.

## The switch

- **Function parameter** `include_org_context: bool = True` on
  `build_rsm_inputs()` — the load-bearing manifest switch. Default preserves
  current behavior exactly.
- **Collector parameter** `no_org_context: bool = False` threaded through
  `collect()` → `_live_collect()` / `_mock_collect()`. Note: `seerist_collector.py`
  `main()` parses `sys.argv` by hand (`:416-432`), not argparse — the flag is
  added in that style: `no_org = "--no-org-context" in args`.
- **CLI flag** `--no-org-context` on `tools/seerist_collector.py` and
  `tools/poc_runner.py` (argparse `:270-296`). `poc_runner.phase_collect` must
  (a) append `--no-org-context` to the collector subprocess call (`:76`),
  (b) **conditionally skip** the `poi_proximity.py` step (`:83`), and
  (c) pass `include_org_context=False` to its `build_rsm_inputs` call (`:98`).

## Manifest behavior when off

`build_rsm_inputs(region, cadence, include_org_context=False, brand_label=...)`:

- `site_registry`, `notable_dates`, `previous_incidents` → `[]`
- `poi_proximity` → `None`
- `optional["aerowind_sites"]`, `optional["audience_config"]`,
  `optional["poi_proximity"]` → `None`; `fallback_flags` for those → `True`;
  existing `fallback_instructions` fire (generic language)
- new fields `org_context_included: false` and `brand_label: <value>`
- `manifest_summary()` prints a banner near the top:
  > `REGION-GUIDED MODE — no org context. The brief covers the {REGION}`
  > `regional risk landscape only. Do NOT name specific sites, facilities, or`
  > `personnel. Use the REGIONAL EXPOSURE section for region-level exposure.`
- the "Allowed site names / ANTI-HALLUCINATION" block is **omitted**.

## REGIONAL EXPOSURE section (replaces AEROWIND EXPOSURE in this mode)

The brief's exposure section is renamed when `org_context_included` is false.

- **Formatter prompt** (`prompts/rsm_formatter_daily.md:49-54`): add a
  region-guided variant. When the manifest has `org_context_included: false`,
  the section header is `█ REGIONAL EXPOSURE` and its body is a region-level
  summary (which countries / sub-areas in the region are hottest, drawn from
  `analytical.pulse` + `risk_ratings`), with **no `▪` site rows**. The header
  band line uses `{brand_label}` instead of the literal `AEROWIND`.
- **Analyst prompt** (`prompts/rsm_regional_analyst_daily.md`): add a short
  region-guided note — when `org_context_included` is false, `poi_alerts` is
  empty by design; produce region-level claims and do not emit `geographic_resonance="facility"`
  claims or facility names.
- **Validator** (`tools/validate_brief.py`): make the exposure entry in
  `REQUIRED_SECTIONS` mode-aware — expect `REGIONAL EXPOSURE` when the manifest
  has `org_context_included: false`, else `AEROWIND EXPOSURE`. `_check_site_discipline`
  already passes cleanly with an empty `site_registry` (`:138` short-circuits on
  the falsy registry — verified), so no change needed there.
- **Renderer** (`tools/render_brief_html.py`): no section-branch change needed —
  `is_exposure` keys off the literal `"AEROWIND EXPOSURE"` (`:278`), so
  `REGIONAL EXPOSURE` naturally falls through to the prose branch (`:297`), and
  the template's `"EXPOSURE" in section.header` test (`rsm_email.html.j2:76`)
  renders the prose body via the `site_blocks`-empty path (`:82-84`). Verified.

## Brand parameterization

Today the brand is hardcoded and **hard-enforced** by the renderer
(`render_brief_html.py:22` `_HEADER_RE = ^AEROWIND // (\S+) DAILY // (\S+)$`),
the template (`rsm_email.html.j2:17,101,102`), the formatter prompt (`:42`), and
the subject (`poc_runner.py:250`). A region-guided brief stamped "AEROWIND // …
PoC v1" cannot be shared with a prospect. We parameterize the brand:

- A single `brand_label` value, default `"AEROWIND"` (preserves current
  output). In `--no-org-context` mode it defaults to a neutral
  `"REGIONAL RISK INTELLIGENCE"`; `--brand "<label>"` overrides in any mode.
- `brand_label` is carried in the manifest (so the formatter writes the right
  header band) via `build_rsm_inputs(brand_label=...)`.
- `render_brief_html.py`: widen `_HEADER_RE` to capture the brand,
  `^(?P<brand>.+?) // (?P<region>\S+) DAILY // (?P<date>\S+)$`; `_parse_brief`
  returns `brand`; `render()` passes `brand` into the template. The error
  message at `:222` becomes brand-agnostic ("missing header band").
- `rsm_email.html.j2`: lines 17, 101 use `{{ brand }}`; the line-102 watermark
  becomes a generic, configurable footnote (drop the "PoC v1 — Seerist live ·
  MED region" specifics; use a neutral one-liner).
- `poc_runner.py`: `--brand` arg; subject (`:250`) uses the resolved brand;
  derive the no-org default as above.

## Error handling

- Defaults (`include_org_context=True`, `no_org_context=False`,
  `brand_label="AEROWIND"`) leave every existing call path byte-for-byte
  unchanged.
- In no-org mode, missing org files are irrelevant (the mode skips them), so
  `build_rsm_inputs` still raises `FileNotFoundError` only for the genuinely
  required `osint_signals` / `data.json`.

## Testing

Extend `tests/`; reuse the MED fixture.

1. **Builder, mode off:** `build_rsm_inputs("MED","daily",include_org_context=False)`
   → `site_registry==[]`, `notable_dates==[]`, `previous_incidents==[]`,
   `poi_proximity is None`, `org_context_included is False`, the three org
   `fallback_flags` are `True`, `brand_label` present.
2. **Builder regression:** default call unchanged — `org_context_included is
   True`, registry populated, `brand_label=="AEROWIND"`.
3. **manifest_summary:** no-org manifest contains the region-guided banner and
   does **not** contain "Allowed site names".
4. **Collector strip (the key leak test):** collector in no-org mock mode →
   output `poi_alerts == []` **and** the string "Casablanca Wind Farm
   Operations" is absent from the written `seerist_signals.json`.
5. **Validator, region-guided:** a brief with `█ REGIONAL EXPOSURE` + a
   manifest with `org_context_included: false` passes `validate_brief`; a brief
   still using `█ AEROWIND EXPOSURE` against that manifest fails (mode mismatch).
6. **Renderer, region-guided:** `render()` on a `REGIONAL EXPOSURE` brief with a
   neutral `brand_label` produces HTML whose header band shows the neutral brand
   and contains no "AEROWIND" and no "PoC v1".

Verification commands:

```
cd poc/seerist-rsm
uv run pytest tests/ -q
uv run python tools/seerist_collector.py MED --mock --no-org-context
uv run python tools/poc_runner.py MED 2026-05-22 --collect --no-org-context
uv run python tools/rsm_input_builder.py MED daily        # default path unchanged
```

After the runner step, inspect
`output/poc/med/2026-05-22/_rsm_manifest_daily.json` (`org_context_included:
false`, empty `site_registry`, `brand_label` set) and
`output/regional/med/seerist_signals.json` (`poi_alerts: []`, no facility name).

## Files touched

`tools/seerist_collector.py`, `tools/rsm_input_builder.py`,
`tools/poc_runner.py`, `tools/validate_brief.py`, `tools/render_brief_html.py`,
`tools/briefs/templates/rsm_email.html.j2`, `prompts/rsm_formatter_daily.md`,
`prompts/rsm_regional_analyst_daily.md`, plus tests under `tests/`.
