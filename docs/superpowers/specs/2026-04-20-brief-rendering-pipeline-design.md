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

### Layer 1 — Collect (existing, but with an input-schema requirement)

The RSM brief consumes:
- `data/aerowind_sites.json` — per-site context registry (schema extension required — see below)
- `output/regional/{region}/osint_signals.json` — per-signal event records

**Required `osint_signals.json` per-item schema** (joins depend on this):
```
{
  "id": str,
  "timestamp": ISO8601,
  "coordinates": { "lat": float, "lon": float },
  "country": ISO-3166 alpha-2,
  "category": one of {terrorism, unrest, conflict, crime, transportation, health, disaster, travel, elections},
  "attack_type": seerist attackType id | null,
  "perpetrator": seerist perpetrator id | null,
  "severity": 0–10,
  "headline": str,
  "source": { "publisher": str, "url": str | null, "admiralty": grade },
  "sector": seerist sector id | null
}
```

If the current collector produces anything less, the implementation plan must include a collector-layer extension task to fill the gaps.

`sections.json` and `signal_clusters.json` are **not consumed** by the RSM brief. They remain available for the Overview tab and regional-analyst flows.

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
5. Invoke `rsm-weekly-synthesizer` to produce narrative fragments: `headline`, per-site `standing_notes_synthesis`, per-group `pattern_framing`, per-evidence-entry `why_it_is_here`
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

Defined in `tools/briefs/models.py`. All models inherit from a common `BriefData` base with shared fields (cover metadata, classification, preparer, issue date). Every field strictly typed — no `dict[str, Any]` escape hatches.

### Provenance layering

Models are split by provenance so tests can mock each layer independently and downstream consumers (Context tab, agent) can take the slice they need.

- **Static** — values that live in `data/aerowind_sites.json` or per-brief YAML/JSON config. Owned by humans (Context tab edits these). Stable across weeks.
- **Computed** — values produced by the deterministic join and ranking pass. Owned by Python. Re-computed every render.
- **Narrative** — short analyst-voice prose fragments. Owned by the LLM. Re-generated every render.

Render-ready composite models (e.g. `SiteBlock`) combine all three.

### `RsmBriefData` — top-level

- `cover: CoverMeta` — region, week_of, issued_at, classification, prepared_by, distribution[]
- `admiralty_physical`, `admiralty_cyber` — graded strings (static per-cycle)
- `headline: str` — narrative
- `baseline_strip: list[CountryPulse]` — country × pulse × forecast × note (computed)
- `top_events: list[RankedEvent]` — ranked by site relevance (computed)
- `cyber_strip: list[CyberStripItem]` — kind + text + ref (computed)
- `baselines_moved: list[BaselineDelta]` — computed against last week
- `reading_guide: list[TocEntry]` — computed from site count + tier mix
- `sites: list[SiteBlock]` — crown-jewel + primary, ordered by tier then joined-hit count
- `regional_cyber: RegionalCyberPage` — static cyber watchlist + computed this-week items + narrative standing notes
- `secondary_sites: list[SecondarySite]` — inline blocks
- `minor_sites: list[MinorSiteRow]` — table rows
- `evidence_physical: list[PhysicalEvidence]` — E-prefix entries
- `evidence_cyber: list[CyberEvidence]` — C-prefix entries

### `SiteContext` (static — lives in `aerowind_sites.json`)

**Migration constraint:** `data/aerowind_sites.json` is already consumed by `tools/poi_proximity.py`, `tools/seerist_collector.py`, `tools/threshold_evaluator.py`, `tools/rsm_input_builder.py`, `tools/build_context.py`, and `.claude/hooks/validators/rsm-brief-context-checks.py`. These access flat keys (`site["lat"]`, `site["lon"]`, `site["poi_radius_km"]`, `site["criticality"]`, `site["personnel_count"]`, `site["expat_count"]`, `site["feeds_into"]`, `site["previous_incidents"]`, `site["notable_dates"]`, `site["site_lead"]`, etc.).

**Rule:** `SiteContext` is an **additive superset** — existing flat fields stay flat; new RSM-brief fields are added alongside; nested shapes the template needs (`coordinates`, `personnel`, `last_incident`) are **computed properties** on the Pydantic model, not stored shapes. Existing consumers continue to work without edits.

