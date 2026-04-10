# CISO Brief — Implementation Plan


**Goal:** Redesign the board PDF and PPTX outputs as a CISO-grade intelligence brief — clean, jargon-free, no VaCR dollar figures, 2×2 region layout derived from existing pillar text.

**Architecture:** `report_builder.py` gains sentence extraction helpers and five new fields on `RegionEntry` (populated from existing parsed pillar text + `data.json`). The Jinja2 HTML template and `export_pptx.py` are redesigned to render the brief layout. The regional-analyst-agent gets one quality gate addition. No new output files, no new pipeline steps.

**Tech Stack:** Python 3.12+, `python-pptx`, `playwright` + `jinja2` (PDF), `pytest`, `uv`

**Spec:** `docs/superpowers/specs/2026-03-24-ciso-brief-design.md`

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `tools/report_builder.py` | New `RegionEntry` fields + sentence extraction helpers |
| Modify | `tools/templates/report.html.j2` | CISO layout — remove VaCR, add 2×2 brief grid |
| Modify | `tools/export_pptx.py` | CISO layout — remove VaCR, add 2×2 brief grid |
| Modify | `.claude/agents/regional-analyst-agent.md` | Add So What quality gate line |
| Modify | `tests/test_report_builder.py` | Tests for new helpers and fields |

---

## Task 1: Add extraction helpers + new fields to `report_builder.py`

**Files:**
- Modify: `tools/report_builder.py`
- Test: `tests/test_report_builder.py`

- [ ] **Step 1: Write failing tests for `_confidence_label`**

Add to `tests/test_report_builder.py`:

```python
from report_builder import _confidence_label, _threat_characterisation, _extract_board_bullets

def test_confidence_label_high():
    assert _confidence_label("A1") == "High"
    assert _confidence_label("B2") == "High"
    assert _confidence_label("B3") == "High"

def test_confidence_label_medium():
    assert _confidence_label("C2") == "Medium"
    assert _confidence_label("C3") == "Medium"

def test_confidence_label_low():
    assert _confidence_label("D3") == "Low"
    assert _confidence_label("E3") == "Low"
    assert _confidence_label("F6") == "Low"

def test_confidence_label_none():
    assert _confidence_label(None) == "Unknown"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_report_builder.py::test_confidence_label_high -v
```
Expected: `ImportError` or `FAILED` — `_confidence_label` does not exist yet.

- [ ] **Step 3: Write failing tests for `_threat_characterisation`**

```python
def test_threat_characterisation_cyber():
    assert _threat_characterisation("Cyber") == "Financially motivated threat"

def test_threat_characterisation_geo():
    assert _threat_characterisation("Geopolitical") == "State-directed threat"

def test_threat_characterisation_mixed():
    assert _threat_characterisation("Mixed") == "Mixed-motive threat"

def test_threat_characterisation_none():
    assert _threat_characterisation(None) == "Unknown"
```

- [ ] **Step 4: Write failing tests for `_extract_board_bullets`**

```python
def test_extract_board_bullets_normal():
    why = "Structural instability is driving state interest in energy IP. Secondary sentence."
    how = "Wind turbine control systems are the primary target. More detail here."
    so_what = "If this materialises, blade production schedules will be disrupted. Watch for credential abuse."
    bullets = _extract_board_bullets(why, how, so_what)
    assert bullets is not None
    assert len(bullets) == 4
    assert bullets[0] == "Structural instability is driving state interest in energy IP."
    assert bullets[1] == "Wind turbine control systems are the primary target."
    assert bullets[2] == "If this materialises, blade production schedules will be disrupted."
    assert bullets[3] == "Watch for credential abuse."

def test_extract_board_bullets_skips_vacr_sentence():
    so_what = "AeroGrid's quantified exposure stands at $4,200,000 (VaCR). If this materialises, maintenance access will be disrupted. Watch for access reviews failing."
    bullets = _extract_board_bullets("why.", "how.", so_what)
    assert bullets is not None
    assert "$" not in bullets[2]
    assert "maintenance access" in bullets[2]

def test_extract_board_bullets_returns_none_when_missing():
    assert _extract_board_bullets(None, "how.", "so_what.") is None
    assert _extract_board_bullets("why.", None, "so_what.") is None
    assert _extract_board_bullets("why.", "how.", None) is None
```

- [ ] **Step 5: Run tests to verify they all fail**

```bash
uv run pytest tests/test_report_builder.py -k "confidence or characterisation or board_bullets" -v
```
Expected: all FAILED or ImportError.

