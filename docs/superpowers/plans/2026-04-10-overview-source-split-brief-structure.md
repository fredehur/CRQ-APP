# Overview Source Split + Brief Structure Plan

**Goal:** Two linked improvements that make the pipeline's intelligence sources visible in the right places and create a shared narrative spine across all output formats.

**Part 1 — Overview source boxes:** Dashboard Overview gets two structured metadata boxes per region — Seerist (strength level, hotspot names, pulse delta) and OSINT (source count, named publications, signal type). No analyst instruction changes. Derived from `seerist_signals.json` and `osint_signals.json` directly, not from claim text.

**Part 2 — Brief structure headlines:** Analyst writes three explicit summary lines in `claims.json` (`why_summary`, `how_summary`, `so_what_summary`). `extract_sections.py` passes them through as `brief_headlines`. CISO, Board, and RSM all open each section with the same sentence — written once by the analyst, rendered consistently across every format. This is the shared narrative spine.

**Why not heuristic extraction?** "First fact claim in paragraph" assumes claim ordering reflects importance — it doesn't. The analyst writes claims in the order they come to mind. The headline-quality sentence may be claim 3. Explicit summary fields cost ~30 words of analyst work and produce real quality. A heuristic produces technically correct but narratively weak openers.

**Architecture:** `extract_sections.py` is the single writer — source metadata and headlines both land in `sections.json`. All consumers (Overview, CISO, Board, RSM) read from the same endpoint. No new files, no new endpoints.

**Tech Stack:** Python 3.11 · pytest · `tools/extract_sections.py` · `output/regional/{region}/sections.json` · `static/app.js` · `static/index.html` · `tools/export_ciso_docx.py` · `tools/report_builder.py` · `tools/rsm_input_builder.py` · `.claude/agents/regional-analyst-agent.md` · `.claude/agents/rsm-formatter-agent.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `.claude/agents/regional-analyst-agent.md` | Modify | Add `why_summary`, `how_summary`, `so_what_summary` to claims.json output instruction |
| `tools/extract_sections.py` | Modify | Add `_build_source_metadata()` + pass through summary fields as `brief_headlines` |
| `tests/test_extract_sections_source_split.py` | Create | Unit tests for source metadata + headline pass-through + `extract()` integration |
| `static/index.html` | Modify | Two structured source boxes in Overview panel |
| `static/app.js` | Modify | Read `source_metadata` and `brief_headlines` from sections API |
| `tools/export_ciso_docx.py` | Modify | Use `brief_headlines` as section subheadings |
| `tools/report_builder.py` | Modify | Use `brief_headlines` in board report section cards |
| `tools/rsm_input_builder.py` | Modify | Include `brief_headlines` in RSM input payload |
| `.claude/agents/rsm-formatter-agent.md` | Modify | Use `brief_headlines` as alert section openers |

---

## Data contract: new fields in sections.json

```json
{
  "intel_bullets": [...],
  "adversary_bullets": [...],
  "impact_bullets": [...],
  "watch_bullets": [...],
  "action_bullets": [...],
  "signal_type_label": "...",
  "status_label": "...",

  "source_metadata": {
    "seerist": {
      "strength": "high",
      "hotspots": ["Taipei — anomaly_flag", "Manila — elevated"],
      "pulse_delta": -0.7,
      "verified_event_count": 1
    },
    "osint": {
      "source_count": 6,
      "sources": ["Reuters", "Mandiant", "Chatham House"],
      "signal_type": "Confirmed Incident + Emerging Pattern"
    }
  },

  "brief_headlines": {
    "why": "Taiwan Strait tensions elevated following PLA naval exercise expansion",
    "how": "State-aligned actors pivoting to supply chain intrusion against energy OEMs",
    "so_what": "Taipei Blade Manufacturing faces elevated physical disruption and IP theft risk"
  }
}
```

`source_metadata` drives the Overview boxes — structured, operator-facing, not prose. `brief_headlines` drives all report formats — analyst-written, consistent across CISO/Board/RSM.

---

## Task 1: Add summary fields to analyst output contract

**Files:**
- Modify: `.claude/agents/regional-analyst-agent.md`

Add to the STEP 4 — WRITE CLAIMS section, after the existing claims schema:

- [ ] **Step 1: Add summary fields instruction**

Find the instruction block that describes `claims.json` structure. Add after the `convergence_assessment` instruction:

```markdown
**Summary fields (required — write these before the claims array):**

