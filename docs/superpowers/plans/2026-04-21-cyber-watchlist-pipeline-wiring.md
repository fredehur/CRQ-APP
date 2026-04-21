# Cyber Watchlist Pipeline Wiring — Implementation Plan

**Goal:** Wire `data/cyber_watchlist.json` into agent prompt injection and signal collection so every pipeline run automatically uses the global threat actor watchlist.

**Architecture:** Three independent changes, each gracefully degrading when `cyber_watchlist.json` is absent. `build_context.py` appends a `[GLOBAL CYBER WATCHLIST]` section to the context block injected into agent prompts. `osint_collector.py` passes threat actor names and CVE categories into the working theory LLM prompt to sharpen cyber query generation. `seerist_collector.py` (live mode only) stamps `analytical.threat_actor_context` onto output so downstream agents see which actors were on watch at collection time.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `pathlib`, `json`

---

## File Structure

| File | Change |
|---|---|
| `tools/build_context.py` | Add `WATCHLIST_FILE` constant, `_format_watchlist_block()`, extend `build_context()` |
| `tools/osint_collector.py` | Add `_load_cyber_watchlist()`, extend `form_working_theory()` signature + prompt, update `run_live_mode()` call site |
| `tools/seerist_collector.py` | Extend `_live_collect()` to load watchlist and stamp `analytical.threat_actor_context` |
| `tests/test_build_context.py` | Add 2 tests: watchlist appended when present, missing file → no watchlist section |
| `tests/test_osint_collector.py` | Add 2 tests: watchlist appears in LLM prompt, no crash when watchlist absent |

---

## Task 1: build_context.py — watchlist block injection

**Files:**
- Modify: `tools/build_context.py`
- Test: `tests/test_build_context.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_build_context.py`:

```python
MINIMAL_WATCHLIST = {
    "threat_actor_groups": [
        {"name": "APT40", "motivation": "espionage", "aliases": ["BRONZE MOHAWK"]}
    ],
    "sector_targeting_campaigns": [
        {"campaign_name": "VOLT TYPHOON ICS", "actor": "Volt Typhoon", "sectors": ["energy"]}
    ],
    "cve_watch_categories": ["ICS/SCADA", "VPN appliances"],
    "global_cyber_geographies_of_concern": ["China", "Russia"],
}


def _patch_with_watchlist(monkeypatch, tmp_path, footprint_data, watchlist_data):
    fp, output_dir = _patch(monkeypatch, tmp_path, footprint_data)
    wl_path = tmp_path / "cyber_watchlist.json"
    wl_path.write_text(json.dumps(watchlist_data), encoding="utf-8")
    monkeypatch.setattr(bc, "WATCHLIST_FILE", wl_path)
    return fp, output_dir


def test_watchlist_appended_when_present(monkeypatch, tmp_path):
    """Watchlist threat actors appear in context block when file exists."""
    _, output_dir = _patch_with_watchlist(monkeypatch, tmp_path, MINIMAL_FOOTPRINT, MINIMAL_WATCHLIST)
    bc.build_context("APAC")
    text = (output_dir / "regional" / "apac" / "context_block.txt").read_text(encoding="utf-8")
    assert "GLOBAL CYBER WATCHLIST" in text
    assert "APT40" in text
    assert "VOLT TYPHOON ICS" in text
    assert "ICS/SCADA" in text


def test_watchlist_absent_when_file_missing(monkeypatch, tmp_path):
    """Missing cyber_watchlist.json → context block contains no watchlist section."""
    _, output_dir = _patch(monkeypatch, tmp_path, MINIMAL_FOOTPRINT)
    monkeypatch.setattr(bc, "WATCHLIST_FILE", tmp_path / "cyber_watchlist.json")  # does not exist
    bc.build_context("APAC")
    text = (output_dir / "regional" / "apac" / "context_block.txt").read_text(encoding="utf-8")
    assert "GLOBAL CYBER WATCHLIST" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_build_context.py::test_watchlist_appended_when_present tests/test_build_context.py::test_watchlist_absent_when_file_missing -v`
Expected: FAIL — `AttributeError: module 'tools.build_context' has no attribute 'WATCHLIST_FILE'`

- [ ] **Step 3: Implement in build_context.py**

Add after line 18 (`KNOWN_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}`):

```python
WATCHLIST_FILE = Path("data/cyber_watchlist.json")
```

Add the new `_format_watchlist_block` function after `_format_context_block` (before `# ── CLI` at line 118):

