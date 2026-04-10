# Target-Centric Research Collector Implementation Plan


**Goal:** Replace the dumb Python OSINT collectors (in live mode) with a target-centric research loop that forms a CRQ-grounded working theory, collects evidence in 2 passes, and writes a `research_scratchpad.json` audit trail consumed by the gatekeeper and analyst.

**Architecture:** A new `tools/research_collector.py` script with 3 bounded Anthropic API calls — form working theory, assess gaps, synthesize signals. Mock mode is completely unchanged (delegates to existing collectors). The scratchpad is a first-class pipeline artifact read by the gatekeeper and analyst, not a debug file.

**Tech Stack:** Python 3.14, Anthropic Python SDK, `uv`, `pytest`, existing `osint_search.py` subprocess pattern (`sys.executable`).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `tools/research_collector.py` | **Create** | Target-centric collection loop — 3 LLM calls, writes scratchpad + signals |
| `tests/test_research_collector.py` | **Create** | Unit tests for each LLM call + mock delegation + scratchpad schema |
| `pyproject.toml` | **Modify** | Add `anthropic` dependency |
| `.claude/agents/gatekeeper-agent.md` | **Modify** | Add scratchpad read — confirm/challenge Admiralty from pre-assessed confidence |
| `.claude/agents/regional-analyst-agent.md` | **Modify** | Add scratchpad read — analyst starts from pre-formed working theory |
| `.claude/commands/run-crq.md` | **Modify** | Live mode calls `research_collector.py` instead of individual collectors |

**New output artifact:** `output/regional/{region_lower}/research_scratchpad.json`

**Key constraints from codebase:**
- `osint_search.py` requires `--type geo|cyber` as a mandatory argument
- `osint_search.py` output schema: `{title, summary, url, published_date}` (not `snippet`)
- Subprocess pattern throughout codebase: `[sys.executable, "tools/script.py", ...]` — not `["uv", "run", ...]`
- Model IDs: Sonnet `claude-sonnet-4-6`, Haiku `claude-haiku-4-5-20251001`

---

## Chunk 1: research_collector.py — Core Logic

### Task 1: Add `anthropic` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add anthropic to project dependencies**

```bash
uv add anthropic
```

- [ ] **Step 2: Verify import works**

```bash
uv run python -c "import anthropic; print(anthropic.__version__)"
```

Expected: version string printed, no error.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add anthropic sdk dependency"
```

---

### Task 2: Scratchpad schema + validator

**Files:**
- Create: `tests/test_research_collector.py` (initial stub)

The `research_scratchpad.json` schema — all downstream code must match this exactly:

```json
{
  "region": "AME",
  "collected_at": "2026-03-16T10:00:00Z",
  "working_theory": {
    "scenario_name": "Wind Farm Telemetry & Maintenance Disruption",
    "vacr_usd": 22000000,
    "hypothesis": "AME carries a $22M exposure...",
    "active_topics": [{"id": "ot-ics-cyber-attacks", "label": "OT/ICS Cyber Attacks on Energy Sector"}],
    "geo_queries": ["AME wind energy regulation 2026", "Americas energy policy instability"],
    "cyber_queries": ["AME ransomware wind energy 2026", "Americas OT ICS cyber attack 2026"]
  },
  "collection": {
    "pass_1_result_count": 4,
    "gap_assessment": "3 corroborating sources found. No wind-sector-specific signal.",
    "gaps_identified": ["No wind-sector specific signals"],
    "pass_2_queries": ["wind turbine OT AME 2026"],
    "pass_2_query_type": "cyber",
    "pass_2_result_count": 3,
    "total_result_count": 7
  },
  "conclusion": {
    "theory_confirmed": true,
    "confidence_rationale": "3 corroborating sources, 1 sector-specific, no contradictions.",
    "suggested_admiralty": "B2",
    "signal_type": "trend",
    "dominant_pillar": "Cyber"
  }
}
```

- [ ] **Step 1: Write schema validation test**

Create `tests/test_research_collector.py`:

```python
"""Tests for research_collector.py — target-centric OSINT collection loop."""
import json
import pytest


REQUIRED_TOP_LEVEL = {"region", "collected_at", "working_theory", "collection", "conclusion"}
REQUIRED_WORKING_THEORY = {"scenario_name", "vacr_usd", "hypothesis", "active_topics", "geo_queries", "cyber_queries"}
REQUIRED_COLLECTION = {"pass_1_result_count", "gap_assessment", "gaps_identified", "pass_2_queries", "pass_2_result_count", "total_result_count"}
REQUIRED_CONCLUSION = {"theory_confirmed", "confidence_rationale", "suggested_admiralty", "signal_type", "dominant_pillar"}


