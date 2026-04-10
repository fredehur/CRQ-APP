# Register Validator Pipeline v2 — Implementation Plan

**Goal:** Fix four structural issues in `tools/register_validator.py` identified in code review: restore OT-specific query branches, add deterministic `verdict_confidence` from `context_tag`, tell Sonnet the probability evidence type, and move recommendation to scenario level. Includes five minor fixes.

**Architecture:** All changes are confined to `tools/register_validator.py` and `static/app.js`. The output schema is backwards-compatible except two additive fields (`verdict_confidence`, `evidence_type`) and one field relocation (`recommendation` moves from `financial`/`probability` to the scenario root). UI updated in same pass.

**Tech Stack:** Python (`tools/register_validator.py`), vanilla JS (`static/app.js`). No new dependencies.

---

## File Map

| File | Change |
|---|---|
| `tools/register_validator.py` | All pipeline changes — 5 tasks |
| `static/app.js` | Confidence badge + recommendation zone + evidence type caveat |
| `static/index.html` | Three new CSS classes for confidence badge |

---

## Task 1: Restore OT Query Branches in `build_register_queries`

**Files:**
- Modify: `tools/register_validator.py` lines 195–206 (`_build_sector_queries`) and lines 278–302 (`phase2_osint_search`)

**Context:** The shipped version generates 1 query per dimension with no OT branching. `phase2_osint_search` iterates `[queries["financial"]]` — a single-element list — instead of the full query array. Scenarios with OT/SCADA tags (system intrusion, ransomware on a wind farm) never get targeted Dragos/CISA/ICS-CERT queries.

**Depends on:** nothing  
**Feeds into:** Task 2 (more OT-specific sources = better `context_tag` signal = better confidence)

---

- [ ] **Step 1: Add named constants for query caps near the top of the file (after line 31)**

```python
_PHASE1_SOURCE_CAP = 5  # limits Tavily API calls per scenario against known sources.db entries
_PHASE2_QUERY_CAP = 3   # max queries per dimension per scenario in Phase 2
```

- [ ] **Step 2: Replace `_build_sector_queries` (lines 195–206) with `build_register_queries`**

```python
def build_register_queries(scenario: dict, register: dict) -> dict:
    """
    Build up to _PHASE2_QUERY_CAP financial queries and _PHASE2_QUERY_CAP probability
    queries per scenario. OT/SCADA branches added when search_tags indicate ICS exposure.

    Returns:
        {"financial": [str, ...], "probability": [str, ...]}
        Each list has 1-3 entries, ordered most-specific first.
    """
    name = scenario["scenario_name"]
    context = register.get("company_context", "energy sector")
    tags = set(scenario.get("search_tags", []))
    is_ot = bool(tags & {"ot_systems", "scada", "wind_turbine", "ics", "industrial_control"})
    is_wind = "wind" in context.lower() or "wind_turbine" in tags

    if is_wind:
        sector = "wind power energy operator"
    elif "manufacturing" in context.lower():
        sector = "manufacturing energy sector"
    else:
        sector = "energy sector"

    financial: list[str] = []
    probability: list[str] = []

    # Base: broad sector query (always included)
    financial.append(f'"{name}" financial cost impact {sector} USD 2024 2025')
    probability.append(f'"{name}" incident rate frequency annual {sector} 2024 2025')

    # OT branch: ICS-specific queries when relevant tags present
    if is_ot:
        financial.append(
            f'"{name}" OT ICS SCADA operational technology cost USD 2024 2025 energy'
        )
        probability.append(
            f'"{name}" ICS OT incident frequency 2024 Dragos OR CISA OR ICS-CERT energy operator'
        )

    # Wind-specific: named incident cost data
    if is_wind:
        financial.append(
            f'wind farm cyber incident cost "system intrusion" OR "ransomware" USD 2022 2023 2024'
        )

    return {
        "financial": financial[:_PHASE2_QUERY_CAP],
        "probability": probability[:_PHASE2_QUERY_CAP],
    }
```

- [ ] **Step 3: Update `phase2_osint_search` to iterate full query lists and use `build_register_queries`**

Replace lines 270–302:

```python
def phase2_osint_search(
    scenario: dict, register: dict
) -> tuple[list[dict], list[dict]]:
    """
    Phase 2: Register-contextualized OSINT.
    Iterates all queries from build_register_queries (up to _PHASE2_QUERY_CAP each).
    Returns (fin_figures, prob_figures) — each item has phase=2.
    """
    queries = build_register_queries(scenario, register)
    fin_figures, prob_figures = [], []

    for query in queries["financial"]:
        print(f"[register_validator] Phase 2 fin -- {query[:80]}", file=sys.stderr)
        results = _search_web(query, max_results=4)
        for r in results:
            content = r.get("content", "")
            src_name = r.get("title") or r.get("url", "")
            for fig in _extract_financial_figures(content, src_name):
                fig["phase"] = 2
                fig["source_url"] = r.get("url", "")
                fin_figures.append(fig)

    for query in queries["probability"]:
        print(f"[register_validator] Phase 2 prob -- {query[:80]}", file=sys.stderr)
        results = _search_web(query, max_results=4)
        for r in results:
            content = r.get("content", "")
            src_name = r.get("title") or r.get("url", "")
            for fig in _extract_probability_figures(content, src_name):
                fig["phase"] = 2
                fig["source_url"] = r.get("url", "")
                prob_figures.append(fig)

    return fin_figures, prob_figures
```

- [ ] **Step 4: Replace `relevant[:5]` in `phase1_refresh_known_sources` (line 236) with the named constant**

```python
    for source in relevant[:_PHASE1_SOURCE_CAP]:
```

- [ ] **Step 5: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat: restore OT query branches in build_register_queries + fix phase2 single-query iteration"
```

---

## Task 2: Add `verdict_confidence` from `context_tag`

**Files:**
- Modify: `tools/register_validator.py` — add `compute_verdict_confidence()`, call in `validate_scenario()`
- Modify: `static/app.js` — render confidence badge in `_renderRegValDimension`
- Modify: `static/index.html` — add three CSS classes

**Context:** `context_tag` is collected per source but plays no role in the verdict. A `CHALLENGES` from OT-specific sources is a strong signal; `CHALLENGES` from general sector reports is weak. This adds a deterministic `verdict_confidence` field (`high`/`medium`/`low`) — no LLM involved.

**Depends on:** Task 1 (OT queries produce OT-tagged sources → `high` confidence more achievable)  
**Feeds into:** UI badge

---

- [ ] **Step 1: Add `compute_verdict_confidence()` after `compute_verdict()` (after line 454)**

```python
def compute_verdict_confidence(sources: list[dict]) -> str:
    """
    Deterministic confidence rating based on source context_tag values.
    high   — at least one source tagged asset_specific or both (OT/ICS data)
    medium — at least one source tagged company_scale (enterprise sector peer)
    low    — all sources are general (no sector or asset specificity)
    """
    tags = [s.get("context_tag", "general") for s in sources]
    if any(t in ("asset_specific", "both") for t in tags):
        return "high"
    if any(t == "company_scale" for t in tags):
        return "medium"
    return "low"
```

- [ ] **Step 2: Add confidence computation in `validate_scenario()` before `fin_result`/`prob_result` construction (after line 606)**

```python
    fin_confidence = compute_verdict_confidence(fin_registered_out + fin_new_out)
    prob_confidence = compute_verdict_confidence(prob_registered_out + prob_new_out)
```

- [ ] **Step 3: Add `verdict_confidence` to `fin_result` dict**

```python
    fin_result = {
        "vacr_figure_usd": vacr_usd,
        "verdict": fin_verdict,
        "verdict_confidence": fin_confidence,
        "benchmark_range_usd": fin_range,
        "registered_sources": fin_registered_out,
        "new_sources": fin_new_out,
        "recommendation": "",
    }
```

- [ ] **Step 4: Add `verdict_confidence` to `prob_result` dict**

```python
    prob_result = {
        "vacr_probability_pct": vacr_pct,
        "verdict": prob_verdict,
        "verdict_confidence": prob_confidence,
        "benchmark_range_pct": prob_range,
        "registered_sources": prob_registered_out,
        "new_sources": prob_new_out,
        "recommendation": "",
    }
