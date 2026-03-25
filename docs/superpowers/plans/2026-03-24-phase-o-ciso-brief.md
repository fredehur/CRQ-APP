# Phase O — CISO Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign PDF and PPTX board outputs to Clean Executive style. Derive four display sentences (Driver, Exposure, Impact, Watch) from existing pillar text. Remove all VaCR figures from rendered outputs. Update the regional analyst quality checklist.

**Spec:** `docs/superpowers/specs/2026-03-24-ciso-brief-design.md`

**Architecture:** No new pipeline step, no new agent. `report_builder.py` extracts brief sentences from existing `why_text / how_text / so_what_text`. Renderers (HTML template + PPTX) read `board_bullets` from `RegionEntry`. VaCR stays on the data model for the analyst web app — it is not rendered in the CISO output paths.

---

## File Map

| File | Change |
|------|--------|
| `tools/report_builder.py` | Add `board_bullets`, `dominant_pillar`, `signal_type` to `RegionEntry`; add `_extract_brief_sentences()`; update `build()` |
| `.claude/agents/regional-analyst-agent.md` | Add one quality check: So What opens with operational consequence |
| `tools/templates/report.html.j2` | Full redesign: Clean Executive style, 2×2 grid, no VaCR |
| `tools/export_pptx.py` | Redesign cover/exec/region slides; no VaCR; 2×2 board_bullets grid |
| `tests/test_report_builder.py` | Add `_extract_brief_sentences` tests |
| `tests/test_export_pdf.py` | Update VaCR and pillar-label tests; add no-VaCR assertion |
| `tests/test_export_pptx.py` | Update cover-title and admiralty tests; add new structural assertions |

---

## Task 1: `report_builder.py` — data model + sentence extractor

**Files:** `tools/report_builder.py`, `tests/test_report_builder.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_report_builder.py`)

```python
from report_builder import _extract_brief_sentences

def test_extract_brief_sentences_normal():
    why = "State actors are exploiting supply chain access. Secondary activity continues."
    how = "OT networks at blade plants are the primary target. Access via third-party VPN."
    so_what = "$18M at risk. Disruption threatens 75% of manufacturing revenue. Watch for escalation."
    result = _extract_brief_sentences(why, how, so_what)
    assert result is not None
    assert len(result) == 4
    assert result[0] == "State actors are exploiting supply chain access."   # Driver — first of why
    assert result[1] == "OT networks at blade plants are the primary target."  # Exposure — first of how
    assert result[2] == "Disruption threatens 75% of manufacturing revenue."   # Impact — first non-$ of so_what
    assert result[3] == "Watch for escalation."                                # Watch — last of so_what


def test_extract_brief_sentences_vacr_skip():
    """Impact must skip ALL leading $ sentences until a non-$ sentence is found."""
    so_what = "$18M at risk. $22M secondary exposure. Operations at all five APAC sites could halt."
    result = _extract_brief_sentences("Driver text.", "Exposure text.", so_what)
    assert result is not None
    assert result[2] == "Operations at all five APAC sites could halt."


def test_extract_brief_sentences_returns_none_if_pillar_missing():
    assert _extract_brief_sentences(None, "how", "so_what") is None
    assert _extract_brief_sentences("why", None, "so_what") is None
    assert _extract_brief_sentences("why", "how", None) is None


def test_extract_brief_sentences_single_so_what_sentence():
    """When so_what has only a $ sentence, watch == impact fallback."""
    so_what = "Operations will halt at the Tianjin facility."
    result = _extract_brief_sentences("Why text.", "How text.", so_what)
    assert result is not None
    assert result[2] == "Operations will halt at the Tianjin facility."
    assert result[3] == "Operations will halt at the Tianjin facility."  # same — only one sentence


def test_region_entry_has_board_bullets_field():
    """RegionEntry must accept board_bullets and new fields without errors."""
    from report_builder import RegionEntry, RegionStatus
    entry = RegionEntry(
        name="APAC", status=RegionStatus.ESCALATED,
        vacr=18_500_000.0, admiralty="B2", velocity="stable",
        severity="HIGH", scenario_match="System intrusion",
        why_text="w", how_text="h", so_what_text="s",
    )
    assert entry.board_bullets is None   # default
    assert entry.dominant_pillar is None  # default
    assert entry.signal_type is None      # default


def test_build_populates_board_bullets(mock_output):
    """build() must set board_bullets for escalated regions with pillar text."""
    from report_builder import build, RegionStatus
    data = build(output_dir=str(mock_output))
    apac = next(r for r in data.regions if r.name == "APAC")
    assert apac.status == RegionStatus.ESCALATED
    assert apac.board_bullets is not None
    assert len(apac.board_bullets) == 4
    # Driver = first sentence of why_text
    assert "State-sponsored" in apac.board_bullets[0]
    # Impact must not start with $
    assert not apac.board_bullets[2].startswith("$")


def test_build_populates_dominant_pillar(mock_output):
    from report_builder import build
    data = build(output_dir=str(mock_output))
    apac = next(r for r in data.regions if r.name == "APAC")
    assert apac.dominant_pillar == "Geopolitical"
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest tests/test_report_builder.py -k "extract_brief or board_bullets or dominant_pillar" -v
```

