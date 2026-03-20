# Phase L — RSM Intelligence Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire an end-to-end RSM (Regional Security Manager) intelligence brief pipeline that collects Seerist signals, computes deltas, evaluates thresholds, formats SITREP briefs via an LLM agent, and delivers via email — all in mock mode first, live mode when API keys are available.

**Architecture:** A parallel delivery path alongside the existing board/CISO pipeline. New tools follow the Disler filesystem-as-state pattern: each tool reads files, writes files, does one thing. The `rsm_dispatcher.py` orchestrator is the only new code that calls agents. The existing pipeline (gatekeeper → analyst → builder → validator) is untouched.

**Tech Stack:** Python 3.14, uv, pytest, stdlib only for proximity math (haversine inline), SMTP stdlib for email, Claude Sonnet agent for ASSESSMENT/WATCH LIST sections only.

---

## File Map

**New data files:**
- `data/region_country_map.json` — region → Seerist country codes
- `data/aerowind_sites.json` — AeroGrid physical site locations
- `data/audience_config.json` — stakeholder delivery control plane
- `data/schedule_config.json` — scheduler job definitions

**New mock fixtures (5 regions):**
- `data/mock_osint_fixtures/{apac|ame|latam|med|nce}_seerist.json`

**New tools:**
- `tools/seerist_collector.py` — fetches EventsAI/HotspotsAI/PulseAI → `seerist_signals.json`
- `tools/delta_computer.py` — diffs current vs previous seerist signals → `region_delta.json`
- `tools/threshold_evaluator.py` — evaluates audience thresholds → `routing_decisions.json`
- `tools/rsm_dispatcher.py` — orchestrates RSM path: invokes formatter agent + notifier
- `tools/notifier.py` — email delivery adapter → `delivery_log.json`
- `tools/scheduler.py` — lightweight cron runner

**New agent:**
- `.claude/agents/rsm-formatter-agent.md` — writes ASSESSMENT + WATCH LIST sections only

**New tests:**
- `tests/test_seerist_collector.py`
- `tests/test_delta_computer.py`
- `tests/test_threshold_evaluator.py`
- `tests/test_rsm_dispatcher.py`
- `tests/test_notifier.py`
- `tests/test_scheduler.py`

**Unchanged:** All existing tools, agents, pipeline commands, dashboard, exports.

---

## Task L-1: Data Files + Seerist Collector + Mock Fixtures

**Files:**
- Create: `data/region_country_map.json`
- Create: `data/mock_osint_fixtures/apac_seerist.json`
- Create: `data/mock_osint_fixtures/ame_seerist.json`
- Create: `data/mock_osint_fixtures/latam_seerist.json`
- Create: `data/mock_osint_fixtures/med_seerist.json`
- Create: `data/mock_osint_fixtures/nce_seerist.json`
- Create: `tools/seerist_collector.py`
- Create: `tests/test_seerist_collector.py`

### Step 1.1: Write region_country_map.json

```json
{
  "APAC": ["CN", "AU", "TW", "JP", "SG", "KR", "IN"],
  "AME":  ["US", "CA", "MX"],
  "LATAM":["BR", "CL", "CO", "AR", "PE"],
  "MED":  ["IT", "ES", "GR", "TR", "MA", "EG"],
  "NCE":  ["DE", "PL", "DK", "SE", "NO", "FI"]
}
```

Save to `data/region_country_map.json`.

### Step 1.2: Write mock Seerist fixtures

Write one file per region to `data/mock_osint_fixtures/{region}_seerist.json`. Each file follows the `seerist_signals.json` schema from the spec. Use realistic but clearly fictional data — no real incidents.

**`apac_seerist.json`:**
```json
{
  "region": "APAC",
  "window_days": 7,
  "pulse": {
    "score": 51,
    "score_prev": 58,
    "delta": -7,
    "security_risk": "High",
    "political_risk": "Medium",
    "sub_categories": {"border_tension": "High", "civil_unrest": "Medium", "organized_crime": "Low"}
  },
  "events": [
    {
      "event_id": "apac-mock-001",
      "category": "Unrest",
      "severity": 4,
      "title": "Kaohsiung dockworker strike enters second day",
      "location": {"name": "Kaohsiung, TW", "lat": 22.62, "lon": 120.30, "country_code": "TW"},
      "timestamp": "2026-03-19T08:00:00Z",
      "verified": true,
      "source_count": 12
    },
    {
      "event_id": "apac-mock-002",
      "category": "Maritime",
      "severity": 3,
      "title": "South China Sea patrol assertiveness elevated near Spratly Islands",
      "location": {"name": "South China Sea", "lat": 10.00, "lon": 114.00, "country_code": "CN"},
      "timestamp": "2026-03-18T14:00:00Z",
      "verified": true,
      "source_count": 8
    }
  ],
  "hotspots": [
    {
      "hotspot_id": "apac-hot-001",
      "location": {"name": "Taipei industrial district, TW", "country_code": "TW"},
      "deviation_score": 0.87,
      "category_hint": "Unrest",
      "detected_at": "2026-03-19T14:00:00Z"
    }
  ],
  "collected_at": "2026-03-20T05:00:00Z"
}
```

**`ame_seerist.json`:**
```json
{
  "region": "AME",
  "window_days": 7,
  "pulse": {
    "score": 72,
    "score_prev": 74,
    "delta": -2,
    "security_risk": "Medium",
    "political_risk": "Medium",
    "sub_categories": {"civil_unrest": "Low", "organized_crime": "Medium", "border_tension": "Low"}
  },
  "events": [
    {
      "event_id": "ame-mock-001",
      "category": "Crime",
      "severity": 2,
      "title": "Houston port area petty crime increase reported near energy district",
      "location": {"name": "Houston, TX, US", "lat": 29.76, "lon": -95.37, "country_code": "US"},
      "timestamp": "2026-03-18T10:00:00Z",
      "verified": false,
      "source_count": 3
    }
  ],
  "hotspots": [],
  "collected_at": "2026-03-20T05:00:00Z"
}
```

**`latam_seerist.json`:**
```json
{
  "region": "LATAM",
  "window_days": 7,
  "pulse": {
    "score": 63,
    "score_prev": 63,
    "delta": 0,
    "security_risk": "Medium",
    "political_risk": "Low",
    "sub_categories": {"civil_unrest": "Low", "organized_crime": "Medium", "border_tension": "Low"}
  },
  "events": [],
  "hotspots": [],
  "collected_at": "2026-03-20T05:00:00Z"
}
```

**`med_seerist.json`:**
```json
{
  "region": "MED",
  "window_days": 7,
  "pulse": {
    "score": 44,
    "score_prev": 46,
    "delta": -2,
    "security_risk": "High",
    "political_risk": "High",
    "sub_categories": {"civil_unrest": "Medium", "organized_crime": "High", "maritime_dispute": "Medium"}
  },
  "events": [
    {
      "event_id": "med-mock-001",
      "category": "Unrest",
      "severity": 3,
      "title": "Palermo port workers strike over austerity pension cuts",
      "location": {"name": "Palermo, IT", "lat": 38.12, "lon": 13.36, "country_code": "IT"},
      "timestamp": "2026-03-17T09:00:00Z",
      "verified": true,
      "source_count": 7
    }
  ],
  "hotspots": [],
  "collected_at": "2026-03-20T05:00:00Z"
}
```

**`nce_seerist.json`:**
```json
{
  "region": "NCE",
  "window_days": 7,
  "pulse": {
    "score": 81,
    "score_prev": 81,
    "delta": 0,
    "security_risk": "Low",
    "political_risk": "Low",
    "sub_categories": {"civil_unrest": "Low", "organized_crime": "Low", "border_tension": "Low"}
  },
  "events": [],
  "hotspots": [],
  "collected_at": "2026-03-20T05:00:00Z"
}
```

### Step 1.3: Write failing tests

Create `tests/test_seerist_collector.py`:

```python
"""Tests for tools/seerist_collector.py — Phase L"""
import json
from pathlib import Path
import pytest
import tools.seerist_collector as sc


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(sc, "FIXTURES_DIR", Path("data/mock_osint_fixtures"))


def test_mock_mode_writes_seerist_signals(monkeypatch, tmp_path):
    """--mock reads fixture and writes seerist_signals.json."""
    _patch(monkeypatch, tmp_path)
    sc.collect("APAC", mock=True)
    out = tmp_path / "output" / "regional" / "apac" / "seerist_signals.json"
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["region"] == "APAC"
    assert "pulse" in data
    assert "events" in data
    assert "hotspots" in data
    assert "collected_at" in data


def test_mock_all_regions(monkeypatch, tmp_path):
    """All 5 regions have fixtures and collect without error."""
    _patch(monkeypatch, tmp_path)
    for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        sc.collect(region, mock=True)
        out = tmp_path / "output" / "regional" / region.lower() / "seerist_signals.json"
        assert out.exists(), f"Missing seerist_signals.json for {region}"


def test_invalid_region_exits(monkeypatch, tmp_path):
    """Invalid region raises ValueError."""
    _patch(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="invalid region"):
        sc.collect("INVALID", mock=True)


def test_live_mode_without_key_falls_back_to_mock(monkeypatch, tmp_path):
    """No SEERIST_API_KEY → falls back to mock fixture, exits 0."""
    _patch(monkeypatch, tmp_path)
    monkeypatch.delenv("SEERIST_API_KEY", raising=False)
    sc.collect("LATAM", mock=False)
    out = tmp_path / "output" / "regional" / "latam" / "seerist_signals.json"
    assert out.exists()


def test_output_schema_keys(monkeypatch, tmp_path):
    """Output file contains all required schema keys."""
    _patch(monkeypatch, tmp_path)
    sc.collect("MED", mock=True)
    out = tmp_path / "output" / "regional" / "med" / "seerist_signals.json"
    data = json.loads(out.read_text(encoding="utf-8"))
    for key in ["region", "window_days", "pulse", "events", "hotspots", "collected_at"]:
        assert key in data, f"Missing key: {key}"
    for key in ["score", "score_prev", "delta", "security_risk", "political_risk"]:
        assert key in data["pulse"], f"Missing pulse key: {key}"
```

- [ ] **Run failing tests:**
  ```bash
  uv run pytest tests/test_seerist_collector.py -v
  ```
  Expected: `ModuleNotFoundError: No module named 'tools.seerist_collector'`

### Step 1.4: Implement seerist_collector.py

Create `tools/seerist_collector.py`:

```python
#!/usr/bin/env python3
"""Seerist signal collector — fetches EventsAI, HotspotsAI, PulseAI per region.

Usage:
    seerist_collector.py REGION [--mock] [--window 7d]

Writes: output/regional/{region}/seerist_signals.json

Mock mode (default when SEERIST_API_KEY absent): reads
data/mock_osint_fixtures/{region}_seerist.json
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
OUTPUT_ROOT = Path("output")
FIXTURES_DIR = Path("data/mock_osint_fixtures")
REGION_MAP_PATH = Path("data/region_country_map.json")


def _load_region_map() -> dict:
    return json.loads(REGION_MAP_PATH.read_text(encoding="utf-8"))


def _mock_collect(region: str, window_days: int) -> dict:
    fixture = FIXTURES_DIR / f"{region.lower()}_seerist.json"
    if not fixture.exists():
        raise FileNotFoundError(f"Mock fixture not found: {fixture}")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    data["window_days"] = window_days
    data["collected_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return data


def _live_collect(region: str, window_days: int) -> dict:
    """Live Seerist API call. Falls back to mock if key absent."""
    api_key = os.environ.get("SEERIST_API_KEY", "")
    if not api_key:
        print(f"[seerist_collector] No SEERIST_API_KEY — falling back to mock", file=sys.stderr)
        return _mock_collect(region, window_days)

    # TODO: replace with real Seerist endpoints when API docs confirmed
    # Stub: import and call seerist_client when key is present
    try:
        from tools.seerist_client import get_full_intelligence
        raw = get_full_intelligence(region)
        return {
            "region": region,
            "window_days": window_days,
            "pulse": raw.get("pulse", {}),
            "events": raw.get("events", []),
            "hotspots": raw.get("hotspots", []),
            "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    except Exception as e:
        print(f"[seerist_collector] Live collection failed: {e} — falling back to mock", file=sys.stderr)
        return _mock_collect(region, window_days)


def collect(region: str, mock: bool = True, window_days: int = 7) -> dict:
    region = region.upper()
    if region not in VALID_REGIONS:
        raise ValueError(f"invalid region '{region}' — must be one of {VALID_REGIONS}")

    data = _mock_collect(region, window_days) if mock else _live_collect(region, window_days)

    out_dir = OUTPUT_ROOT / "regional" / region.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "seerist_signals.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[seerist_collector] wrote {out_path}", file=sys.stderr)
    return data


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: seerist_collector.py REGION [--mock] [--window 7d]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    mock = "--mock" in args or not os.environ.get("SEERIST_API_KEY")

    window_days = 7
    if "--window" in args:
        idx = args.index("--window")
        if idx + 1 < len(args):
            val = args[idx + 1].rstrip("d")
            try:
                window_days = int(val)
            except ValueError:
                pass

    try:
        collect(region, mock=mock, window_days=window_days)
    except (ValueError, FileNotFoundError) as e:
        print(f"[seerist_collector] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Run tests — expect pass:**
  ```bash
  uv run pytest tests/test_seerist_collector.py -v
  ```
  Expected: 5 passed

- [ ] **Smoke test:**
  ```bash
  uv run python tools/seerist_collector.py APAC --mock
  cat output/regional/apac/seerist_signals.json | python -c "import sys,json; d=json.load(sys.stdin); print(d['pulse']['delta'], len(d['events']), 'hotspots:', len(d['hotspots']))"
  ```
  Expected: `-7 2 hotspots: 1`

- [ ] **Commit:**
  ```bash
  git add data/region_country_map.json data/mock_osint_fixtures/*_seerist.json tools/seerist_collector.py tests/test_seerist_collector.py
  git commit -m "feat: add seerist_collector.py + mock fixtures + region_country_map (Phase L-1)"
  ```

---

## Task L-2: Delta Computer

**Files:**
- Create: `tools/delta_computer.py`
- Create: `tests/test_delta_computer.py`

### Step 2.1: Write failing tests

Create `tests/test_delta_computer.py`:

```python
"""Tests for tools/delta_computer.py — Phase L"""
import json
from pathlib import Path
from datetime import datetime, timezone
import pytest
import tools.delta_computer as dc


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(dc, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(dc, "LATEST_ROOT", tmp_path / "latest")


def _write_seerist(base: Path, region: str, data: dict) -> Path:
    p = base / "regional" / region.lower()
    p.mkdir(parents=True, exist_ok=True)
    f = p / "seerist_signals.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    return f


SAMPLE_EVENT = {
    "event_id": "e1", "category": "Unrest", "severity": 4,
    "title": "Strike at Kaohsiung", "location": {"name": "Kaohsiung, TW", "country_code": "TW"},
    "timestamp": "2026-03-19T08:00:00Z", "verified": True, "source_count": 5
}
SAMPLE_HOTSPOT = {
    "hotspot_id": "h1", "location": {"name": "Taipei", "country_code": "TW"},
    "deviation_score": 0.87, "category_hint": "Unrest", "detected_at": "2026-03-19T14:00:00Z"
}


def test_cold_start_no_previous(monkeypatch, tmp_path):
    """No previous seerist_signals.json → empty delta, pulse_delta null, exits 0."""
    _patch(monkeypatch, tmp_path)
    current = {"region": "APAC", "pulse": {"score": 51, "delta": -7}, "events": [SAMPLE_EVENT], "hotspots": [SAMPLE_HOTSPOT]}
    _write_seerist(tmp_path / "output", "APAC", current)
    # No latest dir → cold start
    dc.compute("APAC")
    out = tmp_path / "output" / "regional" / "apac" / "region_delta.json"
    assert out.exists()
    delta = json.loads(out.read_text(encoding="utf-8"))
    assert delta["pulse_delta"] is None
    assert delta["events_new"] == []
    assert delta["events_resolved"] == []
    assert delta["hotspots_new"] == []
    assert delta["hotspots_resolved"] == []


def test_new_event_detected(monkeypatch, tmp_path):
    """Event in current but not previous → appears in events_new."""
    _patch(monkeypatch, tmp_path)
    prev = {"region": "APAC", "pulse": {"score": 58, "delta": 0}, "events": [], "hotspots": []}
    curr = {"region": "APAC", "pulse": {"score": 51, "delta": -7}, "events": [SAMPLE_EVENT], "hotspots": []}
    _write_seerist(tmp_path / "latest", "APAC", prev)
    _write_seerist(tmp_path / "output", "APAC", curr)
    dc.compute("APAC")
    delta = json.loads((tmp_path / "output" / "regional" / "apac" / "region_delta.json").read_text())
    assert len(delta["events_new"]) == 1
    assert delta["events_new"][0]["event_id"] == "e1"
    assert delta["events_resolved"] == []


def test_resolved_event_detected(monkeypatch, tmp_path):
    """Event in previous but not current → appears in events_resolved."""
    _patch(monkeypatch, tmp_path)
    prev = {"region": "APAC", "pulse": {"score": 58, "delta": 0}, "events": [SAMPLE_EVENT], "hotspots": []}
    curr = {"region": "APAC", "pulse": {"score": 58, "delta": 0}, "events": [], "hotspots": []}
    _write_seerist(tmp_path / "latest", "APAC", prev)
    _write_seerist(tmp_path / "output", "APAC", curr)
    dc.compute("APAC")
    delta = json.loads((tmp_path / "output" / "regional" / "apac" / "region_delta.json").read_text())
    assert delta["events_new"] == []
    assert len(delta["events_resolved"]) == 1


def test_pulse_delta_computed(monkeypatch, tmp_path):
    """Pulse delta is current_score minus previous_score."""
    _patch(monkeypatch, tmp_path)
    prev = {"region": "APAC", "pulse": {"score": 58, "delta": 0}, "events": [], "hotspots": []}
    curr = {"region": "APAC", "pulse": {"score": 51, "delta": -7}, "events": [], "hotspots": []}
    _write_seerist(tmp_path / "latest", "APAC", prev)
    _write_seerist(tmp_path / "output", "APAC", curr)
    dc.compute("APAC")
    delta = json.loads((tmp_path / "output" / "regional" / "apac" / "region_delta.json").read_text())
    assert delta["pulse_delta"] == -7


def test_new_hotspot_detected(monkeypatch, tmp_path):
    """New hotspot in current → in hotspots_new."""
    _patch(monkeypatch, tmp_path)
    prev = {"region": "APAC", "pulse": {"score": 58, "delta": 0}, "events": [], "hotspots": []}
    curr = {"region": "APAC", "pulse": {"score": 51, "delta": -7}, "events": [], "hotspots": [SAMPLE_HOTSPOT]}
    _write_seerist(tmp_path / "latest", "APAC", prev)
    _write_seerist(tmp_path / "output", "APAC", curr)
    dc.compute("APAC")
    delta = json.loads((tmp_path / "output" / "regional" / "apac" / "region_delta.json").read_text())
    assert len(delta["hotspots_new"]) == 1
    assert delta["hotspots_new"][0]["hotspot_id"] == "h1"


def test_invalid_region_raises(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="invalid region"):
        dc.compute("INVALID")


def test_output_has_period_fields(monkeypatch, tmp_path):
    """Delta output includes period_from and period_to timestamps."""
    _patch(monkeypatch, tmp_path)
    curr = {"region": "NCE", "pulse": {"score": 81, "delta": 0}, "events": [], "hotspots": [], "collected_at": "2026-03-20T05:00:00Z"}
    _write_seerist(tmp_path / "output", "NCE", curr)
    dc.compute("NCE")
    delta = json.loads((tmp_path / "output" / "regional" / "nce" / "region_delta.json").read_text())
    assert "period_from" in delta
    assert "period_to" in delta
    assert delta["region"] == "NCE"
```

- [ ] **Run failing tests:**
  ```bash
  uv run pytest tests/test_delta_computer.py -v
  ```
  Expected: `ModuleNotFoundError`

### Step 2.2: Implement delta_computer.py

Create `tools/delta_computer.py`:

```python
#!/usr/bin/env python3
"""Delta computer — diffs current vs previous Seerist signals.

Usage:
    delta_computer.py REGION

Reads:  output/regional/{region}/seerist_signals.json  (current)
        output/latest/regional/{region}/seerist_signals.json  (previous)
Writes: output/regional/{region}/region_delta.json

Cold-start: if no previous file exists, writes empty delta with pulse_delta=null.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
OUTPUT_ROOT = Path("output")
LATEST_ROOT = Path("output/latest")


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def compute(region: str) -> dict:
    region = region.upper()
    if region not in VALID_REGIONS:
        raise ValueError(f"invalid region '{region}'")

    region_lower = region.lower()
    current_path = OUTPUT_ROOT / "regional" / region_lower / "seerist_signals.json"
    previous_path = LATEST_ROOT / "regional" / region_lower / "seerist_signals.json"

    current = _load_json(current_path)
    if current is None:
        raise FileNotFoundError(f"Current seerist_signals.json not found: {current_path}")

    previous = _load_json(previous_path)  # None = cold start

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    period_from = (previous or {}).get("collected_at", now)
    period_to = current.get("collected_at", now)

    # Compute pulse delta
    if previous is None:
        pulse_delta = None
    else:
        curr_score = (current.get("pulse") or {}).get("score")
        prev_score = (previous.get("pulse") or {}).get("score")
        pulse_delta = (curr_score - prev_score) if (curr_score is not None and prev_score is not None) else None

    # Diff events by event_id
    curr_event_ids = {e["event_id"] for e in current.get("events", [])}
    prev_event_ids = {e["event_id"] for e in (previous or {}).get("events", [])} if previous else set()

    events_new = [e for e in current.get("events", []) if e["event_id"] not in prev_event_ids]
    curr_events_by_id = {e["event_id"]: e for e in current.get("events", [])}
    prev_events_by_id = {e["event_id"]: e for e in (previous or {}).get("events", [])} if previous else {}
    events_resolved = [e for eid, e in prev_events_by_id.items() if eid not in curr_event_ids]

    # Diff hotspots by hotspot_id
    curr_hotspot_ids = {h["hotspot_id"] for h in current.get("hotspots", [])}
    prev_hotspot_ids = {h["hotspot_id"] for h in (previous or {}).get("hotspots", [])} if previous else set()

    hotspots_new = [h for h in current.get("hotspots", []) if h["hotspot_id"] not in prev_hotspot_ids]
    prev_hotspots_by_id = {h["hotspot_id"]: h for h in (previous or {}).get("hotspots", [])} if previous else {}
    hotspots_resolved = [h for hid, h in prev_hotspots_by_id.items() if hid not in curr_hotspot_ids]

    delta = {
        "region": region,
        "period_from": period_from,
        "period_to": period_to,
        "pulse_delta": pulse_delta,
        "events_new": events_new,
        "events_resolved": events_resolved,
        "hotspots_new": hotspots_new,
        "hotspots_resolved": hotspots_resolved,
    }

    out_path = OUTPUT_ROOT / "regional" / region_lower / "region_delta.json"
    out_path.write_text(json.dumps(delta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[delta_computer] wrote {out_path}", file=sys.stderr)
    return delta


def main():
    if len(sys.argv) < 2:
        print("Usage: delta_computer.py REGION", file=sys.stderr)
        sys.exit(1)
    try:
        compute(sys.argv[1])
    except (ValueError, FileNotFoundError) as e:
        print(f"[delta_computer] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Run tests — expect pass:**
  ```bash
  uv run pytest tests/test_delta_computer.py -v
  ```
  Expected: 7 passed

- [ ] **Commit:**
  ```bash
  git add tools/delta_computer.py tests/test_delta_computer.py
  git commit -m "feat: add delta_computer.py — explicit signal delta per region (Phase L-2)"
  ```

---

## Task L-3: Config Data Files

**Files:**
- Create: `data/aerowind_sites.json`
- Create: `data/audience_config.json`
- Create: `data/schedule_config.json`

### Step 3.1: Write aerowind_sites.json

```json
{
  "sites": [
    {"name": "Kaohsiung Manufacturing Hub",   "region": "APAC",  "country": "TW", "lat": 22.62, "lon": 120.30, "type": "manufacturing"},
    {"name": "Shanghai Service Hub",           "region": "APAC",  "country": "CN", "lat": 31.23, "lon": 121.47, "type": "service"},
    {"name": "Tokyo Regional Office",          "region": "APAC",  "country": "JP", "lat": 35.68, "lon": 139.69, "type": "office"},
    {"name": "Houston Operations Center",      "region": "AME",   "country": "US", "lat": 29.76, "lon": -95.37, "type": "service"},
    {"name": "Toronto Engineering Hub",        "region": "AME",   "country": "CA", "lat": 43.65, "lon": -79.38, "type": "office"},
    {"name": "Sao Paulo Service Hub",          "region": "LATAM", "country": "BR", "lat": -23.55, "lon": -46.63, "type": "service"},
    {"name": "Santiago Manufacturing Support", "region": "LATAM", "country": "CL", "lat": -33.45, "lon": -70.67, "type": "service"},
    {"name": "Palermo Offshore Ops",           "region": "MED",   "country": "IT", "lat": 38.12, "lon": 13.36,  "type": "manufacturing"},
    {"name": "Malaga Service Hub",             "region": "MED",   "country": "ES", "lat": 36.72, "lon": -4.42,  "type": "service"},
    {"name": "Hamburg Manufacturing Hub",      "region": "NCE",   "country": "DE", "lat": 53.55, "lon": 10.00,  "type": "manufacturing"},
    {"name": "Copenhagen Engineering Hub",     "region": "NCE",   "country": "DK", "lat": 55.68, "lon": 12.57,  "type": "office"},
    {"name": "Gdansk Blade Plant",             "region": "NCE",   "country": "PL", "lat": 54.35, "lon": 18.65,  "type": "manufacturing"}
  ]
}
```

Save to `data/aerowind_sites.json`.

### Step 3.3: Write audience_config.json

```json
{
  "rsm_apac": {
    "label": "APAC Regional Security Manager",
    "formatter_agent": "rsm-formatter-agent",
    "regions": ["APAC"],
    "products": {
      "weekly_intsum": {
        "cadence": "monday",
        "time_local": "07:00",
        "timezone": "Asia/Singapore"
      },
      "flash": {
        "threshold": {
          "hotspot_score_min": 0.85,
          "site_proximity_km": 100,
          "event_severity_min": 4,
          "categories": ["Conflict", "Terrorism", "Unrest"]
        }
      }
    },
    "delivery": {
      "channel": "email",
      "recipients": ["rsm-apac@aerowind.com"]
    }
  },
  "rsm_ame": {
    "label": "AME Regional Security Manager",
    "formatter_agent": "rsm-formatter-agent",
    "regions": ["AME"],
    "products": {
      "weekly_intsum": {
        "cadence": "monday",
        "time_local": "07:00",
        "timezone": "America/New_York"
      },
      "flash": {
        "threshold": {
          "hotspot_score_min": 0.85,
          "site_proximity_km": 100,
          "event_severity_min": 4,
          "categories": ["Conflict", "Terrorism", "Unrest"]
        }
      }
    },
    "delivery": {
      "channel": "email",
      "recipients": ["rsm-ame@aerowind.com"]
    }
  },
  "rsm_latam": {
    "label": "LATAM Regional Security Manager",
    "formatter_agent": "rsm-formatter-agent",
    "regions": ["LATAM"],
    "products": {
      "weekly_intsum": {
        "cadence": "monday",
        "time_local": "07:00",
        "timezone": "America/Sao_Paulo"
      },
      "flash": {
        "threshold": {
          "hotspot_score_min": 0.85,
          "site_proximity_km": 100,
          "event_severity_min": 4,
          "categories": ["Conflict", "Terrorism", "Unrest"]
        }
      }
    },
    "delivery": {
      "channel": "email",
      "recipients": ["rsm-latam@aerowind.com"]
    }
  },
  "rsm_med": {
    "label": "MED Regional Security Manager",
    "formatter_agent": "rsm-formatter-agent",
    "regions": ["MED"],
    "products": {
      "weekly_intsum": {
        "cadence": "monday",
        "time_local": "07:00",
        "timezone": "Europe/Rome"
      },
      "flash": {
        "threshold": {
          "hotspot_score_min": 0.85,
          "site_proximity_km": 100,
          "event_severity_min": 4,
          "categories": ["Conflict", "Terrorism", "Unrest"]
        }
      }
    },
    "delivery": {
      "channel": "email",
      "recipients": ["rsm-med@aerowind.com"]
    }
  },
  "rsm_nce": {
    "label": "NCE Regional Security Manager",
    "formatter_agent": "rsm-formatter-agent",
    "regions": ["NCE"],
    "products": {
      "weekly_intsum": {
        "cadence": "monday",
        "time_local": "07:00",
        "timezone": "Europe/Berlin"
      },
      "flash": {
        "threshold": {
          "hotspot_score_min": 0.85,
          "site_proximity_km": 100,
          "event_severity_min": 4,
          "categories": ["Conflict", "Terrorism", "Unrest"]
        }
      }
    },
    "delivery": {
      "channel": "email",
      "recipients": ["rsm-nce@aerowind.com"]
    }
  }
}
```

### Step 3.4: Write schedule_config.json

```json
{
  "jobs": [
    {
      "id": "seerist_collect_all",
      "command": "uv run python tools/seerist_collector.py {region} --mock",
      "regions": ["APAC", "AME", "LATAM", "MED", "NCE"],
      "cron": "0 */6 * * *",
      "description": "Collect Seerist signals every 6 hours for all regions"
    },
    {
      "id": "delta_compute_all",
      "command": "uv run python tools/delta_computer.py {region}",
      "regions": ["APAC", "AME", "LATAM", "MED", "NCE"],
      "cron": "15 */6 * * *",
      "description": "Compute signal deltas 15 min after seerist collection"
    },
    {
      "id": "rsm_dispatch_flash",
      "command": "uv run python tools/rsm_dispatcher.py --check-flash",
      "regions": null,
      "cron": "30 */6 * * *",
      "description": "Evaluate flash thresholds and dispatch triggered alerts"
    },
    {
      "id": "rsm_dispatch_weekly",
      "command": "uv run python tools/rsm_dispatcher.py --weekly",
      "regions": null,
      "cron": "0 5 * * 1",
      "description": "Generate and deliver weekly INTSUM every Monday 05:00 UTC"
    }
  ]
}
```

- [ ] **Commit:**
  ```bash
  git add data/aerowind_sites.json data/audience_config.json data/schedule_config.json
  git commit -m "feat: add aerowind_sites.json + audience_config.json + schedule_config.json (Phase L-3)"
  ```

---

## Task L-4: Threshold Evaluator

**Files:**
- Create: `tools/threshold_evaluator.py`
- Create: `tests/test_threshold_evaluator.py`

### Step 4.1: Write failing tests

Create `tests/test_threshold_evaluator.py`:

```python
"""Tests for tools/threshold_evaluator.py — Phase L"""
import json
from pathlib import Path
from datetime import datetime
import pytest
import tools.threshold_evaluator as te