```

- [ ] **Step 5: Add confidence badge CSS to `static/index.html` after `.rr-verdict-insufficient` block**

```css
/* Verdict confidence qualifiers */
.rr-conf-high   { font-size:8px;color:#3fb950;background:#0a1f0a;border:1px solid #1a4d1a;border-radius:2px;padding:1px 5px;font-family:'IBM Plex Mono',monospace;font-weight:700;letter-spacing:0.06em; }
.rr-conf-medium { font-size:8px;color:#e3b341;background:#1f1700;border:1px solid #4a3800;border-radius:2px;padding:1px 5px;font-family:'IBM Plex Mono',monospace;font-weight:700;letter-spacing:0.06em; }
.rr-conf-low    { font-size:8px;color:#484f58;background:#0d1117;border:1px solid #21262d;border-radius:2px;padding:1px 5px;font-family:'IBM Plex Mono',monospace;font-weight:700;letter-spacing:0.06em; }
```

- [ ] **Step 6: Render confidence badge in `_renderRegValDimension` in `static/app.js`**

Before the `return` template literal in `_renderRegValDimension`, add:

```js
  const confLabel = {high: 'OT DATA', medium: 'SECTOR', low: 'GENERAL'}[d.verdict_confidence] || 'GENERAL';
  const confClass = {high: 'rr-conf-high', medium: 'rr-conf-medium', low: 'rr-conf-low'}[d.verdict_confidence] || 'rr-conf-low';
```

Then update the `rr-dim-right` span from:

```js
<span class="rr-dim-right">${_regValVerdictBadge('', d.verdict)}<span class="rr-src-count">${allSources.length} src</span></span>
```

To:

```js
<span class="rr-dim-right">${_regValVerdictBadge('', d.verdict)}<span class="${confClass}">${confLabel}</span><span class="rr-src-count">${allSources.length} src</span></span>
```

- [ ] **Step 7: Commit**

```bash
git add tools/register_validator.py static/app.js static/index.html
git commit -m "feat: add verdict_confidence from context_tag — OT DATA / SECTOR / GENERAL badge in validation UI"
```

---

## Task 3: Probability Evidence Type — `evidence_type` Field + Sonnet Prompt Caveat

**Files:**
- Modify: `tools/register_validator.py` — update `_PROB_EXTRACTION_PROMPT`, add `evidence_type` to prob_result, update `_RECOMMENDATION_PROMPT` and `_build_recommendation_sonnet`

**Context:** Probability sources return enterprise prevalence rates ("43% of orgs experienced ransomware") not OT loss frequency. Sonnet isn't told this, so it presents probability verdicts with false confidence. Fix: (1) add `evidence_subtype` to Haiku extraction so it labels what kind of figure it found, (2) aggregate into `evidence_type` on prob_result (`prevalence_survey` / `frequency_rate` / `mixed`), (3) tell Sonnet explicitly so it caveats the probability verdict.

**Depends on:** Task 2 (prob_result schema already extended)  
**Feeds into:** Task 5 (UI caveat badge reads `evidence_type`)

---

- [ ] **Step 1: Update `_PROB_EXTRACTION_PROMPT` to capture `evidence_subtype`**

Replace `_PROB_EXTRACTION_PROMPT` (lines 139–163):

```python
_PROB_EXTRACTION_PROMPT = """\
You are extracting incident frequency data from a cybersecurity industry report.

IMPORTANT: Most published cybersecurity reports contain prevalence rates — the percentage
of surveyed organizations that experienced an incident in a given year. These are NOT
per-organization annual probabilities. Extract them as-is and label their type accurately.

For each percentage figure found that relates to incident frequency or prevalence:
- scenario_tag: classify into one of: System intrusion, Ransomware, Accidental disclosure, Physical threat, Insider misuse, DoS attack, Scam or fraud, Defacement, System failure
- sector: the industry sector this applies to
- probability_pct: the percentage value as a float
- evidence_subtype: one of:
    "prevalence_survey"  — % of surveyed organisations affected (most common in reports)
    "frequency_rate"     — incidents per organisation per year (rare, usually in ICS reports)
    "expert_estimate"    — stated as an expert judgement or model output
    "unknown"            — cannot determine
- note: brief description of what this percentage represents and its population
- raw_quote: the exact text excerpt (max 200 chars)
- context_tag: one of "asset_specific", "company_scale", "both", or "general"
  "asset_specific" if the source mentions OT/ICS/SCADA/industrial/wind/turbine/control system
  "company_scale" if the source mentions enterprise/large organization/sector-wide/>1000 employees
  "both" if it matches both criteria
  "general" if neither

Return ONLY a JSON array. If no probability figures found, return [].

Text to analyze:
{raw_text}"""
```

- [ ] **Step 2: Add `evidence_type` computation in `validate_scenario()` after `prob_confidence` is set**

```python
    # Probability evidence type: derived from what Haiku found
    prob_evidence_subtypes = {
        f.get("evidence_subtype", "unknown")
        for f in all_prob_figs
        if f.get("evidence_subtype") and f.get("evidence_subtype") != "unknown"
    }
    if not prob_evidence_subtypes or prob_evidence_subtypes == {"prevalence_survey"}:
        prob_evidence_type = "prevalence_survey"
    elif prob_evidence_subtypes == {"frequency_rate"}:
        prob_evidence_type = "frequency_rate"
    else:
        prob_evidence_type = "mixed"
```

- [ ] **Step 3: Add `evidence_type` to `prob_result` dict**

```python
    prob_result = {
        "vacr_probability_pct": vacr_pct,
        "verdict": prob_verdict,
        "verdict_confidence": prob_confidence,
        "evidence_type": prob_evidence_type,
        "benchmark_range_pct": prob_range,
        "registered_sources": prob_registered_out,
        "new_sources": prob_new_out,
        "recommendation": "",
    }
```

- [ ] **Step 4: Replace `_RECOMMENDATION_PROMPT` to include evidence type context**

```python
_RECOMMENDATION_PROMPT = """\
You are a cyber risk analyst reviewing VaCR (Value at Cyber Risk) validation results.

Register context: {company_context}
Scenario: {scenario_name}
Description: {scenario_description}

Financial validation:
  - Register VaCR: ${vacr_usd:,}
  - Benchmark range from peer industry sources: {fin_range}
  - Verdict: {fin_verdict} ({fin_source_count} sources, data confidence: {fin_confidence})

Probability validation:
  - Register probability: {prob_pct}%
  - Benchmark range from industry sources: {prob_range}
  - Verdict: {prob_verdict} ({prob_source_count} sources, data confidence: {prob_confidence})
  - Evidence type: {prob_evidence_type}

IMPORTANT — PROBABILITY EVIDENCE:
- "prevalence_survey": figures are % of organisations surveyed that experienced the incident.
  These are NOT per-organisation annual frequencies. The probability verdict is directional
  only — state this explicitly in your note.
- "frequency_rate": figures are incidents per organisation per year — more directly comparable.
- "mixed": sources include both types — note the limitation.

Write a concise analyst note (2-3 sentences) addressing:
1. Whether the financial figure appears well-calibrated against peer sector data. If data
   confidence is "low", say the benchmark is from general sector sources, not asset-specific.
2. What the probability evidence type means for the reliability of that verdict.
3. If either verdict is "insufficient", what specific source types would strengthen this.

Tone: direct, no jargon, no financial advice language. Plain text only."""
```

- [ ] **Step 5: Update `_build_recommendation_sonnet` to pass new fields into the prompt**

In `_build_recommendation_sonnet`, update the `prompt = _RECOMMENDATION_PROMPT.format(...)` call:

```python
    prompt = _RECOMMENDATION_PROMPT.format(
        company_context=register.get("company_context", ""),
        scenario_name=scenario["scenario_name"],
        scenario_description=scenario.get("description", ""),
        vacr_usd=fin.get("vacr_figure_usd") or 0,
        fin_range=_fmt_fin_range(fin.get("benchmark_range_usd")),
        fin_verdict=fin.get("verdict", "insufficient"),
        fin_confidence=fin.get("verdict_confidence", "low"),
        fin_source_count=len(all_sources),
        prob_pct=prob.get("vacr_probability_pct") or 0,
        prob_range=_fmt_prob_range(prob.get("benchmark_range_pct")),
        prob_verdict=prob.get("verdict", "insufficient"),
        prob_confidence=prob.get("verdict_confidence", "low"),
        prob_source_count=len(prob_all_sources),
        prob_evidence_type=prob.get("evidence_type", "prevalence_survey"),
    )
```

- [ ] **Step 6: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat: probability evidence_type field + update Sonnet prompt to caveat prevalence vs frequency data"
```

---

## Task 4: Move Recommendation to Scenario Level

**Files:**
- Modify: `tools/register_validator.py` — remove `recommendation` from `fin_result`/`prob_result`, add to scenario root
- Modify: `static/app.js` — read `recommendation` from `valScenario`, remove from `_renderRegValDimension`, add `recommendationZone` to `_renderScenarioDetail`

**Context:** The same recommendation string is currently stored in both `financial.recommendation` and `probability.recommendation`. It belongs at scenario level — it's one analyst note covering both dimensions. This removes the duplication and surfaces the note more prominently in the UI.

**Depends on:** Task 3 (recommendation prompt updated)  
**Feeds into:** nothing

---

- [ ] **Step 1: Remove `"recommendation": ""` from `fin_result` and `prob_result` in `validate_scenario()`**

Find both dict constructions and remove the `"recommendation": "",` line from each.

- [ ] **Step 2: Move recommendation to scenario return dict**

Change lines 625–627 from:

```python
recommendation = _build_recommendation_sonnet(scenario, register, fin_result, prob_result)
fin_result["recommendation"] = recommendation
prob_result["recommendation"] = recommendation
```

To:

```python
recommendation = _build_recommendation_sonnet(scenario, register, fin_result, prob_result)
```

Update the return dict:

```python
    return {
        "scenario_id": scenario["scenario_id"],
        "scenario_name": scenario["scenario_name"],
        "asset_context_note": asset_context_note,
        "recommendation": recommendation,
        "financial": fin_result,
        "probability": prob_result,
    }
```

- [ ] **Step 3: Remove `d.recommendation` render from `_renderRegValDimension` in `static/app.js`**

Find and delete this line inside the expand body div in `_renderRegValDimension`:

```js
      ${d.recommendation ? `<div style="margin-top:8px;padding:8px 10px;background:#080c10;border-left:2px solid ${borderColor};font-size:10px;color:#8b949e;line-height:1.6;font-family:'IBM Plex Sans',sans-serif">${esc(d.recommendation)}</div>` : ''}
```

- [ ] **Step 4: Add `recommendationZone` to `_renderScenarioDetail` in `static/app.js`**

In `_renderScenarioDetail`, after building `validationZone`, add:

```js
  const recommendationZone = valScenario?.recommendation
    ? `<div style="margin:0 12px 14px 12px;padding:10px 12px;background:#080c10;border:1px solid #21262d;border-radius:3px">
        <div style="font-size:8px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#484f58;margin-bottom:6px;font-family:'IBM Plex Mono',monospace">Analyst Note</div>
        <div style="font-size:10px;color:#8b949e;line-height:1.7;font-family:'IBM Plex Sans',sans-serif">${esc(valScenario.recommendation)}</div>
      </div>`
    : '';
```

Update `el.innerHTML` to include it after `validationZone`:

```js
  el.innerHTML = `
    ...header...
    ${descZone}
    ${numbersZone}
    ${validationZone}
    ${recommendationZone}`;
```

- [ ] **Step 5: Commit**

```bash
git add tools/register_validator.py static/app.js
git commit -m "refactor: move recommendation to scenario level — remove duplication from fin/prob result dicts"
```

---

## Task 5: Minor Fixes + Evidence Type UI Badge

**Files:**
- Modify: `tools/register_validator.py` — dynamic year list, log silent exception, move `mkdir`, remove `smb_scale_flag` from prompts
- Modify: `static/app.js` — evidence type caveat badge in probability expand body

**Depends on:** Task 3 (`evidence_type` exists in prob_result)

---

- [ ] **Step 1: Fix `check_source_versions` — dynamic year list (lines 475–477)**

Replace:

```python
for year in [2025, 2026]:
```

With:

```python
current_year = datetime.now().year
for year in range(edition_year + 1, current_year + 2):
```

- [ ] **Step 2: Add logging to silent `except` block in `check_source_versions` (lines 491–498)**

```python
        except Exception as e:
            print(f"[register_validator] Version check failed ({name[:40]}): {e}", file=sys.stderr)
            version_checks.append({
                "source_id": source_id,
                "name": name,
                "edition_year": edition_year,
                "newer_version_found": False,
                "newer_year": None,
                "url": None,
            })
```

- [ ] **Step 3: Move `OUTPUT_PATH.parent.mkdir(...)` from module level (line 31) into `main()`**

Remove line 31: `OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)`

Add as first line of `main()`:

```python
def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    register = load_active_register()
    ...
```

- [ ] **Step 4: Remove `- smb_scale_flag: false` from `_FIN_EXTRACTION_PROMPT` and `_PROB_EXTRACTION_PROMPT`**

In `_FIN_EXTRACTION_PROMPT`, delete the line:
```
- smb_scale_flag: false
```

In `_PROB_EXTRACTION_PROMPT`, delete the line:
```
- smb_scale_flag: false
```

These fields are computed deterministically in Python after extraction. Keeping them in LLM prompts creates noise and risks Haiku overriding the computed value.

- [ ] **Step 5: Add evidence type caveat badge in probability expand body in `_renderRegValDimension` (`static/app.js`)**

At the top of `_renderRegValDimension`, after `const expandId = ...`, add:

```js
  const isProb = dim === 'probability';
  const evidenceCaveat = isProb
    ? ({
        prevalence_survey: `<span style="font-size:8px;color:#6e7681;font-family:'IBM Plex Mono',monospace;background:#0d1117;border:1px solid #21262d;border-radius:2px;padding:1px 5px">PREVALENCE SURVEY</span>`,
        frequency_rate:    `<span style="font-size:8px;color:#3fb950;font-family:'IBM Plex Mono',monospace;background:#0a1f0a;border:1px solid #1a4d1a;border-radius:2px;padding:1px 5px">FREQUENCY DATA</span>`,
        mixed:             `<span style="font-size:8px;color:#e3b341;font-family:'IBM Plex Mono',monospace;background:#1f1700;border:1px solid #4a3800;border-radius:2px;padding:1px 5px">MIXED EVIDENCE</span>`,
      }[d.evidence_type] || '')
    : '';
```

In the expand body div, add evidence type row before `sourcesHtml`:

```js
    <div id="${expandId}" style="display:block;background:#060a0f;padding:8px 10px;border-top:1px solid #0d1117">
      ${isProb && evidenceCaveat ? `<div style="margin-bottom:8px;font-size:9px;color:#6e7681;font-family:'IBM Plex Sans',sans-serif">Evidence type: ${evidenceCaveat}</div>` : ''}
      ${sourcesHtml}
    </div>
```

- [ ] **Step 6: Final smoke test**

```bash
uv run python tools/register_validator.py
```

Then verify output schema:

```bash
python -c "
import json
from pathlib import Path
data = json.loads(Path('output/validation/register_validation.json').read_text())
s = data['scenarios'][0]
assert 'recommendation' in s, 'recommendation missing from scenario root'
assert 'recommendation' not in s['financial'], 'recommendation still in financial'
assert 'recommendation' not in s['probability'], 'recommendation still in probability'
assert 'verdict_confidence' in s['financial'], 'verdict_confidence missing from financial'
assert 'verdict_confidence' in s['probability'], 'verdict_confidence missing from probability'
assert 'evidence_type' in s['probability'], 'evidence_type missing from probability'
print('fin verdict_confidence:', s['financial']['verdict_confidence'])
print('prob evidence_type:', s['probability']['evidence_type'])
print('recommendation:', s['recommendation'][:80])
print('ALL CHECKS PASS')
"
```

Expected: `ALL CHECKS PASS`

- [ ] **Step 7: Commit**

```bash
git add tools/register_validator.py static/app.js static/index.html
git commit -m "fix: dynamic year list, log silent exception, mkdir side effect, smb_flag prompt noise, evidence_type UI badge"
```

---

## Spec Coverage Check

| Review finding | Task |
|---|---|
| OT query branches dropped; single-query iteration | Task 1 Steps 2–3 |
| Phase 1 source cap silent truncation | Task 1 Steps 1, 4 |
| `context_tag` not used in verdict confidence | Task 2 |
| Probability evidence type wrong; Sonnet not told | Task 3 |
| Recommendation duplicated in fin/prob | Task 4 |
| Version check year list hardcoded | Task 5 Step 1 |
| Silent exception in `check_source_versions` | Task 5 Step 2 |
| `mkdir` at module level | Task 5 Step 3 |
| `smb_scale_flag` in LLM prompts | Task 5 Step 4 |
| Evidence type caveat in UI | Task 5 Step 5 |