Expected: `FAILED` — `AttributeError: module 'report_builder' has no attribute '_extract_brief_sentences'`

- [ ] **Step 3: Implement in `tools/report_builder.py`**

Add to `RegionEntry` dataclass (append three optional fields at end — default=None so existing positional construction is not broken):

```python
@dataclass
class RegionEntry:
    name: str
    status: RegionStatus
    vacr: float | None
    admiralty: str | None
    velocity: str | None
    severity: str | None
    scenario_match: str | None
    why_text: str | None
    how_text: str | None
    so_what_text: str | None
    board_bullets: list[str] | None = None   # [Driver, Exposure, Impact, Watch]
    dominant_pillar: str | None = None
    signal_type: str | None = None
```

Add `_extract_brief_sentences()` after `_parse_pillars`:

```python
import re as _re

def _split_sentences(text: str) -> list[str]:
    """Split text into sentences. Handles '. ', '! ', '? ' boundaries."""
    return [s.strip() for s in _re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]


def _extract_brief_sentences(
    why: str | None,
    how: str | None,
    so_what: str | None,
) -> list[str] | None:
    """Derive four display sentences from three-pillar text.

    Returns [Driver, Exposure, Impact, Watch] or None if any pillar is absent/empty.
    Driver   = first sentence of why
    Exposure = first sentence of how
    Impact   = first sentence of so_what that does not contain '$'
    Watch    = last sentence of so_what
    """
    if not why or not how or not so_what:
        return None

    why_sents     = _split_sentences(why)
    how_sents     = _split_sentences(how)
    so_what_sents = _split_sentences(so_what)

    if not why_sents or not how_sents or not so_what_sents:
        return None

    driver   = why_sents[0]
    exposure = how_sents[0]

    # Impact: skip leading $ sentences
    impact = next((s for s in so_what_sents if "$" not in s), so_what_sents[-1])
    watch  = so_what_sents[-1]

    return [driver, exposure, impact, watch]
```

Update `build()` — inside the `if status == RegionStatus.ESCALATED:` block, after the pillar parse, add:

```python
        board_bullets = _extract_brief_sentences(why_text, how_text, so_what_text)
```

And update `regions.append(RegionEntry(...))` to pass the new fields:

```python
        regions.append(RegionEntry(
            ...existing fields...,
            board_bullets=board_bullets,
            dominant_pillar=d.get("dominant_pillar"),
            signal_type=d.get("signal_type"),
        ))
```

For non-escalated regions, `board_bullets` stays `None` (already the default), but still read `dominant_pillar` and `signal_type`:

```python
        regions.append(RegionEntry(
            ...
            board_bullets=None,
            dominant_pillar=d.get("dominant_pillar"),
            signal_type=d.get("signal_type"),
        ))
```

- [ ] **Step 4: Run tests — expect pass**

```bash
uv run pytest tests/test_report_builder.py -v
```

Expected: all tests pass (including new ones)

- [ ] **Step 5: Full suite — no regressions**

```bash
uv run pytest --tb=short -q
```

Expected: all existing tests still pass (the new fields have defaults — no positional-arg breakage)

- [ ] **Step 6: Commit**

```bash
git add tools/report_builder.py tests/test_report_builder.py
git commit -m "feat(O-1): add board_bullets, dominant_pillar, signal_type to RegionEntry"
```

---

## Task 2: Agent quality check

**File:** `.claude/agents/regional-analyst-agent.md`

