# Risk Register Validation V2 — Implementation Plan

**Goal:** Refactor the validation pipeline to search broadly and narrow at extraction, add two-tier context tagging, plausibility flagging, known-source version checks, and fix number formatting.

**Architecture:** Three changes to `register_validator.py` (query strategy, extraction tagging, version check) + output schema split into `registered_sources`/`new_sources` + UI two-box display. No new files — targeted edits to existing pipeline and frontend.

**Tech Stack:** Python `uv`, Anthropic SDK (Haiku + Sonnet), Tavily/DuckDuckGo, FastAPI `server.py`, Vanilla JS, Tailwind CSS

---

## File Map

| File | Change |
|---|---|
| `tools/register_validator.py` | Refactor `build_register_queries` → broad sector queries; update extraction prompts to return `context_tag`; add `smb_scale_flag`; add `check_source_versions()`; split `new_sources`/`registered_sources` in output |
| `data/validation_sources.json` | Add `edition_year: int` to each of the 7 sources |
| `.claude/hooks/validators/register-validation-auditor.py` | Validate `registered_sources`, `new_sources`, `version_checks` fields |
| `static/app.js` | Fix `toLocaleString` calls; render two-box source display; context tag badges; version check flag |
| `static/index.html` | CSS for context tag badge classes |

---

## Task 1: Fix number formatting

**Files:**
- Modify: `static/app.js` lines ~3405, ~3408, ~3430

- [ ] **Step 1: Find all unlocalized toLocaleString calls in the validation render section**

In `static/app.js`, search for `toLocaleString()` (no args) near dollar formatting in the validation render functions (around line 3400). There are three calls:

```js
// Line ~3405 — VaCR figure
`$${Number(d.vacr_figure_usd).toLocaleString()}`

// Line ~3408 — benchmark range
`$${Number(d.benchmark_range_usd[0]).toLocaleString()} – $${Number(d.benchmark_range_usd[1]).toLocaleString()}`

// Line ~3430 — source figure
`$${Number(src.figure_usd).toLocaleString()}`
```

- [ ] **Step 2: Replace all three with en-US locale**

```js
// Line ~3405
`$${Number(d.vacr_figure_usd).toLocaleString('en-US')}`

// Line ~3408
`$${Number(d.benchmark_range_usd[0]).toLocaleString('en-US')} – $${Number(d.benchmark_range_usd[1]).toLocaleString('en-US')}`

// Line ~3430
`$${Number(src.figure_usd).toLocaleString('en-US')}`
```

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "fix(ui): number formatting — use en-US locale for USD figures"
```

---

## Task 2: Add `edition_year` to validation_sources.json

**Files:**
- Modify: `data/validation_sources.json`

- [ ] **Step 1: Add `edition_year` to each source**

Add `"edition_year": <year>` after `"cadence"` for each of the 7 sources. Use the most recent known edition:

| Source ID | edition_year |
|---|---|
| `verizon-dbir` | 2024 |
| `ibm-cost-data-breach` | 2024 |
| `dragos-ics-ot` | 2024 |
| `mandiant-mtrends` | 2024 |
| `claroty-xiot` | 2024 |
| `marsh-cyber-insurance` | 2023 |
| `ponemon-critical-infra` | 2023 |
| `enisa-threat-landscape` | 2024 |
| `nerc-cip` | 2023 |

Example result for `verizon-dbir`:
```json
{
  "id": "verizon-dbir",
  "name": "Verizon Data Breach Investigations Report",
  "url": "https://www.verizon.com/business/resources/reports/dbir/",
  "cadence": "annual",
  "edition_year": 2024,
  "admiralty_reliability": "A",
  ...
}
```

- [ ] **Step 2: Commit**

```bash
git add data/validation_sources.json
git commit -m "data: add edition_year to validation_sources for version checking"
```

---

## Task 3: Refactor query builder — broad sector queries

**Files:**
- Modify: `tools/register_validator.py` — replace `build_register_queries` function (line 171)

- [ ] **Step 1: Replace `build_register_queries` with `_build_sector_queries`**

Delete the existing `build_register_queries` function (lines 171–202) and replace with:

```python
def _build_sector_queries(scenario: dict, register: dict) -> dict:
    """
    Build moderate-breadth sector queries. Includes industry + scenario type.
    Does NOT include asset-specific OT terms — those are applied at extraction tagging.
    Returns {"financial": str, "probability": str}
    """
    name = scenario["scenario_name"]
    # Derive industry context from register company_context (first 80 chars, cleaned)
    context = register.get("company_context", "energy sector")
    # Extract sector hints: prefer explicit sector words
    sector = "energy sector"
    if "wind" in context.lower():
        sector = "energy sector wind power"
    elif "manufacturing" in context.lower():
        sector = "manufacturing energy sector"

    financial = (
        f"{name} financial cost impact {sector} operator USD 2024 2025"
    )
    probability = (
        f"{name} incident rate probability annual {sector} 2024 2025"
    )
    return {"financial": financial, "probability": probability}
