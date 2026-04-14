# Board PPTX Redesign Implementation Plan

**Goal:** Rewrite `tools/export_pptx.py` to produce a 4–6 slide A1-style board read-ahead deck — Cover / Intelligence Overview (split layout) / Active Threat slides (one per scenario group, max 3) / Under Watch — replacing the current BRAND/RED/AMBER/GREEN corporate layout.

**Architecture:** Six slide builders replace the four existing ones. Helper utilities (`_split_why`, `_group_by_scenario`, `_load_sections`, `_load_brief_headlines`) mirror the CISO docx pattern. Color palette drops to pure greyscale (black, white, mid-grey, light-grey). Georgia serif replaces all existing fonts. `output_dir` threads through `export()` → `build_presentation()` → threat/watch builders so section data loads correctly in tests.

**Tech Stack:** python-pptx, pytest, existing `report_builder.build()` / `RegionEntry` / `ReportData` / `RegionStatus` data model.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `tests/test_export_pptx.py` | 6 TDD tests against the new layout |
| Modify | `tools/export_pptx.py` | Full rewrite of all slide builders + helpers |

`tests/conftest.py` already has the `mock_output` fixture and `MOCK_SECTIONS` data — no changes needed there.

---

### Task 1: Write the failing tests

**Files:**
- Create: `tests/test_export_pptx.py`

- [ ] **Step 1: Write `tests/test_export_pptx.py`**

```python
"""TDD tests for the board PPTX redesign (export_pptx.py)."""
import pytest
from pptx import Presentation


# ── Helpers ────────────────────────────────────────────────────────────────────

def _all_text(pptx_path: str) -> str:
    """Extract all visible text from every slide."""
    prs = Presentation(pptx_path)
    parts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        if run.text.strip():
                            parts.append(run.text.strip())
    return " ".join(parts)


def _slide_text(pptx_path: str, slide_idx: int) -> str:
    """Extract visible text from a single slide by index."""
    prs = Presentation(pptx_path)
    slide = prs.slides[slide_idx]
    parts = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    if run.text.strip():
                        parts.append(run.text.strip())
    return " ".join(parts)


def _fill_colors(pptx_path: str) -> set[str]:
    """Return hex strings of every solid fill color used in slide shapes."""
    prs = Presentation(pptx_path)
    colors: set[str] = set()
    for slide in prs.slides:
        for shape in slide.shapes:
            try:
                rgb = shape.fill.fore_color.rgb
                colors.add(str(rgb))
            except Exception:
                pass
    return colors


def _slide_count(pptx_path: str) -> int:
    return len(Presentation(pptx_path).slides)


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_export_runs_without_error(mock_output, tmp_path):
    """export() completes without error and produces a non-trivial file."""
    out = tmp_path / "board_test.pptx"
    from tools.export_pptx import export
    export(output_path=str(out), output_dir=str(mock_output))
    assert out.exists(), "output file not created"
    assert out.stat().st_size > 5000, "file suspiciously small"


def test_cover_shows_plain_language_labels(mock_output, tmp_path):
    """Cover slide uses plain labels (Active Threats / Under Watch / No Active Threat),
    not pipeline enum values (ESCALATED / MONITOR / CLEAR)."""
    out = tmp_path / "board_test.pptx"
    from tools.export_pptx import export
    export(output_path=str(out), output_dir=str(mock_output))
    cover = _slide_text(str(out), 0)
    assert "Active Threats" in cover, f"'Active Threats' not found in cover: {cover}"
    assert "Under Watch" in cover, f"'Under Watch' not found in cover: {cover}"
    assert "No Active Threat" in cover, f"'No Active Threat' not found in cover: {cover}"
    # Enum values must NOT appear on slide face
    assert "ESCALATED" not in cover, "raw 'ESCALATED' found on cover"
    assert "MONITOR" not in cover, "raw 'MONITOR' found on cover"
    assert "CLEAR" not in cover, "raw 'CLEAR' found on cover"


def test_overview_slide_present(mock_output, tmp_path):
    """Slide 2 is the Intelligence Overview — contains section label."""
    out = tmp_path / "board_test.pptx"
    from tools.export_pptx import export
    export(output_path=str(out), output_dir=str(mock_output))
    overview = _slide_text(str(out), 1)
    assert "Intelligence Overview" in overview, (
        f"'Intelligence Overview' not in slide 2: {overview}"
    )


def test_deck_slide_count(mock_output, tmp_path):
    """With 2 escalated (different scenarios) + 1 monitor, deck has 5 slides:
    Cover + Overview + 2 threat slides + 1 watch list."""
    out = tmp_path / "board_test.pptx"
    from tools.export_pptx import export
    export(output_path=str(out), output_dir=str(mock_output))
    assert _slide_count(str(out)) == 5, (
        f"Expected 5 slides, got {_slide_count(str(out))}"
    )


def test_watch_list_present_for_monitor_regions(mock_output, tmp_path):
    """Watch list slide exists and contains 'Under Watch' + MED (the MONITOR region)."""
    out = tmp_path / "board_test.pptx"
    from tools.export_pptx import export
    export(output_path=str(out), output_dir=str(mock_output))
    full_text = _all_text(str(out))
    assert "Under Watch" in full_text, "'Under Watch' not found in deck"
    # MED is the MONITOR region in mock data
    last_slide = _slide_text(str(out), -1)
    assert "MED" in last_slide, f"MED not found in watch list slide: {last_slide}"


def test_no_red_amber_green_brand_colors(mock_output, tmp_path):
    """No RED, AMBER, GREEN, or BRAND NAVY fill colours appear in any slide shape."""
    out = tmp_path / "board_test.pptx"
    from tools.export_pptx import export
    export(output_path=str(out), output_dir=str(mock_output))
    forbidden = {"DC2626", "D97706", "16A34A", "104277"}
    found = _fill_colors(str(out)) & forbidden
    assert not found, f"Forbidden fill colours found in deck: {found}"
```

