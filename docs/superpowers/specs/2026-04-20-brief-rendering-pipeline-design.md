# Brief Rendering Pipeline — Design Spec

**Date:** 2026-04-20
**Status:** Draft — pending user review
**Supersedes:** `tools/brief_data.py` single-brief static pattern; `tools/build_pptx.py` PPTX parity work; legacy CISO DOCX export; legacy RSM markdown weekly.

---

## Purpose

Wire the CRQ Design System v1.0 handoff (`docs/design/handoff/`) into the live AeroGrid pipeline as three production deliverables:

- **Board Report** — quarterly, full board audience
- **CISO Brief** — monthly, CISO + security leadership
- **RSM Weekly INTSUM** — weekly, Regional Security Manager + country leads

The handoff is the architecture, not a reference. Templates, CSS, DOM structure, Playwright settings — all inherited as-is. Data flow, synthesis, and CLI are new.

## Scope

- **In scope:** Three Jinja2 templates, shared design-system CSS, Pydantic data contracts, single `build_pdf.py --brief` CLI, RSM live-data synthesizer (joins + agent narrative), FastAPI integration for the Reports tab.
- **Out of scope this spec (future work):**
  - Board quarterly aggregator (static mock data for now)
  - CISO monthly cross-regional synthesizer (static mock data for now)
  - Context tab UI for editing site registry (separate spec — this design defines the schema it will inherit)
  - PPTX editable-slide output for any of the three briefs
  - Daily + flash RSM derivatives

## Design Principles

1. **Handoff is byte-equivalent ground truth.** Templates mirror the DOM of the golden-reference HTML files. Any structural divergence means a CSS rule breaks silently.
2. **Data contracts are spec.** Pydantic models define what each template consumes. Synthesizers and agents target those models; templates render fields with no business logic.
3. **Output drives schema.** The RSM template's data requirements define the site registry schema that the Context tab (separate workstream) will inherit.
4. **Separation of concerns:** joins are math (Python), narrative is voice (LLM). Neither tries to do the other's job.
5. **One rendering path.** Single `render_pdf()` function. Three brief types pick template + data module; everything else is shared.

## Architecture

Three explicit layers.

### Layer 1 — Collect (existing, no change)

Regional intelligence lands in:
- `output/regional/{region}/osint_signals.json` — Seerist + Firecrawl + Tavily signals per region
- `output/regional/{region}/sections.json` — analyst-authored narrative blocks
- `output/regional/{region}/signal_clusters.json` — clustered event groupings
- `output/pipeline/last_run_log.json` — pipeline run metadata
- `data/aerowind_sites.json` — per-site context registry

No changes to this layer for this spec.

### Layer 2 — Synthesize (new)

Per-brief data module produces a strictly-typed `BriefData` Pydantic model. The model IS the contract — template consumes it, synthesizer produces it, agent validates against it.

```
tools/briefs/
  models.py                  # BoardBriefData, CisoBriefData, RsmBriefData + nested models
  data/
    __init__.py
    board.py                 # load_board_data(quarter) -> BoardBriefData    [static mock]
    ciso.py                  # load_ciso_data(month)   -> CisoBriefData     [static mock]
    rsm.py                   # load_rsm_data(region, week) -> RsmBriefData  [live]
  joins.py                   # pure functions: proximity, pattern_match, actor_match, calendar_ahead
```

**Board + CISO (this pass):** the `data/board.py` and `data/ciso.py` modules return hardcoded `BriefData` matching the handoff's realistic mock content. When quarterly / monthly synthesizers are built later, only these modules change.

**RSM (live):**
1. Load per-site context for the region from `aerowind_sites.json`
2. Load this-week signals from `output/regional/{region}/osint_signals.json`
3. Run deterministic joins: proximity (coords + poi_radius), pattern (relevant_attack_types × signal.attack_type), actor (threat_actors_of_interest × signal.perpetrator), calendar (upcoming window filter)
4. Rank joined signals per site by hit count + severity + freshness
5. Invoke `rsm-formatter-agent` to produce narrative fragments: `headline`, per-site `standing_notes_synthesis`, per-group `pattern_framing`, per-evidence-entry `why_it_is_here`
6. Agent output is JSON validated against the narrative sub-schema
7. Merge computed data + narrative into `RsmBriefData`

