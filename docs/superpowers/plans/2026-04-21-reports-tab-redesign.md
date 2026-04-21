# Reports Tab Redesign Implementation Plan

**Goal:** Rebuild the Reports tab as a card-grid launcher backed by a filesystem archive of versioned PDFs + thumbnails + sidecar JSON, with per-audience stale detection via pipeline run IDs.

**Architecture:** Two new backend modules (`tools/briefs/pipeline_state.py`, `tools/briefs/storage.py`) provide run-id resolution and archive I/O. `render_pdf` grows a `thumbnail_path` output. Loaders return `(data, pipeline_run_id)`. New `/api/briefs/` endpoints replace the three legacy `/api/briefs/{board,ciso}/pdf` + `/api/briefs/rsm/{region}/pdf` routes. Client-side rail is deleted; a new card grid is rendered with safe DOM methods (no `innerHTML`).

**Tech Stack:** Python 3 (uv), FastAPI, Playwright + Jinja2, pytest, vanilla JS (no build step).

**Spec reference:** `docs/superpowers/specs/2026-04-21-reports-tab-redesign.md`

---

## File Structure

### Create
- `tools/briefs/pipeline_state.py` — run-id resolution
- `tools/briefs/storage.py` — filesystem archive with sidecar JSON
- `tests/briefs/test_pipeline_state.py`
- `tests/briefs/test_storage.py`
- `tests/briefs/test_api.py` — FastAPI endpoint tests

### Modify
- `tools/briefs/renderer.py` — accept `thumbnail_path`, screenshot cover `section.page`
- `tools/briefs/data/ciso.py` — return tuple
- `tools/briefs/data/board.py` — return tuple
- `tools/briefs/data/rsm.py` — return tuple
- `tools/build_pdf.py` — archive by default, `--no-archive` opt-out
- `server.py` — replace three legacy routes with `/api/briefs/*`, wire startup sweep
- `static/app.js` — delete rail/in-browser renderers, add card grid builder
- `static/index.html` — delete rail CSS, add card grid CSS
- `tests/briefs/test_loaders.py` — destructure new tuple returns

### Regional pipeline runner (one-line change, location TBD during recon)
- Write `run_id` into `output/regional/{region}/meta.json` at the end of a regional run.

---

# Phase 1 — Foundation: pipeline_state + storage

## Task 1: `pipeline_state.py` — run-id resolution

**Files:**
- Create: `tools/briefs/pipeline_state.py`
- Test: `tests/briefs/test_pipeline_state.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/briefs/test_pipeline_state.py
import json
from pathlib import Path
import pytest
from tools.briefs import pipeline_state


def test_global_run_id_reads_last_run_log(tmp_path, monkeypatch):
    log = tmp_path / "pipeline" / "last_run_log.json"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps({"run_id": "run-2026-04-21-0412"}))
    monkeypatch.setattr(pipeline_state, "PIPELINE_LOG", log)
    assert pipeline_state.global_run_id() == "run-2026-04-21-0412"


def test_global_run_id_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_state, "PIPELINE_LOG", tmp_path / "nope.json")
    assert pipeline_state.global_run_id() is None


def test_region_run_id_reads_regional_meta(tmp_path, monkeypatch):
    meta = tmp_path / "regional" / "med" / "meta.json"
    meta.parent.mkdir(parents=True)
    meta.write_text(json.dumps({"run_id": "run-med-0412"}))
    monkeypatch.setattr(pipeline_state, "REGIONAL_ROOT", tmp_path / "regional")
    assert pipeline_state.region_run_id("med") == "run-med-0412"


def test_region_run_id_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_state, "REGIONAL_ROOT", tmp_path / "regional")
    assert pipeline_state.region_run_id("med") is None


def test_current_run_id_routes_by_audience(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_state, "global_run_id", lambda: "G")
    monkeypatch.setattr(pipeline_state, "region_run_id", lambda r: f"R-{r}")
    assert pipeline_state.current_run_id("ciso") == "G"
    assert pipeline_state.current_run_id("board") == "G"
    assert pipeline_state.current_run_id("rsm-med") == "R-med"


def test_current_run_id_unknown_audience_raises():
    with pytest.raises(ValueError):
        pipeline_state.current_run_id("unknown")
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `uv run pytest tests/briefs/test_pipeline_state.py -v`
Expected: FAIL — module `tools.briefs.pipeline_state` does not exist.

- [ ] **Step 3: Minimal implementation**

```python
# tools/briefs/pipeline_state.py
from __future__ import annotations
import json
from pathlib import Path

PIPELINE_LOG = Path("output/pipeline/last_run_log.json")
REGIONAL_ROOT = Path("output/regional")
_KNOWN_REGIONS = {"apac", "ame", "latam", "med", "nce"}


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def global_run_id() -> str | None:
    data = _read_json(PIPELINE_LOG)
    return data.get("run_id") if data else None


def region_run_id(region: str) -> str | None:
    data = _read_json(REGIONAL_ROOT / region.lower() / "meta.json")
    return data.get("run_id") if data else None