After writing `convergence_assessment`, add three summary fields — one sentence each:

```json
{
  "convergence_assessment": { "category": "CONVERGE", "rationale": "..." },
  "why_summary": "Taiwan Strait tensions elevated following PLA naval exercise expansion",
  "how_summary": "State-aligned actors pivoting to supply chain intrusion against energy OEMs",
  "so_what_summary": "Taipei Blade Manufacturing faces elevated physical disruption and IP theft risk",
  "claims": [...]
}
```

Rules:
- Each summary is one declarative sentence. No hedging, no "it is assessed that."
- `why_summary` — the world event or structural condition driving the threat. No AeroGrid.
- `how_summary` — the observed adversary behaviour or threat vector. No AeroGrid assets.
- `so_what_summary` — the operational consequence for AeroGrid. This is the only sentence where AeroGrid is named.
- These become the opening line of every downstream report format — CISO, Board, RSM. Write them accordingly.
```

- [ ] **Step 2: Add to Self-Validation Checklist**

```markdown
- [ ] `why_summary`, `how_summary`, `so_what_summary` present in claims.json — one sentence each, no hedging
```

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/regional-analyst-agent.md
git commit -m "feat(analyst): add why/how/so_what summary fields to claims.json output contract"
```

---

## Task 2: Extend `extract_sections.py`

