# Tavily Research VaCR Integration — Implementation Plan

**Goal:** Replace the Tavily search + Haiku extraction steps in `vacr_researcher.py` with a single `TavilyClient.research()` call that returns structured figures via `output_schema`, then feed those figures into the unchanged Sonnet reasoning step.

**Architecture:** `_search_web()` and `_extract_figures()` are deleted. A new `_research_tavily()` function submits a Tavily Research task, polls `get_research()` until `status == "completed"`, and returns `result["structured_output"]["figures"]`. `_reason_against_vacr()` is updated for the new field names (`source_name` replaces `_source_name`). `research_scenario()` shrinks to two calls: `_research_tavily()` then `_reason_against_vacr()`. `server.py` is untouched — it already parallelises scenarios via `run_in_executor`.

**Tech Stack:** Python 3.11 · `tavily-python==0.7.23` (new dep, already added to pyproject.toml) · `unittest.mock` for tests

---

## File Map

| File | Change |
|---|---|
| `tools/vacr_researcher.py` | Replace `_search_web` + `_extract_figures` with `_research_tavily`; update `_reason_against_vacr` field names; simplify `research_scenario`; delete dead code |
| `tests/test_vacr_researcher.py` | New — tests for `_research_tavily` and `research_scenario` |

`server.py`, `register_validator.py`, `pyproject.toml`, and output schema are unchanged.

---

### Task 1: Write failing tests for `_research_tavily`

**Files:**
- Create: `tests/test_vacr_researcher.py`

- [ ] **Step 1: Write the three failing tests**

```python
# tests/test_vacr_researcher.py
import pytest
from unittest.mock import MagicMock, patch


def _make_client(status="completed", figures=None, structured_output="present"):
    """Helper: build a mock TavilyClient."""
    mock = MagicMock()
    mock.research.return_value = {"request_id": "req-test-123"}
    payload = {"status": status}
    if status == "completed":
        payload["structured_output"] = (
            {"figures": figures or []} if structured_output == "present" else None
        )
    mock.get_research.return_value = payload
    return mock


def test_research_tavily_returns_figures():
    """Happy path: completed immediately with one figure."""
    figures = [{
        "dimension": "financial",
        "cost_low_usd": 2_000_000,
        "cost_median_usd": 4_500_000,
        "cost_high_usd": 8_000_000,
        "probability_low_pct": None,
        "probability_median_pct": None,
        "probability_high_pct": None,
        "note": "Average ransomware cost in energy sector",
        "raw_quote": "Energy sector ransomware incidents averaged $4.5M in 2024",
        "source_name": "IBM Cost of a Data Breach 2024",
        "source_url": "https://ibm.com/security/data-breach",
    }]
    mock_client = _make_client(figures=figures)

    with patch("tools.vacr_researcher.TavilyClient", return_value=mock_client), \
         patch("tools.vacr_researcher.time") as mock_time:
        mock_time.monotonic.return_value = 0
        mock_time.sleep = MagicMock()
        from tools.vacr_researcher import _research_tavily
        result = _research_tavily("Ransomware", "energy")

    assert len(result) == 1
    assert result[0]["cost_median_usd"] == 4_500_000
    assert result[0]["source_name"] == "IBM Cost of a Data Breach 2024"
    mock_client.research.assert_called_once()
    call_kwargs = mock_client.research.call_args
    assert "Ransomware" in call_kwargs.kwargs.get("input", "") or \
           "Ransomware" in (call_kwargs.args[0] if call_kwargs.args else "")


def test_research_tavily_raises_on_timeout():
    """Polling loop hits 180s deadline → TimeoutError."""
    mock_client = _make_client(status="running")

    with patch("tools.vacr_researcher.TavilyClient", return_value=mock_client), \
         patch("tools.vacr_researcher.time") as mock_time:
        # First call returns 0 (start), subsequent calls return 200 (past deadline)
        mock_time.monotonic.side_effect = [0, 200, 200]
        mock_time.sleep = MagicMock()
        from tools.vacr_researcher import _research_tavily
        with pytest.raises(TimeoutError, match="timed out"):
            _research_tavily("Ransomware", "energy")


def test_research_tavily_raises_on_missing_structured_output():
    """completed status but structured_output is None → ValueError."""
    mock_client = _make_client(status="completed", structured_output=None)

    with patch("tools.vacr_researcher.TavilyClient", return_value=mock_client), \
         patch("tools.vacr_researcher.time") as mock_time:
        mock_time.monotonic.return_value = 0
        mock_time.sleep = MagicMock()
        from tools.vacr_researcher import _research_tavily
        with pytest.raises(ValueError, match="structured_output"):
            _research_tavily("Ransomware", "energy")
```

