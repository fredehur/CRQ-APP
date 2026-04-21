# Cyber Watchlist Wiring — Scribe + RSM Gaps

**Goal:** Close the last two gaps where `data/cyber_watchlist.json` isn't consulted by pipeline code that should use it.

**Architecture:** Same graceful-degradation pattern as Phase 2 — load watchlist with try/except, default to empty/None, use as supplement (never replace) existing logic.

**Tech Stack:** Python stdlib (`json`, `pathlib`), pytest.

---

## Gap A — Scribe enrichment ignores watchlist actors

**Problem:** `tools/scribe_enrichment.py::_extract_actor_if_clean` has a hardcoded set of 8 known actors. Watchlist actors outside that set (e.g. "APT40", "BlackByte") never trigger a WoD actor-search query, so Seerist queries miss the org's declared priority actors.

**Fix:** Load `threat_actor_groups[*].name` + `aliases[]` from `data/cyber_watchlist.json` and merge with the hardcoded set at call time.

### Task A1: failing test + implementation

**Files:**
- Modify: `tools/scribe_enrichment.py` — add watchlist loader, merge in `_extract_actor_if_clean`
- Modify: `tests/test_scribe_enrichment.py` — add 2 tests

- [ ] **Step 1: Write failing tests**

```python
# append to tests/test_scribe_enrichment.py

def test_watchlist_actor_picked_up(monkeypatch, tmp_path):
    """Actor listed in cyber_watchlist.json (but not hardcoded) is detected."""
    import tools.scribe_enrichment as se

    watchlist_path = tmp_path / "cyber_watchlist.json"
    watchlist_path.write_text(json.dumps({
        "threat_actor_groups": [
            {"name": "APT40", "aliases": ["BRONZE MOHAWK"], "motivation": "espionage"}
        ]
    }), encoding="utf-8")
    monkeypatch.setattr(se, "WATCHLIST_FILE", watchlist_path)

    osint = {"dominant_pillar": "Cyber", "lead_indicators": [
        {"text": "Reports of APT40 reconnaissance against regional grid operators"}
    ]}
    actor = se._extract_actor_if_clean(osint)
    assert actor == "APT40"


def test_watchlist_missing_does_not_crash(monkeypatch, tmp_path):
    """Absent watchlist file falls back to hardcoded set without error."""
    import tools.scribe_enrichment as se
    monkeypatch.setattr(se, "WATCHLIST_FILE", tmp_path / "does_not_exist.json")

    osint = {"dominant_pillar": "Cyber", "lead_indicators": [
        {"text": "Volt Typhoon activity observed"}
    ]}
    actor = se._extract_actor_if_clean(osint)
    assert actor == "Volt Typhoon"  # hardcoded fallback still works
```

Also add at top of file: `import json`

- [ ] **Step 2: Run tests to confirm failure**

Run: `uv run pytest tests/test_scribe_enrichment.py::test_watchlist_actor_picked_up -v`
Expected: FAIL — `WATCHLIST_FILE` attribute missing.

- [ ] **Step 3: Implement**

In `tools/scribe_enrichment.py`, add after the existing imports:

```python
WATCHLIST_FILE = REPO_ROOT / "data" / "cyber_watchlist.json"
```

Add a helper above `_extract_actor_if_clean`:

```python
def _load_watchlist_actors() -> set[str]:
    """Return set of actor names + aliases from cyber_watchlist.json, or empty set."""
    if not WATCHLIST_FILE.exists():
        return set()
    try:
        data = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return set()
    names: set[str] = set()
    for group in data.get("threat_actor_groups", []):
        if isinstance(group, dict):
            name = group.get("name")
            if name:
                names.add(name)
            for alias in group.get("aliases", []) or []:
                if alias:
                    names.add(alias)
    return names
```

Modify `_extract_actor_if_clean`:

```python
def _extract_actor_if_clean(osint_signals: dict) -> str | None:
    """Extract threat actor name if it appears cleanly in indicators."""
    hardcoded = {
        "Volt Typhoon", "APT41", "Sandworm", "Lazarus Group",
        "APT28", "APT29", "Kimsuky", "Charming Kitten",
    }
    known_actors = hardcoded | _load_watchlist_actors()
    for ind in osint_signals.get("lead_indicators", []):
        text = ind.get("text", "") if isinstance(ind, dict) else str(ind)
        for actor in known_actors:
            if actor.lower() in text.lower():
                return actor
    return None
```

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_scribe_enrichment.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit** (orchestrator)

---

## Gap B — RSM agent manifest omits cyber watchlist

**Problem:** `tools/rsm_input_builder.py::build_rsm_inputs` builds the manifest that feeds the RSM formatter agent. The watchlist is not included, so RSM briefs can't reference the organization's declared priority actors / campaigns / CVE categories when writing the cyber section.

**Fix:** Load `data/cyber_watchlist.json` (graceful), add as top-level `cyber_watchlist` field in the return dict, and surface actor/campaign counts in `manifest_summary`.

### Task B1: failing test + implementation

**Files:**
- Modify: `tools/rsm_input_builder.py` — load watchlist, add to return + summary
- Modify: `tests/test_rsm_input_builder.py` — add 2 tests