```python
def _format_watchlist_block(watchlist: dict) -> str:
    lines = ["", "[GLOBAL CYBER WATCHLIST]"]

    actors = watchlist.get("threat_actor_groups", [])
    if actors:
        lines.append("Threat Actors:")
        for a in actors:
            aliases = ", ".join(a.get("aliases", []))
            alias_str = f" (aka {aliases})" if aliases else ""
            lines.append(f"  - {a.get('name', '')}{alias_str} — {a.get('motivation', '')}")

    campaigns = watchlist.get("sector_targeting_campaigns", [])
    if campaigns:
        lines.append("Active Campaigns:")
        for c in campaigns:
            lines.append(
                f"  - {c.get('campaign_name', '')} / {c.get('actor', '')} "
                f"— sectors: {', '.join(c.get('sectors', []))}"
            )

    cves = watchlist.get("cve_watch_categories", [])
    if cves:
        lines.append(f"CVE Watch Categories: {' | '.join(cves)}")

    geos = watchlist.get("global_cyber_geographies_of_concern", [])
    if geos:
        lines.append(f"Cyber Geographies of Concern: {', '.join(geos)}")

    return "\n".join(lines)
```

In `build_context()`, replace the line:
```python
    out_path.write_text(block, encoding="utf-8")
```
with:
```python
    if WATCHLIST_FILE.exists():
        try:
            watchlist = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
            has_content = any([
                watchlist.get("threat_actor_groups"),
                watchlist.get("sector_targeting_campaigns"),
                watchlist.get("cve_watch_categories"),
                watchlist.get("global_cyber_geographies_of_concern"),
            ])
            if has_content:
                block += _format_watchlist_block(watchlist)
        except Exception:
            pass
    out_path.write_text(block, encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_build_context.py -v`
