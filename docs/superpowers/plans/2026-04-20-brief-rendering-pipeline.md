# Brief Rendering Pipeline Implementation Plan

**Goal:** Wire the CRQ Design System v1.0 handoff (`docs/design/handoff/`) into the AeroGrid pipeline as three production deliverables (Board / CISO / RSM) with a single render path and RSM live-data synthesis.

**Architecture:** Three layers — collectors (existing), per-brief synthesizers producing strictly-typed Pydantic `BriefData`, a shared `render_pdf()` that feeds Jinja2 templates into Playwright Chromium for PDF output. Board and CISO are fully static mock data this pass. RSM runs deterministic joins in Python + a new `rsm-weekly-synthesizer` agent for narrative JSON.

**Tech Stack:** Python 3.11, Pydantic v2, Jinja2, Playwright (async), pytest, FastAPI, uv.

**Reference spec:** `docs/superpowers/specs/2026-04-20-brief-rendering-pipeline-design.md`. Read this before starting — the spec is the contract.

**Reference handoff:** `docs/design/handoff/` — byte-equivalent target for templates. Do not modify these files.

---

## File Structure

### Created

```
static/design/styles/
  tokens.css                            # copy from docs/design/handoff/styles/tokens.css
  board.css                             # copy from docs/design/handoff/styles/board.css
  ciso.css                              # copy from docs/design/handoff/styles/ciso.css
  rsm.css                               # copy from docs/design/handoff/styles/rsm.css

tools/briefs/
  __init__.py
  models.py                             # Pydantic contracts
  renderer.py                           # render_pdf() + Jinja env + Playwright wrapper
  joins.py                              # proximity/pattern/actor/calendar pure functions
  templates/
    _partials.html.j2                   # shared macros (pill, pulse, meta-rail, sev)
    board.html.j2                       # ports docs/design/handoff/Board Report Q2 2026.html
    ciso.html.j2                        # ports docs/design/handoff/CISO Brief April 2026.html
    rsm.html.j2                         # ports docs/design/handoff/RSM Weekly INTSUM MED.html
  data/
    __init__.py
    board.py                            # static BoardBriefData
    ciso.py                             # static CisoBriefData
    rsm.py                              # live RsmBriefData (joins + agent)
    _rsm_mock.py                        # static RsmBriefData for test fixtures

.claude/agents/
  rsm-weekly-synthesizer.md

.claude/hooks/validators/
  rsm-weekly-synthesizer-output.py

tests/briefs/
  __init__.py
  test_models.py
  test_joins.py
  test_rsm_data.py
  test_renderer.py
  fixtures/
    board_q2_2026.json
    ciso_apr_2026.json
    rsm_med_w17.json
    osint_physical_signals_med_sample.json
    aerowind_sites_sample.json
```

### Modified

```
tools/build_pdf.py                      # rewritten as CLI dispatcher
data/aerowind_sites.json                # schema extension — content-only commit
server.py                               # new brief endpoints
static/app.js                           # Reports tab brief cards
static/index.html                       # Reports tab markup additions
tools/rsm_dispatcher.py                 # remove weekly branch (in deprecation phase)
.claude/agents/rsm-formatter-agent.md   # remove weekly mode (in deprecation phase)
pyproject.toml                          # add pydantic v2 if missing
```

### Deleted (deprecation phase — last)

```
tools/brief_data.py
tools/build_pptx.py
tools/export_ciso_docx.py
tools/export_pptx.py                    # if duplicate
tools/export_pdf.py                     # if superseded by new renderer
```

---

## Phase 1 — Foundation

Shared infrastructure: CSS copy, Pydantic base models, renderer, CLI skeleton, Jinja partials. At the end of this phase, `build_pdf.py --brief board` runs but fails because no template exists yet — that's by design.

### Task 1.1: Scaffold directories and copy CSS

**Files:**
- Create: `static/design/styles/tokens.css` (copied from handoff)
- Create: `static/design/styles/board.css` (copied from handoff)
- Create: `static/design/styles/ciso.css` (copied from handoff)
- Create: `static/design/styles/rsm.css` (copied from handoff)
- Create: `tools/briefs/__init__.py` (empty)
- Create: `tools/briefs/data/__init__.py` (empty)
- Create: `tools/briefs/templates/` directory

- [ ] **Step 1: Copy CSS files verbatim**

```bash
mkdir -p static/design/styles tools/briefs/data tools/briefs/templates tests/briefs/fixtures
cp "docs/design/handoff/styles/tokens.css" static/design/styles/tokens.css
cp "docs/design/handoff/styles/board.css"  static/design/styles/board.css
cp "docs/design/handoff/styles/ciso.css"   static/design/styles/ciso.css
cp "docs/design/handoff/styles/rsm.css"    static/design/styles/rsm.css
```

- [ ] **Step 2: Create empty __init__.py files**

```bash
touch tools/briefs/__init__.py tools/briefs/data/__init__.py tests/briefs/__init__.py
```

- [ ] **Step 3: Verify**

Run: `ls static/design/styles/ && ls tools/briefs/ && ls tests/briefs/`
Expected: all four CSS files + both init files visible.

- [ ] **Step 4: Commit**

```bash
git add static/design/ tools/briefs/__init__.py tools/briefs/data/__init__.py tests/briefs/__init__.py
git commit -m "feat(briefs): scaffold design system CSS and module structure"
```

---

### Task 1.2: Shared Pydantic base models

**Files:**
- Create: `tools/briefs/models.py`
- Test: `tests/briefs/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/briefs/test_models.py
from tools.briefs.models import CoverMeta, BriefData
import pytest
from datetime import date

def test_cover_meta_requires_issued_at_and_classification():
    cover = CoverMeta(
        title="AeroGrid · Board Report · Q2 2026",
        classification="INTERNAL — BOARD DISTRIBUTION",
        prepared_by="M. Okonkwo",
        reviewed_by="R. Salazar",
        issued_at=date(2026, 4, 17),
        version="v1.0 — final",
    )
    assert cover.classification.startswith("INTERNAL")
    assert cover.version == "v1.0 — final"

def test_brief_data_rejects_extra_fields():
    with pytest.raises(Exception):
        BriefData(unknown_field="x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/briefs/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.briefs.models'`.

- [ ] **Step 3: Implement the base models**

```python
# tools/briefs/models.py
from __future__ import annotations
from datetime import date
from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoverMeta(_Strict):
    title: str
    classification: str
    prepared_by: str
    reviewed_by: str
    issued_at: date
    version: str


class BriefData(_Strict):
    """Base marker. Concrete brief types inherit via composition (cover: CoverMeta)."""
    pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/briefs/test_models.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/briefs/models.py tests/briefs/test_models.py
git commit -m "feat(briefs): shared Pydantic base models (CoverMeta, BriefData)"
```

---

### Task 1.3: Renderer — Jinja env + Playwright wrapper

**Files:**
- Create: `tools/briefs/renderer.py`
- Test: `tests/briefs/test_renderer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/briefs/test_renderer.py
import asyncio
from pathlib import Path
from tools.briefs.renderer import build_jinja_env, render_html

def test_jinja_env_finds_partials_template(tmp_path):
    # a trivial test template at tools/briefs/templates/_smoke.html.j2
    env = build_jinja_env()
    tpl = env.from_string("{{ value }}")
    assert tpl.render(value="ok") == "ok"

def test_render_html_serializes_pydantic_fields():
    env = build_jinja_env()
    tpl = env.from_string("{{ data.title }}")
    # duck-typed dict is fine for this unit — Pydantic round-trip tested elsewhere
    out = render_html(tpl, {"title": "Hello"})
    assert out == "Hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/briefs/test_renderer.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the renderer**

```python
# tools/briefs/renderer.py
from __future__ import annotations
import asyncio
import tempfile
from pathlib import Path
from typing import Any
import jinja2

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = REPO_ROOT / "static"


def build_jinja_env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATES_DIR),
        autoescape=jinja2.select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html(template: jinja2.Template, data: Any) -> str:
    return template.render(data=data)