### Layer 3 — Render (new, thin)

One function, fully shared across briefs:

```python
async def render_pdf(
    brief: Literal["board", "ciso", "rsm"],
    data: BriefData,
    out_path: Path,
) -> None:
    template = jinja_env.get_template(f"{brief}.html.j2")
    html = template.render(data=data)
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        f.write(html.encode("utf-8"))
        html_path = Path(f.name)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(f"file://{html_path}")
        await page.wait_for_function("document.fonts.ready")
        await page.pdf(
            path=out_path,
            format="A4",
            print_background=True,            # REQUIRED — severity fills disappear without it
            prefer_css_page_size=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        await browser.close()
    html_path.unlink()
```

The Playwright flags (`print_background`, `prefer_css_page_size`, `wait_for document.fonts.ready`) are non-negotiable — they're specified in the handoff README and guarantee fidelity.

## File Layout

```
tools/
  build_pdf.py                        # CLI entry — dispatches to renderer
  briefs/
    __init__.py
    models.py                         # Pydantic contracts (all three brief types)
    renderer.py                       # render_pdf() + Jinja2 env + Playwright wrapper
    templates/
      board.html.j2                   # mirrors docs/design/handoff/Board Report Q2 2026.html
      ciso.html.j2                    # mirrors docs/design/handoff/CISO Brief April 2026.html
      rsm.html.j2                     # mirrors docs/design/handoff/RSM Weekly INTSUM MED.html
    data/
      __init__.py
      board.py                        # static mock → BoardBriefData
      ciso.py                         # static mock → CisoBriefData
      rsm.py                          # live pipeline → RsmBriefData
    joins.py                          # pure deterministic join functions

static/design/styles/
  tokens.css                          # copied verbatim from handoff
  board.css
  ciso.css
  rsm.css

tests/briefs/
  test_models.py                      # Pydantic validation
  test_joins.py                       # deterministic join functions
  test_rsm_data.py                    # full RSM synthesizer with mock signals
  test_renderer.py                    # renders template + fixture, diff against handoff HTML
  fixtures/
    rsm_med_w17.json                  # frozen RsmBriefData matching handoff
    board_q2_2026.json                # frozen BoardBriefData matching handoff
    ciso_apr_2026.json                # frozen CisoBriefData matching handoff
```

## Data Contracts

Defined in `tools/briefs/models.py`. All models inherit from a common `BriefData` base with shared fields (cover metadata, classification, preparer, issue date).

### `RsmBriefData` (most detailed — drives the context schema)

Top-level:
- `cover: CoverMeta` — region, week_of, issued_at, classification, prepared_by, distribution[]
- `admiralty_physical`, `admiralty_cyber` — graded strings
- `headline: str` — analyst-voice, LLM-produced
- `baseline_strip: list[CountryPulse]` — country × pulse × forecast × note
- `top_events: list[RankedEvent]` — ranked by site relevance
- `cyber_strip: list[CyberStripItem]` — kind + text + ref
- `baselines_moved: list[BaselineDelta]`
- `reading_guide: list[TocEntry]`
- `sites: list[SiteBlock]` — crown-jewel + primary (ordered by tier, then joined-hit count)
- `regional_cyber: RegionalCyberPage`
- `secondary_sites: list[SecondarySite]`
- `minor_sites: list[MinorSiteRow]`
- `evidence_physical: list[PhysicalEvidence]`
- `evidence_cyber: list[CyberEvidence]`

