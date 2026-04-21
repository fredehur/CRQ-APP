# Risk Register Discovery-First Implementation Plan

**Status:** ✅ COMPLETE — all 3 phases shipped (2026-04-20). 60/60 tests passing. Step-level checkboxes below are left unchecked from original plan; completion verified by file presence + test run.

**Goal:** Redesign the Risk Register tab to foreground source discovery with stage-aware refresh progress, per-scenario rerun, a discovery-first layout, and a self-healing auto-tune loop.

**Architecture:** Three independent workstreams. Phase 1 (backend foundation) builds the `on_progress` callback, per-scenario rerun, and `snapshot_merge.py`. Phase 2 (layout) rewrites `static/app.js` to render the discovery-first stack and new register header. Phase 3 (auto-tune) builds the Haiku tuner/validator agent loop, `tuner.py`, `tuning_log.py`, and the live feed UI. Builders A+B run in parallel; Builder C starts after Builder A's `server.py` changes land.

**Tech Stack:** Python / Pydantic / FastAPI / threading / uv pytest | Vanilla JS in `static/app.js` and `static/index.html` | Claude Haiku sub-agents via `.claude/agents/`

**Spec:** `docs/superpowers/specs/2026-04-14-risk-register-discovery-first-design.md`

---

## File Map

### Phase 1 — Backend Foundation (Builder A)

| File | Action | Responsibility |
|---|---|---|
| `tools/source_librarian/__init__.py` | Modify | Add `on_progress` + `scenario_id` params to `run_snapshot`; skip `write_snapshot` when `scenario_id` set |
| `tools/source_librarian/intents.py` | Modify | Add `intent_hash_current(register_id) -> str` helper |
| `tools/source_librarian/snapshot_merge.py` | **Create** | Load latest snapshot, replace one scenario's result, write new file |
| `server.py` | Modify | Add `threading.Lock` to `_research_runs`; `_cancel_events` dict; per-scenario `?scenario=` param on `/run`; `POST /api/research/cancel`; `/latest` returns `current_intent_hash` |
| `tests/source_librarian/test_progress_callbacks.py` | **Create** | on_progress wiring, scenario_id isolation, skip-write-snapshot |
| `tests/source_librarian/test_per_scenario_rerun.py` | **Create** | merge_scenario_result logic |

### Phase 2 — Layout Rewrite (Builder B, parallel with A)

| File | Action | Responsibility |
|---|---|---|
| `static/index.html` | Modify | Register header: add `rr-header-rollup`, `rr-header-stale-badge`, `rr-refresh-all-btn` elements |
| `static/app.js` | Modify | `_renderScenarioList` (sources column); new `_renderEvidenceSection`; rewrite `_renderScenarioDetail` (discovery-first stack); `_updateRegisterHeader`; `refreshAllSources`; `rerunScenario` |

### Phase 3 — Auto-tune (Builder C, after Builder A)

| File | Action | Responsibility |
|---|---|---|
| `tools/source_librarian/tuning_log.py` | **Create** | JSONL append writer + reader |
| `tools/source_librarian/tuner.py` | **Create** | `run_autotune` loop, `AutoTuneResult` dataclass, `_apply_diff` |
| `.claude/agents/intent-tuner-agent.md` | **Create** | Haiku tuner sub-agent |
| `.claude/agents/intent-tuner-validator-agent.md` | **Create** | Haiku validator sub-agent |
| `.claude/hooks/validators/intent-tuner-output.py` | **Create** | Stop hook (dual-mode via `INTENT_TUNER_ROLE` env var) |
| `server.py` | Modify (additive) | `POST /api/research/autotune` endpoint |
| `tests/source_librarian/test_tuning_log.py` | **Create** | Append-only, schema, read-back roundtrip |
| `tests/source_librarian/test_tuner.py` | **Create** | Loop termination, budget, in-memory isolation |
| `static/app.js` | Modify (additive) | `startAutoTune`, `cancelAutoTune`, live feed rendering |

---

## Phase 1 — Backend Foundation

### Task 1: `snapshot_merge.py`

**Files:**
- Create: `tools/source_librarian/snapshot_merge.py`
- Create: `tests/source_librarian/test_per_scenario_rerun.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/source_librarian/test_per_scenario_rerun.py
import pytest
from datetime import datetime, timezone
from pathlib import Path
from tools.source_librarian.snapshot import (
    ScenarioResult, Snapshot, SourceEntry, write_snapshot
)


def _make_snap(register_id: str, output_dir: Path) -> tuple[Snapshot, Path]:
    snap = Snapshot(
        register_id=register_id,
        run_id="run-orig",
        intent_hash="aabbccdd",
        started_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 20, 10, 1, tzinfo=timezone.utc),
        tavily_status="ok",
        firecrawl_status="ok",
        scenarios=[
            ScenarioResult(scenario_id="WP-001", scenario_name="Intrusion",
                           status="ok", sources=[]),
            ScenarioResult(scenario_id="WP-002", scenario_name="Ransomware",
                           status="no_authoritative_coverage", sources=[]),
        ],
    )
    path = write_snapshot(snap, output_dir=output_dir)
    return snap, path


def test_merge_replaces_target_scenario(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path)
    orig, _ = _make_snap("wind_test", tmp_path)

    new_result = ScenarioResult(
        scenario_id="WP-002",
        scenario_name="Ransomware",
        status="ok",
        sources=[
            SourceEntry(
                url="https://dragos.com/report",
                title="OT Year in Review",
                publisher="dragos.com",
                publisher_tier="T1",
                published_date="2026-01-10",
                discovered_by=["tavily"],
                score=0.92,
                summary="Vestas incident covered",
                figures=["$4.1M"],
                scrape_status="ok",
            )
        ],
    )

    from tools.source_librarian.snapshot_merge import merge_scenario_result
    merged = merge_scenario_result("wind_test", new_result, output_dir=tmp_path)

    wp2 = next(s for s in merged.scenarios if s.scenario_id == "WP-002")
    assert wp2.status == "ok"
    assert len(wp2.sources) == 1

    wp1 = next(s for s in merged.scenarios if s.scenario_id == "WP-001")
    assert wp1.status == "ok"

    # intent_hash preserved from original
    assert merged.intent_hash == orig.intent_hash
    assert len(merged.scenarios) == 2


def test_merge_writes_new_file_preserves_old(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path)
    orig, orig_path = _make_snap("wind_test", tmp_path)

    new_result = ScenarioResult(scenario_id="WP-001", scenario_name="Intrusion",
                                status="ok", sources=[])

    from tools.source_librarian.snapshot_merge import merge_scenario_result
    merge_scenario_result("wind_test", new_result, output_dir=tmp_path)

    snapshots = sorted(tmp_path.glob("wind_test_*.json"))
    assert len(snapshots) == 2   # original preserved + new written
    assert orig_path in snapshots


def test_merge_raises_when_no_base_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path)
    new_result = ScenarioResult(scenario_id="WP-001", scenario_name="X",
                                status="ok", sources=[])

    from tools.source_librarian.snapshot_merge import merge_scenario_result
    with pytest.raises(FileNotFoundError, match="No base snapshot"):
        merge_scenario_result("no_register", new_result, output_dir=tmp_path)


def test_merge_raises_when_scenario_not_in_base(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path)
    _make_snap("wind_test", tmp_path)
    new_result = ScenarioResult(scenario_id="WP-999", scenario_name="X",
                                status="ok", sources=[])

    from tools.source_librarian.snapshot_merge import merge_scenario_result
    with pytest.raises(KeyError, match="WP-999"):
        merge_scenario_result("wind_test", new_result, output_dir=tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/source_librarian/test_per_scenario_rerun.py -v
```
Expected: `ModuleNotFoundError: No module named 'tools.source_librarian.snapshot_merge'`