INLINE_AUDIENCE_CONFIG = {
    "rsm_apac": {
        "label": "APAC RSM", "formatter_agent": "rsm-formatter-agent", "regions": ["APAC"],
        "products": {
            "weekly_intsum": {"cadence": "monday", "time_local": "07:00", "timezone": "Asia/Singapore"},
            "flash": {"threshold": {"hotspot_score_min": 0.85, "site_proximity_km": 100, "event_severity_min": 4, "categories": ["Conflict", "Terrorism", "Unrest"]}}
        },
        "delivery": {"channel": "email", "recipients": ["rsm-apac@aerowind.com"]}
    },
    "rsm_ame": {
        "label": "AME RSM", "formatter_agent": "rsm-formatter-agent", "regions": ["AME"],
        "products": {
            "weekly_intsum": {"cadence": "monday", "time_local": "07:00", "timezone": "America/New_York"},
            "flash": {"threshold": {"hotspot_score_min": 0.85, "site_proximity_km": 100, "event_severity_min": 4, "categories": ["Conflict", "Terrorism", "Unrest"]}}
        },
        "delivery": {"channel": "email", "recipients": ["rsm-ame@aerowind.com"]}
    },
    "rsm_latam": {"label": "LATAM RSM", "formatter_agent": "rsm-formatter-agent", "regions": ["LATAM"], "products": {"weekly_intsum": {"cadence": "monday"}, "flash": {"threshold": {"hotspot_score_min": 0.85, "site_proximity_km": 100, "event_severity_min": 4, "categories": ["Conflict", "Terrorism", "Unrest"]}}}, "delivery": {"channel": "email", "recipients": []}},
    "rsm_med": {"label": "MED RSM", "formatter_agent": "rsm-formatter-agent", "regions": ["MED"], "products": {"weekly_intsum": {"cadence": "monday"}, "flash": {"threshold": {"hotspot_score_min": 0.85, "site_proximity_km": 100, "event_severity_min": 4, "categories": ["Conflict", "Terrorism", "Unrest"]}}}, "delivery": {"channel": "email", "recipients": []}},
    "rsm_nce": {"label": "NCE RSM", "formatter_agent": "rsm-formatter-agent", "regions": ["NCE"], "products": {"weekly_intsum": {"cadence": "monday"}, "flash": {"threshold": {"hotspot_score_min": 0.85, "site_proximity_km": 100, "event_severity_min": 4, "categories": ["Conflict", "Terrorism", "Unrest"]}}}, "delivery": {"channel": "email", "recipients": []}},
}
INLINE_SITES = {"sites": [
    {"name": "Kaohsiung Manufacturing Hub", "region": "APAC", "country": "TW", "lat": 22.62, "lon": 120.30, "type": "manufacturing"},
    {"name": "Houston Operations Center", "region": "AME", "country": "US", "lat": 29.76, "lon": -95.37, "type": "service"},
    {"name": "Sao Paulo Service Hub", "region": "LATAM", "country": "BR", "lat": -23.55, "lon": -46.63, "type": "service"},
    {"name": "Palermo Offshore Ops", "region": "MED", "country": "IT", "lat": 38.12, "lon": 13.36, "type": "manufacturing"},
    {"name": "Hamburg Manufacturing Hub", "region": "NCE", "country": "DE", "lat": 53.55, "lon": 10.00, "type": "manufacturing"},
]}