def current_run_id(audience_id: str) -> str | None:
    if audience_id in ("ciso", "board"):
        return global_run_id()
    if audience_id.startswith("rsm-"):
        region = audience_id.removeprefix("rsm-")
        if region not in _KNOWN_REGIONS:
            raise ValueError(f"unknown RSM region: {region}")
        return region_run_id(region)
    raise ValueError(f"unknown audience_id: {audience_id}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/briefs/test_pipeline_state.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/briefs/pipeline_state.py tests/briefs/test_pipeline_state.py
git commit -m "feat(briefs): add pipeline_state — global/region/current run id resolution"
```

---

## Task 2: `storage.py` — `VersionRecord` + timestamp helpers

**Files:**
- Create: `tools/briefs/storage.py` (partial — helpers only)
- Test: `tests/briefs/test_storage.py` (partial)

- [ ] **Step 1: Write failing tests for the helpers**

```python
# tests/briefs/test_storage.py
from datetime import datetime, timezone
from pathlib import Path
from tools.briefs import storage


def test_compact_iso_roundtrip():
    iso = "2026-04-21T04:12:00Z"
    compact = storage.iso_to_compact(iso)
    assert compact == "20260421T041200Z"
    assert storage.compact_to_iso(compact) == iso


def test_utc_now_iso_shape():
    now = storage.utc_now_iso()
    assert now.endswith("Z")
    parsed = datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ")
    assert parsed.tzinfo is None  # naive, treated as UTC by convention


def test_version_record_fields():
    rec = storage.VersionRecord(
        audience_id="ciso",
        version_ts="2026-04-21T04:12:00Z",
        pipeline_run_id="run-0412",
        narrated=False,
        generated_by="manual",
        metadata={},
        pdf_path=Path("/x.pdf"),
        thumbnail_path=Path("/x.png"),
    )
    assert rec.version_ts == "2026-04-21T04:12:00Z"
    assert rec.narrated is False
```

- [ ] **Step 2: Run to confirm fail**

Run: `uv run pytest tests/briefs/test_storage.py -v`
Expected: FAIL — `tools.briefs.storage` has no such attributes.

- [ ] **Step 3: Minimal implementation**

```python
# tools/briefs/storage.py
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ARCHIVE_ROOT = Path("output/deliverables/archive")
RETENTION = int(os.getenv("BRIEFS_RETENTION", "5"))


@dataclass(frozen=True)
class VersionRecord:
    audience_id: str
    version_ts: str                # ISO 8601 UTC, e.g. "2026-04-21T04:12:00Z"
    pipeline_run_id: str | None
    narrated: bool
    generated_by: str              # "cli" | "api" | "manual"
    metadata: dict
    pdf_path: Path
    thumbnail_path: Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_to_compact(iso: str) -> str:
    return iso.replace("-", "").replace(":", "")


def compact_to_iso(compact: str) -> str:
    # compact: YYYYMMDDTHHMMSSZ → YYYY-MM-DDTHH:MM:SSZ
    return f"{compact[0:4]}-{compact[4:6]}-{compact[6:11]}:{compact[11:13]}:{compact[13:16]}"
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/briefs/test_storage.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/briefs/storage.py tests/briefs/test_storage.py
git commit -m "feat(briefs): storage scaffold — VersionRecord + timestamp helpers"
```

---

## Task 3: `record_version` — atomic archive write

**Files:**
- Modify: `tools/briefs/storage.py`
- Modify: `tests/briefs/test_storage.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/briefs/test_storage.py`:

```python
import pytest


def _make_tmp_artifacts(tmp_path):
    pdf = tmp_path / "render.pdf"
    png = tmp_path / "render.png"
    pdf.write_bytes(b"%PDF-1.4 fake")
    png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return pdf, png


def test_record_version_moves_artifacts_and_writes_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    pdf, png = _make_tmp_artifacts(tmp_path)

    rec = storage.record_version(
        audience_id="ciso",
        pdf_tmp_path=pdf,
        thumbnail_tmp_path=png,
        pipeline_run_id="run-0412",
        narrated=False,
        generated_by="api",
        metadata={"month": "2026-04"},
    )

    assert rec.audience_id == "ciso"
    assert rec.pdf_path.exists()
    assert rec.thumbnail_path.exists()
    sidecar = rec.pdf_path.with_suffix(".json")
    assert sidecar.exists()
    data = json.loads(sidecar.read_text())
    assert data["pipeline_run_id"] == "run-0412"
    assert data["narrated"] is False
    # tmp files are consumed
    assert not pdf.exists()
    assert not png.exists()


def test_record_version_sidecar_last_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    pdf, png = _make_tmp_artifacts(tmp_path)

    def boom(*_a, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr(storage, "_write_sidecar", boom)
    with pytest.raises(OSError):
        storage.record_version(
            audience_id="ciso",
            pdf_tmp_path=pdf,
            thumbnail_tmp_path=png,
            pipeline_run_id=None,
            narrated=False,
            generated_by="api",
            metadata={},
        )
    # Nothing should linger in the archive
    audience_dir = tmp_path / "archive" / "ciso"
    if audience_dir.exists():
        assert list(audience_dir.iterdir()) == []
```

- [ ] **Step 2: Run to confirm fail**

Run: `uv run pytest tests/briefs/test_storage.py -v`
Expected: FAIL — `record_version` not defined.

- [ ] **Step 3: Implement `record_version` + internal helpers**

Append to `tools/briefs/storage.py`:

```python
def _audience_dir(audience_id: str) -> Path:
    d = ARCHIVE_ROOT / audience_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_sidecar(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def record_version(
    audience_id: str,
    pdf_tmp_path: Path,
    thumbnail_tmp_path: Path,
    pipeline_run_id: str | None,
    narrated: bool,
    generated_by: str,
    metadata: dict,
) -> VersionRecord:
    if not pdf_tmp_path.exists() or pdf_tmp_path.stat().st_size == 0:
        raise ValueError(f"pdf tmp file missing or empty: {pdf_tmp_path}")
    if not thumbnail_tmp_path.exists() or thumbnail_tmp_path.stat().st_size == 0:
        raise ValueError(f"thumbnail tmp file missing or empty: {thumbnail_tmp_path}")

    sweep_orphans(audience_id)

    version_ts = utc_now_iso()
    basename = iso_to_compact(version_ts)
    dest_dir = _audience_dir(audience_id)
    pdf_dest = dest_dir / f"{basename}.pdf"
    png_dest = dest_dir / f"{basename}.png"
    sidecar_dest = dest_dir / f"{basename}.json"

    os.replace(pdf_tmp_path, pdf_dest)
    try:
        os.replace(thumbnail_tmp_path, png_dest)
    except Exception:
        pdf_dest.unlink(missing_ok=True)
        raise

    payload = {
        "audience_id": audience_id,
        "version_ts": version_ts,
        "pipeline_run_id": pipeline_run_id,
        "narrated": narrated,
        "generated_by": generated_by,
        "metadata": metadata,
    }
    try:
        _write_sidecar(sidecar_dest, payload)
    except Exception:
        pdf_dest.unlink(missing_ok=True)
        png_dest.unlink(missing_ok=True)
        raise

    prune(audience_id)

    return VersionRecord(
        audience_id=audience_id,
        version_ts=version_ts,
        pipeline_run_id=pipeline_run_id,
        narrated=narrated,
        generated_by=generated_by,
        metadata=metadata,
        pdf_path=pdf_dest,
        thumbnail_path=png_dest,
    )


def sweep_orphans(audience_id: str) -> int:
    """Remove pdf/png files without matching sidecar. Returns count removed."""
    d = ARCHIVE_ROOT / audience_id
    if not d.exists():
        return 0
    removed = 0
    for artifact in list(d.glob("*.pdf")) + list(d.glob("*.png")):
        sidecar = artifact.with_suffix(".json")
        if not sidecar.exists():
            artifact.unlink(missing_ok=True)
            removed += 1
    return removed


def prune(audience_id: str) -> int:
    """Keep newest N versions per BRIEFS_RETENTION. Returns count removed."""
    if RETENTION <= 0:
        return 0
    versions = list_versions(audience_id)
    removed = 0
    for rec in versions[RETENTION:]:
        basename = iso_to_compact(rec.version_ts)
        d = ARCHIVE_ROOT / audience_id
        (d / f"{basename}.pdf").unlink(missing_ok=True)
        (d / f"{basename}.png").unlink(missing_ok=True)
        (d / f"{basename}.json").unlink(missing_ok=True)
        removed += 1
    return removed
```

Note: `list_versions` is stubbed in Task 4 but referenced here. For this task, add a temporary stub so imports resolve:

```python
def list_versions(audience_id: str) -> list[VersionRecord]:
    return []
```

- [ ] **Step 4: Run to verify tests pass**

Run: `uv run pytest tests/briefs/test_storage.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/briefs/storage.py tests/briefs/test_storage.py
git commit -m "feat(briefs): record_version + sweep_orphans + prune stubs"
```

---

## Task 4: `list_versions`, `get_latest`, `get_specific`

**Files:**
- Modify: `tools/briefs/storage.py`
- Modify: `tests/briefs/test_storage.py`

- [ ] **Step 1: Add failing tests**

```python
def test_list_versions_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    for _ in range(3):
        pdf, png = _make_tmp_artifacts(tmp_path)
        storage.record_version("ciso", pdf, png, None, False, "api", {})
        # spread timestamps (file mtime is based on utc_now_iso, one-second granularity)
        import time; time.sleep(1.1)

    versions = storage.list_versions("ciso")
    assert len(versions) == 3
    assert versions[0].version_ts > versions[1].version_ts > versions[2].version_ts


def test_list_versions_skips_orphans(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    # create one complete version
    pdf, png = _make_tmp_artifacts(tmp_path)
    storage.record_version("ciso", pdf, png, None, False, "api", {})
    # drop an orphan pdf (no sidecar)
    (tmp_path / "archive" / "ciso" / "20990101T000000Z.pdf").write_bytes(b"orphan")

    versions = storage.list_versions("ciso")
    assert len(versions) == 1


def test_get_latest_returns_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    pdf, png = _make_tmp_artifacts(tmp_path)
    first = storage.record_version("ciso", pdf, png, None, False, "api", {})
    import time; time.sleep(1.1)
    pdf, png = _make_tmp_artifacts(tmp_path)
    second = storage.record_version("ciso", pdf, png, None, False, "api", {})
    latest = storage.get_latest("ciso")
    assert latest.version_ts == second.version_ts


def test_get_latest_empty_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    assert storage.get_latest("ciso") is None


def test_get_specific_returns_record(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    pdf, png = _make_tmp_artifacts(tmp_path)
    rec = storage.record_version("ciso", pdf, png, None, False, "api", {})
    hit = storage.get_specific("ciso", rec.version_ts)
    assert hit == rec
    miss = storage.get_specific("ciso", "2000-01-01T00:00:00Z")
    assert miss is None
```

- [ ] **Step 2: Run to confirm fail**

Run: `uv run pytest tests/briefs/test_storage.py -v`
Expected: FAIL — `list_versions` stub returns empty; `get_latest`/`get_specific` don't exist.

- [ ] **Step 3: Replace stub + add `get_latest` / `get_specific`**

Replace the stubbed `list_versions` in `tools/briefs/storage.py`:

```python
def list_versions(audience_id: str) -> list[VersionRecord]:
    d = ARCHIVE_ROOT / audience_id
    if not d.exists():
        return []
    records: list[VersionRecord] = []
    for sidecar in d.glob("*.json"):
        basename = sidecar.stem
        pdf = d / f"{basename}.pdf"
        png = d / f"{basename}.png"
        if not (pdf.exists() and png.exists()):
            continue
        try:
            payload = json.loads(sidecar.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        records.append(VersionRecord(
            audience_id=payload["audience_id"],
            version_ts=payload["version_ts"],
            pipeline_run_id=payload.get("pipeline_run_id"),
            narrated=bool(payload.get("narrated", False)),
            generated_by=payload.get("generated_by", "unknown"),
            metadata=payload.get("metadata", {}),
            pdf_path=pdf,
            thumbnail_path=png,
        ))
    records.sort(key=lambda r: r.version_ts, reverse=True)
    return records


def get_latest(audience_id: str) -> VersionRecord | None:
    versions = list_versions(audience_id)
    return versions[0] if versions else None


def get_specific(audience_id: str, version_ts: str) -> VersionRecord | None:
    for rec in list_versions(audience_id):
        if rec.version_ts == version_ts:
            return rec
    return None
```

- [ ] **Step 4: Run to verify tests pass**

Run: `uv run pytest tests/briefs/test_storage.py -v`
Expected: 10 passed (including earlier tests).

- [ ] **Step 5: Commit**

```bash
git add tools/briefs/storage.py tests/briefs/test_storage.py
git commit -m "feat(briefs): list_versions / get_latest / get_specific"
```

---

## Task 5: `prune` + retention edge cases

**Files:**
- Modify: `tests/briefs/test_storage.py`

- [ ] **Step 1: Add failing tests**

```python
def test_prune_keeps_newest_n(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    monkeypatch.setattr(storage, "RETENTION", 3)
    # record 5 versions
    import time
    for _ in range(5):
        pdf, png = _make_tmp_artifacts(tmp_path)
        storage.record_version("ciso", pdf, png, None, False, "api", {})
        time.sleep(1.1)
    # record_version calls prune internally; after 5 records, only 3 should remain
    versions = storage.list_versions("ciso")
    assert len(versions) == 3


def test_prune_retention_zero_keeps_all(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    monkeypatch.setattr(storage, "RETENTION", 0)
    import time
    for _ in range(4):
        pdf, png = _make_tmp_artifacts(tmp_path)
        storage.record_version("ciso", pdf, png, None, False, "api", {})
        time.sleep(1.1)
    assert len(storage.list_versions("ciso")) == 4


def test_sweep_orphans_standalone(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    d = tmp_path / "archive" / "ciso"
    d.mkdir(parents=True)
    (d / "20260421T041200Z.pdf").write_bytes(b"orphan")
    (d / "20260421T041200Z.png").write_bytes(b"orphan")
    # no sidecar
    removed = storage.sweep_orphans("ciso")
    assert removed == 2
    assert not list(d.iterdir())


def test_sweep_orphans_empty_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    # audience dir doesn't exist
    assert storage.sweep_orphans("ciso") == 0


def test_stale_when_pipeline_run_id_is_null(tmp_path, monkeypatch):
    """Manual renders (pipeline_run_id=None) are never stale."""
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    pdf, png = _make_tmp_artifacts(tmp_path)
    rec = storage.record_version("ciso", pdf, png, None, False, "manual", {})
    assert rec.pipeline_run_id is None
    # Stale computation lives in server layer; here we assert the stored null survives
    hit = storage.get_latest("ciso")
    assert hit.pipeline_run_id is None
```

- [ ] **Step 2: Run to confirm pass / fail**

Run: `uv run pytest tests/briefs/test_storage.py -v`
Expected: all 15 pass (prune logic already in place from Task 3).

- [ ] **Step 3: No code change needed — tests cover existing code**

If any fail, fix `prune` or `sweep_orphans` in `storage.py` to match.

- [ ] **Step 4: Commit**

```bash
git add tests/briefs/test_storage.py
git commit -m "test(briefs): prune retention + sweep_orphans edge cases"
```

---

# Phase 2 — Renderer + loaders

## Task 6: `render_pdf` produces thumbnail alongside PDF

**Files:**
- Modify: `tools/briefs/renderer.py`
- Modify: `tests/briefs/test_renderer.py` (create if absent)

- [ ] **Step 1: Read current `render_pdf`**

Run: `mcp__jcodemunch-mcp__get_file_outline path=tools/briefs/renderer.py` — identify where Playwright generates the PDF.

- [ ] **Step 2: Write failing test**

```python
# tests/briefs/test_renderer.py — add or append
import asyncio
from pathlib import Path
from tools.briefs.renderer import render_pdf
from tools.briefs.data._rsm_mock import rsm_med_w17_mock


def test_render_pdf_produces_thumbnail(tmp_path):
    pdf_out = tmp_path / "out.pdf"
    thumb_out = tmp_path / "out.png"
    asyncio.run(render_pdf("rsm", rsm_med_w17_mock(), pdf_out, thumbnail_path=thumb_out))
    assert pdf_out.exists() and pdf_out.stat().st_size > 1000
    assert thumb_out.exists() and thumb_out.stat().st_size > 1000
```

- [ ] **Step 3: Run to confirm fail**

Run: `uv run pytest tests/briefs/test_renderer.py::test_render_pdf_produces_thumbnail -v`
Expected: FAIL — `render_pdf` does not accept `thumbnail_path`.

- [ ] **Step 4: Extend `render_pdf`**

In `tools/briefs/renderer.py`:

```python
async def render_pdf(
    brief: str,
    data,
    out_path: Path,
    thumbnail_path: Path | None = None,
) -> None:
    # ... existing setup, html build, page.set_content, page.pdf() ...
    # After page.pdf(...) finishes, before closing the page:
    if thumbnail_path is not None:
        await page.locator("section.page").first.screenshot(
            path=str(thumbnail_path),
            scale="device",
        )
    # ... existing teardown ...
```

Keep backward compatibility — callers that don't pass `thumbnail_path` skip the screenshot step.

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/briefs/test_renderer.py -v`
Expected: PASS (this test) + all previously-green renderer tests still green.

- [ ] **Step 6: Commit**

```bash
git add tools/briefs/renderer.py tests/briefs/test_renderer.py
git commit -m "feat(briefs): render_pdf writes cover thumbnail PNG when thumbnail_path provided"
```

---

## Task 7: `load_ciso_data` returns `(data, pipeline_run_id)`

**Files:**
- Modify: `tools/briefs/data/ciso.py`
- Modify: `tests/briefs/test_loaders.py`

- [ ] **Step 1: Update existing test(s)**

In `tests/briefs/test_loaders.py`, find the CISO test and change the destructure:

```python
def test_load_ciso_data_returns_tuple():
    data, run_id = load_ciso_data("2026-04")
    assert data is not None  # existing assertions on data survive
    assert run_id is None or isinstance(run_id, str)
```

- [ ] **Step 2: Run to confirm fail (single return value)**

Run: `uv run pytest tests/briefs/test_loaders.py -v`
Expected: FAIL — can't unpack a single `CisoBrief` into two values.

- [ ] **Step 3: Modify `load_ciso_data`**

```python
# tools/briefs/data/ciso.py
from tools.briefs.pipeline_state import global_run_id

def load_ciso_data(month: str) -> tuple[CisoBrief, str | None]:
    # ... existing body builds `brief` ...
    return brief, global_run_id()
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/briefs/test_loaders.py::test_load_ciso_data_returns_tuple -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/briefs/data/ciso.py tests/briefs/test_loaders.py
git commit -m "refactor(briefs): load_ciso_data returns (data, pipeline_run_id)"
```

---

## Task 8: `load_board_data` returns `(data, pipeline_run_id)`

**Files:**
- Modify: `tools/briefs/data/board.py`
- Modify: `tests/briefs/test_loaders.py`

- [ ] **Step 1: Update existing test(s)**

```python
def test_load_board_data_returns_tuple():
    data, run_id = load_board_data("2026Q2")
    assert data is not None
    assert run_id is None or isinstance(run_id, str)
```

- [ ] **Step 2: Run to confirm fail**

Run: `uv run pytest tests/briefs/test_loaders.py -v`
Expected: FAIL on board test.

- [ ] **Step 3: Modify `load_board_data`**

```python
# tools/briefs/data/board.py
from tools.briefs.pipeline_state import global_run_id

def load_board_data(quarter: str) -> tuple[BoardBriefData, str | None]:
    # ... existing body builds `brief` ...
    return brief, global_run_id()
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/briefs/test_loaders.py::test_load_board_data_returns_tuple -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/briefs/data/board.py tests/briefs/test_loaders.py
git commit -m "refactor(briefs): load_board_data returns (data, pipeline_run_id)"
```

---

## Task 9: `load_rsm_data` returns `(data, pipeline_run_id)`

**Files:**
- Modify: `tools/briefs/data/rsm.py`
- Modify: `tests/briefs/test_loaders.py`

- [ ] **Step 1: Update existing test(s)**

```python
def test_load_rsm_data_returns_tuple():
    data, run_id = load_rsm_data("med", week_of="2026-W17", narrate=False)
    assert data is not None
    assert run_id is None or isinstance(run_id, str)
```

- [ ] **Step 2: Run to confirm fail**

Expected: FAIL.

- [ ] **Step 3: Modify `load_rsm_data`**

```python
# tools/briefs/data/rsm.py
from tools.briefs.pipeline_state import region_run_id

def load_rsm_data(
    region: str,
    week_of: str | None = None,
    narrate: bool = False,
) -> tuple[RsmBrief, str | None]:
    # ... existing body builds `brief` ...
    return brief, region_run_id(region.lower())
```

- [ ] **Step 4: Update all call sites**

Find and update:
```bash
uv run python -c "import subprocess; subprocess.run(['grep', '-rn', 'load_rsm_data\\|load_ciso_data\\|load_board_data', 'tools/', 'server.py', 'tests/'])"
```

Known call sites to update:
- `tools/build_pdf.py` — `_load_data` helper unpacks tuple
- `server.py` — brief endpoints (to be deleted in Phase 4, but update temporarily so tests pass)
- any existing `tests/briefs/` files referencing these loaders

- [ ] **Step 5: Run all brief tests**

Run: `uv run pytest tests/briefs/ -v`
Expected: all green — 63 existing + new loader cases.

- [ ] **Step 6: Commit**

```bash
git add tools/briefs/data/rsm.py tests/briefs/test_loaders.py tools/build_pdf.py server.py
git commit -m "refactor(briefs): load_rsm_data returns (data, pipeline_run_id); update call sites"
```

---

## Task 10: Regional pipeline writes `run_id` to `meta.json`

**Files:**
- Modify: regional pipeline runner (path TBD — locate via `search_text pattern='last_run_log' repo='crq-agent-workspace'`)
- Create: `output/regional/{region}/meta.json` schema

- [ ] **Step 1: Locate the regional writer**

Run: `mcp__jcodemunch-mcp__search_text` with pattern `output/regional` in `tools/` to find the file that writes regional artifacts at run end.

- [ ] **Step 2: Write failing test**

Pick the regional runner module (expected: `tools/run_regional.py` or similar). Add a test that asserts after a mock run, `output/regional/med/meta.json` contains `{"run_id": ...}`.

If the regional runner is deeply coupled, scope this task to: add `write_region_meta(region, run_id)` helper in `tools/briefs/pipeline_state.py`, call it from the regional runner, and test the helper in isolation.

```python
# tests/briefs/test_pipeline_state.py — append
def test_write_region_meta_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_state, "REGIONAL_ROOT", tmp_path / "regional")
    pipeline_state.write_region_meta("med", "run-0412")
    assert pipeline_state.region_run_id("med") == "run-0412"
```

- [ ] **Step 3: Add helper + call site**

```python
# tools/briefs/pipeline_state.py — append
def write_region_meta(region: str, run_id: str) -> None:
    d = REGIONAL_ROOT / region.lower()
    d.mkdir(parents=True, exist_ok=True)
    meta_path = d / "meta.json"
    existing = _read_json(meta_path) or {}
    existing["run_id"] = run_id
    meta_path.write_text(json.dumps(existing, indent=2, sort_keys=True))
```

Then add a one-line call in the regional runner at end-of-run: `pipeline_state.write_region_meta(region, run_id)`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/briefs/test_pipeline_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/briefs/pipeline_state.py tests/briefs/test_pipeline_state.py tools/<regional_runner>.py
git commit -m "feat(pipeline): regional runs write run_id to output/regional/{region}/meta.json"
```

---

# Phase 3 — CLI integration

## Task 11: `build_pdf.py` — archive by default, `--no-archive` opt-out

**Files:**
- Modify: `tools/build_pdf.py`
- Modify: `tests/test_build_pdf.py` (create if absent)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_build_pdf.py
import subprocess
import sys
from pathlib import Path

def test_build_pdf_archives_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIEFS_RETENTION", "5")
    archive_root = tmp_path / "archive"
    # Run CLI with --mock; expect archive populated
    result = subprocess.run(
        [sys.executable, "-m", "tools.build_pdf",
         "--brief", "ciso", "--month", "2026-04", "--mock"],
        cwd=Path.cwd(),
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    # Check output/deliverables/archive/ciso has at least one version
    # (integration test — uses real paths; run in CI fresh)


def test_build_pdf_no_archive_flag(tmp_path):
    out = tmp_path / "ad_hoc.pdf"
    result = subprocess.run(
        [sys.executable, "-m", "tools.build_pdf",
         "--brief", "ciso", "--month", "2026-04", "--mock",
         "--out", str(out), "--no-archive"],
        cwd=Path.cwd(),
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert out.exists()
```

- [ ] **Step 2: Run to confirm fail**

Expected: FAIL — `--no-archive` not recognized; archive not written.

- [ ] **Step 3: Update `build_pdf.py`**

```python
# tools/build_pdf.py
import tempfile
from tools.briefs import storage

def _load_data(brief: str, args: argparse.Namespace):
    if brief == "board":
        from tools.briefs.data.board import load_board_data
        return load_board_data(args.quarter)  # tuple
    if brief == "ciso":
        from tools.briefs.data.ciso import load_ciso_data
        return load_ciso_data(args.month)
    if brief == "rsm":
        if args.mock:
            from tools.briefs.data._rsm_mock import rsm_med_w17_mock
            return rsm_med_w17_mock(), None
        from tools.briefs.data.rsm import load_rsm_data
        return load_rsm_data(args.region, args.week_of, narrate=args.narrate)
    raise SystemExit(f"unknown brief: {brief}")


def _audience_id(brief: str, region: str | None) -> str:
    if brief == "rsm":
        return f"rsm-{region.lower()}"
    return brief


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="build_pdf")
    p.add_argument("--brief", required=True, choices=BRIEFS)
    p.add_argument("--out", type=Path, help="Optional output path (for ad-hoc renders)")
    p.add_argument("--no-archive", action="store_true",
                   help="Skip archive; requires --out")
    # ... existing per-brief flags ...
    args = p.parse_args(argv)

    if args.no_archive and not args.out:
        raise SystemExit("--no-archive requires --out")

    data, pipeline_run_id = _load_data(args.brief, args)

    with tempfile.TemporaryDirectory() as td:
        tmp_pdf = Path(td) / "out.pdf"
        tmp_png = Path(td) / "out.png"
        asyncio.run(render_pdf(args.brief, data, tmp_pdf, thumbnail_path=tmp_png))

        if args.out:
            import shutil
            args.out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(tmp_pdf, args.out)

        if not args.no_archive:
            audience_id = _audience_id(args.brief, args.region)
            narrated = bool(getattr(args, "narrate", False))
            metadata = {}
            if args.brief == "rsm":
                metadata["region"] = args.region
                metadata["week_of"] = args.week_of
            elif args.brief == "ciso":
                metadata["month"] = args.month
            elif args.brief == "board":
                metadata["quarter"] = args.quarter
            storage.record_version(
                audience_id=audience_id,
                pdf_tmp_path=tmp_pdf,
                thumbnail_tmp_path=tmp_png,
                pipeline_run_id=pipeline_run_id,
                narrated=narrated,
                generated_by="cli",
                metadata=metadata,
            )
            print(f"archived {audience_id}")

    if args.out:
        print(f"wrote {args.out}")
    return 0
```

Note: `storage.record_version` moves the tmp files. If both `--out` and archive are requested, copy to `--out` FIRST (before record_version consumes them).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_build_pdf.py -v`
Expected: PASS.

Also: `uv run pytest tests/briefs/ -v`
Expected: 63 existing still pass.

- [ ] **Step 5: Commit**

```bash
git add tools/build_pdf.py tests/test_build_pdf.py
git commit -m "feat(cli): build_pdf archives by default; --no-archive opts out"
```

---

# Phase 4 — Server endpoints

## Task 12: Delete legacy endpoints

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Find the three legacy routes**

Run: `mcp__jcodemunch-mcp__search_text` with pattern `/api/briefs/(board|ciso|rsm)` in `server.py`.

- [ ] **Step 2: Delete them**

Remove:
- `GET /api/briefs/board/pdf`
- `GET /api/briefs/ciso/pdf`
- `GET /api/briefs/rsm/{region}/pdf`

Leave `_run_build_pdf` helper in place — Task 15 replaces it with an in-process call.

- [ ] **Step 3: Don't commit yet — new routes in Task 13/14/15**

---

## Task 13: `GET /api/briefs/` + `/meta` + `/versions`

**Files:**
- Modify: `server.py`
- Create: `tests/briefs/test_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/briefs/test_api.py
from fastapi.testclient import TestClient
from server import app  # or correct import path

client = TestClient(app)


def test_list_audiences_returns_all_seven():
    r = client.get("/api/briefs/")
    assert r.status_code == 200
    data = r.json()
    ids = {a["id"] for a in data}
    assert ids == {
        "ciso", "board",
        "rsm-apac", "rsm-ame", "rsm-latam", "rsm-med", "rsm-nce",
    }
    ciso = next(a for a in data if a["id"] == "ciso")
    assert "latest_meta" in ciso
    assert "versions" in ciso
    assert ciso["canNarrate"] is False
    rsm = next(a for a in data if a["id"] == "rsm-med")
    assert rsm["canNarrate"] is True


def test_meta_unknown_audience_returns_404():
    r = client.get("/api/briefs/unknown/meta")
    assert r.status_code == 404


def test_versions_empty_archive_returns_empty_list():
    # Requires archive to be empty for this audience (use tmp ARCHIVE_ROOT)
    r = client.get("/api/briefs/ciso/versions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
```

- [ ] **Step 2: Run to confirm fail**

Expected: FAIL — 404 on `/api/briefs/`.

- [ ] **Step 3: Implement routes**

```python
# server.py
from fastapi import HTTPException
from tools.briefs import storage, pipeline_state

AUDIENCE_IDS = ["ciso", "board", "rsm-apac", "rsm-ame", "rsm-latam", "rsm-med", "rsm-nce"]
AUDIENCE_TITLES = {
    "ciso": "CISO", "board": "Board",
    "rsm-apac": "RSM · APAC", "rsm-ame": "RSM · AME",
    "rsm-latam": "RSM · LATAM", "rsm-med": "RSM · MED", "rsm-nce": "RSM · NCE",
}


def _can_narrate(audience_id: str) -> bool:
    return audience_id.startswith("rsm-")


def _version_to_meta(rec: storage.VersionRecord, audience_id: str) -> dict:
    current = pipeline_state.current_run_id(audience_id)
    stale = (
        rec.pipeline_run_id is not None
        and current is not None
        and rec.pipeline_run_id != current
    )
    return {
        "version_ts": rec.version_ts,
        "pipeline_run_id": rec.pipeline_run_id,
        "narrated": rec.narrated,
        "generated_by": rec.generated_by,
        "stale": stale,
    }


@app.get("/api/briefs/")
def list_briefs():
    out = []
    for aid in AUDIENCE_IDS:
        versions = storage.list_versions(aid)
        versions_meta = [_version_to_meta(v, aid) for v in versions]
        # Only the top version gets the "stale" flag in display; prior versions force stale=false
        for i, vm in enumerate(versions_meta):
            if i > 0:
                vm["stale"] = False
        latest = versions_meta[0] if versions_meta else None
        out.append({
            "id": aid,
            "title": AUDIENCE_TITLES[aid],
            "canNarrate": _can_narrate(aid),
            "latest_meta": latest,
            "versions": versions_meta,
        })
    return out


@app.get("/api/briefs/{audience_id}/meta")
def get_meta(audience_id: str, version: str | None = None):
    if audience_id not in AUDIENCE_IDS:
        raise HTTPException(404, "unknown audience")
    if version is None:
        rec = storage.get_latest(audience_id)
    else:
        iso = storage.compact_to_iso(version)
        rec = storage.get_specific(audience_id, iso)
    if rec is None:
        raise HTTPException(404, "no version")
    return _version_to_meta(rec, audience_id)


@app.get("/api/briefs/{audience_id}/versions")
def get_versions(audience_id: str):
    if audience_id not in AUDIENCE_IDS:
        raise HTTPException(404, "unknown audience")
    versions = storage.list_versions(audience_id)
    metas = [_version_to_meta(v, audience_id) for v in versions]
    for i, m in enumerate(metas):
        if i > 0:
            m["stale"] = False
    return metas
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/briefs/test_api.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add server.py tests/briefs/test_api.py
git commit -m "feat(api): GET /api/briefs/ + /meta + /versions with stale computation"
```

---

## Task 14: `GET /api/briefs/{id}/pdf` + `/thumbnail` with `?version=`

**Files:**
- Modify: `server.py`
- Modify: `tests/briefs/test_api.py`

- [ ] **Step 1: Add failing tests**

```python
def test_get_pdf_latest(tmp_archive_with_ciso):
    r = client.get("/api/briefs/ciso/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" not in r.headers.get("content-disposition", "")


def test_get_pdf_download_has_human_filename(tmp_archive_with_ciso):
    r = client.get("/api/briefs/ciso/pdf?download=1")
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "ciso_" in cd  # human name, not compact timestamp


def test_get_pdf_specific_version(tmp_archive_with_ciso):
    # caller has two versions; pick older via ?version=
    r = client.get("/api/briefs/ciso/versions")
    older = r.json()[-1]["version_ts"]
    compact = older.replace("-", "").replace(":", "")
    r2 = client.get(f"/api/briefs/ciso/pdf?version={compact}")
    assert r2.status_code == 200


def test_get_pdf_unknown_version_404(tmp_archive_with_ciso):
    r = client.get("/api/briefs/ciso/pdf?version=20000101T000000Z")
    assert r.status_code == 404


def test_get_thumbnail_serves_png(tmp_archive_with_ciso):
    r = client.get("/api/briefs/ciso/thumbnail")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
```

(`tmp_archive_with_ciso` is a pytest fixture that monkeypatches `storage.ARCHIVE_ROOT` and seeds two fake versions. Add it at the top of the test file.)

- [ ] **Step 2: Run to confirm fail**

Expected: FAIL — routes don't exist.

- [ ] **Step 3: Implement routes**

```python
# server.py
from fastapi.responses import FileResponse


def _resolve_version(audience_id: str, version: str | None) -> storage.VersionRecord:
    if audience_id not in AUDIENCE_IDS:
        raise HTTPException(404, "unknown audience")
    if version is None:
        rec = storage.get_latest(audience_id)
    else:
        iso = storage.compact_to_iso(version)
        rec = storage.get_specific(audience_id, iso)
    if rec is None:
        raise HTTPException(404, "no version")
    return rec


def _human_filename(audience_id: str, version_ts: str, ext: str) -> str:
    # "2026-04-21T04:12:00Z" → "2026-04-21_0412"
    date_part = version_ts[:10]
    time_part = version_ts[11:13] + version_ts[14:16]
    return f"{audience_id}_{date_part}_{time_part}.{ext}"


@app.get("/api/briefs/{audience_id}/pdf")
def get_pdf(audience_id: str, version: str | None = None, download: int = 0):
    rec = _resolve_version(audience_id, version)
    headers = {}
    if download:
        fname = _human_filename(audience_id, rec.version_ts, "pdf")
        headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return FileResponse(rec.pdf_path, media_type="application/pdf", headers=headers)


@app.get("/api/briefs/{audience_id}/thumbnail")
def get_thumbnail(audience_id: str, version: str | None = None):
    rec = _resolve_version(audience_id, version)
    return FileResponse(rec.thumbnail_path, media_type="image/png")
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/briefs/test_api.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server.py tests/briefs/test_api.py
git commit -m "feat(api): /pdf + /thumbnail with ?version= + ?download=1 filename"
```

---

## Task 15: `POST /api/briefs/{id}/regenerate`

**Files:**
- Modify: `server.py`
- Modify: `tests/briefs/test_api.py`

- [ ] **Step 1: Add failing tests**

```python
def test_regenerate_creates_new_version(tmp_archive_with_ciso, monkeypatch):
    # monkeypatch render_pdf to write tiny files, skip Playwright
    async def fake_render(brief, data, pdf, thumbnail_path=None):
        pdf.write_bytes(b"%PDF-fake")
        if thumbnail_path:
            thumbnail_path.write_bytes(b"\x89PNG-fake")
    monkeypatch.setattr("tools.briefs.renderer.render_pdf", fake_render)

    before = len(client.get("/api/briefs/ciso/versions").json())
    r = client.post("/api/briefs/ciso/regenerate", json={})
    assert r.status_code == 200
    body = r.json()
    assert "new_version" in body
    assert "versions" in body

    after = len(client.get("/api/briefs/ciso/versions").json())
    assert after == before + 1


def test_regenerate_rsm_with_narrate(tmp_archive_with_rsm_med, monkeypatch):
    captured = {}
    async def fake_render(brief, data, pdf, thumbnail_path=None):
        pdf.write_bytes(b"%PDF"); thumbnail_path.write_bytes(b"\x89PNG")
    def fake_load(region, week_of=None, narrate=False):
        captured["narrate"] = narrate
        # return minimal RsmBrief + run_id — use mock
        from tools.briefs.data._rsm_mock import rsm_med_w17_mock
        return rsm_med_w17_mock(), None
    monkeypatch.setattr("tools.briefs.renderer.render_pdf", fake_render)
    monkeypatch.setattr("tools.briefs.data.rsm.load_rsm_data", fake_load)

    r = client.post("/api/briefs/rsm-med/regenerate", json={"narrate": True})
    assert r.status_code == 200
    assert captured["narrate"] is True
    latest = client.get("/api/briefs/rsm-med/meta").json()
    assert latest["narrated"] is True


def test_regenerate_unknown_audience_404():
    r = client.post("/api/briefs/unknown/regenerate", json={})
    assert r.status_code == 404
```

- [ ] **Step 2: Run to confirm fail**

Expected: FAIL.

- [ ] **Step 3: Implement route**

```python
# server.py
import asyncio, tempfile
from pathlib import Path
from tools.briefs.renderer import render_pdf


def _default_period_for(audience_id: str) -> dict:
    """Return the default period args for a given audience (today-based)."""
    from datetime import date
    today = date.today()
    if audience_id == "ciso":
        return {"month": today.strftime("%Y-%m")}
    if audience_id == "board":
        q = (today.month - 1) // 3 + 1
        return {"quarter": f"{today.year}Q{q}"}
    # rsm
    return {"region": audience_id.removeprefix("rsm-").upper(), "week_of": None}


@app.post("/api/briefs/{audience_id}/regenerate")
async def regenerate(audience_id: str, body: dict | None = None):
    if audience_id not in AUDIENCE_IDS:
        raise HTTPException(404, "unknown audience")
    body = body or {}
    narrate = bool(body.get("narrate", False))
    period = _default_period_for(audience_id)

    if audience_id == "ciso":
        from tools.briefs.data.ciso import load_ciso_data
        data, run_id = load_ciso_data(period["month"])
        brief_kind = "ciso"
        metadata = {"month": period["month"]}
    elif audience_id == "board":
        from tools.briefs.data.board import load_board_data
        data, run_id = load_board_data(period["quarter"])
        brief_kind = "board"
        metadata = {"quarter": period["quarter"]}
    else:
        from tools.briefs.data.rsm import load_rsm_data
        data, run_id = load_rsm_data(period["region"], period["week_of"], narrate=narrate)
        brief_kind = "rsm"
        metadata = {"region": period["region"], "week_of": period["week_of"]}

    with tempfile.TemporaryDirectory() as td:
        tmp_pdf = Path(td) / "out.pdf"
        tmp_png = Path(td) / "out.png"
        try:
            await render_pdf(brief_kind, data, tmp_pdf, thumbnail_path=tmp_png)
        except Exception as exc:
            raise HTTPException(500, f"render failed: {exc}")

        new_rec = storage.record_version(
            audience_id=audience_id,
            pdf_tmp_path=tmp_pdf,
            thumbnail_tmp_path=tmp_png,
            pipeline_run_id=run_id,
            narrated=narrate,
            generated_by="api",
            metadata=metadata,
        )

    versions = storage.list_versions(audience_id)
    versions_meta = [_version_to_meta(v, audience_id) for v in versions]
    for i, m in enumerate(versions_meta):
        if i > 0:
            m["stale"] = False

    return {
        "new_version": _version_to_meta(new_rec, audience_id),
        "versions": versions_meta,
    }
```

- [ ] **Step 4: Wire startup sweep**

```python
# server.py — alongside @app.on_event("startup") or a lifespan handler
@app.on_event("startup")
def _sweep_orphans_on_startup():
    for aid in AUDIENCE_IDS:
        storage.sweep_orphans(aid)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/briefs/test_api.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add server.py tests/briefs/test_api.py
git commit -m "feat(api): POST /api/briefs/{id}/regenerate + startup orphan sweep"
```

---

# Phase 5 — Client UI

## Task 16: Delete old Reports JS + CSS

**Files:**
- Modify: `static/app.js`
- Modify: `static/index.html`

- [ ] **Step 1: Find all symbols to remove**

Run: `mcp__jcodemunch-mcp__search_symbols` for: `renderCisoView`, `renderBoardGlobalView`, `renderBoardRegionalView`, `renderRsmInReports`, `_hubGenerate`, `renderReportsRail`, `renderAudienceContent`, `selectAudience`, `renderReports`.

- [ ] **Step 2: Delete each function body from `static/app.js`**

Delete:
- `renderCisoView`, `renderBoardGlobalView`, `renderBoardRegionalView`, `renderRsmInReports`, `_hubGenerate`
- `renderReportsRail`, `renderAudienceContent`, `selectAudience`, current `renderReports`
- Any private helpers that become unreferenced (confirm via search before deleting).

- [ ] **Step 3: Delete rail-era CSS from `static/index.html`**

Remove classes: `.rpt-shell`, `.rpt-rail`, `.rpt-rail-*`, `.rpt-live-badge`, `.rpt-plan-badge`, `.rpt-content`, `.rpt-action-bar*`, `.rpt-section*`, `.rpt-cards` (existing — will be re-added cleanly in Task 18), `.rpt-card*` (existing), `.rpt-decision*`, `.rpt-tp*`, `.rpt-watch*`, `.rpt-region-selector`, `.rpt-region-btn*`.

- [ ] **Step 4: Reduce `AUDIENCE_REGISTRY` to a minimal client fallback**

Drop fields: `renderer`, `generate`, `subviews`, `sales`. Keep `id`, `title`, `canNarrate` as a schema hint only — actual data comes from `GET /api/briefs/`.

- [ ] **Step 5: Confirm nothing else references deleted symbols**

Run: `mcp__jcodemunch-mcp__search_text pattern='renderCisoView|renderBoardGlobalView|renderRsmInReports|_hubGenerate'`
Expected: no hits.

- [ ] **Step 6: Commit**

```bash
git add static/app.js static/index.html
git commit -m "refactor(ui): delete legacy Reports rail + in-browser brief renderers"
```

---

## Task 17: Add card grid CSS

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Add CSS block**

Inside the `<style>` block in `static/index.html`, add:

```css
.rpt-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
  padding: 16px;
}

.rpt-audience-card {
  background: var(--card-bg, #fff);
  border: 1px solid var(--card-border, #e1e4e8);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.rpt-thumb {
  width: 100%;
  aspect-ratio: 210 / 297;  /* A4 */
  background: #f5f5f5;
  object-fit: cover;
  display: block;
}

.rpt-thumb-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #888;
  font-size: 13px;
}

.rpt-card-body {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rpt-card-title {
  font-weight: 600;
  font-size: 14px;
}

.rpt-freshness {
  font-size: 12px;
  color: #555;
  cursor: pointer;
  user-select: none;
}

.rpt-freshness:hover {
  text-decoration: underline;
}

.rpt-stale-badge {
  display: inline-block;
  background: #ffd666;
  color: #664d03;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  margin-left: 6px;
}

.rpt-actions {
  display: flex;
  gap: 6px;
  padding: 8px 12px 12px;
  flex-wrap: wrap;
}

.rpt-card-btn {
  background: #f0f1f4;
  border: 1px solid #d1d5db;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  text-decoration: none;
  color: #222;
}

.rpt-card-btn:hover { background: #e6e8ec; }
.rpt-card-btn:disabled, .rpt-card-btn[aria-disabled="true"] {
  opacity: 0.5; cursor: not-allowed;
}

.rpt-error-strip {
  border-left: 3px solid #d73a49;
  background: #fff5f5;
  padding: 8px 12px;
  font-size: 12px;
  color: #a40e0e;
  display: flex;
  justify-content: space-between;
}

.rpt-version-menu {
  position: absolute;
  background: #fff;
  border: 1px solid #ccc;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  z-index: 10;
  min-width: 220px;
}

.rpt-version-row {
  padding: 6px 10px;
  cursor: pointer;
  font-size: 12px;
}

.rpt-version-row:hover { background: #f0f1f4; }

.rpt-subheader {
  font-size: 13px;
  font-weight: 600;
  color: #555;
  padding: 8px 16px 0;
  grid-column: 1 / -1;
}
```

- [ ] **Step 2: Commit**

```bash
git add static/index.html
git commit -m "style(reports): card grid CSS"
```

---

## Task 18: New `renderReports` — card builder with safe DOM methods

**Files:**
- Modify: `static/app.js`

This task uses `document.createElement`, `element.textContent`, `element.appendChild`, `element.setAttribute`, and `element.classList.add` — no `innerHTML` or `outerHTML` anywhere.

- [ ] **Step 1: Write the new render module**

Append to `static/app.js`:

```javascript
// --- Reports tab: card grid renderer ---

const RSM_AUDIENCE_IDS = ["rsm-apac", "rsm-ame", "rsm-latam", "rsm-med", "rsm-nce"];

function formatRelative(isoUtc) {
  if (!isoUtc) return "";
  const then = new Date(isoUtc);
  const now = new Date();
  const hh = String(then.getUTCHours()).padStart(2, "0");
  const mm = String(then.getUTCMinutes()).padStart(2, "0");
  const timeStr = hh + ":" + mm + " UTC";
  const thenDay = then.toISOString().slice(0, 10);
  const nowDay = now.toISOString().slice(0, 10);
  if (thenDay === nowDay) return "Today · " + timeStr;
  const yest = new Date(now.getTime() - 86400000).toISOString().slice(0, 10);
  if (thenDay === yest) return "Yesterday · " + timeStr;
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const label = months[then.getUTCMonth()] + " " + String(then.getUTCDate()).padStart(2, "0");
  return label + " · " + timeStr;
}

function isoToCompact(iso) {
  return iso.replace(/[-:]/g, "");
}

function el(tag, opts) {
  const e = document.createElement(tag);
  if (!opts) return e;
  if (opts.text !== undefined) e.textContent = opts.text;
  if (opts.cls) {
    (Array.isArray(opts.cls) ? opts.cls : [opts.cls]).forEach(c => e.classList.add(c));
  }
  if (opts.attrs) {
    for (const k of Object.keys(opts.attrs)) e.setAttribute(k, opts.attrs[k]);
  }
  return e;
}

function buildThumbnail(audienceId, viewingTs) {
  if (!viewingTs) {
    return el("div", { cls: ["rpt-thumb", "rpt-thumb-placeholder"], text: "No brief yet" });
  }
  const compact = isoToCompact(viewingTs);
  const img = el("img", {
    cls: "rpt-thumb",
    attrs: {
      src: "/api/briefs/" + audienceId + "/thumbnail?version=" + compact,
      alt: audienceId + " cover thumbnail",
      loading: "lazy",
    },
  });
  return img;
}

function buildFreshnessLabel(latestMeta, viewingIsLatest, onToggle) {
  const label = el("span", { cls: "rpt-freshness" });
  if (!latestMeta) {
    label.textContent = "";
    return label;
  }
  const prefix = viewingIsLatest ? "Latest · " : "";
  label.textContent = prefix + formatRelative(latestMeta.version_ts) + " ▾";
  label.addEventListener("click", onToggle);
  return label;
}

function buildStaleBadge() {
  return el("span", { cls: "rpt-stale-badge", text: "⚠ Stale" });
}

function buildActionBar(audienceId, viewingTs, canNarrate, canActions, handlers) {
  const bar = el("div", { cls: "rpt-actions" });
  const compact = viewingTs ? isoToCompact(viewingTs) : "";

  const preview = el("a", {
    cls: "rpt-card-btn",
    text: "Preview",
    attrs: {
      href: viewingTs ? "/api/briefs/" + audienceId + "/pdf?version=" + compact : "#",
      target: "_blank",
      rel: "noopener",
    },
  });
  if (!viewingTs) preview.setAttribute("aria-disabled", "true");
  bar.appendChild(preview);

  const regen = el("button", { cls: "rpt-card-btn", text: "Regenerate" });
  regen.disabled = !canActions;
  regen.addEventListener("click", handlers.onRegenerate);
  bar.appendChild(regen);

  if (canNarrate) {
    const narrate = el("button", { cls: "rpt-card-btn", text: "Narrate" });
    narrate.disabled = !canActions;
    narrate.addEventListener("click", handlers.onNarrate);
    bar.appendChild(narrate);
  }

  const download = el("a", {
    cls: "rpt-card-btn",
    text: "Download",
    attrs: {
      href: viewingTs ? "/api/briefs/" + audienceId + "/pdf?version=" + compact + "&download=1" : "#",
      download: "",
    },
  });
  if (!viewingTs) download.setAttribute("aria-disabled", "true");
  bar.appendChild(download);

  return bar;
}

function buildVersionMenu(audience, onSelect) {
  const menu = el("div", { cls: "rpt-version-menu" });
  audience.versions.forEach((v, idx) => {
    const row = el("div", { cls: "rpt-version-row" });
    const labelText = (idx === 0 ? "Latest · " : "") + formatRelative(v.version_ts)
      + (v.narrated ? " · narrated" : "");
    row.textContent = labelText;
    row.addEventListener("click", () => onSelect(v.version_ts));
    menu.appendChild(row);
  });
  return menu;
}

function buildErrorStrip(message, onDismiss) {
  const strip = el("div", { cls: "rpt-error-strip" });
  const msg = el("span", { text: message });
  strip.appendChild(msg);
  const close = el("button", { cls: "rpt-card-btn", text: "×" });
  close.addEventListener("click", onDismiss);
  strip.appendChild(close);
  return strip;
}

// Per-card state: { audienceId -> { viewingTs, menuOpen, error, inFlight } }
const reportCardState = new Map();

function buildAudienceCard(audience) {
  const state = reportCardState.get(audience.id) || {
    viewingTs: audience.latest_meta ? audience.latest_meta.version_ts : null,
    menuOpen: false,
    error: null,
    inFlight: false,
  };
  reportCardState.set(audience.id, state);

  const card = el("div", { cls: "rpt-audience-card" });
  card.setAttribute("data-audience-id", audience.id);

  // Thumbnail
  card.appendChild(buildThumbnail(audience.id, state.viewingTs));

  // Body (title + freshness)
  const body = el("div", { cls: "rpt-card-body" });
  body.appendChild(el("div", { cls: "rpt-card-title", text: audience.title }));

  const viewingIsLatest = audience.latest_meta &&
    state.viewingTs === audience.latest_meta.version_ts;

  const freshnessWrap = el("div");
  const viewingMeta = audience.versions.find(v => v.version_ts === state.viewingTs) || audience.latest_meta;
  freshnessWrap.appendChild(buildFreshnessLabel(viewingMeta, viewingIsLatest, () => {
    state.menuOpen = !state.menuOpen;
    rerenderCard(audience);
  }));
  if (viewingIsLatest && audience.latest_meta && audience.latest_meta.stale) {
    freshnessWrap.appendChild(buildStaleBadge());
  }
  body.appendChild(freshnessWrap);

  if (state.menuOpen && audience.versions.length > 0) {
    body.appendChild(buildVersionMenu(audience, (ts) => {
      state.viewingTs = ts;
      state.menuOpen = false;
      rerenderCard(audience);
    }));
  }

  card.appendChild(body);

  // Actions
  const canActions = !state.inFlight && audience.versions.length >= 0;
  card.appendChild(buildActionBar(
    audience.id,
    state.viewingTs,
    audience.canNarrate,
    !state.inFlight,
    {
      onRegenerate: () => triggerRegenerate(audience, false),
      onNarrate: () => triggerRegenerate(audience, true),
    },
  ));

  if (state.error) {
    card.appendChild(buildErrorStrip(state.error, () => {
      state.error = null;
      rerenderCard(audience);
    }));
  }

  return card;
}

function rerenderCard(audience) {
  const existing = document.querySelector('[data-audience-id="' + audience.id + '"]');
  if (!existing) return;
  const fresh = buildAudienceCard(audience);
  existing.replaceWith(fresh);
}

async function triggerRegenerate(audience, narrate) {
  const state = reportCardState.get(audience.id);
  state.inFlight = true;
  state.error = null;
  rerenderCard(audience);

  try {
    const resp = await fetch("/api/briefs/" + audience.id + "/regenerate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ narrate: !!narrate }),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(resp.status + ": " + text.slice(0, 200));
    }
    const body = await resp.json();
    audience.versions = body.versions;
    audience.latest_meta = body.new_version;
    state.viewingTs = body.new_version.version_ts;
  } catch (err) {
    state.error = err.message;
  } finally {
    state.inFlight = false;
    rerenderCard(audience);
  }
}

async function renderReports() {
  const container = document.getElementById("tab-reports");
  while (container.firstChild) container.removeChild(container.firstChild);

  const grid = el("div", { cls: "rpt-grid" });

  let audiences;
  try {
    const resp = await fetch("/api/briefs/");
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    audiences = await resp.json();
  } catch (err) {
    grid.appendChild(el("div", { text: "Failed to load briefs: " + err.message }));
    container.appendChild(grid);
    return;
  }

  // Top row: CISO + Board
  for (const a of audiences.filter(x => !x.id.startsWith("rsm-"))) {
    grid.appendChild(buildAudienceCard(a));
  }
  // Subheader
  grid.appendChild(el("div", { cls: "rpt-subheader", text: "RSM — 5 regions" }));
  // RSM row
  for (const a of audiences.filter(x => RSM_AUDIENCE_IDS.includes(x.id))) {
    grid.appendChild(buildAudienceCard(a));
  }

  container.appendChild(grid);
}
```

- [ ] **Step 2: Wire `renderReports` to the tab switcher**

Find the tab-switching code (likely a function like `showTab` or similar). When the Reports tab becomes active, call `renderReports()`.

- [ ] **Step 3: Manual smoke test**

Start server: `uv run python server.py` (port 8001).
Open `http://localhost:8001/`. Switch to Reports tab. Expect: card grid renders 7 cards, thumbnails load from API, Preview opens PDF in new tab, Regenerate triggers POST and card refreshes.

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): card grid Reports tab using safe DOM methods"
```

---

# Phase 6 — Acceptance

## Task 19: Manual acceptance + full test run

- [ ] **Step 1: Run entire test suite**

Run: `uv run pytest tests/ -v`
Expected: all green. Baseline was 63 briefs tests + existing suite. New: ~15 storage + 5 pipeline_state + ~12 API + 2 build_pdf ≈ 34 new.

- [ ] **Step 2: Manual acceptance walkthrough**

Per the spec's checklist:
1. Reports tab mounts, 7 cards render with thumbnails + freshness.
2. Preview button opens PDF in a new browser tab (native viewer).
3. Regenerate on CISO — thumbnail refreshes, VersionMenu grows.
4. Narrate visible only on RSM cards.
5. VersionMenu expand → select prior version → thumbnail swaps, Preview/Download repoint.
6. Stale badge shows on Latest after pipeline run id advances; regenerate clears it.
7. Regenerate on audience with no pipeline data → error strip visible.
8. With `BRIEFS_RETENTION=5`, 6th regenerate prunes oldest (`ls output/deliverables/archive/ciso/`).

- [ ] **Step 3: Confirm `output/deliverables/archive/` is gitignored**

Run: `git check-ignore output/deliverables/archive/ciso/test.pdf`
Expected: matches `.gitignore` rule (should already — `output/` is gitignored).

- [ ] **Step 4: Final commit — tag the milestone**

```bash
git add .
git commit -m "feat(reports): card grid launcher v1 complete — archive + versions + stale detection"
git tag reports-v1
```

---

# Self-Review Checklist (run after plan written)

- [x] Every task shows exact file paths, failing test, minimal impl, test command, commit message.
- [x] No `innerHTML` / `outerHTML` anywhere in Task 18's JS — all DOM construction via `createElement` / `textContent` / `appendChild` / `replaceWith`.
- [x] Type consistency: `VersionRecord` fields in Task 2 match references in Tasks 3, 4, 13, 14, 15.
- [x] Loader return signatures match across Tasks 7, 8, 9, and their use in Task 11 (build_pdf) + Task 15 (regenerate).
- [x] `_version_to_meta` is defined in Task 13 and reused in Tasks 14, 15 without redefinition.
- [x] Spec coverage: every spec section maps to at least one task —
  - Storage & archive → Tasks 2–5
  - Pipeline run ID plumbing → Tasks 1, 7, 8, 9, 10
  - Renderer thumbnail → Task 6
  - API endpoints → Tasks 12–15
  - Client card grid → Tasks 16–18
  - Manual acceptance → Task 19
- [x] Retention via env var (`BRIEFS_RETENTION`) read once at module import — Task 2.
- [x] Sidecar-last write ordering + `sweep_orphans` — Tasks 3, 4.
- [x] Stale detection in server layer, never on prior versions, never when `pipeline_run_id=null` — Task 13.
- [x] Download filename via `Content-Disposition` — Task 14.

---

# Handoff

After the user reviews and approves this plan, orchestrator proceeds to `TeamCreate`. Execution pattern is fixed:

```
TeamCreate → Builders (Sonnet, no Bash) → Validator (Sonnet, read-only) → TeamDelete
```

Per memory: after writing-plans, stop for user review — do NOT auto-execute.