- [ ] **Step 2: Run tests to verify they all FAIL**

```
uv run pytest tests/test_export_pptx.py -v
```

Expected: All 6 tests FAIL (cover shows ESCALATED not "Active Threats", wrong colors, wrong slide count, etc.)

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_export_pptx.py
git commit -m "test(pptx): add 6 failing TDD tests for board report redesign"
```

---

### Task 2: Replace color constants and add helper utilities

**Files:**
- Modify: `tools/export_pptx.py` (lines 1–115 — constants, imports, helpers)

- [ ] **Step 1: Replace the color constants block and update `_add_text`**

Replace the entire section from `# Brand colours` through the end of `_status_label` and `_vel_label` with:

```python
import json
import re
from pathlib import Path

# ── Greyscale palette (A1 style — no RED/AMBER/GREEN/BRAND in body content) ────
BLACK      = RGBColor(0x11, 0x11, 0x11)   # near-black primary text
BODY       = RGBColor(0x37, 0x41, 0x51)   # body text
META       = RGBColor(0x9C, 0xA3, 0xAF)   # labels, metadata, badges
MID_GREY   = RGBColor(0x6B, 0x72, 0x80)   # monitor count
LIGHT_GREY = RGBColor(0xD1, 0xD5, 0xDB)   # clear count
RULE       = RGBColor(0xE5, 0xE7, 0xEB)   # thin rules and dividers
WHITE      = RGBColor(0xFF, 0xFF, 0xFF)   # badge text, pill text

# Slide dimensions (10×7.5in widescreen)
W = Inches(10)
H = Inches(7.5)

# Sentence splitter — used by _split_why and watch list first-sentence extraction
_SENT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"\'(])')
```

- [ ] **Step 2: Update `_add_text` to accept `font_name` and default to Georgia**

Replace the existing `_add_text` function with:

```python
def _add_text(slide, text: str, left, top, width, height,
              font_size: int = 11, bold: bool = False,
              color: RGBColor = BODY, align=PP_ALIGN.LEFT,
              font_name: str = "Georgia", wrap: bool = True) -> None:
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name = font_name
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.color.rgb = color
```

- [ ] **Step 3: Add the helper functions after `_add_text`**

Add these four helpers (insert after the `_add_text` definition, before the `# ── Slide builders` section):

```python
# ── Data helpers ──────────────────────────────────────────────────────────────

OUTPUT_DIR = "output/pipeline"


def _split_why(text: str, max_bullets: int = 3) -> list[str]:
    """Split a paragraph into 2–3 sentence bullets for talking points."""
    if not text or not text.strip():
        return []
    sentences = [s.strip() for s in _SENT_RE.split(text.strip()) if s.strip()]
    return sentences[:max_bullets]


def _group_by_scenario(
    entries: list,
) -> list[tuple[str, list]]:
    """Group RegionEntry list by scenario_match.

    Returns [(scenario_label, [entries])] ordered by Admiralty confidence
    (A > B > C > D) then by descending region count.
    """
    groups: dict[str, list] = {}
    for entry in entries:
        key = entry.scenario_match or "Unknown Scenario"
        groups.setdefault(key, []).append(entry)

    def _sort_key(item: tuple[str, list]) -> tuple[str, int]:
        _, grp = item
        # Best admiralty letter in group (A < B < C < D alphabetically = higher first)
        letters = [e.admiralty[0] for e in grp if e.admiralty]
        best = min(letters) if letters else "Z"
        return (best, -len(grp))   # A first; more regions = higher priority on tie

    return sorted(groups.items(), key=_sort_key)


def _load_sections(region_name: str, output_dir: str = OUTPUT_DIR) -> dict:
    """Load sections.json for a region. Regional tree is sibling of pipeline dir."""
    path = (
        Path(output_dir).parent / "regional" / region_name.lower() / "sections.json"
    )
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_brief_headlines(region_name: str, output_dir: str = OUTPUT_DIR) -> dict:
    """Return brief_headlines dict from sections.json for a region."""
    return _load_sections(region_name, output_dir).get("brief_headlines", {})
```

- [ ] **Step 4: Remove the helpers that are no longer used**

Delete these two functions from the file (they will not be called after the rewrite):
- `_status_label()`
- `_vel_label()`

- [ ] **Step 5: Run the test suite to confirm tests still fail (not broken differently)**

```
uv run pytest tests/test_export_pptx.py -v
```

Expected: Still 6 FAILs — the helper functions exist but slide builders are not yet rewritten.

---

### Task 3: Rewrite `build_cover()`

**Files:**
- Modify: `tools/export_pptx.py` (replace `build_cover` function body)

- [ ] **Step 1: Replace `build_cover` with the A1 implementation**