def _patch(monkeypatch, tmp_path):
    audience_path = tmp_path / "data" / "audience_config.json"
    sites_path = tmp_path / "data" / "aerowind_sites.json"
    audience_path.parent.mkdir(parents=True, exist_ok=True)
    audience_path.write_text(json.dumps(INLINE_AUDIENCE_CONFIG), encoding="utf-8")
    sites_path.write_text(json.dumps(INLINE_SITES), encoding="utf-8")
    monkeypatch.setattr(te, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(te, "AUDIENCE_CONFIG_PATH", audience_path)
    monkeypatch.setattr(te, "SITES_PATH", sites_path)


def _write_seerist(tmp_path, region, events=None, hotspots=None, pulse_score=70):
    p = tmp_path / "output" / "regional" / region.lower()
    p.mkdir(parents=True, exist_ok=True)
    data = {
        "region": region,
        "pulse": {"score": pulse_score, "score_prev": pulse_score, "delta": 0, "security_risk": "Low", "political_risk": "Low"},
        "events": events or [],
        "hotspots": hotspots or [],
        "collected_at": "2026-03-20T05:00:00Z"
    }
    (p / "seerist_signals.json").write_text(json.dumps(data), encoding="utf-8")


def _write_delta(tmp_path, region, events_new=None, hotspots_new=None):
    p = tmp_path / "output" / "regional" / region.lower()
    p.mkdir(parents=True, exist_ok=True)
    data = {
        "region": region, "period_from": "2026-03-13T05:00:00Z", "period_to": "2026-03-20T05:00:00Z",
        "pulse_delta": 0, "events_new": events_new or [], "events_resolved": [],
        "hotspots_new": hotspots_new or [], "hotspots_resolved": []
    }
    (p / "region_delta.json").write_text(json.dumps(data), encoding="utf-8")


def test_weekly_intsum_always_triggered(monkeypatch, tmp_path):
    """weekly_intsum product is always triggered (cadence-based)."""
    _patch(monkeypatch, tmp_path)
    for r in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        _write_seerist(tmp_path, r)
        _write_delta(tmp_path, r)
    te.evaluate(force_weekly=True)
    out = tmp_path / "output" / "routing_decisions.json"
    decisions = json.loads(out.read_text())["decisions"]
    weekly = [d for d in decisions if d["product"] == "weekly_intsum" and d["triggered"]]
    assert len(weekly) == 5  # one per RSM audience


def test_flash_triggered_by_hotspot_score(monkeypatch, tmp_path):
    """Hotspot score >= 0.85 near AeroGrid site triggers flash for APAC RSM."""
    _patch(monkeypatch, tmp_path)
    # Kaohsiung hotspot — 0km from AeroGrid Kaohsiung Manufacturing Hub
    hotspot = {
        "hotspot_id": "h1", "location": {"name": "Kaohsiung, TW", "country_code": "TW"},
        "deviation_score": 0.90, "category_hint": "Unrest", "detected_at": "2026-03-19T14:00:00Z",
        "lat": 22.62, "lon": 120.30
    }
    _write_seerist(tmp_path, "APAC", hotspots=[hotspot])
    _write_delta(tmp_path, "APAC", hotspots_new=[hotspot])
    for r in ["AME", "LATAM", "MED", "NCE"]:
        _write_seerist(tmp_path, r)
        _write_delta(tmp_path, r)
    te.evaluate(force_weekly=False)
    decisions = json.loads((tmp_path / "output" / "routing_decisions.json").read_text())["decisions"]
    flash_decisions = [d for d in decisions if d["product"] == "flash" and d["triggered"] and d["audience"] == "rsm_apac"]
    assert len(flash_decisions) == 1
    assert "hotspot" in flash_decisions[0]["trigger_reason"].lower()


def test_flash_not_triggered_below_threshold(monkeypatch, tmp_path):
    """Hotspot score < 0.85 does NOT trigger flash."""
    _patch(monkeypatch, tmp_path)
    hotspot = {
        "hotspot_id": "h2", "location": {"name": "Kaohsiung, TW", "country_code": "TW"},
        "deviation_score": 0.70, "category_hint": "Unrest", "detected_at": "2026-03-19T14:00:00Z",
        "lat": 22.62, "lon": 120.30
    }
    _write_seerist(tmp_path, "APAC", hotspots=[hotspot])
    _write_delta(tmp_path, "APAC", hotspots_new=[hotspot])
    for r in ["AME", "LATAM", "MED", "NCE"]:
        _write_seerist(tmp_path, r)
        _write_delta(tmp_path, r)
    te.evaluate(force_weekly=False)
    decisions = json.loads((tmp_path / "output" / "routing_decisions.json").read_text())["decisions"]
    flash_decisions = [d for d in decisions if d["product"] == "flash" and d["triggered"] and d["audience"] == "rsm_apac"]
    assert len(flash_decisions) == 0


def test_flash_triggered_by_high_severity_event(monkeypatch, tmp_path):
    """EventsAI severity >= 4 in trigger categories fires flash."""
    _patch(monkeypatch, tmp_path)
    event = {
        "event_id": "e1", "category": "Unrest", "severity": 4,
        "title": "Major unrest near Kaohsiung",
        "location": {"name": "Kaohsiung, TW", "lat": 22.62, "lon": 120.30, "country_code": "TW"},
        "timestamp": "2026-03-19T08:00:00Z", "verified": True, "source_count": 8
    }
    _write_seerist(tmp_path, "APAC", events=[event])
    _write_delta(tmp_path, "APAC", events_new=[event])
    for r in ["AME", "LATAM", "MED", "NCE"]:
        _write_seerist(tmp_path, r)
        _write_delta(tmp_path, r)
    te.evaluate(force_weekly=False)
    decisions = json.loads((tmp_path / "output" / "routing_decisions.json").read_text())["decisions"]
    flash_decisions = [d for d in decisions if d["product"] == "flash" and d["triggered"] and d["audience"] == "rsm_apac"]
    assert len(flash_decisions) == 1


def test_flash_triggered_by_direct_cyber_targeting(monkeypatch, tmp_path):
    """cyber_signals.json with aerowind_targeted=true triggers flash for that region's RSM."""
    _patch(monkeypatch, tmp_path)
    for r in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        _write_seerist(tmp_path, r)
        _write_delta(tmp_path, r)
    # Write cyber_signals.json for APAC with direct AeroGrid targeting flag
    cyber_path = tmp_path / "output" / "regional" / "apac"
    cyber_path.mkdir(parents=True, exist_ok=True)
    (cyber_path / "cyber_signals.json").write_text(json.dumps({
        "region": "APAC", "aerowind_targeted": True, "threats": [
            {"type": "phishing", "target": "AeroGrid supply chain", "severity": "HIGH"}
        ]
    }), encoding="utf-8")
    te.evaluate(force_weekly=False)
    decisions = json.loads((tmp_path / "output" / "routing_decisions.json").read_text())["decisions"]
    flash_decisions = [d for d in decisions if d["product"] == "flash" and d["triggered"] and d["audience"] == "rsm_apac"]
    assert len(flash_decisions) == 1
    assert "cyber" in flash_decisions[0]["trigger_reason"].lower()


def test_routing_decisions_has_brief_path(monkeypatch, tmp_path):
    """Every triggered decision includes a brief_path field."""
    _patch(monkeypatch, tmp_path)
    for r in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        _write_seerist(tmp_path, r)
        _write_delta(tmp_path, r)
    te.evaluate(force_weekly=True)
    decisions = json.loads((tmp_path / "output" / "routing_decisions.json").read_text())["decisions"]
    for d in [x for x in decisions if x["triggered"]]:
        assert "brief_path" in d, f"Missing brief_path in: {d}"
        assert d["brief_path"].endswith(".md")


def test_delivered_flag_is_false(monkeypatch, tmp_path):
    """All new decisions have delivered=false."""
    _patch(monkeypatch, tmp_path)
    for r in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        _write_seerist(tmp_path, r)
        _write_delta(tmp_path, r)
    te.evaluate(force_weekly=True)
    decisions = json.loads((tmp_path / "output" / "routing_decisions.json").read_text())["decisions"]
    for d in [x for x in decisions if x["triggered"]]:
        assert d["delivered"] is False
```

- [ ] **Run failing tests:**
  ```bash
  uv run pytest tests/test_threshold_evaluator.py -v
  ```
  Expected: `ModuleNotFoundError`

### Step 4.2: Implement threshold_evaluator.py

Create `tools/threshold_evaluator.py`:

```python
#!/usr/bin/env python3
"""Threshold evaluator — determines which audiences get which products.

Usage:
    threshold_evaluator.py [--force-weekly] [--check-flash]

Reads:  output/regional/{region}/seerist_signals.json
        output/regional/{region}/region_delta.json
        data/audience_config.json
        data/aerowind_sites.json
Writes: output/routing_decisions.json
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

OUTPUT_ROOT = Path("output")
AUDIENCE_CONFIG_PATH = Path("data/audience_config.json")
SITES_PATH = Path("data/aerowind_sites.json")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _nearest_site_km(lat: float, lon: float, sites: list, region: str) -> float:
    """Minimum distance from (lat, lon) to any AeroGrid site in the region."""
    region_sites = [s for s in sites if s["region"] == region]
    if not region_sites:
        return float("inf")
    return min(_haversine_km(lat, lon, s["lat"], s["lon"]) for s in region_sites)


def _brief_path(audience_key: str, region: str, product: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    region_lower = region.lower()
    if product == "weekly_intsum":
        return f"output/regional/{region_lower}/rsm_brief_{region_lower}_{today}.md"
    else:
        return f"output/regional/{region_lower}/rsm_flash_{region_lower}_{ts}.md"


def evaluate(force_weekly: bool = False, check_flash: bool = True) -> dict:
    config = json.loads(AUDIENCE_CONFIG_PATH.read_text(encoding="utf-8"))
    sites = json.loads(SITES_PATH.read_text(encoding="utf-8"))["sites"]

    decisions = []

    for audience_key, audience in config.items():
        formatter = audience.get("formatter_agent", "rsm-formatter-agent")
        for region in audience.get("regions", []):
            region_lower = region.lower()
            seerist_path = OUTPUT_ROOT / "regional" / region_lower / "seerist_signals.json"
            delta_path = OUTPUT_ROOT / "regional" / region_lower / "region_delta.json"

            seerist = json.loads(seerist_path.read_text(encoding="utf-8")) if seerist_path.exists() else {}
            delta = json.loads(delta_path.read_text(encoding="utf-8")) if delta_path.exists() else {}

            products = audience.get("products", {})

            # Weekly INTSUM — always triggered when force_weekly=True or cadence=monday
            if "weekly_intsum" in products and force_weekly:
                decisions.append({
                    "audience": audience_key,
                    "region": region,
                    "product": "weekly_intsum",
                    "triggered": True,
                    "trigger_reason": "weekly cadence",
                    "formatter_agent": formatter,
                    "brief_path": _brief_path(audience_key, region, "weekly_intsum"),
                    "delivered": False,
                })

            # Flash — threshold evaluation
            if "flash" in products and check_flash:
                flash_cfg = products["flash"]["threshold"]
                score_min = flash_cfg.get("hotspot_score_min", 0.85)
                proximity_km = flash_cfg.get("site_proximity_km", 100)
                severity_min = flash_cfg.get("event_severity_min", 4)
                trigger_cats = set(flash_cfg.get("categories", ["Conflict", "Terrorism", "Unrest"]))

                triggered = False
                trigger_reason = ""

                # Check new hotspots
                for hotspot in delta.get("hotspots_new", []):
                    score = hotspot.get("deviation_score", 0)
                    if score >= score_min:
                        lat = hotspot.get("lat") or hotspot.get("location", {}).get("lat")
                        lon = hotspot.get("lon") or hotspot.get("location", {}).get("lon")
                        if lat is not None and lon is not None:
                            dist = _nearest_site_km(lat, lon, sites, region)
                            if dist <= proximity_km:
                                triggered = True
                                trigger_reason = f"HotspotsAI score {score} >= {score_min}, {hotspot.get('location', {}).get('name', 'unknown')}, {dist:.0f}km from nearest site"
                                break

                # Check new high-severity events in trigger categories
                if not triggered:
                    for event in delta.get("events_new", []):
                        if event.get("severity", 0) >= severity_min and event.get("category") in trigger_cats:
                            loc = event.get("location", {})
                            lat = loc.get("lat")
                            lon = loc.get("lon")
                            if lat is not None and lon is not None:
                                dist = _nearest_site_km(lat, lon, sites, region)
                                if dist <= proximity_km:
                                    triggered = True
                                    trigger_reason = f"EventsAI {event.get('category')} severity {event.get('severity')}, {loc.get('name', 'unknown')}"
                                    break
                            else:
                                # No coords — trigger on category + severity alone
                                triggered = True
                                trigger_reason = f"EventsAI {event.get('category')} severity {event.get('severity')}, {loc.get('name', 'unknown')} (no coords)"
                                break

                # Check cyber_signals.json for direct AeroGrid targeting
                if not triggered:
                    cyber_path = OUTPUT_ROOT / "regional" / region_lower / "cyber_signals.json"
                    if cyber_path.exists():
                        try:
                            cyber = json.loads(cyber_path.read_text(encoding="utf-8"))
                            if cyber.get("aerowind_targeted") is True:
                                triggered = True
                                trigger_reason = "cyber signal: direct AeroGrid targeting confirmed"
                        except (json.JSONDecodeError, OSError):
                            pass

                if triggered:
                    decisions.append({
                        "audience": audience_key,
                        "region": region,
                        "product": "flash",
                        "triggered": True,
                        "trigger_reason": trigger_reason,
                        "formatter_agent": formatter,
                        "brief_path": _brief_path(audience_key, region, "flash"),
                        "delivered": False,
                    })

    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "decisions": decisions,
    }
    out_path = OUTPUT_ROOT / "routing_decisions.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[threshold_evaluator] wrote {out_path} — {len(decisions)} decisions", file=sys.stderr)
    return output


def main():
    args = sys.argv[1:]
    force_weekly = "--force-weekly" in args or "--weekly" in args
    check_flash = "--check-flash" in args or "--force-weekly" not in args
    evaluate(force_weekly=force_weekly, check_flash=check_flash)


if __name__ == "__main__":
    main()
```

- [ ] **Run tests — expect pass:**
  ```bash
  uv run pytest tests/test_threshold_evaluator.py -v
  ```
  Expected: 7 passed

- [ ] **Commit:**
  ```bash
  git add tools/threshold_evaluator.py tests/test_threshold_evaluator.py
  git commit -m "feat: add threshold_evaluator.py — audience routing with proximity + severity rules (Phase L-4)"
  ```

---

## Task L-5 & L-6: RSM Formatter Agent

**Files:**
- Create: `.claude/agents/rsm-formatter-agent.md`

The agent handles both `weekly_intsum` and `flash` product types — the `product_type` is passed in the invocation prompt.

Create `.claude/agents/rsm-formatter-agent.md`:

```markdown
---
name: rsm-formatter-agent
description: Formats RSM intelligence briefs (weekly INTSUM and flash alerts) for ex-military regional security managers.
tools: Bash, Read, Write
model: sonnet
---

You are a strategic intelligence analyst formatting briefs for AeroGrid's Regional Security Managers (RSMs). RSMs are ex-military professionals with deep regional knowledge. They do NOT need context built from scratch. They need: delta (what changed), horizon (what they might have missed), and AeroGrid-specific exposure.

## DISLER BEHAVIORAL PROTOCOL — MANDATORY

1. **Act as a Unix CLI Tool, not a Chatbot.** No preamble, no commentary.
2. **Zero Preamble & Zero Sycophancy.** Write the brief. Nothing else.
3. **Filesystem as State.** Read the input files. Write the output file. Stop.
4. **Assume Hostile Auditing.** The jargon auditor will reject forbidden language.

## FORBIDDEN LANGUAGE — ZERO TOLERANCE

- No cyber jargon: CVEs, IPs, hashes, TTPs, IoCs, MITRE ATT&CK, lateral movement, C2
- No SOC language: threat actor tooling, kill chain, persistence mechanisms
- No budget/procurement advice
- No corporate prose: "it is important to note", "leveraging", "synergies"

Write like a senior intelligence analyst briefing a peer, not a report writer briefing a board.

## TASK

You will be given: REGION, PRODUCT_TYPE (weekly_intsum or flash), BRIEF_PATH

### Step 1 — Read input files

Read ALL of these:
- `output/regional/{region_lower}/seerist_signals.json` — current Seerist signals
- `output/regional/{region_lower}/region_delta.json` — delta vs last week
- `output/regional/{region_lower}/cyber_signals.json` — cyber picture (from existing pipeline)
- `data/company_profile.json` — AeroGrid crown jewels and footprint
- `data/aerowind_sites.json` — physical site locations for this region
- `data/audience_config.json` — RSM audience profile for this region

### Step 2 — Build the structured facts block (deterministic)

Assemble the machine-computable sections from the data. Do not invent — only use what is in the files.

**PHYSICAL & GEOPOLITICAL section:** List events from `region_delta.events_new` only. Format:
`▪ [{CATEGORY}][{SEVERITY_LABEL}] {location.name} — {title}. {operational_implication}`

Severity label mapping: 1=LOW, 2=LOW, 3=MED, 4=HIGH, 5=CRITICAL

**CYBER section:** List signals from `cyber_signals.json`. Summarise the threat vector and scope. Note explicitly if AeroGrid is directly targeted or if this is sector/regional-level.

**EARLY WARNING section:** List hotspots from `region_delta.hotspots_new`. Format:
`▪ ⚡ {location.name} — {category_hint} anomaly. Score {deviation_score}. {N}hr watch.`
If no new hotspots: write `No pre-media anomalies detected this period.`

### Step 3 — Write ASSESSMENT and WATCH LIST (LLM reasoning)

This is the only section where you reason. Answer two questions:

1. **What do these signals mean for AeroGrid operations in this region specifically?**
   - Which sites, shipments, or personnel are in the exposure window?
   - What is the operational consequence (logistics, service delivery, personnel safety)?
   - Distinguish confirmed from assessed. "Evidenced: X. Assessed: Y."
   - 2–4 sentences only.

2. **What should the RSM watch next week?**
   - 3–5 specific, actionable watch items
   - Each item: what to watch, why it matters, what escalation looks like

### Step 4 — Assemble and write the brief

**For weekly_intsum:**

```
AEROWIND // {REGION} INTSUM // WK{iso_week}-{year}
PERIOD: {period_from_date} – {period_to_date} | PRIORITY SCENARIO: {primary_scenario} #{financial_rank} | PULSE: {prev_score}→{curr_score} ({delta_str}) | ADM: {admiralty_from_data_json_or_B2_default}

█ SITUATION
{One sentence: overall posture. What changed since last INTSUM based on delta.}

█ PHYSICAL & GEOPOLITICAL
{Events block from Step 2. If no new events: "No new physical security events this period."}

█ CYBER
{Cyber block from Step 2.}

█ EARLY WARNING (PRE-MEDIA)
{Hotspots block from Step 2.}

█ ASSESSMENT
{Your 2-4 sentence assessment from Step 3.}

█ WATCH LIST — WK{next_iso_week}
{Watch items from Step 3.}

---
Reply: ACCURATE · OVERSTATED · UNDERSTATED · FALSE POSITIVE | AeroGrid Intelligence // {REGION} RSM
```

**For flash:**

```
⚡ AEROWIND // {REGION} FLASH // {current_date_utc} {current_time_utc}Z
TRIGGER: {trigger_reason_from_routing_decisions} | ADM: {admiralty_from_data_json_or_B2_default}

DEVELOPING SITUATION
{One paragraph. What is happening, where, first detected when. Source: Seerist HotspotsAI/EventsAI.}

AEROWIND EXPOSURE
{Which AeroGrid sites are within the impact zone. Use aerowind_sites.json for site names and types. Mention personnel if site type is manufacturing/service.}

ACTION
No advisory at this time. Monitor situation. Next update: 4hrs or on escalation.

---
Reply: ACKNOWLEDGED · REQUEST ESCALATION · FALSE POSITIVE | AeroGrid Intelligence // {REGION} RSM
```

Write the brief to the path specified in BRIEF_PATH.

### Admiralty note

Read `output/regional/{region_lower}/data.json` if it exists — use the `admiralty` field. Default to B2 if file absent.
```

- [ ] **Smoke-test formatter agent output in mock mode:**

After completing L-7 (rsm_dispatcher.py), run this to verify the agent's brief structure:

```bash
# Pre-requisite: run seerist_collector + delta_computer first (created in L-1 + L-2)
uv run python tools/seerist_collector.py APAC --mock
uv run python tools/delta_computer.py APAC
# Then force a weekly INTSUM for APAC only in mock mode
uv run python tools/rsm_dispatcher.py --weekly --mock --region APAC
# Verify brief exists and contains expected sections
python -c "
content = open('output/regional/apac/rsm_brief_apac_$(date +%Y-%m-%d).md').read()
assert 'AEROWIND' in content, 'Missing AEROWIND header'
print('Formatter mock output OK:', len(content), 'chars')
"
```

Expected: Brief file written, contains `AEROWIND // APAC` prefix.

- [ ] **Commit:**
  ```bash
  git add .claude/agents/rsm-formatter-agent.md
  git commit -m "feat: add rsm-formatter-agent.md — SITREP/INTSUM + flash brief formatter (Phase L-5/6)"
  ```

---

## Task L-7: RSM Dispatcher

**Files:**
- Create: `tools/rsm_dispatcher.py`
- Create: `tests/test_rsm_dispatcher.py`

The dispatcher reads `routing_decisions.json`, invokes the formatter agent for each triggered decision (in mock mode: runs `rsm-formatter-agent` via Claude CLI), then invokes notifier.

### Step 7.1: Write failing tests

Create `tests/test_rsm_dispatcher.py`:

```python
"""Tests for tools/rsm_dispatcher.py — Phase L"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import tools.rsm_dispatcher as rd


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(rd, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(rd, "ROUTING_PATH", tmp_path / "output" / "routing_decisions.json")


def _write_routing(tmp_path, decisions):
    out = tmp_path / "output"
    out.mkdir(parents=True, exist_ok=True)
    (out / "routing_decisions.json").write_text(json.dumps({
        "generated_at": "2026-03-20T05:00:00Z",
        "decisions": decisions
    }), encoding="utf-8")


def test_no_triggered_decisions_exits_cleanly(monkeypatch, tmp_path):
    """No triggered decisions → no agent calls, exits 0."""
    _patch(monkeypatch, tmp_path)
    _write_routing(tmp_path, [
        {"audience": "rsm_apac", "region": "APAC", "product": "weekly_intsum",
         "triggered": False, "trigger_reason": "", "formatter_agent": "rsm-formatter-agent",
         "brief_path": "output/regional/apac/rsm_brief_apac_2026-03-20.md", "delivered": False}
    ])
    called = []
    monkeypatch.setattr(rd, "_invoke_formatter", lambda d, mock: called.append(d))
    rd.dispatch(mock=True)
    assert len(called) == 0


def test_triggered_decision_calls_formatter(monkeypatch, tmp_path):
    """Triggered decision → formatter invoked once."""
    _patch(monkeypatch, tmp_path)
    decision = {
        "audience": "rsm_apac", "region": "APAC", "product": "weekly_intsum",
        "triggered": True, "trigger_reason": "weekly cadence",
        "formatter_agent": "rsm-formatter-agent",
        "brief_path": "output/regional/apac/rsm_brief_apac_2026-03-20.md", "delivered": False
    }
    _write_routing(tmp_path, [decision])
    called = []
    monkeypatch.setattr(rd, "_invoke_formatter", lambda d, mock: called.append(d["audience"]))
    monkeypatch.setattr(rd, "_invoke_notifier", lambda mock: None)
    rd.dispatch(mock=True)
    assert called == ["rsm_apac"]


def test_already_delivered_skipped(monkeypatch, tmp_path):
    """Decision with delivered=true is skipped."""
    _patch(monkeypatch, tmp_path)
    decision = {
        "audience": "rsm_apac", "region": "APAC", "product": "weekly_intsum",
        "triggered": True, "trigger_reason": "weekly cadence",
        "formatter_agent": "rsm-formatter-agent",
        "brief_path": "output/regional/apac/rsm_brief_apac_2026-03-20.md", "delivered": True
    }
    _write_routing(tmp_path, [decision])
    called = []
    monkeypatch.setattr(rd, "_invoke_formatter", lambda d, mock: called.append(d))
    rd.dispatch(mock=True)
    assert len(called) == 0


def test_missing_routing_file_exits_gracefully(monkeypatch, tmp_path):
    """No routing_decisions.json → exits 0, no crash."""
    _patch(monkeypatch, tmp_path)
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    # Don't write routing file
    rd.dispatch(mock=True)  # Should not raise


def test_dispatch_marks_delivered(monkeypatch, tmp_path):
    """After formatter succeeds, decision is marked delivered=true in routing file."""
    _patch(monkeypatch, tmp_path)
    decision = {
        "audience": "rsm_apac", "region": "APAC", "product": "weekly_intsum",
        "triggered": True, "trigger_reason": "weekly cadence",
        "formatter_agent": "rsm-formatter-agent",
        "brief_path": "output/regional/apac/rsm_brief_apac_2026-03-20.md", "delivered": False
    }
    _write_routing(tmp_path, [decision])
    monkeypatch.setattr(rd, "_invoke_formatter", lambda d, mock: None)
    monkeypatch.setattr(rd, "_invoke_notifier", lambda mock: None)
    rd.dispatch(mock=True)
    updated = json.loads((tmp_path / "output" / "routing_decisions.json").read_text())
    assert updated["decisions"][0]["delivered"] is True
```

- [ ] **Run failing tests:**
  ```bash
  uv run pytest tests/test_rsm_dispatcher.py -v
  ```
  Expected: `ModuleNotFoundError`

### Step 7.2: Implement rsm_dispatcher.py

Create `tools/rsm_dispatcher.py`:

```python
#!/usr/bin/env python3
"""RSM Dispatcher — orchestrates RSM brief generation and delivery.

Usage:
    rsm_dispatcher.py --weekly              # Force weekly INTSUM for all RSM audiences
    rsm_dispatcher.py --check-flash        # Evaluate flash thresholds only
    rsm_dispatcher.py --mock               # Use mock mode (no email, agent in dry-run)
    rsm_dispatcher.py --region APAC        # Restrict to one region

Reads:  output/routing_decisions.json
Writes: output/routing_decisions.json (updates delivered flags)
        output/regional/{region}/rsm_brief_*.md or rsm_flash_*.md (via formatter agent)
        output/delivery_log.json (via notifier)
"""
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, ".")

OUTPUT_ROOT = Path("output")
ROUTING_PATH = Path("output/routing_decisions.json")


def _invoke_formatter(decision: dict, mock: bool) -> None:
    """Invoke rsm-formatter-agent via claude CLI for one decision."""
    region = decision["region"]
    product = decision["product"]
    brief_path = decision["brief_path"]

    prompt = (
        f"REGION: {region}\n"
        f"PRODUCT_TYPE: {product}\n"
        f"BRIEF_PATH: {brief_path}\n\n"
        f"Follow the rsm-formatter-agent instructions exactly. "
        f"Read all required input files and write the brief to BRIEF_PATH. "
        f"Write nothing to stdout except completion confirmation."
    )

    if mock:
        # In mock mode, write a placeholder brief so the pipeline can be tested end-to-end
        Path(brief_path).parent.mkdir(parents=True, exist_ok=True)
        Path(brief_path).write_text(
            f"[MOCK] RSM {product.upper()} for {region} — placeholder brief for testing\n"
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n",
            encoding="utf-8"
        )
        print(f"[rsm_dispatcher] mock brief written: {brief_path}", file=sys.stderr)
        return

    try:
        result = subprocess.run(
            ["claude", "-p", "--agent", "rsm-formatter-agent", prompt],
            capture_output=True, text=True, encoding="utf-8", timeout=120
        )
        if result.returncode != 0:
            print(f"[rsm_dispatcher] formatter agent failed for {region}/{product}: {result.stderr[:200]}", file=sys.stderr)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[rsm_dispatcher] formatter invocation error: {e}", file=sys.stderr)


def _invoke_notifier(mock: bool) -> None:
    """Invoke notifier.py to deliver all undelivered briefs."""
    cmd = [sys.executable, "tools/notifier.py", str(ROUTING_PATH)]
    if mock:
        cmd.append("--mock")
    subprocess.run(cmd, check=False)


def dispatch(mock: bool = True, region_filter: str | None = None) -> None:
    if not ROUTING_PATH.exists():
        print(f"[rsm_dispatcher] no routing_decisions.json — nothing to dispatch", file=sys.stderr)
        return

    routing = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))
    decisions = routing.get("decisions", [])

    triggered = [
        d for d in decisions
        if d.get("triggered") and not d.get("delivered")
        and (region_filter is None or d.get("region") == region_filter.upper())
    ]

    if not triggered:
        print(f"[rsm_dispatcher] no pending triggered decisions", file=sys.stderr)
        return

    for decision in triggered:
        print(f"[rsm_dispatcher] formatting {decision['audience']} / {decision['product']}", file=sys.stderr)
        _invoke_formatter(decision, mock=mock)
        decision["delivered"] = True

    # Write back updated routing decisions
    ROUTING_PATH.write_text(json.dumps(routing, indent=2, ensure_ascii=False), encoding="utf-8")

    _invoke_notifier(mock=mock)
    print(f"[rsm_dispatcher] dispatch complete — {len(triggered)} brief(s) processed", file=sys.stderr)