`SiteBlock`:
- Identity: `id, name, tier, country, seerist_country_code, coordinates, capital_distance_km`
- Personnel: `personnel.total, .expat, .contractors`, `country_lead`
- Criticality: `criticality_drivers, downstream_dependency, asset_type, sector, status`
- Environment: `host_country_risk_baseline, last_incident, standing_notes`
- Seerist join keys: `seerist_poi_radius_km, relevant_seerist_categories, threat_actors_of_interest, relevant_attack_types`
- Cyber join keys: `ot_stack, site_cyber_actors_of_interest`
- Computed (this-week): `baseline (pulse, forecast, days_since_incident, admiralty), proximity_hits, pattern_hits, actor_hits, calendar_ahead, cyber_callout`
- Narrative (LLM): `standing_notes_synthesis` (optional override of static standing_notes for weekly context)

The join key fields + Environment fields + People fields are exactly the schema the Context tab will inherit.

### `BoardBriefData`
Covers: `cover`, `state_of_risk_line`, `posture_shift`, `board_takeaways[5]`, `delta_bar[5 regions]`, `key_developments[5]`, `also_tracking[3]`, `watch_next[3]`, `matrix_dots[8]`, `matrix_headline`, `matrix_bottom_line`, `scenarios[3]`, `methodology`, `end_matter`.

### `CisoBriefData`
Covers: `cover`, `state_of_risk_line`, `posture`, `ciso_takeaways[3]`, `regions_grid[5]`, `cross_regional_items[4]`, `coupling_strip` (physical + cyber tracks + summary), `cyber_surface` (sector / actor / vulnerability bundles), `cyber_physical_join_page` (facts + timeline + read), `scenarios[4 with delta ribbons]`, `evidence_physical[]`, `evidence_cyber[]`.

All fields strictly typed. No `dict[str, Any]` escape hatches.

## Agent Change: `rsm-formatter-agent`

Current: produces markdown brief.
New: produces JSON fragment strictly matching the `RsmNarrativeFragment` sub-schema.

**Input:** computed `RsmBriefData` with `headline`, `standing_notes_synthesis`, `pattern_framing`, `evidence_why_lines` left null.
**Output:** JSON filling those fields.
**Stop hook:** validates output against `RsmNarrativeFragment` schema; validates jargon filter + site discipline + admiralty attribution (existing hooks, unchanged).

The agent's persona ("Strategic Geopolitical & Cyber Risk Analyst") stays. What changes is the output format — structured JSON instead of free markdown. The persona guidance and stop hooks already enforce voice quality; now voice lands in specific, bounded fields.

