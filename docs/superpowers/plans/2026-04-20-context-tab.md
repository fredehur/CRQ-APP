# Context Tab Implementation Plan

**Goal:** Ship a new `Context` top-level tab that lets RSMs edit company profile, sites, and cyber watchlists through a region-first UI backed by existing JSON files; retire the Config -> Footprint sub-tab.

**Architecture:** FastAPI endpoints under `/api/context/*` with atomic tmp-file-swap writes and PUT-replace semantics. Plain-JS frontend in `static/app.js` + `static/index.html`, following the existing pattern (no framework). Two reusable UI primitives (Tag List, Record List) defined once and used by every surface.

**Tech Stack:** Python 3.12 / FastAPI / pytest (`fastapi.testclient.TestClient`); vanilla JavaScript + Tailwind CDN; JSON files under `data/`.

**Spec:** `docs/superpowers/specs/2026-04-20-context-tab-design.md`

---

## File structure

### Backend
- Modify: `server.py` — add 8 endpoints under `/api/context/*`; remove the 2 `/api/footprint` endpoints in a later task.
- Create: `tools/context_api.py` — pure helpers for shape validation, headcount derivation, alias double-write. Keeps handlers thin and testable without TestClient.

### Frontend
- Modify: `static/index.html` — add nav button, tab panel markup, region strip, four surface containers.
- Modify: `static/app.js` — add `contextState`, `switchTab` case, loader/renderer per surface, Tag List + Record List utilities, dirty-state guard.

### Tests
- Create: `tests/test_context_api.py` — one test per endpoint plus shape validation.

### Docs
- Create: `docs/context-flow-matrix.md` — agent x field matrix.

---

## Task sequence

Backend endpoints (Tasks 1-8) are independent and can run in parallel once Task 0 lands. Frontend tasks (9-16) build incrementally on each other in-file so they must be sequential. Tasks 17-19 are cleanup + docs.

### Note on the frontend DOM-update pattern

Tasks 9-16 use `element.innerHTML` assignments with `esc()` for escaping. This matches the existing codebase (see `renderFootprint`, `renderTopicsTable`, `renderHistory`, etc. in `static/app.js`). Do not change this to textContent / DOM-creation methods — it breaks consistency with the other ~20 surfaces in the app. All user-provided strings are passed through `esc()`, the existing HTML-escape utility.

---

### Task 0: Scaffold helper module + test file

**Files:**
- Create: `tools/context_api.py`
- Create: `tests/test_context_api.py`

- [ ] **Step 1: Create the helper module with shared utilities.** Write this to `tools/context_api.py`:

```python
"""Pure helpers for the Context tab API - no FastAPI imports."""
from pathlib import Path
import json
from typing import Any


def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically via tmp-file swap."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
```

- [ ] **Step 2: Create the test file with the shared fixture.** Write this to `tests/test_context_api.py`:

```python
import json
from pathlib import Path

import pytest
import server
from fastapi.testclient import TestClient

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    """Redirect server.BASE to tmp_path and seed representative files."""
    data = tmp_path / "data"
    data.mkdir()

    (data / "company_profile.json").write_text(json.dumps({
        "name": "AeroGrid",
        "employee_count": 30000,
        "sectors": ["wind"],
        "countries_of_operation": ["DK", "DE"],
        "risk_appetite": "moderate",
        "strategic_priorities": "offshore expansion",
    }), encoding="utf-8")

    (data / "aerowind_sites.json").write_text(json.dumps({
        "sites": [
            {
                "site_id": "apac-kaohsiung-mfg", "name": "Kaohsiung", "region": "APAC",
                "country": "TW", "lat": 22.62, "lon": 120.30, "type": "manufacturing",
                "subtype": "assembly", "poi_radius_km": 50,
                "personnel_count": 320, "expat_count": 18, "shift_pattern": "24/7",
                "criticality": "crown_jewel", "tier": "crown_jewel",
                "produces": "blades", "dependencies": [], "feeds_into": [],
                "customer_dependencies": [], "previous_incidents": [], "notable_dates": [],
                "site_lead": {"name": "A", "phone": "1"},
                "duty_officer": {"name": "B", "phone": "2"},
                "embassy_contact": {"country_of_origin": "DK", "contact": "c", "phone": "3"},
            },
            {
                "site_id": "ame-houston-ops", "name": "Houston", "region": "AME",
                "country": "US", "lat": 29.76, "lon": -95.37, "type": "service",
                "subtype": "ops", "poi_radius_km": 30,
                "personnel_count": 180, "expat_count": 5, "shift_pattern": "two",
                "criticality": "major", "tier": "primary",
                "produces": "service", "dependencies": [], "feeds_into": [],
                "customer_dependencies": [], "previous_incidents": [], "notable_dates": [],
                "site_lead": {"name": "D", "phone": "4"},
                "duty_officer": {"name": "E", "phone": "5"},
                "embassy_contact": {"country_of_origin": "DK", "contact": "f", "phone": "6"},
            },
        ]
    }), encoding="utf-8")

    (data / "regional_footprint.json").write_text(json.dumps({
        "APAC": {"summary": "APAC primary", "headcount": 3200, "notes": "", "stakeholders": []},
        "AME":  {"summary": "AME ops",      "headcount": 2100, "notes": "", "stakeholders": []},
    }), encoding="utf-8")

    monkeypatch.setattr(server, "BASE", tmp_path)
    yield tmp_path
```

- [ ] **Step 3: Verify module imports.** Run: `uv run python -c "import tools.context_api; print('ok')"` Expected: `ok`.

- [ ] **Step 4: Verify pytest collects the empty file.** Run: `uv run pytest tests/test_context_api.py -v` Expected: `collected 0 items` (exit 5).

- [ ] **Step 5: Commit.**

```bash
git add tools/context_api.py tests/test_context_api.py
git commit -m "feat(context): scaffold context_api helper + test file"
```

---

### Task 1: GET /api/context/company

**Files:** `server.py` (add endpoint before `/api/trends`, around line 432), `tests/test_context_api.py`.

- [ ] **Step 1: Write the failing test.** Append to `tests/test_context_api.py`:

```python
def test_get_company_returns_document():
    r = client.get("/api/context/company")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "AeroGrid"
    assert body["employee_count"] == 30000
    assert body["sectors"] == ["wind"]
```

- [ ] **Step 2: Verify it fails (404).** Run: `uv run pytest tests/test_context_api.py::test_get_company_returns_document -v`

- [ ] **Step 3: Add the endpoint in `server.py`:**

```python
@app.get("/api/context/company")
async def get_context_company():
    path = BASE / "data" / "company_profile.json"
    if not path.exists():
        return JSONResponse({"error": "company_profile.json not found"}, status_code=500)
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Verify pass.** Run: `uv run pytest tests/test_context_api.py::test_get_company_returns_document -v`

- [ ] **Step 5: Commit.**

```bash
git add server.py tests/test_context_api.py
git commit -m "feat(context): GET /api/context/company"
```

---

### Task 2: PUT /api/context/company

**Files:** `server.py`, `tests/test_context_api.py`.

- [ ] **Step 1: Write the failing test.**

```python
def test_put_company_full_replace(tmp_data):
    new_doc = {
        "name": "AeroGrid 2",
        "employee_count": 31000,
        "sectors": ["wind", "solar"],
        "countries_of_operation": ["DK"],
        "risk_appetite": "high",
        "strategic_priorities": "solar expansion",
    }
    r = client.put("/api/context/company", json=new_doc)
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    saved = json.loads((tmp_data / "data" / "company_profile.json").read_text())
    assert saved == new_doc
```

- [ ] **Step 2: Verify fails (405).** Run: `uv run pytest tests/test_context_api.py::test_put_company_full_replace -v`

- [ ] **Step 3: Add the endpoint.**

```python
@app.put("/api/context/company")
async def put_context_company(body: dict):
    from tools.context_api import atomic_write_json
    path = BASE / "data" / "company_profile.json"
    atomic_write_json(path, body)
    return {"ok": True}
```

- [ ] **Step 4: Verify pass.** Run: `uv run pytest tests/test_context_api.py::test_put_company_full_replace -v`

- [ ] **Step 5: Commit.**

```bash
git add server.py tests/test_context_api.py
git commit -m "feat(context): PUT /api/context/company (full replace)"
```

---

### Task 3: GET /api/context/cyber-watchlist (with empty scaffold fallback)

**Files:** `server.py`, `tools/context_api.py`, `tests/test_context_api.py`.

- [ ] **Step 1: Add scaffold helper to `tools/context_api.py`:**

```python
def empty_cyber_watchlist() -> dict:
    """Return the empty scaffold used when cyber_watchlist.json does not exist."""
    return {
        "threat_actor_groups": [],
        "sector_targeting_campaigns": [],
        "cve_watch_categories": [],
        "global_cyber_geographies_of_concern": [],
    }
```

- [ ] **Step 2: Write two failing tests.**

```python
def test_get_cyber_watchlist_empty_scaffold_when_missing():
    r = client.get("/api/context/cyber-watchlist")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "threat_actor_groups": [],
        "sector_targeting_campaigns": [],
        "cve_watch_categories": [],
        "global_cyber_geographies_of_concern": [],
    }


def test_get_cyber_watchlist_returns_file_when_present(tmp_data):
    doc = {
        "threat_actor_groups": [{"name": "Volt Typhoon", "aliases": ["APT40"], "motivation": "espionage",
                                  "target_sectors": ["energy"], "target_geographies": ["US", "TW"]}],
        "sector_targeting_campaigns": [],
        "cve_watch_categories": ["OT/ICS"],
        "global_cyber_geographies_of_concern": ["CN"],
    }
    (tmp_data / "data" / "cyber_watchlist.json").write_text(json.dumps(doc), encoding="utf-8")
    r = client.get("/api/context/cyber-watchlist")
    assert r.status_code == 200
    assert r.json() == doc
```

- [ ] **Step 3: Verify both fail (404).** Run: `uv run pytest tests/test_context_api.py -k cyber_watchlist -v`

- [ ] **Step 4: Add endpoint in `server.py`.**

```python
@app.get("/api/context/cyber-watchlist")
async def get_context_cyber_watchlist():
    from tools.context_api import empty_cyber_watchlist
    path = BASE / "data" / "cyber_watchlist.json"
    if not path.exists():
        return empty_cyber_watchlist()
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 5: Verify pass.** Run: `uv run pytest tests/test_context_api.py -k cyber_watchlist -v`

- [ ] **Step 6: Commit.**

```bash
git add server.py tools/context_api.py tests/test_context_api.py
git commit -m "feat(context): GET /api/context/cyber-watchlist with empty scaffold"
```

---

### Task 4: PUT /api/context/cyber-watchlist

**Files:** `server.py`, `tests/test_context_api.py`.

- [ ] **Step 1: Write the failing test.**