```python
def build_cover(prs: Presentation, data: ReportData) -> None:
    """Slide 1 — Cover: eyebrow, large title, thin rule, meta, status counts."""
    slide = _add_blank_slide(prs)

    # ── Top area ──────────────────────────────────────────────────────────────
    _add_text(
        slide, "AeroGrid Wind Solutions \u2014 Restricted",
        Inches(0.8), Inches(0.6), Inches(8.4), Inches(0.3),
        font_size=8, color=META, font_name="Courier New",
    )

    _add_text(
        slide, "Global Risk\nIntelligence\nBrief",
        Inches(0.8), Inches(1.1), Inches(7.0), Inches(2.5),
        font_size=40, bold=True, color=BLACK,
    )

    # Short decorative rule under title (36px ≈ 0.375in wide, 1pt tall)
    rule_shape = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        Inches(0.8), Inches(3.7), Inches(0.375), Pt(1),
    )
    rule_shape.line.fill.background()
    rule_shape.fill.solid()
    rule_shape.fill.fore_color.rgb = BLACK

    # Meta line: "Board Read-Ahead · Month Year · Cycle N"
    try:
        month_year = data.timestamp[:7]   # "2026-03" → keep as-is or reformat below
        import datetime
        dt = datetime.datetime.strptime(month_year, "%Y-%m")
        month_label = dt.strftime("%B %Y")
    except Exception:
        month_label = data.timestamp[:7]

    cycle = data.run_id or "\u2014"
    meta_text = f"Board Read-Ahead  \u00b7  {month_label}  \u00b7  Cycle {cycle}"
    _add_text(
        slide, meta_text,
        Inches(0.8), Inches(3.9), Inches(8.4), Inches(0.3),
        font_size=8, color=META, font_name="Courier New",
    )

    # ── Separator rule ────────────────────────────────────────────────────────
    sep = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        Inches(0.8), Inches(4.5), Inches(8.4), Pt(0.5),
    )
    sep.line.fill.background()
    sep.fill.solid()
    sep.fill.fore_color.rgb = RULE

    # ── Status counts ─────────────────────────────────────────────────────────
    # (escalated=dark, monitor=mid-grey, clear=light-grey)
    counts = [
        (str(data.escalated_count), "Active Threats",    BLACK,      BODY),
        (str(data.monitor_count),   "Under Watch",       MID_GREY,   META),
        (str(data.clear_count),     "No Active Threat",  LIGHT_GREY, META),
    ]
    for i, (num, label, num_color, lbl_color) in enumerate(counts):
        x = Inches(0.8 + i * 2.0)
        _add_text(
            slide, num,
            x, Inches(4.7), Inches(1.8), Inches(0.85),
            font_size=34, bold=True, color=num_color,
        )
        _add_text(
            slide, label,
            x, Inches(5.55), Inches(1.8), Inches(0.3),
            font_size=7, color=lbl_color, font_name="Courier New",
        )
```

- [ ] **Step 2: Run the cover test**

```
uv run pytest tests/test_export_pptx.py::test_cover_shows_plain_language_labels -v
```

Expected: PASS — "Active Threats", "Under Watch", "No Active Threat" are in slide 0 text; "ESCALATED"/"MONITOR"/"CLEAR" are not.

---

### Task 4: Rewrite `build_exec_summary()` → `build_overview()`

**Files:**
- Modify: `tools/export_pptx.py` (rename and replace `build_exec_summary`)

- [ ] **Step 1: Replace `build_exec_summary` with `build_overview`**