Markdown output for daily + flash briefs is unchanged this spec (those cadences aren't re-designed yet).

## CLI

```
uv run python tools/build_pdf.py --brief rsm   --region MED                    --out output/deliverables/rsm_med_2026-W17.pdf
uv run python tools/build_pdf.py --brief board --quarter 2026Q2                --out output/deliverables/board_q2_2026.pdf
uv run python tools/build_pdf.py --brief ciso  --month 2026-04                 --out output/deliverables/ciso_apr_2026.pdf
```

Each sub-command:
1. Loads the appropriate data via `tools.briefs.data.{brief}`
2. Validates as `{Brief}BriefData`
3. Calls `render_pdf(brief, data, out)`

Flags specific to each brief are declared per-sub-command.

## FastAPI Integration

New endpoints, following the `source_librarian` pattern:

```
POST /api/briefs/{brief}/render           body: {region?, quarter?, month?}   → {run_id}
GET  /api/briefs/{brief}/status/{run_id}                                      → {state, progress}
GET  /api/briefs/{brief}/latest           ?region=MED (rsm) | quarter=2026Q2  → {pdf_url, generated_at, data_summary}
```

Reports tab in the app lists the three brief types. Each brief shows:
- Latest-rendered timestamp
- Download button
- Inline PDF preview (via `<object>` or iframe)
- Regenerate button (for RSM, per region)

Same component chrome as the source librarian reading-list block so the Reports tab stays visually consistent.

## Regression Strategy

**Golden-reference fixtures.** The handoff HTML at `docs/design/handoff/*.html` is the byte-equivalent target. Tests:

1. **Template shape test (`test_renderer.py::test_template_matches_handoff`):** for each brief, render the template with its fixture data, normalise whitespace, diff against the handoff HTML. Any structural change to the template or data model that drifts from the handoff fails here. This runs every CI.

2. **Playwright PDF test (manual, not CI):** render each brief to PDF, compare pixel-wise against a committed reference PDF. Used to catch font, CSS, or Chromium rendering drift. Run before releases, not every commit (expensive).

3. **Pydantic validation (`test_models.py`):** validates that `RsmBriefData` accepts the fixture and rejects known-bad shapes.

4. **Join function tests (`test_joins.py`):** pure-function tests for proximity / pattern / actor / calendar joins against synthetic signals.

## Deprecations

This spec supersedes (deletions happen in the implementation plan after templates are proven):

- `tools/build_pptx.py` — handoff is PDF-native; PPTX parity from last session is not carried forward
- `tools/brief_data.py` — single-brief static-dict pattern replaced by per-brief data modules
- CISO DOCX export — PDF supersedes for monthly
- RSM weekly markdown — PDF pack supersedes for weekly cadence (daily + flash markdown unchanged)

The handoff HTML stash at `docs/design/handoff/` is NEVER deprecated — it's the byte-equivalent target forever.

## Dependencies & Assumptions

- **IBM Plex Sans** loaded from Google Fonts with weights 400/500/600/700. If the environment is air-gapped, self-host the same four weights with `@font-face` pointing at `static/design/fonts/`.
- **Playwright Chromium** installed and up to date. Font-ready wait + `print_background=True` + `prefer_css_page_size=True` are required.
- **`data/aerowind_sites.json`** needs its schema extended with the fields listed in `RsmBriefData.SiteBlock` before the RSM brief can render with live data. The template's data requirements define the exact fields needed.
- **`rsm-formatter-agent`** frontmatter updated to reflect JSON output; stop hook extended to validate schema.

## Open Questions (for the implementation plan)

- Do templates use Jinja2 macros for shared components (pill, pulse, meta-rail), or inline everything per brief? Lean: macros in `tools/briefs/templates/_partials.html.j2` for the truly shared atoms only (pill, sev-chip, meta-rail). Block-level composition stays inline per brief.
- Do we pre-generate and cache PDFs server-side, or render on demand per request? Lean: async render + cache, following the source-librarian pattern.
- How does the app poll-for-status UX look for brief rendering? Lean: reuse the source-librarian polling pattern (spinner, auto-refresh on completion).
- Should `render_pdf()` live in `tools/briefs/renderer.py` or `tools/pdf_renderer.py` (shared with future slide-agent integration)? Lean: in `tools/briefs/renderer.py` for now; lift to shared later if a second PDF-emitting feature appears.

These are decisions for the plan, not the design.

## What Perfect Implementation Looks Like

1. Running `uv run python tools/build_pdf.py --brief rsm --region MED` produces a PDF indistinguishable from `docs/design/handoff/RSM Weekly INTSUM MED.html` printed through the same Playwright settings — but with live data for MED's current week.
2. Running the same command for `--brief board` and `--brief ciso` produces polished PDFs from static mock data (ready to replace when the Board and CISO synthesizers get built).
3. All three briefs render from the exact same `render_pdf()` function, differ only in template + data module.
4. Pydantic validation catches any malformed data before rendering.
5. The `rsm-formatter-agent` produces schema-conformant JSON; the stop hook rejects anything else.
6. The Reports tab in the app lists all three briefs with preview, download, and regenerate controls.
7. The Context tab (separate workstream) reads the `SiteBlock` schema straight out of `tools/briefs/models.py` — no re-definition.
8. Swapping the CRQ Design System v1.1 later means editing CSS files in `static/design/styles/` — nothing else moves.