def validate_scratchpad(data: dict) -> list[str]:
    """Returns list of schema violations. Empty list = valid."""
    errors = []
    for key in REQUIRED_TOP_LEVEL:
        if key not in data:
            errors.append(f"Missing top-level key: {key}")
    if "working_theory" in data:
        for key in REQUIRED_WORKING_THEORY:
            if key not in data["working_theory"]:
                errors.append(f"Missing working_theory.{key}")
    if "collection" in data:
        for key in REQUIRED_COLLECTION:
            if key not in data["collection"]:
                errors.append(f"Missing collection.{key}")
    if "conclusion" in data:
        for key in REQUIRED_CONCLUSION:
            if key not in data["conclusion"]:
                errors.append(f"Missing conclusion.{key}")
    return errors


def test_validate_scratchpad_passes_valid_data():
    valid = {
        "region": "AME",
        "collected_at": "2026-03-16T10:00:00Z",
        "working_theory": {
            "scenario_name": "Wind Farm Telemetry Disruption",
            "vacr_usd": 22000000,
            "hypothesis": "Test hypothesis",
            "active_topics": [],
            "geo_queries": ["geo query 1"],
            "cyber_queries": ["cyber query 1"],
        },
        "collection": {
            "pass_1_result_count": 4,
            "gap_assessment": "3 sources found",
            "gaps_identified": [],
            "pass_2_queries": [],
            "pass_2_result_count": 0,
            "total_result_count": 4,
        },
        "conclusion": {
            "theory_confirmed": True,
            "confidence_rationale": "Corroborated.",
            "suggested_admiralty": "B2",
            "signal_type": "trend",
            "dominant_pillar": "Cyber",
        },
    }
    assert validate_scratchpad(valid) == []


def test_validate_scratchpad_catches_missing_keys():
    errors = validate_scratchpad({"region": "AME"})
    assert any("collected_at" in e for e in errors)
    assert any("working_theory" in e for e in errors)
    assert any("collection" in e for e in errors)
    assert any("conclusion" in e for e in errors)
```

- [ ] **Step 2: Run tests — both should pass (pure dict logic, no imports)**

```bash
uv run pytest tests/test_research_collector.py -v
```

Expected: 2 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_research_collector.py
git commit -m "test: scratchpad schema validator"
```

---

### Task 3: research_collector.py skeleton + mock delegation

**Files:**
- Create: `tools/research_collector.py`

- [ ] **Step 1: Write failing test for mock delegation**

Add to `tests/test_research_collector.py`:

```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import patch, MagicMock


def test_mock_mode_calls_geo_and_cyber_collectors():
    """In mock mode, research_collector delegates to geo_collector + cyber_collector."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        from tools.research_collector import run_mock_mode
        run_mock_mode("AME")
        calls = [str(c) for c in mock_run.call_args_list]
        assert any("geo_collector" in c for c in calls)
        assert any("cyber_collector" in c for c in calls)
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_research_collector.py::test_mock_mode_calls_geo_and_cyber_collectors -v
```

Expected: `ImportError` — `tools.research_collector` does not exist.

- [ ] **Step 3: Create tools/research_collector.py skeleton**

```python
#!/usr/bin/env python3
"""Target-centric OSINT research collector.

Usage:
    uv run python tools/research_collector.py <REGION> [--mock]

Mock mode: delegates to geo_collector.py + cyber_collector.py (unchanged behaviour).
Live mode: 3-pass target-centric loop using Anthropic API.

Writes (live mode only):
    output/regional/{region}/research_scratchpad.json  — audit trail
    output/regional/{region}/geo_signals.json          — same schema as geo_collector
    output/regional/{region}/cyber_signals.json        — same schema as cyber_collector
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}


def run_mock_mode(region: str) -> None:
    """Delegate to existing collectors unchanged."""
    for collector in ("geo_collector", "cyber_collector"):
        subprocess.run(
            [sys.executable, f"tools/{collector}.py", region, "--mock"],
            check=True,
        )


def run_live_mode(region: str) -> None:
    """Target-centric collection loop — 3 LLM calls."""
    raise NotImplementedError("Live mode not yet implemented")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: research_collector.py <REGION> [--mock]", file=sys.stderr)
        sys.exit(1)

    region = sys.argv[1].upper()
    if region not in VALID_REGIONS:
        print(f"Invalid region: {region}. Valid: {VALID_REGIONS}", file=sys.stderr)
        sys.exit(1)

    mock = "--mock" in sys.argv

    if mock:
        run_mock_mode(region)
    else:
        run_live_mode(region)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_research_collector.py::test_mock_mode_calls_geo_and_cyber_collectors -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/research_collector.py tests/test_research_collector.py
git commit -m "feat: research_collector skeleton with mock delegation"
```

---

### Task 4: LLM helper + `form_working_theory()` (LLM Call 1)

Reads CRQ database + topics registry + company profile. Returns a structured working theory with separate geo and cyber query lists.

**Files:**
- Modify: `tools/research_collector.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_research_collector.py`:

```python
def test_form_working_theory_structure():
    """form_working_theory returns dict with required keys including geo_queries and cyber_queries."""
    crq_data = {
        "AME": [{"scenario_name": "Wind Farm Telemetry & Maintenance Disruption", "value_at_cyber_risk_usd": 22000000}]
    }
    topics = [
        {"id": "ot-ics-cyber-attacks", "label": "OT/ICS Cyber Attacks", "regions": ["AME"], "active": True},
        {"id": "other-topic", "label": "Other", "regions": ["APAC"], "active": True},
    ]
    company_profile = {"industry": "Wind Energy", "crown_jewels": ["turbine designs"]}

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "hypothesis": "AME carries $22M exposure in wind telemetry...",
        "geo_queries": ["AME energy policy instability 2026", "Americas wind regulation 2026"],
        "cyber_queries": ["AME wind farm cyber attack 2026", "Americas OT ICS ransomware 2026"],
    }))]

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        from tools.research_collector import form_working_theory
        result = form_working_theory("AME", crq_data, topics, company_profile)

    assert result["scenario_name"] == "Wind Farm Telemetry & Maintenance Disruption"
    assert result["vacr_usd"] == 22000000
    assert "hypothesis" in result
    assert "geo_queries" in result and isinstance(result["geo_queries"], list)
    assert "cyber_queries" in result and isinstance(result["cyber_queries"], list)
    assert len(result["geo_queries"]) >= 2
    assert len(result["cyber_queries"]) >= 2
    # Only AME-scoped active topics
    assert all(t["id"] == "ot-ics-cyber-attacks" for t in result["active_topics"])
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_research_collector.py::test_form_working_theory_structure -v
```

Expected: `ImportError` — `form_working_theory` not defined.

- [ ] **Step 3: Implement `_call_llm()` and `form_working_theory()`**

Add to `tools/research_collector.py` (before `run_mock_mode`):

```python
import anthropic


def _call_llm(prompt: str, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 1024) -> dict:
    """Call Anthropic API, parse JSON response. Raises ValueError on bad JSON."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


def form_working_theory(region: str, crq_data: dict, topics: list, company_profile: dict) -> dict:
    """LLM Call 1: Form a CRQ-grounded working theory for the region.

    Returns dict with: scenario_name, vacr_usd, hypothesis, active_topics, geo_queries, cyber_queries
    """
    scenario = crq_data.get(region, [{}])[0]
    scenario_name = scenario.get("scenario_name", "Unknown")
    vacr = scenario.get("value_at_cyber_risk_usd", 0)

    active_topics = [
        {"id": t["id"], "label": t["label"]}
        for t in topics
        if t.get("active") and region in t.get("regions", [])
    ]

    prompt = f"""You are forming a target-centric intelligence collection hypothesis.

REGION: {region}
CRQ SCENARIO: {scenario_name}
VALUE AT CYBER RISK: ${vacr:,}
COMPANY: {company_profile.get("industry", "Wind Energy")} operator
CROWN JEWELS: {json.dumps(company_profile.get("crown_jewels", []))}
ACTIVE TOPICS FOR THIS REGION: {json.dumps(active_topics)}

Form a working theory: is there evidence that the {scenario_name} scenario is materializing in {region}?

Return ONLY valid JSON (no markdown fences):
{{
  "hypothesis": "One paragraph — state the hypothesis grounded in the dollar exposure and what evidence would confirm or deny it",
  "geo_queries": ["geopolitical query 1", "geopolitical query 2", "geopolitical query 3"],
  "cyber_queries": ["cyber threat query 1", "cyber threat query 2", "cyber threat query 3"]
}}

geo_queries: focus on geopolitical drivers, regulatory change, state actor intent.
cyber_queries: focus on cyber incidents, threat actor activity, OT/ICS targeting.
All queries must be specific to {region}, the scenario, and wind energy context. Minimum 2 per list."""

    result = _call_llm(prompt)
    return {
        "scenario_name": scenario_name,
        "vacr_usd": vacr,
        "hypothesis": result["hypothesis"],
        "active_topics": active_topics,
        "geo_queries": result["geo_queries"],
        "cyber_queries": result["cyber_queries"],
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_research_collector.py::test_form_working_theory_structure -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/research_collector.py tests/test_research_collector.py
git commit -m "feat: form_working_theory — LLM call 1, CRQ-grounded hypothesis"
```

---

### Task 5: `run_search_pass()` — subprocess collection with deduplication

Calls `osint_search.py` for a list of queries with the required `--type` flag. Deduplicates by URL.

**Files:**
- Modify: `tools/research_collector.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_research_collector.py`:

```python
def test_run_search_pass_deduplicates_by_url():
    """run_search_pass deduplicates results sharing the same URL."""
    result_a = json.dumps([
        {"title": "A", "summary": "summary a", "url": "https://example.com/a", "published_date": "2026-01-01"},
        {"title": "B", "summary": "summary b", "url": "https://example.com/b", "published_date": "2026-01-02"},
    ])
    result_b = json.dumps([
        {"title": "B duplicate", "summary": "summary b again", "url": "https://example.com/b", "published_date": "2026-01-02"},
        {"title": "C", "summary": "summary c", "url": "https://example.com/c", "published_date": "2026-01-03"},
    ])

    call_count = 0
    def fake_run(cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        mock = MagicMock()
        mock.stdout = result_a if call_count == 1 else result_b
        mock.returncode = 0
        return mock

    with patch("subprocess.run", side_effect=fake_run):
        from tools.research_collector import run_search_pass
        results = run_search_pass("AME", ["query one", "query two"], "geo")

    urls = [r["url"] for r in results]
    assert len(urls) == len(set(urls)), "Duplicate URLs found"
    assert len(results) == 3  # A, B, C — B deduplicated


def test_run_search_pass_includes_type_flag():
    """run_search_pass passes --type flag to osint_search.py."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        from tools.research_collector import run_search_pass
        run_search_pass("AME", ["test query"], "cyber")
        cmd = mock_run.call_args[0][0]
        assert "--type" in cmd
        assert "cyber" in cmd


def test_run_search_pass_skips_failed_queries():
    """run_search_pass skips queries where osint_search returns non-zero."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        from tools.research_collector import run_search_pass
        results = run_search_pass("AME", ["bad query"], "geo")
    assert results == []
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_research_collector.py::test_run_search_pass_deduplicates_by_url tests/test_research_collector.py::test_run_search_pass_includes_type_flag tests/test_research_collector.py::test_run_search_pass_skips_failed_queries -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `run_search_pass()`**

Add to `tools/research_collector.py`:

```python
def run_search_pass(region: str, queries: list[str], query_type: str) -> list[dict]:
    """Run queries via osint_search.py with the given type. Returns deduplicated results.

    Args:
        query_type: "geo" or "cyber" — passed as --type flag to osint_search.py
    """
    seen_urls: set[str] = set()
    results: list[dict] = []

    for query in queries:
        proc = subprocess.run(
            [sys.executable, "tools/osint_search.py", region, query, "--type", query_type],
            capture_output=True, text=True,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            continue
        try:
            items = json.loads(proc.stdout)
        except json.JSONDecodeError:
            continue
        for item in items:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                results.append(item)

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_research_collector.py::test_run_search_pass_deduplicates_by_url tests/test_research_collector.py::test_run_search_pass_includes_type_flag tests/test_research_collector.py::test_run_search_pass_skips_failed_queries -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/research_collector.py tests/test_research_collector.py
git commit -m "feat: run_search_pass — typed, deduplicated subprocess collection"
```

---

### Task 6: LLM Call 2 — `assess_gaps()`

Reads initial results against the working theory. Returns gap list and targeted follow-up queries.

**Files:**
- Modify: `tools/research_collector.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_research_collector.py`:

```python
def test_assess_gaps_returns_no_gaps_when_sufficient():
    """assess_gaps returns run_pass_2=False when evidence is sufficient."""
    working_theory = {
        "scenario_name": "Wind Farm Telemetry Disruption",
        "vacr_usd": 22000000,
        "hypothesis": "Test hypothesis",
        "active_topics": [],
    }
    results = [
        {"title": f"Result {i}", "summary": f"summary {i}", "url": f"https://ex.com/{i}"}
        for i in range(5)
    ]

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "gap_assessment": "5 sources corroborate the hypothesis. Sufficient coverage.",
        "gaps_identified": [],
        "follow_up_queries": [],
        "follow_up_query_type": "cyber",
        "run_pass_2": False,
    }))]

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        from tools.research_collector import assess_gaps
        result = assess_gaps("AME", working_theory, results)

    assert result["run_pass_2"] is False
    assert result["gaps_identified"] == []


def test_assess_gaps_returns_queries_when_gaps_found():
    """assess_gaps returns run_pass_2=True and follow_up_queries when gaps found."""
    working_theory = {"scenario_name": "Test", "vacr_usd": 0, "hypothesis": "Test", "active_topics": []}
    results = [{"title": "Generic news", "summary": "general politics", "url": "https://ex.com/1"}]

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "gap_assessment": "No wind-sector signal found.",
        "gaps_identified": ["No energy sector specificity"],
        "follow_up_queries": ["wind turbine cyber attack AME 2026"],
        "follow_up_query_type": "cyber",
        "run_pass_2": True,
    }))]

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        from tools.research_collector import assess_gaps
        result = assess_gaps("AME", working_theory, results)

    assert result["run_pass_2"] is True
    assert len(result["follow_up_queries"]) >= 1
    assert result["follow_up_query_type"] in ("geo", "cyber")
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_research_collector.py::test_assess_gaps_returns_no_gaps_when_sufficient tests/test_research_collector.py::test_assess_gaps_returns_queries_when_gaps_found -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `assess_gaps()`**