```python
def test_put_cyber_watchlist_creates_file_if_missing(tmp_data):
    doc = {
        "threat_actor_groups": [],
        "sector_targeting_campaigns": [{"campaign_name": "Dragonfly", "actor": "Energetic Bear",
                                         "sectors": ["energy"], "first_observed": "2020", "status": "active"}],
        "cve_watch_categories": ["SCADA"],
        "global_cyber_geographies_of_concern": [],
    }
    assert not (tmp_data / "data" / "cyber_watchlist.json").exists()
    r = client.put("/api/context/cyber-watchlist", json=doc)
    assert r.status_code == 200
    saved = json.loads((tmp_data / "data" / "cyber_watchlist.json").read_text())
    assert saved == doc
```

- [ ] **Step 2: Verify fails (405).** Run: `uv run pytest tests/test_context_api.py::test_put_cyber_watchlist_creates_file_if_missing -v`

- [ ] **Step 3: Add endpoint.**

```python
@app.put("/api/context/cyber-watchlist")
async def put_context_cyber_watchlist(body: dict):
    from tools.context_api import atomic_write_json
    path = BASE / "data" / "cyber_watchlist.json"
    atomic_write_json(path, body)
    return {"ok": True}
```

- [ ] **Step 4: Verify pass.** Run: `uv run pytest tests/test_context_api.py::test_put_cyber_watchlist_creates_file_if_missing -v`

- [ ] **Step 5: Commit.**

```bash
git add server.py tests/test_context_api.py
git commit -m "feat(context): PUT /api/context/cyber-watchlist"
```

---

### Task 5: GET /api/context/sites?region=X (filtered)

**Files:** `server.py`, `tests/test_context_api.py`.

- [ ] **Step 1: Write three failing tests — valid region, missing region, unknown region.**

```python
def test_get_sites_filtered_by_region():
    r = client.get("/api/context/sites?region=APAC")
    assert r.status_code == 200
    body = r.json()
    assert "sites" in body
    site_ids = [s["site_id"] for s in body["sites"]]
    assert "apac-kaohsiung-mfg" in site_ids
    # Other regions' sites must not leak in
    assert all(s["region"] == "APAC" for s in body["sites"])


def test_get_sites_missing_region_returns_400():
    r = client.get("/api/context/sites")
    assert r.status_code == 400


def test_get_sites_unknown_region_returns_400():
    r = client.get("/api/context/sites?region=ZZZ")
    assert r.status_code == 400
```

- [ ] **Step 2: Verify fail.** Run: `uv run pytest tests/test_context_api.py -k get_sites -v`

- [ ] **Step 3: Add endpoint in `server.py`.**

```python
@app.get("/api/context/sites")
async def get_context_sites(region: str = Query(None)):
    if not region:
        return JSONResponse({"error": "region query param required"}, status_code=400)
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=400)
    path = BASE / "data" / "aerowind_sites.json"
    if not path.exists():
        return {"sites": []}
    doc = json.loads(path.read_text(encoding="utf-8"))
    sites = [s for s in doc.get("sites", []) if s.get("region") == r]
    return {"sites": sites}
```

- [ ] **Step 4: Verify pass.** Run: `uv run pytest tests/test_context_api.py -k get_sites -v`

- [ ] **Step 5: Commit.**

```bash
git add server.py tests/test_context_api.py
git commit -m "feat(context): GET /api/context/sites?region"
```

---

### Task 6: PUT /api/context/sites/{site_id}

**Files:** `server.py`, `tools/context_api.py`, `tests/test_context_api.py`.

- [ ] **Step 1: Add helper to `tools/context_api.py`:**

```python
def replace_site_in_registry(registry_path: Path, site_id: str, new_record: dict) -> tuple[bool, str | None]:
    """Replace one site record. Returns (ok, error_reason).

    error_reason in {'not_found', 'id_change', 'region_change', None}.
    """
    doc = json.loads(registry_path.read_text(encoding="utf-8"))
    sites = doc.get("sites", [])
    for i, s in enumerate(sites):
        if s.get("site_id") == site_id:
            if new_record.get("site_id") != site_id:
                return False, "id_change"
            if new_record.get("region") != s.get("region"):
                return False, "region_change"
            sites[i] = new_record
            doc["sites"] = sites
            atomic_write_json(registry_path, doc)
            return True, None
    return False, "not_found"
```

- [ ] **Step 2: Write four failing tests.**

```python
def test_put_site_full_replace(tmp_data):
    record = {
        "site_id": "apac-kaohsiung-mfg", "name": "Kaohsiung (edited)", "region": "APAC",
        "country": "TW", "lat": 22.62, "lon": 120.30, "type": "manufacturing",
        "subtype": "assembly", "poi_radius_km": 60,
        "personnel_count": 340, "expat_count": 20, "shift_pattern": "24/7",
        "criticality": "crown_jewel", "tier": "crown_jewel",
        "produces": "blades", "dependencies": [], "feeds_into": [],
        "customer_dependencies": [], "previous_incidents": [], "notable_dates": [],
        "site_lead": {"name": "A", "phone": "1"},
        "duty_officer": {"name": "B", "phone": "2"},
        "embassy_contact": {"country_of_origin": "DK", "contact": "c", "phone": "3"},
        "new_field_from_phase5": "extra",
    }
    r = client.put("/api/context/sites/apac-kaohsiung-mfg", json=record)
    assert r.status_code == 200
    saved_doc = json.loads((tmp_data / "data" / "aerowind_sites.json").read_text())
    saved_site = next(s for s in saved_doc["sites"] if s["site_id"] == "apac-kaohsiung-mfg")
    assert saved_site["name"] == "Kaohsiung (edited)"
    assert saved_site["new_field_from_phase5"] == "extra"
    other = next(s for s in saved_doc["sites"] if s["site_id"] == "ame-houston-ops")
    assert other["name"] == "Houston"


def test_put_site_unknown_id_returns_404():
    r = client.put("/api/context/sites/does-not-exist",
                   json={"site_id": "does-not-exist", "region": "APAC"})
    assert r.status_code == 404


def test_put_site_changing_id_returns_400():
    r = client.put("/api/context/sites/apac-kaohsiung-mfg",
                   json={"site_id": "other", "region": "APAC"})
    assert r.status_code == 400


def test_put_site_changing_region_returns_400():
    r = client.put("/api/context/sites/apac-kaohsiung-mfg",
                   json={"site_id": "apac-kaohsiung-mfg", "region": "AME"})
    assert r.status_code == 400
```

- [ ] **Step 3: Verify fail.** Run: `uv run pytest tests/test_context_api.py -k put_site -v`

- [ ] **Step 4: Add endpoint in `server.py`.**

```python
@app.put("/api/context/sites/{site_id}")
async def put_context_site(site_id: str, body: dict):
    from tools.context_api import replace_site_in_registry
    path = BASE / "data" / "aerowind_sites.json"
    if not path.exists():
        return JSONResponse({"error": "aerowind_sites.json not found"}, status_code=500)
    ok, err = replace_site_in_registry(path, site_id, body)
    if ok:
        return {"ok": True}
    if err == "not_found":
        return JSONResponse({"error": f"Unknown site_id: {site_id}"}, status_code=404)
    if err in ("id_change", "region_change"):
        field = err.replace("_change", "")
        return JSONResponse({"error": f"Cannot change {field} via PUT"}, status_code=400)
    return JSONResponse({"error": "unknown error"}, status_code=500)
```

- [ ] **Step 5: Verify pass.** Run: `uv run pytest tests/test_context_api.py -k put_site -v`

- [ ] **Step 6: Commit.**

```bash
git add server.py tools/context_api.py tests/test_context_api.py
git commit -m "feat(context): PUT /api/context/sites/{site_id}"
```

---

### Task 7: GET /api/context/regional/{region} with computed headcount

**Files:** `server.py`, `tools/context_api.py`, `tests/test_context_api.py`.

- [ ] **Step 1: Add helpers to `tools/context_api.py`:**

```python
def derive_headcount(sites: list[dict], region: str) -> tuple[int, int]:
    """Return (headcount, contractors) for a region.

    headcount = sum(personnel_count + expat_count) across region sites.
    contractors = sum(contractors_count) across region sites (may be absent).
    """
    regional = [s for s in sites if s.get("region") == region]
    headcount = sum(int(s.get("personnel_count", 0) or 0) + int(s.get("expat_count", 0) or 0) for s in regional)
    contractors = sum(int(s.get("contractors_count", 0) or 0) for s in regional)
    return headcount, contractors


def load_regional_record(footprint_path: Path, sites_path: Path, region: str) -> dict:
    """Return footprint[region] augmented with computed headcount/contractors and new aliases."""
    footprint = json.loads(footprint_path.read_text(encoding="utf-8"))
    entry = footprint.get(region, {})
    sites_doc = json.loads(sites_path.read_text(encoding="utf-8")) if sites_path.exists() else {"sites": []}
    headcount, contractors = derive_headcount(sites_doc.get("sites", []), region)
    out = dict(entry)
    out["headcount"] = headcount
    out["contractors"] = contractors
    out.setdefault("regional_summary", entry.get("summary", ""))
    out.setdefault("standing_notes", entry.get("notes", ""))
    out.setdefault("regional_threat_actor_groups", entry.get("regional_threat_actor_groups", []))
    out.setdefault("regional_sector_targeting_campaigns", entry.get("regional_sector_targeting_campaigns", []))
    out.setdefault("regional_cyber_geographies_of_concern", entry.get("regional_cyber_geographies_of_concern", []))
    out.setdefault("regional_standing_notes", entry.get("regional_standing_notes", ""))
    return out
```

- [ ] **Step 2: Write tests.**

```python
def test_get_regional_computes_headcount_from_sites():
    r = client.get("/api/context/regional/APAC")
    assert r.status_code == 200
    body = r.json()
    assert body["headcount"] == 338  # 320 personnel + 18 expats
    assert body["contractors"] == 0
    assert body["regional_summary"] == "APAC primary"
    assert body["standing_notes"] == ""


def test_get_regional_unknown_region_returns_400():
    r = client.get("/api/context/regional/ZZZ")
    assert r.status_code == 400
```

- [ ] **Step 3: Verify fail.** Run: `uv run pytest tests/test_context_api.py -k get_regional -v`

- [ ] **Step 4: Add endpoint in `server.py`.**

```python
@app.get("/api/context/regional/{region}")
async def get_context_regional(region: str):
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=400)
    from tools.context_api import load_regional_record
    footprint_path = BASE / "data" / "regional_footprint.json"
    sites_path = BASE / "data" / "aerowind_sites.json"
    if not footprint_path.exists():
        return JSONResponse({"error": "regional_footprint.json not found"}, status_code=500)
    return load_regional_record(footprint_path, sites_path, r)
```

- [ ] **Step 5: Verify pass.** Run: `uv run pytest tests/test_context_api.py -k get_regional -v`

- [ ] **Step 6: Commit.**

```bash
git add server.py tools/context_api.py tests/test_context_api.py
git commit -m "feat(context): GET /api/context/regional with derived headcount"
```

---

### Task 8: PUT /api/context/regional/{region} with alias double-write

**Files:** `server.py`, `tools/context_api.py`, `tests/test_context_api.py`.

- [ ] **Step 1: Add write helper to `tools/context_api.py`:**