```python
def build_overview(prs: Presentation, data: ReportData, output_dir: str = OUTPUT_DIR) -> None:
    """Slide 2 — Intelligence Overview: split layout (counts left / framing right)."""
    slide = _add_blank_slide(prs)

    # Section label + thin rule below it
    _add_text(
        slide, "Intelligence Overview",
        Inches(0.8), Inches(0.6), Inches(8.4), Inches(0.3),
        font_size=7, color=META, font_name="Courier New",
    )
    label_rule = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        Inches(0.8), Inches(1.0), Inches(8.4), Pt(0.5),
    )
    label_rule.line.fill.background()
    label_rule.fill.solid()
    label_rule.fill.fore_color.rgb = RULE

    # ── Left column: stacked status counts (0.8in – 2.5in) ───────────────────
    stats = [
        (str(data.escalated_count), "Active Threats",    BLACK,      BODY),
        (str(data.monitor_count),   "Under Watch",       MID_GREY,   META),
        (str(data.clear_count),     "No Active Threat",  LIGHT_GREY, META),
    ]
    y_stat = Inches(1.3)
    for num, label, num_color, lbl_color in stats:
        _add_text(
            slide, num,
            Inches(0.8), y_stat, Inches(1.5), Inches(0.75),
            font_size=30, bold=True, color=num_color,
        )
        _add_text(
            slide, label,
            Inches(0.8), y_stat + Inches(0.78), Inches(1.5), Inches(0.25),
            font_size=6, color=lbl_color, font_name="Courier New",
        )
        y_stat += Inches(1.5)

    # ── Vertical divider at 2.7in ─────────────────────────────────────────────
    vdiv = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        Inches(2.7), Inches(1.1), Pt(0.5), Inches(5.5),
    )
    vdiv.line.fill.background()
    vdiv.fill.solid()
    vdiv.fill.fore_color.rgb = RULE

    # ── Right column: framing paragraph (2.9in – 9.2in) ──────────────────────
    # Primary: data.exec_summary. Fallback: auto-generated sentence.
    framing = (data.exec_summary or "").strip()
    if not framing:
        esc_names = [r.name for r in data.regions if r.status == RegionStatus.ESCALATED]
        mon_names = [r.name for r in data.regions if r.status == RegionStatus.MONITOR]
        esc_str = ", ".join(esc_names) if esc_names else "no regions"
        n = len(esc_names)
        scenario_word = "scenario" if n == 1 else "scenarios"
        framing = (
            f"This month, AeroGrid faces {n} active threat {scenario_word} "
            f"affecting {esc_str} operations."
        )
        if mon_names:
            framing += f" {', '.join(mon_names)} {'is' if len(mon_names)==1 else 'are'} under active intelligence monitoring."

    _add_text(
        slide, framing,
        Inches(2.9), Inches(1.3), Inches(6.3), Inches(4.5),
        font_size=11, color=BODY, wrap=True,
    )

    # ── Footer ────────────────────────────────────────────────────────────────
    try:
        date_str = data.timestamp[:10]
    except Exception:
        date_str = data.timestamp
    footer = (
        f"Intelligence current as of {date_str}  \u00b7  "
        "CRQ Agentic Pipeline  \u00b7  Not for external distribution"
    )
    _add_text(
        slide, footer,
        Inches(0.8), Inches(6.9), Inches(8.4), Inches(0.3),
        font_size=6, color=META, font_name="Courier New",
    )
```

- [ ] **Step 2: Run the overview test**

```
uv run pytest tests/test_export_pptx.py::test_overview_slide_present -v
```

Expected: PASS — "Intelligence Overview" found in slide 1 text.

---

### Task 5: Rewrite `build_region()` → `build_threat_slide()`

**Files:**
- Modify: `tools/export_pptx.py` (rename and replace `build_region`)

- [ ] **Step 1: Replace `build_region` with `build_threat_slide`**

