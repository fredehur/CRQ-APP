# CISO Weekly Brief Redesign — Implementation Plan

**Goal:** Restructure `tools/export_ciso_docx.py` to produce a threat-centric, 6-section CISO weekly brief with BLUF, threat grouping across regions, consolidated Action Register, and pure black/white visual style.

**Architecture:** Keep all existing infrastructure (`SourceRegistry`, `_process_citations`, `_build_signal_url_map`, `_build_cluster_map`, `_build_references`, `_build_footer_note`, font helpers). Replace the five old section builders (`_build_exec_summary`, `_build_region_escalated`, `_build_monitor_section`, `_build_global_opener`, `_build_cover`) with eight new ones. Wire them in `export()` in the new order. Old functions stay in the file until Task 7 removes them.

**Tech Stack:** `python-docx`, `pytest`, existing `report_builder.ReportData` / `RegionEntry`, `tools/config.py` paths.

---

## File Map

| File | Action | What changes |
|---|---|---|
| `tests/conftest.py` | Modify | Add `sections.json` files for APAC, AME, MED in the mock fixture |
| `tests/test_export_ciso_docx.py` | Create | 6 tests covering all spec criteria |
| `tools/export_ciso_docx.py` | Modify | Replace 5 old builders with 8 new ones; wire `export()` |

---

## Task 1: Extend conftest + write failing tests

**Files:**
- Modify: `tests/conftest.py`
- Create: `tests/test_export_ciso_docx.py`

### Step 1: Add `sections.json` mock data to conftest.py

Add the following constants and fixture extension **before** the `mock_output` fixture in `tests/conftest.py`:

```python
MOCK_SECTIONS = {
    "APAC": {
        "intel_bullets": ["Supply chain compromise detected in APAC wind sector [B2]"],
        "adversary_bullets": ["State-nexus actor using spear-phishing on OT networks"],
        "impact_bullets": ["$18.5M at risk across APAC operations"],
        "watch_bullets": ["Watch for further OT targeting if diplomatic tensions persist"],
        "action_bullets": [
            "Validate offline backup integrity for turbine control systems",
            "Brief regional ops on vendor access controls",
        ],
        "signal_type_label": "Confirmed Incident",
        "status_label": "[ESCALATED — GEO-LED]",
        "source_metadata": {
            "seerist": {"strength": "med", "hotspots": [], "pulse_delta": 1.2, "verified_event_count": 2},
            "osint": {"sources": ["Reuters", "CISA"], "source_count": 2},
        },
        "brief_headlines": {
            "why": "State-sponsored groups in the South China Sea corridor are targeting supply chain access. System intrusion attempts focus on OT networks at blade manufacturing plants.",
            "how": "System intrusion attempts targeting OT networks at blade manufacturing plants via spear-phishing campaigns directed at third-party vendors.",
            "so_what": "$18.5M at risk. Disruption threatens 75% of AeroGrid APAC manufacturing revenue.",
        },
    },
    "AME": {
        "intel_bullets": ["Ransomware campaign targeting North American energy sector [A1]"],
        "adversary_bullets": ["Double-extortion ransomware hitting backup systems"],
        "impact_bullets": ["$22M at risk — wind farm service delivery at stake"],
        "watch_bullets": ["Monitor for escalation if ransom demands increase sector-wide"],
        "action_bullets": [
            "Validate offline backup integrity for turbine control systems",
            "Review incident response readiness with regional security team",
        ],
        "signal_type_label": "Emerging Pattern",
        "status_label": "[ESCALATED — CYBER-LED]",
        "source_metadata": {
            "seerist": {"strength": "high", "hotspots": [], "pulse_delta": 2.1, "verified_event_count": 3},
            "osint": {"sources": ["Reuters", "CISA", "ENISA"], "source_count": 3},
        },
        "brief_headlines": {
            "why": "Ransomware groups are exploiting North American energy sector during regulatory transition. Double-extortion tactics target backup systems and operational databases.",
            "how": "Double-extortion ransomware targeting backup systems and operational databases across North American wind farm operations.",
            "so_what": "$22M at risk. Service delivery continuity for 25% of global operations at stake.",
        },
    },
    "MED": {
        "intel_bullets": [],
        "adversary_bullets": [],
        "impact_bullets": [],
        "watch_bullets": ["Insider misuse risk remains elevated in Mediterranean operations"],
        "action_bullets": [],
        "signal_type_label": "Emerging Pattern",
        "status_label": "[MONITOR]",
        "source_metadata": {
            "seerist": {"strength": "low", "hotspots": [], "pulse_delta": 0.5, "verified_event_count": 0},
            "osint": {"sources": [], "source_count": 0},
        },
        "brief_headlines": {
            "why": "Insider misuse indicators detected in Mediterranean operations. No escalation threshold reached.",
            "how": "Behavioural anomalies flagged in access logs for MED region facilities.",
            "so_what": "$4.2M at risk. Monitoring continues pending further signals.",
        },
    },
}
```