Expected: All 9 tests PASS (7 existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add tools/build_context.py tests/test_build_context.py
git commit -m "feat(context): append global cyber watchlist to regional context blocks"
```

---

## Task 2: osint_collector.py — watchlist-augmented working theory

**Files:**
- Modify: `tools/osint_collector.py`
- Test: `tests/test_osint_collector.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_osint_collector.py`:

```python
import tools.osint_collector as oc


MINIMAL_WATCHLIST = {
    "threat_actor_groups": [
        {"name": "APT40", "motivation": "espionage", "aliases": ["BRONZE MOHAWK"]}
    ],
    "sector_targeting_campaigns": [
        {"campaign_name": "VOLT TYPHOON ICS", "actor": "Volt Typhoon", "sectors": ["energy"]}
    ],
    "cve_watch_categories": ["ICS/SCADA"],
    "global_cyber_geographies_of_concern": ["China"],
}

MINIMAL_COMPANY = {
    "industry": "Wind Turbine Manufacturing",
    "crown_jewels": ["OT/SCADA networks", "turbine aerodynamic designs"],
}

MOCK_CRQ = {"APAC": [{"scenario_name": "Supply Chain Attack", "value_at_cyber_risk_usd": 1_000_000}]}

MOCK_LLM_RESPONSE = {
    "hypothesis": "APAC faces elevated risk from APT40 targeting OT networks.",
    "geo_queries": ["Taiwan geopolitical tension wind energy", "APAC supply chain disruption"],
    "cyber_queries": ["APT40 ICS targeting wind", "Volt Typhoon SCADA intrusion"],
}


def test_form_working_theory_includes_watchlist_in_prompt(monkeypatch):
    """Watchlist actor and campaign names appear in the LLM prompt when watchlist is supplied."""
    captured_prompts = []

    def mock_llm(prompt, **kwargs):
        captured_prompts.append(prompt)
        return MOCK_LLM_RESPONSE

    monkeypatch.setattr(oc, "_call_llm", mock_llm)
    oc.form_working_theory("APAC", MOCK_CRQ, [], MINIMAL_COMPANY, MINIMAL_WATCHLIST)
    assert len(captured_prompts) == 1
    assert "APT40" in captured_prompts[0]
    assert "VOLT TYPHOON ICS" in captured_prompts[0]


def test_form_working_theory_no_watchlist_no_crash(monkeypatch):
    """form_working_theory with no watchlist arg runs without error and returns expected keys."""
    monkeypatch.setattr(oc, "_call_llm", lambda *a, **kw: MOCK_LLM_RESPONSE)
    result = oc.form_working_theory("APAC", MOCK_CRQ, [], MINIMAL_COMPANY)
    assert "hypothesis" in result
    assert "cyber_queries" in result
    assert "geo_queries" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_osint_collector.py::test_form_working_theory_includes_watchlist_in_prompt tests/test_osint_collector.py::test_form_working_theory_no_watchlist_no_crash -v`
Expected: FAIL — `TypeError: form_working_theory() takes 4 positional arguments but 5 were given`

- [ ] **Step 3: Implement in osint_collector.py**

**3a.** Add `_load_cyber_watchlist` helper after `_load_json` (around line 347):

```python
def _load_cyber_watchlist() -> dict:
    """Load cyber_watchlist.json from data/. Returns empty dict if absent or malformed."""
    path = REPO_ROOT / "data" / "cyber_watchlist.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
```

**3b.** Change `form_working_theory` signature (line 119) from:

```python
def form_working_theory(region: str, crq_data: dict, topics: list, company_profile: dict) -> dict:
```

to:

```python
def form_working_theory(region: str, crq_data: dict, topics: list, company_profile: dict, cyber_watchlist: dict | None = None) -> dict:
```

**3c.** Inside `form_working_theory`, add the `watchlist_section` variable immediately before the `prompt = f"""...` line:

```python
    watchlist_section = ""
    if cyber_watchlist:
        actors = [a.get("name", "") for a in cyber_watchlist.get("threat_actor_groups", []) if a.get("name")]
        campaigns = [c.get("campaign_name", "") for c in cyber_watchlist.get("sector_targeting_campaigns", []) if c.get("campaign_name")]
        cves = cyber_watchlist.get("cve_watch_categories", [])
        parts = []
        if actors:
            parts.append(f"Actors: {', '.join(actors)}")
        if campaigns:
            parts.append(f"Campaigns: {', '.join(campaigns)}")
        if cves:
            parts.append(f"CVE Categories: {', '.join(cves)}")
        if parts:
            watchlist_section = "\nTHREAT ACTOR WATCHLIST (prioritize signals from these actors):\n" + "\n".join(parts)
```

**3d.** In the `prompt = f"""...` string, insert `{watchlist_section}` after the `CROWN JEWELS:` line:

```python
    prompt = f"""You are forming a target-centric intelligence collection hypothesis.

REGION: {region}
CRQ SCENARIO: {scenario_name}
VALUE AT CYBER RISK: ${vacr:,}
COMPANY: {company_profile.get("industry", "Wind Energy")} operator
CROWN JEWELS: {json.dumps(company_profile.get("crown_jewels", []))}
ACTIVE TOPICS FOR THIS REGION: {json.dumps(active_topics)}{watchlist_section}

Form a working theory: is there evidence that the {scenario_name} scenario is materializing in {region}?
...
```

(Keep all existing text after `ACTIVE TOPICS FOR THIS REGION:` unchanged. Only insert `{watchlist_section}` on its own line after the active topics line.)

**3e.** In `run_live_mode()`, add before the `form_working_theory` call (around line 388):

```python
    cyber_watchlist = _load_cyber_watchlist()
```

And change the `form_working_theory` call from:

```python
    working_theory = form_working_theory(region, crq_data, topics, company_profile)
```

to:

```python
    working_theory = form_working_theory(region, crq_data, topics, company_profile, cyber_watchlist)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_osint_collector.py -v`
Expected: All 5 tests PASS (3 existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add tools/osint_collector.py tests/test_osint_collector.py
git commit -m "feat(osint): inject global cyber watchlist into working theory prompt"
```

---

## Task 3: seerist_collector.py — threat actor context stamp

No new tests — `_live_collect` requires a live Seerist API key and the mock path reads static fixtures (unchanged). This is additive metadata only.

**Files:**
- Modify: `tools/seerist_collector.py`

- [ ] **Step 1: Implement in seerist_collector.py**

In `_live_collect()`, add the following block immediately before `return result` (at the end of the function):

```python
    # Stamp watchlist context for downstream agents — non-fatal if absent
    watchlist_path = REPO_ROOT / "data" / "cyber_watchlist.json"
    threat_actor_context: list[str] = []
    if watchlist_path.exists():
        try:
            wl = json.loads(watchlist_path.read_text(encoding="utf-8"))
            for actor in wl.get("threat_actor_groups", []):
                name = actor.get("name", "")
                aliases = actor.get("aliases", [])
                if name:
                    threat_actor_context.append(name)
                threat_actor_context.extend(a for a in aliases if a)
        except Exception:
            pass
    result["analytical"]["threat_actor_context"] = threat_actor_context
```

- [ ] **Step 2: Verify no regressions**

Run: `uv run pytest tests/ -v -x --ignore=tests/test_ui.py`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add tools/seerist_collector.py
git commit -m "feat(seerist): stamp threat_actor_context from watchlist onto live collection output"
```

---

## Self-Review

**Spec coverage:**
- Wire cyber_watchlist.json into agent prompts → Task 1 (build_context.py) ✓
- Wire cyber_watchlist.json into OSINT signal collection → Task 2 (osint_collector.py) ✓
- Wire cyber_watchlist.json into Seerist signal collection → Task 3 (seerist_collector.py) ✓
- Graceful degradation when file absent → all three tasks handle missing file silently ✓

**Placeholder scan:** None. All code blocks are complete and exact.

**Type consistency:**
- `_format_watchlist_block(watchlist: dict) -> str` — defined Task 1, used Task 1 only ✓
- `form_working_theory(..., cyber_watchlist: dict | None = None)` — defined Task 2, called Task 2 ✓
- `_load_cyber_watchlist() -> dict` — defined and called Task 2 only ✓
- `threat_actor_context: list[str]` — defined and stamped Task 3 only ✓