- [ ] **Step 3: Implement `tools/source_librarian/snapshot_merge.py`**

```python
"""Merge a per-scenario rerun result into the latest register snapshot."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .snapshot import (
    OUTPUT_DIR, ScenarioResult, Snapshot,
    list_snapshot_paths, read_snapshot, write_snapshot,
)


def merge_scenario_result(
    register_id: str,
    new_result: ScenarioResult,
    *,
    output_dir: Optional[Path] = None,
) -> Snapshot:
    """Load the latest snapshot, replace one scenario's result, write a new file.

    Raises FileNotFoundError if no base snapshot exists.
    Raises KeyError if scenario_id not in base snapshot.
    intent_hash is preserved from the base — the yaml did not change.
    """
    target = output_dir or OUTPUT_DIR
    paths = list_snapshot_paths(register_id, output_dir=target)
    if not paths:
        raise FileNotFoundError(
            f"No base snapshot found for register '{register_id}'"
        )

    base = read_snapshot(paths[0])
    scenario_ids = [s.scenario_id for s in base.scenarios]
    if new_result.scenario_id not in scenario_ids:
        raise KeyError(
            f"Scenario '{new_result.scenario_id}' not found in base snapshot "
            f"(known: {scenario_ids})"
        )

    merged_scenarios = [
        new_result if s.scenario_id == new_result.scenario_id else s
        for s in base.scenarios
    ]

    merged = Snapshot(
        register_id=base.register_id,
        run_id=base.run_id,
        intent_hash=base.intent_hash,   # preserved — yaml unchanged
        started_at=base.started_at,
        completed_at=datetime.now(timezone.utc),
        tavily_status=base.tavily_status,
        firecrawl_status=base.firecrawl_status,
        scenarios=merged_scenarios,
        debug=base.debug,
    )
    write_snapshot(merged, output_dir=target)
    return merged
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/source_librarian/test_per_scenario_rerun.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add tools/source_librarian/snapshot_merge.py tests/source_librarian/test_per_scenario_rerun.py
git commit -m "feat(source-librarian): per-scenario snapshot merge module with tests"
```

---

### Task 2: `intent_hash_current` helper

**Files:**
- Modify: `tools/source_librarian/intents.py`
- Modify: `tests/source_librarian/test_intents.py` (append one test)

- [ ] **Step 1: Write the failing test** (append to existing `test_intents.py`)

```python
def test_intent_hash_current_matches_file(tmp_path, monkeypatch):
    import shutil
    from pathlib import Path
    FIX = Path(__file__).parent / "fixtures"
    d = tmp_path / "research_intents"
    d.mkdir()
    shutil.copy(FIX / "intent_wind_minimal.yaml", d / "wind_test.yaml")
    monkeypatch.setattr("tools.source_librarian.intents.INTENTS_DIR", d)

    from tools.source_librarian.intents import intent_hash_current
    from tools.source_librarian.snapshot import intent_hash

    h = intent_hash_current("wind_test")
    expected = intent_hash((d / "wind_test.yaml").read_text(encoding="utf-8"))
    assert h == expected
    assert len(h) == 8
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/source_librarian/test_intents.py::test_intent_hash_current_matches_file -v
```
Expected: `ImportError: cannot import name 'intent_hash_current'`

- [ ] **Step 3: Append to `tools/source_librarian/intents.py`**

After the `load_publishers` function at the bottom of the file, add:

```python
def intent_hash_current(register_id: str) -> str:
    """Return the 8-char sha256 hash of the intent yaml currently on disk."""
    from . import intents as _mod
    from .snapshot import intent_hash
    path = _mod.INTENTS_DIR / f"{register_id}.yaml"
    return intent_hash(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run all intent tests**

```
uv run pytest tests/source_librarian/test_intents.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tools/source_librarian/intents.py tests/source_librarian/test_intents.py
git commit -m "feat(source-librarian): intent_hash_current helper"
```

---

### Task 3: `on_progress` + `scenario_id` in `run_snapshot`

**Files:**
- Modify: `tools/source_librarian/__init__.py`
- Create: `tests/source_librarian/test_progress_callbacks.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/source_librarian/test_progress_callbacks.py
"""Tests for run_snapshot on_progress callback and scenario_id isolation."""
import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

FIX = Path(__file__).parent / "fixtures"


def _clients():
    tavily = MagicMock()
    tavily.search.return_value = json.loads((FIX / "tavily_search_response.json").read_text())
    firecrawl = MagicMock()
    firecrawl.search.return_value = json.loads((FIX / "firecrawl_search_response.json").read_text())
    doc = MagicMock()
    doc.markdown = (FIX / "firecrawl_scrape_dragos.md").read_text()
    doc.metadata = MagicMock()
    doc.metadata.title = "OT Year in Review 2024"
    firecrawl.scrape.return_value = doc
    haiku = MagicMock()
    haiku.messages.create.return_value = MagicMock(content=[MagicMock(text="Cost $4.1M")])
    return tavily, firecrawl, haiku


def _stage_intent_dir(tmp_path):
    d = tmp_path / "research_intents"
    d.mkdir()
    (d / "wind_test.yaml").write_text((FIX / "intent_wind_minimal.yaml").read_text())
    (d / "publishers.yaml").write_text((FIX / "publishers_minimal.yaml").read_text())
    return d


def test_on_progress_called_per_scenario(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.intents.INTENTS_DIR", _stage_intent_dir(tmp_path))
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path / "out")
    tavily, firecrawl, haiku = _clients()

    events = []
    from tools.source_librarian import run_snapshot
    run_snapshot(
        "wind_test",
        on_progress=lambda d: events.append(d),
        tavily_client=tavily,
        firecrawl_client=firecrawl,
        haiku_client=haiku,
        today=date(2026, 4, 20),
    )

    stages = {e["stage"] for e in events}
    assert "discovery" in stages

    disc_events = [e for e in events if e["stage"] == "discovery"]
    assert len(disc_events) == 2   # one per scenario (wind_test has WP-001 and WP-002)
    for e in disc_events:
        assert e["status"] == "done"
        assert e["counts"]["discovery"]["total"] == 2


def test_scenario_id_returns_single_scenario(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.intents.INTENTS_DIR", _stage_intent_dir(tmp_path))
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path / "out")
    tavily, firecrawl, haiku = _clients()

    from tools.source_librarian import run_snapshot
    snap = run_snapshot(
        "wind_test",
        scenario_id="WP-001",
        tavily_client=tavily,
        firecrawl_client=firecrawl,
        haiku_client=haiku,
        today=date(2026, 4, 20),
    )

    assert len(snap.scenarios) == 1
    assert snap.scenarios[0].scenario_id == "WP-001"