Inside the `mock_output` fixture, **after** writing the report.md files, add the `sections.json` writes:

```python
    # sections.json for regions that have one (escalated + monitor)
    for region in ["APAC", "AME", "MED"]:
        sdata = MOCK_SECTIONS[region]
        (tmp_path / "regional" / region.lower() / "sections.json").write_text(
            json.dumps(sdata), encoding="utf-8"
        )
```

- [ ] **Step 1a: Apply the conftest changes above**

- [ ] **Step 1b: Run existing tests to confirm no regression**

```bash
cd C:/Users/frede/crq-agent-workspace
python -m pytest tests/ -x -q 2>&1 | tail -20
```

Expected: all existing tests pass.

### Step 2: Create failing tests

Create `tests/test_export_ciso_docx.py`:

```python
"""Tests for the redesigned CISO weekly brief exporter (6-section, threat-centric)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import json
import pytest
from docx import Document
from docx.shared import RGBColor
import export_ciso_docx as ex


RED   = RGBColor(0xdc, 0x26, 0x26)
AMBER = RGBColor(0xd9, 0x77, 0x06)
GREEN = RGBColor(0x16, 0xa3, 0x4a)


def test_export_runs_without_error(mock_output, tmp_path):
    """export() writes a non-trivial .docx without raising."""
    out = str(tmp_path / "ciso_brief.docx")
    ex.export(output_path=out, output_dir=str(mock_output))
    assert os.path.exists(out)
    assert os.path.getsize(out) > 5_000


def test_docx_contains_bluf(mock_output, tmp_path):
    """BLUF sentence appears before PURPOSE section."""
    out = str(tmp_path / "ciso.docx")
    ex.export(output_path=out, output_dir=str(mock_output))
    doc = Document(out)
    texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    # BLUF must appear before PURPOSE OF THIS BRIEF
    bluf_idx = next((i for i, t in enumerate(texts) if "CISO attention" in t or "No threats escalated" in t), None)
    purpose_idx = next((i for i, t in enumerate(texts) if "PURPOSE OF THIS BRIEF" in t), None)
    assert bluf_idx is not None, "BLUF sentence not found"
    assert purpose_idx is not None, "PURPOSE section not found"
    assert bluf_idx < purpose_idx, "BLUF must appear before PURPOSE"


def test_docx_contains_all_section_headers(mock_output, tmp_path):
    """All 6 named section headers present in the document."""
    out = str(tmp_path / "ciso.docx")
    ex.export(output_path=out, output_dir=str(mock_output))
    doc = Document(out)
    full_text = "\n".join(p.text for p in doc.paragraphs)
    for header in [
        "PURPOSE OF THIS BRIEF",
        "INTELLIGENCE PICTURE",
        "THREAT ASSESSMENT",
        "SITUATION",
        "ACTION REGISTER",
        "CONSIDERATIONS",
    ]:
        assert header in full_text, f"Missing section header: {header}"


def test_watch_list_present_when_monitor_regions(mock_output, tmp_path):
    """WATCH LIST section appears when at least one region is MONITOR (MED in mock)."""
    out = str(tmp_path / "ciso.docx")
    ex.export(output_path=out, output_dir=str(mock_output))
    doc = Document(out)
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "WATCH LIST" in full_text


def test_action_register_deduplicates(mock_output, tmp_path):
    """Action text shared by APAC and AME appears exactly once in Action Register."""
    out = str(tmp_path / "ciso.docx")
    ex.export(output_path=out, output_dir=str(mock_output))
    doc = Document(out)
    full_text = "\n".join(p.text for p in doc.paragraphs)
    # Both APAC and AME mock sections contain "Validate offline backup integrity..."
    count = full_text.count("Validate offline backup integrity")
    assert count == 1, f"Expected 1 occurrence after dedup, got {count}"


def test_no_red_amber_green_in_body(mock_output, tmp_path):
    """No run in the document uses red, amber, or green font colour."""
    out = str(tmp_path / "ciso.docx")
    ex.export(output_path=out, output_dir=str(mock_output))
    doc = Document(out)
    for para in doc.paragraphs:
        for run in para.runs:
            try:
                colour = run.font.color.rgb
            except Exception:
                colour = None
            assert colour not in (RED, AMBER, GREEN), (
                f"Disallowed colour {colour} in: {para.text[:80]}"
            )
```