- [ ] **Step 2: Run tests — verify all three FAIL**

```bash
cd c:/Users/frede/crq-agent-workspace
uv run pytest tests/test_vacr_researcher.py -v
```

Expected: `ImportError` or `AttributeError: module has no attribute '_research_tavily'`

---

### Task 2: Add `OUTPUT_SCHEMA`, `import time`, `from tavily import TavilyClient`, and implement `_research_tavily`

**Files:**
- Modify: `tools/vacr_researcher.py`

- [ ] **Step 1: Add imports and OUTPUT_SCHEMA at the top of the file**

Replace the existing imports block (lines 1–16) with:

```python
#!/usr/bin/env python3
"""VaCR Benchmark Researcher — researches industry sources per scenario and reasons against current VaCR.

Usage:
    uv run python tools/vacr_researcher.py <incident_type> <current_vacr_usd> [--sector energy|manufacturing]

Writes: output/pipeline/vacr_research.json (appends/updates this scenario's entry)
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_FILE = REPO_ROOT / "output" / "pipeline" / "vacr_research.json"

SONNET_MODEL = "claude-sonnet-4-6"

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "figures": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["dimension", "note", "raw_quote", "source_name", "source_url"],
                "properties": {
                    "dimension":              {"type": "string", "enum": ["financial", "probability"]},
                    "cost_low_usd":           {"type": ["number", "null"]},
                    "cost_median_usd":        {"type": ["number", "null"]},
                    "cost_high_usd":          {"type": ["number", "null"]},
                    "probability_low_pct":    {"type": ["number", "null"]},
                    "probability_median_pct": {"type": ["number", "null"]},
                    "probability_high_pct":   {"type": ["number", "null"]},
                    "note":        {"type": "string"},
                    "raw_quote":   {"type": "string"},
                    "source_name": {"type": "string"},
                    "source_url":  {"type": "string"},
                },
            },
        }
    },
    "required": ["figures"],
}

_RESEARCH_TIMEOUT_S = 180
_RESEARCH_POLL_INTERVAL_S = 5
```

- [ ] **Step 2: Add `_research_tavily()` function after the constants block**

```python
def _research_tavily(incident_type: str, sector: str) -> list[dict]:
    """Submit a Tavily Research task, poll until complete, return structured figures.

    Raises:
        TimeoutError: if the task does not complete within _RESEARCH_TIMEOUT_S seconds.
        ValueError: if the completed response has no structured_output.
        tavily.errors.ForbiddenError: if the Tavily plan does not include the Research API.
    """
    import os
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    query = (
        f"{incident_type} financial cost incident rate probability "
        f"{sector} sector renewable energy operator USD 2024 2025"
    )
    print(f"[vacr-researcher] Submitting Tavily Research: {query[:80]}...", file=sys.stderr)
    task = client.research(input=query, model="mini", output_schema=OUTPUT_SCHEMA)
    request_id = task["request_id"]

    deadline = time.monotonic() + _RESEARCH_TIMEOUT_S
    while time.monotonic() < deadline:
        result = client.get_research(request_id)
        status = result.get("status")
        if status == "completed":
            structured = result.get("structured_output")
            if not structured or "figures" not in structured:
                raise ValueError(
                    f"Tavily research completed but returned no structured_output "
                    f"for {incident_type!r} (request_id={request_id})"
                )
            figures = structured["figures"]
            print(f"[vacr-researcher] Research complete: {len(figures)} figures extracted", file=sys.stderr)
            return figures
        print(f"[vacr-researcher] Research status={status}, polling...", file=sys.stderr)
        time.sleep(_RESEARCH_POLL_INTERVAL_S)

    raise TimeoutError(
        f"Tavily research timed out after {_RESEARCH_TIMEOUT_S}s (request_id={request_id})"
    )
```