```
class SiteContext(BaseModel):
    model_config = ConfigDict(extra="ignore")   # tolerate unknown existing fields

    # Existing flat fields — preserved
    site_id: str
    name: str
    region: Literal["APAC", "AME", "LATAM", "MED", "NCE"]
    country: str                                 # ISO-3166 alpha-2 (existing convention)
    lat: float
    lon: float
    poi_radius_km: int
    type: str
    subtype: str | None = None
    shift_pattern: str | None = None
    criticality: Literal["crown_jewel", "major", "standard"]
    personnel_count: int
    expat_count: int
    produces: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    feeds_into: list[str] = Field(default_factory=list)
    customer_dependencies: list[dict] = Field(default_factory=list)
    previous_incidents: list[dict] = Field(default_factory=list)
    notable_dates: list[dict] = Field(default_factory=list)
    site_lead: dict                              # {name, phone}
    duty_officer: dict | None = None
    embassy_contact: dict | None = None

    # New additive fields — RSM brief pipeline
    tier: Literal["crown_jewel", "primary", "secondary", "minor"] | None = None
    criticality_drivers: str = ""
    downstream_dependency: str = ""
    asset_type: Literal["wind_farm", "substation", "ops_center",
                        "manufacturing", "office", "port"] | None = None
    sector: int | None = None
    status: Literal["active", "commissioning", "decommissioned", "planned"] = "active"
    seerist_country_code: str | None = None      # defaults to .country at read
    contractors_count: int = 0
    country_lead: dict | None = None             # {name, email, phone} — falls back to site_lead
    host_country_risk_baseline: Literal["low", "elevated", "high"] = "elevated"
    standing_notes: str = ""
    relevant_seerist_categories: list[str] = Field(default_factory=list)
    threat_actors_of_interest: list[int] = Field(default_factory=list)
    relevant_attack_types: list[int] = Field(default_factory=list)
    ot_stack: list[dict] | None = None           # [{vendor, product, version}]
    site_cyber_actors_of_interest: list[int] | None = None

    # Computed properties — shapes the RSM template needs
    @computed_field
    @property
    def coordinates(self) -> Coordinates:
        return Coordinates(lat=self.lat, lon=self.lon)

    @computed_field
    @property
    def seerist_poi_radius_km(self) -> int:
        return self.poi_radius_km

    @computed_field
    @property
    def resolved_tier(self) -> Literal["crown_jewel", "primary", "secondary", "minor"]:
        if self.tier:
            return self.tier
        # Default mapping from legacy `criticality`
        return {"crown_jewel": "crown_jewel",
                "major": "primary",
                "standard": "secondary"}[self.criticality]

    @computed_field
    @property
    def personnel(self) -> Personnel:
        return Personnel(total=self.personnel_count,
                         expat=self.expat_count,
                         contractors=self.contractors_count)

    @computed_field
    @property
    def resolved_country_lead(self) -> dict:
        return self.country_lead or {**self.site_lead, "email": None}

    @computed_field
    @property
    def last_incident(self) -> dict | None:
        if not self.previous_incidents:
            return None
        return sorted(self.previous_incidents, key=lambda i: i.get("date", ""))[-1]
```

Templates read the computed properties (`site.context.coordinates.lat`, `site.context.personnel.total`, `site.context.resolved_tier`). Existing consumers continue reading flat fields. The Context tab edits the full record — stored fields + new fields — and respects the invariant that renames are additions, not replacements.

This is the exact schema the Context tab (separate workstream) will edit. Exported as JSON Schema for the frontend to consume.

### `SiteComputed` (this-week joins — produced by `tools/briefs/joins.py`)

```
class SiteComputed:
    baseline: SiteBaseline                   # pulse, forecast, days_since_incident, admiralty
    proximity_hits: list[JoinedEvent]        # events within seerist_poi_radius_km
    pattern_hits: list[JoinedEvent]          # relevant_attack_types × country / 30d
    actor_hits: list[JoinedEvent]            # threat_actors_of_interest × signals
    calendar_ahead: list[CalendarItem]       # next 14 days
    cyber_callout_computed: CyberCalloutComputed | None  # event stub + site match; narrative filled later
```

### `SiteNarrative` (LLM-produced — JSON from `rsm-weekly-synthesizer` agent)

```
class SiteNarrative:
    standing_notes_synthesis: str | None     # optional weekly override of static standing_notes
    pattern_framing: str | None              # one sentence framing the pattern hits
    cyber_callout_text: str | None           # one-line text for the cyber callout
```

### `SiteBlock` (render-ready composite)

```
class SiteBlock:
    context: SiteContext
    computed: SiteComputed
    narrative: SiteNarrative
```

Template reads `site.context.name`, `site.computed.proximity_hits`, `site.narrative.pattern_framing` — explicit provenance at the template level.

### `BoardBriefData`