- [ ] **Step 6: Add sentence utilities and helpers to `report_builder.py`**

Add after the existing imports (before `logger = ...`):

```python
import re
```

Add after the `_PILLAR_HEADERS` block, before `_header_matches`:

```python
# ── Sentence utilities ────────────────────────────────────────────────────────

_SENT_RE = re.compile(r'(?<=[.!?])\s+')


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text.strip()) if s.strip()]


def _first_sentence(text: str | None) -> str | None:
    if not text:
        return None
    parts = _split_sentences(text)
    return parts[0] if parts else None


def _last_sentence(text: str | None) -> str | None:
    if not text:
        return None
    parts = _split_sentences(text)
    return parts[-1] if parts else None


def _first_non_vacr_sentence(text: str | None) -> str | None:
    """Return first sentence that contains no dollar amount or VaCR reference."""
    if not text:
        return None
    for s in _split_sentences(text):
        if '$' not in s and 'vacr' not in s.lower():
            return s
    return _split_sentences(text)[0] if text else None


def _confidence_label(admiralty: str | None) -> str:
    if not admiralty:
        return "Unknown"
    prefix = admiralty[0].upper()
    if prefix in ('A', 'B'):
        return "High"
    if prefix == 'C':
        return "Medium"
    return "Low"


def _threat_characterisation(dominant_pillar: str | None) -> str:
    return {
        "Cyber":        "Financially motivated threat",
        "Geopolitical": "State-directed threat",
        "Mixed":        "Mixed-motive threat",
    }.get(dominant_pillar or "", "Unknown")


def _extract_board_bullets(
    why: str | None,
    how: str | None,
    so_what: str | None,
) -> list[str] | None:
    """Derive [Driver, Exposure, Impact, Watch] from pillar text.

    Returns None if any source pillar is absent.
    """
    if not all([why, how, so_what]):
        return None
    driver   = _first_sentence(why)
    exposure = _first_sentence(how)
    impact   = _first_non_vacr_sentence(so_what)
    watch    = _last_sentence(so_what)
    if not all([driver, exposure, impact, watch]):
        return None
    return [driver, exposure, impact, watch]
```

- [ ] **Step 7: Add new fields to `RegionEntry`**

The existing `RegionEntry` ends at `so_what_text: str | None`. Add five new optional fields with defaults after it:

```python
    dominant_pillar: str | None = None
    signal_type: str | None = None
    board_bullets: list[str] | None = None
    confidence_label: str | None = None
    threat_characterisation: str | None = None
```

- [ ] **Step 8: Populate new fields in `build()`**

In the `build()` function, the `regions.append(RegionEntry(...))` block currently ends at `so_what_text=so_what_text`. Before that call, add:

```python
dominant_pillar = d.get("dominant_pillar")
signal_type     = d.get("signal_type")
board_bullets   = _extract_board_bullets(why_text, how_text, so_what_text)
```

Then extend the `RegionEntry(...)` call with:

```python
    dominant_pillar=dominant_pillar,
    signal_type=signal_type,
    board_bullets=board_bullets,
    confidence_label=_confidence_label(d.get("admiralty")),
    threat_characterisation=_threat_characterisation(dominant_pillar),
```

- [ ] **Step 9: Run all tests**

```bash
uv run pytest tests/test_report_builder.py -v
```
Expected: all PASS. The existing `test_region_entry_is_dataclass` test uses keyword arguments — new optional fields have `= None` defaults so it passes unchanged.

- [ ] **Step 10: Commit**

```bash
git add tools/report_builder.py tests/test_report_builder.py
git commit -m "feat(ciso-brief): add board_bullets extraction helpers to report_builder"
```

---

## Task 2: Redesign the HTML template

**Files:**
- Modify: `tools/templates/report.html.j2`

No unit tests for Jinja2 templates — visual verification via PDF export at end of this task.

- [ ] **Step 1: Update cover page**

In `report.html.j2`, in the cover-band div update the report-title text:

```html
<div class="report-title">Cyber Risk Intelligence Brief<br>CISO Edition</div>
```

In the cover-body div, remove the `cover-vacr-label`, `cover-vacr`, and `Trend vs Prior Run` elements entirely. The cover-body becomes:

```html
<div class="cover-body">
  <div>
    <div class="cover-meta">
      <span>Pipeline ID: {{ data.run_id }}</span>
      <span>Run Date: {{ data.timestamp }}</span>
      <span>Regions Assessed: {{ data.regions|length }}</span>
    </div>
  </div>
  <div class="cover-confidential">CONFIDENTIAL · CISO EDITION</div>
</div>
```