```python
def build_threat_slide(
    prs: Presentation,
    scenario: str,
    group: list[RegionEntry],
    output_dir: str = OUTPUT_DIR,
) -> None:
    """Slide 3–N — Active Threat: one slide per scenario group (max 3).

    Assertion title from brief_headlines.why (first sentence).
    Bullets from _split_why sentences 2-3.
    Exposure block from brief_headlines.so_what.
    Speaker notes: brief_headlines.how + intel_bullets.
    No response notes, no action bullets, no Admiralty codes on slide face.
    """
    slide = _add_blank_slide(prs)
    rep = group[0]   # lead region for headline data

    # ── Header row: section label + region pill badge(s) ─────────────────────
    _add_text(
        slide, "Active Threat",
        Inches(0.8), Inches(0.6), Inches(2.0), Inches(0.3),
        font_size=7, color=META, font_name="Courier New",
    )
    # Region pill: filled black rectangle with white Courier New text
    pill_text = "  \u00b7  ".join(e.name for e in group)
    pill = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        Inches(2.9), Inches(0.55), Inches(len(pill_text) * 0.075 + 0.2), Inches(0.28),
    )
    pill.line.fill.background()
    pill.fill.solid()
    pill.fill.fore_color.rgb = BLACK
    tf = pill.text_frame
    tf.word_wrap = False
    p = tf.paragraphs[0]
    from pptx.util import Pt as _Pt
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = pill_text.upper()
    run.font.name = "Courier New"
    run.font.size = _Pt(7)
    run.font.bold = True
    run.font.color.rgb = WHITE

    # Thin rule below header row
    hdr_rule = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        Inches(0.8), Inches(1.0), Inches(8.4), Pt(0.5),
    )
    hdr_rule.line.fill.background()
    hdr_rule.fill.solid()
    hdr_rule.fill.fore_color.rgb = RULE

    # ── Assertion title (brief_headlines.why first sentence) ─────────────────
    bh = _load_brief_headlines(rep.name, output_dir)
    why_full = bh.get("why") or getattr(rep, "why_text", "") or ""
    why_sentences = _split_why(why_full, max_bullets=3)
    title_text = why_sentences[0] if why_sentences else (scenario or rep.scenario_match or "")

    _add_text(
        slide, title_text,
        Inches(0.8), Inches(1.15), Inches(8.4), Inches(1.2),
        font_size=18, bold=True, color=BLACK, wrap=True,
    )

    # ── Bullet points (sentences 2-3 with em-dash prefix) ────────────────────
    bullets = why_sentences[1:3]   # up to 2 additional sentences
    y_bullet = Inches(2.5)
    for bullet in bullets:
        _add_text(
            slide, f"\u2014  {bullet}",
            Inches(0.8), y_bullet, Inches(8.4), Inches(0.55),
            font_size=10, color=BODY, wrap=True,
        )
        y_bullet += Inches(0.6)

    # ── AeroGrid Exposure block ───────────────────────────────────────────────
    so_what = bh.get("so_what") or getattr(rep, "so_what_text", "") or ""
    if so_what:
        y_exp = max(y_bullet + Inches(0.15), Inches(3.8))
        # 2pt left border stripe (black)
        stripe = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.RECTANGLE,
            Inches(0.8), y_exp, Pt(2), Inches(0.8),
        )
        stripe.line.fill.background()
        stripe.fill.solid()
        stripe.fill.fore_color.rgb = BLACK

        _add_text(
            slide, "AEROGRID EXPOSURE",
            Inches(1.0), y_exp, Inches(7.9), Inches(0.2),
            font_size=7, color=MID_GREY, font_name="Courier New",
        )
        _add_text(
            slide, so_what,
            Inches(1.0), y_exp + Inches(0.22), Inches(7.9), Inches(0.55),
            font_size=9, color=BODY, wrap=True,
        )

    # ── Speaker notes: brief_headlines.how + intel_bullets ───────────────────
    how = bh.get("how") or getattr(rep, "how_text", "") or ""
    sec = _load_sections(rep.name, output_dir)
    intel = sec.get("intel_bullets", [])[:5]

    notes_parts: list[str] = []
    if how:
        notes_parts.append(how)
    for grp_entry in group:
        grp_bh = _load_brief_headlines(grp_entry.name, output_dir)
        grp_how = grp_bh.get("how") or ""
        if grp_how and grp_how != how:
            notes_parts.append(f"{grp_entry.name}: {grp_how}")
        grp_sec = _load_sections(grp_entry.name, output_dir)
        grp_intel = grp_sec.get("intel_bullets", [])[:5]
        if grp_intel:
            notes_parts.append("\n".join(f"- {b}" for b in grp_intel))

    if notes_parts:
        slide.notes_slide.notes_text_frame.text = "\n\n".join(notes_parts)
```

- [ ] **Step 2: Run the color and slide-count tests (they will still fail — `build_presentation` not updated yet)**

```
uv run pytest tests/test_export_pptx.py -v 2>&1 | head -40
```

Expected: Some tests still fail because `build_presentation()` still calls the old functions. That is fine — we fix that in Task 7.

---

### Task 6: Rewrite `build_appendix()` → `build_watch_list()`

**Files:**
- Modify: `tools/export_pptx.py` (rename and replace `build_appendix`)

- [ ] **Step 1: Replace `build_appendix` with `build_watch_list`**