- [ ] **Step 2a: Write the file above**

- [ ] **Step 2b: Run tests to confirm they all fail**

```bash
python -m pytest tests/test_export_ciso_docx.py -v 2>&1 | tail -30
```

Expected: 6 FAILED (export() doesn't accept `output_dir` yet; section headers don't exist yet).

- [ ] **Step 2c: Commit**

```bash
git add tests/conftest.py tests/test_export_ciso_docx.py
git commit -m "test: add CISO brief redesign tests (all failing — TDD baseline)"
```

---

## Task 2: Visual style + simplified cover

**Files:**
- Modify: `tools/export_ciso_docx.py` — lines around `_add_subheading`, `_build_cover`, `_status_colour`

The goal: black/white only in body content. Section headers → grey 8pt. Cover → title + date + divider only (no page break, no status block).

### Step 1: Update `_add_subheading` (line ~277)

Replace:
```python
def _add_subheading(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    r = p.add_run(text)
    _font(r, 11, bold=True, colour=NAVY)
    p.paragraph_format.space_after = Pt(2)
```

With:
```python
def _add_subheading(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    r = p.add_run(text)
    _font(r, 8, bold=True, colour=GREY)
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(2)
```

### Step 2: Replace `_build_cover` (lines 299–333)

Replace the entire function with:
```python
def _build_cover(doc: Document, data: ReportData) -> None:
    """Header block — title, date, cycle. No page break. BLUF follows immediately."""
    p = doc.add_paragraph()
    r = p.add_run("AeroGrid Wind Solutions  —  CONFIDENTIAL")
    _font(r, 8, colour=GREY)
    p.paragraph_format.space_after = Pt(2)

    p = doc.add_paragraph()
    r = p.add_run("CISO Intelligence Brief")
    _font(r, 18, bold=True)
    p.paragraph_format.space_after = Pt(2)

    date_str = (
        data.timestamp[:10]
        if data.timestamp and data.timestamp != "unknown"
        else datetime.now().strftime("%Y-%m-%d")
    )
    p = doc.add_paragraph()
    r = p.add_run(f"{date_str}  ·  Cycle {data.run_id}")
    _font(r, 9, colour=GREY)

    _add_divider(doc)
```

### Step 3: Run no-colour test (partial pass)

```bash
python -m pytest tests/test_export_ciso_docx.py::test_no_red_amber_green_in_body -v
```

This will still fail because the old section builders use RED/AMBER/GREEN. That's expected — the test will pass fully only after Task 7 removes the old builders from `export()`.

### Step 4: Commit

```bash
git add tools/export_ciso_docx.py
git commit -m "style: CISO brief — black/white visual style, simplified cover header"
```

---

## Task 3: New helper functions

**Files:**
- Modify: `tools/export_ciso_docx.py` — add 5 new functions after the existing `_load_brief_headlines` function (line ~524)