```python
def write_regional_record(footprint_path: Path, sites_path: Path, region: str, body: dict) -> None:
    """Write the regional sub-document with alias double-write and recomputed headcount.

    - Double-writes: regional_summary -> summary, standing_notes -> notes (legacy consumers).
    - Recomputes: headcount from sites (ignores body['headcount']).
    """
    footprint = json.loads(footprint_path.read_text(encoding="utf-8"))
    entry = footprint.get(region, {})

    entry["regional_summary"] = body.get("regional_summary", "")
    entry["standing_notes"] = body.get("standing_notes", "")
    entry["regional_threat_actor_groups"] = body.get("regional_threat_actor_groups", [])
    entry["regional_sector_targeting_campaigns"] = body.get("regional_sector_targeting_campaigns", [])
    entry["regional_cyber_geographies_of_concern"] = body.get("regional_cyber_geographies_of_concern", [])
    entry["regional_standing_notes"] = body.get("regional_standing_notes", "")

    # Legacy aliases for build_context.py and other existing consumers
    entry["summary"] = entry["regional_summary"]
    entry["notes"] = entry["standing_notes"]

    sites_doc = json.loads(sites_path.read_text(encoding="utf-8")) if sites_path.exists() else {"sites": []}
    headcount, _ = derive_headcount(sites_doc.get("sites", []), region)
    entry["headcount"] = headcount

    footprint[region] = entry
    atomic_write_json(footprint_path, footprint)
```

- [ ] **Step 2: Write tests.**

```python
def test_put_regional_writes_both_alias_and_new_keys(tmp_data):
    body = {
        "regional_summary": "APAC updated",
        "standing_notes": "Watch MED-to-APAC lateral",
        "regional_threat_actor_groups": [],
        "regional_sector_targeting_campaigns": [],
        "regional_cyber_geographies_of_concern": ["CN"],
        "regional_standing_notes": "Increased scanning observed",
    }
    r = client.put("/api/context/regional/APAC", json=body)
    assert r.status_code == 200
    saved = json.loads((tmp_data / "data" / "regional_footprint.json").read_text())["APAC"]
    assert saved["regional_summary"] == "APAC updated"
    assert saved["regional_standing_notes"] == "Increased scanning observed"
    assert saved["regional_cyber_geographies_of_concern"] == ["CN"]
    assert saved["summary"] == "APAC updated"
    assert saved["notes"] == "Watch MED-to-APAC lateral"


def test_put_regional_recomputes_headcount_from_sites(tmp_data):
    body = {
        "regional_summary": "x", "standing_notes": "x",
        "regional_threat_actor_groups": [], "regional_sector_targeting_campaigns": [],
        "regional_cyber_geographies_of_concern": [], "regional_standing_notes": "",
        "headcount": 99999,
    }
    r = client.put("/api/context/regional/APAC", json=body)
    assert r.status_code == 200
    saved = json.loads((tmp_data / "data" / "regional_footprint.json").read_text())["APAC"]
    assert saved["headcount"] == 338
    assert saved["headcount"] != 99999
```

- [ ] **Step 3: Verify fail.** Run: `uv run pytest tests/test_context_api.py -k put_regional -v`

- [ ] **Step 4: Add endpoint in `server.py`.**

```python
@app.put("/api/context/regional/{region}")
async def put_context_regional(region: str, body: dict):
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=400)
    from tools.context_api import write_regional_record
    footprint_path = BASE / "data" / "regional_footprint.json"
    sites_path = BASE / "data" / "aerowind_sites.json"
    if not footprint_path.exists():
        return JSONResponse({"error": "regional_footprint.json not found"}, status_code=500)
    write_regional_record(footprint_path, sites_path, r, body)
    return {"ok": True}
```

- [ ] **Step 5: Verify pass.** Run: `uv run pytest tests/test_context_api.py -k put_regional -v`

- [ ] **Step 6: Add error-path tests** for JSON decode failures. These exercise the FastAPI default 422 behavior on malformed bodies. Append:

```python
def test_put_company_malformed_json_returns_422():
    # Send bytes that are not valid JSON
    r = client.put("/api/context/company", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code in (400, 422)


def test_put_cyber_watchlist_malformed_json_returns_422():
    r = client.put("/api/context/cyber-watchlist", content=b"", headers={"Content-Type": "application/json"})
    assert r.status_code in (400, 422)
```

Run: `uv run pytest tests/test_context_api.py -k malformed -v`
Expected: PASS. FastAPI's default `dict` body validator rejects malformed JSON with 422.

- [ ] **Step 7: Commit.**

```bash
git add server.py tools/context_api.py tests/test_context_api.py
git commit -m "feat(context): PUT /api/context/regional with alias double-write"
```

---

### Task 9: Context tab shell — nav button, panel, region strip, state, placeholders

**Files:** `static/index.html`, `static/app.js`.

- [ ] **Step 1: Add nav button in `static/index.html`.** After the Source Library nav entry (around line 994), insert:

```html
      <div class="nav-tab" id="nav-context"  onclick="switchTab('context')">Context</div>
```

- [ ] **Step 2: Add tab panel block in `static/index.html`.** After the Config tab block (around line 1193, before `<!-- PIPELINE TAB -->`), insert:

```html
<!-- CONTEXT TAB -->
<div id="tab-context" class="hidden" style="height:calc(100vh - 60px);display:flex;flex-direction:column;overflow:hidden">
  <div id="context-region-strip" style="display:flex;border-bottom:1px solid #21262d;flex-shrink:0;padding:0 16px"></div>
  <div id="context-body" style="flex:1;overflow-y:auto;padding:16px 20px"></div>
</div>
```

- [ ] **Step 3: Register `context` in the `_doSwitchTab` tabs list.** In `static/app.js` line 1765, find:

```javascript
  ['overview', 'reports', 'history', 'trends', 'config', 'validate', 'sources', 'pipeline', 'runlog'].forEach(t => {
```

Replace with:

```javascript
  ['overview', 'reports', 'history', 'trends', 'config', 'validate', 'sources', 'context', 'pipeline', 'runlog'].forEach(t => {
```

- [ ] **Step 4: Extend the display logic at line 1769.** Find:

```javascript
    el.style.display = t === tab ? (t === 'config' || t === 'overview' || t === 'pipeline' || t === 'runlog' || t === 'validate' ? 'flex' : 'block') : 'none';
```

Replace with:

```javascript
    el.style.display = t === tab ? (t === 'config' || t === 'overview' || t === 'pipeline' || t === 'runlog' || t === 'validate' || t === 'context' ? 'flex' : 'block') : 'none';
```

- [ ] **Step 5: Add the context render hook.** After line 1780 (`if (tab === 'runlog') renderRunLog();`), insert:

```javascript
  if (tab === 'context') renderContextTab();
```

- [ ] **Step 6: Append `contextState` + scaffold functions at EOF of `static/app.js`:**

```javascript
// =====================================================================
// Context Tab
// =====================================================================
const contextState = {
  currentRegion: 'Global',
  company: null,
  cyberWatchlist: null,
  sitesByRegion: {},
  regionalByRegion: {},
  dirty: { company: false, cyberWatchlist: false, regional: {}, sites: {} },
  selectedSiteId: null,
};

function renderContextTab() {
  renderContextRegionStrip();
  renderContextBody();
}

function renderContextRegionStrip() {
  const strip = $('context-region-strip');
  if (!strip) return;
  const regions = ['Global', 'APAC', 'AME', 'LATAM', 'MED', 'NCE'];
  strip.innerHTML = regions.map(function (r) {
    const active = contextState.currentRegion === r;
    return '<div class="nav-tab' + (active ? ' active' : '') + '" onclick="switchContextRegion(\'' + r + '\')">' + r + '</div>';
  }).join('');
}

function switchContextRegion(region) {
  if (anyContextSurfaceDirty()) {
    if (!confirm('You have unsaved changes in ' + contextState.currentRegion + '. Discard?')) return;
  }
  contextState.currentRegion = region;
  contextState.dirty = { company: false, cyberWatchlist: false, regional: {}, sites: {} };
  contextState.selectedSiteId = null;
  renderContextTab();
}

function anyContextSurfaceDirty() {
  const d = contextState.dirty;
  if (d.company || d.cyberWatchlist) return true;
  if (Object.values(d.regional || {}).some(Boolean)) return true;
  if (Object.values(d.sites || {}).some(Boolean)) return true;
  return false;
}

function renderContextBody() {
  const body = $('context-body');
  if (!body) return;
  if (contextState.currentRegion === 'Global') {
    body.innerHTML = '<div id="ctx-company"></div><div id="ctx-global-cyber" style="margin-top:24px"></div>';
    renderCompanySurface();
    renderGlobalCyberWatchlistSurface();
  } else {
    body.innerHTML = '<div id="ctx-sites"></div><div id="ctx-regional" style="margin-top:24px"></div>';
    renderSitesSurface();
    renderRegionalSurface();
  }
}

// Surface stubs — replaced in tasks 12-15
function renderCompanySurface() { $('ctx-company').innerHTML = '<em style="color:#6e7681">Company panel (Task 12)</em>'; }
function renderGlobalCyberWatchlistSurface() { $('ctx-global-cyber').innerHTML = '<em style="color:#6e7681">Global cyber watchlist (Task 13)</em>'; }
function renderSitesSurface() { $('ctx-sites').innerHTML = '<em style="color:#6e7681">Sites panel (Task 14)</em>'; }
function renderRegionalSurface() { $('ctx-regional').innerHTML = '<em style="color:#6e7681">Regional panel (Task 15)</em>'; }
```

- [ ] **Step 7: Smoke test.** Start the dev server: `uv run uvicorn server:app --port 8001` (run in background or a separate shell). Open `http://localhost:8001`. Click the Context nav tab. Verify:
- Region strip shows 6 buttons (Global, APAC, AME, LATAM, MED, NCE).
- Global view shows two placeholder boxes (Company + Global cyber).
- Clicking APAC shows two different placeholder boxes (Sites + Regional).

- [ ] **Step 8: Commit.**

```bash
git add static/index.html static/app.js
git commit -m "feat(context): tab shell, region strip, placeholder surfaces"
```

---

### Task 10: Tag List primitive

**Files:** `static/app.js`.

- [ ] **Step 1: Append to `static/app.js` after the Context state block from Task 9.** The code below uses string concatenation with `esc()` because several onclick handlers need to interpolate `instanceId`. Match the existing codebase convention (see `renderTopicsTable`, `renderFootprint`):