```

- [ ] **Step 2: Update `phase2_osint_search` to use new function**

In `phase2_osint_search` (line 266), replace the call to `build_register_queries`:

```python
def phase2_osint_search(
    scenario: dict, register: dict
) -> tuple[list[dict], list[dict]]:
    """
    Track 1: Broad sector OSINT — moderate-breadth query, context tagged at extraction.
    Returns (fin_figures, prob_figures) — each item has phase=2.
    """
    queries = _build_sector_queries(scenario, register)
    fin_figures, prob_figures = [], []

    print(f"[register_validator] Track1 fin -- {queries['financial'][:80]}", file=sys.stderr)
    results = _search_web(queries["financial"], max_results=6)
    for r in results:
        content = r.get("content", "")
        src_name = r.get("title") or r.get("url", "")
        for fig in _extract_financial_figures(content, src_name):
            fig["phase"] = 2
            fig["source_url"] = r.get("url", "")
            fin_figures.append(fig)

    print(f"[register_validator] Track1 prob -- {queries['probability'][:80]}", file=sys.stderr)
    results = _search_web(queries["probability"], max_results=6)
    for r in results:
        content = r.get("content", "")
        src_name = r.get("title") or r.get("url", "")
        for fig in _extract_probability_figures(content, src_name):
            fig["phase"] = 2
            fig["source_url"] = r.get("url", "")
            prob_figures.append(fig)

    return fin_figures, prob_figures
```

- [ ] **Step 3: Commit**

```bash
git add tools/register_validator.py
git commit -m "refactor(validator): broad sector queries — context applied at extraction not search"
```

---

## Task 4: Add context tagging to Haiku extraction

**Files:**
- Modify: `tools/register_validator.py` — update `_FIN_EXTRACTION_PROMPT` and `_PROB_EXTRACTION_PROMPT`

- [ ] **Step 1: Update `_FIN_EXTRACTION_PROMPT` to include `context_tag`**

Replace the existing `_FIN_EXTRACTION_PROMPT` constant:

```python
_FIN_EXTRACTION_PROMPT = """\
You are extracting financial impact data from a cybersecurity industry report.

Extract all dollar-denominated financial impact figures for cyber incidents. For each figure found:
- scenario_tag: classify into one of: System intrusion, Ransomware, Accidental disclosure, Physical threat, Insider misuse, DoS attack, Scam or fraud, Defacement, System failure
- sector: the industry sector this applies to (e.g. "manufacturing", "energy", "all")
- cost_low_usd: lower bound in USD as integer (null if not stated)
- cost_median_usd: median or average in USD as integer (null if not stated)
- cost_high_usd: upper bound in USD as integer (null if not stated)
- note: brief description of what this figure represents
- raw_quote: the exact text excerpt (max 200 chars)
- context_tag: classify the source based on its content:
    "asset_specific" if the source specifically discusses OT systems, ICS, SCADA, industrial control, wind, turbine, or critical infrastructure operations
    "company_scale" if the source discusses enterprise-scale, large organisations (>1000 employees), sector-wide statistics without OT specificity
    "both" if it meets both criteria
    "general" if neither applies

Return ONLY a JSON array. If no financial figures found, return [].

Text to analyze:
{raw_text}"""
```

- [ ] **Step 2: Update `_PROB_EXTRACTION_PROMPT` to include `context_tag`**

Replace the existing `_PROB_EXTRACTION_PROMPT` constant:

```python
_PROB_EXTRACTION_PROMPT = """\
You are extracting incident probability data from a cybersecurity industry report.

Extract all percentage figures that represent incident frequency or probability:
- Annual incident probability (% of organizations affected per year)
- Incident frequency rates
- Prevalence rates for cyber incidents

For each figure found:
- scenario_tag: classify into one of: System intrusion, Ransomware, Accidental disclosure, Physical threat, Insider misuse, DoS attack, Scam or fraud, Defacement, System failure
- sector: the industry sector this applies to
- probability_pct: the percentage value as a float
- note: brief description of what this percentage represents
- raw_quote: the exact text excerpt (max 200 chars)
- context_tag: classify the source based on its content:
    "asset_specific" if the source specifically discusses OT systems, ICS, SCADA, industrial control, wind, turbine, or critical infrastructure operations
    "company_scale" if the source discusses enterprise-scale, large organisations (>1000 employees), sector-wide statistics without OT specificity
    "both" if it meets both criteria
    "general" if neither applies

Return ONLY a JSON array. If no probability figures found, return [].

Text to analyze:
{raw_text}"""
```

- [ ] **Step 3: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat(validator): context tagging in Haiku extraction — asset_specific / company_scale / both / general"
```