Add all five functions in this block, directly after `_load_brief_headlines`:

```python
# ── New helpers: threat grouping, source signal, cycle delta ──────────────────

_SENT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"\'(])')


def _split_why(text: str, max_bullets: int = 3) -> list[str]:
    """Split a why/how paragraph into sentence-length bullets."""
    if not text:
        return []
    sentences = [s.strip() for s in _SENT_RE.split(text) if s.strip()]
    return sentences[:max_bullets]


def _group_by_scenario(
    entries: list,  # list[RegionEntry]
) -> list[tuple[str, list]]:
    """Group RegionEntry list by scenario_match. Preserves insertion order.

    Returns list of (scenario_key, [entries]) tuples. Regions with no
    scenario_match are grouped under their region name.
    """
    groups: dict[str, list] = {}
    for entry in entries:
        key = entry.scenario_match or f"Unknown — {entry.name}"
        groups.setdefault(key, []).append(entry)
    return list(groups.items())


def _load_source_signal(region_name: str) -> str:
    """Return '(N sources · N corroborated)' string, or '' if data absent."""
    try:
        path = (
            Path(OUTPUT_DIR).parent
            / "regional"
            / region_name.lower()
            / "sections.json"
        )
        sections = json.loads(path.read_text(encoding="utf-8"))
        sm = sections.get("source_metadata", {})
        source_count = sm.get("osint", {}).get("source_count", 0)
        verified = sm.get("seerist", {}).get("verified_event_count", 0)
        if source_count:
            corr = f" · {verified} corroborated" if verified else ""
            return f"({source_count} sources{corr})"
    except Exception:
        pass
    return ""


def _get_previous_escalated_count() -> int | None:
    """Return escalated region count from most recent archived run, or None."""
    try:
        runs_dir = Path(OUTPUT_DIR) / "runs"
        if not runs_dir.exists():
            return None
        for run_dir in sorted(runs_dir.iterdir(), reverse=True):
            grp = run_dir / "global_report.json"
            if grp.exists():
                report = json.loads(grp.read_text(encoding="utf-8"))
                return len(report.get("regional_threats", []))
    except Exception:
        pass
    return None


def _build_bluf(doc: Document, data: ReportData) -> None:
    """One-sentence bottom line. No label. Top of document, after cover."""
    escalated = [r for r in data.regions if r.status == RegionStatus.ESCALATED]
    groups = _group_by_scenario(escalated)

    if not groups:
        sentence = (
            f"No threats escalated this cycle — "
            f"{data.monitor_count} region{'s' if data.monitor_count != 1 else ''} at monitor."
        )
    else:
        _WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five"}
        count = len(groups)
        word = _WORDS.get(count, str(count))
        noun = "threat requires" if count == 1 else "threats require"
        parts = []
        for scenario, entries in groups:
            codes = " / ".join(e.name for e in entries)
            parts.append(f"{scenario} ({codes})")
        joined = "; ".join(parts)
        sentence = f"{word} {noun} CISO attention this week: {joined}."

    p = doc.add_paragraph()
    r = p.add_run(sentence)
    _font(r, 11, bold=True)
    p.paragraph_format.space_after = Pt(6)
```

- [ ] **Step 3a: Add the block above to `tools/export_ciso_docx.py` after `_load_brief_headlines`**

- [ ] **Step 3b: Run smoke check**

```bash
cd C:/Users/frede/crq-agent-workspace
python -c "import sys; sys.path.insert(0,'tools'); import export_ciso_docx; print('OK')"
```

Expected: `OK` — no import errors.

- [ ] **Step 3c: Commit**

```bash
git add tools/export_ciso_docx.py
git commit -m "feat(ciso): add _group_by_scenario, _load_source_signal, _build_bluf helpers"
```

---

## Task 4: `_build_purpose` + `_build_intelligence_picture`

**Files:**
- Modify: `tools/export_ciso_docx.py` — add two new builder functions after the helpers block from Task 3

Add both functions after `_build_bluf`:

```python
def _build_purpose(doc: Document, data: ReportData) -> None:
    """Section 0 — static boilerplate with date + cycle injected."""
    _add_subheading(doc, "PURPOSE OF THIS BRIEF")

    date_str = (
        data.timestamp[:10]
        if data.timestamp and data.timestamp != "unknown"
        else datetime.now().strftime("%Y-%m-%d")
    )
    text = (
        f"This brief provides AeroGrid Wind Solutions' CISO with a consolidated "
        f"geopolitical and cyber threat assessment for the week of {date_str}. "
        f"Intelligence current as of {date_str}. "
        f"It covers 5 operational regions (APAC, AME, LATAM, MED, NCE) and is produced "
        f"by the CRQ agentic intelligence pipeline (Cycle {data.run_id}). "
        f"Intended for internal decision-making and upward briefing. "
        f"Not for external distribution."
    )
    _add_normal(doc, text, italic=True, colour=GREY)
    _add_divider(doc)


def _build_intelligence_picture(doc: Document, data: ReportData) -> None:
    """Section 1 — status counts, cycle delta, global framing paragraph."""
    _add_subheading(doc, "INTELLIGENCE PICTURE")

    # Status count line + cycle delta
    prev = _get_previous_escalated_count()
    if prev is None:
        delta_str = ""
    elif data.escalated_count > prev:
        delta_str = f"  (+{data.escalated_count - prev} since last cycle)"
    elif data.escalated_count < prev:
        delta_str = f"  (−{prev - data.escalated_count} since last cycle)"
    else:
        delta_str = "  (unchanged)"

    p = doc.add_paragraph()
    r = p.add_run(
        f"{data.escalated_count} escalated  ·  "
        f"{data.monitor_count} monitored  ·  "
        f"{data.clear_count} clear{delta_str}"
    )
    _font(r, 10, colour=GREY)

    # Global framing — prefer management_summary, fall back to executive_summary,
    # fall back to auto-generated sentence
    summary = ""
    try:
        base = Path(OUTPUT_DIR)
        global_report = json.loads(
            (base / "global_report.json").read_text(encoding="utf-8")
        )
        summary = (
            global_report.get("management_summary")
            or global_report.get("executive_summary", "")
        )
    except Exception:
        pass

    if not summary:
        escalated_names = [
            r.name for r in data.regions if r.status == RegionStatus.ESCALATED
        ]
        names_str = ", ".join(escalated_names) if escalated_names else "none"
        verb = "is" if len(escalated_names) == 1 else "are"
        mon_word = "region" if data.monitor_count == 1 else "regions"
        summary = (
            f"This cycle, {names_str} {verb} escalated. "
            f"{data.monitor_count} {mon_word} remain on monitor."
        )

    _add_normal(doc, summary)
    _add_divider(doc)
```

- [ ] **Step 4a: Add both functions to `tools/export_ciso_docx.py`**

- [ ] **Step 4b: Smoke check**

```bash
python -c "import sys; sys.path.insert(0,'tools'); import export_ciso_docx; print('OK')"
```

Expected: `OK`

- [ ] **Step 4c: Commit**

```bash
git add tools/export_ciso_docx.py
git commit -m "feat(ciso): add _build_purpose, _build_intelligence_picture"
```

---

## Task 5: `_build_threat_assessments` + `_build_situation`

**Files:**
- Modify: `tools/export_ciso_docx.py` — add two new builders after `_build_intelligence_picture`