def test_scenario_id_skips_write_to_disk(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.intents.INTENTS_DIR", _stage_intent_dir(tmp_path))
    out_dir = tmp_path / "out"
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", out_dir)
    tavily, firecrawl, haiku = _clients()

    from tools.source_librarian import run_snapshot
    run_snapshot(
        "wind_test",
        scenario_id="WP-001",
        tavily_client=tavily,
        firecrawl_client=firecrawl,
        haiku_client=haiku,
        today=date(2026, 4, 20),
    )

    assert not out_dir.exists() or not list(out_dir.glob("*.json"))


def test_unknown_scenario_id_raises(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr("tools.source_librarian.intents.INTENTS_DIR", _stage_intent_dir(tmp_path))
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path / "out")
    tavily, firecrawl, haiku = _clients()

    from tools.source_librarian import run_snapshot
    with pytest.raises(KeyError, match="WP-999"):
        run_snapshot(
            "wind_test",
            scenario_id="WP-999",
            tavily_client=tavily,
            firecrawl_client=firecrawl,
            haiku_client=haiku,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/source_librarian/test_progress_callbacks.py -v
```
Expected: `TypeError: run_snapshot() got an unexpected keyword argument 'on_progress'`

- [ ] **Step 3: Rewrite `run_snapshot` in `tools/source_librarian/__init__.py`**

Replace the function signature (line 83) and body. New signature:

```python
from typing import Any, Callable, Optional

def run_snapshot(
    register_id: str,
    *,
    on_progress: Optional[Callable[[dict], None]] = None,
    scenario_id: Optional[str] = None,
    debug: bool = False,
    tavily_client: Optional[Any] = None,
    firecrawl_client: Optional[Any] = None,
    haiku_client: Optional[Any] = None,
    today: Optional[date] = None,
) -> Snapshot:
```

Key changes to the body:

After `query_plan = build_queries(intent, today=today)`, add:

```python
    # Filter to one scenario when scenario_id is set
    if scenario_id is not None:
        if scenario_id not in query_plan:
            raise KeyError(f"scenario_id '{scenario_id}' not in intent for '{register_id}'")
        query_plan = {scenario_id: query_plan[scenario_id]}

    scenario_ids = list(query_plan.keys())
    total = len(scenario_ids)

    def _emit(stage: str, sid: str, done_count: int) -> None:
        if on_progress is None:
            return
        on_progress({
            "stage": stage,
            "scenario_id": sid,
            "status": "done",
            "counts": {stage: {"done": done_count, "total": total}},
        })
```

In the discovery loop, change `for sid, queries in query_plan.items():` to track count and emit:

```python
    discovered: dict[str, list[dict]] = {}
    for i, (sid, queries) in enumerate(query_plan.items(), 1):
        discovered[sid] = discover_for_scenario(
            news_queries=queries["news_set"],
            doc_queries=queries["doc_set"],
            tavily_client=tavily_client,
            firecrawl_client=firecrawl_client,
            status=status,
        )
        _emit("discovery", sid, i)
```

In the summarize loop, after each scenario's sources are processed, emit:

```python
            scenarios_out.append(ScenarioResult(...))
            _emit("summarizing", sid, i)
```
(add `for i, (sid, sel) in enumerate(selections.items(), 1):`)

At the end, replace `write_snapshot(snap)` with:

```python
    # Skip disk write for per-scenario reruns — caller owns merge + write
    if scenario_id is None:
        write_snapshot(snap)

    return snap
```

- [ ] **Step 4: Run all affected tests**

```
uv run pytest tests/source_librarian/test_progress_callbacks.py tests/source_librarian/test_run_snapshot.py -v
```
Expected: all pass (existing tests unchanged)

- [ ] **Step 5: Commit**

```bash
git add tools/source_librarian/__init__.py tests/source_librarian/test_progress_callbacks.py
git commit -m "feat(source-librarian): on_progress callback and scenario_id isolation in run_snapshot"
```

---

### Task 4: Server — progress wiring, cancel, per-scenario, stale hash

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Replace the Source Librarian API block**

Find the block starting at `# ── API: Source Librarian` (line ~1354) through `research_latest`. Replace with:

```python
# ── API: Source Librarian ─────────────────────────────────────────────────
import threading
import uuid as _uuid
from fastapi import BackgroundTasks

_research_runs: dict[str, dict] = {}
_cancel_events: dict[str, threading.Event] = {}


def _make_progress_writer(run_id: str):
    def _write(progress_update: dict) -> None:
        state = _research_runs.get(run_id)
        if state is None:
            return
        lock = state.get("lock")
        if lock:
            with lock:
                state["progress"] = progress_update
        else:
            state["progress"] = progress_update
    return _write


def _execute_research(run_id: str, register: str, scenario_id: str | None = None) -> None:
    """Run snapshot synchronously inside a BackgroundTask thread."""
    try:
        from tools.source_librarian import run_snapshot
        snap = run_snapshot(
            register,
            on_progress=_make_progress_writer(run_id),
            scenario_id=scenario_id,
        )
        if scenario_id is not None:
            from tools.source_librarian.snapshot_merge import merge_scenario_result
            snap = merge_scenario_result(register, snap.scenarios[0])
        state = _research_runs[run_id]
        lock = state.get("lock")
        update = {"status": "complete", "snapshot": snap.model_dump(mode="json")}
        if lock:
            with lock:
                state.update(update)
        else:
            state.update(update)
    except Exception as exc:
        log.exception("[source_librarian] run failed")
        state = _research_runs.get(run_id, {})
        lock = state.get("lock")
        update = {"status": "failed", "error": str(exc)}
        if lock:
            with lock:
                state.update(update)
        else:
            state.update(update)
    finally:
        _cancel_events.pop(run_id, None)


@app.post("/api/research/run")
async def start_research(register: str, background: BackgroundTasks,
                         scenario: str | None = None):
    """Kick off a source_librarian snapshot (full register or one scenario)."""
    run_id = str(_uuid.uuid4())
    lock = threading.Lock()
    _research_runs[run_id] = {
        "status": "running",
        "register": register,
        "scenario_id": scenario,
        "progress": {},
        "lock": lock,
    }
    cancel_event = threading.Event()
    _cancel_events[run_id] = cancel_event
    background.add_task(_execute_research, run_id, register, scenario)
    return {"run_id": run_id, "status": "running"}


@app.post("/api/research/cancel")
async def cancel_research(run_id: str):
    """Signal a running research run to stop cooperatively."""
    event = _cancel_events.get(run_id)
    if event:
        event.set()
        return {"cancelled": True}
    return {"cancelled": False, "reason": "run_id not found or already complete"}


@app.get("/api/research/{register}/status/{run_id}")
async def research_status(register: str, run_id: str):
    state = _research_runs.get(run_id)
    if state is None:
        return {"status": "unknown", "run_id": run_id}
    if state.get("register") != register:
        return JSONResponse({"error": "run_id does not match register"}, status_code=404)
    lock = state.get("lock")
    if lock:
        with lock:
            return {k: v for k, v in state.items() if k != "lock"}
    return {k: v for k, v in state.items() if k != "lock"}


@app.get("/api/research/{register}/latest")
async def research_latest(register: str):
    from tools.source_librarian import get_latest_snapshot
    from tools.source_librarian.intents import intent_hash_current
    snap = get_latest_snapshot(register)
    result: dict = {"snapshot": None, "current_intent_hash": None}
    try:
        result["current_intent_hash"] = intent_hash_current(register)
    except FileNotFoundError:
        pass
    if snap is not None:
        result["snapshot"] = snap.model_dump(mode="json")
    return result
```

- [ ] **Step 2: Verify server imports cleanly**

```
uv run python -c "import server; print('server ok')"
```
Expected: `server ok`

- [ ] **Step 3: Run full source_librarian test suite**

```
uv run pytest tests/source_librarian/ -v
```
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add server.py
git commit -m "feat(server): progress wiring, per-scenario run, cancel endpoint, stale hash in /latest"
```

---

## Phase 2 — Layout Rewrite

### Task 5: Register header — rollup, stale badge, REFRESH ALL

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`

- [ ] **Step 1: Update the header strip in `index.html`**

Find the `<!-- Tab header strip -->` div inside `tab-validate` (line ~1276). The existing header contains `rr-header-name`, `rr-header-count`, `rr-header-ts`, and the Run button. Add three new elements after `rr-header-count`:

- `rr-header-rollup` — span for "N ok · N no-coverage" text
- `rr-header-stale-badge` — span (initially `display:none`) with text "INTENT CHANGED — RERUN", amber styling
- `rr-refresh-all-btn` — button calling `refreshAllSources()`, blue primary styling

Keep the existing `rr-header-ts` and Run button. Place REFRESH ALL after the Run button on the right.

- [ ] **Step 2: Add `_updateRegisterHeader` to `app.js`**

New async function. Fetches `/api/research/{registerId}/latest`, then:
1. Counts scenarios by status (ok/no_authoritative_coverage/engines_down) and writes HTML to `rr-header-rollup`
2. Compares `data.snapshot.intent_hash` vs `data.current_intent_hash` — shows/hides `rr-header-stale-badge`
3. Stores `data.snapshot` in `window._readingListCache[registerId]`

Call `_updateRegisterHeader(r.register_id)` at the end of `renderRiskRegisterTab`.

- [ ] **Step 3: Add `refreshAllSources` to `app.js`**

Replaces the old `refreshReadingList`. Differences:
- Posts to `/api/research/run?register=X` (no scenario param)
- Polls at **2s** (down from 5s)
- Uses button id `rr-refresh-all-btn`
- On progress: reads `state.progress.stage` and `state.progress.counts` to show "DISCOVERY 3/9…" in button text
- On complete: calls `_renderEvidenceSection(state.snapshot, selectedScenarioId, registerId)` and `_updateRegisterHeader`
- **No `alert()` calls** — console.error on failure, button resets

- [ ] **Step 4: Delete old `refreshReadingList` function**

Search for `async function refreshReadingList` and remove the entire function. Also remove the old `loadReadingListForScenario` function. The new `_renderEvidenceSection` and `refreshAllSources` replace both.

- [ ] **Step 5: Start dev server and verify header**

```
uv run python server.py
```
Open `http://localhost:8001`. Navigate to Risk Register tab. Confirm:
- "REFRESH ALL SOURCES" button visible
- Stale badge hidden
- No JS console errors

- [ ] **Step 6: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat(ui): register header bar — rollup, stale badge, refresh-all button"
```

---

### Task 6: Scenario list — SOURCES column

**Files:**
- Modify: `static/app.js` (`_renderScenarioList`)

- [ ] **Step 1: Rewrite `_renderScenarioList`**

Current grid: `28px 1fr 72px 50px` (4 columns: #, Scenario, Impact, Prob)
New grid: `22px 1fr 92px 60px 40px` (5 columns: #, Scenario, Sources, Impact, Prob)

Column header: add "Sources" between Scenario and Impact.

Row rendering: add a new cell between scenario name and impact. Logic:
- If no snapshot in `window._readingListCache[registerId]`: render a dim `—`
- If scenario `status === 'no_authoritative_coverage'`: amber `NO COV` pill
- If scenario `status === 'engines_down'`: red `DOWN` text
- Otherwise: up to 3 tier badges (T1 green, T2 blue, T3 amber) from `sc.sources.slice(0, 3)`

Snapshot is read from `(window._readingListCache || {})[registerId] || null`.

- [ ] **Step 2: Verify in browser**

Reload, navigate to Risk Register. After snapshot loads via `_updateRegisterHeader`, confirm 5 columns visible with tier badges.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): scenario list sources column with tier badges and no-coverage pill"
```

---

### Task 7: Scenario detail — discovery-first stack + `_renderEvidenceSection`

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add `_renderEvidenceSection(snap, scenarioId, registerId)`**

New function with 4 render branches (check in this order):

**Branch 1 — no snapshot:** Render empty-state onboarding card (dashed border). Content per spec §2.4:
- Title: "No evidence gathered yet"
- Body: names Dragos, CISA, ENISA, IBM X-Force
- Pipeline steps: "1. Tavily + Firecrawl search all N scenarios. 2. Ranker picks top 3 T1/T2 per scenario. 3. Haiku summarizes and extracts figures."
- Shows intent yaml path: `data/research_intents/{registerId}.yaml`
- No cost disclosure

**Branch 2 — engines_down:** Red degraded panel per spec §2.5. Shows per-engine status rows (TAVILY / FIRECRAWL), RETRY NOW button that calls `refreshAllSources()`.

**Branch 3 — no_authoritative_coverage:** Amber degraded panel per spec §2.5. Shows rejected candidates list, three buttons: AUTO-TUNE (calls `startAutoTune`), RERUN THIS SCENARIO (calls `rerunScenario`), COPY INTENT PATH (copies to clipboard).

**Branch 4 — ok:** Source rows. Format per spec §2.1 and existing `_renderReadingList` pattern:
- `{n}. {publisher}` as blue link + `— {title}` + right-aligned `T{n} · {score}` badge
- Italic summary line
- Figure chips (blue pill style)
- Dim metadata: `{published_date} · {discovered_by}`

- [ ] **Step 2: Rewrite `_renderScenarioDetail` final assembly**

Current stack order (bottom of function):
```
header | descZone | numbersZone | recommendationZone | baselineHtml | validationZone | readingListZone
```

New stack order:
```
header | evidenceZone | descZone | numbersZone | recommendationZone | baselineHtml | validationZone
```

The `evidenceZone` HTML wraps:
- A header row with "Evidence & Sources" in 13px font (not 9px caps), tier legend on right, meta text, a hidden rerun link (`rr-evidence-rerun-{id}`)
- A body div with id `rr-evidence-body-{scenarioId}`

After setting `el.innerHTML`, call:
```javascript
_renderEvidenceSection(
  (window._readingListCache || {})[registerId] || null,
  scenario.scenario_id,
  registerId
);
```
If no snapshot cached, also fetch `/api/research/{registerId}/latest` async and call `_renderEvidenceSection` again with result.

- [ ] **Step 3: Add `rerunScenario(registerId, scenarioId)`**

Posts to `/api/research/run?register=X&scenario=Y`. Polls at 2s. On complete: updates `_readingListCache`, calls `_renderEvidenceSection`, `_renderScenarioList`, `_updateRegisterHeader`.

- [ ] **Step 4: Verify layout in browser**

Start dev server. Navigate to Risk Register. Confirm:
- Evidence & Sources appears at top of right panel (before description)
- Empty state card shows when no snapshot loaded
- No `alert()` in error paths

- [ ] **Step 5: Measure layout on 1440×900 viewport**

Open DevTools, set viewport to 1440×900. Confirm Evidence & Sources header is visible without scrolling (success criterion SC1).

- [ ] **Step 6: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): discovery-first layout — evidence section promoted to position 1 with degraded states"
```

---

## Phase 3 — Auto-tune Loop

### Task 8: `tuning_log.py`

**Files:**
- Create: `tools/source_librarian/tuning_log.py`
- Create: `tests/source_librarian/test_tuning_log.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/source_librarian/test_tuning_log.py
import json
from pathlib import Path


def test_append_and_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.tuning_log.TUNING_LOG_DIR", tmp_path)
    from tools.source_librarian.tuning_log import append_event, read_log

    e1 = {"ts": "2026-04-20T10:00:00Z", "register_id": "wp", "scenario_id": "WP-001",
           "run_id": "r1", "iteration": 1, "event": "proposed",
           "diff": {"add_threat_terms": ["OT ransomware"]}, "reasoning": "too narrow",
           "validator_verdict": "approved", "cost_usd": 0.01}
    e2 = {**e1, "event": "rerun_result", "candidates_discovered": 3,
          "t1_t2_count": 0, "best_rejection": {"url": "x", "reason": "tier"}, "cost_usd": 0.02}

    append_event("wp", e1)
    append_event("wp", e2)

    log = read_log("wp")
    assert len(log) == 2
    assert log[0]["event"] == "proposed"
    assert log[1]["event"] == "rerun_result"


def test_append_is_truly_append_only(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.tuning_log.TUNING_LOG_DIR", tmp_path)
    from tools.source_librarian.tuning_log import append_event, read_log

    for i in range(5):
        append_event("wp", {"iteration": i, "event": "proposed"})

    log = read_log("wp")
    assert len(log) == 5
    for i, entry in enumerate(log):
        assert entry["iteration"] == i


def test_read_log_returns_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.tuning_log.TUNING_LOG_DIR", tmp_path)
    from tools.source_librarian.tuning_log import read_log
    assert read_log("no_register") == []


def test_creates_directory_on_first_write(tmp_path, monkeypatch):
    log_dir = tmp_path / "nested" / "tuning"
    monkeypatch.setattr("tools.source_librarian.tuning_log.TUNING_LOG_DIR", log_dir)
    from tools.source_librarian.tuning_log import append_event
    append_event("wp", {"event": "test"})
    assert (log_dir / "wp.jsonl").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/source_librarian/test_tuning_log.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools/source_librarian/tuning_log.py`**

```python
"""Append-only JSONL log of auto-tune iterations per register."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
TUNING_LOG_DIR = REPO_ROOT / "data" / "research_intents" / "tuning_log"


def append_event(register_id: str, event: dict[str, Any]) -> None:
    """Append one JSONL line to the tuning log for this register."""
    log_dir = TUNING_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{register_id}.jsonl"
    with open(path, mode="a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_log(register_id: str) -> list[dict[str, Any]]:
    """Return all log entries for a register, oldest first."""
    path = TUNING_LOG_DIR / f"{register_id}.jsonl"
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries
```

- [ ] **Step 4: Run tests**

```
uv run pytest tests/source_librarian/test_tuning_log.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add tools/source_librarian/tuning_log.py tests/source_librarian/test_tuning_log.py
git commit -m "feat(source-librarian): JSONL tuning log module"
```

---

### Task 9: `tuner.py` — auto-tune loop

**Files:**
- Create: `tools/source_librarian/tuner.py`
- Create: `tests/source_librarian/test_tuner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/source_librarian/test_tuner.py
"""Tests for run_autotune — termination, budget enforcement, in-memory isolation."""
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import shutil, pytest

FIX = Path(__file__).parent / "fixtures"


def _base_no_cov_snap(scenario_id="WP-001"):
    from tools.source_librarian.snapshot import ScenarioResult, Snapshot
    return Snapshot(
        register_id="wind_test", run_id="r0", intent_hash="aabb1122",
        started_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 20, 10, 1, tzinfo=timezone.utc),
        tavily_status="ok", firecrawl_status="ok",
        scenarios=[ScenarioResult(
            scenario_id=scenario_id, scenario_name="Accidental disclosure",
            status="no_authoritative_coverage", sources=[],
            diagnostics={"candidates_discovered": 4, "top_rejected": [
                {"url": "https://ex.com", "title": "X", "reason": "wrong tier"}
            ]},
        )],
    )


def _ok_snap():
    from tools.source_librarian.snapshot import ScenarioResult, Snapshot
    return Snapshot(
        register_id="wind_test", run_id="r1", intent_hash="aabb1122",
        started_at=datetime(2026, 4, 20, 10, 2, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 20, 10, 3, tzinfo=timezone.utc),
        tavily_status="ok", firecrawl_status="ok",
        scenarios=[ScenarioResult(scenario_id="WP-001", scenario_name="X",
                                   status="ok", sources=[])],
    )


def _mock_diff():
    return {"add_threat_terms": ["OT ransomware energy"], "remove_threat_terms": [],
            "add_asset_terms": [], "remove_asset_terms": [],
            "add_industry_terms": [], "remove_industry_terms": [],
            "reasoning": "terms too narrow"}


def _setup_intent(tmp_path, monkeypatch):
    d = tmp_path / "research_intents"
    d.mkdir()
    shutil.copy(FIX / "intent_wind_minimal.yaml", d / "wind_test.yaml")
    monkeypatch.setattr("tools.source_librarian.intents.INTENTS_DIR", d)
    monkeypatch.setattr("tools.source_librarian.tuning_log.TUNING_LOG_DIR", tmp_path / "tlog")
    monkeypatch.setattr("tools.source_librarian.snapshot.OUTPUT_DIR", tmp_path / "out")


def test_autotune_found_on_first_success(tmp_path, monkeypatch):
    _setup_intent(tmp_path, monkeypatch)
    with patch("tools.source_librarian.tuner._call_tuner_agent", return_value=_mock_diff()), \
         patch("tools.source_librarian.tuner._call_validator_agent",
               return_value={"verdict": "approved", "reason": "ok"}), \
         patch("tools.source_librarian.tuner._run_discovery_for_scenario",
               return_value=_ok_snap()):
        from tools.source_librarian.tuner import run_autotune
        result = run_autotune("wind_test", "WP-001", base_snapshot=_base_no_cov_snap())

    assert result.outcome == "found"
    assert result.iterations_used == 1
    assert result.winning_diff is not None


def test_autotune_exhausted_after_max_iterations(tmp_path, monkeypatch):
    _setup_intent(tmp_path, monkeypatch)
    with patch("tools.source_librarian.tuner._call_tuner_agent", return_value=_mock_diff()), \
         patch("tools.source_librarian.tuner._call_validator_agent",
               return_value={"verdict": "approved", "reason": "ok"}), \
         patch("tools.source_librarian.tuner._run_discovery_for_scenario",
               return_value=_base_no_cov_snap()):
        from tools.source_librarian.tuner import run_autotune
        result = run_autotune("wind_test", "WP-001", base_snapshot=_base_no_cov_snap(),
                              max_iterations=3)

    assert result.outcome == "exhausted"
    assert result.iterations_used == 3


def test_autotune_cancelled_immediately(tmp_path, monkeypatch):
    _setup_intent(tmp_path, monkeypatch)
    cancel = threading.Event()
    cancel.set()

    with patch("tools.source_librarian.tuner._call_tuner_agent", return_value=_mock_diff()), \
         patch("tools.source_librarian.tuner._call_validator_agent",
               return_value={"verdict": "approved", "reason": "ok"}), \
         patch("tools.source_librarian.tuner._run_discovery_for_scenario",
               return_value=_base_no_cov_snap()):
        from tools.source_librarian.tuner import run_autotune
        result = run_autotune("wind_test", "WP-001", base_snapshot=_base_no_cov_snap(),
                              cancel_event=cancel)

    assert result.outcome == "cancelled"
    assert result.iterations_used == 0


def test_autotune_yaml_on_disk_never_mutated(tmp_path, monkeypatch):
    _setup_intent(tmp_path, monkeypatch)
    yaml_path = tmp_path / "research_intents" / "wind_test.yaml"
    original = yaml_path.read_text()

    with patch("tools.source_librarian.tuner._call_tuner_agent",
               return_value={**_mock_diff(), "add_threat_terms": ["INJECTED_TERM"]}), \
         patch("tools.source_librarian.tuner._call_validator_agent",
               return_value={"verdict": "approved", "reason": "ok"}), \
         patch("tools.source_librarian.tuner._run_discovery_for_scenario",
               return_value=_base_no_cov_snap()):
        from tools.source_librarian.tuner import run_autotune
        run_autotune("wind_test", "WP-001", base_snapshot=_base_no_cov_snap(), max_iterations=1)

    assert yaml_path.read_text() == original
    assert "INJECTED_TERM" not in yaml_path.read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/source_librarian/test_tuner.py -v
```
Expected: `ModuleNotFoundError: No module named 'tools.source_librarian.tuner'`

- [ ] **Step 3: Implement `tools/source_librarian/tuner.py`**

```python
"""Auto-tune loop: self-healing discovery for no_authoritative_coverage scenarios."""
from __future__ import annotations

import copy
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .intents import load_intent
from .snapshot import Snapshot
from .tuning_log import append_event


@dataclass
class AutoTuneResult:
    outcome: str   # "found" | "exhausted" | "cancelled"
    iterations_used: int
    cost_usd: float
    winning_diff: Optional[dict] = None
    winning_sources: list[dict] = field(default_factory=list)
    log_entries: list[dict] = field(default_factory=list)


def _apply_diff(scenario_intent: dict, diff: dict) -> dict:
    """Return a NEW dict with diff applied. Original is never mutated."""
    result = copy.deepcopy(scenario_intent)
    for key in ("threat_terms", "asset_terms", "industry_terms"):
        current = list(result.get(key, []))
        adds = diff.get(f"add_{key}", [])
        removes = set(diff.get(f"remove_{key}", []))
        result[key] = [t for t in current if t not in removes] + adds
    return result


def _call_tuner_agent(
    scenario_intent: dict,
    rejected_candidates: list[dict],
    scenario_desc: str,
    prior_attempts: list[dict],
) -> dict:
    """Call Haiku to propose a diff. In tests, this function is patched."""
    import anthropic
    client = anthropic.Anthropic()
    prompt = (
        f"Scenario: {scenario_desc}\n\n"
        f"Current intent scenario:\n{json.dumps(scenario_intent, indent=2)}\n\n"
        f"Rejected candidates:\n{json.dumps(rejected_candidates, indent=2)}\n\n"
        f"Prior diffs tried:\n{json.dumps(prior_attempts, indent=2)}\n\n"
        f"Propose a diff with keys: add_threat_terms, remove_threat_terms, "
        f"add_asset_terms, remove_asset_terms, add_industry_terms, remove_industry_terms, reasoning. "
        f"Respond with ONLY valid JSON."
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _call_validator_agent(
    diff: dict,
    rejected_candidates: list[dict],
    scenario_desc: str,
) -> dict:
    """Call Haiku to validate the diff. In tests, this function is patched."""
    import anthropic
    client = anthropic.Anthropic()
    prompt = (
        f"Scenario: {scenario_desc}\n\n"
        f"Proposed diff:\n{json.dumps(diff, indent=2)}\n\n"
        f"Rejected candidates:\n{json.dumps(rejected_candidates, indent=2)}\n\n"
        f"Approve if terms are on-topic, not hallucinated, and not more narrow. "
        f"Respond with ONLY: {{\"verdict\": \"approved\"|\"rejected\", \"reason\": \"...\"}}"
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=128,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _run_discovery_for_scenario(
    register_id: str,
    scenario_id: str,
    modified_intent_sc: dict,
) -> Snapshot:
    """Run discovery+rank for one scenario with an in-memory modified intent.

    The yaml on disk is never read after the initial load.
    In tests, this function is patched.
    """
    from .intents import load_intent, ScenarioIntent
    from . import run_snapshot
    import tools.source_librarian.intents as _intents_mod

    base_intent = load_intent(register_id)
    modified_sc = ScenarioIntent(
        name=modified_intent_sc.get("name", ""),
        threat_terms=modified_intent_sc.get("threat_terms", []),
        asset_terms=modified_intent_sc.get("asset_terms", []),
        industry_terms=modified_intent_sc.get("industry_terms", []),
        time_focus_years=modified_intent_sc.get("time_focus_years", 3),
        notes=modified_intent_sc.get("notes", ""),
    )
    patched_scenarios = {**base_intent.scenarios, scenario_id: modified_sc}
    patched_intent = base_intent.model_copy(update={"scenarios": patched_scenarios})

    original_load = _intents_mod.load_intent

    def _patched_load(reg_id: str):
        return patched_intent if reg_id == register_id else original_load(reg_id)

    _intents_mod.load_intent = _patched_load
    try:
        return run_snapshot(register_id, scenario_id=scenario_id)
    finally:
        _intents_mod.load_intent = original_load


def run_autotune(
    register_id: str,
    scenario_id: str,
    *,
    base_snapshot: Snapshot,
    max_iterations: int = 5,
    max_cost_usd: float = 0.50,
    cancel_event: Optional[threading.Event] = None,
    on_progress: Optional[Callable[[dict], None]] = None,
) -> AutoTuneResult:
    """Self-healing discovery loop. Returns on success, budget exhaustion, or cancellation.

    The intent yaml on disk is NEVER mutated.
    """
    run_id = f"autotune-{uuid.uuid4().hex[:8]}"
    intent = load_intent(register_id)
    sc_intent = intent.scenarios.get(scenario_id)
    if sc_intent is None:
        raise KeyError(f"Scenario '{scenario_id}' not in intent for '{register_id}'")

    base_sc = next((s for s in base_snapshot.scenarios if s.scenario_id == scenario_id), None)
    if base_sc is None:
        raise KeyError(f"Scenario '{scenario_id}' not in base_snapshot")

    scenario_desc = sc_intent.name + (f" — {sc_intent.notes}" if sc_intent.notes else "")
    current_sc_dict = sc_intent.model_dump()
    rejected_candidates = (base_sc.diagnostics or {}).get("top_rejected", [])
    prior_attempts: list[dict] = []
    total_cost = 0.0
    log_entries: list[dict] = []
    last_iteration = 0

    for iteration in range(1, max_iterations + 1):
        last_iteration = iteration

        if cancel_event and cancel_event.is_set():
            return AutoTuneResult(
                outcome="cancelled", iterations_used=iteration - 1,
                cost_usd=total_cost, log_entries=log_entries,
            )

        if on_progress:
            on_progress({"event": "iteration_start", "iteration": iteration, "max": max_iterations})

        diff = _call_tuner_agent(current_sc_dict, rejected_candidates, scenario_desc, prior_attempts)
        verdict_resp = _call_validator_agent(diff, rejected_candidates, scenario_desc)
        verdict = verdict_resp.get("verdict", "rejected")

        log_entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "register_id": register_id, "scenario_id": scenario_id,
            "run_id": run_id, "iteration": iteration,
            "event": "proposed", "diff": diff,
            "reasoning": diff.get("reasoning", ""),
            "validator_verdict": verdict, "cost_usd": 0.01,
        }
        append_event(register_id, log_entry)
        log_entries.append(log_entry)
        total_cost += 0.01

        if on_progress:
            on_progress({"event": "diff_proposed", "iteration": iteration,
                         "reasoning": diff.get("reasoning", ""), "verdict": verdict})

        if verdict != "approved":
            prior_attempts.append(diff)
            continue

        modified_sc_dict = _apply_diff(current_sc_dict, diff)
        rerun_snap = _run_discovery_for_scenario(register_id, scenario_id, modified_sc_dict)

        rerun_sc = next((s for s in rerun_snap.scenarios if s.scenario_id == scenario_id), None)
        t1t2_count = len([s for s in (rerun_sc.sources if rerun_sc else [])
                          if s.publisher_tier in ("T1", "T2")])
        new_rejected = (rerun_sc.diagnostics or {}).get("top_rejected", []) if rerun_sc else []

        rerun_entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "register_id": register_id, "scenario_id": scenario_id,
            "run_id": run_id, "iteration": iteration, "event": "rerun_result",
            "candidates_discovered": (rerun_sc.diagnostics or {}).get("candidates_discovered", 0) if rerun_sc else 0,
            "t1_t2_count": t1t2_count,
            "best_rejection": new_rejected[0] if new_rejected else None,
            "cost_usd": 0.04,
        }
        append_event(register_id, rerun_entry)
        log_entries.append(rerun_entry)
        total_cost += 0.04

        if on_progress:
            on_progress({"event": "rerun_result", "iteration": iteration,
                         "t1_t2_count": t1t2_count,
                         "best_rejection": new_rejected[0] if new_rejected else None})

        if t1t2_count > 0:
            won: dict[str, Any] = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "register_id": register_id, "scenario_id": scenario_id,
                "run_id": run_id, "iteration": iteration, "event": "succeeded",
                "winning_diff": diff,
                "sources_found": [s.model_dump(mode="json") for s in (rerun_sc.sources if rerun_sc else [])],
                "total_cost_usd": total_cost,
            }
            append_event(register_id, won)
            log_entries.append(won)
            return AutoTuneResult(
                outcome="found", iterations_used=iteration, cost_usd=total_cost,
                winning_diff=diff,
                winning_sources=[s.model_dump(mode="json") for s in (rerun_sc.sources if rerun_sc else [])],
                log_entries=log_entries,
            )

        rejected_candidates = new_rejected
        prior_attempts.append(diff)

        if total_cost >= max_cost_usd:
            break

    return AutoTuneResult(
        outcome="exhausted", iterations_used=last_iteration,
        cost_usd=total_cost, log_entries=log_entries,
    )
```

- [ ] **Step 4: Run tests**

```
uv run pytest tests/source_librarian/test_tuner.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add tools/source_librarian/tuner.py tests/source_librarian/test_tuner.py
git commit -m "feat(source-librarian): auto-tune loop with patched tuner/validator callsites"
```

---

### Task 10: Agent definitions + stop hook

**Files:**
- Create: `.claude/agents/intent-tuner-agent.md`
- Create: `.claude/agents/intent-tuner-validator-agent.md`
- Create: `.claude/hooks/validators/intent-tuner-output.py`

- [ ] **Step 1: Create `.claude/agents/intent-tuner-agent.md`**

```markdown
---
name: intent-tuner-agent
description: Proposes intent yaml diffs to improve discovery coverage for a no_authoritative_coverage scenario
model: claude-haiku-4-5-20251001
tools:
  - Read
  - Glob
  - Grep
hooks:
  stop:
    - type: command
      command: "INTENT_TUNER_ROLE=tuner uv run python .claude/hooks/validators/intent-tuner-output.py"
---

You are an intent tuner for a cyber risk intelligence pipeline.

Analyze a scenario that landed in no_authoritative_coverage and propose minimal search term changes
to help find T1/T2 coverage from publishers like ICS-CERT, Dragos, ENISA, IBM X-Force.

## Output

Respond with ONLY a JSON object — no prose, no markdown fences:

{"add_threat_terms": [...], "remove_threat_terms": [...], "add_asset_terms": [...],
 "remove_asset_terms": [...], "add_industry_terms": [...], "remove_industry_terms": [...],
 "reasoning": "one sentence explaining why"}

## Constraints

- Only modify threat_terms, asset_terms, industry_terms. No other fields.
- Do not duplicate terms already in prior_attempts.
- Use vocabulary that matches ICS/OT publisher tagging conventions.
```

- [ ] **Step 2: Create `.claude/agents/intent-tuner-validator-agent.md`**

```markdown
---
name: intent-tuner-validator-agent
description: Validates tuner diff proposals — blocks off-topic, hallucinated, or narrowing diffs
model: claude-haiku-4-5-20251001
tools:
  - Read
hooks:
  stop:
    - type: command
      command: "INTENT_TUNER_ROLE=validator uv run python .claude/hooks/validators/intent-tuner-output.py"
---

You are a diff validator for a cyber risk intelligence pipeline.

Evaluate the proposed term diff against the scenario description and rejected candidates.

## Output

Respond with ONLY a JSON object — no prose, no markdown fences:

{"verdict": "approved", "reason": "..."} OR {"verdict": "rejected", "reason": "..."}

## Approval criteria (ALL must be true to approve)

- Terms are on-topic for the scenario
- Terms are real ICS/OT/cybersecurity vocabulary (not hallucinated)
- Diff is at least as broad as current terms — does not narrow the query
- No term duplicates prior_attempts
```

- [ ] **Step 3: Create `.claude/hooks/validators/intent-tuner-output.py`**

```python
#!/usr/bin/env python3
"""Stop hook for intent-tuner-agent (INTENT_TUNER_ROLE=tuner) and
intent-tuner-validator-agent (INTENT_TUNER_ROLE=validator)."""
import json
import os
import sys

ALLOWED_DIFF_KEYS = {
    "add_threat_terms", "remove_threat_terms",
    "add_asset_terms", "remove_asset_terms",
    "add_industry_terms", "remove_industry_terms",
    "reasoning",
}
REQUIRED_DIFF_KEYS = ALLOWED_DIFF_KEYS - {"reasoning"}
ALLOWED_VERDICTS = {"approved", "rejected"}


def validate_tuner(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return [f"Output is not valid JSON: {e}"]
    errors = []
    missing = REQUIRED_DIFF_KEYS - set(data.keys())
    if missing:
        errors.append(f"Missing required keys: {sorted(missing)}")
    extra = set(data.keys()) - ALLOWED_DIFF_KEYS
    if extra:
        errors.append(f"Disallowed keys (tuner may only modify term lists): {sorted(extra)}")
    for key in REQUIRED_DIFF_KEYS:
        if key in data and not isinstance(data[key], list):
            errors.append(f"Key '{key}' must be a list, got {type(data[key]).__name__}")
    return errors


def validate_validator(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return [f"Output is not valid JSON: {e}"]
    errors = []
    if "verdict" not in data:
        errors.append("Missing required key: 'verdict'")
    elif data["verdict"] not in ALLOWED_VERDICTS:
        errors.append(f"'verdict' must be one of {ALLOWED_VERDICTS}, got '{data['verdict']}'")
    if "reason" not in data:
        errors.append("Missing required key: 'reason'")
    return errors


def main():
    role = os.environ.get("INTENT_TUNER_ROLE", "tuner")
    text = sys.stdin.read().strip()
    if not text:
        print("ERROR: empty agent output", file=sys.stderr)
        sys.exit(1)
    errors = validate_tuner(text) if role == "tuner" else validate_validator(text)
    if errors:
        for e in errors:
            print(f"STOP HOOK FAIL: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify stop hook exit codes**

```
echo '{"add_threat_terms":["x"],"remove_threat_terms":[],"add_asset_terms":[],"remove_asset_terms":[],"add_industry_terms":[],"remove_industry_terms":[],"reasoning":"r"}' | INTENT_TUNER_ROLE=tuner uv run python .claude/hooks/validators/intent-tuner-output.py && echo "exit 0"
```
Expected: `exit 0`

```
echo '{"verdict":"approved","reason":"ok"}' | INTENT_TUNER_ROLE=validator uv run python .claude/hooks/validators/intent-tuner-output.py && echo "exit 0"
```
Expected: `exit 0`

```
echo '{"verdict":"maybe","reason":"ok"}' | INTENT_TUNER_ROLE=validator uv run python .claude/hooks/validators/intent-tuner-output.py; echo "exit $?"
```
Expected: `exit 1`

- [ ] **Step 5: Commit**

```bash
git add .claude/agents/intent-tuner-agent.md .claude/agents/intent-tuner-validator-agent.md .claude/hooks/validators/intent-tuner-output.py
git commit -m "feat(agents): intent-tuner and intent-tuner-validator agents with stop hooks"
```

---

### Task 11: Server autotune endpoint + client live feed UI

**Files:**
- Modify: `server.py` (additive — new endpoint after cancel_research)
- Modify: `static/app.js` (additive — startAutoTune, cancelAutoTune)

- [ ] **Step 1: Add `POST /api/research/autotune` to `server.py`**

After the `cancel_research` endpoint:

```python
@app.post("/api/research/autotune")
async def start_autotune(register: str, scenario: str, background: BackgroundTasks):
    """Kick off an auto-tune loop for one scenario."""
    run_id = f"autotune-{str(_uuid.uuid4())[:8]}"
    lock = threading.Lock()
    _research_runs[run_id] = {
        "status": "running", "register": register, "scenario_id": scenario,
        "autotune": {"iteration": 0, "log": [], "cost_usd": 0.0, "budget_remaining": 5},
        "progress": {}, "lock": lock,
    }
    cancel_event = threading.Event()
    _cancel_events[run_id] = cancel_event

    def _execute():
        try:
            from tools.source_librarian import get_latest_snapshot
            from tools.source_librarian.tuner import run_autotune
            base_snap = get_latest_snapshot(register)
            if base_snap is None:
                state = _research_runs[run_id]
                with state["lock"]:
                    state.update({"status": "failed", "error": "No base snapshot found"})
                return

            def _progress(update: dict):
                state = _research_runs.get(run_id)
                if state is None:
                    return
                with state["lock"]:
                    state["progress"] = update
                    at = state.setdefault("autotune", {})
                    if update.get("event") == "iteration_start":
                        at["iteration"] = update.get("iteration", 0)
                        at["budget_remaining"] = 5 - at["iteration"]
                    if update.get("event") in ("diff_proposed", "rerun_result"):
                        at.setdefault("log", []).append(update)

            result = run_autotune(register, scenario, base_snapshot=base_snap,
                                  cancel_event=cancel_event, on_progress=_progress)

            state = _research_runs[run_id]
            with state["lock"]:
                state.update({
                    "status": "complete",
                    "autotune_outcome": result.outcome,
                    "autotune_iterations": result.iterations_used,
                    "autotune_cost_usd": result.cost_usd,
                    "winning_diff": result.winning_diff,
                })
                if result.outcome == "found":
                    snap = get_latest_snapshot(register)
                    if snap:
                        state["snapshot"] = snap.model_dump(mode="json")
        except Exception as exc:
            log.exception("[autotune] run failed")
            state = _research_runs.get(run_id, {})
            lock_ = state.get("lock")
            update_ = {"status": "failed", "error": str(exc)}
            if lock_:
                with lock_:
                    state.update(update_)
            else:
                state.update(update_)
        finally:
            _cancel_events.pop(run_id, None)

    background.add_task(_execute)
    return {"run_id": run_id, "status": "running"}
```

- [ ] **Step 2: Add `startAutoTune` and `cancelAutoTune` to `static/app.js`**

`startAutoTune(registerId, scenarioId)`:
1. Replace the no-coverage panel body with a live feed container (monospaced timestamped log, iteration counter, budget footer, cancel button)
2. POST to `/api/research/autotune?register=X&scenario=Y`
3. Poll at 2s — update iteration counter and log lines from `state.progress`
4. On `state.status === 'complete'` with `autotune_outcome === 'found'`: update cache, call `_renderEvidenceSection`, `_renderScenarioList`, `_updateRegisterHeader`
5. On exhausted: append "Auto-tune ran N iterations — no T1/T2 found." then re-render no-coverage panel
6. Store `runId` in `window._autotuneRunIds[scenarioId]`

`cancelAutoTune(registerId, scenarioId)`:
1. Read `runId` from `window._autotuneRunIds[scenarioId]`
2. POST to `/api/research/cancel?run_id=X`
3. Disable cancel button, show "Cancelling…"

- [ ] **Step 3: Verify server boots**

```
uv run python -c "import server; print('ok')"
```
Expected: `ok`

- [ ] **Step 4: Start dev server and exercise auto-tune**

```
uv run python server.py
```
Navigate to a scenario with no-coverage. Click AUTO-TUNE. Verify:
- Live feed panel replaces no-coverage panel
- Log lines appear during run
- Cancel button works and shows "Cancelling…"

- [ ] **Step 5: Commit**

```bash
git add server.py static/app.js
git commit -m "feat(ui,server): auto-tune live feed UI and autotune endpoint"
```

---

## Final Verification

- [ ] **Run full test suite**

```
uv run pytest tests/source_librarian/ -v
```
Expected: all pass, including:
- `test_per_scenario_rerun.py` — 4 tests
- `test_progress_callbacks.py` — 4 tests
- `test_tuning_log.py` — 4 tests
- `test_tuner.py` — 4 tests

- [ ] **No `alert()` in research/refresh paths**

```
grep -n "alert(" static/app.js
```
Expected: 0 occurrences in `refreshAllSources`, `rerunScenario`, `startAutoTune`

- [ ] **Stale badge smoke test**

Edit any field in `data/research_intents/wind_power_plant.yaml`, save, reload app. Confirm `⚠ INTENT CHANGED — RERUN` badge appears in register header.

---

## Self-Review

**Spec coverage:**

| Spec § | Covered by |
|---|---|
| §2.1 Register header bar (rollup, stale badge, REFRESH ALL) | Task 5 |
| §2.1 Scenario list SOURCES column | Task 6 |
| §2.1 Scenario detail stack (Evidence first) | Task 7 |
| §2.2 `on_progress`, 2s poll, skeleton progress | Tasks 3, 4, 5 |
| §2.2 Cancel via cooperative threading.Event | Task 4 |
| §2.3 Per-scenario rerun + merge | Tasks 1, 4, 7 |
| §2.4 Empty state onboarding card | Task 7 (`_renderEvidenceSection` branch 1) |
| §2.5 Degraded states (amber/red inline) | Task 7 (`_renderEvidenceSection` branches 2+3) |
| §2.6 Auto-tune loop (tuner + validator agents) | Tasks 9, 10, 11 |
| §2.7 JSONL tuning log | Task 8 |
| §2.8 Stale-intent indicator | Tasks 2, 4, 5 |

**Type consistency:**
- `merge_scenario_result(register_id, new_result, *, output_dir)` — used identically in `server.py` and tests
- `run_autotune(register_id, scenario_id, *, base_snapshot, ...)` — `base_snapshot` is keyword-only `Snapshot`; server fetches it first
- `_renderEvidenceSection(snap, scenarioId, registerId)` — consistent call signature across `_renderScenarioDetail`, `refreshAllSources`, `rerunScenario`, `startAutoTune`
- `refreshReadingList` and `loadReadingListForScenario` — deleted, not referenced anywhere after Phase 2

**Placeholder scan:** No TBD, TODO, or vague steps present.