Add to `tools/research_collector.py`:

```python
def assess_gaps(region: str, working_theory: dict, results: list[dict]) -> dict:
    """LLM Call 2: Assess evidence against the working theory. Identify gaps.

    Returns dict with: gap_assessment, gaps_identified, follow_up_queries,
                       follow_up_query_type, run_pass_2
    """
    snippets_text = "\n".join(
        f"- [{r.get('title', '')}] {r.get('summary', '')}"
        for r in results[:15]  # Cap to keep prompt size bounded
    )

    prompt = f"""You are assessing intelligence collection coverage.

REGION: {region}
WORKING THEORY: {working_theory['hypothesis']}
SCENARIO: {working_theory['scenario_name']} (${working_theory['vacr_usd']:,} exposure)

EVIDENCE COLLECTED ({len(results)} results):
{snippets_text}

Assess: does the collected evidence adequately address the working theory?
- Is there a wind energy or sector-specific signal?
- Are there gaps (e.g., no sector signal, no recent events, no cyber-specific indicator)?
- If gaps exist, what 1-3 targeted follow-up queries would fill them?
- Should they be geo type (geopolitical) or cyber type?

Return ONLY valid JSON (no markdown fences):
{{
  "gap_assessment": "2-3 sentence assessment of evidence quality against the theory",
  "gaps_identified": ["gap1", "gap2"],
  "follow_up_queries": ["targeted query 1"],
  "follow_up_query_type": "geo",
  "run_pass_2": true
}}

Set run_pass_2 to false if 3+ corroborating sources address the scenario (sufficient).
Set run_pass_2 to true if significant gaps remain. Maximum 3 follow_up_queries."""

    return _call_llm(prompt)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_research_collector.py::test_assess_gaps_returns_no_gaps_when_sufficient tests/test_research_collector.py::test_assess_gaps_returns_queries_when_gaps_found -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/research_collector.py tests/test_research_collector.py
git commit -m "feat: assess_gaps — LLM call 2, target-centric gap identification"
```

---

### Task 7: LLM Call 3 — `synthesize_signals()` (Sonnet)

Synthesizes all collected results into `geo_signals.json` + `cyber_signals.json` schemas.

**Files:**
- Modify: `tools/research_collector.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_research_collector.py`:

```python
def test_synthesize_signals_produces_valid_schema():
    """synthesize_signals returns geo_signals, cyber_signals, conclusion matching expected schemas."""
    working_theory = {
        "scenario_name": "Wind Farm Telemetry Disruption",
        "vacr_usd": 22000000,
        "hypothesis": "Test",
        "active_topics": [{"id": "ot-ics-cyber-attacks", "label": "OT/ICS"}],
    }
    results = [
        {"title": "Wind energy OT attack", "summary": "Ransomware hit wind farm", "url": "https://ex.com/1"},
        {"title": "AME energy sector", "summary": "Cyber threat trend", "url": "https://ex.com/2"},
    ]

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "geo_signals": {
            "summary": "Geopolitical instability drives energy sector risk in AME.",
            "lead_indicators": ["Congressional hearing on grid ransomware", "Executive order on wind infrastructure"],
            "dominant_pillar": "Geopolitical",
            "matched_topics": ["ot-ics-cyber-attacks"],
        },
        "cyber_signals": {
            "summary": "Ransomware trend targeting wind farm telemetry systems.",
            "threat_vector": "Ransomware via supply chain",
            "target_assets": ["Live telemetry", "Remote maintenance systems"],
            "dominant_pillar": "Cyber",
            "matched_topics": ["ot-ics-cyber-attacks"],
        },
        "conclusion": {
            "theory_confirmed": True,
            "confidence_rationale": "2 corroborating sources, sector-specific.",
            "suggested_admiralty": "B2",
            "signal_type": "trend",
            "dominant_pillar": "Cyber",
        },
    }))]

    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        from tools.research_collector import synthesize_signals
        geo, cyber, conclusion = synthesize_signals("AME", working_theory, results)

    assert "summary" in geo
    assert "lead_indicators" in geo
    assert isinstance(geo["lead_indicators"], list)
    assert "summary" in cyber
    assert "threat_vector" in cyber
    assert "suggested_admiralty" in conclusion
    assert conclusion["signal_type"] in ("event", "trend", "mixed")
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_research_collector.py::test_synthesize_signals_produces_valid_schema -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `synthesize_signals()`**

Add to `tools/research_collector.py`:

```python
def synthesize_signals(
    region: str, working_theory: dict, results: list[dict]
) -> tuple[dict, dict, dict]:
    """LLM Call 3 (Sonnet): Synthesize all results into geo + cyber signal schemas.

    Returns: (geo_signals, cyber_signals, conclusion)
    """
    snippets_text = "\n".join(
        f"- [{r.get('title', '')}] ({r.get('url', '')}) {r.get('summary', '')}"
        for r in results[:20]
    )
    topic_ids = [t["id"] for t in working_theory.get("active_topics", [])]

    prompt = f"""You are synthesizing OSINT collection into structured intelligence signals.

REGION: {region}
WORKING THEORY: {working_theory['hypothesis']}
SCENARIO: {working_theory['scenario_name']} (${working_theory['vacr_usd']:,})
ACTIVE TOPICS: {json.dumps(topic_ids)}

COLLECTED EVIDENCE ({len(results)} results):
{snippets_text}

Synthesize this into structured intelligence. Separate the geopolitical context (WHY) from the cyber vector (HOW).

Return ONLY valid JSON (no markdown fences):
{{
  "geo_signals": {{
    "summary": "2-3 sentence geopolitical context",
    "lead_indicators": ["indicator 1", "indicator 2", "indicator 3"],
    "dominant_pillar": "Geopolitical",
    "matched_topics": ["topic-id-if-matched"]
  }},
  "cyber_signals": {{
    "summary": "2-3 sentence cyber threat summary",
    "threat_vector": "How the threat reaches the organisation",
    "target_assets": ["asset 1", "asset 2"],
    "dominant_pillar": "Cyber",
    "matched_topics": ["topic-id-if-matched"]
  }},
  "conclusion": {{
    "theory_confirmed": true,
    "confidence_rationale": "Evidence quality assessment — sources, corroboration, contradictions",
    "suggested_admiralty": "B2",
    "signal_type": "event|trend|mixed",
    "dominant_pillar": "Geo|Cyber"
  }}
}}

signal_type must be one of: event, trend, mixed.
Only include topic IDs from the ACTIVE TOPICS list in matched_topics."""

    # Sonnet for synthesis — quality-critical step
    result = _call_llm(prompt, model="claude-sonnet-4-6", max_tokens=2048)
    return result["geo_signals"], result["cyber_signals"], result["conclusion"]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_research_collector.py::test_synthesize_signals_produces_valid_schema -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/research_collector.py tests/test_research_collector.py
