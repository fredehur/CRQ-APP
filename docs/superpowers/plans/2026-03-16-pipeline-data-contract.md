# Pipeline Data Contract Implementation Plan


**Goal:** Extend the pipeline to output `signal_clusters.json` per region, `synthesis_brief` in `global_report.json`, and a `--window` date-range parameter on all OSINT collectors.

**Architecture:** Three independent additions to the existing pipeline. `--window` flows from the orchestrator through collectors into `signal_clusters.json`. The `regional-analyst-agent` writes `signal_clusters.json` alongside `report.md`. The `global-builder-agent` writes a new `synthesis_brief` field. The `json-auditor.py` is updated last to accept the new field.

**Tech Stack:** Python 3.11+, uv, pytest, existing subprocess-based collector chain, Claude sub-agent instruction files (`.claude/agents/`)

---

## Chunk 1: `--window` parameter on OSINT collectors

### Files
- Modify: `tools/osint_search.py`
- Modify: `tools/geo_collector.py`
- Modify: `tools/cyber_collector.py`
- Modify: `tools/write_manifest.py`
- Modify: `.claude/commands/run-crq.md`
- Create: `tests/test_window_param.py`

---

### Task 1: Add `--window` to `osint_search.py`

The `parse_args` function needs a `--window` arg (`1d`, `7d`, `30d`, `90d`). Both backends use it: Tavily via `days` int param; DDG via the `timelimit` kwarg (`'d'`=day, `'w'`=week, `'m'`=month, `'y'`=year for 90d — DDG has no 90-day option, year is the closest available).

- [ ] **Write the failing test**

Create `tests/test_window_param.py`:

```python
import json
import subprocess
import sys


def run_osint(args):
    result = subprocess.run(
        [sys.executable, "tools/osint_search.py"] + args,
        capture_output=True, text=True, encoding="utf-8"
    )
    return result


def test_window_accepted_in_mock_mode():
    """--window arg is accepted without error in mock mode."""
    r = run_osint(["AME", "test query", "--type", "geo", "--mock", "--window", "7d"])
    assert r.returncode == 0, f"stderr: {r.stderr}"


def test_window_invalid_rejected():
    """Invalid --window value exits non-zero."""
    r = run_osint(["AME", "test query", "--type", "geo", "--mock", "--window", "99x"])
    assert r.returncode != 0


def test_window_default_is_none():
    """Omitting --window still works (backward compat)."""
    r = run_osint(["AME", "test query", "--type", "geo", "--mock"])
    assert r.returncode == 0
```

- [ ] **Run test to confirm it fails**

```bash
cd c:/Users/frede/crq-agent-workspace && uv run pytest tests/test_window_param.py -v
```

Expected: `FAILED` — `test_window_invalid_rejected` may pass by accident (unknown args are silently ignored currently), but at least `test_window_invalid_rejected` logic needs verifying. Confirm all three run and at least the validation test needs the new code.

- [ ] **Implement `--window` in `osint_search.py`**

In `parse_args`, add window parsing after the existing arg loop:

```python
VALID_WINDOWS = {"1d", "7d", "30d", "90d"}

def parse_args(argv):
    if len(argv) < 2:
        print("Usage: osint_search.py REGION QUERY --type geo|cyber [--mock] [--window 1d|7d|30d|90d]", file=sys.stderr)
        sys.exit(1)

    region = argv[0].upper()
    query = argv[1]
    type_ = None
    mock = False
    window = None  # None = no date filter

    i = 2
    while i < len(argv):
        if argv[i] == "--type" and i + 1 < len(argv):
            type_ = argv[i + 1]
            i += 2
        elif argv[i] == "--mock":
            mock = True
            i += 1
        elif argv[i] == "--window" and i + 1 < len(argv):
            window = argv[i + 1]
            i += 2
        else:
            i += 1

    if region not in VALID_REGIONS:
        print(f"[osint_search] invalid region '{region}'. Valid: {sorted(VALID_REGIONS)}", file=sys.stderr)
        sys.exit(1)
    if type_ is None:
        print("[osint_search] --type geo|cyber is required", file=sys.stderr)
        sys.exit(1)
    if type_ not in VALID_TYPES:
        print(f"[osint_search] invalid type '{type_}'. Valid: geo, cyber", file=sys.stderr)
        sys.exit(1)
    if window is not None and window not in VALID_WINDOWS:
        print(f"[osint_search] invalid --window '{window}'. Valid: {sorted(VALID_WINDOWS)}", file=sys.stderr)
        sys.exit(1)

    return region, query, type_, mock, window
```

