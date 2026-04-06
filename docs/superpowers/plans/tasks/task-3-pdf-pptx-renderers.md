# Task 3 — Board PDF + PPTX Renderer Alignment
**Assigned to:** Session B (can run in parallel with Task 4)
**Blocks:** Nothing
**Blocked by:** Task 2 (must be complete — `RegionEntry` must have section fields)
**Master plan:** `docs/superpowers/plans/2026-04-05-master-build-plan.md`

---

## What You Are Building

Replace the 2×2 grid layout (DRIVER/EXPOSURE/IMPACT/WATCH) in the board PDF and PPTX with the proper 7-section intelligence structure that mirrors the CISO docx. Both outputs say "CISO Edition" — fix that too.

`RegionEntry` now has pre-extracted section fields (from Task 2). Your job is pure rendering — read the fields, render them correctly. No extraction logic.

---

## Files to Read First

Read these in full before touching anything:

1. `tools/report_builder.py` — understand the current `RegionEntry` dataclass (Task 2 will have updated it — verify the new fields exist: `intel_bullets`, `adversary_bullets`, `impact_bullets`, `watch_bullets`, `action_bullets`, `threat_actor`, `signal_type_label`, `source_quality`)
2. `tools/templates/report.html.j2` — current PDF template (what you are replacing)
3. `tools/export_pptx.py` — current PPTX builder (what you are updating)
4. `tools/export_ciso_docx.py` — the gold standard. Understand its section structure — your PDF and PPTX must mirror it.
5. `output/ciso_brief.docx` — if accessible, open it to see what the target looks like

**Verify Task 2 is done:** Run `uv run python -c "from tools.report_builder import RegionEntry; import dataclasses; print([f.name for f in dataclasses.fields(RegionEntry)])"` — confirm `intel_bullets`, `adversary_bullets` etc. are present.

**Your responsibility for `board_bullets`:** Task 2 deprecated `board_bullets` (set to `None` but kept the field). This task must remove ALL references to `board_bullets` from `report.html.j2` and `export_pptx.py`. After your done criteria pass and validation completes, the field can be removed from `RegionEntry` in a cleanup commit. Do not use `board_bullets` anywhere in your new code.

---

## Part A — Board PDF (`report.html.j2`)

### A-1: Fix cover page

Change:
```html
<div class="cover-subtitle">CISO Edition</div>
```
To: remove this line entirely (or replace with empty string — no subtitle needed).

### A-2: Replace per-region 2×2 grid with 7-section layout

Find the region pages section (the `{% for r in data.regions if r.status == "escalated" %}` block).

Replace the entire `{% if r.board_bullets ... %}` conditional block (the 2×2 grid and unavailable notice) with this 7-section layout:

```html
{# ── Region meta row ─────────────────────────────────────────────── #}
<div class="region-meta">
  {% if r.threat_actor %}
    <span class="meta-item"><strong>Threat Actor:</strong> {{ r.threat_actor }}</span>
  {% endif %}
  {% if r.signal_type_label %}
    <span class="meta-item"><strong>Signal Type:</strong> {{ r.signal_type_label }}</span>
  {% endif %}
</div>

{# ── Intelligence sections ─────────────────────────────────────────── #}
{% if r.intel_bullets %}
<div class="intel-section">
  <div class="section-heading">Intel Findings</div>
  <ul class="intel-list">
    {% for b in r.intel_bullets %}<li>{{ b }}</li>{% endfor %}
  </ul>
</div>
{% endif %}

{% if r.adversary_bullets %}
<div class="intel-section">
  <div class="section-heading">Observed Adversary Activity</div>
  <ul class="intel-list">
    {% for b in r.adversary_bullets %}<li>{{ b }}</li>{% endfor %}
  </ul>
</div>
{% endif %}

{% if r.impact_bullets %}
<div class="intel-section impact">
  <div class="section-heading">Impact for AeroGrid</div>
  <ul class="intel-list">
    {% for b in r.impact_bullets %}<li>{{ b }}</li>{% endfor %}
  </ul>
</div>
{% endif %}

{% if r.watch_bullets %}
<div class="intel-section watch">
  <div class="section-heading">Watch For — Adversary Tradecraft</div>
  <ul class="intel-list">
    {% for b in r.watch_bullets %}<li>{{ b }}</li>{% endfor %}
  </ul>
</div>
{% endif %}

{% if r.action_bullets %}
<div class="intel-section actions">
  <div class="section-heading">Recommended Actions</div>
  <ul class="intel-list">
    {% for b in r.action_bullets %}<li>{{ b }}</li>{% endfor %}
  </ul>
</div>
{% endif %}

{% if not r.intel_bullets and not r.adversary_bullets %}
<div class="unavailable-notice">
  Detailed intelligence analysis is unavailable for this region this cycle.
</div>
{% endif %}
```