```javascript
// Tag List primitive: flat-string array -> removable pills + add input.
function renderTagList(values, onChange, instanceId) {
  const inputId = "tl-input-" + instanceId;
  window["__tl_" + instanceId + "_change"] = onChange;
  window["__tl_" + instanceId + "_values"] = values.slice();

  const pillStyle = "display:inline-flex;align-items:center;gap:6px;background:#1f2936;border:1px solid #30363d;border-radius:12px;padding:2px 10px;margin:2px 4px 2px 0;font-size:11px;color:#c9d1d9";
  const xBtnStyle = "background:none;border:none;color:#6e7681;cursor:pointer;font-size:12px;padding:0";
  const pills = values.map(function (v, i) {
    const xBtn = "<button onclick=\"__tlRemove(" + JSON.stringify(instanceId) + "," + i + ")\" style=\"" + xBtnStyle + "\">x</button>";
    return "<span style=\"" + pillStyle + "\">" + esc(v) + xBtn + "</span>";
  }).join("");

  const inputStyle = "flex:1;background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:4px 8px;font-size:11px;font-family:\"IBM Plex Mono\",monospace;border-radius:2px";
  const addBtnStyle = "font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:2px 10px;border-radius:2px;cursor:pointer";
  const inputHtml = "<input type=\"text\" id=\"" + inputId + "\" placeholder=\"Add...\" onkeydown=\"if(event.key==='Enter'){__tlAdd(" + JSON.stringify(instanceId) + ");event.preventDefault();}\" style=\"" + inputStyle + "\">";
  const addBtn = "<button onclick=\"__tlAdd(" + JSON.stringify(instanceId) + ")\" style=\"" + addBtnStyle + "\">+</button>";
  const inputRow = "<div style=\"display:flex;gap:6px;margin-top:6px\">" + inputHtml + addBtn + "</div>";
  const emptyMsg = "<span style=\"color:#6e7681;font-size:11px\">(none)</span>";
  return "<div>" + "<div>" + (pills || emptyMsg) + "</div>" + inputRow + "</div>";
}

function __tlAdd(instanceId) {
  const input = $("tl-input-" + instanceId);
  const v = (input.value || "").trim();
  if (!v) return;
  const values = window["__tl_" + instanceId + "_values"];
  if (values.indexOf(v) !== -1) { input.value = ""; return; }
  values.push(v);
  window["__tl_" + instanceId + "_change"](values);
}

function __tlRemove(instanceId, index) {
  const values = window["__tl_" + instanceId + "_values"];
  values.splice(index, 1);
  window["__tl_" + instanceId + "_change"](values);
}
```

- [ ] **Step 2: Commit.** The primitive is exercised in later tasks — no standalone smoke test.

```bash
git add static/app.js
git commit -m "feat(context): Tag List UI primitive"
```

---

### Task 11: Record List primitive

**Files:** `static/app.js`.

- [ ] **Step 1: Append after the Tag List primitive.** The onChange callback takes a second `info` arg with `kind`: `"mutate"` (text edit — do NOT re-render; the UI input retains focus while the parent just marks dirty) or `"structure"` (add/remove — DO re-render so the row layout updates). Toggle expand is a local DOM mutation that does not fire onChange at all, so it can't accidentally dirty the surface.

```javascript
// Record List primitive: records[] with labeled mini-forms.
// fieldDefs items: {key, label, type: "text" | "textarea" | "taglist"}
// onChange(records, { kind: "mutate" | "structure" }) — caller decides whether to re-render.
function renderRecordList(records, fieldDefs, summaryFn, onChange, instanceId) {
  window["__rl_" + instanceId + "_change"] = onChange;
  window["__rl_" + instanceId + "_records"] = records;  // share the reference; mutations are visible to caller
  window["__rl_" + instanceId + "_fields"] = fieldDefs;
  window["__rl_" + instanceId + "_summary"] = summaryFn;
  if (!window["__rl_" + instanceId + "_expanded"]) window["__rl_" + instanceId + "_expanded"] = new Set();
  const expanded = window["__rl_" + instanceId + "_expanded"];

  const rows = records.map(function (r, i) {
    const isOpen = expanded.has(i);
    const summary = esc(summaryFn(r) || "(empty)");
    const chevron = isOpen ? "v" : ">";
    let editor = "";
    if (isOpen) {
      editor = "<div id=\"rl-body-" + instanceId + "-" + i + "\" style=\"padding:8px 12px;background:#0d1117;border-top:1px solid #21262d\">" +
        fieldDefs.map(function (f) { return __rlFieldInput(instanceId, i, f, r[f.key]); }).join("") +
      "</div>";
    }
    const headerStyle = "display:flex;align-items:center;gap:8px;padding:6px 12px;cursor:pointer";
    const xBtnStyle = "background:none;border:none;color:#6e7681;cursor:pointer;font-size:12px";
    const header = "<div id=\"rl-header-" + instanceId + "-" + i + "\" style=\"" + headerStyle + "\" onclick=\"__rlToggle(" + JSON.stringify(instanceId) + "," + i + ")\">" +
      "<span style=\"color:#6e7681\">" + chevron + "</span>" +
      "<span style=\"flex:1;font-size:11px\">" + summary + "</span>" +
      "<button onclick=\"event.stopPropagation();__rlRemove(" + JSON.stringify(instanceId) + "," + i + ")\" style=\"" + xBtnStyle + "\">x</button>" +
    "</div>";
    return "<div id=\"rl-row-" + instanceId + "-" + i + "\" style=\"border:1px solid #21262d;border-radius:2px;margin:4px 0;background:#080c10\">" + header + editor + "</div>";
  }).join("");

  const addBtnStyle = "margin-top:6px;font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:4px 10px;border-radius:2px;cursor:pointer";
  const addBtn = "<button onclick=\"__rlAdd(" + JSON.stringify(instanceId) + ")\" style=\"" + addBtnStyle + "\">+ Add row</button>";
  const emptyMsg = "<div style=\"color:#6e7681;font-size:11px;padding:4px 0\">(no entries)</div>";
  return "<div>" + (rows || emptyMsg) + addBtn + "</div>";
}

function __rlFieldInput(instanceId, recordIdx, f, value) {
  const id = "rl-" + instanceId + "-" + recordIdx + "-" + f.key;
  const labelBlock = "<label style=\"display:block;font-size:9px;letter-spacing:0.06em;text-transform:uppercase;color:#6e7681;margin:6px 0 2px\">" + esc(f.label) + "</label>";
  const baseStyle = "width:100%;background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:4px 8px;font-size:11px;font-family:\"IBM Plex Mono\",monospace;border-radius:2px";
  const onInput = "oninput=\"__rlFieldChange(" + JSON.stringify(instanceId) + "," + recordIdx + "," + JSON.stringify(f.key) + ",this.value)\"";
  if (f.type === "textarea") {
    return labelBlock + "<textarea id=\"" + id + "\" " + onInput + " style=\"" + baseStyle + ";min-height:40px\">" + esc(value || "") + "</textarea>";
  }
  if (f.type === "taglist") {
    return labelBlock + "<div id=\"" + id + "\"></div>";
  }
  const safeVal = esc(value == null ? "" : String(value));
  return labelBlock + "<input type=\"text\" id=\"" + id + "\" value=\"" + safeVal + "\" " + onInput + " style=\"" + baseStyle + "\">";
}

// Toggle expand is a LOCAL DOM operation — does not fire onChange, does not dirty the surface.
function __rlToggle(instanceId, idx) {
  const s = window["__rl_" + instanceId + "_expanded"];
  const wasOpen = s.has(idx);
  if (wasOpen) s.delete(idx); else s.add(idx);

  // Fire onChange with kind=structure so the caller re-renders only the Record List host element.
  // Callers for structure events re-render the whole surface; for local expand we prefer a tighter
  // update, but re-render via structure is acceptable since no text input is open in the toggling row.
  window["__rl_" + instanceId + "_change"](window["__rl_" + instanceId + "_records"], { kind: "structure" });
}

function __rlAdd(instanceId) {
  const recs = window["__rl_" + instanceId + "_records"];
  const fields = window["__rl_" + instanceId + "_fields"];
  const blank = {};
  fields.forEach(function (f) { blank[f.key] = f.type === "taglist" ? [] : ""; });
  recs.push(blank);
  window["__rl_" + instanceId + "_expanded"].add(recs.length - 1);
  window["__rl_" + instanceId + "_change"](recs, { kind: "structure" });
}

function __rlRemove(instanceId, idx) {
  if (!confirm("Remove this entry?")) return;
  const recs = window["__rl_" + instanceId + "_records"];
  recs.splice(idx, 1);
  const oldSet = window["__rl_" + instanceId + "_expanded"];
  const newSet = new Set();
  oldSet.forEach(function (i) { if (i === idx) return; newSet.add(i > idx ? i - 1 : i); });
  window["__rl_" + instanceId + "_expanded"] = newSet;
  window["__rl_" + instanceId + "_change"](recs, { kind: "structure" });
}

// Field edits MUTATE the shared records array in-place and signal "mutate" — caller marks dirty
// but does not re-render. The <input> retains focus and the user keeps typing.
function __rlFieldChange(instanceId, idx, key, value) {
  const recs = window["__rl_" + instanceId + "_records"];
  recs[idx][key] = value;
  window["__rl_" + instanceId + "_change"](recs, { kind: "mutate" });
}
```

- [ ] **Step 2: Tag List signature unchanged.** Tag List onChange still receives only `values` — not splitting because every Tag List operation (add/remove) is structural. The text input is for *adding* a new tag, not editing an existing one, so the focus-loss problem does not apply.

- [ ] **Step 2: Commit.**

```bash
git add static/app.js
git commit -m "feat(context): Record List UI primitive"
```

---

### Task 12: Company surface

**Files:** `static/app.js`.

- [ ] **Step 1: Replace the `renderCompanySurface` stub appended in Task 9 with the real implementation.** Find the stub and replace with:

```javascript
async function renderCompanySurface() {
  const el = $("ctx-company");
  if (!el) return;
  el.innerHTML = "<span style=\"color:#6e7681\">Loading company profile...</span>";
  if (!contextState.company) {
    contextState.company = await fetch("/api/context/company").then(function (r) { return r.ok ? r.json() : {}; }).catch(function () { return {}; });
  }
  const c = contextState.company;
  const dirty = contextState.dirty.company;

  const dot = dirty ? "<span title=\"Unsaved changes\" style=\"color:#ffa657\">●</span>" : "";
  const saveCol = dirty ? "#3fb950" : "#6e7681";
  const saveBg = dirty ? "#1a3a1a" : "#0d1117";
  const saveBd = dirty ? "#238636" : "#21262d";
  const saveCursor = dirty ? "pointer" : "not-allowed";
  const saveDisabled = dirty ? "" : "disabled";
  const saveBtn = "<button id=\"company-save-btn\" onclick=\"saveCompany()\" " + saveDisabled +
    " style=\"font-size:11px;color:" + saveCol + ";background:" + saveBg + ";border:1px solid " + saveBd + ";padding:4px 14px;border-radius:2px;cursor:" + saveCursor + "\">Save</button>";

  el.innerHTML =
    "<div style=\"background:#0d1117;border:1px solid #21262d;border-radius:4px;padding:14px 18px\">" +
      "<div style=\"display:flex;align-items:center;gap:8px;margin-bottom:10px\">" +
        "<span style=\"font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681\">Company</span>" + dot +
      "</div>" +
      "<div style=\"display:grid;grid-template-columns:1fr 1fr;gap:12px\">" +
        __ctxField("company-name",      "Name",           "text",   c.name,           "company") +
        __ctxField("company-employees", "Employee count", "number", c.employee_count, "company") +
      "</div>" +
      "<label style=\"display:block;font-size:9px;letter-spacing:0.06em;text-transform:uppercase;color:#6e7681;margin:10px 0 4px\">Sectors</label>" +
      "<div id=\"company-sectors\"></div>" +
      "<label style=\"display:block;font-size:9px;letter-spacing:0.06em;text-transform:uppercase;color:#6e7681;margin:10px 0 4px\">Countries of operation</label>" +
      "<div id=\"company-countries\"></div>" +
      __ctxField("company-appetite",   "Risk appetite",        "textarea", c.risk_appetite,        "company") +
      __ctxField("company-priorities", "Strategic priorities", "textarea", c.strategic_priorities, "company") +
      "<div style=\"text-align:right;margin-top:12px\">" + saveBtn + "</div>" +
    "</div>";

  $("company-sectors").innerHTML = renderTagList(c.sectors || [], function (next) {
    c.sectors = next; __ctxMarkDirty("company"); renderCompanySurface();
  }, "company-sectors");
  $("company-countries").innerHTML = renderTagList(c.countries_of_operation || [], function (next) {
    c.countries_of_operation = next; __ctxMarkDirty("company"); renderCompanySurface();
  }, "company-countries");
}

function __ctxField(id, label, type, value, surface) {
  const labelHtml = "<label style=\"display:block;font-size:9px;letter-spacing:0.06em;text-transform:uppercase;color:#6e7681;margin:0 0 4px\">" + esc(label) + "</label>";
  const baseStyle = "width:100%;background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:6px 8px;font-size:11px;font-family:\"IBM Plex Mono\",monospace;border-radius:2px";
  const onInput = "oninput=\"__ctxFieldEdit(" + JSON.stringify(id) + "," + JSON.stringify(surface) + ",this.value," + JSON.stringify(type) + ")\"";
  if (type === "textarea") {
    return "<div style=\"margin-top:10px\">" + labelHtml + "<textarea id=\"" + id + "\" " + onInput + " style=\"" + baseStyle + ";min-height:50px\">" + esc(value || "") + "</textarea></div>";
  }
  return "<div>" + labelHtml + "<input type=\"" + type + "\" id=\"" + id + "\" value=\"" + esc(value == null ? "" : String(value)) + "\" " + onInput + " style=\"" + baseStyle + "\"></div>";
}

function __ctxFieldEdit(id, surface, value, type) {
  const c = contextState.company;
  const mapping = {
    "company-name": "name",
    "company-employees": "employee_count",
    "company-appetite": "risk_appetite",
    "company-priorities": "strategic_priorities",
  };
  const key = mapping[id];
  if (key && surface === "company") {
    c[key] = type === "number" ? parseInt(value || "0", 10) : value;
    __ctxMarkDirty("company");
    __setSaveButtonEnabled("saveCompany()");
  }
}

function __ctxMarkDirty(surface, extra) {
  if (surface === "company") contextState.dirty.company = true;
  if (surface === "cyberWatchlist") contextState.dirty.cyberWatchlist = true;
  if (surface === "regional") contextState.dirty.regional[contextState.currentRegion] = true;
  if (surface === "sites") contextState.dirty.sites[extra] = true;
}

// Shared helpers used by every Context surface.
// __setSaveButtonEnabled: flip a Save button to enabled without re-rendering (preserves input focus).
// __showSurfaceError: render an inline error banner inside the named surface container.
function __setSaveButtonEnabled(onclickPrefix) {
  const btns = document.querySelectorAll("button[onclick]");
  btns.forEach(function (b) {
    const oc = b.getAttribute("onclick") || "";
    if (oc.indexOf(onclickPrefix) !== 0) return;
    b.disabled = false;
    b.style.color = "#3fb950"; b.style.background = "#1a3a1a";
    b.style.borderColor = "#238636"; b.style.cursor = "pointer";
  });
}

function __showSurfaceError(containerId, message) {
  const host = document.getElementById(containerId);
  if (!host) return;
  const existing = host.querySelector(".ctx-error-banner");
  if (existing) existing.remove();
  const banner = document.createElement("div");
  banner.className = "ctx-error-banner";
  banner.setAttribute("role", "alert");
  banner.style.cssText = "margin:8px 0;padding:8px 12px;background:#2d0000;border:1px solid #da3633;color:#ff7b72;font-size:11px;border-radius:2px";
  banner.textContent = message;
  // Banner sits above the save control. Simplest placement: prepend to surface so it's always visible.
  host.insertBefore(banner, host.firstChild);
  // Auto-clear after 8 seconds so stale errors do not linger.
  setTimeout(function () { if (banner.parentNode) banner.parentNode.removeChild(banner); }, 8000);
}

async function saveCompany() {
  const r = await fetch("/api/context/company", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(contextState.company),
  });
  if (r.ok) {
    contextState.dirty.company = false;
    contextState.company = null;
    renderCompanySurface();
  } else {
    __showSurfaceError("ctx-company", "Save failed (HTTP " + r.status + "). Stored file is unchanged.");
  }
}
```

- [ ] **Step 2: Smoke test.** With dev server running: Context -> Global. Edit Name. Dirty dot appears, Save button enables. Click Save — page re-renders with saved value.

- [ ] **Step 3: Commit.**

```bash
git add static/app.js
git commit -m "feat(context): company surface (editor)"
```

---

### Task 13: Global Cyber Watchlist surface

**Files:** `static/app.js`.

- [ ] **Step 1: Replace the `renderGlobalCyberWatchlistSurface` stub with:**

```javascript
async function renderGlobalCyberWatchlistSurface() {
  const el = $("ctx-global-cyber");
  if (!el) return;
  if (!contextState.cyberWatchlist) {
    const empty = {
      threat_actor_groups: [], sector_targeting_campaigns: [],
      cve_watch_categories: [], global_cyber_geographies_of_concern: [],
    };
    contextState.cyberWatchlist = await fetch("/api/context/cyber-watchlist").then(function (r) { return r.ok ? r.json() : empty; });
  }
  const w = contextState.cyberWatchlist;
  const dirty = contextState.dirty.cyberWatchlist;
  const dot = dirty ? "<span style=\"color:#ffa657\">●</span>" : "";

  const saveCol = dirty ? "#3fb950" : "#6e7681";
  const saveBg = dirty ? "#1a3a1a" : "#0d1117";
  const saveBd = dirty ? "#238636" : "#21262d";
  const saveCursor = dirty ? "pointer" : "not-allowed";
  const saveDisabled = dirty ? "" : "disabled";
  const saveBtn = "<button onclick=\"saveCyberWatchlist()\" " + saveDisabled + " style=\"font-size:11px;color:" + saveCol + ";background:" + saveBg + ";border:1px solid " + saveBd + ";padding:4px 14px;border-radius:2px;cursor:" + saveCursor + "\">Save</button>";

  const sectionHdr = "font-size:10px;color:#79c0ff;margin-bottom:4px";
  el.innerHTML =
    "<div style=\"background:#0d1117;border:1px solid #21262d;border-radius:4px;padding:14px 18px\">" +
      "<div style=\"display:flex;align-items:center;gap:8px;margin-bottom:10px\">" +
        "<span style=\"font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681\">Global Cyber Watchlist</span>" + dot +
      "</div>" +
      "<div style=\"margin-top:12px\"><div style=\"" + sectionHdr + "\">Threat actor groups</div><div id=\"cyber-actors\"></div></div>" +
      "<div style=\"margin-top:16px\"><div style=\"" + sectionHdr + "\">Sector-targeting campaigns</div><div id=\"cyber-campaigns\"></div></div>" +
      "<div style=\"margin-top:16px\"><div style=\"" + sectionHdr + "\">CVE watch categories</div><div id=\"cyber-cves\"></div></div>" +
      "<div style=\"margin-top:16px\"><div style=\"" + sectionHdr + "\">Geographies of concern</div><div id=\"cyber-geos\"></div></div>" +
      "<div style=\"text-align:right;margin-top:14px\">" + saveBtn + "</div>" +
    "</div>";

  // Record List onChange comes with kind: structure = re-render surface; mutate = only mark dirty.
  const rlOnChange = function (assign) {
    return function (next, info) {
      assign(next);
      __ctxMarkDirty("cyberWatchlist");
      if (info && info.kind === "structure") {
        renderGlobalCyberWatchlistSurface();
      } else {
        __setSaveButtonEnabled("saveCyberWatchlist()");
      }
    };
  };
  const tlOnChange = function (assign) {
    return function (next) {
      assign(next);
      __ctxMarkDirty("cyberWatchlist");
      renderGlobalCyberWatchlistSurface();  // Tag List changes are always structural
    };
  };

  $("cyber-actors").innerHTML = renderRecordList(
    w.threat_actor_groups, [
      { key: "name", label: "Name", type: "text" },
      { key: "aliases", label: "Aliases", type: "taglist" },
      { key: "motivation", label: "Motivation", type: "text" },
      { key: "target_sectors", label: "Target sectors", type: "taglist" },
      { key: "target_geographies", label: "Target geographies", type: "taglist" },
    ],
    function (r) { return (r.name || "(unnamed)") + (r.motivation ? " - " + r.motivation : ""); },
    rlOnChange(function (next) { w.threat_actor_groups = next; }),
    "cyber-actors"
  );
  $("cyber-campaigns").innerHTML = renderRecordList(
    w.sector_targeting_campaigns, [
      { key: "campaign_name", label: "Campaign name", type: "text" },
      { key: "actor", label: "Actor", type: "text" },
      { key: "sectors", label: "Sectors", type: "taglist" },
      { key: "first_observed", label: "First observed", type: "text" },
      { key: "status", label: "Status", type: "text" },
    ],
    function (r) { return (r.campaign_name || "(unnamed)") + (r.actor ? " / " + r.actor : ""); },
    rlOnChange(function (next) { w.sector_targeting_campaigns = next; }),
    "cyber-campaigns"
  );
  $("cyber-cves").innerHTML = renderTagList(
    w.cve_watch_categories, tlOnChange(function (next) { w.cve_watch_categories = next; }), "cyber-cves"
  );
  $("cyber-geos").innerHTML = renderTagList(
    w.global_cyber_geographies_of_concern, tlOnChange(function (next) { w.global_cyber_geographies_of_concern = next; }), "cyber-geos"
  );
}

async function saveCyberWatchlist() {
  const btn = document.querySelector("button[onclick=\"saveCyberWatchlist()\"]");
  const r = await fetch("/api/context/cyber-watchlist", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(contextState.cyberWatchlist),
  });
  if (r.ok) {
    contextState.dirty.cyberWatchlist = false;
    contextState.cyberWatchlist = null;
    renderGlobalCyberWatchlistSurface();
  } else {
    __showSurfaceError("ctx-global-cyber", "Save failed (HTTP " + r.status + "). Stored file is unchanged.");
  }
}
```

- [ ] **Step 2: Smoke test.** Context -> Global. Add a threat actor group. Add a CVE tag. Click Save. Refresh — entries persist.

- [ ] **Step 3: Commit.**

```bash
git add static/app.js
git commit -m "feat(context): global cyber watchlist surface (capture)"
```

---

### Task 14: Sites surface — list + detail

**Files:** `static/app.js`.

The surface is two columns: a site list on the left and a scrollable detail form on the right. The detail form is grouped into collapsible sections. Implementing in four code blocks for readability.

- [ ] **Step 1a: Replace the `renderSitesSurface` stub** with the list renderer (detail section is loaded by `renderSiteDetail`, defined in 1b):