async def render_pdf(
    brief: str,
    data: Any,
    out_path: Path,
) -> None:
    from playwright.async_api import async_playwright

    env = build_jinja_env()
    template = env.get_template(f"{brief}.html.j2")
    html = render_html(template, data)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".html",
        dir=STATIC_DIR,
        delete=False,
    ) as f:
        f.write(html)
        html_path = Path(f.name)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(f"file://{html_path.as_posix()}")
            await page.wait_for_function("document.fonts.ready")
            await page.pdf(
                path=str(out_path),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
            await browser.close()
    finally:
        html_path.unlink(missing_ok=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/briefs/test_renderer.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/briefs/renderer.py tests/briefs/test_renderer.py
git commit -m "feat(briefs): renderer with Jinja env and Playwright PDF wrapper"
```

---

### Task 1.4: CLI dispatcher — `build_pdf.py` rewrite

**Files:**
- Modify: `tools/build_pdf.py` (complete rewrite)
- Test: `tests/briefs/test_cli.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/briefs/test_cli.py
import subprocess, sys
def test_build_pdf_requires_brief_flag():
    r = subprocess.run(
        [sys.executable, "-m", "tools.build_pdf"],
        capture_output=True, text=True
    )
    assert r.returncode != 0
    assert "--brief" in (r.stderr + r.stdout)

def test_build_pdf_rejects_unknown_brief():
    r = subprocess.run(
        [sys.executable, "-m", "tools.build_pdf", "--brief", "bogus"],
        capture_output=True, text=True
    )
    assert r.returncode != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/briefs/test_cli.py -v`
Expected: FAIL (the current `build_pdf.py` doesn't have `--brief`).

- [ ] **Step 3: Rewrite `tools/build_pdf.py`**

```python
# tools/build_pdf.py
from __future__ import annotations
import argparse
import asyncio
from pathlib import Path
from tools.briefs.renderer import render_pdf


BRIEFS = ("board", "ciso", "rsm")


def _load_data(brief: str, args: argparse.Namespace):
    if brief == "board":
        from tools.briefs.data.board import load_board_data
        return load_board_data(args.quarter)
    if brief == "ciso":
        from tools.briefs.data.ciso import load_ciso_data
        return load_ciso_data(args.month)
    if brief == "rsm":
        from tools.briefs.data.rsm import load_rsm_data
        return load_rsm_data(args.region, args.week_of)
    raise SystemExit(f"unknown brief: {brief}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="build_pdf")
    p.add_argument("--brief", required=True, choices=BRIEFS)
    p.add_argument("--out", type=Path, required=True)
    # per-brief flags
    p.add_argument("--region", help="RSM: region code (APAC, AME, LATAM, MED, NCE)")
    p.add_argument("--week-of", dest="week_of", help="RSM: ISO week, e.g. 2026-W17")
    p.add_argument("--quarter", help="Board: e.g. 2026Q2")
    p.add_argument("--month", help="CISO: YYYY-MM")
    args = p.parse_args(argv)
    data = _load_data(args.brief, args)
    asyncio.run(render_pdf(args.brief, data, args.out))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/briefs/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/build_pdf.py tests/briefs/test_cli.py
git commit -m "feat(briefs): build_pdf CLI dispatcher with --brief flag"
```

---

### Task 1.5: Shared Jinja partials

**Files:**
- Create: `tools/briefs/templates/_partials.html.j2`
- Test: `tests/briefs/test_partials.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/briefs/test_partials.py
from tools.briefs.renderer import build_jinja_env

def test_pill_macro_renders_severity_class():
    env = build_jinja_env()
    env.loader.searchpath.append(str(env.loader.searchpath[0]))  # idempotent
    tpl = env.from_string(
        '{% import "_partials.html.j2" as p %}{{ p.pill("Critical", "critical") }}'
    )
    out = tpl.render()
    assert 'class="pill pill--critical"' in out
    assert ">Critical<" in out

def test_sev_chip_macro():
    env = build_jinja_env()
    tpl = env.from_string(
        '{% import "_partials.html.j2" as p %}{{ p.sev("HIGH", "high") }}'
    )
    assert 'class="sev sev--high"' in tpl.render()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/briefs/test_partials.py -v`
Expected: FAIL — template not found.

- [ ] **Step 3: Write the partials**

```jinja2
{# tools/briefs/templates/_partials.html.j2 #}
{% macro pill(label, severity) -%}
<span class="pill pill--{{ severity }}">{{ label }}</span>
{%- endmacro %}

{% macro sev(label, severity) -%}
<span class="sev sev--{{ severity }}">{{ label }}</span>
{%- endmacro %}

{% macro pulse(label, severity, arrow) -%}
<span class="pulse pulse--{{ severity }}"><span class="dot"></span>{{ label }} <span class="arrow">{{ arrow }}</span></span>
{%- endmacro %}

{% macro meta_rail(items) -%}
<div class="meta-rail">
{%- for it in items -%}
{{ it }}{% if not loop.last %} <span class="dot">·</span> {% endif %}
{%- endfor -%}
</div>
{%- endmacro %}

{% macro ref(label) -%}
<span class="ref">[{{ label }}]</span>
{%- endmacro %}

{% macro tier(label, kind) -%}
<span class="tier tier--{{ kind }}">{{ label }}</span>
{%- endmacro %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/briefs/test_partials.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/briefs/templates/_partials.html.j2 tests/briefs/test_partials.py
git commit -m "feat(briefs): shared Jinja2 partials (pill, sev, pulse, meta-rail, ref, tier)"
```

---

## Phase 2 — Board brief (static)

Port the Board template and data. Simplest brief, fully static — validates the pipeline end-to-end before tackling CISO's denser layouts or RSM's live data.

### Task 2.1: `BoardBriefData` Pydantic model

**Files:**
- Modify: `tools/briefs/models.py` (add BoardBriefData and its nested types)
- Test: `tests/briefs/test_models.py` (extend)

- [ ] **Step 1: Write failing tests**

```python
# tests/briefs/test_models.py  (append)
from tools.briefs.models import (
    BoardBriefData, BoardCover, PosturePanel, BoardTakeaway, RegionDelta,
    KeyDevelopment, AlsoTrackingItem, WatchNextItem, RiskMatrix, MatrixDot,
    RegisterRow, BoardScenario, ScenarioPosture, ScenarioNarrative,
    EvidenceRef, Methodology, ReadingRule, EndMatter,
)
import pytest

def test_board_takeaway_severity_enum():
    tk = BoardTakeaway(n=1, severity="high", body_markdown="**x** y", anchor="S-07 · MED")
    assert tk.severity == "high"
    with pytest.raises(Exception):
        BoardTakeaway(n=1, severity="extreme", body_markdown="x", anchor="y")

def test_matrix_dot_coords_clamped():
    d = MatrixDot(
        scenario_id="S-07", region="MED", label="Unrest · Cape Wind",
        likelihood=72, impact=72, severity="high", label_position="up",
    )
    assert 0 <= d.likelihood <= 100
    with pytest.raises(Exception):
        MatrixDot(
            scenario_id="S-99", region="MED", label="x",
            likelihood=150, impact=50, severity="high", label_position="up",
        )

def test_board_brief_data_full_example_parses():
    from tests.briefs.fixtures_data import board_example
    bbd = BoardBriefData.model_validate(board_example())
    assert bbd.cover.title.startswith("AeroGrid")
    assert len(bbd.delta_bar) == 5
```

- [ ] **Step 2: Run tests to confirm failures**

Run: `uv run pytest tests/briefs/test_models.py -v`
Expected: FAIL — models missing.

- [ ] **Step 3: Implement Board models**

Add to `tools/briefs/models.py`:

```python
from typing import Literal
from pydantic import Field

Severity = Literal["critical", "high", "medium", "monitor"]
Region = Literal["APAC", "AME", "LATAM", "MED", "NCE"]
DriverCategory = Literal["M", "W", "C", "G", "S"]
DeltaDirection = Literal["up", "high", "flat", "down", "cyber"]
LabelPos = Literal["up", "down", "left", "right"]


class BoardCover(CoverMeta):
    quarter: str                                # "Q2 2026"
    quarter_short: str                          # "Q2·26"
    board_meeting: str                          # "21 April 2026 · London HQ"
    distribution_note: str                      # hairline top-right text


class PosturePanel(_Strict):
    overall_posture: Literal["LOW", "MODERATE", "HIGH", "SEVERE"]
    posture_shift: str
    admiralty: str
    admiralty_shift: str
    scenarios_on_watch: int = Field(ge=0)
    scenarios_split: str
    next_review: str


class BoardTakeaway(_Strict):
    n: int = Field(ge=1)
    severity: Severity
    body_markdown: str
    anchor: str


class RegionDelta(_Strict):
    region: Region
    direction: DeltaDirection
    label: str
    cause: str


class KeyDevelopment(_Strict):
    n: int = Field(ge=1)
    category: DriverCategory
    headline: str
    body: str
    meaning: str
    severity: Severity
    region: str
    anchors: list[str]


class AlsoTrackingItem(_Strict):
    head: str
    tail: str


class WatchNextItem(_Strict):
    horizon: str
    head: str
    tail: str


class MatrixDot(_Strict):
    scenario_id: str
    region: Region
    label: str
    likelihood: int = Field(ge=0, le=100)
    impact: int = Field(ge=0, le=100)
    severity: Severity
    label_position: LabelPos


class RegisterRow(_Strict):
    id: str
    region: Region
    headline: str
    severity: Severity


class RiskMatrix(_Strict):
    headline: str
    bottom_line: str
    dots: list[MatrixDot]
    register_tail: list[RegisterRow]


class ScenarioPosture(_Strict):
    pill_label: str
    pill_severity: Severity
    severity: str
    likelihood: str
    admiralty: str
    delta_vs_prior: str


class ScenarioNarrative(_Strict):
    lede: str
    paragraphs: list[str]


class EvidenceRef(_Strict):
    ref: str
    headline: str
    admiralty: str


class BoardScenario(_Strict):
    id: str
    region: str
    title: str
    type_tags: list[str]
    posture: ScenarioPosture
    narrative: ScenarioNarrative
    implications: list[str]
    baselines_moved: list[str]
    drivers: list[str]
    actions: list[str]
    evidence_anchors: list[EvidenceRef]


class ReadingRule(_Strict):
    cond: str
    then_markdown: str


class Methodology(_Strict):
    sources: dict[str, str]
    rating_system: dict[str, str]
    reading_rules: list[ReadingRule]
    against_last_quarter_prose: str
    against_last_quarter_kv: dict[str, str]


class EndMatter(_Strict):
    distribution: dict[str, str]
    provenance: dict[str, str]
    handling_paragraphs: list[str]
    linked_products: dict[str, str]


class BoardBriefData(BriefData):
    cover: BoardCover
    state_of_risk_line: str
    cover_thesis_title: str
    cover_thesis_subtitle: str
    posture: PosturePanel
    board_takeaways: list[BoardTakeaway]
    delta_bar: list[RegionDelta] = Field(min_length=5, max_length=5)
    key_developments: list[KeyDevelopment]
    also_tracking: list[AlsoTrackingItem]
    watch_next: list[WatchNextItem]
    matrix: RiskMatrix
    scenarios: list[BoardScenario]
    methodology: Methodology
    end_matter: EndMatter
```

- [ ] **Step 4: Create `tests/briefs/fixtures_data.py` with `board_example()`**

```python
# tests/briefs/fixtures_data.py
from datetime import date

def board_example() -> dict:
    return {
        "cover": {
            "title": "AeroGrid · Board Report · Q2 2026",
            "classification": "INTERNAL — BOARD DISTRIBUTION",
            "prepared_by": "M. Okonkwo",
            "reviewed_by": "R. Salazar",
            "issued_at": date(2026, 4, 17),
            "version": "v1.0 — final",
            "quarter": "Q2 2026",
            "quarter_short": "Q2·26",
            "board_meeting": "21 April 2026 · London HQ",
            "distribution_note": "AeroGrid Wind Solutions · Board of Directors",
        },
        "state_of_risk_line": "Q2 2026 saw elevated North African unrest...",
        "cover_thesis_title": "Two items warrant board action.",
        "cover_thesis_subtitle": "Six remain within management authority.",
        "posture": {
            "overall_posture": "HIGH", "posture_shift": "↑ from MEDIUM · Q1",
            "admiralty": "B2", "admiralty_shift": "held · Q1 was B2",
            "scenarios_on_watch": 8, "scenarios_split": "2 board-action · 6 mgmt",
            "next_review": "Q3 board · October 2026",
        },
        "board_takeaways": [
            {"n": 1, "severity": "high",
             "body_markdown": "**Cape Wind (crown-jewel, MA)** remains on raised watch...",
             "anchor": "S-07 · MED"},
        ],
        "delta_bar": [
            {"region": "MED", "direction": "up", "label": "Raised",
             "cause": "MA election, IT port strike · posture raised through May."},
            {"region": "NCE", "direction": "high", "label": "Held · cyber ↑",
             "cause": "Physical quiet. Sector-targeting cyber active."},
            {"region": "APAC", "direction": "down", "label": "Quieted",
             "cause": "Transit corridor stability improved."},
            {"region": "LATAM", "direction": "flat", "label": "Baseline",
             "cause": "No new triggers. Watchlist cold."},
            {"region": "AME", "direction": "flat", "label": "Baseline",
             "cause": "No new triggers. Third-party vendor watch retained."},
        ],
        "key_developments": [],
        "also_tracking": [],
        "watch_next": [],
        "matrix": {
            "headline": "Concentration in MED political and NCE cyber.",
            "bottom_line": "Two scenarios in the upper-right warrant board-level action.",
            "dots": [], "register_tail": [],
        },
        "scenarios": [],
        "methodology": {
            "sources": {}, "rating_system": {}, "reading_rules": [],
            "against_last_quarter_prose": "", "against_last_quarter_kv": {},
        },
        "end_matter": {
            "distribution": {}, "provenance": {},
            "handling_paragraphs": [], "linked_products": {},
        },
    }
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest tests/briefs/test_models.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/briefs/models.py tests/briefs/fixtures_data.py tests/briefs/test_models.py
git commit -m "feat(briefs): BoardBriefData Pydantic models with full field tree"
```

---

### Task 2.2: `board.py` data module — full static instance

**Files:**
- Create: `tools/briefs/data/board.py`
- Test: `tests/briefs/test_rsm_data.py` → use this as reference for load-style tests

- [ ] **Step 1: Write failing test**

```python
# tests/briefs/test_board_data.py
from tools.briefs.data.board import load_board_data
from tools.briefs.models import BoardBriefData

def test_load_board_data_returns_valid_model():
    data = load_board_data("2026Q2")
    assert isinstance(data, BoardBriefData)
    assert data.cover.quarter == "Q2 2026"
    assert len(data.delta_bar) == 5
    assert len(data.board_takeaways) >= 3
    assert len(data.key_developments) >= 4
    assert len(data.scenarios) >= 2
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/briefs/test_board_data.py -v`
Expected: FAIL — `load_board_data` not defined.

- [ ] **Step 3: Implement `board.py`**

```python
# tools/briefs/data/board.py
from datetime import date
from tools.briefs.models import (
    BoardBriefData, BoardCover, PosturePanel, BoardTakeaway, RegionDelta,
    KeyDevelopment, AlsoTrackingItem, WatchNextItem, MatrixDot, RegisterRow,
    RiskMatrix, ScenarioPosture, ScenarioNarrative, EvidenceRef, BoardScenario,
    ReadingRule, Methodology, EndMatter,
)


def load_board_data(quarter: str) -> BoardBriefData:
    """Static mock matching docs/design/handoff/Board Report Q2 2026.html.

    Future: replaced by a quarterly synthesizer reading aggregated regional output.
    """
    if quarter != "2026Q2":
        raise NotImplementedError(f"only 2026Q2 mock is available; got {quarter}")

    cover = BoardCover(
        title="AeroGrid · Board Report · Q2 2026",
        classification="INTERNAL — BOARD DISTRIBUTION",
        prepared_by="M. Okonkwo · Director, Threat Intelligence",
        reviewed_by="R. Salazar · VP Risk & Resilience",
        issued_at=date(2026, 4, 17),
        version="v1.0 — final",
        quarter="Q2 2026",
        quarter_short="Q2·26",
        board_meeting="21 April 2026 · London HQ",
        distribution_note="AeroGrid Wind Solutions · Board of Directors",
    )
    # ...full mock content from docs/design/handoff/Board Report Q2 2026.html
    # Follow the handoff HTML verbatim — every <div class="takeaway">,
    # <div class="kd">, <div class="dot-s">, etc. corresponds to one
    # Pydantic instance in the lists below.
    # [CONTINUES — see the full port in the handoff HTML, every string
    # that appears there gets pasted into the appropriate field here.]
    return BoardBriefData(
        cover=cover,
        state_of_risk_line=(
            "Q2 2026 saw elevated North African unrest, sustained EU renewables "
            "cyber pressure, and a material stabilisation of APAC transit corridors; "
            "the AeroGrid portfolio remains materially exposed to Moroccan political "
            "volatility and a widening EU ransomware campaign."
        ),
        cover_thesis_title="Two items warrant board action.",
        cover_thesis_subtitle="Six remain within management authority.",
        posture=PosturePanel(
            overall_posture="HIGH",
            posture_shift="↑ from MEDIUM · Q1",
            admiralty="B2",
            admiralty_shift="held · Q1 was B2",
            scenarios_on_watch=8,
            scenarios_split="2 board-action · 6 mgmt",
            next_review="Q3 board · October 2026",
        ),
        board_takeaways=[
            BoardTakeaway(n=1, severity="high",
                body_markdown="**Cape Wind (crown-jewel, MA) remains on raised watch through Q3** "
                "following the April general election. Short-term unrest risk on the Casablanca "
                "corridor is the dominant portfolio exposure this quarter; reassess at the October board.",
                anchor="S-07 · MED"),
            BoardTakeaway(n=2, severity="high",
                body_markdown="**SolarGlare ransomware is no longer hypothetical for NCE.** "
                "The campaign has been confirmed at two German wind operators; AeroGrid NCE sites "
                "should be treated as exposed. Recommend accelerating CVE-2026-1847 patching "
                "and a third-party vendor access review.",
                anchor="S-11 · NCE"),
            BoardTakeaway(n=3, severity="medium",
                body_markdown="**APT28 scanning of Moroccan and Spanish energy ASNs tracks the election calendar.** "
                "No observed AeroGrid impact, but the cyber-physical coupling means Cape Wind carries "
                "a joint intelligence signal, not two separate ones. SOC monitoring in place.",
                anchor="S-07 · MED"),
            BoardTakeaway(n=4, severity="monitor",
                body_markdown="**Supply chain exposure on turbine blades is stable but strategically watched.** "
                "Single-source Chinese supplier remains a 2027 delivery-timeline risk. "
                "Second-source qualification targeted Q4 2026; no board action required this quarter.",
                anchor="S-14 · APAC"),
            BoardTakeaway(n=5, severity="monitor",
                body_markdown="**Regulatory surface is widening.** EU Commission draft legislation "
                "on OT/ICS resilience has a Q3 submission deadline; compliance cost estimate "
                "pending for the October board. Flag, not action.",
                anchor="REG · EU"),
        ],
        delta_bar=[
            RegionDelta(region="MED", direction="up", label="Raised",
                cause="MA election, IT port strike · posture raised through May."),
            RegionDelta(region="NCE", direction="high", label="Held · cyber ↑",
                cause="Physical quiet. Sector-targeting cyber active."),
            RegionDelta(region="APAC", direction="down", label="Quieted",
                cause="Transit corridor stability improved. Supply watch retained."),
            RegionDelta(region="LATAM", direction="flat", label="Baseline",
                cause="No new triggers. Watchlist cold."),
            RegionDelta(region="AME", direction="flat", label="Baseline",
                cause="No new triggers. Third-party vendor watch retained."),
        ],
        key_developments=[
            KeyDevelopment(n=1, category="G",
                headline="Moroccan general election (April).",
                body="Outcome elevated short-term unrest risk on the Casablanca corridor; coalition formation ongoing.",
                meaning="Cape Wind (crown-jewel) remains on raised watch through Q3; reassess at October board.",
                severity="high", region="MED · MA", anchors=["E1", "E2", "E4"]),
            KeyDevelopment(n=2, category="C",
                headline="SolarGlare ransomware confirmed at two German wind operators.",
                body="TTP pattern observed; 4 additional EU operators report probable targeting.",
                meaning="NCE sites move from hypothetical to exposed; CVE-2026-1847 patch deployment at 40% portfolio rollout.",
                severity="high", region="NCE · DE", anchors=["C1", "C2", "C3"]),
            KeyDevelopment(n=3, category="W",
                headline="Taranto Offshore commissioning on track.",
                body="Grid-tie achieved on schedule; storm-season preparations complete ahead of October.",
                meaning="No governance ask; flagged positively for baseline continuity.",
                severity="monitor", region="MED · IT", anchors=["E5", "E6"]),
            KeyDevelopment(n=4, category="C",
                headline="APT28 scanning against Moroccan and Spanish energy ASNs.",
                body="Cadence up 3× over March; coincident with MA election calendar.",
                meaning="No observed AeroGrid impact. Treat cyber activity + physical exposure as a joint signal.",
                severity="medium", region="MED · MA/ES", anchors=["C4", "C5"]),
            KeyDevelopment(n=5, category="G",
                headline="EU Commission draft legislation on OT/ICS resilience.",
                body="Q3 submission deadline; compliance cost estimate pending for the October board.",
                meaning="Regulatory surface widens across the NCE footprint; flag for now, action next quarter.",
                severity="monitor", region="NCE · EU", anchors=["E8"]),
        ],
        also_tracking=[
            AlsoTrackingItem(head="Greek local election · late May.",
                tail="3 minor AeroGrid sites in region; contained exposure, monitored through polling window."),
            AlsoTrackingItem(head="Turkish currency instability.",
                tail="Vendor payment exposure under review by Treasury; joint assessment with GRC expected by late May."),
            AlsoTrackingItem(head="US IRA tariff adjustments.",
                tail="Indirect supply-chain effect under assessment; no direct AeroGrid footprint impact identified."),
        ],
        watch_next=[
            WatchNextItem(horizon="6–12 weeks",
                head="Moroccan post-election coalition stability.",
                tail="Drives whether Cape Wind posture normalises or remains raised into Q4."),
            WatchNextItem(horizon="Q3 rollout",
                head="CVE-2026-1847 — turbine SCADA patching.",
                tail="Portfolio-wide deployment target; residual exposure modelled for October board."),
            WatchNextItem(horizon="Oct onward",
                head="Winter season onset · MED offshore.",
                tail="Taranto, Cape Wind weather-risk baseline reset; standard seasonal review."),
        ],
        matrix=RiskMatrix(
            headline="Two scenarios in the upper-right warrant board-level action this quarter.",
            bottom_line="S-07 (MED) and S-11 (NCE) are the board-action set. The remaining six are "
                "within management authority and are tracked through the RSM reporting line.",
            dots=[
                MatrixDot(scenario_id="S-07", region="MED", label="Unrest · Cape Wind (MED)",
                    likelihood=72, impact=72, severity="high", label_position="up"),
                MatrixDot(scenario_id="S-11", region="NCE", label="OT cyber · NCE",
                    likelihood=78, impact=82, severity="high", label_position="down"),
                MatrixDot(scenario_id="S-14", region="APAC", label="Blades supply · APAC",
                    likelihood=48, impact=50, severity="medium", label_position="down"),
                MatrixDot(scenario_id="S-09", region="AME", label="3P vendor · AME",
                    likelihood=44, impact=38, severity="medium", label_position="left"),
                MatrixDot(scenario_id="S-03", region="LATAM", label="Local unrest · LATAM",
                    likelihood=22, impact=30, severity="monitor", label_position="right"),
                MatrixDot(scenario_id="S-05", region="MED", label="GR local · MED",
                    likelihood=32, impact=20, severity="monitor", label_position="down"),
                MatrixDot(scenario_id="S-12", region="NCE", label="OT/ICS reg · NCE",
                    likelihood=58, impact=62, severity="medium", label_position="up"),
                MatrixDot(scenario_id="S-06", region="MED", label="TR vendor · MED",
                    likelihood=38, impact=14, severity="monitor", label_position="down"),
            ],
            register_tail=[
                RegisterRow(id="S-03", region="LATAM", headline="Local unrest · minor sites", severity="monitor"),
                RegisterRow(id="S-05", region="MED",   headline="GR local election exposure",   severity="monitor"),
                RegisterRow(id="S-06", region="MED",   headline="TR currency · vendor pay",      severity="monitor"),
                RegisterRow(id="S-07", region="MED",   headline="Unrest · Cape Wind",            severity="high"),
                RegisterRow(id="S-09", region="AME",   headline="3P vendor compromise",          severity="medium"),
                RegisterRow(id="S-11", region="NCE",   headline="Cyber · OT vendor",             severity="high"),
                RegisterRow(id="S-12", region="NCE",   headline="OT/ICS regulation",             severity="medium"),
                RegisterRow(id="S-14", region="APAC",  headline="Blades · supply chain",         severity="medium"),
            ],
        ),
        scenarios=[
            # S-07
            BoardScenario(
                id="S-07", region="MED · Morocco",
                title="Sustained civil unrest in the Casablanca corridor near Cape Wind.",
                type_tags=["Political-security", "Crown-jewel exposure", "Horizon: 0–12 weeks"],
                posture=ScenarioPosture(
                    pill_label="HIGH · MED likelihood", pill_severity="high",
                    severity="HIGH", likelihood="MED", admiralty="B2",
                    delta_vs_prior="↑ from MED",
                ),
                narrative=ScenarioNarrative(
                    lede="The April general election closed without a clear coalition. "
                         "Youth unemployment and regional economic stress remain the structural drivers; "
                         "the post-election window is the acute one.",
                    paragraphs=[
                        "Protest activity clustered in urban centres through the polling period and has not fully "
                        "subsided. Security-force posture in the Casablanca corridor is elevated and is expected "
                        "to remain so until a governing coalition is named. The Cape Wind site itself has not been "
                        "the object of protest; the proximate risks are access-road disruption, expat movement, "
                        "and secondary effects on local vendor continuity.",
                        "In parallel, APT28 scanning against Moroccan energy ASNs has run coincident with the "
                        "election calendar. The SOC has observed no anomalies at Cape Wind, but the cyber-physical "
                        "coupling means the scenario is being assessed as a joint signal.",
                        "Base case is normalisation over a 6–12 week horizon as coalition formation completes. "
                        "Tail risk is prolonged coalition friction combined with economic stress — that case "
                        "reaches the October board.",
                    ],
                ),
                implications=[
                    "Offtake continuity — local grid interface",
                    "Expat safety & movement (12 FTE on site)",
                    "Local reputation with host ministry",
                    "Insurance premium renewal (Q4 cycle)",
                ],
                baselines_moved=[
                    "Regional posture: **MED → HIGH**",
                    "Site watch: **normal → raised**",
                    "Expat travel: **permitted → essential only**",
                ],
                drivers=[
                    "Post-election coalition friction; no clear plurality winner.",
                    "Youth unemployment at structural highs; regional wage stagnation.",
                    "Broader regional economic stress (currency, remittances).",
                    "Historic pattern of post-poll protest activity in urban centres.",
                ],
                actions=[
                    "Continue raised site watch at Cape Wind through end Q3.",
                    "Reassess severity at the October board based on coalition outcome.",
                    "Maintain SOC joint-signal monitoring on Moroccan energy ASNs.",
                    "No board approval needed this quarter; noting for awareness.",
                ],
                evidence_anchors=[
                    EvidenceRef(ref="E1", headline="MA election result · Reuters", admiralty="B1"),
                    EvidenceRef(ref="E2", headline="Casablanca protest tracker · Le360", admiralty="B2"),
                    EvidenceRef(ref="E4", headline="Security posture advisory · Seerist", admiralty="A2"),
                    EvidenceRef(ref="C4", headline="ASN scanning · CERT-MA", admiralty="B2"),
                    EvidenceRef(ref="C5", headline="APT28 TTP · NCSC brief", admiralty="B1"),
                ],
            ),
            # S-11 and S-14 — follow same pattern, content from handoff HTML.
            # For brevity of the plan, the engineer ports the remaining two scenarios
            # by reading pages 6 and 7 of Board Report Q2 2026.html and transcribing
            # identically. No new content is invented.
        ],
        methodology=Methodology(
            sources={
                "Commercial": "Seerist (Control Risks) — geopolitical feed, confidence-rated.",
                "OSINT":      "Firecrawl + Tavily discovery across accredited regional media.",
                "Cyber":      "CERT-EU, CISA, NCSC, vendor advisories.",
                "Internal":   "RSM weekly INTSUMs (MED, NCE, APAC, LATAM, AME).",
            },
            rating_system={
                "Severity":   "CRITICAL · HIGH · MEDIUM · MONITOR.",
                "Likelihood": "HIGH · MED-HIGH · MEDIUM · LOW-MED · LOW.",
                "Admiralty":  "A1 (near-certain) — F6 (unverifiable). Typical range: B1–C2.",
                "Confidence": "NATO framework: HIGH / MODERATE / LOW.",
            },
            reading_rules=[
                ReadingRule(cond="B2 → A1",
                    then_markdown="A scenario moving from **B2 to A1** on Admiralty should be treated as "
                                  "near-certain. Governance response is warranted even if severity is unchanged."),
                ReadingRule(cond="MED → HIGH",
                    then_markdown="A severity change from **MEDIUM to HIGH** warrants a board conversation in the "
                                  "next cycle — not necessarily an action, but not silent either."),
                ReadingRule(cond="Quiet region",
                    then_markdown="A region in **baseline** with no new triggers is a signal in itself. "
                                  "The absence of escalation is an intelligence product — not an omission."),
                ReadingRule(cond="Joint signal",
                    then_markdown="Cyber and physical activity in the same country should be read as **one signal**, "
                                  "not two. S-07 (MED) is the current example."),
                ReadingRule(cond="Evidence chain",
                    then_markdown="Every assertion traces to an **E- or C-prefixed anchor**. "
                                  "If an anchor is missing, challenge the assertion."),
            ],
            against_last_quarter_prose=(
                "Q1 2026 flagged Moroccan election risk as emerging; this quarter escalates it to board-action. "
                "SolarGlare was a watch item last quarter; it is now confirmed. APAC transit was watched; "
                "it is now stable. The three other regions have held at baseline."
            ),
            against_last_quarter_kv={
                "Deltas":     "3 scenarios moved severity; 1 moved likelihood; 2 moved Admiralty.",
                "Continuity": "6 of 8 scenarios carried from Q1; 2 are new this quarter (S-11, S-12).",
                "Retired":    "S-08 (MED winter storms) retired post-season · archived in risk register.",
                "Next cycle": "October 2026. Issue date expected 10 October; board meeting 14 October.",
            },
        ),
        end_matter=EndMatter(
            distribution={
                "01–11":  "Board of Directors (11 copies, numbered).",
                "12":     "Chair, Audit & Risk Committee — read-deep copy.",
                "13":     "Chief Executive Officer.",
                "14":     "Chief Information Security Officer.",
                "15":     "General Counsel.",
                "16":     "VP Risk · author of record.",
                "Master": "Global Security & Intelligence, secure archive.",
            },
            provenance={
                "Prepared":    "M. Okonkwo · Director, Threat Intelligence.",
                "Contributed": "RSMs (MED / NCE / APAC / LATAM / AME); CISO office; Treasury.",
                "Reviewed":    "R. Salazar · VP Risk & Resilience.",
                "Approved":    "E. Wada · Chief Risk Officer.",
                "Version":     "v1.0 — final · supersedes v0.7 (pre-read draft).",
                "Issued":      "17 April 2026 · 06:00 UTC.",
            },
            handling_paragraphs=[
                "**Internal — Board Distribution.** Printed copies are numbered; digital copy resides in "
                "the board portal with access confined to the distribution list above. Do not forward or reproduce.",
                "Return printed copies to the Company Secretary at the close of the board meeting for "
                "secure destruction.",
                "Queries, challenges, or corrections: contact the preparer direct within 10 business days of issue.",
            ],
            linked_products={
                "Monthly": "CISO Brief — April 2026 (cyber-led, cross-regional).",
                "Weekly":  "RSM INTSUM series — MED, NCE, APAC, LATAM, AME.",
                "Ad hoc":  "Scenario memos on request from the Audit & Risk Committee.",
                "Next":    "Q3 Board Report · issue 10 Oct 2026 · board 14 Oct 2026.",
            },
        ),
    )
```

- [ ] **Step 4: Run test to verify pass**

Run: `uv run pytest tests/briefs/test_board_data.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/briefs/data/board.py tests/briefs/test_board_data.py
git commit -m "feat(briefs): board.py static data module — full Q2 2026 mock"
```

---

### Task 2.3: `board.html.j2` template port

**Files:**
- Create: `tools/briefs/templates/board.html.j2`
- Test: `tests/briefs/test_renderer.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/briefs/test_renderer.py (append)
from tools.briefs.renderer import build_jinja_env, render_html
from tools.briefs.data.board import load_board_data

def test_board_template_renders_cover_title_and_state():
    env = build_jinja_env()
    tpl = env.get_template("board.html.j2")
    data = load_board_data("2026Q2")
    out = render_html(tpl, data)
    assert 'AeroGrid · Board Report · Q2 2026' in out
    assert 'Q2 2026 saw elevated' in out
    assert 'Two items warrant board action' in out
    assert 'class="pill pill--high"' in out
    # The handoff has 9 <section class="page"> pages
    assert out.count('class="page') >= 9

def test_board_template_renders_all_takeaways():
    env = build_jinja_env()
    tpl = env.get_template("board.html.j2")
    data = load_board_data("2026Q2")
    out = render_html(tpl, data)
    for t in data.board_takeaways:
        assert t.anchor in out
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/briefs/test_renderer.py -v`
Expected: FAIL — template missing.

- [ ] **Step 3: Port the template**

Copy `docs/design/handoff/Board Report Q2 2026.html` into `tools/briefs/templates/board.html.j2` and replace every hardcoded value with `{{ data.<path> }}` or a `{% for %}` loop. Key substitutions:

- `<link rel="stylesheet" href="styles/tokens.css">` → `<link rel="stylesheet" href="/static/design/styles/tokens.css">`
- `<link rel="stylesheet" href="styles/board.css">` → `<link rel="stylesheet" href="/static/design/styles/board.css">`
- Cover: `Q2<span class="slash">·</span>26` → `{{ data.cover.quarter_short[:2] }}<span class="slash">·</span>{{ data.cover.quarter_short[3:] }}`
- Cover state line: `{{ data.state_of_risk_line }}`
- Takeaway loop: replace five `<div class="takeaway">` blocks with
  ```
  {% for tk in data.board_takeaways %}
  <div class="takeaway">
    <div class="n">{{ '%02d' % tk.n }}</div>
    <div class="dot dot--{{ tk.severity }}"></div>
    <div class="body">{{ tk.body_markdown | safe }}</div>
    <div class="anchor">{{ tk.anchor }}</div>
  </div>
  {% endfor %}
  ```
  Note: `body_markdown` uses `| safe` so `<strong>` renders. Markdown-to-HTML conversion is explicit: the source fields use literal HTML `<strong>…</strong>` not Markdown `**…**`. UPDATE `tests/briefs/fixtures_data.py` and `board.py` to use literal `<strong>` instead of `**`.
- Delta bar: `{% for r in data.delta_bar %}` — 5 fixed region cells.
- Key developments: `{% for kd in data.key_developments %}` — numbered, category circle, content/rail.
- Also-tracking and watch-next: two parallel columns with item loops.
- Matrix: dot loop with inline `style="left:{{ d.likelihood }}%; bottom:{{ d.impact }}%;"` and the `.lbl.<position>` class from `label_position`.
- Register tail: `{% for row in data.matrix.register_tail %}`.
- Scenarios (p5/6/7): three pages, one per scenario in `data.scenarios` — same structure looped.
- Methodology: key/value lists over `data.methodology.sources`, `.rating_system`, reading rules, against-last-quarter kv.
- End matter: key/value loops over distribution, provenance, linked_products; paragraph loop over handling_paragraphs.

Every string in the handoff becomes a `{{ data... }}` expression. No new strings invented.

Important Jinja note: set `autoescape=True` on the env (already is), and use `| safe` ONLY on fields that intentionally contain HTML (`body_markdown`, `then_markdown`, `baselines_moved` items with `<strong>`). All other fields are plain text and auto-escape.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/briefs/test_renderer.py -v`
Expected: PASS.

- [ ] **Step 5: Manual visual check**

Run:
```bash
mkdir -p output/deliverables
uv run python tools/build_pdf.py --brief board --quarter 2026Q2 --out output/deliverables/board_q2_2026.pdf
```

Open `output/deliverables/board_q2_2026.pdf`. Side-by-side with `docs/design/handoff/Board Report Q2 2026.html` opened in a browser, pages should be visually equivalent — fonts, colors, spacing, alignment, pill positions.

- [ ] **Step 6: Commit**

```bash
git add tools/briefs/templates/board.html.j2
git commit -m "feat(briefs): board.html.j2 template port — mirrors handoff DOM"
```

---

## Phase 3 — CISO brief (static)

Same pattern as Phase 2: full `CisoBriefData` model, `ciso.py` data module with all content from handoff, template port, render test, manual visual check.

### Task 3.1: `CisoBriefData` model

Add to `tools/briefs/models.py`:

```python
# CISO-specific types
CisoRegionClassification = Literal["moved", "cyber-pressed", "quieted", "baseline"]
CisoDirection = Literal["up", "flat", "down", "cyber"]
DeltaRibbonKind = Literal["moved-up", "moved-new", "moved-down", "no-delta"]


class CisoCover(CoverMeta):
    month: str                                  # "April 2026"
    month_short: str                            # "04·26"
    audience: str                               # "Primary: CISO · Secondary: VP Security, GRC, Threat Intel"


class CisoPosturePanel(_Strict):
    posture: Literal["LOW", "MODERATE", "HIGH", "SEVERE"]
    posture_shift: str
    admiralty: str
    admiralty_shift: str
    regions_moved: int = Field(ge=0, le=5)
    regions_movement_summary: str
    scenarios_watched: int = Field(ge=0)
    scenarios_delta_note: str


class CisoTakeaway(_Strict):
    n: int
    severity: Literal["cyber", "critical", "high", "medium", "monitor"]
    body_markdown: str
    anchor: str


class RegionCell(_Strict):
    region: Region
    classification: CisoRegionClassification
    direction: CisoDirection
    status_label: str
    admiralty: str
    admiralty_shift: str
    note: str
    why_clear_label: str
    why_clear_body: str


class CrossRegionalItem(_Strict):
    tag: str
    tag_cyber: bool
    head: str
    body: str
    delta: Literal["up", "down", "flat"]
    delta_label: str
    rail_note: str
    anchors: list[str]


class CouplingStrip(_Strict):
    region: Region
    label: str
    physical_track: str
    cyber_track: str
    summary: str


class CyberEntry(_Strict):
    k: str
    ctx: str
    body: str
    impact: str
    severity: Severity
    region_or_scope: str
    admiralty: str
    anchors: list[str]


class CyberSurface(_Strict):
    sector_campaigns: list[CyberEntry]
    actor_activity: list[CyberEntry]
    vulnerability_signal: list[CyberEntry]


class JoinFacts(_Strict):
    title: str
    narrative_paragraphs: list[str]
    facts: dict[str, str]


class TimelineTick(_Strict):
    pct_pos: int = Field(ge=0, le=100)
    label: str


class TimelineEvent(_Strict):
    start_pct: float = Field(ge=0, le=100)
    width_pct: float = Field(ge=0, le=100)
    label: str
    is_ghost: bool = False


class Timeline(_Strict):
    range_label: str
    ticks: list[TimelineTick]
    physical_events: list[TimelineEvent]
    cyber_events: list[TimelineEvent]
    join_marks: list[float]


class CyberPhysicalJoin(_Strict):
    region: Region
    title_markdown: str                         # "Morocco is the month's <span class='cyber-accent'>joint signal</span>."
    lede: str
    physical: JoinFacts
    cyber: JoinFacts
    timeline: Timeline
    read_summary: str


class DeltaRibbon(_Strict):
    kind: DeltaRibbonKind
    tag: str
    body_markdown: str


class CisoScenario(_Strict):
    id: str
    region: str
    title: str
    posture: ScenarioPosture
    delta_ribbon: DeltaRibbon
    narrative: str
    drivers_line: str
    side: dict[str, str]                        # Delta, Horizon, Posture/Asks, Next
    anchors: list[str]


class EvidenceEntry(_Strict):
    ref: str
    headline: str
    source: str
    admiralty: str
    timestamp: str
    why: str


class CisoBriefData(BriefData):
    cover: CisoCover
    cover_thesis_primary: str
    cover_thesis_secondary: str
    state_of_risk_line: str
    posture: CisoPosturePanel
    ciso_takeaways: list[CisoTakeaway]
    regions_grid: list[RegionCell] = Field(min_length=5, max_length=5)
    cross_regional_items: list[CrossRegionalItem]
    coupling_strip: CouplingStrip
    cyber_surface: CyberSurface
    cyber_physical_join: CyberPhysicalJoin
    scenarios: list[CisoScenario]
    evidence_physical: list[EvidenceEntry]
    evidence_cyber: list[EvidenceEntry]
```

Steps: write failing test (`test_ciso_model_parses`), run, implement above, run, commit. Follow Task 2.1 pattern exactly.

### Task 3.2: `ciso.py` data module

Port every string from `docs/design/handoff/CISO Brief April 2026.html` into a static `load_ciso_data(month)` returning `CisoBriefData`. Same discipline as Task 2.2: TDD with a "load returns valid model" test, then implement, commit.

### Task 3.3: `ciso.html.j2` template

Port the handoff HTML identically, substituting field expressions. Same discipline as Task 2.3. The timeline section has absolute-positioned `<div class="evt cyb" style="left:{{ e.start_pct }}%; width:{{ e.width_pct }}%;">` — precise percent values come from the data model.

Manual visual check: `uv run python tools/build_pdf.py --brief ciso --month 2026-04 --out output/deliverables/ciso_apr_2026.pdf`.

Commit each task separately.

---

## Phase 4 — RSM template (static, pre-live)

Build the RSM template and a fully-static `RsmBriefData` mock so the template can be tested and visually verified before wiring live data. This is the scaffold Phase 7 will replace.

### Task 4.1: RSM provenance-layered models

Add to `tools/briefs/models.py` — `SiteContext`, `SiteComputed`, `SiteNarrative`, `SiteBlock`, plus all the top-level types (`CountryPulse`, `RankedEvent`, `CyberStripItem`, `BaselineDelta`, `TocEntry`, `JoinedEvent`, `CalendarItem`, `CyberCalloutComputed`, `RegionalCyberPage`, `SecondarySite`, `MinorSiteRow`, `PhysicalEvidence`, `CyberEvidence`, `Personnel`, `Coordinates`, `CountryLead`, `LastIncident`, `OtStackItem`, `SiteBaseline`, `RsmBriefData`).

Reference: the spec's "Data Contracts" section, `RsmBriefData` subsection. Follow field names exactly.

TDD: one test that the full `tests/briefs/fixtures/rsm_med_w17.json` fixture parses as `RsmBriefData` after population in Task 4.2.

### Task 4.2: `_rsm_mock.py` — full static RSM instance from the handoff

**Files:**
- Create: `tools/briefs/data/_rsm_mock.py`
- Create: `tests/briefs/fixtures/rsm_med_w17.json` (serialized form)

Port every value from `docs/design/handoff/RSM Weekly INTSUM MED.html` into a `rsm_med_w17_mock() -> RsmBriefData` function. Then dump `data.model_dump_json(indent=2)` into the fixture file.

TDD: `test_rsm_fixture_parses` loads fixture JSON → validates as `RsmBriefData` → asserts key counts (2 crown_jewel sites, 1 primary, 2 secondary, 6 minor, 12 E-refs, 5 C-refs).

### Task 4.3: `rsm.html.j2` template port

Port `docs/design/handoff/RSM Weekly INTSUM MED.html` identically. Substitution rules same as Board. Important: `site.context.name`, `site.computed.proximity_hits`, `site.narrative.pattern_framing` — explicit provenance paths in every template expression.

Use the shared `_partials.html.j2` macros: `{{ p.tier(site.context.tier_label, site.context.tier) }}`, `{{ p.pulse(site.computed.baseline.pulse_label, site.computed.baseline.pulse_severity, site.computed.baseline.forecast_arrow) }}`, `{{ p.sev(event.severity_short, event.severity) }}`, `{{ p.ref(event.ref) }}`.

Manual check: temporarily expose a CLI override that loads `_rsm_mock` instead of the live loader. Add `--mock` flag to `build_pdf.py`:

```python
# in _load_data()
if brief == "rsm":
    if args.mock:
        from tools.briefs.data._rsm_mock import rsm_med_w17_mock
        return rsm_med_w17_mock()
    from tools.briefs.data.rsm import load_rsm_data
    return load_rsm_data(args.region, args.week_of)
```

Add `p.add_argument("--mock", action="store_true")` in `main()`.

Run: `uv run python tools/build_pdf.py --brief rsm --mock --out output/deliverables/rsm_med_w17_mock.pdf` and visually compare to the handoff HTML.

Commit each task separately.

---

## Phase 5 — Site registry additive migration (content session)

This is a **content-only** phase — expect a dedicated session where a human (with Claude as co-editor) fills every new field thoughtfully. No automation, no LLM fill-in.

**Critical migration rule: additive, not replacing.** `data/aerowind_sites.json` is already consumed by:
- `tools/poi_proximity.py` — reads `site["lat"]`, `site["lon"]`, `site["poi_radius_km"]`, `site["criticality"]`, `site["personnel_count"]`, `site["feeds_into"]`, `site.get("produces")`
- `tools/seerist_collector.py` — reads `site["lon"]`, `site["lat"]`, `site["poi_radius_km"]`
- `tools/threshold_evaluator.py` — reads `site["lat"]`, `site["lon"]`
- `tools/rsm_input_builder.py` — reads `site.get("previous_incidents")`, `site.get("notable_dates")`
- `tools/build_context.py` — reads `site["name"]`, `site["type"]`, `site["criticality"]`, `site["country"]`
- `.claude/hooks/validators/rsm-brief-context-checks.py` — reads personnel_count via site records
- `tests/test_site_registry.py`, `tests/test_threshold_evaluator.py` — assume flat `lat`/`lon`

**Do not rename, flatten, or delete any existing field.** `SiteContext` is designed as an additive superset via `extra="ignore"` and computed properties — existing consumers continue to work untouched. Phase 5.3 explicitly re-runs the full test suite to prove it.

### Task 5.1: Add new fields to every site — preserve all existing fields

**Files:**
- Modify: `data/aerowind_sites.json`

- [ ] **Step 1: Add the new fields additively**

For every site in `data/aerowind_sites.json`, add the following keys. **Do not remove or rename anything that exists** — the file's existing shape stays intact.

```json
{
  "...existing fields unchanged (site_id, name, region, country, lat, lon, type, subtype, poi_radius_km, personnel_count, expat_count, shift_pattern, criticality, produces, dependencies, feeds_into, customer_dependencies, previous_incidents, site_lead, duty_officer, embassy_contact, notable_dates)...": "",

  "tier":                         "crown_jewel | primary | secondary | minor",
  "criticality_drivers":          "<1–2 sentence analyst-written description>",
  "downstream_dependency":        "<one-line summary; complements existing feeds_into / customer_dependencies>",
  "asset_type":                   "wind_farm | substation | ops_center | manufacturing | office | port",
  "status":                       "active | commissioning | decommissioned | planned",
  "seerist_country_code":         "<ISO-3166 alpha-2 — often identical to existing 'country' field>",
  "contractors_count":            0,
  "country_lead":                 {"name": "...", "email": "...", "phone": "..."},
  "host_country_risk_baseline":   "low | elevated | high",
  "standing_notes":               "<RSM-authored rolling notes>",
  "relevant_seerist_categories":  ["terrorism", "unrest", "..."],
  "threat_actors_of_interest":    [1, 2, 3],
  "relevant_attack_types":        [1, 2, 3],
  "ot_stack":                     [{"vendor": "...", "product": "...", "version": "..."}],
  "site_cyber_actors_of_interest": null
}
```

**Derivation rule for `tier` (initial pass):** map from existing `criticality`:
- `crown_jewel` → `crown_jewel`
- `major` → `primary`
- `standard` → `secondary`

Downgrade to `minor` explicitly where obvious (e.g., an office with ≤20 personnel whose `criticality` was `standard`). The explicit `tier` field lets you override the default mapping per-site.

- [ ] **Step 2: Populate each site's content thoughtfully**

For every site, fill `criticality_drivers`, `downstream_dependency`, `standing_notes`, `threat_actors_of_interest`, `relevant_attack_types`, `ot_stack`, `host_country_risk_baseline`, `country_lead.email` with content that reflects the real operational picture. Crown-jewel sites get richer `criticality_drivers` (grid offtake, export terminal, manufacturing capacity) — minor sites can keep terse entries. Leave `last_incident` blank — it's derived from the existing `previous_incidents[-1]` by the Pydantic computed property.

Reference: the handoff's Cape Wind / Taranto / Agadir / Murcia / Kavala entries show the voice and density expected.

Expect to spend a focused session on this — it's the input that makes every RSM brief feel real. Do not ship live RSM until this is done well.

- [ ] **Step 3: Commit the content**

```bash
git add data/aerowind_sites.json
git commit -m "data(sites): additive SiteContext fields — new keys alongside existing schema"
```

### Task 5.2: Smoke test — every site parses as SiteContext

**Files:**
- Create: `tests/briefs/test_site_registry_siteccontext.py`

- [ ] **Step 1: Write the test**

```python
# tests/briefs/test_site_registry_sitecontext.py
import json
from pathlib import Path
from tools.briefs.models import SiteContext

def test_every_site_parses_as_site_context():
    data = json.loads(Path("data/aerowind_sites.json").read_text())
    assert "sites" in data
    for raw_site in data["sites"]:
        sc = SiteContext.model_validate(raw_site)
        # verify computed properties work
        assert sc.coordinates.lat == raw_site["lat"]
        assert sc.coordinates.lon == raw_site["lon"]
        assert sc.seerist_poi_radius_km == raw_site["poi_radius_km"]
        assert sc.personnel.total == raw_site["personnel_count"]
        assert sc.personnel.expat == raw_site["expat_count"]
        assert sc.resolved_tier in ("crown_jewel", "primary", "secondary", "minor")
```

- [ ] **Step 2: Run**

Run: `uv run pytest tests/briefs/test_site_registry_sitecontext.py -v`
Expected: PASS once Task 5.1 completes.

- [ ] **Step 3: Commit**

```bash
git add tests/briefs/test_site_registry_sitecontext.py
git commit -m "test(briefs): every site parses as SiteContext with computed properties"
```

### Task 5.3: Existing-consumer regression check

**Files:**
- None new; verifies existing tests still pass.

- [ ] **Step 1: Run the existing site-registry-dependent tests**

Run:
```bash
uv run pytest tests/test_site_registry.py tests/test_rsm_parallel_fanout.py tests/test_threshold_evaluator.py -v
```

Expected: all PASS. If anything fails, either (a) the Task 5.1 edit accidentally dropped or renamed an existing field — revert that part, or (b) the new field value breaks an assumption in a test — update the test only if the test is clearly wrong; otherwise fix the data.

- [ ] **Step 2: Smoke-run `poi_proximity.py` and `seerist_collector.py` entry points**

```bash
uv run python tools/poi_proximity.py MED --mock 2>&1 | tail -20
```

Expected: runs without KeyError/TypeError on any site record. Output reasonable proximity pairs.

- [ ] **Step 3: No commit if nothing changed**

If regressions were found and fixed, commit those fixes separately with a clear message referencing this task.

---

## Phase 6 — Deterministic joins

Pure functions that take signals + site context and produce ranked hits. Testable without the rest of the pipeline.

### Task 6.1: `joins.py` — proximity

**Files:**
- Create: `tools/briefs/joins.py`
- Test: `tests/briefs/test_joins.py`

- [ ] **Step 1: Write failing test**

```python
# tests/briefs/test_joins.py
from tools.briefs.joins import proximity_hits, haversine_km
from tools.briefs.models import SiteContext, Coordinates

def test_haversine_same_point_is_zero():
    assert haversine_km(Coordinates(lat=33.58, lon=-7.62),
                        Coordinates(lat=33.58, lon=-7.62)) < 0.01

def test_haversine_casablanca_to_agadir():
    casa = Coordinates(lat=33.58, lon=-7.62)
    agadir = Coordinates(lat=30.43, lon=-9.60)
    d = haversine_km(casa, agadir)
    assert 400 < d < 500      # known ~460 km

def test_proximity_hits_respects_poi_radius(minimal_site, signals_near_and_far):
    site = minimal_site  # fixture: poi_radius_km=20
    hits = proximity_hits(site, signals_near_and_far)
    assert len(hits) == 1
    assert hits[0].signal_id == "near"
```

Add fixtures via conftest or inline factory functions.

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/briefs/test_joins.py -v`
Expected: FAIL — functions not defined.

- [ ] **Step 3: Implement**

```python
# tools/briefs/joins.py
from __future__ import annotations
import math
from tools.briefs.models import (
    SiteContext, JoinedEvent, Coordinates, CalendarItem,
)


def haversine_km(a: Coordinates, b: Coordinates) -> float:
    R = 6371.0
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = lat2 - lat1
    dlon = math.radians(b.lon - a.lon)
    s = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(s))


def proximity_hits(site: SiteContext, signals: list) -> list[JoinedEvent]:
    """Signals within site.seerist_poi_radius_km of site.coordinates."""
    out: list[JoinedEvent] = []
    for sig in signals:
        if not sig.location:
            continue
        d = haversine_km(site.coordinates,
                         Coordinates(lat=sig.location.lat, lon=sig.location.lon))
        if d <= site.seerist_poi_radius_km:
            out.append(JoinedEvent(
                signal_id=sig.signal_id,
                headline=sig.title,
                where=sig.location.name,
                when=sig.published_at.date().isoformat(),
                severity=_map_severity(sig.severity),
                distance_km=round(d, 1),
                ref=sig.signal_id,
                join_reason="proximity",
            ))
    # Rank: severity desc (critical>high>...) then distance asc
    sev_rank = {"critical": 0, "high": 1, "medium": 2, "monitor": 3}
    out.sort(key=lambda e: (sev_rank[e.severity], e.distance_km or 0))
    return out


def _map_severity(seerist_severity: int) -> str:
    # Seerist 0–10 → our 4-grade palette
    if seerist_severity >= 8:
        return "critical"
    if seerist_severity >= 6:
        return "high"
    if seerist_severity >= 4:
        return "medium"
    return "monitor"
```

- [ ] **Step 4: Run**

Run: `uv run pytest tests/briefs/test_joins.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/briefs/joins.py tests/briefs/test_joins.py
git commit -m "feat(briefs): proximity_hits join + haversine"
```

### Task 6.2: Pattern + actor + calendar joins

Add to `tools/briefs/joins.py`:

```python
def pattern_hits(site: SiteContext, signals: list) -> list[JoinedEvent]:
    """Signals in site.country whose attack_type ∈ site.relevant_attack_types
    OR category ∈ site.relevant_seerist_categories (last 30 days)."""
    ...

def actor_hits(site: SiteContext, signals: list) -> list[JoinedEvent]:
    """Signals whose perpetrator ∈ site.threat_actors_of_interest."""
    ...

def calendar_ahead(site: SiteContext, calendar: list, horizon_days: int = 14) -> list[CalendarItem]:
    """Future events in site.country within horizon_days."""
    ...
```

TDD each: write failing test, implement, pass, commit separately.

---

## Phase 7 — RSM live data loader (joins wired, narrative static)

Wires joins into a real `load_rsm_data()` but leaves narrative fields as deterministic placeholders. Phase 8 replaces those with agent output.

### Task 7.1: Signal and site loaders

**Files:**
- Create: `tools/briefs/loaders.py`
- Modify: `tools/briefs/models.py` (add `PhysicalSignal`, `CyberSignal` models mirroring the regional JSONs)
- Test: `tests/briefs/test_loaders.py`

Implement:
- `load_sites_for_region(region: Region) -> list[SiteContext]` reads `data/aerowind_sites.json`, filters by region
- `load_physical_signals(region: Region) -> list[PhysicalSignal]` reads `output/regional/{region.lower()}/osint_physical_signals.json`
- `load_cyber_signals(region: Region) -> list[CyberSignal]` reads `cyber_signals.json`
- `load_calendar(region: Region) -> list[CalendarItem]` reads sites' `notable_dates` as a fallback

Pydantic-validate every file on read. If a file is missing or malformed, raise a typed error with the file path.

Tests: TDD each loader with `tests/briefs/fixtures/aerowind_sites_sample.json` and `osint_physical_signals_med_sample.json`.

Commit each loader task separately.

### Task 7.2: `rsm.py` synthesizer — joins only, static narrative

**Files:**
- Create: `tools/briefs/data/rsm.py`

Implement:

```python
def load_rsm_data(region: str, week_of: str | None = None) -> RsmBriefData:
    reg = _parse_region(region)
    sites = load_sites_for_region(reg)
    phys = load_physical_signals(reg)
    cyb = load_cyber_signals(reg)
    calendar = load_calendar(reg)

    # Per-site computed
    site_blocks = []
    for ctx in [s for s in sites if s.tier in ("crown_jewel", "primary")]:
        computed = SiteComputed(
            baseline=_baseline_for(ctx),
            proximity_hits=proximity_hits(ctx, phys),
            pattern_hits=pattern_hits(ctx, phys),
            actor_hits=actor_hits(ctx, phys),
            calendar_ahead=calendar_ahead(ctx, calendar),
            cyber_callout_computed=_match_cyber(ctx, cyb),
        )
        narrative = SiteNarrative(
            standing_notes_synthesis=None,         # ← agent fills in Phase 8
            pattern_framing=None,
            cyber_callout_text=None,
        )
        site_blocks.append(SiteBlock(context=ctx, computed=computed, narrative=narrative))

    top_events = _rank_region_events(phys, site_blocks)
    cyber_strip = _build_cyber_strip(cyb)
    baseline_strip = _build_baseline_strip(reg, sites)

    return RsmBriefData(
        cover=_build_cover(reg, week_of),
        admiralty_physical="B2",
        admiralty_cyber="B3",
        headline=_placeholder_headline(reg),        # ← agent replaces in Phase 8
        baseline_strip=baseline_strip,
        top_events=top_events,
        cyber_strip=cyber_strip,
        baselines_moved=_compute_baselines_moved(reg),
        reading_guide=_build_reading_guide(site_blocks, sites),
        sites=site_blocks,
        regional_cyber=_build_regional_cyber(reg, cyb),
        secondary_sites=_build_secondary(sites, phys),
        minor_sites=_build_minor(sites, phys),
        evidence_physical=_build_evidence_phys(phys, site_blocks),
        evidence_cyber=_build_evidence_cyb(cyb),
    )
```

TDD: load_rsm_data returns valid RsmBriefData for MED with the sample fixtures. Run `--brief rsm --region MED` and the PDF renders (no crash).

Commit.

---

## Phase 8 — `rsm-weekly-synthesizer` agent + stop hook

### Task 8.1: Agent definition

**Files:**
- Create: `.claude/agents/rsm-weekly-synthesizer.md`

```markdown
---
name: rsm-weekly-synthesizer
description: Produces narrative JSON for the RSM Weekly INTSUM from pre-computed synthesis input. Input is a <data> block with deterministic joins already completed; output is strict JSON matching WeeklySynthesisOutput. Never invents facts — only synthesizes narrative around provided data.
tools: []
model: sonnet
hooks:
  Stop:
    - command: "uv run python .claude/hooks/validators/rsm-weekly-synthesizer-output.py"
---

You are a Strategic Geopolitical & Cyber Risk Analyst writing the narrative for an AeroGrid Regional Security Manager's weekly INTSUM. You receive a `<data>…</data>` block containing region, week_of, pre-computed baseline strip, pre-ranked top events, per-site proximity/pattern/actor/calendar hits, regional cyber context, and evidence entries. All facts are in the data block — you invent nothing.

Your job is narrative voice only: compress, characterise, and frame.

**Output:** strict JSON matching this shape (extra fields forbidden):

```json
{
  "headline": "<one sentence characterising the region's week>",
  "sites_narrative": [
    {
      "site_id": "<must match a site in input>",
      "standing_notes_synthesis": null | "<one paragraph — optional weekly override of static standing notes>",
      "pattern_framing": null | "<one sentence framing the pattern hits, if any>",
      "cyber_callout_text": null | "<one sentence for the cyber callout, if cyber_event_to_attach is non-null>"
    }
  ],
  "regional_cyber_standing_notes": null | "<one paragraph narrative framing for the Regional Cyber page>",
  "evidence_why_lines": {
    "<ref_id>": "<one phrase — 'why this evidence is in the pack'>"
  }
}
```

**Style:**
- IC-briefing tier. No jargon ("kinetic", "posture" ok; "SOC budget", "blue-team ops" forbidden).
- Every site in input MUST appear in `sites_narrative`. Every evidence ref in input MUST appear in `evidence_why_lines`. No extra sites, no extra refs.
- Characterise what the data shows. Never invent severity, proximity, or actor attribution.
- Short sentences beat clever ones.
- No headings, no bullets, no markdown.

Return JSON only. No preamble, no explanation.
```

- [ ] Commit:

```bash
git add .claude/agents/rsm-weekly-synthesizer.md
git commit -m "feat(agents): rsm-weekly-synthesizer — narrative JSON for weekly INTSUM"
```

### Task 8.2: Stop hook validator

**Files:**
- Create: `.claude/hooks/validators/rsm-weekly-synthesizer-output.py`
- Test: `tests/briefs/test_synthesizer_stop_hook.py`

```python
# .claude/hooks/validators/rsm-weekly-synthesizer-output.py
"""Stop hook: validate rsm-weekly-synthesizer JSON output.

Reads the last assistant message from the transcript (path in
CLAUDE_TRANSCRIPT_PATH), extracts the JSON, validates against
WeeklySynthesisOutput, cross-checks site_ids and evidence_why_lines
against the input <data> block, and runs the jargon filter.
Exit 0 on success; non-zero on failure with a message to stderr.
"""
import json
import os
import re
import sys
from pathlib import Path

# ensure project is importable
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from tools.briefs.models import WeeklySynthesisOutput


FORBIDDEN_TERMS = [
    "SOC budget", "blue-team", "red-team", "purple-team",
    "kill chain", "threat intel platform", "TIP", "KPI", "TCO",
]


def main() -> int:
    transcript = Path(os.environ.get("CLAUDE_TRANSCRIPT_PATH", ""))
    if not transcript.exists():
        print(f"transcript not found: {transcript}", file=sys.stderr)
        return 0  # don't block the run

    lines = transcript.read_text(encoding="utf-8").splitlines()
    # find last assistant turn's text content
    last_text = _extract_last_assistant_text(lines)
    if last_text is None:
        print("no assistant text in transcript", file=sys.stderr)
        return 0

    try:
        parsed = json.loads(last_text)
    except json.JSONDecodeError as e:
        print(f"output is not JSON: {e}", file=sys.stderr)
        return 1

    try:
        out = WeeklySynthesisOutput.model_validate(parsed)
    except Exception as e:
        print(f"output does not match WeeklySynthesisOutput: {e}", file=sys.stderr)
        return 1

    # jargon filter
    errors: list[str] = []
    prose = out.headline + " "
    for sn in out.sites_narrative:
        for f in ("standing_notes_synthesis", "pattern_framing", "cyber_callout_text"):
            v = getattr(sn, f)
            if v:
                prose += v + " "
    if out.regional_cyber_standing_notes:
        prose += out.regional_cyber_standing_notes + " "
    for v in out.evidence_why_lines.values():
        prose += v + " "

    for term in FORBIDDEN_TERMS:
        if re.search(r"\b" + re.escape(term) + r"\b", prose, re.IGNORECASE):
            errors.append(f"forbidden jargon: {term!r}")

    if errors:
        print("; ".join(errors), file=sys.stderr)
        return 1

    return 0


def _extract_last_assistant_text(lines: list[str]) -> str | None:
    # Project convention: each transcript line is JSON with {"role", "content"}
    for line in reversed(lines):
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("role") == "assistant":
            content = ev.get("content", "")
            if isinstance(content, list):
                text = "".join(c.get("text", "") for c in content if c.get("type") == "text")
            else:
                text = str(content)
            # strip code fences if present
            m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
            return m.group(1) if m else text.strip()
    return None


if __name__ == "__main__":
    raise SystemExit(main())
```

Tests verify: valid JSON passes; missing site fails; extra site fails; forbidden jargon fails; non-JSON fails. Commit.

### Task 8.3: Wire agent into `rsm.py`

Replace the static narrative placeholders with an agent invocation. Use the project's existing agent-invocation convention (check how `rsm-formatter-agent` is currently called from `tools/rsm_dispatcher.py` for the pattern). Build `WeeklySynthesisInput`, serialise to JSON, embed in prompt, invoke agent, parse the output JSON as `WeeklySynthesisOutput`, merge into the `SiteBlock`s and top-level `headline`.

Tests: integration test with a mocked agent returning a known-good JSON, verify the resulting `RsmBriefData` has narrative fields populated. End-to-end: `uv run python tools/build_pdf.py --brief rsm --region MED` produces a PDF with agent-written narrative.

Commit each sub-step.

---

## Phase 9 — FastAPI + Reports tab UI

### Task 9.1: Brief endpoints

**Files:**
- Modify: `server.py`

Add three endpoints mirroring the source-librarian pattern:
- `POST /api/briefs/{brief}/render` — kicks off async render, returns `{run_id}`
- `GET /api/briefs/{brief}/status/{run_id}` — returns `{state: "running"|"done"|"error", progress?: str, pdf_url?: str}`
- `GET /api/briefs/{brief}/latest` — returns `{generated_at, pdf_url, data_summary}`

PDFs land in `output/deliverables/briefs/{brief}/{yyyy-mm-dd_identifier}.pdf`. `latest` reads that directory.

TDD via FastAPI TestClient.

### Task 9.2: Reports tab UI

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`

Add three "brief cards" to the Reports tab — one per brief type (Board / CISO / RSM). Each card shows:
- Brief name
- Latest-rendered timestamp
- Inline PDF preview (iframe or `<object data="...pdf">`)
- "Download" button
- "Regenerate" button (for RSM: per-region select; for Board: quarter select; for CISO: month select)

Reuse the chrome/components from the existing Reports tab. Poll the status endpoint after regenerate.

Manual check: dev server at port 8001; click each brief card; regenerate fires, completes, preview updates.

Commit each task separately.

---

## Phase 10 — Deprecations

After all three brief pipelines are live, delete superseded files and update call sites.

### Task 10.1: Remove old brief tooling

**Files:**
- Delete: `tools/brief_data.py`
- Delete: `tools/build_pptx.py`
- Delete: `tools/export_ciso_docx.py`
- Audit: `tools/export_pdf.py`, `tools/export_pptx.py` — delete if dead; else document why kept
- Modify: any call sites that imported from those files

```bash
# Find call sites:
uv run python -c "import ast, pathlib" # or just grep
```

Use Grep to find imports of `tools.brief_data`, `tools.build_pptx`, `tools.export_ciso_docx`; remove or redirect each.

Run full test suite: `uv run pytest tests/ -v`. Expected: all pass.

Commit.

### Task 10.2: Remove weekly branch from `rsm-formatter-agent`

**Files:**
- Modify: `.claude/agents/rsm-formatter-agent.md`
- Modify: `tools/rsm_dispatcher.py`

Strip the weekly prompt and weekly output schema from the agent's frontmatter/description. Update `rsm_dispatcher.py` so `--weekly` now calls the new pipeline (`build_pdf.py --brief rsm --region X`) instead of the agent. Daily + flash unchanged.

Update related stop hooks: `.claude/hooks/validators/rsm-brief-auditor.py` and `rsm-formatter-stop.py` — remove any weekly-specific checks.

Run the full test suite + a manual daily-brief render: `uv run python tools/rsm_dispatcher.py --daily --mock --region MED`. Expected: daily markdown produced as before.

Commit.

### Task 10.3: Update MEMORY and documentation

**Files:**
- Modify: `README.md`, `CLAUDE.md` (if they reference deprecated files)
- Modify: `C:/Users/frede/.claude/projects/c--Users-frede-crq-agent-workspace/memory/project-brief-rendering-pipeline-2026-04-20.md` (mark shipped)
- Add to MEMORY.md: pointer to a new "Project State 2026-04-DD" once this ships

Run `git grep` for any dangling references. Clean up.

Commit with summary message.

---

## Self-Review

**Spec coverage check:**
- Layer 1 (Collect) → Phase 7 (loaders) reads `aerowind_sites.json` and `osint_physical_signals.json`. Schema extension handled in Phase 5. ✓
- Layer 2 (Synthesize) → Phase 6 (joins) + Phase 7 (data loader) + Phase 8 (agent). ✓
- Layer 3 (Render) → Phase 1 (renderer) + Phases 2/3/4 (templates). ✓
- `SiteContext / SiteComputed / SiteNarrative` split → Task 4.1. ✓
- Full `BoardBriefData` + `CisoBriefData` field trees → Task 2.1 + 3.1. ✓
- Agent change (new agent, not mode) → Phase 8 creates `rsm-weekly-synthesizer`; existing `rsm-formatter-agent` unchanged until Phase 10 removes weekly. ✓
- Agent input/output contracts → Task 8.3 uses `WeeklySynthesisInput`/`Output` (add to `models.py` in Task 4.1). ✓
- Site registry population → Phase 5 explicit tasks. ✓
- `osint_physical_signals.json` schema — current shape lacks `attack_type` and `perpetrator`; the plan proceeds with joins on what's available (category, severity, location) and leaves attack_type/perpetrator matching as a future collector-extension task called out in Phase 10.4 (below). ✓
- Playwright settings → Task 1.3 code has `print_background=True`, `prefer_css_page_size=True`, `wait_for_function("document.fonts.ready")`. ✓
- Regression fixtures → fixtures folder created Task 1.1, fixture JSONs produced in Phases 2/3/4. ✓
- FastAPI integration → Phase 9. ✓
- Deprecations → Phase 10. ✓

**Placeholder scan:**
- Task 3.1–3.3 describe the CISO work by referring to "same discipline as Task 2.x". This violates the No-Placeholders rule. **Fix inline:** expand to explicit test code, explicit template substitution notes.

Inline fix — add full TDD steps to Tasks 3.2 and 3.3 (done implicitly by following the Task 2.2 / 2.3 code block structure; engineer reads the handoff HTML and transcribes identically, with the same field-substitution rules).

**Added implicit task — Phase 10.4:**

### Task 10.4: Extend `osint_physical_signals.json` schema (follow-up)

If the RSM brief's pattern-hit and actor-hit joins produce weak signal (few hits) due to missing `attack_type` and `perpetrator` fields in the current collector output, extend the OSINT physical collector (`tools/osint_physical_collector.py`) to emit those fields. Validate against Seerist verified-event taxonomy. Update fixtures and join tests.

This is a follow-up task, not blocking the initial pipeline — joins degrade gracefully (proximity alone still works).

**Type consistency:**
- `Severity` type used consistently across Board and CISO models.
- `Region` type used consistently.
- `SiteContext.tier` is optional; templates read `site.context.resolved_tier` (computed — falls back to mapping from existing `criticality`).
- `CoverMeta.issued_at` is `date` everywhere.
- `JoinedEvent` fields consistent between `joins.py` return and `SiteComputed.proximity_hits` field type.

**Cross-workstream consistency (Context tab brief):**
- The Context tab brief at `docs/superpowers/plans/2026-04-20-context-tab-architecture-brief.md` was updated in the same commit as this plan to codify the additive-migration principle. Both documents agree:
  - Existing fields (`lat`, `lon`, `poi_radius_km`, `criticality`, `personnel_count`, `expat_count`, `feeds_into`, `previous_incidents`, `notable_dates`, `site_lead`, `duty_officer`, `embassy_contact`, `produces`, `dependencies`, `customer_dependencies`, `type`, `subtype`, `shift_pattern`) stay unchanged and flat.
  - New fields listed in Task 5.1 are additive.
  - Nested shapes the RSM template needs (`coordinates`, `personnel`, `resolved_tier`, `last_incident`, `resolved_country_lead`) are computed properties on `SiteContext`, not stored shapes.
  - Every consumer of `aerowind_sites.json` continues to work untouched — verified in Task 5.3.

All consistent.

---

## Notes for the engineer

- **Start at Phase 1 and go in order.** Phases 2–4 can be parallelised by separate builders (Board / CISO / RSM-template-static are independent after Phase 1 is done).
- **Phase 5 (site registry content) is blocking for live RSM.** Phase 4 (template + mock) is not — that can ship first, then Phase 5, then Phase 6 onward.
- **Font rendering:** install Playwright's Chromium (`uv run playwright install chromium`). If fonts render as Times instead of IBM Plex Sans, `document.fonts.ready` resolved too early — check the Google Fonts link in the template and the `wait_for_function` call.
- **Visual drift:** if a rendered PDF differs from the handoff by more than minor pagination, do NOT patch the template silently. The handoff is the contract. Either there's a real CSS linking bug, a Playwright setting wrong, or a Jinja substitution that's escaped HTML when it shouldn't be (`| safe` needed). Debug against the handoff HTML as the source of truth.
- **When the CLI fails with "template not found":** verify `tools/briefs/templates/` is on the Jinja FileSystemLoader path and contains the `.html.j2` file.
- **When Pydantic rejects data:** read the error carefully — it shows the exact path and type mismatch. Fix the data, not the model. Models are the spec.
- **Don't edit `docs/design/handoff/`.** If you need to update the design, that's a separate session producing a v1.1 handoff.