git commit -m "feat: synthesize_signals — LLM call 3 (Sonnet), produces geo+cyber schemas"
```

---

### Task 8: Wire live mode + write all outputs

Assembles the full live collection loop in `run_live_mode()`, writes signal files and scratchpad.

**Files:**
- Modify: `tools/research_collector.py`

- [ ] **Step 1: Write failing integration test**

Add to `tests/test_research_collector.py`:

```python
def test_run_live_mode_writes_all_output_files(tmp_path, monkeypatch):
    """run_live_mode writes scratchpad, geo_signals, cyber_signals to the output dir."""
    import tools.research_collector as rc

    region_dir = tmp_path / "regional" / "ame"
    region_dir.mkdir(parents=True)
    monkeypatch.setattr(rc, "get_output_dir", lambda region: region_dir)

    data_by_path = {
        "mock_crq_database": {"AME": [{"scenario_name": "Test Scenario", "value_at_cyber_risk_usd": 22000000}]},
        "osint_topics": [],
        "company_profile": {"industry": "Wind Energy", "crown_jewels": []},
    }
    def fake_load_json(path):
        path_str = str(path)
        for key, val in data_by_path.items():
            if key in path_str:
                return val
        return {}

    monkeypatch.setattr(rc, "_load_json", fake_load_json)
    monkeypatch.setattr(rc, "form_working_theory", lambda *a, **kw: {
        "scenario_name": "Test", "vacr_usd": 22000000,
        "hypothesis": "Test", "active_topics": [],
        "geo_queries": ["q1"], "cyber_queries": ["q2"],
    })
    monkeypatch.setattr(rc, "run_search_pass", lambda *a, **kw: [
        {"title": "T", "summary": "S", "url": "https://ex.com/1"}
    ])
    monkeypatch.setattr(rc, "assess_gaps", lambda *a, **kw: {
        "gap_assessment": "OK", "gaps_identified": [],
        "follow_up_queries": [], "follow_up_query_type": "cyber", "run_pass_2": False,
    })
    monkeypatch.setattr(rc, "synthesize_signals", lambda *a, **kw: (
        {"summary": "geo", "lead_indicators": [], "dominant_pillar": "Geopolitical", "matched_topics": []},
        {"summary": "cyber", "threat_vector": "test", "target_assets": [], "dominant_pillar": "Cyber", "matched_topics": []},
        {"theory_confirmed": True, "confidence_rationale": "OK", "suggested_admiralty": "B2",
         "signal_type": "trend", "dominant_pillar": "Cyber"},
    ))

    rc.run_live_mode("AME")

    assert (region_dir / "research_scratchpad.json").exists()
    assert (region_dir / "geo_signals.json").exists()
    assert (region_dir / "cyber_signals.json").exists()

    scratchpad = json.loads((region_dir / "research_scratchpad.json").read_text())
    errors = validate_scratchpad(scratchpad)
    assert errors == [], f"Scratchpad schema violations: {errors}"
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_research_collector.py::test_run_live_mode_writes_all_output_files -v
```

Expected: fails — `get_output_dir`, `_load_json` not defined yet.

- [ ] **Step 3: Implement helpers and full `run_live_mode()`**

Add helpers and replace the stub `run_live_mode` in `tools/research_collector.py`:

```python
def _load_json(path: str | Path) -> dict | list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_output_dir(region: str) -> Path:
    p = Path("output/regional") / region.lower()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_json(path: Path, data: dict | list) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def run_live_mode(region: str) -> None:
    """Target-centric collection loop — 3 bounded LLM calls."""
    crq_data = _load_json("data/mock_crq_database.json")
    topics = _load_json("data/osint_topics.json")
    company_profile = _load_json("data/company_profile.json")
    out_dir = get_output_dir(region)

    # --- LLM Call 1: Form working theory ---
    working_theory = form_working_theory(region, crq_data, topics, company_profile)

    # --- Pass 1: Initial geo + cyber collection ---
    pass_1_geo = run_search_pass(region, working_theory["geo_queries"], "geo")
    pass_1_cyber = run_search_pass(region, working_theory["cyber_queries"], "cyber")
    pass_1_results = pass_1_geo + pass_1_cyber

    # --- LLM Call 2: Assess gaps ---
    gap_data = assess_gaps(region, working_theory, pass_1_results)

    # --- Pass 2: Fill gaps (if needed) ---
    pass_2_results: list[dict] = []
    if gap_data.get("run_pass_2") and gap_data.get("follow_up_queries"):
        query_type = gap_data.get("follow_up_query_type", "cyber")
        pass_2_results = run_search_pass(region, gap_data["follow_up_queries"], query_type)

    all_results = pass_1_results + pass_2_results

    # --- LLM Call 3: Synthesize (Sonnet) ---
    geo_signals, cyber_signals, conclusion = synthesize_signals(region, working_theory, all_results)

    # --- Enrich with metadata ---
    collected_at = datetime.now(timezone.utc).isoformat()
    geo_signals.update({"region": region, "collected_at": collected_at})
    cyber_signals.update({"region": region, "collected_at": collected_at})

    # --- Write outputs ---
    _write_json(out_dir / "geo_signals.json", geo_signals)
    _write_json(out_dir / "cyber_signals.json", cyber_signals)

    scratchpad = {
        "region": region,
        "collected_at": collected_at,
        "working_theory": working_theory,
        "collection": {
            "pass_1_result_count": len(pass_1_results),
            "gap_assessment": gap_data.get("gap_assessment", ""),
            "gaps_identified": gap_data.get("gaps_identified", []),
            "pass_2_queries": gap_data.get("follow_up_queries", []),
            "pass_2_result_count": len(pass_2_results),
            "total_result_count": len(all_results),
        },
        "conclusion": conclusion,
    }
    _write_json(out_dir / "research_scratchpad.json", scratchpad)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_research_collector.py::test_run_live_mode_writes_all_output_files -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite — no regressions**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add tools/research_collector.py tests/test_research_collector.py