Update `search_ddg` to accept and use `window`:

```python
def _ddg_timelimit(window):
    """Map our window presets to DDG timelimit codes.
    DDG supports: d=day, w=week, m=month, y=year. No 90-day option — 90d maps to 'y' (closest).
    """
    return {"1d": "d", "7d": "w", "30d": "m", "90d": "y"}.get(window)


def search_ddg(query: str, max_results: int = 8, window: str = None) -> list[dict]:
    """DuckDuckGo backend — free, no API key required."""
    try:
        from duckduckgo_search import DDGS
        timelimit = _ddg_timelimit(window) if window else None
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, timelimit=timelimit))
        return [
            {
                "title": r.get("title", ""),
                "summary": r.get("body", ""),
                "url": r.get("href", ""),
                "published_date": "",
            }
            for r in results
        ]
    except Exception as e:
        print(f"[osint_search] DDG search failed: {e}", file=sys.stderr)
        return []
```

Update `search_tavily` to accept and use `window`:

```python
def search_tavily(query: str, max_results: int = 8, window: str = None) -> list[dict]:
    """Tavily backend — requires TAVILY_API_KEY env var."""
    try:
        import httpx
        api_key = os.environ["TAVILY_API_KEY"]
        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        }
        if window:
            days_map = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}
            payload["days"] = days_map[window]
        resp = httpx.post("https://api.tavily.com/search", json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "title": r.get("title", ""),
                "summary": r.get("content", ""),
                "url": r.get("url", ""),
                "published_date": r.get("published_date", ""),
            }
            for r in data.get("results", [])
        ]
    except Exception as e:
        print(f"[osint_search] Tavily search failed: {e}", file=sys.stderr)
        return []
```

Update `main` to pass `window` through:

```python
def main():
    region, query, type_, mock, window = parse_args(sys.argv[1:])

    if mock:
        articles = load_fixture(region, type_)
    elif os.environ.get("TAVILY_API_KEY"):
        articles = search_tavily(query, window=window)
    else:
        articles = search_ddg(query, window=window)

    sys.stdout.buffer.write(json.dumps(articles, ensure_ascii=False).encode("utf-8") + b"\n")
```

- [ ] **Run tests to confirm they pass**

```bash
uv run pytest tests/test_window_param.py -v
```

Expected: all 3 PASS.

- [ ] **Commit**

```bash
git add tools/osint_search.py tests/test_window_param.py
git commit -m "feat: add --window date-range param to osint_search"
```

---

### Task 2: Pass `--window` through `geo_collector.py` and `cyber_collector.py`

- [ ] **Add failing test for collector window passthrough**

Append to `tests/test_window_param.py`:

```python
def test_geo_collector_accepts_window():
    """geo_collector.py passes --window to osint_search without error."""
    r = subprocess.run(
        [sys.executable, "tools/geo_collector.py", "AME", "--mock", "--window", "7d"],
        capture_output=True, text=True, encoding="utf-8",
        cwd="c:/Users/frede/crq-agent-workspace"
    )
    assert r.returncode == 0, f"stderr: {r.stderr}"


def test_cyber_collector_accepts_window():
    """cyber_collector.py passes --window to osint_search without error."""
    r = subprocess.run(
        [sys.executable, "tools/cyber_collector.py", "AME", "--mock", "--window", "30d"],
        capture_output=True, text=True, encoding="utf-8",
        cwd="c:/Users/frede/crq-agent-workspace"
    )
    assert r.returncode == 0, f"stderr: {r.stderr}"
```

- [ ] **Run new tests to confirm they fail**