- [ ] **Step 3: Run tests — verify all three PASS**

```bash
uv run pytest tests/test_vacr_researcher.py -v
```

Expected:
```
PASSED tests/test_vacr_researcher.py::test_research_tavily_returns_figures
PASSED tests/test_vacr_researcher.py::test_research_tavily_raises_on_timeout
PASSED tests/test_vacr_researcher.py::test_research_tavily_raises_on_missing_structured_output
```

- [ ] **Step 4: Commit**

```bash
git add tools/vacr_researcher.py tests/test_vacr_researcher.py
git commit -m "feat(vacr): add _research_tavily() with Tavily Research API + OUTPUT_SCHEMA"
```

---

### Task 3: Update `_reason_against_vacr` field names and simplify `research_scenario`

**Files:**
- Modify: `tools/vacr_researcher.py`

- [ ] **Step 1: Write a failing test for `research_scenario` using mocked `_research_tavily`**

Add to `tests/test_vacr_researcher.py`:

```python
def test_research_scenario_uses_tavily_figures():
    """research_scenario() calls _research_tavily and _reason_against_vacr, returns correct shape."""
    mock_figures = [{
        "dimension": "financial",
        "cost_low_usd": None,
        "cost_median_usd": 5_000_000,
        "cost_high_usd": None,
        "probability_low_pct": None,
        "probability_median_pct": None,
        "probability_high_pct": None,
        "note": "Test note",
        "raw_quote": "Test quote",
        "source_name": "Test Source",
        "source_url": "https://example.com",
    }]
    mock_reasoning = {
        "findings": [{"source": "Test Source", "quote": "Test quote",
                      "figure_usd": 5_000_000, "direction": "↑", "assessment": "Supports"}],
        "overall_direction": "↑",
        "agent_summary": "Evidence supports higher VaCR.",
    }

    with patch("tools.vacr_researcher._research_tavily", return_value=mock_figures), \
         patch("tools.vacr_researcher._reason_against_vacr", return_value=mock_reasoning):
        from tools.vacr_researcher import research_scenario
        result = research_scenario("Ransomware", 4_000_000, "energy")

    assert result["incident_type"] == "Ransomware"
    assert result["current_vacr_usd"] == 4_000_000
    assert result["direction"] == "↑"
    assert result["agent_summary"] == "Evidence supports higher VaCR."
    assert "researched_at" in result
```

- [ ] **Step 2: Run test — verify it FAILS**

```bash
uv run pytest tests/test_vacr_researcher.py::test_research_scenario_uses_tavily_figures -v
```

Expected: FAIL — `research_scenario` still calls old `_search_web` path.

- [ ] **Step 3: Update `_reason_against_vacr` to use new field names**

Replace the `for f in all_figures[:20]:` block inside `_reason_against_vacr` (currently lines ~133–139):

```python
    for f in all_figures[:20]:
        src = f.get("source_name", "Unknown source")
        note = f.get("note", "")
        quote = f.get("raw_quote", "")
        median = f.get("cost_median_usd")
        dimension = f.get("dimension", "financial")
        if median:
            lines.append(f"- {src}: {dimension} | median=${median:,} | {note} | \"{quote}\"")
        else:
            lines.append(f"- {src}: {dimension} | {note} | \"{quote}\"")
```

- [ ] **Step 4: Replace `research_scenario` body**

Replace the entire `research_scenario` function (lines ~170–221):