```
class BoardBriefData:
    cover: BoardCover                        # quarter, issue_date, classification, preparer, reviewer, board_meeting
    state_of_risk_line: str                  # narrative, one sentence
    cover_thesis_title: str                  # "Two items warrant board action."
    cover_thesis_subtitle: str               # "Six remain within management authority."

    posture: PosturePanel
        # overall_posture: Literal["LOW","MODERATE","HIGH","SEVERE"]
        # posture_shift: str                 # "↑ from MEDIUM · Q1"
        # admiralty: str
        # admiralty_shift: str
        # scenarios_on_watch: int
        # scenarios_split: str               # "2 board-action · 6 mgmt"
        # next_review: str

    board_takeaways: list[BoardTakeaway]     # 3–5 items
        # n: int
        # severity: Literal["critical","high","medium","monitor"]
        # body_markdown: str                 # includes <strong> emphasis
        # anchor: str                        # "S-07 · MED" or "REG · EU"

    delta_bar: list[RegionDelta]             # exactly 5
        # region: Literal["MED","NCE","APAC","LATAM","AME"]
        # direction: Literal["up","flat","down","cyber"]
        # label: str                         # "Raised", "Quieted", "Baseline"
        # cause: str                         # 1 line

    key_developments: list[KeyDevelopment]   # 4–6
        # n: int
        # category: Literal["M","W","C","G","S"]
        # headline: str
        # body: str
        # meaning: str                       # the "→" line
        # severity: Literal["critical","high","medium","monitor"]
        # region: str
        # anchors: list[str]                 # ["E1","E2","C3"]

    also_tracking: list[AlsoTrackingItem]    # 2–4
        # head: str
        # tail: str

    watch_next: list[WatchNextItem]          # 2–3
        # horizon: str                       # "6–12 weeks"
        # head: str
        # tail: str

    matrix: RiskMatrix
        # headline: str
        # bottom_line: str
        # dots: list[MatrixDot]              # 6–10
        #   scenario_id: str
        #   region: str
        #   label: str                       # "Unrest · Cape Wind (MED)"
        #   likelihood: int                  # 0–100
        #   impact: int                      # 0–100
        #   severity: Literal[...]
        #   label_position: Literal["up","down","left","right"]
        # register_tail: list[RegisterRow]   # compact 8-col strip

    scenarios: list[BoardScenario]           # 2–3
        # id: str                            # "S-07"
        # region: str
        # title: str
        # type_tags: list[str]               # ["Political-security","Crown-jewel exposure","Horizon: 0–12 weeks"]
        # posture: ScenarioPosture           # pill + severity + likelihood + admiralty + delta
        # narrative: ScenarioNarrative       # lede + list[str] paragraphs
        # implications: list[str]
        # baselines_moved: list[str]         # each with <strong>…</strong>
        # drivers: list[str]                 # 3–4 numbered
        # actions: list[str]                 # 3–4 numbered; item[0] may start with "Board ask:"
        # evidence_anchors: list[EvidenceRef]
        #   ref: str                         # "E1" or "C2"
        #   headline: str                    # source-line
        #   admiralty: str                   # "B1"

    methodology: Methodology
        # sources: dict[str,str]             # "Commercial": "Seerist...", etc.
        # rating_system: dict[str,str]
        # reading_rules: list[ReadingRule]   # cond + then
        # against_last_quarter: str + dict[str,str]

    end_matter: EndMatter
        # distribution: dict[str,str]
        # provenance: dict[str,str]
        # handling: list[str]                # 3 paragraphs
        # linked_products: dict[str,str]
```

### `CisoBriefData`