**Files:**
- Modify: `tools/extract_sections.py`
- Test: `tests/test_extract_sections_source_split.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_extract_sections_source_split.py
"""Tests for source metadata, headline pass-through, and extract() integration."""
import json
import pytest
from pathlib import Path


# --- Fixtures ---

def _make_seerist(hotspots=None, verified=None, avg_delta=0.0):
    return {
        "situational": {
            "events": [],
            "verified_events": verified or [],
            "breaking_news": [],
            "news": [],
        },
        "analytical": {
            "hotspots": hotspots or [],
            "pulse": {"region_summary": {"avg_delta": avg_delta}},
        },
    }


def _make_osint(sources=None, signal_type="Emerging Pattern"):
    return {
        "dominant_pillar": "geo",
        "signal_type": signal_type,
        "sources": sources or [],
        "lead_indicators": [],
    }


def _make_claims(why_summary="Why headline", how_summary="How headline",
                 so_what_summary="So what headline"):
    return {
        "region": "APAC",
        "convergence_assessment": {"category": "CONVERGE", "rationale": "Test"},
        "why_summary": why_summary,
        "how_summary": how_summary,
        "so_what_summary": so_what_summary,
        "claims": [],
    }


# --- Source metadata tests ---

def test_seerist_metadata_high_strength_with_hotspot():
    from tools.extract_sections import _build_source_metadata
    seerist = _make_seerist(hotspots=[
        {"signal_id": "seerist:hotspot:apac-001", "anomaly_flag": True, "location": "Taipei"},
    ])
    osint = _make_osint(sources=[{"name": "Reuters", "url": "https://reuters.com"}])
    meta = _build_source_metadata(seerist, osint)
    assert meta["seerist"]["strength"] == "high"
    assert "Taipei" in meta["seerist"]["hotspots"][0]


def test_seerist_metadata_none_when_empty():
    from tools.extract_sections import _build_source_metadata
    meta = _build_source_metadata({}, {})
    assert meta["seerist"]["strength"] == "none"
    assert meta["seerist"]["hotspots"] == []


def test_osint_metadata_source_count_and_names():
    from tools.extract_sections import _build_source_metadata
    osint = _make_osint(sources=[
        {"name": "Reuters", "url": "https://reuters.com"},
        {"name": "Mandiant", "url": "https://mandiant.com"},
    ])
    meta = _build_source_metadata({}, osint)
    assert meta["osint"]["source_count"] == 2
    assert "Reuters" in meta["osint"]["sources"]
    assert "Mandiant" in meta["osint"]["sources"]


def test_osint_metadata_deduplicates_sources():
    from tools.extract_sections import _build_source_metadata
    osint = _make_osint(sources=[
        {"name": "Reuters", "url": "https://reuters.com"},
        {"name": "Reuters", "url": "https://reuters.com/other"},
    ])
    meta = _build_source_metadata({}, osint)
    assert meta["osint"]["source_count"] == 1


# --- Headline pass-through tests ---

def test_brief_headlines_extracted_from_summary_fields():
    from tools.extract_sections import _extract_brief_headlines
    claims_data = _make_claims(
        why_summary="PLA drills elevate cross-strait risk",
        how_summary="APT actors targeting OT networks",
        so_what_summary="Taipei manufacturing faces disruption risk",
    )
    h = _extract_brief_headlines(claims_data)
    assert h["why"] == "PLA drills elevate cross-strait risk"
    assert h["how"] == "APT actors targeting OT networks"
    assert h["so_what"] == "Taipei manufacturing faces disruption risk"


def test_brief_headlines_default_to_empty_string_when_absent():
    from tools.extract_sections import _extract_brief_headlines
    h = _extract_brief_headlines({})
    assert h["why"] == ""
    assert h["how"] == ""
    assert h["so_what"] == ""


# --- Integration test: extract() writes new fields to disk ---

def test_extract_writes_source_metadata_and_headlines(tmp_path, monkeypatch):
    import tools.extract_sections as es
    monkeypatch.setattr(es, "OUTPUT_ROOT", tmp_path / "output")

    region_dir = tmp_path / "output" / "regional" / "apac"
    region_dir.mkdir(parents=True)

    (region_dir / "claims.json").write_text(json.dumps(_make_claims(
        why_summary="Why test",
        how_summary="How test",
        so_what_summary="So what test",
    )))
    (region_dir / "seerist_signals.json").write_text(json.dumps(_make_seerist(
        hotspots=[{"signal_id": "seerist:hotspot:apac-001", "anomaly_flag": True, "location": "Taipei"}]
    )))
    (region_dir / "osint_signals.json").write_text(json.dumps(_make_osint(
        sources=[{"name": "Reuters", "url": "https://reuters.com"}]
    )))
    (region_dir / "data.json").write_text(json.dumps({"dominant_pillar": "geo"}))

    es.extract("APAC")

    sections = json.loads((region_dir / "sections.json").read_text())
    assert "source_metadata" in sections
    assert sections["source_metadata"]["seerist"]["strength"] == "high"
    assert sections["source_metadata"]["osint"]["source_count"] == 1
    assert "brief_headlines" in sections
    assert sections["brief_headlines"]["why"] == "Why test"
    assert sections["brief_headlines"]["how"] == "How test"
    assert sections["brief_headlines"]["so_what"] == "So what test"
```

- [ ] **Step 2: Run tests to verify they fail**

```
PYTHONPATH=. uv run pytest tests/test_extract_sections_source_split.py -v
```
Expected: `ImportError` — functions don't exist yet

- [ ] **Step 3: Add `_build_source_metadata()` and `_extract_brief_headlines()` to `extract_sections.py`**

Add import at top:
```python
from tools.seerist_strength import score_seerist_strength
```

Add two new functions after `_get_action_bullets()`:

```python
def _build_source_metadata(seerist: dict, osint: dict) -> dict:
    """Build structured source metadata for Overview boxes.

    Reads seerist_signals.json and osint_signals.json directly — not from claims.
    Seerist box: strength level, anomaly hotspot names, pulse delta, verified event count.
    OSINT box: deduplicated source names, count, signal type.
    """
    # Seerist metadata
    strength = score_seerist_strength(seerist)
    ana = seerist.get("analytical", {})
    sit = seerist.get("situational", {})

    hotspot_labels = [
        f"{h.get('location', h.get('signal_id', '?'))} — anomaly"
        for h in ana.get("hotspots", [])
        if h.get("anomaly_flag")
    ]
    pulse_delta = ana.get("pulse", {}).get("region_summary", {}).get("avg_delta", 0.0)
    verified_count = len(sit.get("verified_events", []))

    # OSINT metadata
    raw_sources = osint.get("sources", [])
    seen_names: set[str] = set()
    unique_sources: list[str] = []
    for s in raw_sources:
        name = s.get("name", "")
        if name and name not in seen_names:
            seen_names.add(name)
            unique_sources.append(name)

    return {
        "seerist": {
            "strength": strength,
            "hotspots": hotspot_labels,
            "pulse_delta": pulse_delta,
            "verified_event_count": verified_count,
        },
        "osint": {
            "source_count": len(unique_sources),
            "sources": unique_sources,
            "signal_type": osint.get("signal_type", ""),
        },
    }


def _extract_brief_headlines(claims_data: dict) -> dict:
    """Pass through analyst-written summary fields as brief_headlines.

    Reads why_summary, how_summary, so_what_summary from claims.json top level.
    Returns empty strings if any field is absent — never None.
    """
    return {
        "why": claims_data.get("why_summary", ""),
        "how": claims_data.get("how_summary", ""),
        "so_what": claims_data.get("so_what_summary", ""),
    }
```

In `extract()`, load the two signal files and add the new fields:

```python
    # Load signal files for source metadata
    seerist: dict = {}
    osint: dict = {}
    seerist_path = base / "seerist_signals.json"
    osint_path = base / "osint_signals.json"
    if seerist_path.exists():
        try:
            seerist = json.loads(seerist_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    if osint_path.exists():
        try:
            osint = json.loads(osint_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    grouped["source_metadata"] = _build_source_metadata(seerist, osint)
    grouped["brief_headlines"] = _extract_brief_headlines(claims_data)
```

- [ ] **Step 4: Run tests to verify they pass**

```
PYTHONPATH=. uv run pytest tests/test_extract_sections_source_split.py -v
```
Expected: all tests PASS

- [ ] **Step 5: Run full Seerist test suite — no regressions**

```
PYTHONPATH=. uv run pytest tests/test_seerist_strength.py tests/test_collection_gate.py tests/test_stop_hook_gate4.py tests/test_extract_sections_source_split.py -v
```

- [ ] **Step 6: Commit**

```bash
git add tools/extract_sections.py tests/test_extract_sections_source_split.py
git commit -m "feat: extract_sections adds source_metadata and brief_headlines to sections.json"
```

---

## Task 3: Dashboard Overview — structured source boxes

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`

The two boxes show structured metadata, not prose bullets. Operators see what they need: signal strength, hotspot locations, source names.

- [ ] **Step 1: Add source box HTML to index.html**

```html
<!-- Source Intelligence Boxes — Overview only -->
<div id="source-split-panel" class="source-split-panel hidden">
  <div class="source-box source-box--seerist">
    <div class="source-box-header">Seerist</div>
    <div id="seerist-strength-badge" class="source-strength-badge"></div>
    <ul id="seerist-detail-list" class="source-detail-list"></ul>
  </div>
  <div class="source-box source-box--osint">
    <div class="source-box-header">OSINT</div>
    <div id="osint-source-count" class="source-count-label"></div>
    <ul id="osint-sources-list" class="source-detail-list"></ul>
  </div>