```javascript
async function renderSitesSurface() {
  const el = $("ctx-sites");
  if (!el) return;
  const region = contextState.currentRegion;
  if (!contextState.sitesByRegion[region]) {
    const resp = await fetch("/api/context/sites?region=" + region).then(function (r) { return r.ok ? r.json() : { sites: [] }; });
    contextState.sitesByRegion[region] = resp.sites || [];
  }
  const sites = contextState.sitesByRegion[region];
  if (!contextState.selectedSiteId && sites.length) contextState.selectedSiteId = sites[0].site_id;
  const selected = sites.find(function (s) { return s.site_id === contextState.selectedSiteId; });

  const listHdr = "padding:8px 12px;border-bottom:1px solid #21262d;font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681";
  const rows = sites.map(function (s) {
    const active = s.site_id === contextState.selectedSiteId;
    const sdirty = contextState.dirty.sites[s.site_id];
    const rowBg = active ? "#1a2532" : "transparent";
    const dot = sdirty ? "<span style=\"color:#ffa657\">●</span>" : "";
    const rowStyle = "padding:8px 12px;border-bottom:1px solid #21262d;cursor:pointer;background:" + rowBg + ";display:flex;align-items:center;gap:6px";
    return "<div onclick=\"selectContextSite(" + JSON.stringify(s.site_id) + ")\" style=\"" + rowStyle + "\">" +
      "<span style=\"font-size:11px;color:#c9d1d9;flex:1\">" + esc(s.name) + "</span>" +
      "<span style=\"font-size:9px;color:#6e7681\">" + esc(__tierBadge(s.tier)) + "</span>" +
      dot + "</div>";
  }).join("");
  const emptyList = "<div style=\"padding:12px;color:#6e7681;font-size:11px\">No sites in this region</div>";

  el.innerHTML =
    "<div style=\"display:grid;grid-template-columns:240px 1fr;gap:16px\">" +
      "<div style=\"background:#0d1117;border:1px solid #21262d;border-radius:4px;overflow:hidden\">" +
        "<div style=\"" + listHdr + "\">Sites - " + region + "</div>" +
        (rows || emptyList) +
      "</div>" +
      "<div id=\"ctx-site-detail\" style=\"background:#0d1117;border:1px solid #21262d;border-radius:4px;padding:14px 18px\"></div>" +
    "</div>";

  if (selected) renderSiteDetail(selected);
}

function __tierBadge(tier) {
  const map = { crown_jewel: "CJ", primary: "PR", secondary: "SC", minor: "MN" };
  return map[tier] || (tier ? tier.slice(0, 2).toUpperCase() : "");
}

function selectContextSite(siteId) {
  const prevId = contextState.selectedSiteId;
  if (prevId && contextState.dirty.sites[prevId]) {
    const prev = (contextState.sitesByRegion[contextState.currentRegion] || []).find(function (s) { return s.site_id === prevId; });
    const name = prev ? prev.name : prevId;
    if (!confirm("Discard unsaved changes to " + name + "?")) return;
    contextState.dirty.sites[prevId] = false;
    delete contextState.sitesByRegion[contextState.currentRegion];
  }
  contextState.selectedSiteId = siteId;
  renderSitesSurface();
}
```

- [ ] **Step 1b: Add the detail renderer** with field-group definitions:

```javascript
function renderSiteDetail(site) {
  const el = $("ctx-site-detail");
  const dirty = contextState.dirty.sites[site.site_id];
  const groups = [
    { title: "Identity", open: true, fields: [
      ["name","Name","text"],["country","Country","text"],["type","Type","text"],
      ["subtype","Subtype","text"],["asset_type","Asset type","text"],
      ["status","Status","text"],["seerist_country_code","Seerist country code","text"],
    ]},
    { title: "Location", open: false, fields: [
      ["lat","Latitude","number"],["lon","Longitude","number"],
      ["poi_radius_km","POI radius km","number"],
      ["capital_distance_km","Capital distance km (read-only)","readonly"],
    ]},
    { title: "Criticality", open: true, fields: [
      ["tier","Tier","select:crown_jewel|primary|secondary|minor"],
      ["criticality","Criticality","select:crown_jewel|major|standard"],
      ["criticality_drivers","Criticality drivers","textarea"],
      ["downstream_dependency","Downstream dependency","text"],
    ]},
    { title: "People", open: false, fields: [
      ["personnel_count","Personnel count","number"],["expat_count","Expat count","number"],
      ["contractors_count","Contractors count","number"],["shift_pattern","Shift pattern","text"],
    ]},
    { title: "Environment", open: false, fields: [
      ["host_country_risk_baseline","Host country baseline","select:low|elevated|high"],
      ["standing_notes","Standing notes","textarea"],
    ]},
    { title: "Seerist Joins", open: false, fields: [
      ["relevant_seerist_categories","Categories","taglist"],
      ["threat_actors_of_interest","Actors of interest","taglist"],
      ["relevant_attack_types","Attack types","taglist"],
    ]},
    { title: "Cyber", open: false, fields: [
      ["site_cyber_actors_of_interest","Cyber actors of interest","taglist"],
    ]},
  ];

  const dirtyBadge = dirty ? "<span style=\"color:#ffa657\">● unsaved</span>" : "";
  const saveCol = dirty ? "#3fb950" : "#6e7681";
  const saveBg = dirty ? "#1a3a1a" : "#0d1117";
  const saveBd = dirty ? "#238636" : "#21262d";
  const saveCursor = dirty ? "pointer" : "not-allowed";
  const saveDisabled = dirty ? "" : "disabled";
  const saveBtn = "<button onclick=\"saveSite(" + JSON.stringify(site.site_id) + ")\" " + saveDisabled +
    " style=\"font-size:11px;color:" + saveCol + ";background:" + saveBg + ";border:1px solid " + saveBd + ";padding:4px 14px;border-radius:2px;cursor:" + saveCursor + "\">Save site</button>";

  el.innerHTML =
    "<div style=\"display:flex;align-items:center;gap:10px;margin-bottom:12px\">" +
      "<h2 style=\"font-size:13px;color:#e6edf3;margin:0;flex:1\">" + esc(site.name) +
        " <span style=\"color:#6e7681;font-size:10px\">" + esc(site.site_id) + "</span></h2>" +
      dirtyBadge +
    "</div>" +
    groups.map(function (g) { return __ctxGroupBlock(site, g); }).join("") +
    "<div style=\"text-align:right;margin-top:14px\">" + saveBtn + "</div>";

  groups.forEach(function (g) {
    g.fields.forEach(function (tup) {
      const key = tup[0], type = tup[2];
      if (type === "taglist") {
        const cid = "site-" + site.site_id + "-" + key;
        const host = document.getElementById(cid);
        if (host) host.innerHTML = renderTagList(
          site[key] || [],
          function (next) { site[key] = next; __ctxMarkDirty("sites", site.site_id); renderSiteDetail(site); },
          cid
        );
      }
    });
  });
}

function __ctxGroupBlock(site, group) {
  const fieldsHtml = group.fields.map(function (tup) { return __ctxSiteField(site, tup[0], tup[1], tup[2]); }).join("");
  const openAttr = group.open ? " open" : "";
  const summaryStyle = "padding:6px 12px;cursor:pointer;font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:#79c0ff";
  return "<details" + openAttr + " style=\"margin:6px 0;border:1px solid #21262d;border-radius:2px;background:#080c10\">" +
    "<summary style=\"" + summaryStyle + "\">" + esc(group.title) + "</summary>" +
    "<div style=\"padding:8px 12px\">" + fieldsHtml + "</div>" +
  "</details>";
}
```

- [ ] **Step 1c: Add the field-input helper and edit handler:**

```javascript
function __ctxSiteField(site, key, label, type) {
  const value = site[key];
  const id = "site-" + site.site_id + "-" + key;
  const labelHtml = "<label style=\"display:block;font-size:9px;letter-spacing:0.06em;text-transform:uppercase;color:#6e7681;margin:6px 0 2px\">" + esc(label) + "</label>";
  const baseStyle = "width:100%;background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:4px 8px;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px";

  if (type === "readonly") {
    return labelHtml + "<div style=\"" + baseStyle + ";color:#6e7681\">" + esc(value == null ? "-" : String(value)) + "</div>";
  }
  const argsInput  = JSON.stringify(site.site_id) + "," + JSON.stringify(key) + "," + JSON.stringify(type) + ",this.value";
  const argsSelect = JSON.stringify(site.site_id) + "," + JSON.stringify(key) + ",\"text\",this.value";
  const onInput  = "oninput=\"__siteFieldEdit("  + argsInput  + ")\"";
  const onChange = "onchange=\"__siteFieldEdit(" + argsSelect + ")\"";
  if (type === "textarea") {
    return labelHtml + "<textarea id=\"" + id + "\" " + onInput + " style=\"" + baseStyle + ";min-height:40px\">" + esc(value || "") + "</textarea>";
  }
  if (type === "taglist") {
    return labelHtml + "<div id=\"" + id + "\"></div>";
  }
  if (type.indexOf("select:") === 0) {
    const opts = type.split(":")[1].split("|");
    const optsHtml = opts.map(function (o) { return "<option value=\"" + o + "\"" + (value === o ? " selected" : "") + ">" + o + "</option>"; }).join("");
    return labelHtml + "<select id=\"" + id + "\" " + onChange + " style=\"" + baseStyle + "\">" + optsHtml + "</select>";
  }
  const safeVal = esc(value == null ? "" : String(value));
  return labelHtml + "<input type=\"" + type + "\" id=\"" + id + "\" value=\"" + safeVal + "\" " + onInput + " style=\"" + baseStyle + "\">";
}

function __siteFieldEdit(siteId, key, type, value) {
  const site = (contextState.sitesByRegion[contextState.currentRegion] || []).find(function (s) { return s.site_id === siteId; });
  if (!site) return;
  site[key] = type === "number" ? Number(value) : value;
  __ctxMarkDirty("sites", siteId);
  __setSaveButtonEnabled("saveSite(");
}
```

- [ ] **Step 1d: Add the save handler:**

```javascript
async function saveSite(siteId) {
  const site = (contextState.sitesByRegion[contextState.currentRegion] || []).find(function (s) { return s.site_id === siteId; });
  if (!site) return;
  const r = await fetch("/api/context/sites/" + encodeURIComponent(siteId), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(site),
  });
  if (r.ok) {
    contextState.dirty.sites[siteId] = false;
    delete contextState.sitesByRegion[contextState.currentRegion];
    renderSitesSurface();
  } else {
    __showSurfaceError("ctx-site-detail", "Save failed (HTTP " + r.status + "). Stored record is unchanged.");
  }
}
```

- [ ] **Step 2: Smoke test.** Start dev server. Context -> APAC. Select a site. Expand Criticality. Edit `criticality_drivers`. Save site. Re-select that site — value persists. Click a different site mid-edit on another — expect the "Discard unsaved changes?" confirm.

- [ ] **Step 3: Commit.**

```bash
git add static/app.js
git commit -m "feat(context): sites surface (list + detail editor)"
```

---

### Task 15: Regional Profile + Regional Cyber Overlay surface