Also remove the `.cover-vacr` and `.cover-vacr-label` CSS rules from the `<style>` block.

- [ ] **Step 2: Remove VaCR from the exec summary status strip**

Remove the `badge-blue` TOTAL VaCR badge div and the TREND badge div from the status strip. The strip should contain only the three badges: ESCALATED, MONITOR, CLEAR.

Remove `.total-vacr` and `.total-vacr-label` CSS rules.

- [ ] **Step 3: Update the region posture table**

Replace the exec summary table. Keep the `{% set escalated_regions = ... %}` line that already exists just above the table — do not remove it. Replace only the `<table>` element:

```html
{% set escalated_regions = data.regions | selectattr("status", "equalto", "escalated") | list %}
{% if escalated_regions %}
<table class="admiralty-table">
  <thead>
    <tr>
      <th>Region</th>
      <th>Scenario</th>
      <th>Signal Type</th>
      <th>Confidence</th>
      <th>Velocity</th>
      <th>Severity</th>
    </tr>
  </thead>
  <tbody>
    {% for r in escalated_regions %}
    <tr>
      <td><strong>{{ r.name }}</strong></td>
      <td>{{ r.scenario_match or "—" }}</td>
      <td>{{ r.signal_type or "—" }}</td>
      <td>{{ r.confidence_label or "—" }}</td>
      <td>
        {% if r.velocity == "accelerating" %}<span class="vel-up">↑ Accelerating</span>
        {% elif r.velocity == "improving"   %}<span class="vel-down">↓ Improving</span>
        {% else %}<span class="vel-flat">→ {{ r.velocity | title if r.velocity else "—" }}</span>
        {% endif %}
      </td>
      <td>{{ r.severity or "—" }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
```

- [ ] **Step 4: Add 2×2 grid CSS, remove sidebar CSS**

In the `<style>` block, remove these rule blocks: `.region-layout`, `.region-sidebar`, `.kpi-cell`, `.kpi-cell:last-child`, `.kpi-label`, `.kpi-value`, `.kpi-value.red`, `.kpi-value.amber`, `.kpi-value.green`, `.region-body`.

Add in their place:

```css
/* ── CISO 2×2 brief grid ──────────────────────────────────────────── */
.brief-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4mm;
  margin-top: 5mm;
}
.brief-cell {
  padding: 3mm 3mm 3mm 4mm;
  border-radius: 0 3px 3px 0;
  background: #f8fafc;
}
.brief-cell-navy  { border-left: 3px solid #1e3a5f; }
.brief-cell-red   { border-left: 3px solid #dc2626; }
.brief-cell-amber { border-left: 3px solid #d97706; }
.brief-label {
  font-size: 7.5pt; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.8px; margin-bottom: 1.5mm;
}
.brief-label-navy  { color: #1e3a5f; }
.brief-label-red   { color: #dc2626; }
.brief-label-amber { color: #d97706; }
.brief-text { font-size: 10pt; line-height: 1.6; color: #334155; }

.region-footer {
  margin-top: 5mm; padding-top: 3mm;
  border-top: 1px solid #e2e8f0;
  display: flex; gap: 8mm;
  font-size: 8.5pt; color: #64748b;
}
```

- [ ] **Step 5: Replace the region page body**

Replace the entire region page loop (the `{% for r in data.regions if r.status == "escalated" %}` block) with:

```html
{% for r in data.regions if r.status == "escalated" %}
<div class="page">
  <div class="section-header">
    <div>
      <h2>{{ r.name }}</h2>
      <span class="sub">{{ r.scenario_match or "" }} · {{ r.signal_type or "" }} · Confidence: {{ r.confidence_label or "—" }}</span>
    </div>
    {% set sev = (r.severity or "") | upper %}
    {% if sev == "CRITICAL" %}
      <span class="chip chip-red">{{ sev }}</span>
    {% elif sev == "HIGH" %}
      <span class="chip chip-amber">{{ sev }}</span>
    {% else %}
      <span class="chip" style="background:#fef9c3;color:#854d0e;">{{ sev }}</span>
    {% endif %}
  </div>

  {% if r.board_bullets %}
  <div class="brief-grid">
    <div class="brief-cell brief-cell-navy">
      <div class="brief-label brief-label-navy">Driver</div>
      <div class="brief-text">{{ r.board_bullets[0] }}</div>
    </div>
    <div class="brief-cell brief-cell-navy">
      <div class="brief-label brief-label-navy">Exposure</div>
      <div class="brief-text">{{ r.board_bullets[1] }}</div>
    </div>
    <div class="brief-cell brief-cell-red">
      <div class="brief-label brief-label-red">Impact</div>
      <div class="brief-text">{{ r.board_bullets[2] }}</div>
    </div>
    <div class="brief-cell brief-cell-amber">
      <div class="brief-label brief-label-amber">Watch</div>
      <div class="brief-text">{{ r.board_bullets[3] }}</div>
    </div>
  </div>
  {% else %}
  <div class="unavailable-notice">
    Regional intelligence report unavailable for this run. Check pipeline logs.
  </div>
  {% endif %}

  <div class="region-footer">
    <span>
      Trend:&nbsp;
      {% if r.velocity == "accelerating" %}<span class="vel-up">↑ Accelerating</span>
      {% elif r.velocity == "improving"   %}<span class="vel-down">↓ Improving</span>
      {% else %}<span class="vel-flat">→ {{ r.velocity | title if r.velocity else "—" }}</span>
      {% endif %}
    </span>
    <span>{{ r.threat_characterisation or "—" }}</span>
  </div>
</div>
{% endfor %}
```

- [ ] **Step 6: Visual check — generate PDF**

```bash
uv run python tools/export_pdf.py output/board_report.pdf
```

Open `output/board_report.pdf`. Confirm:
- Cover: no dollar figure, title reads "Cyber Risk Intelligence Brief — CISO Edition"
- Exec summary: 3 status badges only (no VaCR badge), table has Confidence column
- Each escalated region: 2×2 grid with Driver/Exposure/Impact/Watch cells
- Footer per region: Trend + threat characterisation
- No `$` sign anywhere in the document

- [ ] **Step 7: Commit**

```bash
git add tools/templates/report.html.j2
git commit -m "feat(ciso-brief): redesign HTML template — 2x2 brief grid, no VaCR"
```

---

## Task 3: Redesign the PPTX exporter

**Files:**
- Modify: `tools/export_pptx.py`

- [ ] **Step 1: Remove VaCR from `build_cover`**

In `build_cover`, delete the two `_add_text` blocks that render `"TOTAL VALUE AT CYBER RISK"` and `_vacr_fmt(data.total_vacr)`. Update the report title string:

```python
_add_text(slide, "Cyber Risk Intelligence Brief\nCISO Edition",
          Inches(0.6), Inches(1.1), Inches(8.8), Inches(2.0),
          font_size=28, bold=True, color=WHITE)
```

- [ ] **Step 2: Remove VaCR from `build_exec_summary`**

Delete the VaCR badge block — the `_add_rect` and two `_add_text` calls that render `_vacr_fmt(data.total_vacr)` and `"TOTAL VaCR"` (approximately lines 165–172 of the original file).

Update the table columns and row values:

```python
cols = ["Region", "Scenario", "Signal Type", "Confidence", "Velocity", "Severity"]
col_widths = [Inches(1.1), Inches(2.0), Inches(1.2), Inches(1.2), Inches(1.8), Inches(1.1)]
```

```python
row = [
    r.name,
    r.scenario_match or "—",
    r.signal_type or "—",
    r.confidence_label or "—",
    _vel_label(r.velocity),
    r.severity or "—",
]
```

- [ ] **Step 3: Rewrite `build_region` for the 2×2 layout**

Replace the entire `build_region` function body with the implementation below. The 2×2 grid uses a left accent bar (thin rect) + label + content text per cell:

```python
def build_region(prs: Presentation, region: RegionEntry) -> None:
    slide = _add_blank_slide(prs)

    # Header band
    _add_rect(slide, 0, 0, W, Inches(0.65), BRAND)
    _add_text(slide, region.name,
              Inches(0.3), Inches(0.1), Inches(5.5), Inches(0.45),
              font_size=16, bold=True, color=WHITE)
    sub = f"{region.scenario_match or ''} · {region.signal_type or ''} · Confidence: {region.confidence_label or '—'}"
    _add_text(slide, sub,
              Inches(0.3), Inches(0.38), Inches(7.5), Inches(0.25),
              font_size=8, color=RGBColor(0xBF, 0xDB, 0xFF))

    # Severity chip — PPTX uses solid fill (no background/text split).
    # CRITICAL=red, HIGH=amber, MEDIUM=dark-gold. Intentional deviation from
    # the spec's CSS chip values which use a light background + dark text.
    sev = (region.severity or "").upper()
    chip_color = RED if sev == "CRITICAL" else AMBER if sev == "HIGH" else RGBColor(0xCA, 0x8A, 0x04)
    _add_rect(slide, Inches(8.4), Inches(0.12), Inches(1.3), Inches(0.38), chip_color)
    _add_text(slide, sev or "—",
              Inches(8.4), Inches(0.16), Inches(1.3), Inches(0.3),
              font_size=8, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

    if not region.board_bullets:
        _add_text(slide, "Regional intelligence report unavailable for this run.",
                  Inches(0.4), Inches(1.0), Inches(9.2), Inches(0.5),
                  font_size=10, color=AMBER)
        return

    driver, exposure, impact, watch = region.board_bullets

    CELL_W  = Inches(4.45)
    CELL_H  = Inches(2.6)
    GAP     = Inches(0.15)
    LEFT    = Inches(0.3)
    TOP     = Inches(0.85)
    BAR_W   = Inches(0.06)

    cells = [
        (driver,   "DRIVER",   BRAND, LEFT,                TOP),
        (exposure, "EXPOSURE", BRAND, LEFT + CELL_W + GAP, TOP),
        (impact,   "IMPACT",   RED,   LEFT,                TOP + CELL_H + GAP),
        (watch,    "WATCH",    AMBER, LEFT + CELL_W + GAP, TOP + CELL_H + GAP),
    ]

    for text, label, accent, x, y in cells:
        _add_rect(slide, x, y, BAR_W, CELL_H, accent)
        _add_text(slide, label,
                  x + BAR_W + Inches(0.05), y + Inches(0.05),
                  CELL_W - BAR_W - Inches(0.05), Inches(0.28),
                  font_size=7, bold=True, color=accent)
        _add_text(slide, (text or "")[:280],
                  x + BAR_W + Inches(0.05), y + Inches(0.35),
                  CELL_W - BAR_W - Inches(0.05), CELL_H - Inches(0.4),
                  font_size=9, color=DARK, wrap=True)

    # Footer
    vel = _vel_label(region.velocity)
    _add_text(slide,
              f"Trend: {vel}   ·   {region.threat_characterisation or '—'}",
              Inches(0.3), Inches(7.05), Inches(9.4), Inches(0.3),
              font_size=8, color=SLATE)
```

- [ ] **Step 4: Visual check — generate PPTX**

```bash
uv run python tools/export_pptx.py output/board_report.pptx
```

Open `output/board_report.pptx`. Confirm:
- Cover: no dollar figure, title reads "Cyber Risk Intelligence Brief / CISO Edition"
- Exec summary: no VaCR badge, table shows Confidence column
- Each escalated region slide: 2×2 grid with coloured left accent bars per cell
- Footer on each region slide: Trend + threat characterisation
- No `$` sign anywhere in the deck

- [ ] **Step 5: Commit**

```bash
git add tools/export_pptx.py
git commit -m "feat(ciso-brief): redesign PPTX — 2x2 brief grid, no VaCR"
```

---

## Task 4: Add So What quality gate to regional-analyst-agent

**Files:**
- Modify: `.claude/agents/regional-analyst-agent.md`

- [ ] **Step 1: Add quality check line**

In the `### QUALITY STANDARD` checklist, add after `- [ ] VaCR is immutable: report the number exactly as received`:

```markdown
- [ ] So What opens with operational consequence, not the VaCR figure (VaCR sentence may appear later in the paragraph)
```

- [ ] **Step 2: Commit**

```bash
git add .claude/agents/regional-analyst-agent.md
git commit -m "feat(ciso-brief): add So What quality gate to regional-analyst-agent"
```

---

## Task 5: Full pipeline smoke test

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest tests/ -v
```
Expected: all tests pass.

- [ ] **Step 2: Generate both outputs end-to-end**

```bash
uv run python tools/export_pdf.py output/board_report.pdf
uv run python tools/export_pptx.py output/board_report.pptx
```
Both must complete without error and produce non-empty files.

- [ ] **Step 3: Verify no VaCR leakage**

Open both outputs. Confirm no `$` sign and no "VaCR" text appears on any page or slide.

- [ ] **Step 4: Final commit**

```bash
git add tools/report_builder.py tests/test_report_builder.py tools/templates/report.html.j2 tools/export_pptx.py .claude/agents/regional-analyst-agent.md
git commit -m "feat(ciso-brief): smoke test pass — CISO brief complete"
```

---

*Spec: `docs/superpowers/specs/2026-03-24-ciso-brief-design.md`*