```
class CisoBriefData:
    cover: CisoCover                         # month, issue_date, classification, preparer, reviewer, audience

    cover_thesis_primary: str                # "The month's dominant signal is..."
    cover_thesis_secondary: str              # italic subline
    state_of_risk_line: str                  # narrative

    posture: CisoPosturePanel
        # posture, posture_shift, admiralty, admiralty_shift,
        # regions_moved: int (of 5), regions_movement_summary: str
        # scenarios_watched: int, scenarios_delta_note: str

    ciso_takeaways: list[CisoTakeaway]       # 3
        # n, severity: Literal["cyber","high","medium","monitor","critical"]
        # body_markdown, anchor

    regions_grid: list[RegionCell]           # exactly 5
        # region, classification: Literal["moved","cyber-pressed","quieted","baseline"]
        # direction: Literal["up","flat","down","cyber"]
        # status_label: str
        # admiralty: str, admiralty_shift: str
        # note: str
        # why_clear_label: str, why_clear_body: str

    cross_regional_items: list[CrossRegionalItem]    # 3–4
        # tag: str, tag_cyber: bool
        # head: str, body: str
        # delta: Literal["up","down","flat"], delta_label: str
        # rail_note: str, anchors: list[str]

    coupling_strip: CouplingStrip
        # region: str, label: str
        # physical_track: str (body prose)
        # cyber_track: str (body prose)
        # summary: str (the "Read: ..." line)

    cyber_surface: CyberSurface
        # sector_campaigns: list[CyberEntry]
        # actor_activity: list[CyberEntry]
        # vulnerability_signal: list[CyberEntry]
        # where CyberEntry = { k: str, ctx: str, body: str, impact: str,
        #                      severity: Literal[...], region_or_scope: str,
        #                      admiralty: str, anchors: list[str] }

    cyber_physical_join_page: CyberPhysicalJoin
        # physical: { title, narrative_paragraphs: list[str], facts: dict[str,str] }
        # cyber: { title, narrative_paragraphs: list[str], facts: dict[str,str] }
        # timeline: Timeline
        #   range_label: str
        #   ticks: list[TimelineTick]        # date + label
        #   physical_events: list[TimelineEvent]    # start_pct, width_pct, label, is_ghost
        #   cyber_events: list[TimelineEvent]
        #   join_marks: list[float]          # pct positions
        # read_summary: str                  # the "CISO read" paragraph

    scenarios: list[CisoScenario]            # 3–5
        # id, region, title
        # posture: ScenarioPosture
        # delta_ribbon: { kind: Literal["moved-up","moved-new","moved-down","no-delta"],
        #                 tag: str, body_markdown: str }
        # narrative: str (with drivers line appended)
        # side: dict[str,str]                # Delta, Horizon, Status/Asks, Next
        # anchors: list[str]

    evidence_physical: list[PhysicalEvidenceEntry]   # 8–12
    evidence_cyber: list[CyberEvidenceEntry]         # 5–10
        # Each: ref, headline, source, admiralty, timestamp, why
```

Both `BoardBriefData` and `CisoBriefData` are **fully static** this pass — their data modules return hardcoded instances matching the handoff's mock content. The Board quarterly synthesizer and CISO monthly synthesizer are future separate specs.

## Agent Change: new `rsm-weekly-synthesizer`

**Decision: new agent, not a mode on the existing one.** Daily and flash cadences continue with the existing `rsm-formatter-agent` producing markdown, unchanged. Weekly switches to a new dedicated agent producing structured JSON.

Rationale:
- Dual-mode on one agent means every prompt, stop hook, and failure path has to branch on cadence — brittle and hard to test.
- Weekly has a different output contract (JSON, not markdown), a different input shape (computed data pre-filled), and stricter validation (Pydantic schema check) than daily/flash.
- Splitting keeps the daily + flash pipeline stable while the weekly evolves independently.
- The `rsm-weekly-synthesizer` can inherit the `rsm-formatter-agent` persona + jargon filter + site-discipline rules by reference — no duplication of voice guidance.

### `rsm-weekly-synthesizer`

**Persona:** "Strategic Geopolitical & Cyber Risk Analyst" (same as `rsm-formatter-agent`).

**Input (prompt serialisation):**
The data module serialises a `WeeklySynthesisInput` Pydantic model to JSON, embeds it in the prompt inside a `<data>…</data>` block, and precedes it with a `<task>` block describing exactly which fields to fill.

```
class WeeklySynthesisInput:
    region: str
    week_of: str                              # "2026-04-20 → 2026-04-26"
    regional_admiralty_physical: str
    regional_admiralty_cyber: str
    baseline_strip: list[CountryPulse]        # computed
    top_events: list[RankedEvent]             # computed, severity + distance populated
    baselines_moved: list[BaselineDelta]      # computed vs last week
    sites_to_narrate: list[SiteForNarration]
        # SiteForNarration = {
        #   id, name, tier, country, country_lead,
        #   criticality_drivers,                     # static — for context
        #   standing_notes_static,                   # static — RSM's rolling notes
        #   pulse, host_baseline, days_since_incident,
        #   proximity_hits: list[JoinedEvent],       # computed
        #   pattern_hits: list[JoinedEvent],         # computed
        #   actor_hits: list[JoinedEvent],           # computed
        #   calendar_ahead: list[CalendarItem],      # computed
        #   cyber_event_to_attach: CyberCalloutComputed | None
        # }
    regional_cyber_context: RegionalCyberContext     # watchlist + this-week items
    evidence_entries: list[EvidenceEntryStub]
        # EvidenceEntryStub = { ref, headline, source, admiralty, timestamp,
        #                       supporting_sites: list[str],
        #                       supporting_pattern_or_actor: str | None }
```