**Files:** `static/app.js`.

- [ ] **Step 1: Replace the `renderRegionalSurface` stub.** The surface renders Profile + Cyber overlay together, with ONE shared Save button that writes the whole regional record in one atomic PUT:

```javascript
async function renderRegionalSurface() {
  const el = $("ctx-regional");
  if (!el) return;
  const region = contextState.currentRegion;
  if (!contextState.regionalByRegion[region]) {
    contextState.regionalByRegion[region] = await fetch("/api/context/regional/" + region).then(function (r) { return r.ok ? r.json() : {}; });
  }
  const r = contextState.regionalByRegion[region];
  const dirty = !!contextState.dirty.regional[region];
  const dot = dirty ? "<span style=\"color:#ffa657\">●</span>" : "";

  const saveCol = dirty ? "#3fb950" : "#6e7681";
  const saveBg = dirty ? "#1a3a1a" : "#0d1117";
  const saveBd = dirty ? "#238636" : "#21262d";
  const saveCursor = dirty ? "pointer" : "not-allowed";
  const saveDisabled = dirty ? "" : "disabled";
  const saveBtn = "<button onclick=\"saveRegional()\" " + saveDisabled +
    " style=\"font-size:11px;color:" + saveCol + ";background:" + saveBg + ";border:1px solid " + saveBd + ";padding:4px 14px;border-radius:2px;cursor:" + saveCursor + "\">Save region</button>";

  const taStyle = "width:100%;background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:6px 8px;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px;min-height:50px";
  const sectionHdr = "font-size:10px;color:#79c0ff;margin:6px 0 4px";

  el.innerHTML =
    "<div style=\"background:#0d1117;border:1px solid #21262d;border-radius:4px;padding:14px 18px\">" +
      "<div style=\"display:flex;align-items:center;gap:8px;margin-bottom:10px\">" +
        "<span style=\"font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681\">Regional - " + region + "</span>" + dot +
        "<span style=\"margin-left:auto;font-size:10px;color:#8b949e\">headcount: " + (r.headcount || 0) + " - contractors: " + (r.contractors || 0) + "</span>" +
      "</div>" +

      "<label style=\"display:block;font-size:9px;letter-spacing:0.06em;text-transform:uppercase;color:#6e7681;margin:6px 0 2px\">Regional summary</label>" +
      "<textarea id=\"reg-summary\" oninput=\"__regionalFieldEdit('regional_summary', this.value)\" style=\"" + taStyle + "\">" + esc(r.regional_summary || "") + "</textarea>" +

      "<label style=\"display:block;font-size:9px;letter-spacing:0.06em;text-transform:uppercase;color:#6e7681;margin:10px 0 2px\">Standing notes</label>" +
      "<textarea id=\"reg-standing\" oninput=\"__regionalFieldEdit('standing_notes', this.value)\" style=\"" + taStyle + "\">" + esc(r.standing_notes || "") + "</textarea>" +

      "<details style=\"margin-top:14px;border:1px solid #21262d;border-radius:2px;background:#080c10\">" +
        "<summary style=\"padding:6px 12px;cursor:pointer;font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:#79c0ff\">Regional cyber overlay</summary>" +
        "<div style=\"padding:8px 12px\">" +
          "<div style=\"" + sectionHdr + "\">Regional threat actor groups</div><div id=\"reg-actors\"></div>" +
          "<div style=\"" + sectionHdr + "\">Regional sector targeting campaigns</div><div id=\"reg-campaigns\"></div>" +
          "<div style=\"" + sectionHdr + "\">Regional geographies of concern</div><div id=\"reg-geos\"></div>" +
          "<div style=\"" + sectionHdr + "\">Regional standing notes (cyber tempo)</div>" +
          "<textarea id=\"reg-cyber-notes\" oninput=\"__regionalFieldEdit('regional_standing_notes', this.value)\" style=\"" + taStyle + ";min-height:40px\">" + esc(r.regional_standing_notes || "") + "</textarea>" +
        "</div>" +
      "</details>" +

      "<div style=\"text-align:right;margin-top:14px\">" + saveBtn + "</div>" +
    "</div>";

  const rlOnChange = function (assign) {
    return function (next, info) {
      assign(next);
      __ctxMarkDirty("regional");
      if (info && info.kind === "structure") {
        renderRegionalSurface();
      } else {
        __setSaveButtonEnabled("saveRegional()");
      }
    };
  };
  const tlOnChange = function (assign) {
    return function (next) {
      assign(next);
      __ctxMarkDirty("regional");
      renderRegionalSurface();  // Tag List changes are always structural
    };
  };

  $("reg-actors").innerHTML = renderRecordList(
    r.regional_threat_actor_groups || [], [
      { key: "name", label: "Name", type: "text" },
      { key: "aliases", label: "Aliases", type: "taglist" },
      { key: "motivation", label: "Motivation", type: "text" },
      { key: "target_sectors", label: "Target sectors", type: "taglist" },
      { key: "target_geographies", label: "Target geographies", type: "taglist" },
    ],
    function (rec) { return (rec.name || "(unnamed)") + (rec.motivation ? " - " + rec.motivation : ""); },
    rlOnChange(function (next) { r.regional_threat_actor_groups = next; }),
    "reg-actors-" + region
  );
  $("reg-campaigns").innerHTML = renderRecordList(
    r.regional_sector_targeting_campaigns || [], [
      { key: "campaign_name", label: "Campaign", type: "text" },
      { key: "actor", label: "Actor", type: "text" },
      { key: "sectors", label: "Sectors", type: "taglist" },
      { key: "first_observed", label: "First observed", type: "text" },
      { key: "status", label: "Status", type: "text" },
    ],
    function (rec) { return (rec.campaign_name || "(unnamed)") + (rec.actor ? " / " + rec.actor : ""); },
    rlOnChange(function (next) { r.regional_sector_targeting_campaigns = next; }),
    "reg-campaigns-" + region
  );
  $("reg-geos").innerHTML = renderTagList(
    r.regional_cyber_geographies_of_concern || [],
    tlOnChange(function (next) { r.regional_cyber_geographies_of_concern = next; }),
    "reg-geos-" + region
  );
}

function __regionalFieldEdit(key, value) {
  const region = contextState.currentRegion;
  const r = contextState.regionalByRegion[region];
  if (!r) return;
  r[key] = value;
  __ctxMarkDirty("regional");
  __setSaveButtonEnabled("saveRegional()");
}

async function saveRegional() {
  const region = contextState.currentRegion;
  const body = contextState.regionalByRegion[region];
  const resp = await fetch("/api/context/regional/" + region, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (resp.ok) {
    contextState.dirty.regional[region] = false;
    delete contextState.regionalByRegion[region];
    renderRegionalSurface();
  } else {
    __showSurfaceError("ctx-regional", "Save failed (HTTP " + resp.status + "). Stored file is unchanged.");
  }
}
```

- [ ] **Step 2: Smoke test.** Context -> APAC. Scroll to Regional panel. Edit Regional summary. Click Save region. Refresh — persists. Expand Regional cyber overlay. Add a geography. Save. Verify.

- [ ] **Step 3: Commit.**

```bash
git add static/app.js
git commit -m "feat(context): regional profile + cyber overlay surface"
```

---

### Task 16: Cross-tab + reload dirty guards

**Files:** `static/app.js`.

- [ ] **Step 1: Extend the top-level `switchTab` dirty guard at line 1751-1757.** Find:

```javascript
function switchTab(tab) {
  if (cfgState.dirty.topics || cfgState.dirty.sources) {
    showUnsavedModal(() => _doSwitchTab(tab));
    return;
  }
  _doSwitchTab(tab);
}
```

Replace with:

```javascript
function switchTab(tab) {
  if (cfgState.dirty.topics || cfgState.dirty.sources) {
    showUnsavedModal(() => _doSwitchTab(tab));
    return;
  }
  if (typeof anyContextSurfaceDirty === "function" && anyContextSurfaceDirty()) {
    if (!confirm("You have unsaved changes in the Context tab. Discard?")) return;
    contextState.dirty = { company: false, cyberWatchlist: false, regional: {}, sites: {} };
    contextState.company = null;
    contextState.cyberWatchlist = null;
    contextState.sitesByRegion = {};
    contextState.regionalByRegion = {};
  }
  _doSwitchTab(tab);
}
```

- [ ] **Step 2: Add `beforeunload` guard at EOF of `static/app.js`:**

```javascript
window.addEventListener("beforeunload", function (e) {
  if (typeof anyContextSurfaceDirty === "function" && anyContextSurfaceDirty()) {
    e.preventDefault();
    e.returnValue = "";
    return "";
  }
});
```

- [ ] **Step 3: Smoke test.** Context -> Global, edit Company name but don't save. Click Overview tab — expect confirm. Cancel — stays on Context. Click Overview, confirm — switches. Reload mid-edit — expect browser beforeunload prompt.

- [ ] **Step 4: Commit.**

```bash
git add static/app.js
git commit -m "feat(context): cross-tab + reload dirty guards"
```

---

### Task 17: Retire Config -> Footprint sub-tab

**Files:** `static/index.html`, `static/app.js`, `server.py`, possibly `tests/`.

- [ ] **Step 1: Confirm new regional endpoint works.** With dev server running:

Run: `curl http://localhost:8001/api/context/regional/APAC`
Expected: 200 with `regional_summary`, `standing_notes`, `headcount`, `contractors` keys.

- [ ] **Step 2: Remove the sub-tab nav + panel in `static/index.html`.** Use symbolic anchors — line numbers from the spec may be stale after Tasks 9-16.

Delete the nav entry. Search for and delete:

```html
<div class="nav-tab" id="cfg-nav-footprint" onclick="switchCfgTab('footprint')">Footprint</div>
```

Delete the sub-panel. Search for the three-line block and delete it:

```html
  <!-- Footprint sub-tab -->
  <div id="cfg-tab-footprint" style="display:none;flex:1;overflow-y:auto;padding:16px 20px">
    <div id="footprint-panels"></div>
  </div>
```

- [ ] **Step 3: Remove JS code in `static/app.js` by name.** Locate and delete:

- The `if (tab === 'footprint') loadFootprint();` line inside `switchCfgTab` (search exact string).
- Function declarations: `loadFootprint`, `renderFootprint`, `toggleFpRegion`, `markFpDirty`, `saveFpRegion` — delete each function definition and body.
- References to `cfgState.footprintLoaded`, `cfgState.footprintData`, `cfgState.footprintDirty` (delete the references; keep the rest of `cfgState`).
- Any `.fp-*` CSS class definitions that have no remaining live usages.

After deletions, verify:

```bash
grep -n "footprint\|fp-\|loadFootprint\|renderFootprint" static/app.js static/index.html
```

Expected: zero matches in live code paths. Comments mentioning the historical name are acceptable.

- [ ] **Step 4: Remove server endpoints in `server.py` by symbol.** Delete both handlers:

```python
@app.get("/api/footprint")
async def get_footprint():
    ...
```

```python
@app.put("/api/footprint/{region}")
async def update_footprint(region: str, body: dict):
    ...
```

Find each by decorator string, delete the decorator line plus the entire function body through the blank line before the next `@app.` handler.