```python
def research_scenario(incident_type: str, current_vacr_usd: int, sector: str = "energy") -> dict:
    """Full pipeline for one scenario. Returns result dict."""
    print(f"[vacr-researcher] Researching: {incident_type} (VaCR ${current_vacr_usd:,})", file=sys.stderr)

    figures = _research_tavily(incident_type, sector)
    reasoning = _reason_against_vacr(incident_type, current_vacr_usd, sector, figures)

    return {
        "incident_type": incident_type,
        "current_vacr_usd": current_vacr_usd,
        "sector": sector,
        "direction": reasoning.get("overall_direction", "?"),
        "findings": reasoning.get("findings", []),
        "agent_summary": reasoning.get("agent_summary", ""),
        "researched_at": datetime.now(timezone.utc).isoformat(),
    }
```

- [ ] **Step 5: Run all four tests — verify PASS**

```bash
uv run pytest tests/test_vacr_researcher.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/vacr_researcher.py tests/test_vacr_researcher.py
git commit -m "feat(vacr): wire research_scenario to _research_tavily; update field names"
```

---

### Task 4: Delete dead code

**Files:**
- Modify: `tools/vacr_researcher.py`

- [ ] **Step 1: Delete these items from `vacr_researcher.py`**

Remove the following entirely:
- `HAIKU_MODEL = "claude-haiku-4-5-20251001"` (line 22)
- `EXTRACTION_PROMPT = """..."""` (lines 25–40)
- `def _search_web(...)` (lines 74–97)
- `def _extract_figures(...)` (lines 100–124)

The file should now contain only:
- Module docstring + imports (`json`, `sys`, `time`, `datetime`, `Path`, `load_dotenv`, `TavilyClient`)
- `SONNET_MODEL`, `OUTPUT_SCHEMA`, `_RESEARCH_TIMEOUT_S`, `_RESEARCH_POLL_INTERVAL_S`
- `REASONING_PROMPT`
- `_research_tavily()`
- `_reason_against_vacr()`
- `research_scenario()`
- `_update_output()`
- `if __name__ == "__main__":` block

- [ ] **Step 2: Run the full test suite**

```bash
uv run pytest tests/test_vacr_researcher.py tests/test_register_validator_counters.py tests/test_register_validator_run_summary.py tests/test_register_validator_baseline.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Run the full suite to catch regressions**

```bash
uv run pytest --tb=short -q
```

Expected: same pass count as before this feature (no new failures).

- [ ] **Step 4: Final commit**

```bash
git add tools/vacr_researcher.py
git commit -m "refactor(vacr): delete _search_web, _extract_figures, EXTRACTION_PROMPT, HAIKU_MODEL"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `research()` is async-submit; poll `get_research()` | Task 2 Step 2 |
| `output_schema` constant defined | Task 2 Step 1 |
| `structured_output` field checked | Task 2 Step 2 |
| 180s hard timeout → `TimeoutError` | Task 2 Step 2 + test |
| Missing `structured_output` → `ValueError` | Task 2 Step 2 + test |
| `model="mini"` | Task 2 Step 2 |
| `_search_web`, `_extract_figures`, `HAIKU_MODEL`, `EXTRACTION_PROMPT` deleted | Task 4 |
| `research_scenario()` stays synchronous (server.py uses `run_in_executor`) | Task 3 Step 4 |
| `source_name` replaces `_source_name` in `_reason_against_vacr` | Task 3 Step 3 |
| `tavily-python` in `pyproject.toml` | Already done (brainstorming session) |
| `REASONING_PROMPT` + Sonnet call unchanged | Tasks 3–4 (untouched) |
| `_update_output()` unchanged | Tasks 3–4 (untouched) |

**Placeholder scan:** No TBDs. All code blocks are complete.

**Type consistency:** `_research_tavily()` returns `list[dict]` with `source_name` field. `_reason_against_vacr()` reads `f.get("source_name", ...)` — consistent across Task 2 and Task 3.