**Output (strictly validated):**
```
class WeeklySynthesisOutput:
    headline: str                             # one sentence, regional characterisation
    sites_narrative: list[SiteNarrativeOut]
        # SiteNarrativeOut = {
        #   site_id: str,
        #   standing_notes_synthesis: str | null,   # optional weekly override
        #   pattern_framing: str | null,            # one sentence
        #   cyber_callout_text: str | null          # one sentence
        # }
    regional_cyber_standing_notes: str | null  # narrative framing for the cyber page
    evidence_why_lines: dict[str, str]         # ref → "why it's here" (exactly one per evidence entry)
```

**Stop hook:** new Python validator at `.claude/hooks/validators/rsm-weekly-synthesizer-output.py`:
1. Parse agent output as JSON.
2. Validate against `WeeklySynthesisOutput` Pydantic schema.
3. Confirm every `site_id` in the output matches a site in the input.
4. Confirm `evidence_why_lines` covers every evidence ref in input (no missing, no extra).
5. Re-run the existing jargon filter + site-discipline rules against all prose fields.
6. On failure, the agent retries once with a compact error message; second failure raises a build error.

### `rsm-formatter-agent` — unchanged

Daily and flash cadences continue producing markdown as today. No frontmatter change, no stop hook change.

### Deprecation note

The current weekly markdown output of `rsm-formatter-agent` is superseded by this spec. The implementation plan removes the weekly branch from `rsm-formatter-agent` once the new pipeline proves out.

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
- **`rsm-weekly-synthesizer`** is a new agent defined in `.claude/agents/rsm-weekly-synthesizer.md`. Its stop hook validator is a new Python file.
- **`rsm-formatter-agent`** unchanged for daily + flash. Weekly branch removed as a follow-up deprecation step.

### Site registry population — explicit, additive implementation task

The RSM brief cannot render with live data until `data/aerowind_sites.json` carries the new `SiteContext` fields. This is a **blocking prerequisite** for any RSM live-render test.

**Migration rule: additive, not replacing.** Existing fields stay unchanged — `tools/poi_proximity.py`, `tools/seerist_collector.py`, `tools/threshold_evaluator.py`, `tools/rsm_input_builder.py`, `tools/build_context.py`, and `.claude/hooks/validators/rsm-brief-context-checks.py` all continue to work without edits.

The implementation plan MUST include a dedicated task:

1. Add new fields alongside existing ones in `data/aerowind_sites.json`:
   - `tier`, `criticality_drivers`, `downstream_dependency`, `asset_type`, `status`, `seerist_country_code`, `contractors_count`, `country_lead`, `host_country_risk_baseline`, `standing_notes`, `relevant_seerist_categories`, `threat_actors_of_interest`, `relevant_attack_types`, `ot_stack`, `site_cyber_actors_of_interest`.
2. Do NOT rename, flatten, or delete any existing field (`lat`, `lon`, `poi_radius_km`, `criticality`, `personnel_count`, `expat_count`, `feeds_into`, `previous_incidents`, `notable_dates`, `site_lead`, etc. all stay).
3. Populate new fields with plausible real-ish content per site — crown-jewel sites get richer content than minor ones.
4. Validate the whole file parses as `list[SiteContext]` via a smoke test (model uses `extra="ignore"` so truly unknown fields pass through).
5. Run the existing test suite: `uv run pytest tests/test_site_registry.py tests/test_rsm_parallel_fanout.py tests/test_threshold_evaluator.py -v`. Expected: all pass — existing consumers untouched.
6. Commit as a content-only change separate from any code changes.

This is content work, not engineering — expect a dedicated session. No automation, no heuristics, no "ask the LLM to fill it in". The values feed real RSM briefs and will surface in stakeholder reads. They need to be deliberate.

### Input-data requirements

- `output/regional/{region}/osint_signals.json` must emit per-signal records conforming to the schema in **Layer 1** above. If the current collector is missing fields (`attack_type`, `perpetrator`, `sector`), the implementation plan includes a collector-extension task. Verify current shape before scoping.

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
5. The `rsm-weekly-synthesizer` produces schema-conformant JSON; the stop hook rejects anything else. `rsm-formatter-agent` continues producing daily + flash markdown as today.
6. The Reports tab in the app lists all three briefs with preview, download, and regenerate controls.
7. The Context tab (separate workstream) reads the `SiteBlock` schema straight out of `tools/briefs/models.py` — no re-definition.
8. Swapping the CRQ Design System v1.1 later means editing CSS files in `static/design/styles/` — nothing else moves.