```bash
uv run pytest tests/test_window_param.py::test_geo_collector_accepts_window tests/test_window_param.py::test_cyber_collector_accepts_window -v
```

Expected: FAIL (unknown arg is silently ignored but window is not stored/forwarded — verify behavior).

- [ ] **Update `geo_collector.py` — three touch points**

**1. `run_search` signature and cmd construction:**
```python
def run_search(region, query, mock, window=None):
    cmd = [sys.executable, "tools/osint_search.py", region, query, "--type", "geo"]
    if mock:
        cmd.append("--mock")
    if window:
        cmd.extend(["--window", window])
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
```

**2. `collect` signature and run_search calls** (window must pass through collect → run_search):
```python
def collect(region, mock, window=None):
    articles1 = run_search(region, f"{region} geopolitical risk wind energy", mock, window)
    articles2 = run_search(region, f"{region} trade tensions manufacturing", mock, window)
    # ... rest of collect unchanged
```

**3. `main` — parse --window and pass to collect:**
```python
def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: geo_collector.py REGION [--mock] [--window 1d|7d|30d|90d]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    mock = "--mock" in args
    window = None
    if "--window" in args:
        idx = args.index("--window")
        if idx + 1 < len(args):
            window = args[idx + 1]

    if region not in VALID_REGIONS:
        print(f"[geo_collector] invalid region '{region}'", file=sys.stderr)
        sys.exit(1)

    result = collect(region, mock, window)
    # ... rest unchanged
```

Apply the exact same three-point pattern to `cyber_collector.py` (only difference: `--type cyber` in run_search cmd).

**Note on collector tests:** The tests call the real collector with `--mock`, which means `osint_search.py` loads a static fixture and ignores `--window` entirely. This is correct — we're testing that the `--window` arg is accepted and forwarded without error, not that it filters live results. The tests are integration tests (real subprocess), not unit tests with mocks.

- [ ] **Run all window tests**

```bash
uv run pytest tests/test_window_param.py -v
```

Expected: all 5 PASS.

- [ ] **Commit**

```bash
git add tools/geo_collector.py tools/cyber_collector.py tests/test_window_param.py
git commit -m "feat: pass --window through geo and cyber collectors"
```

---

### Task 3: Record `window_used` in `run_manifest.json`

- [ ] **Update `write_manifest.py`**

Add `window_used` parameter to `build_manifest` and add argparse to `__main__`. The argparse lives only inside the `if __name__ == "__main__"` block — it does not execute on import.

```python
def build_manifest(window_used=None):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_slug = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")

    regions_summary = {}
    total_vacr = 0
    # ... existing regions loop unchanged ...

    manifest = {
        "pipeline_id": f"crq-{date_slug}",
        "client": "AeroGrid Wind Solutions",
        "run_timestamp": timestamp,
        "window_used": window_used or "unspecified",
        "status": "complete",
        "total_vacr_exposure_usd": total_vacr,
        "regions": regions_summary,
        "outputs": {
            # ... existing outputs unchanged ...
        },
    }

    out_path = "output/run_manifest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Wrote {out_path} — {len(REGIONS)} regions, total VaCR: ${total_vacr:,.0f}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", default=None, choices=["1d", "7d", "30d", "90d"])
    parsed = parser.parse_args()
    build_manifest(window_used=parsed.window)
```

- [ ] **Update `run-crq.md` orchestrator** — three edits:

**Edit 1 — Phase 0, after OSINT mode determination, add:**
```markdown
**Determine window:**
The user may invoke as `/run-crq --window 7d` (or `1d`, `30d`, `90d`). Parse the `--window` argument if present; default to `7d` if absent. Store as `WINDOW`.
```

**Edit 2 — Phase 1, update collector calls to:**
```
uv run python tools/geo_collector.py {REGION} {OSINT_MODE} --window {WINDOW}
uv run python tools/cyber_collector.py {REGION} {OSINT_MODE} --window {WINDOW}
```

**Edit 3 — Phase 3 manifest assembly call, update to:**
```
uv run python tools/write_manifest.py --window {WINDOW}
```