- [ ] **Step 1: Add one line to the QUALITY STANDARD checklist (Step 4)**

Locate the `### QUALITY STANDARD` block. After the VaCR immutability check, add:

```markdown
- [ ] So What opens with operational consequence (what stops working), not the VaCR figure
```

The full checklist should now end with:

```markdown
- [ ] VaCR is immutable: report the number exactly as received
- [ ] So What opens with operational consequence (what stops working), not the VaCR figure
```

- [ ] **Step 2: Commit**

```bash
git add .claude/agents/regional-analyst-agent.md
git commit -m "feat(O-2): add So What quality check — operational consequence must lead"
```

---

## Task 3: `report.html.j2` — Clean Executive redesign

**Files:** `tools/templates/report.html.j2`, `tests/test_export_pdf.py`

- [ ] **Step 1: Write updated/new tests first** (edit `tests/test_export_pdf.py`)

Replace `test_template_contains_vacr` with a no-VaCR assertion. Replace `test_template_contains_three_pillar_labels` with board-grid label assertions. Add a confidence-label test.

```python
def test_template_does_not_contain_vacr_dollar_amounts(mock_output):
    """CISO brief must not render dollar exposure figures."""
    html = _render(mock_output)
    # The executive summary text mentions $44.7M — that's acceptable since it's
    # the agent-written exec summary string. What must be absent is the rendered
    # VaCR KPI blocks (cover-vacr, total-vacr, VaCR column header in the table).
    assert "Total Value at Cyber Risk" not in html
    assert "TOTAL VaCR" not in html
    assert "VaCR Exposure" not in html   # old sidebar KPI label
    assert "VaCR" not in html  # column header


def test_template_contains_board_grid_labels(mock_output):
    html = _render(mock_output)
    assert "Driver" in html
    assert "Exposure" in html
    assert "Watch" in html


def test_template_contains_confidence_label(mock_output):
    """Admiralty B2 → 'High' confidence label. Admiralty code must not appear."""
    html = _render(mock_output)
    assert "High" in html           # confidence label present
    # Admiralty codes themselves are not shown in CISO brief
    # (B2 appears in the mock data but must not appear as a standalone KPI label)
    assert "Admiralty" not in html  # old KPI label gone


def test_template_cover_says_ciso_edition(mock_output):
    html = _render(mock_output)
    assert "CISO" in html


def test_template_cover_no_vacr(mock_output):
    html = _render(mock_output)
    # Cover must not show the VaCR figure block
    assert "cover-vacr" not in html
```

- [ ] **Step 2: Run to confirm they fail (pre-redesign baseline)**

```bash
uv run pytest tests/test_export_pdf.py -v
```

Expected: new tests FAIL (old template still renders VaCR); old tests may still pass.

- [ ] **Step 3: Rewrite `tools/templates/report.html.j2`**

Full replacement. Key changes per spec:

**CSS changes:**
- Remove: `.cover-vacr`, `.cover-vacr-label`, `.total-vacr`, `.total-vacr-label`
- Remove: `.region-sidebar`, `.kpi-cell`, `.kpi-label`, `.kpi-value`
- Remove: `.region-layout`, `.region-body`, `.pillar`, `.pillar-label`, `.pillar-text`
- Add: `.board-grid` (2-col grid), `.board-cell` (with colored left border via CSS variable), `.cell-navy`, `.cell-red`, `.cell-amber`
- Add: `.severity-chip` (inline-block, colored background/text by severity)
- Add: `.region-footer` (small grey, two fields)
- Add: `.region-subheader` (scenario · signal_type · Confidence: {label})
- Update: `.cover-band .report-title` to "Cyber Risk Intelligence Brief — CISO Edition"

**Cover page changes:**
- Remove `cover-vacr-label` and `cover-vacr` divs
- Remove trend delta line
- Title text: "Cyber Risk Intelligence Brief — CISO Edition"
- Keep: company name, pipeline ID, run date, regions assessed, CONFIDENTIAL

**Exec summary changes:**
- Remove VaCR badge div from status strip
- Remove TREND badge div from status strip
- Remove `VaCR Exposure` column header and `$M` cells from table
- Table columns: Region | Scenario | Confidence | Velocity | Severity
- Confidence derived from `r.admiralty` via Jinja2 macro