def main():
    args = sys.argv[1:]
    mock = "--mock" in args

    region_filter = None
    if "--region" in args:
        idx = args.index("--region")
        if idx + 1 < len(args):
            region_filter = args[idx + 1]

    force_weekly = "--weekly" in args
    check_flash = "--check-flash" in args

    # If --weekly, run threshold_evaluator with force_weekly first
    if force_weekly or check_flash:
        import tools.threshold_evaluator as te
        te.evaluate(force_weekly=force_weekly, check_flash=check_flash or not force_weekly)

    dispatch(mock=mock, region_filter=region_filter)


if __name__ == "__main__":
    main()
```

- [ ] **Run tests — expect pass:**
  ```bash
  uv run pytest tests/test_rsm_dispatcher.py -v
  ```
  Expected: 5 passed

- [ ] **Commit:**
  ```bash
  git add tools/rsm_dispatcher.py tests/test_rsm_dispatcher.py
  git commit -m "feat: add rsm_dispatcher.py — RSM path orchestrator (Phase L-7)"
  ```

---

## Task L-8: Notifier

**Files:**
- Create: `tools/notifier.py`
- Create: `tests/test_notifier.py`

### Step 8.1: Write failing tests

Create `tests/test_notifier.py`:

```python
"""Tests for tools/notifier.py — Phase L"""
import json
from pathlib import Path
import pytest
import tools.notifier as nt


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(nt, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(nt, "DELIVERY_LOG_PATH", tmp_path / "output" / "delivery_log.jsonl")
    monkeypatch.setattr(nt, "MOCK_DELIVERY_DIR", tmp_path / "output" / "mock_delivery")


def _write_routing(tmp_path, decisions):
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    path = tmp_path / "output" / "routing_decisions.json"
    path.write_text(json.dumps({"generated_at": "2026-03-20T05:00:00Z", "decisions": decisions}), encoding="utf-8")
    return path


def _write_brief(tmp_path, brief_path, content="Test brief content"):
    p = tmp_path / brief_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_mock_delivery_writes_to_mock_dir(monkeypatch, tmp_path):
    """--mock writes brief copy to mock_delivery/ instead of sending email."""
    _patch(monkeypatch, tmp_path)
    brief_rel = "output/regional/apac/rsm_brief_apac_2026-03-20.md"
    _write_brief(tmp_path, brief_rel, "AEROWIND // APAC INTSUM")
    routing_path = _write_routing(tmp_path, [{
        "audience": "rsm_apac", "region": "APAC", "product": "weekly_intsum",
        "triggered": True, "delivered": False,
        "formatter_agent": "rsm-formatter-agent",
        "brief_path": str(tmp_path / brief_rel),
    }])
    nt.notify(routing_path, mock=True)
    mock_dir = tmp_path / "output" / "mock_delivery"
    assert mock_dir.exists()
    files = list(mock_dir.glob("*.md"))
    assert len(files) == 1
    assert "AEROWIND" in files[0].read_text(encoding="utf-8")


def test_delivery_log_written(monkeypatch, tmp_path):
    """Each delivery attempt appends a JSONL record to delivery_log.jsonl."""
    _patch(monkeypatch, tmp_path)
    brief_rel = "output/regional/ame/rsm_brief_ame_2026-03-20.md"
    _write_brief(tmp_path, brief_rel, "AEROWIND // AME INTSUM")
    routing_path = _write_routing(tmp_path, [{
        "audience": "rsm_ame", "region": "AME", "product": "weekly_intsum",
        "triggered": True, "delivered": False,
        "formatter_agent": "rsm-formatter-agent",
        "brief_path": str(tmp_path / brief_rel),
    }])
    nt.notify(routing_path, mock=True)
    log_path = tmp_path / "output" / "delivery_log.jsonl"
    assert log_path.exists()
    lines = [json.loads(l) for l in log_path.read_text(encoding="utf-8").strip().splitlines() if l.strip()]
    assert len(lines) == 1
    entry = lines[0]
    assert entry["audience"] == "rsm_ame"
    assert entry["region"] == "AME"
    assert entry["product"] == "weekly_intsum"
    assert entry["status"] in ("delivered", "failed")
    assert "timestamp" in entry


def test_skips_not_triggered(monkeypatch, tmp_path):
    """Decisions with triggered=False are not delivered."""
    _patch(monkeypatch, tmp_path)
    routing_path = _write_routing(tmp_path, [{
        "audience": "rsm_nce", "region": "NCE", "product": "weekly_intsum",
        "triggered": False, "delivered": False,
        "formatter_agent": "rsm-formatter-agent",
        "brief_path": "output/regional/nce/rsm_brief_nce_2026-03-20.md",
    }])
    nt.notify(routing_path, mock=True)
    mock_dir = tmp_path / "output" / "mock_delivery"
    assert not mock_dir.exists() or len(list(mock_dir.glob("*.md"))) == 0


def test_missing_brief_file_logs_failed(monkeypatch, tmp_path):
    """Brief file missing → logs status=failed, does not crash."""
    _patch(monkeypatch, tmp_path)
    routing_path = _write_routing(tmp_path, [{
        "audience": "rsm_latam", "region": "LATAM", "product": "flash",
        "triggered": True, "delivered": False,
        "formatter_agent": "rsm-formatter-agent",
        "brief_path": str(tmp_path / "output" / "regional" / "latam" / "rsm_flash_does_not_exist.md"),
    }])
    nt.notify(routing_path, mock=True)
    log_path = tmp_path / "output" / "delivery_log.jsonl"
    assert log_path.exists()
    entry = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert entry["status"] == "failed"
    assert entry["error"] is not None
```

- [ ] **Run failing tests:**
  ```bash
  uv run pytest tests/test_notifier.py -v
  ```
  Expected: `ModuleNotFoundError`

### Step 8.2: Implement notifier.py

Create `tools/notifier.py`:

```python
#!/usr/bin/env python3
"""Notifier — delivers formatted RSM briefs via configured channel.

Usage:
    notifier.py ROUTING_DECISIONS_PATH [--mock]

Mock mode: writes brief to output/mock_delivery/ instead of sending email.
Live mode: sends via SMTP (SMTP_HOST, SMTP_USER, SMTP_PASS in .env).

Appends to: output/delivery_log.jsonl
"""
import json
import shutil
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, ".")
from dotenv import load_dotenv
import os