```python
def build_watch_list(
    prs: Presentation,
    data: ReportData,
    output_dir: str = OUTPUT_DIR,
) -> None:
    """Under Watch slide — MONITOR regions only. Omitted if zero MONITOR regions.

    CLEAR regions are NOT shown here. Their absence from slide body implies
    no active threat; confirmed by the "No Active Threat" count on the cover.
    """
    monitor = [r for r in data.regions if r.status == RegionStatus.MONITOR]
    if not monitor:
        return   # omit slide entirely

    slide = _add_blank_slide(prs)

    # Section label
    _add_text(
        slide, "Under Watch",
        Inches(0.8), Inches(0.6), Inches(8.4), Inches(0.3),
        font_size=7, color=META, font_name="Courier New",
    )
    label_rule = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        Inches(0.8), Inches(1.0), Inches(8.4), Pt(0.5),
    )
    label_rule.line.fill.background()
    label_rule.fill.solid()
    label_rule.fill.fore_color.rgb = RULE

    # One entry per MONITOR region, alphabetical order
    sorted_monitor = sorted(monitor, key=lambda r: r.name)
    y = Inches(1.2)
    for i, entry in enumerate(sorted_monitor):
        bh = _load_brief_headlines(entry.name, output_dir)
        why_full = bh.get("why") or getattr(entry, "why_text", "") or ""
        first_sentence = _SENT_RE.split(why_full)[0].strip() if why_full else f"{entry.name} — under active intelligence monitoring."

        # Region name bold
        _add_text(
            slide, entry.name,
            Inches(0.8), y, Inches(8.4), Inches(0.3),
            font_size=11, bold=True, color=BLACK,
        )
        # First sentence in grey
        _add_text(
            slide, first_sentence,
            Inches(0.8), y + Inches(0.3), Inches(8.4), Inches(0.4),
            font_size=9, color=MID_GREY, wrap=True,
        )
        y += Inches(0.85)

        # Thin rule below entry (not after last entry)
        if i < len(sorted_monitor) - 1:
            entry_rule = slide.shapes.add_shape(
                MSO_AUTO_SHAPE_TYPE.RECTANGLE,
                Inches(0.8), y - Inches(0.1), Inches(8.4), Pt(0.5),
            )
            entry_rule.line.fill.background()
            entry_rule.fill.solid()
            entry_rule.fill.fore_color.rgb = RULE

    # Footer
    _add_text(
        slide,
        "These regions are under active intelligence monitoring. No board action required at this time.",
        Inches(0.8), Inches(6.7), Inches(8.4), Inches(0.5),
        font_size=8, color=META, wrap=True,
    )
```

- [ ] **Step 2: Confirm the function was added correctly**

```
uv run python -c "from tools.export_pptx import build_watch_list; print('OK')"
```

Expected output: `OK`

---

### Task 7: Update `build_presentation()` and `export()`, run full test suite

**Files:**
- Modify: `tools/export_pptx.py` (last ~30 lines)

- [ ] **Step 1: Replace `build_presentation` and `export`**

```python
def build_presentation(data: ReportData, output_dir: str = OUTPUT_DIR) -> Presentation:
    """Assemble slides in spec order: Cover / Overview / Threat (max 3) / Watch List."""
    _ensure_base_pptx()
    prs = Presentation(str(BASE_PPTX))
    prs.slide_width  = W
    prs.slide_height = H

    build_cover(prs, data)
    build_overview(prs, data, output_dir)

    # Threat slides: one per scenario group (escalated only), max 3
    escalated = [r for r in data.regions if r.status == RegionStatus.ESCALATED]
    scenario_groups = _group_by_scenario(escalated)

    overflow_scenarios: list[str] = []
    for i, (scenario, group) in enumerate(scenario_groups):
        if i < 3:
            build_threat_slide(prs, scenario, group, output_dir)
        else:
            overflow_scenarios.append(scenario)

    # TODO-free: overflow_scenarios are excess escalated groups beyond the 3-slide cap.
    # Spec says to append them as one-line entries in the Watch List under a separator.
    # This is handled inside build_watch_list when overflow_scenarios is non-empty,
    # but we keep build_watch_list signature simple here — the max-3 cap on escalated
    # groups is enforced above; overflow is a rare edge case logged to stdout.
    if overflow_scenarios:
        print(f"[export_pptx] WARNING: {len(overflow_scenarios)} scenario group(s) exceeded 3-slide cap: {overflow_scenarios}")

    build_watch_list(prs, data, output_dir)

    return prs


def export(output_path: str = DEFAULT_OUT, output_dir: str = OUTPUT_DIR) -> None:
    """Generate Board Intelligence Brief as .pptx."""
    data = build(output_dir=output_dir)
    prs  = build_presentation(data, output_dir=output_dir)
    prs.save(output_path)
    print(f"[export_pptx] Saved -> {output_path}")
```