**Region pages changes (per escalated region):**
- Remove `region-sidebar` div entirely
- Section header: brand band with `region.name` + severity chip (colored by severity) top-right
- Sub-header line: `{{ r.scenario_match }} · {{ r.signal_type or "—" }} · Confidence: {{ admiralty_to_confidence(r.admiralty) }}`
- Body: `board-grid` div with 4 cells using `board_bullets` (if present); fallback notice if None
  - Cell 1: "DRIVER" label + navy border + `board_bullets[0]`
  - Cell 2: "EXPOSURE" label + navy border + `board_bullets[1]`
  - Cell 3: "IMPACT" label + red border + `board_bullets[2]`
  - Cell 4: "WATCH" label + amber border + `board_bullets[3]`
- Footer: `Trend: {vel}  ·  {threat_char(r.dominant_pillar)}`

**Jinja2 helpers (define as macros at top of template body):**
```jinja2
{% macro admiralty_to_confidence(code) %}
  {%- if code in ('A', 'B', 'A1', 'A2', 'B1', 'B2', 'B3') %}High
  {%- elif code in ('C', 'C1', 'C2', 'C3') %}Medium
  {%- else %}Low{%- endif -%}
{% endmacro %}

{% macro threat_char(pillar) %}
  {%- if pillar == 'Cyber' %}Financially motivated threat
  {%- elif pillar == 'Geopolitical' %}State-directed threat
  {%- else %}Mixed-motive threat{%- endif -%}
{% endmacro %}
```

**Severity chip macro:**
```jinja2
{% macro severity_chip(sev) %}
  {%- set bg = '#fee2e2' if sev == 'CRITICAL' else ('#ffedd5' if sev == 'HIGH' else '#fef9c3') -%}
  {%- set fg = '#991b1b' if sev == 'CRITICAL' else ('#9a3412' if sev == 'HIGH' else '#854d0e') -%}
  <span style="background:{{ bg }};color:{{ fg }};padding:1mm 3mm;border-radius:3px;font-size:8pt;font-weight:700;">{{ sev }}</span>
{% endmacro %}
```

- [ ] **Step 4: Run PDF tests — expect all pass**

```bash
uv run pytest tests/test_export_pdf.py -v
```

Expected: all pass (including new assertions, updated VaCR/pillar tests)

- [ ] **Step 5: Full suite — no regressions**

```bash
uv run pytest --tb=short -q
```

- [ ] **Step 6: Commit**

```bash
git add tools/templates/report.html.j2 tests/test_export_pdf.py
git commit -m "feat(O-3): Clean Executive HTML template — 2x2 grid, no VaCR"
```

---

## Task 4: `export_pptx.py` — slide redesign

**Files:** `tools/export_pptx.py`, `tests/test_export_pptx.py`

- [ ] **Step 1: Update tests first** (edit `tests/test_export_pptx.py`)

Replace broken tests and add new structural assertions:

```python
def test_pptx_cover_says_ciso_edition(mock_output):
    """Cover slide must contain 'CISO' — not just 'Global Cyber Risk'."""
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    cover = prs.slides[0]
    title_texts = [shape.text for shape in cover.shapes if shape.has_text_frame]
    all_text = " ".join(title_texts)
    assert "CISO" in all_text or "Intelligence Brief" in all_text


def test_pptx_cover_no_vacr(mock_output):
    """Cover slide must not contain VaCR dollar amount."""
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    cover = prs.slides[0]
    all_text = " ".join(shape.text for shape in cover.shapes if shape.has_text_frame)
    assert "TOTAL VALUE AT CYBER RISK" not in all_text
    assert "VaCR" not in all_text


def test_pptx_region_slide_has_severity_not_admiralty_code(mock_output):
    """Region slides show confidence label (High/Medium/Low), not raw Admiralty code."""
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    apac_slide = prs.slides[2]  # slide 0=cover, 1=exec, 2=APAC
    all_text = " ".join(shape.text for shape in apac_slide.shapes if shape.has_text_frame)
    assert "High" in all_text          # B2 → High confidence label
    assert "VaCR" not in all_text      # no VaCR KPI


def test_pptx_region_slide_contains_driver_sentence(mock_output):
    """Region slides must contain board_bullets[0] (Driver sentence)."""
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    apac_slide = prs.slides[2]
    all_text = " ".join(shape.text for shape in apac_slide.shapes if shape.has_text_frame)
    assert "State-sponsored" in all_text  # first sentence of APAC why_text


def test_pptx_exec_summary_no_vacr_column(mock_output):
    """Exec summary slide must not contain VaCR column header."""
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    exec_slide = prs.slides[1]
    all_text = " ".join(shape.text for shape in exec_slide.shapes if shape.has_text_frame)
    assert "VaCR" not in all_text
    assert "TOTAL VaCR" not in all_text
```