git commit -m "feat: run_live_mode — full target-centric loop, scratchpad + signals written"
```

---

## Chunk 2: Pipeline Wiring

### Task 9: Wire into run-crq.md (live mode)

**Files:**
- Modify: `.claude/commands/run-crq.md`

- [ ] **Step 1: Find the current OSINT collection section**

```bash
grep -n "geo_collector\|cyber_collector\|OSINT\|mock" .claude/commands/run-crq.md | head -20
```

- [ ] **Step 2: Update the collector section**

Locate the block in `run-crq.md` that calls `geo_collector.py` and `cyber_collector.py`. Replace the block so that:

- **Mock mode (default, `--mock` flag passed to collectors):** unchanged — still calls `geo_collector.py --mock` + `cyber_collector.py --mock`
- **Live mode (`OSINT_LIVE=true`):** calls `research_collector.py {REGION}` instead

Add this section to run-crq.md where OSINT collection is described:

```markdown
**OSINT Collection (per region):**

Check the `OSINT_LIVE` environment variable:

- If `OSINT_LIVE=true`:
  Run: `uv run python tools/research_collector.py {REGION}`
  This runs the target-centric research loop (3 LLM calls) and writes:
  - `output/regional/{region}/research_scratchpad.json` (working theory + audit trail)
  - `output/regional/{region}/geo_signals.json`
  - `output/regional/{region}/cyber_signals.json`

- Otherwise (default):
  Run: `uv run python tools/geo_collector.py {REGION} --mock`
  Run: `uv run python tools/cyber_collector.py {REGION} --mock`