---

## Task 5: Add plausibility flag

**Files:**
- Modify: `tools/register_validator.py` — add `_compute_scale_floor` and apply `smb_scale_flag`

- [ ] **Step 1: Add `_compute_scale_floor` function**

Add after the `filter_outliers` function (after line 324):

```python
def _compute_scale_floor(register: dict) -> float:
    """
    Derive a plausibility floor from the register's VaCR figures.
    Any extracted financial figure below this is flagged as possible SMB-scale data.
    Floor = max($100k, 5% of the minimum non-zero VaCR across all scenarios).
    """
    vacr_values = [
        s.get("value_at_cyber_risk_usd", 0)
        for s in register.get("scenarios", [])
        if s.get("value_at_cyber_risk_usd")
    ]
    if not vacr_values:
        return 100_000.0
    return max(100_000.0, min(vacr_values) * 0.05)
```

- [ ] **Step 2: Apply `smb_scale_flag` in `validate_scenario`**

In `validate_scenario` (line 454), after `p1_fin, p1_prob` and `p2_fin, p2_prob` are assembled and before `fin_values` loop, add:

```python
    scale_floor = _compute_scale_floor(register)
```

Then in the deduplication loop where `fin_sources_out` is built (around line 496), add the flag:

```python
    for f in all_fin_figs:
        key = (f.get("_source_name", "") or "")[:60]
        if key and key not in seen_fin:
            seen_fin.add(key)
            fig_usd = f.get("cost_median_usd")
            fin_sources_out.append({
                "name": f.get("_source_name", ""),
                "url": f.get("source_url", ""),
                "figure_usd": fig_usd,
                "context_tag": f.get("context_tag", "general"),
                "smb_scale_flag": bool(fig_usd and float(fig_usd) < scale_floor),
                "note": f.get("note", ""),
                "raw_quote": f.get("raw_quote", ""),
                "phase": f.get("phase", 2),
            })
```

And for `prob_sources_out`, add `context_tag`:

```python
    for f in all_prob_figs:
        key = (f.get("_source_name", "") or "")[:60]
        if key and key not in seen_prob:
            seen_prob.add(key)
            prob_sources_out.append({
                "name": f.get("_source_name", ""),
                "url": f.get("source_url", ""),
                "figure_pct": f.get("probability_pct"),
                "context_tag": f.get("context_tag", "general"),
                "smb_scale_flag": False,
                "note": f.get("note", ""),
                "raw_quote": f.get("raw_quote", ""),
                "phase": f.get("phase", 2),
            })
```

- [ ] **Step 3: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat(validator): plausibility flag — smb_scale_flag on figures below register scale floor"
```

---

## Task 6: Split output into registered_sources / new_sources + asset_context_note

**Files:**
- Modify: `tools/register_validator.py` — `validate_scenario` output assembly

- [ ] **Step 1: Split sources by phase in `validate_scenario`**

In the output assembly section of `validate_scenario` (around line 522), replace the current `fin_result` and `prob_result` dicts:

```python
    # Split sources: phase=1 (known registry) → registered_sources; phase=2 (Track 1) → new_sources
    fin_registered = [s for s in fin_sources_out if s.get("phase") == 1]
    fin_new        = [s for s in fin_sources_out if s.get("phase") == 2]
    prob_registered = [s for s in prob_sources_out if s.get("phase") == 1]
    prob_new        = [s for s in prob_sources_out if s.get("phase") == 2]

    # Asset context note — if no asset_specific sources found
    has_asset_fin  = any(s["context_tag"] in ("asset_specific", "both") for s in fin_sources_out)
    has_asset_prob = any(s["context_tag"] in ("asset_specific", "both") for s in prob_sources_out)
    asset_context_note = ""
    if not has_asset_fin and not has_asset_prob:
        asset_context_note = "No OT/asset-specific quantitative data found — company-scale sources only."

    fin_result = {
        "vacr_figure_usd": vacr_usd,
        "verdict": fin_verdict,
        "benchmark_range_usd": fin_range,
        "registered_sources": fin_registered,
        "new_sources": fin_new,
        "recommendation": "",
    }
    prob_result = {
        "vacr_probability_pct": vacr_pct,
        "verdict": prob_verdict,
        "benchmark_range_pct": prob_range,
        "registered_sources": prob_registered,
        "new_sources": prob_new,
        "recommendation": "",
    }