- [ ] **Manual smoke test**

```bash
uv run python tools/write_manifest.py --window 7d
```

Open `output/run_manifest.json`. Confirm `"window_used": "7d"` is present.

- [ ] **Commit**

```bash
git add tools/write_manifest.py .claude/commands/run-crq.md
git commit -m "feat: record window_used in run_manifest and orchestrator"
```

---

## Chunk 2: `signal_clusters.json` per region

### Files
- Modify: `.claude/agents/regional-analyst-agent.md`
- Create: `tools/validate_signal_clusters.py` (schema validator utility)
- Create: `tests/test_signal_clusters.py`

---

### Task 4: Write `signal_clusters.json` schema validator

This utility validates the signal_clusters.json schema — used in tests and can be run manually.

- [ ] **Create `tools/validate_signal_clusters.py`**

```python
#!/usr/bin/env python3
"""Validates signal_clusters.json schema. Exits 0 on pass, 1 on fail."""
import json
import sys

VALID_PILLARS = {"Geo", "Cyber"}


def validate(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)

    errors = []

    for key in ("region", "timestamp", "window_used", "total_signals", "sources_queried", "clusters"):
        if key not in data:
            errors.append(f"Missing top-level key: {key}")

    if not isinstance(data.get("clusters"), list):
        errors.append("'clusters' must be a list")
    else:
        for i, c in enumerate(data["clusters"]):
            for ckey in ("name", "pillar", "convergence", "sources"):
                if ckey not in c:
                    errors.append(f"clusters[{i}] missing key: {ckey}")
            if c.get("pillar") not in VALID_PILLARS:
                errors.append(f"clusters[{i}].pillar must be 'Geo' or 'Cyber', got: {c.get('pillar')}")
            if not isinstance(c.get("convergence"), int):
                errors.append(f"clusters[{i}].convergence must be int")
            if not isinstance(c.get("sources"), list):
                errors.append(f"clusters[{i}].sources must be list")
            else:
                for j, s in enumerate(c["sources"]):
                    if "name" not in s or "headline" not in s:
                        errors.append(f"clusters[{i}].sources[{j}] missing name or headline")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"PASS: {path} — {len(data['clusters'])} clusters, {data['total_signals']} signals")
    sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: validate_signal_clusters.py <path>")
        sys.exit(1)
    validate(sys.argv[1])
```

- [ ] **Create `tests/test_signal_clusters.py`**

```python
import json
import subprocess
import sys
import tempfile
import os


VALID_CLUSTER = {
    "region": "AME",
    "timestamp": "2026-03-16T09:00:00Z",
    "window_used": "7d",
    "total_signals": 2,
    "sources_queried": 10,
    "clusters": [
        {
            "name": "Grid disruption cluster",
            "pillar": "Cyber",
            "convergence": 2,
            "sources": [
                {"name": "Reuters", "headline": "Grid warning issued"},
                {"name": "CISA", "headline": "Energy sector alert"},
            ]
        }
    ]
}

CLEAR_CLUSTER = {
    "region": "LATAM",
    "timestamp": "2026-03-16T09:00:00Z",
    "window_used": "7d",
    "total_signals": 0,
    "sources_queried": 8,
    "clusters": []
}


def run_validator(data):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
        path = f.name
    try:
        r = subprocess.run(
            [sys.executable, "tools/validate_signal_clusters.py", path],
            capture_output=True, text=True
        )
        return r
    finally:
        os.unlink(path)


def test_valid_escalated_schema():
    r = run_validator(VALID_CLUSTER)
    assert r.returncode == 0, r.stderr


def test_valid_clear_schema():
    r = run_validator(CLEAR_CLUSTER)
    assert r.returncode == 0, r.stderr


def test_missing_required_key():
    bad = {**VALID_CLUSTER}
    del bad["sources_queried"]
    r = run_validator(bad)
    assert r.returncode != 0


def test_invalid_pillar():
    bad = {**VALID_CLUSTER, "clusters": [{**VALID_CLUSTER["clusters"][0], "pillar": "Unknown"}]}
    r = run_validator(bad)
    assert r.returncode != 0


def test_missing_source_headline():
    bad_source = {"name": "Reuters"}  # missing headline
    bad = {**VALID_CLUSTER, "clusters": [{**VALID_CLUSTER["clusters"][0], "sources": [bad_source]}]}
    r = run_validator(bad)
    assert r.returncode != 0


def test_invalid_convergence_type():
    """convergence must be int, not float or string."""
    bad_cluster = {**VALID_CLUSTER["clusters"][0], "convergence": "3"}  # string, not int
    bad = {**VALID_CLUSTER, "clusters": [bad_cluster]}
    r = run_validator(bad)
    assert r.returncode != 0
```