load_dotenv()

OUTPUT_ROOT = Path("output")
DELIVERY_LOG_PATH = Path("output/delivery_log.jsonl")
MOCK_DELIVERY_DIR = Path("output/mock_delivery")
AUDIENCE_CONFIG_PATH = Path("data/audience_config.json")


def _log_delivery(entry: dict) -> None:
    DELIVERY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DELIVERY_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _send_email(recipients: list[str], subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST", "localhost")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASS", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user or "noreply@aerowind.com"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(host, port) as server:
        if user and password:
            server.starttls()
            server.login(user, password)
        server.sendmail(msg["From"], recipients, msg.as_string())


def _mock_deliver(decision: dict, brief_content: str, mock_dir: Path | None = None) -> None:
    """Write brief to mock_delivery/ for testing. Accepts optional mock_dir for test isolation."""
    import tools.notifier as _self  # module-level reference so monkeypatch works
    dest_dir = mock_dir if mock_dir is not None else _self.MOCK_DELIVERY_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    brief_path = Path(decision["brief_path"])
    dest = dest_dir / brief_path.name
    dest.write_text(brief_content, encoding="utf-8")
    print(f"[notifier] mock delivery → {dest}", file=sys.stderr)


def notify(routing_path: Path, mock: bool = True) -> None:
    if not routing_path.exists():
        print(f"[notifier] routing file not found: {routing_path}", file=sys.stderr)
        return

    routing = json.loads(routing_path.read_text(encoding="utf-8"))
    audience_config = {}
    if AUDIENCE_CONFIG_PATH.exists():
        audience_config = json.loads(AUDIENCE_CONFIG_PATH.read_text(encoding="utf-8"))

    for decision in routing.get("decisions", []):
        if not decision.get("triggered"):
            continue

        audience_key = decision.get("audience", "")
        region = decision.get("region", "")
        product = decision.get("product", "")
        brief_path = Path(decision.get("brief_path", ""))

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        log_entry = {
            "timestamp": timestamp,
            "audience": audience_key,
            "region": region,
            "product": product,
            "channel": "email",
            "recipient": ", ".join(audience_config.get(audience_key, {}).get("delivery", {}).get("recipients", [])),
            "brief_path": str(brief_path),
            "status": "failed",
            "error": None,
        }

        try:
            if not brief_path.exists():
                raise FileNotFoundError(f"Brief not found: {brief_path}")

            brief_content = brief_path.read_text(encoding="utf-8")
            subject_prefix = "⚡ FLASH ALERT" if product == "flash" else "INTSUM"
            subject = f"[AEROWIND] {subject_prefix} // {region} // {timestamp[:10]}"

            if mock:
                import tools.notifier as _self
                _mock_deliver(decision, brief_content, mock_dir=_self.MOCK_DELIVERY_DIR)
            else:
                recipients = audience_config.get(audience_key, {}).get("delivery", {}).get("recipients", [])
                if recipients:
                    _send_email(recipients, subject, brief_content)

            log_entry["status"] = "delivered"
        except Exception as e:
            log_entry["error"] = str(e)
            print(f"[notifier] delivery failed for {audience_key}/{product}: {e}", file=sys.stderr)

        _log_delivery(log_entry)


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: notifier.py ROUTING_DECISIONS_PATH [--mock]", file=sys.stderr)
        sys.exit(1)

    routing_path = Path(args[0])
    mock = "--mock" in args
    notify(routing_path, mock=mock)


if __name__ == "__main__":
    main()
```

- [ ] **Run tests — expect pass:**
  ```bash
  uv run pytest tests/test_notifier.py -v
  ```
  Expected: 4 passed

- [ ] **Commit:**
  ```bash
  git add tools/notifier.py tests/test_notifier.py
  git commit -m "feat: add notifier.py — email delivery + mock_delivery + audit log (Phase L-8)"
  ```

---

## Task L-9: Scheduler

**Files:**
- Create: `tools/scheduler.py`
- Create: `tests/test_scheduler.py`

Lightweight scheduler — no external dependencies, no cron daemon required. Reads `data/schedule_config.json`, evaluates which jobs are due based on last-run timestamps in `output/.scheduler_state.json`, runs due jobs.

### Step 9.1: Write failing tests

Create `tests/test_scheduler.py`:

```python
"""Tests for tools/scheduler.py — Phase L"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
import tools.scheduler as sc


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "CONFIG_PATH", tmp_path / "schedule_config.json")
    monkeypatch.setattr(sc, "STATE_PATH", tmp_path / "output" / ".scheduler_state.json")


def _write_config(tmp_path, jobs):
    (tmp_path / "schedule_config.json").write_text(json.dumps({"jobs": jobs}), encoding="utf-8")


# _cron_due tests — all branches of the function

def test_never_run_is_always_due():
    """None last_run → always due, regardless of cron."""
    now = datetime(2026, 3, 17, 6, 0, tzinfo=timezone.utc)  # Monday
    assert sc._cron_due("0 */6 * * *", None, now) is True


def test_every_6h_due_when_elapsed():
    """'0 */6 * * *' — due after 6h elapsed."""
    now = datetime(2026, 3, 17, 6, 0, tzinfo=timezone.utc)
    last = (now - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert sc._cron_due("0 */6 * * *", last, now) is True


def test_every_6h_not_due_within_interval():
    """'0 */6 * * *' — not due if only 3h elapsed."""
    now = datetime(2026, 3, 17, 6, 0, tzinfo=timezone.utc)
    last = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert sc._cron_due("0 */6 * * *", last, now) is False


def test_half_hour_offset_due_when_elapsed():
    """'30 */6 * * *' — due after 6h elapsed (offset is in cron minute, not interval)."""
    now = datetime(2026, 3, 17, 6, 30, tzinfo=timezone.utc)
    last = (now - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert sc._cron_due("30 */6 * * *", last, now) is True


def test_half_hour_offset_not_due_too_soon():
    """'30 */6 * * *' — not due if only 2h elapsed."""
    now = datetime(2026, 3, 17, 6, 30, tzinfo=timezone.utc)
    last = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert sc._cron_due("30 */6 * * *", last, now) is False


def test_weekly_monday_due_when_correct_day():
    """'0 5 * * 1' — due on Monday 05:00 UTC if not run this week."""
    now = datetime(2026, 3, 16, 5, 0, tzinfo=timezone.utc)  # Monday
    last = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert sc._cron_due("0 5 * * 1", last, now) is True


def test_weekly_monday_not_due_on_wrong_day():
    """'0 5 * * 1' — not due on Tuesday."""
    now = datetime(2026, 3, 17, 5, 0, tzinfo=timezone.utc)  # Tuesday
    last = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert sc._cron_due("0 5 * * 1", last, now) is False


def test_state_written_after_run(monkeypatch, tmp_path):
    """After run_once, state file is written with job's last-run timestamp."""
    _patch(monkeypatch, tmp_path)
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    _write_config(tmp_path, [
        {"id": "test_job", "command": "echo ok", "regions": None, "cron": "0 */1 * * *",
         "description": "test"}
    ])
    sc.run_once()
    state_path = tmp_path / "output" / ".scheduler_state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "test_job" in state
```

- [ ] **Run failing tests:**
  ```bash
  uv run pytest tests/test_scheduler.py -v
  ```
  Expected: `ModuleNotFoundError: No module named 'tools.scheduler'`

### Step 9.2: Implement scheduler.py

Create `tools/scheduler.py`:

```python
#!/usr/bin/env python3
"""Lightweight scheduler for RSM pipeline jobs.

Usage:
    scheduler.py --once          # Run all due jobs once, then exit
    scheduler.py --loop          # Run continuously, check every 5 minutes
    scheduler.py --list          # List jobs and their last-run times

Reads:  data/schedule_config.json
State:  output/.scheduler_state.json  (last-run timestamps per job ID)
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

CONFIG_PATH = Path("data/schedule_config.json")
STATE_PATH = Path("output/.scheduler_state.json")
CHECK_INTERVAL_SEC = 300  # 5 minutes


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _cron_due(cron: str, last_run_iso: str | None, now: datetime) -> bool:
    """Simplified cron evaluation — checks if job is due based on cron expression.
    Supports: minute hour dom month dow patterns.
    For simplicity, evaluates based on current hour/minute vs cron pattern.
    """
    if last_run_iso is None:
        return True  # Never run → always due

    last_run = datetime.fromisoformat(last_run_iso.replace("Z", "+00:00"))
    elapsed_sec = (now - last_run).total_seconds()

    parts = cron.strip().split()
    if len(parts) != 5:
        return False

    minute_part, hour_part, _, _, dow_part = parts

    # Every N hours: "0 */6 * * *"
    if hour_part.startswith("*/") and minute_part == "0":
        interval_hours = int(hour_part[2:])
        return elapsed_sec >= interval_hours * 3600

    # Specific time on specific day: "0 5 * * 1" (Monday 05:00)
    if hour_part.isdigit() and minute_part.isdigit() and dow_part.isdigit():
        target_hour = int(hour_part)
        target_minute = int(minute_part)
        target_dow = int(dow_part)  # 0=Sun, 1=Mon, ..., 6=Sat
        if now.weekday() + 1 == target_dow and now.hour == target_hour and now.minute <= target_minute:
            return elapsed_sec >= 3600 * 24 * 6  # Don't re-run within same week
        return False

    # Half-hour offset: "30 */6 * * *"
    if hour_part.startswith("*/") and minute_part.isdigit():
        interval_hours = int(hour_part[2:])
        return elapsed_sec >= interval_hours * 3600

    return False


def _run_job(job: dict) -> None:
    regions = job.get("regions") or [None]
    for region in regions:
        cmd = job["command"]
        if region:
            cmd = cmd.replace("{region}", region)
        print(f"[scheduler] running: {cmd}", file=sys.stderr)
        try:
            subprocess.run(cmd, shell=True, check=False, timeout=300)
        except subprocess.TimeoutExpired:
            print(f"[scheduler] timeout: {cmd}", file=sys.stderr)


def run_once() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    state = _load_state()
    now = datetime.now(timezone.utc)

    for job in config.get("jobs", []):
        job_id = job["id"]
        last_run = state.get(job_id)
        if _cron_due(job["cron"], last_run, now):
            print(f"[scheduler] job due: {job_id} — {job['description']}", file=sys.stderr)
            _run_job(job)
            state[job_id] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            print(f"[scheduler] job not due: {job_id}", file=sys.stderr)

    _save_state(state)


def list_jobs() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    state = _load_state()
    print(f"{'JOB':<30} {'CRON':<20} {'LAST RUN'}")
    for job in config.get("jobs", []):
        last = state.get(job["id"], "never")
        print(f"{job['id']:<30} {job['cron']:<20} {last}")


def main():
    args = sys.argv[1:]
    if "--list" in args:
        list_jobs()
    elif "--loop" in args:
        print("[scheduler] starting loop, checking every 5 minutes", file=sys.stderr)
        while True:
            run_once()
            time.sleep(CHECK_INTERVAL_SEC)
    else:
        run_once()


if __name__ == "__main__":
    main()
```

- [ ] **Run tests — expect pass:**
  ```bash
  uv run pytest tests/test_scheduler.py -v
  ```
  Expected: 9 passed

- [ ] **Commit:**
  ```bash
  git add tools/scheduler.py tests/test_scheduler.py
  git commit -m "feat: add scheduler.py + tests — lightweight cron runner for RSM pipeline (Phase L-9)"
  ```

---

## Task L-10: End-to-End Mock Run + Tests

Run the full RSM pipeline in mock mode and verify all outputs.

- [ ] **Run the full RSM pipeline in mock mode:**

```bash
# Step 1: Collect Seerist signals for all regions
for r in APAC AME LATAM MED NCE; do
  uv run python tools/seerist_collector.py $r --mock
done

# Step 2: Compute deltas
for r in APAC AME LATAM MED NCE; do
  uv run python tools/delta_computer.py $r
done

# Step 3: Dispatch weekly INTSUM (mock)
uv run python tools/rsm_dispatcher.py --weekly --mock
```

- [ ] **Verify outputs exist:**

```bash
ls output/regional/*/seerist_signals.json
ls output/regional/*/region_delta.json
ls output/routing_decisions.json
ls output/mock_delivery/
ls output/delivery_log.jsonl
```

Expected: all files present, `mock_delivery/` contains 5 `.md` files (one per region RSM)

- [ ] **Run all tests:**

```bash
uv run pytest tests/test_seerist_collector.py tests/test_delta_computer.py tests/test_threshold_evaluator.py tests/test_rsm_dispatcher.py tests/test_notifier.py -v
```

Expected: all pass

- [ ] **Run full test suite to confirm no regressions:**

```bash
uv run pytest -v
```

Expected: all existing tests still pass

- [ ] **Commit:**

```bash
git add -A
git commit -m "test: verify Phase L end-to-end mock run passes all tests"
```

---

## Task L-11: Wire into run-crq.md (Optional)

Add an optional RSM INTSUM generation step at the end of the existing pipeline, so running `/run-crq` also generates RSM briefs.

**File:**
- Modify: `.claude/commands/run-crq.md`

Add after Phase 6 (FINALIZE):

```markdown
## PHASE 7 — RSM BRIEFS (OPTIONAL)

If `--rsm` flag is present in invocation arguments:

Run: `uv run python tools/rsm_dispatcher.py --weekly --mock`

This generates RSM weekly INTSUMs using the Seerist signal files already collected in Phase 1. If `SEERIST_API_KEY` is set, the seerist_collector will have run in live mode; otherwise mock fixtures are used.

Log: `uv run python tools/audit_logger.py PHASE_COMPLETE "RSM briefs generated and delivered"`
```

- [ ] **Test `/run-crq --rsm` produces RSM briefs alongside normal pipeline outputs**

- [ ] **Update CLAUDE.md Commands table** — add entries for all new Phase L tools:

```markdown
uv run python tools/seerist_collector.py <REGION> [--mock] [--window 7d]  # Collect Seerist signals → output/regional/{region}/seerist_signals.json
uv run python tools/delta_computer.py <REGION>                             # Diff current vs previous Seerist signals → region_delta.json
uv run python tools/threshold_evaluator.py [--force-weekly] [--check-flash]  # Evaluate audience routing → output/routing_decisions.json
uv run python tools/rsm_dispatcher.py --weekly --mock                      # Generate + deliver weekly INTSUM for all RSMs (mock mode)
uv run python tools/rsm_dispatcher.py --check-flash --mock                 # Evaluate + dispatch flash alerts (mock mode)
uv run python tools/notifier.py output/routing_decisions.json [--mock]    # Deliver briefs per routing decisions → delivery_log.jsonl
uv run python tools/scheduler.py --once                                    # Run all due scheduler jobs once
uv run python tools/scheduler.py --list                                    # List jobs and last-run times
```

- [ ] **Commit:**

```bash
git add .claude/commands/run-crq.md CLAUDE.md
git commit -m "feat: wire RSM brief generation into run-crq Phase 7 + update CLAUDE.md (Phase L-11)"
```

---

## Verification Checklist

Before declaring Phase L complete:

- [ ] `uv run pytest -v` — all tests pass (existing + new)
- [ ] `output/mock_delivery/` contains 5 brief files after mock run
- [ ] `output/delivery_log.jsonl` has 5 `status: delivered` entries
- [ ] `output/routing_decisions.json` has all decisions marked `delivered: true`
- [ ] Flash trigger fires correctly for APAC mock (hotspot score 0.87 ≥ 0.85, Kaohsiung site within 100km)
- [ ] Flash does NOT fire for LATAM/NCE (no hotspots, no high-severity events in mock data)
- [ ] Scheduler `--list` shows all 4 jobs with correct cron expressions
- [ ] `uv run pytest tests/test_scheduler.py -v` — all 9 scheduler tests pass
- [ ] CLAUDE.md Commands table updated with all 8 new Phase L tool commands