```

And update the returned dict to include `asset_context_note`:

```python
    return {
        "scenario_id": scenario["scenario_id"],
        "scenario_name": scenario["scenario_name"],
        "asset_context_note": asset_context_note,
        "financial": fin_result,
        "probability": prob_result,
    }
```

- [ ] **Step 2: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat(validator): split registered_sources/new_sources in output; add asset_context_note"
```

---

## Task 7: Add version check (Track 3)

**Files:**
- Modify: `tools/register_validator.py` — add `check_source_versions` function and call in `main()`

- [ ] **Step 1: Add `check_source_versions` function**

Add after `phase2_osint_search` (after line 299):

```python
# ---------------------------------------------------------------------------
# Track 3: Known source version check
# ---------------------------------------------------------------------------

VALIDATION_SOURCES_PATH = REPO_ROOT / "data" / "validation_sources.json"


def check_source_versions() -> list[dict]:
    """
    Track 3: For each source in validation_sources.json, search for a newer edition.
    Compares found year against edition_year. Runs once per validation run (not per scenario).
    Returns list of version check results.
    """
    import datetime
    current_year = datetime.datetime.now().year
    try:
        sources = json.loads(VALIDATION_SOURCES_PATH.read_text(encoding="utf-8")).get("sources", [])
    except Exception as e:
        print(f"[register_validator] Could not load validation_sources.json: {e}", file=sys.stderr)
        return []

    results = []
    for source in sources:
        edition_year = source.get("edition_year", current_year - 1)
        name = source["name"]
        url = source.get("url", "")

        # Only check if edition might be stale (more than 1 year old)
        if current_year - edition_year < 1:
            results.append({
                "source_id": source["id"],
                "name": name,
                "edition_year": edition_year,
                "newer_version_found": False,
                "newer_year": None,
                "url": url,
            })
            continue

        query = f'"{name}" {current_year} annual report'
        print(f"[register_validator] Track3 version -- {name[:50]}: {query[:70]}", file=sys.stderr)
        search_results = _search_web(query, max_results=3)

        newer_year = None
        newer_url = url
        for r in search_results:
            title = r.get("title", "") + " " + r.get("content", "")[:200]
            # Look for current_year or current_year-1 in title/content
            for yr in [current_year, current_year - 1]:
                if str(yr) in title and yr > edition_year:
                    newer_year = yr
                    newer_url = r.get("url", url)
                    break
            if newer_year:
                break

        results.append({
            "source_id": source["id"],
            "name": name,
            "edition_year": edition_year,
            "newer_version_found": newer_year is not None,
            "newer_year": newer_year,
            "url": newer_url if newer_year else url,
        })

    return results
```

- [ ] **Step 2: Call `check_source_versions` in `main()`**

In `main()` (line 555), add after `register = load_active_register()`:

```python
    print("[register_validator] Track 3 — checking source versions...")
    version_checks = check_source_versions()
    newer_count = sum(1 for v in version_checks if v["newer_version_found"])
    print(f"[register_validator] Version check: {newer_count}/{len(version_checks)} sources may have newer editions")
```

And add `version_checks` to the output dict (line ~572):

```python
    output = {
        "register_id": register["register_id"],
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "version_checks": version_checks,
        "scenarios": scenario_results,
    }
```