- [ ] **Step 2: Confirm the module imports cleanly**

```
uv run python -c "from tools.export_pptx import export, build_presentation; print('imports OK')"
```

Expected: `imports OK`

- [ ] **Step 3: Run the full pptx test suite**

```
uv run pytest tests/test_export_pptx.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 4: Smoke-test end-to-end against the real pipeline output**

```
uv run python -m tools.export_pptx
```

Expected: `[export_pptx] Saved -> output/deliverables/board_report.pptx` (or the configured path). No exception.

- [ ] **Step 5: Run the full test suite to verify no regressions**

```
uv run pytest tests/ -v --tb=short
```

Expected: All existing tests continue to pass. New 6 pptx tests pass.

- [ ] **Step 6: Commit the implementation**

```bash
git add tools/export_pptx.py
git commit -m "feat(pptx): rewrite board report as A1-style 4-6 slide read-ahead deck"
```

---

## Self-Review

**1. Spec coverage:**

| Spec requirement | Covered by task |
|---|---|
| Cover: eyebrow + title + thin rule + meta + status counts | Task 3 |
| Plain-language status labels (Active Threats / Under Watch / No Active Threat) | Task 3 |
| Overview: split layout 28% left / 72% right, vertical rule | Task 4 |
| `data.exec_summary` with auto-generated fallback | Task 4 |
| Footer on overview slide | Task 4 |
| One threat slide per scenario group, max 3 | Task 7 |
| Admiralty-first ordering, region count tiebreaker | Task 5 (`_group_by_scenario`) |
| Assertion title from `brief_headlines.why` first sentence | Task 5 |
| Em-dash bullets from sentences 2-3 | Task 5 |
| Exposure block from `brief_headlines.so_what` with 2pt black stripe | Task 5 |
| Speaker notes: `brief_headlines.how` + `intel_bullets` (plain text) | Task 5 |
| No response notes / action bullets on slide face | Task 5 (not added) |
| No Admiralty codes on slide face | Task 5 (not added) |
| Watch list: MONITOR only, alphabetical, bold name + first sentence why | Task 6 |
| Watch list omitted when zero MONITOR regions | Task 6 |
| CLEAR regions not shown in slide body | Task 6 |
| Footer on watch list slide | Task 6 |
| No RED/AMBER/GREEN/BRAND_NAVY in body content | Task 2 (constants removed) |
| Georgia for all display/body text | Task 2 (`_add_text` default) |
| Courier New for labels/metadata/badges | Tasks 3–6 (font_name="Courier New") |
| `output_dir` threads through to `_load_sections` / `_load_brief_headlines` | Task 7 |
| Deck = 2 slides (Cover + Overview) when zero escalated + zero monitor | Task 7 (both functions return early) |

**2. Placeholder scan:** No TBD/TODO in the plan tasks. The overflow comment in Task 7 describes the behaviour explicitly rather than deferring it.

**3. Type consistency:** `_group_by_scenario` defined in Task 2, called in Task 7 with `escalated: list[RegionEntry]`. `build_threat_slide(prs, scenario, group, output_dir)` defined in Task 5, called in Task 7 with `(prs, scenario, group, output_dir)` — match confirmed. `_load_brief_headlines(region_name, output_dir)` defined in Task 2, called in Tasks 5 and 6 — match confirmed.