- [ ] **Run tests — expect FAIL (validator doesn't exist yet)**

```bash
uv run pytest tests/test_signal_clusters.py -v
```

- [ ] **Run tests after creating the validator — expect PASS**

```bash
uv run pytest tests/test_signal_clusters.py -v
```

Expected: all 6 PASS (valid escalated, valid clear, missing key, invalid pillar, missing headline, invalid convergence type).

- [ ] **Commit**

```bash
git add tools/validate_signal_clusters.py tests/test_signal_clusters.py
git commit -m "feat: add signal_clusters.json schema validator + tests"
```

---

### Task 5: Update `regional-analyst-agent.md` to write `signal_clusters.json`

This is an agent instruction update — no Python code. The agent is prompted to write a structured JSON alongside `report.md`.

- [ ] **Read the full current agent file**

```bash
cat .claude/agents/regional-analyst-agent.md
```

- [ ] **Add STEP 5 after the existing STEP 4 (write report.md) and before the data.json update step**

Locate the section after `## STEP 4 — WRITE THE BRIEF` and add:

```markdown
## STEP 5 — WRITE SIGNAL CLUSTERS JSON

After writing `report.md`, write `output/regional/{region_lower}/signal_clusters.json` using the Write tool.

This file is the structured signal inventory for the analyst dashboard. It must be valid JSON. Do not include any markdown, code fences, or commentary — pure JSON only.

**Schema:**
```json
{
  "region": "<REGION>",
  "timestamp": "<ISO 8601 UTC — same timestamp you will use in data.json>",
  "window_used": "<value passed to you by the orchestrator — default '7d' if not provided>",
  "total_signals": <integer — count of distinct signals you identified across geo and cyber feeds>,
  "sources_queried": <integer — count of distinct source names found across all signal files>,
  "clusters": [
    {
      "name": "<short descriptive label for the theme — 4-8 words>",
      "pillar": "<'Geo' or 'Cyber'>",
      "convergence": <integer — number of sources pointing at this theme>,
      "sources": [
        { "name": "<source publication name>", "headline": "<title or lead sentence, max 120 chars>" }
      ]
    }
  ]
}
```

**Rules:**
- Group signals by dominant theme — a cluster is 2+ sources converging on the same named entity, scenario, or geographic development
- Single-source signals still get their own cluster with `convergence: 1`
- `pillar` is `"Geo"` if the signal came from geo_signals.json; `"Cyber"` if from cyber_signals.json
- For CLEAR regions: `clusters: []`, `total_signals: 0`, `sources_queried` = count of sources you found in the signal files (even if empty)
- Do not duplicate the brief narrative — this is structured metadata only
```

- [ ] **Ensure STEP 5 in the agent instruction includes the exact write path and tool call**

The instruction must be as explicit as the existing steps. The path template and example Bash call must be present, or the sub-agent will invent a path. Confirm the added instruction reads:

```
Write the file to: `output/regional/{region_lower}/signal_clusters.json`

Use the Write tool. Example:
  Write tool → path: output/regional/ame/signal_clusters.json
               content: { "region": "AME", ... }
```

This mirrors how the existing STEP 4 specifies `output/regional/{region_lower}/report.md` explicitly.

**Important: `signal_clusters.json` is a terminal artifact.** It is written by the regional-analyst-agent and consumed directly by the analyst dashboard UI (`static/app.js`). No other pipeline agent reads it. The global-builder-agent does NOT read signal_clusters.json — it reads report.md and data.json as before.

- [ ] **Integration smoke test (promotes to pytest)**

Add to `tests/test_signal_clusters.py`:

```python
import os

def test_signal_clusters_written_after_mock_run():
    """After running collectors + scenario_mapper in mock mode, signal_clusters.json
    should exist at the expected path once the agent instruction is live.
    This test is intentionally skipped in CI unless a full mock run has been executed.
    """
    path = "output/regional/ame/signal_clusters.json"
    if not os.path.exists(path):
        import pytest
        pytest.skip("signal_clusters.json not present — run /crq-region AME first")
    r = subprocess.run(
        [sys.executable, "tools/validate_signal_clusters.py", path],
        capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
```

- [ ] **Run integration test after `/crq-region AME`**

```bash
uv run pytest tests/test_signal_clusters.py::test_signal_clusters_written_after_mock_run -v
```

Expected: PASS (not skipped).

- [ ] **Commit**

```bash
git add .claude/agents/regional-analyst-agent.md
git commit -m "feat: regional-analyst-agent writes signal_clusters.json"
```

---

## Chunk 3: `synthesis_brief` + `json-auditor.py` update

### Files
- Modify: `.claude/agents/global-builder-agent.md`
- Modify: `.claude/hooks/validators/json-auditor.py`
- Modify: `tests/test_signal_clusters.py` (add synthesis_brief test)

---

### Task 6: Update `global-builder-agent.md` to write `synthesis_brief`

- [ ] **Read the full current global-builder-agent.md**

```bash
cat .claude/agents/global-builder-agent.md
```

- [ ] **Add `synthesis_brief` to the OUTPUT FORMAT schema**

In the JSON schema block, add the field after `"executive_summary"`:

```json
"synthesis_brief": "<string — exactly 1-2 sentences. Cross-regional pattern only. What do multiple regions share in common? If no cross-regional pattern, state that each region's threat is independent. This appears in the analyst dashboard left panel — it must be immediately scannable.>",
```

Add a rule in the output instructions:
```markdown
**`synthesis_brief` rules:**
- Max 2 sentences. If 2, they must each carry distinct information.
- Focus on cross-regional patterns, not individual region summaries.
- Must not repeat `executive_summary` content.
- Must not contain VaCR dollar values (dashboard-only field).
- Example: "AME and APAC signals converge on state-adjacent pressure targeting renewable grid infrastructure. Two regions clear; no cross-regional indicator of coordinated campaign yet."
```

- [ ] **Commit**

```bash
git add .claude/agents/global-builder-agent.md
git commit -m "feat: global-builder-agent writes synthesis_brief field"
```

---

### Task 7: Update `json-auditor.py` to require `synthesis_brief`

- [ ] **Write the failing test**

Append to `tests/test_signal_clusters.py`:

```python
def test_json_auditor_requires_synthesis_brief():
    """json-auditor.py fails if synthesis_brief is missing.
    Uses unique label 'test_synthesis_missing' to avoid retry-file state pollution.
    Cleans up retry file after test regardless of outcome.
    """
    import tempfile, os
    label = "test_synthesis_missing"
    retry_file = f"output/.retries/{label}_json.retries"
    os.makedirs("output/.retries", exist_ok=True)
    missing_brief = {
        "total_vacr_exposure": 1000000,
        "executive_summary": "A" * 50,
        "regional_threats": []
        # synthesis_brief intentionally absent
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(missing_brief, f)
        path = f.name
    try:
        r = subprocess.run(
            [sys.executable, ".claude/hooks/validators/json-auditor.py", path, label],
            capture_output=True, text=True
        )
        assert r.returncode == 2, f"Expected exit 2 (audit fail), got {r.returncode}. stderr: {r.stderr}"
    finally:
        os.unlink(path)
        if os.path.exists(retry_file):
            os.remove(retry_file)


def test_json_auditor_passes_with_synthesis_brief():
    """json-auditor.py passes when synthesis_brief is present.
    Uses unique label 'test_synthesis_present' to avoid retry-file state pollution.
    """
    import tempfile, os
    label = "test_synthesis_present"
    retry_file = f"output/.retries/{label}_json.retries"
    os.makedirs("output/.retries", exist_ok=True)
    with_brief = {
        "total_vacr_exposure": 1000000,
        "executive_summary": "A" * 50,
        "synthesis_brief": "Cross-regional pattern identified. Two regions show convergence.",
        "regional_threats": []
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(with_brief, f)
        path = f.name
    try:
        r = subprocess.run(
            [sys.executable, ".claude/hooks/validators/json-auditor.py", path, label],
            capture_output=True, text=True
        )
        assert r.returncode == 0, f"Expected exit 0, got {r.returncode}. stderr: {r.stderr}"
    finally:
        os.unlink(path)
        if os.path.exists(retry_file):
            os.remove(retry_file)
```

- [ ] **Run tests — expect FAIL**

```bash
uv run pytest tests/test_signal_clusters.py::test_json_auditor_requires_synthesis_brief tests/test_signal_clusters.py::test_json_auditor_passes_with_synthesis_brief -v
```

Expected: `test_json_auditor_requires_synthesis_brief` FAIL (auditor currently passes without the field).

- [ ] **Update `json-auditor.py`**

Add `synthesis_brief` to `REQUIRED_TOP_KEYS` and add a type/length check:

```python
REQUIRED_TOP_KEYS = ["total_vacr_exposure", "executive_summary", "synthesis_brief", "regional_threats"]
```

After the `executive_summary` check, add:

```python
if not isinstance(data.get("synthesis_brief"), str) or len(data["synthesis_brief"]) < 30:
    fail("JSON AUDIT FAILED: 'synthesis_brief' must be a string with at least 30 characters (roughly one meaningful sentence).", retry_file, retries)
```

Add a third auditor test to cover the minimum length floor:

```python
def test_json_auditor_rejects_short_synthesis_brief():
    """synthesis_brief shorter than 30 chars should fail."""
    import tempfile, os
    label = "test_synthesis_short"
    retry_file = f"output/.retries/{label}_json.retries"
    os.makedirs("output/.retries", exist_ok=True)
    short_brief = {
        "total_vacr_exposure": 1000000,
        "executive_summary": "A" * 50,
        "synthesis_brief": "Too short.",   # 10 chars — below 30-char floor
        "regional_threats": []
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(short_brief, f)
        path = f.name
    try:
        r = subprocess.run(
            [sys.executable, ".claude/hooks/validators/json-auditor.py", path, label],
            capture_output=True, text=True
        )
        assert r.returncode == 2, f"Expected exit 2, got {r.returncode}. stderr: {r.stderr}"
    finally:
        os.unlink(path)
        if os.path.exists(retry_file):
            os.remove(retry_file)
```

- [ ] **Run all auditor tests**

```bash
uv run pytest tests/test_signal_clusters.py -v
```

Expected: all PASS (including the 3 auditor tests and 6 validator tests).

- [ ] **Run the full test suite**

```bash
uv run pytest tests/ -v
```

Fix any regressions before committing.

- [ ] **Commit**

```bash
git add .claude/hooks/validators/json-auditor.py tests/test_signal_clusters.py
git commit -m "feat: json-auditor requires synthesis_brief field"
```

---

## End-to-End Validation

- [ ] **Run the full mock pipeline**

```bash
# In Claude Code, run:
/run-crq --window 7d
```

Confirm after completion:
1. `output/run_manifest.json` contains `"window_used": "7d"`
2. Each escalated region has `output/regional/{region}/signal_clusters.json`
3. Run validator on each: `uv run python tools/validate_signal_clusters.py output/regional/ame/signal_clusters.json`
4. `output/global_report.json` contains `"synthesis_brief"` field
5. json-auditor passes: `uv run python .claude/hooks/validators/json-auditor.py output/global_report.json final`

- [ ] **Final commit if all checks pass**

```bash
git add -A
git commit -m "feat: complete pipeline data contract — window, signal_clusters, synthesis_brief"
```