- [ ] **Step 3: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat(validator): Track 3 — known source version check, newer edition detection"
```

---

## Task 8: Update stop hook schema validation

**Files:**
- Modify: `.claude/hooks/validators/register-validation-auditor.py`

- [ ] **Step 1: Read current auditor**

Read `.claude/hooks/validators/register-validation-auditor.py` to understand current checks.

- [ ] **Step 2: Add checks for new schema fields**

In the scenario validation loop, add checks for new fields. Find the scenario-level checks and add:

```python
# Check registered_sources and new_sources exist (replacing existing_sources/new_sources check)
for dim in ["financial", "probability"]:
    d = scenario.get(dim, {})
    if "registered_sources" not in d:
        errors.append(f"{sid}.{dim}: missing 'registered_sources'")
    if "new_sources" not in d:
        errors.append(f"{sid}.{dim}: missing 'new_sources'")
    # context_tag on each source
    for src in d.get("registered_sources", []) + d.get("new_sources", []):
        if src.get("context_tag") not in ("asset_specific", "company_scale", "both", "general"):
            errors.append(f"{sid}.{dim}: source missing valid context_tag")

# Check asset_context_note field exists
if "asset_context_note" not in scenario:
    errors.append(f"{sid}: missing 'asset_context_note'")
```

And at the top level, add:

```python
# Check version_checks at top level
if "version_checks" not in data:
    errors.append("Missing top-level 'version_checks'")