```

- [ ] **Step 3: Verify mock path still works end-to-end**

```bash
uv run python tools/research_collector.py AME --mock && echo "mock delegation OK"
ls -la output/regional/ame/geo_signals.json output/regional/ame/cyber_signals.json
```

Expected: both files present, no `research_scratchpad.json` (correct — mock mode skips it).

- [ ] **Step 4: Commit**

```bash
git add .claude/commands/run-crq.md
git commit -m "feat: run-crq wires research_collector for live mode OSINT"
```

---

### Task 10: Update gatekeeper-agent — read scratchpad

**Files:**
- Modify: `.claude/agents/gatekeeper-agent.md`

- [ ] **Step 1: Add scratchpad as optional input**

In the TASK section of `gatekeeper-agent.md`, add a 4th read step:

```markdown
4. If it exists, read: `output/regional/{region_lower}/research_scratchpad.json`
   - Contains the target-centric working theory and pre-assessed confidence from the research collector.
   - If present: read `conclusion.suggested_admiralty` and `conclusion.confidence_rationale`.
     Your Admiralty assignment must either confirm or explicitly challenge it with a one-sentence rationale.
     Format: "Confirmed B2 — [your rationale]" or "Assessed C3 — [override rationale]"
   - If absent (mock mode): assign Admiralty as normal from signal files alone.
```

- [ ] **Step 2: Verify the gatekeeper mock pipeline still works**

```bash
uv run python tools/geo_collector.py APAC --mock
uv run python tools/cyber_collector.py APAC --mock
uv run python tools/scenario_mapper.py APAC --mock
echo "Signal files written — gatekeeper can be triggered normally"
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/gatekeeper-agent.md
git commit -m "feat: gatekeeper reads scratchpad to confirm/challenge suggested admiralty"
```

---

### Task 11: Update regional-analyst-agent — read scratchpad

**Files:**
- Modify: `.claude/agents/regional-analyst-agent.md`

- [ ] **Step 1: Add scratchpad to STEP 1 — LOAD CONTEXT**

In the numbered file read list in `regional-analyst-agent.md`, add:

```markdown
8. `output/regional/{region_lower}/research_scratchpad.json` (if present — live mode only)
   - `working_theory.hypothesis`: the collection hypothesis that drove OSINT. Use as an analytical starting frame — not a conclusion.
   - `conclusion.signal_type`: the collector's suggested classification (event/trend/mixed). Validate it against your own reading of the signal files.
   - `collection.gap_assessment` + `collection.gaps_identified`: what the collector could not find. Reference remaining gaps in your brief's forward-looking closing statement.
   - If absent: proceed as normal.
```

- [ ] **Step 2: Add note to STEP 2 — SCENARIO COUPLING**

At the top of the STEP 2 section, add:

```markdown
If `research_scratchpad.json` is present, the working theory provides a starting analytical frame:
- Hypothesis: `working_theory.hypothesis`
- Do not accept it uncritically — validate it against the signal files and master_scenarios.json.
- If the collector's hypothesis conflicts with what the signals actually show, use your judgment and state why.
```

- [ ] **Step 3: Run full test suite — confirm no regressions**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add .claude/agents/regional-analyst-agent.md
git commit -m "feat: analyst reads scratchpad working theory as analytical starting frame"
```

---

### Task 12: Integration smoke test

**Files:** No changes.

- [ ] **Step 1: Mock pipeline — all 5 regions**

```bash
for region in APAC AME LATAM MED NCE; do
  uv run python tools/research_collector.py $region --mock && echo "$region OK"
done
```

Expected: all 5 print OK.

- [ ] **Step 2: Confirm scratchpad absent in mock mode**

```bash
ls output/regional/ame/research_scratchpad.json 2>/dev/null && echo "UNEXPECTED" || echo "Correctly absent in mock mode"
```

Expected: `Correctly absent in mock mode`.

- [ ] **Step 3: Final test suite run**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all pass, zero failures.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "test: integration smoke test — research collector mock path all 5 regions"
```

---

## Summary

| Layer | Before | After |
|---|---|---|
| Collection (live) | 2 fixed queries, 1-3 results, no reasoning | 3 LLM calls: CRQ-grounded theory, geo+cyber passes, gap assessment |
| Collection (mock) | `geo_collector --mock` + `cyber_collector --mock` | **Unchanged** — `research_collector --mock` delegates identically |
| Subprocess pattern | `[sys.executable, "tools/script.py", ...]` | Same — consistent throughout |
| `osint_search.py` contract | `--type geo|cyber` required | Honoured — `run_search_pass` always passes `--type` |
| New artifact | — | `research_scratchpad.json`: working theory + evidence + conclusion |
| Gatekeeper | Assigns Admiralty cold | Confirms/challenges pre-assessed confidence from scratchpad |
| Analyst | Forms theory cold | Starts from scratchpad hypothesis + gap list |
| New dependencies | — | `anthropic` SDK only |
