# Task 2 — report_builder.py Enrichment (Shared Extraction Layer)
**Assigned to:** Session A
**Blocks:** Task 3 (must complete before Task 3 starts)
**Blocked by:** Task 1 (must be complete — `source_quality` must be in `data.json`)
**Master plan:** `docs/superpowers/plans/2026-04-05-master-build-plan.md`

---

## What You Are Building

`report_builder.py` is the shared data layer consumed by all three exporters (PDF, PPTX, CISO docx). Currently it does thin extraction — 4 `board_bullets` (first sentences only). All the real intelligence extraction logic lives buried inside `export_ciso_docx.py`.

You will:
1. Move all extraction functions from `export_ciso_docx.py` into `report_builder.py`
2. Add 8 new fields to `RegionEntry` (7 intelligence sections + `source_quality`)
3. Make `export_ciso_docx.py` a pure renderer — reads from `RegionEntry` fields, does no extraction

After this task, all exporters get the same pre-extracted data. Task 3 (PDF + PPTX) can then build clean renderers without any content logic.

---

## Files to Read First

Read these in full before touching anything:

1. `tools/report_builder.py` — understand current `RegionEntry` dataclass and `build()` function
2. `tools/export_ciso_docx.py` — identify every extraction function to move (listed below)
3. `output/regional/apac/data.json` — verify `source_quality` field is present (Task 1 must be done)
4. `output/regional/apac/report.md` — understand the three-pillar structure (Why/How/So What)

---

## Change 1 — Move extraction functions into `report_builder.py`

The following functions and constants move FROM `export_ciso_docx.py` INTO `report_builder.py`. Copy them exactly — with one naming fix.

**NAMING FIX:** `export_ciso_docx.py` has a private `_sentences()` function. `report_builder.py` already has `_split_sentences()` — same regex, same logic, different name. When moving extraction functions that call `_sentences()` internally, replace every call to `_sentences()` with `_split_sentences()`. Do NOT create a duplicate `_sentences()` function in `report_builder.py`.

**Constants to move:**
```python
_SIGNAL_TYPE_LABELS = {
    "Event":   "Confirmed Incident",
    "Trend":   "Emerging Pattern",
    "Mixed":   "Confirmed Incident + Emerging Pattern",
    "Unknown": "Under Assessment",
}

_SCENARIO_ACTIONS: dict[str, list[str]] = {
    "Ransomware": [...],
    "System intrusion": [...],
    "Insider misuse": [...],
    "Accidental disclosure": [...],
}

_STATE_ACTORS = [...]   # the list of (keyword, label) tuples
_CRIMINAL_PAT = re.compile(...)   # the criminal actor pattern
```

**Functions to move:**
```python
def _signal_type_label(signal_type: str | None) -> str: ...
def _extract_threat_actor(why: str | None, how: str | None) -> str: ...
def _intel_bullets(why: str | None) -> list[str]: ...
def _adversary_bullets(how: str | None) -> list[str]: ...
def _impact_bullets(so_what: str | None) -> list[str]: ...
def _watch_bullets(how: str | None, so_what: str | None) -> list[str]: ...
def _action_bullets(scenario: str | None) -> list[str]: ...
```

These are pure functions — no side effects, no file I/O. They move cleanly.

---

## Change 2 — Update `RegionEntry` dataclass

Replace the current `RegionEntry` dataclass in `report_builder.py` with this target schema.

**Remove:** `vacr: float | None` — VaCR is not intelligence. `RegionEntry.vacr` only. `ReportData.total_vacr` stays untouched.

**Deprecate (do NOT remove yet):** `board_bullets: list[str] | None` — keep the field in the dataclass but set it to `None` in `build()`. Task 3 will remove all template/PPTX references to it. Only after Task 3 is validated should `board_bullets` be removed from the dataclass entirely. Removing it now breaks `export_pptx.py:232` and `report.html.j2:474` before Task 3 has updated them.

**Add 8 new fields** (after existing fields, before end of dataclass):

```python
@dataclass
class RegionEntry:
    # identity
    name: str
    status: RegionStatus

    # existing metadata (keep all)
    admiralty: str | None
    velocity: str | None
    severity: str | None
    scenario_match: str | None
    dominant_pillar: str | None
    signal_type: str | None
    confidence_label: str | None
    threat_characterisation: str | None
    top_sources: list[str] | None

    # raw pillar text (keep — used by extraction)
    why_text: str | None
    how_text: str | None
    so_what_text: str | None

    # NEW — pre-extracted intelligence sections
    threat_actor: str | None            # extracted from why+how text
    signal_type_label: str | None       # mapped display label
    intel_bullets: list[str]            # sentences from why_text, max 3
    adversary_bullets: list[str]        # sentences from how_text, max 2
    impact_bullets: list[str]           # sentences from so_what_text, non-VaCR, max 2
    watch_bullets: list[str]            # tradecraft from how/so_what overflow
    action_bullets: list[str]           # scenario-mapped recommended actions

    # NEW — source quality (populated by Task 1 enrich_region_data)
    source_quality: dict | None         # {"tier_a": 3, "tier_b": 8, "tier_c": 1, "total": 12}
```

---

## Change 3 — Update `build()` function in `report_builder.py`

In the `build()` function, where `RegionEntry` objects are constructed, populate the new fields:

```python
# After parsing pillars (why_text, how_text, so_what_text).
# For MONITOR/CLEAR regions why_text/how_text/so_what_text are None —
# the extraction functions handle None input and return [] or None safely.
# Explicitly: only call extraction functions when status == ESCALATED.
# For all other statuses set all bullet fields to [] and actor/label to None.

if status == RegionStatus.ESCALATED:
    threat_actor   = _extract_threat_actor(why_text, how_text)
    sig_type_label = _signal_type_label(d.get("signal_type"))
    intel_b        = _intel_bullets(why_text)
    adversary_b    = _adversary_bullets(how_text)
    impact_b       = _impact_bullets(so_what_text)
    watch_b        = _watch_bullets(how_text, so_what_text)
    action_b       = _action_bullets(d.get("primary_scenario"))
else:
    threat_actor   = None
    sig_type_label = _signal_type_label(d.get("signal_type"))  # label still useful for monitor
    intel_b        = []
    adversary_b    = []
    impact_b       = []
    watch_b        = []
    action_b       = []

source_quality = d.get("source_quality")  # written by enrich_region_data()

regions.append(RegionEntry(
    name=region_name,
    status=status,
    # existing fields...
    admiralty=d.get("admiralty"),
    velocity=d.get("velocity"),
    severity=d.get("severity"),
    scenario_match=d.get("primary_scenario"),
    dominant_pillar=d.get("dominant_pillar"),
    signal_type=d.get("signal_type"),
    why_text=why_text,
    how_text=how_text,
    so_what_text=so_what_text,
    confidence_label=_confidence_label(d.get("admiralty")),
    threat_characterisation=_threat_characterisation(d.get("dominant_pillar")),
    top_sources=top_sources,
    # new fields
    threat_actor=threat_actor,
    signal_type_label=sig_type_label,
    intel_bullets=intel_b,
    adversary_bullets=adversary_b,
    impact_bullets=impact_b,
    watch_bullets=watch_b,
    action_bullets=action_b,
    source_quality=source_quality,
))
```

Also remove: `board_bullets=_extract_board_bullets(...)` and `vacr=float(...)` from the constructor call. Remove `_extract_board_bullets()` function entirely from `report_builder.py`.

---

## Change 4 — Make `export_ciso_docx.py` a pure renderer

In `export_ciso_docx.py`:

**Remove** these functions (they now live in `report_builder.py`):
- `_signal_type_label()`
- `_extract_threat_actor()`
- `_intel_bullets()`
- `_adversary_bullets()`
- `_impact_bullets()`
- `_watch_bullets()`
- `_action_bullets()`
- `_SIGNAL_TYPE_LABELS` dict
- `_SCENARIO_ACTIONS` dict
- `_STATE_ACTORS` list
- `_CRIMINAL_PAT` pattern

**Keep** in `export_ciso_docx.py` (rendering logic specific to docx format):
- `SourceRegistry` class
- `_process_citations()`
- `_load_signal_sources()`
- `_build_signal_url_map()`
- `_load_clusters()`
- `_build_cluster_map()`
- `_infer_tier()`
- All `_build_*` document section functions
- `_add_*` document helper functions
- `_SKIP_SOURCES`, `_SKIP_PREFIXES`, `_NON_CITATION_RE`

**Update `_build_region_escalated()`** to read from `RegionEntry` fields instead of calling extraction functions:

```python
def _build_region_escalated(doc, entry: RegionEntry, registry, cluster_map):
    # Use entry.intel_bullets instead of _intel_bullets(entry.why_text)
    # Use entry.adversary_bullets instead of _adversary_bullets(entry.how_text)
    # Use entry.impact_bullets instead of _impact_bullets(entry.so_what_text)
    # Use entry.watch_bullets instead of _watch_bullets(entry.how_text, entry.so_what_text)
    # Use entry.action_bullets instead of _action_bullets(entry.scenario_match)
    # Use entry.threat_actor instead of _extract_threat_actor(entry.why_text, entry.how_text)
    # Use entry.signal_type_label instead of _signal_type_label(entry.signal_type)
```

**Update import** at top of `export_ciso_docx.py`:
```python
from report_builder import build, ReportData, RegionEntry, RegionStatus
# (no change needed — RegionEntry now has the fields)
```

---

## Done Criteria

- [ ] `report_builder.py` imports `re` and has all moved constants + functions
- [ ] `RegionEntry` has 8 new fields, no `vacr`, no `board_bullets`
- [ ] `build()` populates all 8 new fields for every escalated region
- [ ] `source_quality` is read from `d.get("source_quality")` — not computed in `report_builder`
- [ ] `export_ciso_docx.py` has no extraction functions (they all moved)
- [ ] `_build_region_escalated()` reads from `entry.*_bullets` not from calling extraction functions
- [ ] Run `uv run python -c "from tools.report_builder import build; d = build(); print(d.regions[0].intel_bullets)"` — no errors, returns list
- [ ] Run `uv run python tools/export_ciso_docx.py` — produces `output/ciso_brief.docx` without error

**Signal to Task 3:** "Task 2 complete. `RegionEntry` has all section fields. PDF and PPTX renderers can read from `entry.intel_bullets`, `entry.adversary_bullets`, `entry.impact_bullets`, `entry.watch_bullets`, `entry.action_bullets`, `entry.threat_actor`, `entry.signal_type_label`, `entry.source_quality`."