```

- [ ] **Step 3: Commit**

```bash
git add .claude/hooks/validators/register-validation-auditor.py
git commit -m "feat(hooks): update register-validation-auditor for v2 schema"
```

---

## Task 9: UI — context tag badge CSS

**Files:**
- Modify: `static/index.html` — add context tag badge CSS

- [ ] **Step 1: Add badge CSS to `<style>` block**

Find the closing `</style>` tag. Before it, add:

```css
    /* Validation source context tag badges */
    .ctx-badge {
      display: inline-block;
      font-size: 8px;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 2px;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      flex-shrink: 0;
    }
    .ctx-asset   { background: #0d1f2e; border: 1px solid #1f4a6e; color: #79c0ff; }
    .ctx-scale   { background: #1a0d2e; border: 1px solid #3d2d7a; color: #a371f7; }
    .ctx-both    { background: #071810; border: 1px solid #1a5c2a; color: #3fb950; }
    .ctx-general { background: #111318; border: 1px solid #30363d; color: #484f58; }
    .ctx-smb     { background: #2e1a07; border: 1px solid #6e4a1a; color: #e3b341; font-style: italic; }
    .ctx-newver  { background: #2e1a07; border: 1px solid #6e4a1a; color: #e3b341; }

    /* Two-box source layout */
    .val-sources-box {
      border: 1px solid #21262d;
      border-radius: 3px;
      margin-top: 8px;
    }
    .val-sources-box-label {
      font-size: 8px;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #484f58;
      padding: 5px 10px 4px;
      border-bottom: 1px solid #21262d;
      background: #080c10;
    }
    .val-source-row {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 6px 10px;
      border-bottom: 1px solid #161b22;
      font-size: 10px;
    }
    .val-source-row:last-child { border-bottom: none; }
    .val-source-name { color: #79c0ff; text-decoration: none; flex: 1; min-width: 0; word-break: break-word; }
    .val-source-name:hover { text-decoration: underline; }
    .val-source-figure { color: #3fb950; font-weight: 600; white-space: nowrap; }
    .val-source-note { color: #484f58; font-size: 9px; margin-top: 2px; }
    .val-empty-box { padding: 8px 10px; font-size: 10px; color: #30363d; font-style: italic; }
```

- [ ] **Step 2: Commit**

```bash
git add static/index.html
git commit -m "feat(ui): context tag badge CSS + two-box source layout CSS"
```

---

## Task 10: UI — two-box source display in app.js

**Files:**
- Modify: `static/app.js` — rewrite source rendering in validation expanded rows

- [ ] **Step 1: Add `_ctxBadge` helper near other badge helpers**

Find the `_vtierBadge` or similar badge helper functions in `static/app.js`. Add:

```js
function _ctxBadge(tag) {
  const map = {
    asset_specific: ['ctx-asset', 'OT / Asset'],
    company_scale:  ['ctx-scale', 'Enterprise Scale'],
    both:           ['ctx-both', 'Both'],
    general:        ['ctx-general', 'General'],
  };
  const [cls, label] = map[tag] || ['ctx-general', 'General'];
  return `<span class="ctx-badge ${cls}">${label}</span>`;
}

function _renderSourceRow(src, versionChecks) {
  const figure = src.figure_usd != null
    ? `<span class="val-source-figure">$${Number(src.figure_usd).toLocaleString('en-US')}</span>`
    : src.figure_pct != null
      ? `<span class="val-source-figure">${src.figure_pct}%</span>`
      : '';
  const smbFlag = src.smb_scale_flag
    ? `<span class="ctx-badge ctx-smb" title="Figure may reflect SMB-scale incident, not enterprise scale">SMB-scale?</span>`
    : '';
  const ctxTag = _ctxBadge(src.context_tag || 'general');
  // Check if this source has a newer version (match by name fragment)
  let newVerBadge = '';
  if (versionChecks) {
    const vc = versionChecks.find(v => v.newer_version_found &&
      (src.name || '').toLowerCase().includes((v.name || '').toLowerCase().split(' ')[0]));
    if (vc) newVerBadge = `<span class="ctx-badge ctx-newver">${vc.newer_year} edition available</span>`;
  }
  const nameEl = src.url
    ? `<a class="val-source-name" href="${src.url}" target="_blank" rel="noopener">${esc(src.name || src.url)}</a>`
    : `<span class="val-source-name" style="color:#8b949e">${esc(src.name || '—')}</span>`;

  return `<div class="val-source-row">
  <div style="flex:1;min-width:0">
    <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
      ${nameEl}${figure}${ctxTag}${smbFlag}${newVerBadge}
    </div>
    ${src.note ? `<div class="val-source-note">${esc(src.note)}</div>` : ''}
  </div>
</div>`;
}

function _renderSourcesBox(label, sources, versionChecks) {
  if (!sources || !sources.length) {
    return `<div class="val-sources-box">
  <div class="val-sources-box-label">${label}</div>
  <div class="val-empty-box">No sources found</div>
</div>`;
  }
  return `<div class="val-sources-box">
  <div class="val-sources-box-label">${label}</div>
  ${sources.map(s => _renderSourceRow(s, versionChecks)).join('')}
</div>`;
}
```

- [ ] **Step 2: Update expanded row rendering to use two-box layout**

Find the function that renders the expanded validation row (the one that currently renders `src` items with `phase` attribute — likely inside a `renderValidation` or `_renderVacrRow` function). Replace the source list rendering with:

```js
// Inside the expanded row render — replace the existing source list:
const versionChecks = _validationData?.version_checks || [];
const financialBox = `
  ${_renderSourcesBox('Registered Sources', dim.registered_sources, versionChecks)}
  ${_renderSourcesBox('New Sources', dim.new_sources, null)}
`;
```

Where `dim` is the `financial` or `probability` object from the validation result, and `_validationData` is the full validation result object stored in state.

- [ ] **Step 3: Add asset_context_note display**

In the scenario header row (the expandable row per scenario), after the verdict badges, add:

```js
${scenario.asset_context_note
  ? `<div style="font-size:9px;color:#484f58;font-style:italic;margin-top:4px">${esc(scenario.asset_context_note)}</div>`
  : ''}
```

- [ ] **Step 4: Verify in browser**

Reload app → Risk Register tab → run validation → expand a scenario row. Should see:
- **Registered Sources** box with known sources, context tag badges, `[2025 edition available]` where applicable
- **New Sources** box with newly found sources, linked titles, figures, context tags
- SMB-scale flag on any suspiciously small figures
- asset_context_note when no OT-specific sources found

- [ ] **Step 5: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): two-box source display — registered/new sources, context tag badges, version flags"
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task |
|---|---|
| Broad sector queries (not narrow OT at search time) | Task 3 |
| Context tagging at extraction from source content | Task 4 |
| Plausibility flag (not reject) on SMB-scale figures | Task 5 |
| Split registered_sources / new_sources in output | Task 6 |
| asset_context_note when no OT sources found | Task 6 |
| Known source version check (Track 3) | Task 7 |
| edition_year field in validation_sources.json | Task 2 |
| Stop hook validates new schema | Task 8 |
| Number formatting en-US | Task 1 |
| CSS for context tag badges | Task 9 |
| Two-box UI with badges + version flags | Task 10 |

**Placeholder scan:** No TBDs. Task 10 Step 2 references `_validationData` — builder must find the existing state variable name for validation results in app.js (search for `register_validation` or `validationResult` in app.js and use the correct name).

**Type consistency:** `context_tag` values are `"asset_specific"`, `"company_scale"`, `"both"`, `"general"` throughout extraction prompt, flag logic, UI badge map, and stop hook check. `smb_scale_flag: bool` consistently. `registered_sources`/`new_sources` split consistently in Task 6 output and Task 10 UI render.