Remove `test_pptx_cover_slide_has_title` and `test_pptx_region_slides_contain_admiralty` (both will be superseded by the new tests above).

- [ ] **Step 2: Run to confirm new tests fail**

```bash
uv run pytest tests/test_export_pptx.py -v
```

Expected: new tests fail, old tests may still pass (pre-redesign).

- [ ] **Step 3: Implement in `tools/export_pptx.py`**

**Add helpers (after `_vel_label`):**

```python
def _confidence_label(admiralty: str | None) -> str:
    """Map Admiralty code to plain-language confidence label."""
    if not admiralty:
        return "—"
    prefix = admiralty[0].upper() if admiralty else ""
    if prefix in ("A", "B"):
        return "High"
    if prefix == "C":
        return "Medium"
    return "Low"


def _threat_char(dominant_pillar: str | None) -> str:
    """Map dominant_pillar to plain-language threat characterisation."""
    mapping = {
        "Cyber": "Financially motivated threat",
        "Geopolitical": "State-directed threat",
    }
    return mapping.get(dominant_pillar or "", "Mixed-motive threat")
```

**`build_cover` changes:**
- Change title text from "Global Cyber Risk\nIntelligence Brief" → "Cyber Risk Intelligence Brief\nCISO Edition"
- Remove the VaCR block (lines adding "TOTAL VALUE AT CYBER RISK" label and `_vacr_fmt(data.total_vacr)` value)
- Keep: company name, meta (pipeline ID + timestamp), CONFIDENTIAL

**`build_exec_summary` changes:**
- Remove the VaCR badge rect + text (the block at `Inches(8.0), Inches(0.85)`)
- Update columns list: `cols = ["Region", "Scenario", "Confidence", "Velocity", "Severity"]`
- Update `col_widths` to 5 columns (remove VaCR column width, redistribute)
- Update row data to `[r.name, r.scenario_match or "—", _confidence_label(r.admiralty), _vel_label(r.velocity), r.severity or "—"]`

**`build_region` changes:**

New design — replace current implementation with:

```python
def build_region(prs: Presentation, region: RegionEntry) -> None:
    slide = _add_blank_slide(prs)

    # 3px navy top stripe
    _add_rect(slide, 0, 0, W, Inches(0.05), BRAND)

    # Region name + severity chip
    _add_text(slide, region.name, Inches(0.3), Inches(0.12),
              Inches(6), Inches(0.45), font_size=16, bold=True, color=DARK)

    # Severity chip (colored rectangle + label)
    sev = region.severity or ""
    chip_color = RED if sev == "CRITICAL" else AMBER if sev == "HIGH" else RGBColor(0xCA, 0x8A, 0x04)
    _add_rect(slide, Inches(8.2), Inches(0.12), Inches(1.5), Inches(0.38), chip_color)
    _add_text(slide, sev, Inches(8.2), Inches(0.16),
              Inches(1.5), Inches(0.3), font_size=8, bold=True,
              color=WHITE, align=PP_ALIGN.CENTER)

    # Sub-header line: Scenario · Signal type · Confidence
    subheader = (
        f"{region.scenario_match or '—'}"
        f"  ·  {region.signal_type or '—'}"
        f"  ·  Confidence: {_confidence_label(region.admiralty)}"
    )
    _add_text(slide, subheader, Inches(0.3), Inches(0.58),
              Inches(9.2), Inches(0.28), font_size=8, color=SLATE)

    # 2×2 board_bullets grid
    NAVY = RGBColor(0x1E, 0x3A, 0x5F)
    cell_labels  = ["DRIVER", "EXPOSURE", "IMPACT", "WATCH"]
    border_colors = [NAVY, NAVY, RED, AMBER]
    cell_x = [Inches(0.3), Inches(5.2), Inches(0.3), Inches(5.2)]
    cell_y = [Inches(1.0), Inches(1.0), Inches(3.5), Inches(3.5)]
    cell_w = Inches(4.6)
    cell_h = Inches(2.2)

    if region.board_bullets and len(region.board_bullets) == 4:
        for i, (label, text, color, x, y) in enumerate(
            zip(cell_labels, region.board_bullets, border_colors, cell_x, cell_y)
        ):
            # Colored left border bar
            _add_rect(slide, x, y, Inches(0.05), cell_h, color)
            # Label
            _add_text(slide, label, x + Inches(0.1), y + Inches(0.05),
                      cell_w, Inches(0.25), font_size=7, bold=True, color=SLATE)
            # Bullet sentence
            _add_text(slide, text, x + Inches(0.1), y + Inches(0.3),
                      cell_w - Inches(0.1), cell_h - Inches(0.35),
                      font_size=9, color=DARK, wrap=True)
    else:
        _add_text(slide, "Regional intelligence report unavailable for this run.",
                  Inches(0.3), Inches(1.0), Inches(9.2), Inches(0.5),
                  font_size=10, color=AMBER)

    # Footer
    footer = f"Trend: {_vel_label(region.velocity)}    ·    {_threat_char(region.dominant_pillar)}"
    _add_text(slide, footer, Inches(0.3), Inches(6.9), Inches(9.2), Inches(0.35),
              font_size=8, color=SLATE)
```