</div>
```

CSS:
```css
.source-split-panel {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1.25rem;
}
.source-box {
  background: var(--surface-2, #1e2533);
  border-radius: 8px;
  padding: 0.875rem 1rem;
  border-top: 3px solid transparent;
}
.source-box--seerist { border-top-color: #f59e0b; }
.source-box--osint   { border-top-color: #4a9eff; }
.source-box-header {
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted, #8892a4);
  margin-bottom: 0.5rem;
}
.source-strength-badge {
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  display: inline-block;
  margin-bottom: 0.4rem;
}
.source-strength-badge.high   { background: #7f1d1d; color: #fca5a5; }
.source-strength-badge.low    { background: #713f12; color: #fcd34d; }
.source-strength-badge.none   { background: #1f2937; color: #6b7280; }
.source-count-label {
  font-size: 0.75rem;
  color: var(--text-muted, #8892a4);
  margin-bottom: 0.4rem;
}
.source-detail-list {
  margin: 0; padding: 0 0 0 1rem;
  font-size: 0.78rem;
  color: var(--text-secondary, #c9d1e0);
  line-height: 1.5;
}
.source-detail-list li { margin-bottom: 0.2rem; }
```

- [ ] **Step 2: Wire source boxes in app.js**

```javascript
function _renderSourceBoxes(sections) {
  const panel = document.getElementById('source-split-panel');
  if (!panel) return;

  const sm = sections.source_metadata;
  if (!sm) { panel.classList.add('hidden'); return; }

  // Seerist box
  const s = sm.seerist || {};
  const strengthBadge = document.getElementById('seerist-strength-badge');
  const seeristList = document.getElementById('seerist-detail-list');
  if (strengthBadge) {
    strengthBadge.textContent = `Strength: ${(s.strength || 'none').toUpperCase()}`;
    strengthBadge.className = `source-strength-badge ${s.strength || 'none'}`;
  }
  if (seeristList) {
    const items = [];
    if (s.hotspots && s.hotspots.length) s.hotspots.forEach(h => items.push(h));
    if (s.verified_event_count) items.push(`${s.verified_event_count} verified event(s)`);
    if (typeof s.pulse_delta === 'number' && s.pulse_delta !== 0)
      items.push(`Pulse delta: ${s.pulse_delta.toFixed(1)}`);
    seeristList.innerHTML = items.length
      ? items.map(t => `<li>${_esc(t)}</li>`).join('')
      : '<li><em>No substantive signals</em></li>';
  }

  // OSINT box
  const o = sm.osint || {};
  const countLabel = document.getElementById('osint-source-count');
  const osintList = document.getElementById('osint-sources-list');
  if (countLabel) countLabel.textContent = `${o.source_count || 0} sources`;
  if (osintList) {
    const srcs = o.sources || [];
    osintList.innerHTML = srcs.length
      ? srcs.map(n => `<li>${_esc(n)}</li>`).join('')
      : '<li><em>No named sources</em></li>';
  }

  panel.classList.remove('hidden');
}
```

Call `_renderSourceBoxes(sections)` from `_renderSections()`.

- [ ] **Step 3: Verify visually**

Run server, load APAC in Overview. Confirm:
- Seerist box: amber top border, strength badge with correct colour, hotspot names, pulse delta
- OSINT box: blue top border, source count, named publications
- Boxes hidden when `source_metadata` absent

- [ ] **Step 4: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat: Overview structured source boxes — Seerist strength + OSINT sources"
```

---

## Task 4: Wire `brief_headlines` into CISO report

**Files:**
- Modify: `tools/export_ciso_docx.py`

The CISO report currently has prose section headers (Why / How / So What). Replace each header with the analyst-written headline, then follow with bullet points. Eliminates the redundant Header → **Bold sentence** → bullets problem.

- [ ] **Step 1: Load `brief_headlines` from sections.json**

```python
brief_headlines = sections.get("brief_headlines", {})
why_headline    = brief_headlines.get("why", "")
how_headline    = brief_headlines.get("how", "")
so_what_headline = brief_headlines.get("so_what", "")
```

- [ ] **Step 2: Use headline as section subheading**

For each paragraph block, replace the static section header with the headline sentence, styled as a subheading (not bold inline text). If headline is empty, fall back to the static header.

```python
# Why section
_add_section_heading(doc, why_headline or "Geopolitical Driver")
for bullet in intel_bullets:
    doc.add_paragraph(bullet, style="List Bullet")

# How section
_add_section_heading(doc, how_headline or "Cyber Vector")
for bullet in adversary_bullets:
    doc.add_paragraph(bullet, style="List Bullet")

# So What section
_add_section_heading(doc, so_what_headline or "Business Impact")
for bullet in impact_bullets:
    doc.add_paragraph(bullet, style="List Bullet")
```

- [ ] **Step 3: Verify a generated CISO docx**

```bash
PYTHONPATH=. uv run python tools/export_ciso_docx.py APAC
```

Confirm: section headings are analyst-written sentences, not generic labels.

- [ ] **Step 4: Commit**

```bash
git add tools/export_ciso_docx.py
git commit -m "feat(ciso): use brief_headlines as section headings in CISO Word brief"
```

---

## Task 5: Wire `brief_headlines` into Board report

**Files:**
- Modify: `tools/report_builder.py`

The board report renders region cards. Each card currently has a scenario name and bullet list. After this task, each card opens with the `so_what_summary` — the one sentence that answers "what does this mean for us."

- [ ] **Step 1: Load `brief_headlines` from sections.json per region in report_builder.py**

In the region card builder, after loading sections:
```python
headlines = sections.get("brief_headlines", {})
card["so_what_headline"] = headlines.get("so_what", "")
card["why_headline"] = headlines.get("why", "")
```

- [ ] **Step 2: Render headlines in board card template**

In the Jinja2/HTML template for region cards, add headline above the bullets:
```html
{% if card.so_what_headline %}
<p class="card-headline">{{ card.so_what_headline }}</p>
{% endif %}
```

- [ ] **Step 3: Commit**

```bash
git add tools/report_builder.py
git commit -m "feat(board): add so_what headline to region cards"
```

---

## Task 6: Wire `brief_headlines` into RSM input builder

**Files:**
- Modify: `tools/rsm_input_builder.py`
- Modify: `.claude/agents/rsm-formatter-agent.md`

- [ ] **Step 1: Add `brief_headlines` to RSM input payload**

```python
payload["brief_headlines"] = sections.get("brief_headlines", {})
```

- [ ] **Step 2: Update rsm-formatter-agent.md**

```markdown
- `brief_headlines.why` — opening sentence for the geopolitical driver section
- `brief_headlines.how` — opening sentence for the threat activity section
- `brief_headlines.so_what` — opening sentence for the business impact section

Use these verbatim as the first sentence of each corresponding section. Do not paraphrase.
These are the shared narrative anchor across CISO, Board, and RSM formats.
```

- [ ] **Step 3: Commit**

```bash
git add tools/rsm_input_builder.py .claude/agents/rsm-formatter-agent.md
git commit -m "feat(rsm): add brief_headlines to RSM input for narrative consistency"
```

---

## Task 7: Integration test

- [ ] **Step 1: Run extract_sections for APAC and inspect sections.json**

```bash
PYTHONPATH=. uv run python tools/extract_sections.py APAC
python -c "import json; d=json.load(open('output/regional/apac/sections.json')); print(json.dumps({k: d[k] for k in ['source_metadata','brief_headlines']}, indent=2))"
```

Expected: `source_metadata` with seerist strength + OSINT sources; `brief_headlines` with three non-empty strings.

- [ ] **Step 2: Verify CISO docx headlines**

```bash
PYTHONPATH=. uv run python tools/export_ciso_docx.py APAC
```

Open the output — section headings should be the analyst's summary sentences.

- [ ] **Step 3: Full mock pipeline**

```
/crq-region APAC
```

Confirm: Overview shows structured source boxes, CISO sections open with analyst-written headlines.

---

## Self-Review

**What changed from v1:**

| v1 (heuristic) | v2 (this plan) |
|---|---|
| Headlines from "first fact claim" | Headlines from explicit `why/how/so_what_summary` fields |
| Source boxes show claim prose text | Source boxes show structured metadata (strength, hotspot names, source list) |
| Board report not included | Board report included (Task 5) |
| `"impact"` paragraph (doesn't exist) | No phantom paragraph references |
| No integration test for `extract()` | Task 2 includes `test_extract_writes_source_metadata_and_headlines` |
| 4 tasks | 7 tasks — cleaner separation of concerns |

**Design decisions:**
- `brief_headlines` is read-only pass-through in `extract_sections.py` — no logic, no fallbacks. If the analyst didn't write summary fields, headlines are empty strings. Downstream formats handle empty gracefully with static fallbacks.
- `source_metadata` reads `seerist_signals.json` and `osint_signals.json` directly — not from claims. Source intel is always available even if the analyst wrote no claims.
- All four consumers (Overview, CISO, Board, RSM) are wired — partial consistency is worse than no consistency.