### A-3: Add CSS for new section styles

Add to the `<style>` block (remove `.bullets-grid`, `.bullet-cell.*` classes — no longer needed):

```css
/* ── Region meta row ──────────────────────────────────────────────── */
.region-meta {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  font-size: 9px;
  color: var(--grey);
  margin-bottom: 4mm;
}
.region-meta .meta-item strong { color: #333; }

/* ── Intelligence sections ────────────────────────────────────────── */
.intel-section {
  margin-bottom: 4mm;
  padding-left: 3mm;
  border-left: 2px solid var(--navy);
}
.intel-section.impact  { border-left-color: var(--red); }
.intel-section.watch   { border-left-color: var(--amber); }
.intel-section.actions { border-left-color: #6b7280; }

.section-heading {
  font-size: 8px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--navy);
  margin-bottom: 3px;
}
.intel-section.impact  .section-heading { color: var(--red); }
.intel-section.watch   .section-heading { color: var(--amber); }
.intel-section.actions .section-heading { color: #6b7280; }

.intel-list {
  margin: 0;
  padding-left: 12px;
  font-size: 10px;
  line-height: 1.6;
  color: #333;
}
.intel-list li { margin-bottom: 2px; }
```

### A-4: Update region footer to include source_quality if present

In the `.region-footer` block, add source quality badge:

```html
{% if r.source_quality and r.source_quality.total > 0 %}
  <span style="margin-left:auto;">
    Sources: {{ r.source_quality.tier_a }}A
    · {{ r.source_quality.tier_b }}B
    · {{ r.source_quality.tier_c }}C
  </span>
{% elif r.top_sources %}
  <span style="margin-left:auto;font-style:italic;">
    Sources: {{ r.top_sources | join(" · ") }}
  </span>
{% endif %}
```

---

## Part B — Board PPTX (`export_pptx.py`)

### B-1: Fix cover slide

In `build_cover()`, find:
```python
_add_text(slide, "CISO Edition", ...)
```
Remove this line entirely.

### B-2: Replace region slide body

In `build_region()`, replace the entire `if region.board_bullets and len(region.board_bullets) >= 4:` block with a vertical 5-row intelligence structure.

The new layout for the region slide body:

```python
def build_region(prs: Presentation, region: RegionEntry) -> None:
    slide = _add_blank_slide(prs)

    # ── Header band ──────────────────────────────────────────────────
    _add_rect(slide, 0, 0, W, Inches(0.65), BRAND)
    _add_text(slide, region.name, Inches(0.3), Inches(0.1),
              Inches(6), Inches(0.45), font_size=16, bold=True, color=WHITE)
    _add_text(slide, region.scenario_match or "",
              Inches(0.3), Inches(0.38), Inches(6), Inches(0.25),
              font_size=9, color=RGBColor(0xBF, 0xDB, 0xFF))

    # Severity chip (keep existing logic)
    ...

    # ── Status label + meta row ──────────────────────────────────────
    status_label = _status_label(region.status, region.dominant_pillar)
    meta_parts = [status_label]
    if region.threat_actor:
        meta_parts.append(f"Threat Actor: {region.threat_actor}")
    if region.signal_type_label:
        meta_parts.append(region.signal_type_label)
    if region.confidence_label:
        meta_parts.append(f"Confidence: {region.confidence_label}")
    _add_text(slide, "  ·  ".join(meta_parts),
              Inches(0.3), Inches(0.75), Inches(9), Inches(0.28),
              font_size=9, color=SLATE)

    # ── 5 intelligence rows (vertical list) ─────────────────────────
    rows = [
        ("INTEL FINDINGS",       region.intel_bullets[0] if region.intel_bullets else None,      BRAND),
        ("ADVERSARY ACTIVITY",   region.adversary_bullets[0] if region.adversary_bullets else None, BRAND),
        ("IMPACT FOR AEROGRID",  region.impact_bullets[0] if region.impact_bullets else None,     RED),
        ("WATCH FOR",            region.watch_bullets[0] if region.watch_bullets else None,       AMBER),
        ("RECOMMENDED ACTION",   region.action_bullets[0] if region.action_bullets else None,     SLATE),
    ]

    y = Inches(1.1)
    row_h = Inches(1.0)
    for label, text, color in rows:
        if not text:
            y += row_h
            continue
        # Left border stripe
        _add_rect(slide, Inches(0.3), y, Inches(0.05), row_h - Inches(0.1), color)
        # Label
        _add_text(slide, label,
                  Inches(0.45), y, Inches(9), Inches(0.22),
                  font_size=7, bold=True, color=SLATE)
        # Content
        _add_text(slide, text,
                  Inches(0.45), y + Inches(0.22), Inches(9.1), row_h - Inches(0.32),
                  font_size=9, color=DARK, wrap=True)
        y += row_h

    # ── Footer ───────────────────────────────────────────────────────
    _add_text(slide, _vel_label(region.velocity),
              Inches(0.3), Inches(6.4), Inches(2.5), Inches(0.3),
              font_size=8, color=SLATE)
    _add_text(slide, region.threat_characterisation or "",
              Inches(3.0), Inches(6.4), Inches(4.0), Inches(0.3),
              font_size=8, color=SLATE)

    # Source quality badge
    sq = region.source_quality
    if sq and sq.get("total", 0) > 0:
        sq_text = f"Sources: {sq['tier_a']}A · {sq['tier_b']}B · {sq['tier_c']}C"
    elif region.top_sources:
        sq_text = "Sources: " + " · ".join(region.top_sources[:3])
    else:
        sq_text = ""
    if sq_text:
        _add_text(slide, sq_text,
                  Inches(0.3), Inches(6.8), Inches(9.4), Inches(0.28),
                  font_size=7, color=SLATE)

    # ── Speaker notes ────────────────────────────────────────────────
    notes_parts = []
    if region.intel_bullets:
        notes_parts.append("INTEL FINDINGS:\n" + "\n".join(f"• {b}" for b in region.intel_bullets))
    if region.adversary_bullets:
        notes_parts.append("ADVERSARY ACTIVITY:\n" + "\n".join(f"• {b}" for b in region.adversary_bullets))
    if region.impact_bullets:
        notes_parts.append("IMPACT FOR AEROGRID:\n" + "\n".join(f"• {b}" for b in region.impact_bullets))
    if region.watch_bullets:
        notes_parts.append("WATCH FOR:\n" + "\n".join(f"• {b}" for b in region.watch_bullets))
    if region.action_bullets:
        notes_parts.append("RECOMMENDED ACTIONS:\n" + "\n".join(f"• {b}" for b in region.action_bullets))

    if notes_parts:
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = "\n\n".join(notes_parts)
```

**Note on `_status_label`:** This function does NOT exist in `export_pptx.py` (confirmed — grep returns zero matches). It exists in `export_ciso_docx.py` only. Add it locally to `export_pptx.py`:

```python
def _status_label(status: RegionStatus, dominant_pillar: str | None = None) -> str:
    if status == RegionStatus.ESCALATED:
        if dominant_pillar == "Geopolitical": return "ESCALATED — GEO-LED"
        if dominant_pillar == "Cyber":        return "ESCALATED — CYBER-LED"
        return "ESCALATED"
    if status == RegionStatus.MONITOR: return "MONITOR"
    if status == RegionStatus.CLEAR:   return "CLEAR"
    return "UNKNOWN"
```

---

## Done Criteria

**PDF:**
- [ ] Cover page has no "CISO Edition" subtitle
- [ ] Per-region page shows Intel Findings, Adversary Activity, Impact for AeroGrid, Watch For, Recommended Actions sections
- [ ] Each section has a left border stripe (navy/red/amber/grey)
- [ ] Source quality badge in footer if `source_quality` present
- [ ] No 2×2 grid CSS or HTML remains (`bullets-grid`, `bullet-cell` classes removed)
- [ ] No `board_bullets` references remain in `report.html.j2`
- [ ] Run `uv run python tools/export_pdf.py` — produces `output/board_report.pdf` without error

**PPTX:**
- [ ] Cover slide has no "CISO Edition" text
- [ ] `_status_label()` defined locally in `export_pptx.py`
- [ ] Region slide has 5 labelled rows (INTEL FINDINGS / ADVERSARY ACTIVITY / IMPACT / WATCH FOR / RECOMMENDED ACTION)
- [ ] Each row has a left border stripe with correct colour
- [ ] Speaker notes contain full bullet arrays for all sections
- [ ] Source quality badge in footer
- [ ] No `board_bullets` references remain in `export_pptx.py`
- [ ] Run `uv run python tools/export_pptx.py` — produces `output/board_report.pptx` without error