```python
def _build_threat_assessments(
    doc: Document,
    data: ReportData,
    registry: SourceRegistry,
    cluster_map: dict[str, str],
) -> None:
    """Section 2 — one block per threat group (regions sharing same scenario_match)."""
    escalated = [r for r in data.regions if r.status == RegionStatus.ESCALATED]
    if not escalated:
        return

    _add_subheading(doc, "THREAT ASSESSMENT")

    groups = _group_by_scenario(escalated)

    for scenario, entries in groups:
        entry = entries[0]  # use first entry for shared fields
        codes = " / ".join(e.name for e in entries)
        pillar = entry.dominant_pillar or "UNKNOWN"
        admiralty = entry.admiralty or "—"

        # Threat header line
        p = doc.add_paragraph()
        r = p.add_run(f"{scenario}  —  {codes}")
        _font(r, 12, bold=True)

        # Badge + metadata line
        p2 = doc.add_paragraph()
        r2 = p2.add_run("ESCALATED")
        _font(r2, 8, bold=True)
        r3 = p2.add_run(f"   {pillar}-LED  ·  Admiralty {admiralty}")
        _font(r3, 8, colour=GREY)
        p2.paragraph_format.space_after = Pt(2)

        # Source signal line (per-region, joined)
        sig_parts = []
        for e in entries:
            sig = _load_source_signal(e.name)
            if sig:
                sig_parts.append(f"{e.name} {sig}")
        if sig_parts:
            p3 = doc.add_paragraph()
            r4 = p3.add_run("  ".join(sig_parts))
            _font(r4, 8, italic=True, colour=GREY)
            p3.paragraph_format.space_after = Pt(4)

        # Talking points from brief_headlines.why (first entry with non-empty why)
        why_bullets: list[str] = []
        for e in entries:
            bh = _load_brief_headlines(e.name)
            why = bh.get("why") or e.why_text or ""
            if why:
                why_bullets = _split_why(why, max_bullets=3)
                break

        for bullet in why_bullets:
            _add_bullet(doc, f"{bullet} [{admiralty}]")

        # Impact from brief_headlines.so_what
        so_what = ""
        for e in entries:
            bh = _load_brief_headlines(e.name)
            so_what = bh.get("so_what") or e.so_what_text or ""
            if so_what:
                break
        if so_what:
            p4 = doc.add_paragraph()
            r5 = p4.add_run("Impact:  ")
            _font(r5, 10, bold=True)
            r6 = p4.add_run(so_what)
            _font(r6, 10)

        _add_divider(doc)


def _build_situation(
    doc: Document,
    data: ReportData,
    registry: SourceRegistry,
    cluster_map: dict[str, str],
) -> None:
    """Section 3 — ground truth per threat group: brief_headlines.how + intel_bullets."""
    escalated = [r for r in data.regions if r.status == RegionStatus.ESCALATED]
    if not escalated:
        return

    _add_subheading(doc, "SITUATION")

    groups = _group_by_scenario(escalated)

    def proc(text: str) -> str:
        return _process_citations(text, registry, cluster_map)

    for scenario, entries in groups:
        entry = entries[0]
        bh = _load_brief_headlines(entry.name)
        how = bh.get("how") or entry.how_text or ""

        p = doc.add_paragraph()
        r = p.add_run(scenario)
        _font(r, 10, bold=True)
        p.paragraph_format.space_after = Pt(2)

        if how:
            _add_normal(doc, proc(how))

        # Supporting intel bullets (max 3 from first entry)
        for b in entry.intel_bullets[:3]:
            _add_bullet(doc, proc(b))

    _add_divider(doc)
```

- [ ] **Step 5a: Add both functions to `tools/export_ciso_docx.py`**

- [ ] **Step 5b: Smoke check**

```bash
python -c "import sys; sys.path.insert(0,'tools'); import export_ciso_docx; print('OK')"
```

Expected: `OK`

- [ ] **Step 5c: Commit**

```bash
git add tools/export_ciso_docx.py
git commit -m "feat(ciso): add _build_threat_assessments, _build_situation"
```

---

## Task 6: `_build_watch_list`, `_build_action_register`, `_build_considerations`

**Files:**
- Modify: `tools/export_ciso_docx.py` — add three new builders after `_build_situation`