- [ ] **Step 1: Write failing tests**

```python
# append to tests/test_rsm_input_builder.py

def test_manifest_includes_cyber_watchlist_when_present(chdir_repo, tmp_path, monkeypatch):
    """If data/cyber_watchlist.json exists, manifest includes it."""
    import tools.rsm_input_builder as rib

    wl_path = tmp_path / "cyber_watchlist.json"
    wl_path.write_text(json.dumps({
        "threat_actor_groups": [{"name": "APT40", "motivation": "espionage"}],
        "sector_targeting_campaigns": [],
        "cve_watch_categories": ["ICS/SCADA"],
        "global_cyber_geographies_of_concern": ["China"],
    }), encoding="utf-8")

    # monkeypatch the module-level constant that Task B1 will add
    monkeypatch.setattr(rib, "WATCHLIST_FILE", wl_path)

    try:
        m = build_rsm_inputs("MED", cadence="daily")
    except FileNotFoundError:
        pytest.skip("MED pipeline not populated")
    assert "cyber_watchlist" in m
    assert m["cyber_watchlist"] is not None
    assert m["cyber_watchlist"]["threat_actor_groups"][0]["name"] == "APT40"


def test_manifest_cyber_watchlist_none_when_absent(chdir_repo, tmp_path, monkeypatch):
    """Missing watchlist file → manifest['cyber_watchlist'] is None."""
    import tools.rsm_input_builder as rib
    monkeypatch.setattr(rib, "WATCHLIST_FILE", tmp_path / "nonexistent.json")
    try:
        m = build_rsm_inputs("MED", cadence="daily")
    except FileNotFoundError:
        pytest.skip("MED pipeline not populated")
    assert m["cyber_watchlist"] is None


def test_manifest_summary_mentions_watchlist_when_present(chdir_repo, tmp_path, monkeypatch):
    """manifest_summary surfaces actor/campaign counts."""
    import tools.rsm_input_builder as rib

    wl_path = tmp_path / "cyber_watchlist.json"
    wl_path.write_text(json.dumps({
        "threat_actor_groups": [{"name": "APT40"}, {"name": "Volt Typhoon"}],
        "sector_targeting_campaigns": [{"campaign_name": "VOLT ICS"}],
        "cve_watch_categories": ["ICS/SCADA"],
    }), encoding="utf-8")
    monkeypatch.setattr(rib, "WATCHLIST_FILE", wl_path)

    try:
        m = build_rsm_inputs("MED", cadence="daily")
    except FileNotFoundError:
        pytest.skip("MED pipeline not populated")
    summary = manifest_summary(m)
    assert "watchlist" in summary.lower()
    assert "APT40" in summary or "2" in summary  # actor count or name
```

Top of test file: add `import json` if not already present.

- [ ] **Step 2: Run tests to confirm failure**

Run: `uv run pytest tests/test_rsm_input_builder.py::test_manifest_includes_cyber_watchlist_when_present -v`
Expected: FAIL — `WATCHLIST_FILE` attribute missing or `cyber_watchlist` key absent.

- [ ] **Step 3: Implement**

In `tools/rsm_input_builder.py`, after `NOTABLE_DATE_HORIZON_DAYS = 7`:

```python
WATCHLIST_FILE = Path(__file__).parent.parent / "data" / "cyber_watchlist.json"
```

Inside `build_rsm_inputs`, before the `return {...}` block, add:

```python
    # ── cyber watchlist (global, non-region-specific) ────────────────────────
    cyber_watchlist = _load_json(WATCHLIST_FILE)
```

Add `"cyber_watchlist": cyber_watchlist,` to the return dict.

In `manifest_summary`, add a rendering block before the `return "\n".join(lines)`:

```python
    wl = manifest.get("cyber_watchlist")
    if isinstance(wl, dict):
        actors = wl.get("threat_actor_groups", []) or []
        campaigns = wl.get("sector_targeting_campaigns", []) or []
        cves = wl.get("cve_watch_categories", []) or []
        if actors or campaigns or cves:
            lines.append("\nGlobal cyber watchlist:")
            if actors:
                names = ", ".join(a.get("name", "") for a in actors if a.get("name"))
                lines.append(f"  priority actors ({len(actors)}): {names}")
            if campaigns:
                camp_names = ", ".join(
                    c.get("campaign_name", "") for c in campaigns if c.get("campaign_name")
                )
                lines.append(f"  active campaigns ({len(campaigns)}): {camp_names}")
            if cves:
                lines.append(f"  CVE watch categories: {' | '.join(cves)}")
```

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_rsm_input_builder.py -v`
Expected: all 10 tests PASS (7 existing + 3 new).

- [ ] **Step 5: Commit** (orchestrator)

---

## Final Verification

Run full test suite (excluding known pre-existing broken/paid tests):

```
uv run pytest tests/ \
  --ignore=tests/test_ui.py \
  --ignore=tests/test_export_ciso_docx.py \
  --ignore=tests/test_evidence_tiering.py \
  -q
```

Expected: all pass (prior baseline was 520 passed).