- [ ] **Step 4: Run PPTX tests — expect all pass**

```bash
uv run pytest tests/test_export_pptx.py -v
```

Expected: all pass

- [ ] **Step 5: Full suite — no regressions**

```bash
uv run pytest --tb=short -q
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add tools/export_pptx.py tests/test_export_pptx.py
git commit -m "feat(O-4): Clean Executive PPTX — 2x2 grid, no VaCR, confidence labels"
```

---

## Task 5: Integration smoke

**Files:** Output files (not committed — runtime artifacts)

- [ ] **Step 1: Generate PDF**

```bash
uv run python tools/export_pdf.py output/board_report.pdf
```

Expected: `PDF exported: output/board_report.pdf` — no errors

- [ ] **Step 2: Generate PPTX**

```bash
uv run python tools/export_pptx.py output/board_report.pptx
```

Expected: `PPTX exported: output/board_report.pptx` — no errors

- [ ] **Step 3: Open and visually verify PDF**

Open `output/board_report.pdf`. Verify:
- Cover says "Cyber Risk Intelligence Brief — CISO Edition" — no dollar figure
- Exec summary: 3 status badges (Escalated/Monitor/Clear), no VaCR badge, table has Confidence column (not VaCR)
- APAC region page: severity chip (HIGH, orange), 4-cell 2×2 grid with Driver/Exposure/Impact/Watch, footer with velocity + threat char
- AME region page: severity chip (CRITICAL, red), 4-cell grid populated
- Appendix: monitor + clear regions, metadata — no VaCR

- [ ] **Step 4: Final full suite**

```bash
uv run pytest --tb=short -q
```

Expected: all tests pass, no regressions

- [ ] **Step 5: Commit + push**

```bash
git add tools/report_builder.py tools/export_pptx.py tools/templates/report.html.j2 \
        .claude/agents/regional-analyst-agent.md \
        tests/test_report_builder.py tests/test_export_pdf.py tests/test_export_pptx.py
git commit -m "feat(O-5): Phase O complete — CISO Brief Clean Executive PDF + PPTX"
git push
```

---

## Success Checklist

- [ ] `_extract_brief_sentences()` derives Driver/Exposure/Impact/Watch from three-pillar text
- [ ] Impact skips VaCR-leading sentences (those containing `$`)
- [ ] `RegionEntry.board_bullets` populated for all escalated regions with report.md
- [ ] `RegionEntry.dominant_pillar` and `signal_type` read from `data.json`
- [ ] Agent quality check added: So What opens with operational consequence
- [ ] PDF cover: "CISO Edition" title, no VaCR dollar block
- [ ] PDF exec summary: no VaCR badge, no VaCR column, Confidence column present
- [ ] PDF region pages: 2×2 board_bullets grid, severity chip, confidence label, no VaCR KPI
- [ ] PPTX matches same VaCR-free structure
- [ ] PPTX region slides: board_bullets grid, severity chip, threat characterisation footer
- [ ] All existing tests pass + new tests green
- [ ] `uv run pytest --tb=short -q` exits 0