- [ ] **Step 5: Clean up any tests that referenced the removed endpoints.**

Run: `grep -rn "/api/footprint" tests/`
- If any tests hit `/api/footprint`, delete just those test functions. The new endpoint is covered in `tests/test_context_api.py`.

- [ ] **Step 6: Run full test suite.**

Run: `uv run pytest -x --tb=short 2>&1 | tail -40`
Expected: all tests pass.

- [ ] **Step 7: Smoke test.** Open Config tab. Confirm only "Intelligence Sources" sub-tab exists. Context -> APAC. Confirm Regional panel still works end-to-end.

- [ ] **Step 8: Commit.**

```bash
git add static/index.html static/app.js server.py tests/
git commit -m "feat(context): retire Config -> Footprint sub-tab"
```

---

### Task 18: Context-flow matrix — stub + deferred audit

**Files:** `docs/context-flow-matrix.md` (new, stub-only).

The full matrix requires reading ~8 reader modules + 4 agent definitions and recording every field-access with `file:line`. That audit is an independent research workstream — doing it well takes a dedicated session and its own spec review. Shipping a half-populated matrix alongside the UI feature would commit the wrong thing.

This task ships a **stub** that declares the schema and commits an empty table with a clear TODO pointing to the dedicated workstream. The audit becomes its own follow-up task (tracked in memory, not in this plan).

- [ ] **Step 1: Create `docs/context-flow-matrix.md`** with the schema and a deferral note:

````markdown
# Context Flow Matrix

**Status:** Schema committed; audit deferred to a dedicated workstream.

## Purpose

For every agent in the pipeline, document which context fields it reads at runtime, what outputs it produces, and which deliverables those outputs land in. This is the input-side companion to the output-side spec at `docs/superpowers/specs/2026-04-20-context-tab-design.md`.

## Schema

| Column | Meaning |
|---|---|
| `agent` | Agent identifier (from `.claude/agents/*.md` or `tools/source_librarian/*`) |
| `context_fields_read` | `file.field` pairs read at runtime — one entry per distinct field-access |
| `produces` | Names of outputs the agent writes |
| `downstream_consumers` | Deliverables that include this output (CISO brief, Board report, RSM brief, Risk Register, etc.) |
| `source_ref` | `path/to/file.py:line` where the read or write happens |

## Agents to cover (audit pending)

- `gatekeeper-agent` — `.claude/agents/gatekeeper-agent.md`
- `regional-analyst-agent` — `.claude/agents/regional-analyst-agent.md`
- `global-builder-agent` — `.claude/agents/global-builder-agent.md`
- `rsm-formatter-agent` — `.claude/agents/rsm-formatter-agent.md`
- Source librarian — `tools/source_librarian/intents.py`, `discovery.py`

## Reader modules to audit

- `tools/build_context.py`
- `tools/rsm_input_builder.py`
- `tools/poi_proximity.py`
- `tools/seerist_collector.py`
- `tools/threshold_evaluator.py`
- `.claude/hooks/validators/rsm-brief-context-checks.py`

## Audit procedure (for the follow-up workstream)

1. For each agent file, list every context field its system prompt explicitly names (grep the markdown file).
2. For each reader module, grep for `site[`, `site.get(`, `regional_footprint`, `company_profile`, `cyber_watchlist` and record every field-access with line number.
3. Join (agent × field) via the agent's prompt reference → the actual reader code invoked for that agent.
4. Record one row per (agent, field) pair.

## Derived fields (already known)

- `headcount` — `tools/context_api.derive_headcount` (called from `GET/PUT /api/context/regional/{region}`). Input: `aerowind_sites.json`. Output: integer sum.
- `contractors` — same function, second return value.

## Capture-surface fields (not yet read by any agent)

Fields present in the Context schema that no agent currently reads. These are forward-looking:

- `cyber_watchlist.threat_actor_groups[]` — will drive per-site cyber callouts in RSM briefs once the formatter is extended.
- `regional_footprint.regional_threat_actor_groups[]` — not yet consumed.
- `regional_footprint.regional_sector_targeting_campaigns[]` — not yet consumed.
- `regional_footprint.regional_cyber_geographies_of_concern[]` — not yet consumed.
- `regional_footprint.regional_standing_notes` — not yet consumed.

When the RSM weekly/daily/flash formatter is extended to read these, move them out of this list and into the agent rows above.
````

- [ ] **Step 2: Add a project-memory note** for the follow-up audit so it doesn't get lost. Append to `C:\Users\frede\.claude\projects\c--Users-frede-crq-agent-workspace\memory\MEMORY.md` under "Upcoming Work":

```markdown
- **Context-flow matrix audit** — populate `docs/context-flow-matrix.md` with per-field `file:line` entries for all pipeline agents. Stub schema committed as part of Context tab v1; audit is its own session.
```

- [ ] **Step 3: Commit.**

```bash
git add docs/context-flow-matrix.md C:/Users/frede/.claude/projects/c--Users-frede-crq-agent-workspace/memory/MEMORY.md
git commit -m "docs(context): context-flow matrix stub + schema (audit deferred)"
```

---

### Task 19: End-to-end verification

**Files:** None; this is test + verification.

- [ ] **Step 1: Run the context-api test suite.**

Run: `uv run pytest tests/test_context_api.py -v`
Expected: every test passes.

- [ ] **Step 2: Run the whole test suite — check for regressions.**

Run: `uv run pytest -x --tb=short 2>&1 | tail -40`
Expected: all tests pass.

- [ ] **Step 3: Verify legacy alias double-write still feeds `tools/build_context.py`.** The module entry point is `build_context(region: str) -> None` (verified at `tools/build_context.py:35`) — it has side effects (writes files) rather than returning a string, so this step runs it and then checks the output.

Before running: `git diff --stat output/` to record existing state.

```bash
uv run python -c "from tools.build_context import build_context; build_context('APAC')"
```

Then inspect the produced context file (path depends on the module's write target — read `tools/build_context.py` lines 35-67 to confirm). Expected: the written output contains the APAC headcount, and the number matches `sum(personnel_count + expat_count)` across APAC sites in `data/aerowind_sites.json`.

- [ ] **Step 4: End-to-end functional verification — spec success criterion 7.** The CRQ regional pipeline is invoked as a Claude Code slash command, not a Python CLI. Exact invocation:

  (a) Start server: `uv run uvicorn server:app --port 8001` (background).
  (b) Open the UI. Context -> APAC. Select Kaohsiung. Change `tier` from `crown_jewel` to `primary`. Save site.
  (c) In Claude Code, run: `/crq-region APAC`
    The slash command is defined at `.claude/commands/crq-region.md` — it dispatches the gatekeeper + regional-analyst pipeline for the named region. No `--mock` flag is needed if the mock fixtures are already in place; confirm by reading the command's `## INPUT` and early-step sections.
  (d) Inspect `output/regional/apac/sections.json` — search for Kaohsiung references. The gatekeeper's scenario match and the regional-analyst's criticality framing should reflect `primary`, not `crown_jewel`.
  (e) Revert the tier change through the UI. Save. Confirm `data/aerowind_sites.json` is back to its committed state (`git diff data/aerowind_sites.json` returns empty).

- [ ] **Step 5: Record verification with an empty commit.**

```bash
git commit --allow-empty -m "test(context): e2e verified — tier edit reflected in /crq-region APAC output"
```

---

## Self-review

**Spec coverage:**
- In-scope item 1 (new Context tab) -> Task 9
- In-scope item 2 (region-first nav) -> Task 9
- In-scope item 3 (four UI surfaces) -> Tasks 12, 13, 14, 15
- In-scope item 4 (four backing files) -> Tasks 1-8 read/write; new cyber_watchlist.json created by Task 4
- In-scope item 5 (API PUT-replace) -> Tasks 1-8
- In-scope item 6 (Footprint retirement) -> Task 17
- In-scope item 7 (context-flow matrix) -> Task 18
- Spec Data Model sections -> backing-file structure enforced by Tasks 1-8 helpers
- Spec UI Primitives (Tag List, Record List) -> Tasks 10-11
- Spec Dirty-state rules -> Task 14 (sites list-click guard) and Task 16 (cross-tab + reload guards)
- Spec Test Plan (11 items) -> 10 covered by unit tests in Tasks 1-8; item 11 (Footprint-gone smoke) is Task 17 step 7
- Success criterion 7 (end-to-end tier edit) -> Task 19 step 4

**Placeholder scan:** Task 18 is a schema + deferral stub (not a half-populated matrix). Explicitly marked as "audit deferred to a dedicated workstream"; the stub commits the schema and moves the audit to memory as follow-up work. No cell reads `...` in the committed artifact.

**Type consistency:**
- Helpers: `atomic_write_json`, `empty_cyber_watchlist`, `replace_site_in_registry`, `derive_headcount`, `load_regional_record`, `write_regional_record` — referenced identically across tasks.
- JS functions: `renderContextTab`, `renderContextRegionStrip`, `switchContextRegion`, `anyContextSurfaceDirty`, `renderCompanySurface`, `renderGlobalCyberWatchlistSurface`, `renderSitesSurface`, `renderSiteDetail`, `renderRegionalSurface`, `saveCompany`, `saveCyberWatchlist`, `saveSite`, `saveRegional`, `__ctxField`, `__ctxFieldEdit`, `__ctxMarkDirty`, `__ctxSiteField`, `__ctxGroupBlock`, `__siteFieldEdit`, `__setSaveButtonEnabled`, `__showSurfaceError`, `__tlAdd`, `__tlRemove`, `__rlAdd`, `__rlRemove`, `__rlToggle`, `__rlFieldChange`, `__rlFieldInput` — consistent across tasks.
- State: `contextState.dirty.company`, `contextState.dirty.cyberWatchlist`, `contextState.dirty.regional[region]`, `contextState.dirty.sites[site_id]` — consistent.
- API paths: `/api/context/company`, `/api/context/cyber-watchlist`, `/api/context/sites`, `/api/context/regional/{region}` — identical in server, tests, and client code.

**Rev v2 fixes applied:**
- Record List `onChange(records, info)` signature — `kind: "mutate"` on field edits (no re-render, preserves focus) vs `kind: "structure"` on add/remove (full re-render). Tasks 13 and 15 updated to check `info.kind`.
- Shared helpers `__setSaveButtonEnabled` and `__showSurfaceError` replace scattered `alert()` and inline DOM toggling; error banners land inline inside the surface per spec.
- Task 17 line-number anchors replaced with symbolic anchors (function names, exact search strings) since Tasks 9-16 shift line counts.
- Task 19 step 3: correct entry point is `tools.build_context.build_context(region)` (returns None, writes files) — not the invented `build_region_context`.
- Task 19 step 4: CRQ regional pipeline is the `/crq-region APAC` slash command, not `tools/run_region.py`.
- Task 5 fixture-count assertion replaced with region-membership assertion (`site_id in site_ids`) so future seed additions don't break the test.
- Dirty-state indicator changed from `*` (asterisk) to `●` (U+25CF bullet) per spec wording.
- Task 8 step 6: added malformed-JSON tests for PUT endpoints.

**Open issues:** None.