```python
def _build_watch_list(doc: Document, data: ReportData) -> None:
    """Section 4 — one line per MONITOR region. Omitted if none."""
    monitor_entries = [r for r in data.regions if r.status == RegionStatus.MONITOR]
    if not monitor_entries:
        return

    _add_subheading(doc, "WATCH LIST")

    for entry in monitor_entries:
        bh = _load_brief_headlines(entry.name)
        why = bh.get("why") or entry.why_text or ""
        # First sentence only
        first = why.split(".")[0].strip() if why else "Under assessment"
        if first and not first.endswith("."):
            first += "."

        p = doc.add_paragraph()
        r1 = p.add_run(f"{entry.name}  ")
        _font(r1, 10, bold=True)
        r2 = p.add_run("MONITOR")
        _font(r2, 8, colour=GREY)
        r3 = p.add_run(f"  —  {first}")
        _font(r3, 10)
        p.paragraph_format.space_after = Pt(3)

    _add_divider(doc)


def _build_action_register(doc: Document, data: ReportData) -> None:
    """Section 5 — all action_bullets consolidated, deduplicated, numbered."""
    escalated = [r for r in data.regions if r.status == RegionStatus.ESCALATED]
    if not escalated:
        return

    # Collect: action_text -> [region_names] (preserving insertion order)
    action_map: dict[str, list[str]] = {}
    for entry in escalated:
        for bullet in entry.action_bullets:
            key = bullet.strip()
            if not key:
                continue
            if key not in action_map:
                action_map[key] = []
            if entry.name not in action_map[key]:
                action_map[key].append(entry.name)

    if not action_map:
        return

    _add_subheading(doc, "ACTION REGISTER")

    total_regions = len(escalated)
    for i, (bullet, regions) in enumerate(action_map.items(), 1):
        # Show region suffix only when multiple escalated regions exist
        if total_regions > 1:
            suffix = f"  —  {', '.join(regions)}"
        else:
            suffix = ""
        p = doc.add_paragraph()
        r = p.add_run(f"{i}.  {bullet}{suffix}")
        _font(r, 10)
        p.paragraph_format.space_after = Pt(3)

    _add_divider(doc)


def _build_considerations(
    doc: Document,
    data: ReportData,
    registry: SourceRegistry,
    cluster_map: dict[str, str],
) -> None:
    """Section 6 — watch_bullets from escalated regions + global management_summary."""
    _add_subheading(doc, "CONSIDERATIONS")

    def proc(text: str) -> str:
        return _process_citations(text, registry, cluster_map)

    # Watch bullets from all escalated regions (max 3 total)
    watch_bullets: list[str] = []
    for entry in data.regions:
        if entry.status == RegionStatus.ESCALATED:
            watch_bullets.extend(entry.watch_bullets)

    for bullet in watch_bullets[:3]:
        _add_bullet(doc, proc(bullet))

    # Global management_summary as final bullet if present
    try:
        base = Path(OUTPUT_DIR)
        global_report = json.loads(
            (base / "global_report.json").read_text(encoding="utf-8")
        )
        mgmt = global_report.get("management_summary", "")
        if mgmt:
            _add_bullet(doc, proc(mgmt))
    except Exception:
        pass

    _add_divider(doc)
```

- [ ] **Step 6a: Add the three functions to `tools/export_ciso_docx.py`**

- [ ] **Step 6b: Smoke check**

```bash
python -c "import sys; sys.path.insert(0,'tools'); import export_ciso_docx; print('OK')"
```

Expected: `OK`

- [ ] **Step 6c: Commit**

```bash
git add tools/export_ciso_docx.py
git commit -m "feat(ciso): add _build_watch_list, _build_action_register, _build_considerations"
```

---

## Task 7: Wire `export()` + run all tests

**Files:**
- Modify: `tools/export_ciso_docx.py` — replace the `export()` function body; add `output_dir` parameter

### Step 1: Replace `export()` (lines ~567–594)

Replace the entire `export` function with:

```python
def export(output_path: str = DEFAULT_OUT, output_dir: str = OUTPUT_DIR) -> None:
    """Build and save the CISO weekly intelligence brief as a .docx.

    Args:
        output_path: destination file path for the .docx
        output_dir:  pipeline output directory (default: output/pipeline).
                     Override in tests to point at a mock fixture.
    """
    from report_builder import build as _build
    data        = _build(output_dir=output_dir)
    url_map     = _build_signal_url_map()
    registry    = SourceRegistry(url_map=url_map)
    cluster_map = _build_cluster_map()
    doc         = Document()

    for section in doc.sections:
        section.top_margin    = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin   = Cm(2.5)
        section.right_margin  = Cm(2.5)

    _build_cover(doc, data)
    _build_bluf(doc, data)
    _build_purpose(doc, data)
    _build_intelligence_picture(doc, data)
    _build_threat_assessments(doc, data, registry, cluster_map)
    _build_situation(doc, data, registry, cluster_map)
    _build_watch_list(doc, data)
    _build_action_register(doc, data)
    _build_considerations(doc, data, registry, cluster_map)
    _build_references(doc, registry)
    _build_footer_note(doc, data)

    doc.save(output_path)
    print(f"[export_ciso_docx] saved → {output_path}", file=sys.stderr)
```

> **Note:** The old functions `_build_exec_summary`, `_build_region_escalated`, `_build_monitor_section`, and `_build_global_opener` are no longer called from `export()`. Leave them in the file for now — they can be deleted in a follow-up cleanup commit once all tests are green.

### Step 2: Run all tests

```bash
python -m pytest tests/test_export_ciso_docx.py -v
```

Expected output:
```
tests/test_export_ciso_docx.py::test_export_runs_without_error PASSED
tests/test_export_ciso_docx.py::test_docx_contains_bluf PASSED
tests/test_export_ciso_docx.py::test_docx_contains_all_section_headers PASSED
tests/test_export_ciso_docx.py::test_watch_list_present_when_monitor_regions PASSED
tests/test_export_ciso_docx.py::test_action_register_deduplicates PASSED
tests/test_export_ciso_docx.py::test_no_red_amber_green_in_body PASSED

6 passed in X.XXs
```

If any test fails, diagnose before moving on. Common failures:
- `test_no_red_amber_green_in_body` fails → a new builder is accidentally calling `_status_colour()` which still returns RED/AMBER/GREEN. Search for `_status_colour` calls in the new builders and remove them.
- `test_action_register_deduplicates` fails → check that both APAC and AME mock sections.json have the exact same string for the shared action bullet.

### Step 3: Run full test suite (no regressions)

```bash
python -m pytest tests/ -v 2>&1 | tail -30
```

Expected: all existing tests still pass.

### Step 4: Smoke test the actual output

```bash
python -m tools.export_ciso_docx 2>&1 | tail -5
```

Expected: `[export_ciso_docx] saved → output/deliverables/ciso_brief.docx` (or similar path from `DEFAULT_OUT`).

Open the output file in Word or LibreOffice to visually verify:
- Document starts with "CISO Intelligence Brief" header
- BLUF sentence below the header
- 6 named sections in order
- No colour in body text
- References section at end

### Step 5: Commit

```bash
git add tools/export_ciso_docx.py
git commit -m "feat(ciso): wire new 8-section export() — threat-centric CISO weekly brief"
```

---

## Self-Review

### Spec coverage check

| Spec requirement | Task |
|---|---|
| BLUF — top of page 1 | Task 3 `_build_bluf`, Task 7 wire |
| Purpose + intelligence cutoff date | Task 4 `_build_purpose` |
| Intelligence Picture + cycle delta | Task 4 `_build_intelligence_picture` |
| Threat Assessment — per THREAT not per region | Task 5 `_build_threat_assessments` + `_group_by_scenario` |
| Source corroboration signal | Task 3 `_load_source_signal`, Task 5 |
| Talking points from `brief_headlines.why` | Task 5 |
| Impact from `brief_headlines.so_what` | Task 5 |
| Situation — `brief_headlines.how` + intel_bullets | Task 5 `_build_situation` |
| Watch List — MONITOR regions only, absent if none | Task 6 `_build_watch_list` |
| Action Register — deduplicated, all regions | Task 6 `_build_action_register` |
| Considerations — watch_bullets + management_summary | Task 6 `_build_considerations` |
| References — SourceRegistry (unchanged) | Kept as-is |
| A1 visual — black/white, Georgia, no colour | Task 2 |
| `export()` accepts `output_dir` for testability | Task 7 |

All spec requirements covered. No placeholders. ✓
