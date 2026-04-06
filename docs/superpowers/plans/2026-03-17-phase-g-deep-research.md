# Phase G — Deep Research Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared `tools/deep_research.py` module wrapping GPT Researcher with Claude + Tavily, wired into the pipeline as an optional deep research pass and consumed by a new `tools/discover.py` for Config tab discovery.

**Architecture:** GPT Researcher runs as an async Python library. A sync CLI wrapper makes it callable from the pipeline. A Haiku extraction step converts markdown reports to structured JSON matching existing signal schemas. Progress streams to the Agent Activity Console via the existing SSE infrastructure. The pipeline adds `--deep`, `--deep-scope`, and `--depth` flags to `run-crq`.

**Tech Stack:** `gpt-researcher` (pip), `anthropic` SDK (already installed), `asyncio`, existing `osint_topics.json` registry.

**Spec:** `docs/superpowers/specs/2026-03-17-phase-g-deep-research.md`

---

## Existing Signal Schemas (do not change)

**`geo_signals.json`:**
```json
{
  "summary": "string",
  "lead_indicators": ["string"],
  "dominant_pillar": "Geopolitical|Cyber",
  "matched_topics": ["topic-id"]
}
```

**`cyber_signals.json`:**
```json
{
  "summary": "string",
  "threat_vector": "string",
  "target_assets": ["string"],
  "matched_topics": ["topic-id"]
}
```

All output from `deep_research.py` MUST match these schemas exactly so downstream tools (gatekeeper, analyst) are unaffected.

---

## Chunk 1: Install + Shared Module Core

### Task 1: Install gpt-researcher

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock` (auto-updated)

- [ ] **Step 1: Add dependency**

```bash
cd c:/Users/frede/crq-agent-workspace
uv add gpt-researcher
```

Expected: resolves and installs. If version conflict with existing deps, pin: `uv add "gpt-researcher>=0.10.0"`.

- [ ] **Step 2: Verify import**

```bash
uv run python -c "from gpt_researcher import GPTResearcher; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add gpt-researcher dependency"
```

---

### Task 2: Create tools/deep_research.py

**Files:**
- Create: `tools/deep_research.py`
- Create: `tests/test_deep_research.py`

**Context:** This is the shared module. It owns GPT Researcher config, the extraction step, and the CLI entry point. All other tools import from it.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_deep_research.py
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path


@pytest.fixture
def tmp_output(tmp_path, monkeypatch):
    """Redirect BASE output path."""
    import tools.deep_research as dr
    monkeypatch.setattr(dr, "OUTPUT", tmp_path / "output")
    (tmp_path / "output" / "regional" / "apac").mkdir(parents=True)
    return tmp_path


def test_depth_config_quick():
    from tools.deep_research import DEPTH_CONFIG
    cfg = DEPTH_CONFIG["quick"]
    assert cfg["max_subtopics"] == 2
    assert cfg["report_type"] == "summary_report"


def test_depth_config_standard():
    from tools.deep_research import DEPTH_CONFIG
    cfg = DEPTH_CONFIG["standard"]
    assert cfg["max_subtopics"] == 3
    assert cfg["report_type"] == "research_report"


def test_depth_config_deep():
    from tools.deep_research import DEPTH_CONFIG
    cfg = DEPTH_CONFIG["deep"]
    assert cfg["max_subtopics"] == 5


def test_build_query_geo():
    from tools.deep_research import build_query
    q = build_query("APAC", "geo")
    assert "APAC" in q
    assert "wind" in q.lower() or "energy" in q.lower() or "geopolit" in q.lower()


def test_build_query_cyber():
    from tools.deep_research import build_query
    q = build_query("AME", "cyber")
    assert "AME" in q or "America" in q
    assert "cyber" in q.lower() or "OT" in q or "threat" in q.lower()


def test_extract_geo_signals_returns_schema():
    from tools.deep_research import _validate_geo_signals
    valid = {
        "summary": "test summary",
        "lead_indicators": ["a", "b"],
        "dominant_pillar": "Geopolitical",
        "matched_topics": []
    }
    assert _validate_geo_signals(valid) == valid


def test_extract_geo_signals_rejects_missing_key():
    from tools.deep_research import _validate_geo_signals
    with pytest.raises(ValueError):
        _validate_geo_signals({"summary": "x"})  # missing required keys


def test_extract_cyber_signals_returns_schema():
    from tools.deep_research import _validate_cyber_signals
    valid = {
        "summary": "test",
        "threat_vector": "phishing",
        "target_assets": ["OT systems"],
        "matched_topics": []
    }
    assert _validate_cyber_signals(valid) == valid


def test_cli_requires_region_and_type(capsys):
    """CLI with no args should exit non-zero."""
    import sys
    with pytest.raises(SystemExit) as exc:
        import tools.deep_research as dr
        dr.cli_main([])
    assert exc.value.code != 0


@pytest.mark.asyncio
async def test_run_deep_research_writes_output(tmp_output):
    """Mock GPT Researcher + extraction, verify output file written."""
    import tools.deep_research as dr

    mock_report = "# Test Report\n\nSouth China Sea tensions rising."
    mock_sources = [{"href": "https://example.com", "title": "Test"}]

    expected_geo = {
        "summary": "Test summary",
        "lead_indicators": ["indicator 1"],
        "dominant_pillar": "Geopolitical",
        "matched_topics": []
    }

    with patch("tools.deep_research.GPTResearcher") as MockGPT, \
         patch("tools.deep_research._extract_with_haiku", new=AsyncMock(return_value=expected_geo)):

        instance = AsyncMock()
        instance.conduct_research = AsyncMock(return_value=[])
        instance.write_report = AsyncMock(return_value=mock_report)
        instance.get_source_urls = MagicMock(return_value=["https://example.com"])
        MockGPT.return_value = instance

        result = await dr.run_deep_research("APAC", "geo", depth="quick")

    assert result["summary"] == "Test summary"
    out_path = tmp_output / "output" / "regional" / "apac" / "geo_signals.json"
    assert out_path.exists()
    saved = json.loads(out_path.read_text())
    assert saved["summary"] == "Test summary"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_deep_research.py -v 2>&1 | head -30
```

Expected: ImportError or multiple FAILED — module doesn't exist yet.

- [ ] **Step 3: Create tools/deep_research.py**

```python
#!/usr/bin/env python3
"""Deep research module — wraps GPT Researcher with Claude + Tavily.

Usage (CLI):
    uv run python tools/deep_research.py APAC geo [--depth=standard]
    uv run python tools/deep_research.py AME cyber [--depth=quick]

Writes:
    output/regional/{region}/geo_signals.json   (overwrites shallow collector)
    output/regional/{region}/cyber_signals.json (overwrites shallow collector)
"""
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Allow importing from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUTPUT = Path(__file__).resolve().parent.parent / "output"
VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}

# ── Depth presets ──────────────────────────────────────────────────────
DEPTH_CONFIG = {
    "quick":    {"max_subtopics": 2, "report_type": "summary_report"},
    "standard": {"max_subtopics": 3, "report_type": "research_report"},
    "deep":     {"max_subtopics": 5, "report_type": "research_report"},
}

# ── Query builders ─────────────────────────────────────────────────────
GEO_QUERY_TEMPLATE = (
    "Geopolitical risk analysis {region} wind energy manufacturing and service operations 2026. "
    "Focus: state actor intent, trade policy, regulatory shifts, supply chain exposure, "
    "infrastructure security threats relevant to wind turbine production and offshore wind farm operations."
)

CYBER_QUERY_TEMPLATE = (
    "Cyber threat intelligence {region} operational technology OT ICS wind energy sector 2026. "
    "Focus: active campaigns targeting energy infrastructure, manufacturing IP theft, "
    "ransomware groups, supply chain compromise, SCADA vulnerabilities in wind energy."
)


def build_query(region: str, signal_type: str) -> str:
    """Build research query for a region + signal type."""
    if signal_type == "geo":
        return GEO_QUERY_TEMPLATE.format(region=region)
    elif signal_type == "cyber":
        return CYBER_QUERY_TEMPLATE.format(region=region)
    raise ValueError(f"Unknown signal_type: {signal_type}")


# ── Extraction prompts ─────────────────────────────────────────────────
GEO_EXTRACTION_PROMPT = """You are extracting structured intelligence signals from a research report.

Region: {region}
Report:
{report}

Extract and return ONLY valid JSON matching this exact schema:
{{
  "summary": "2-3 sentence geopolitical threat summary for {region} wind energy operations",
  "lead_indicators": ["specific signal 1", "specific signal 2", "specific signal 3"],
  "dominant_pillar": "Geopolitical",
  "matched_topics": []
}}

Rules:
- summary must describe business impact on wind energy manufacturing or service delivery
- lead_indicators must be specific, factual signals from the report (not generic statements)
- dominant_pillar is always "Geopolitical" for geo signals
- matched_topics is always empty array (pipeline populates it separately)
- Return ONLY the JSON object, no markdown, no explanation
"""

CYBER_EXTRACTION_PROMPT = """You are extracting structured cyber threat signals from a research report.

Region: {region}
Report:
{report}

Extract and return ONLY valid JSON matching this exact schema:
{{
  "summary": "2-3 sentence cyber threat summary for {region} wind energy OT/ICS",
  "threat_vector": "primary attack vector or method",
  "target_assets": ["asset 1", "asset 2", "asset 3"],
  "matched_topics": []
}}

Rules:
- summary must describe the threat in business terms, not technical jargon
- threat_vector is the primary method: supply chain, phishing, insider, etc.
- target_assets are business assets at risk: OT networks, IP, telemetry systems, etc.
- matched_topics is always empty array
- Return ONLY the JSON object, no markdown, no explanation
"""

EXTRACTION_PROMPTS = {"geo": GEO_EXTRACTION_PROMPT, "cyber": CYBER_EXTRACTION_PROMPT}


# ── Validation ─────────────────────────────────────────────────────────
def _validate_geo_signals(data: dict) -> dict:
    required = {"summary", "lead_indicators", "dominant_pillar", "matched_topics"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Missing keys in geo signals: {missing}")
    return data


def _validate_cyber_signals(data: dict) -> dict:
    required = {"summary", "threat_vector", "target_assets", "matched_topics"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Missing keys in cyber signals: {missing}")
    return data


VALIDATORS = {"geo": _validate_geo_signals, "cyber": _validate_cyber_signals}


# ── Haiku extraction ───────────────────────────────────────────────────
async def _extract_with_haiku(
    report: str,
    signal_type: str,
    region: str,
) -> dict:
    """Call Claude Haiku to extract structured signals from markdown report."""
    import anthropic

    client = anthropic.AsyncAnthropic()
    prompt = EXTRACTION_PROMPTS[signal_type].format(
        region=region,
        report=report[:8000],  # cap tokens
    )
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    data = json.loads(raw)
    return VALIDATORS[signal_type](data)


# ── Core async function ────────────────────────────────────────────────
async def run_deep_research(
    region: str,
    signal_type: str,
    depth: str = "standard",
    on_progress=None,
) -> dict:
    """
    Run deep research for a region + signal type.
    Writes output file and returns signals dict.
    """
    from gpt_researcher import GPTResearcher

    if region not in VALID_REGIONS:
        raise ValueError(f"Unknown region: {region}")
    if signal_type not in ("geo", "cyber"):
        raise ValueError(f"Unknown signal_type: {signal_type}")
    if depth not in DEPTH_CONFIG:
        raise ValueError(f"Unknown depth: {depth}. Use quick|standard|deep")

    cfg = DEPTH_CONFIG[depth]
    query = build_query(region, signal_type)

    # Progress helper
    async def _progress(msg: str):
        if on_progress:
            await on_progress(msg)

    await _progress(f"generating sub-queries ({depth} mode, {cfg['max_subtopics']} subtopics)...")

    researcher = GPTResearcher(
        query=query,
        report_type=cfg["report_type"],
        report_source="web",
        max_subtopics=cfg["max_subtopics"],
        verbose=False,
    )

    # Wire GPT Researcher's own progress to our callback
    async def gpt_progress(msg):
        await _progress(f"searching — {str(msg)[:80]}")

    await researcher.conduct_research(on_progress=gpt_progress)
    await _progress("synthesising report...")

    report = await researcher.write_report()
    await _progress("extracting signals...")

    signals = await _extract_with_haiku(report, signal_type, region)
    await _progress("done ✓")

    # Write output file
    out_dir = OUTPUT / "regional" / region.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{signal_type}_signals.json"
    out_path.write_text(json.dumps(signals, indent=2, ensure_ascii=False), encoding="utf-8")

    return signals


# ── CLI entry point ────────────────────────────────────────────────────
def cli_main(args=None):
    if args is None:
        args = sys.argv[1:]

    if len(args) < 2:
        print("Usage: deep_research.py REGION geo|cyber [--depth=standard]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    signal_type = args[1].lower()
    depth = "standard"
    for a in args[2:]:
        if a.startswith("--depth="):
            depth = a.split("=", 1)[1]

    async def _run():
        print(f"[deep_research] {region} {signal_type} depth={depth}", flush=True)

        async def progress(msg):
            print(f"[deep_research] {region} {signal_type} — {msg}", flush=True)

        result = await run_deep_research(region, signal_type, depth=depth, on_progress=progress)
        print(json.dumps(result, indent=2))
        return result

    asyncio.run(_run())


if __name__ == "__main__":
    cli_main()
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_deep_research.py -v
```

Expected: All tests PASS. The async test requires `pytest-anyio` — if missing: `uv add --dev pytest-anyio` and add `@pytest.mark.anyio` instead of `@pytest.mark.asyncio`.

- [ ] **Step 5: Smoke test CLI (requires ANTHROPIC_API_KEY + TAVILY_API_KEY)**

```bash
uv run python tools/deep_research.py APAC geo --depth=quick 2>&1 | tail -20
```

Expected: Progress lines printed, then JSON object matching geo_signals schema.

- [ ] **Step 6: Commit**

```bash
git add tools/deep_research.py tests/test_deep_research.py
git commit -m "feat: add tools/deep_research.py — GPT Researcher + Claude Haiku extraction"
```

---

## Chunk 2: Pipeline Integration

### Task 3: Wire deep research into run-crq + server.py SSE

**Files:**
- Modify: `.claude/commands/run-crq.md`
- Modify: `server.py`

- [ ] **Step 1: Read current run-crq.md to understand pipeline phases**

Read `.claude/commands/run-crq.md` — note where Phase 1 (collectors) and Phase 2 (gatekeeper) complete so you know where to insert the deep research pass.

- [ ] **Step 2: Add deep research phase to run-crq.md**

After the gatekeeper fan-in section, add Phase 1.5 — Deep Research Pass:

```markdown
## Phase 1.5 — Deep Research Pass (conditional)

Only runs if `--deep` flag is present.

**Scope logic:**
- If `--deep-scope=all` → run for ALL 5 regions
- Default (`--deep-scope=escalated`) → run only for regions where gatekeeper returned ESCALATE

**For each in-scope region (run in parallel via Task fan-out):**
```bash
uv run python tools/deep_research.py {REGION} geo  --depth={depth}
uv run python tools/deep_research.py {REGION} cyber --depth={depth}
```

Where `{depth}` comes from the `--depth=quick|standard|deep` flag (default: `standard`).

These commands overwrite the shallow `geo_signals.json` and `cyber_signals.json` files written in Phase 1. The regional-analyst-agent in Phase 2 reads the enriched versions.

Log on entry:
```bash
uv run python tools/audit_logger.py PHASE_COMPLETE "Deep research pass started — scope={scope} depth={depth}"
```

Log on completion:
```bash
uv run python tools/audit_logger.py PHASE_COMPLETE "Deep research pass complete"
```
```

- [ ] **Step 3: Add deep_research SSE event handler to server.py**

Add a new event type to `_run_tools_mode` (and `_run_full_mode`) that forwards deep research progress to the SSE queue. In `server.py`, the `_emit` function already handles this — the tool just needs to emit the right event type. Add a note in `_run_tools_mode` that deep research subprocess stdout lines are forwarded as `deep_research` events.

- [ ] **Step 4: Add deep_research SSE handler to app.js**

In `static/app.js`, add after the existing SSE event listeners (around line 360):

```js
es.addEventListener('deep_research', e => {
  const d = JSON.parse(e.data);
  appendConsoleEntry(
    `<span style="color:#79c0ff;font-size:10px">[deep] ${esc(d.region||'')} ${esc(d.type||'')} — ${esc(d.message||'')}</span>`
  );
});
```

- [ ] **Step 5: Commit**

```bash
git add .claude/commands/run-crq.md server.py static/app.js
git commit -m "feat: wire deep research pass into run-crq pipeline + SSE progress events"
```

---

## Chunk 3: discover.py + Config Tab Backend

### Task 4: Create tools/discover.py

**Files:**
- Create: `tools/discover.py`
- Create: `tools/suggest_config.py`
- Modify: `server.py`

- [ ] **Step 1: Create tools/discover.py**

```python
#!/usr/bin/env python3
"""Discovery agent — find new OSINT topics and YouTube channels.

Usage:
    uv run python tools/discover.py topics "OT cyber attacks energy sector"
    uv run python tools/discover.py sources "geopolitical risk wind energy APAC"

Output: JSON array of suggested topics or sources (stdout).
Used by: /api/discover/topics and /api/discover/sources endpoints.
"""
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deep_research import _extract_with_haiku

TOPIC_QUERY_TEMPLATE = "Research: {query}. Focus on events, trends, or threat actors relevant to wind energy manufacturing and service delivery. Find 3-5 specific trackable topics."

SOURCE_QUERY_TEMPLATE = "Find credible YouTube channels covering: {query}. Focus on geopolitical analysts, energy sector experts, cybersecurity researchers. Channels must be active in 2025-2026."

TOPIC_EXTRACTION_PROMPT = """Extract suggested OSINT tracking topics from this research.

Query: {query}
Report: {report}

Return ONLY a JSON array of 3-5 topic suggestions:
[
  {{
    "id": "kebab-case-id",
    "type": "event|trend",
    "keywords": ["keyword1", "keyword2", "keyword3"],
    "regions": ["APAC"],
    "active": true,
    "rationale": "One sentence explaining relevance to AeroGrid wind energy operations"
  }}
]

Return ONLY the JSON array, no markdown."""

SOURCE_EXTRACTION_PROMPT = """Extract suggested YouTube channel sources from this research.

Query: {query}
Report: {report}

Return ONLY a JSON array of 3-5 channel suggestions:
[
  {{
    "channel_id": "UCxxxxxxxxxx or @handle",
    "name": "Channel Name",
    "region_focus": ["APAC"],
    "topics": [],
    "rationale": "One sentence explaining credibility and relevance"
  }}
]

Return ONLY the JSON array, no markdown."""


async def discover(discover_type: str, query: str, depth: str = "quick") -> list:
    """Run discovery research and return structured suggestions."""
    from gpt_researcher import GPTResearcher
    from tools.deep_research import DEPTH_CONFIG
    import anthropic

    cfg = DEPTH_CONFIG[depth]
    full_query = TOPIC_QUERY_TEMPLATE.format(query=query) if discover_type == "topics" \
        else SOURCE_QUERY_TEMPLATE.format(query=query)

    researcher = GPTResearcher(
        query=full_query,
        report_type=cfg["report_type"],
        report_source="web",
        max_subtopics=cfg["max_subtopics"],
        verbose=False,
    )
    await researcher.conduct_research()
    report = await researcher.write_report()

    # Extract structured suggestions via Haiku
    prompt = (TOPIC_EXTRACTION_PROMPT if discover_type == "topics" else SOURCE_EXTRACTION_PROMPT)
    prompt = prompt.format(query=query, report=report[:6000])

    client = anthropic.AsyncAnthropic()
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def main():
    if len(sys.argv) < 3:
        print("Usage: discover.py topics|sources <query>", file=sys.stderr)
        sys.exit(1)

    discover_type = sys.argv[1]
    query = sys.argv[2]
    depth = "quick"
    for a in sys.argv[3:]:
        if a.startswith("--depth="):
            depth = a.split("=", 1)[1]

    results = asyncio.run(discover(discover_type, query, depth=depth))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create tools/suggest_config.py**

```python
#!/usr/bin/env python3
"""Post-run config suggestions — reads signal files, suggests new topics + channels.

Usage:
    uv run python tools/suggest_config.py

Writes: output/config_suggestions.json
"""
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUTPUT = Path(__file__).resolve().parent.parent / "output"
REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]

SUGGESTION_PROMPT = """You are a geopolitical and cyber threat intelligence advisor for AeroGrid Wind Solutions.

Existing OSINT topics being tracked:
{existing_topics}

Current pipeline signals:
{signals_summary}

Based on the signals above, suggest:
1. Three new OSINT topics that would strengthen coverage
2. Three YouTube channels that would provide relevant intelligence

Return ONLY valid JSON:
{{
  "topics": [
    {{
      "id": "kebab-case-id",
      "type": "event|trend",
      "keywords": ["kw1", "kw2"],
      "regions": ["REGION"],
      "active": true,
      "rationale": "Why this topic matters to AeroGrid"
    }}
  ],
  "sources": [
    {{
      "channel_id": "UCxxx or @handle",
      "name": "Channel Name",
      "region_focus": ["REGION"],
      "topics": [],
      "rationale": "Why this channel is credible and relevant"
    }}
  ],
  "generated_at": "{timestamp}"
}}"""


async def suggest():
    import anthropic
    from datetime import datetime, timezone

    # Load existing topics
    topics_path = Path("data/osint_topics.json")
    existing_topics = json.loads(topics_path.read_text(encoding="utf-8")) if topics_path.exists() else []

    # Collect signal summaries from all regions
    signals = []
    for region in REGIONS:
        for sig_type in ("geo", "cyber"):
            path = OUTPUT / "regional" / region.lower() / f"{sig_type}_signals.json"
            if path.exists():
                try:
                    d = json.loads(path.read_text(encoding="utf-8"))
                    signals.append(f"{region} {sig_type}: {d.get('summary', '')[:200]}")
                except Exception:
                    pass

    if not signals:
        print('{"topics": [], "sources": [], "generated_at": "no data"}')
        return

    prompt = SUGGESTION_PROMPT.format(
        existing_topics=json.dumps([t.get("id") for t in existing_topics], indent=2),
        signals_summary="\n".join(signals),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    client = anthropic.AsyncAnthropic()
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    result = json.loads(raw)
    out_path = OUTPUT / "config_suggestions.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(suggest())
```

- [ ] **Step 3: Add 3 discovery endpoints to server.py**

Add after the existing config endpoints (after `post_prompt`):

```python
# ── API: Discovery ────────────────────────────────────────────────────
@app.post("/api/discover/topics")
async def discover_topics(body: dict):
    query = body.get("query", "").strip()
    depth = body.get("depth", "quick")
    if not query:
        return JSONResponse({"error": "query required"}, status_code=400)
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", "python", str(BASE / "tools" / "discover.py"),
        "topics", query, f"--depth={depth}",
        cwd=str(BASE),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
    if proc.returncode != 0:
        return JSONResponse({"error": stderr.decode(errors="replace")[:300]}, status_code=500)
    return json.loads(stdout.decode(errors="replace"))


@app.post("/api/discover/sources")
async def discover_sources(body: dict):
    query = body.get("query", "").strip()
    depth = body.get("depth", "quick")
    if not query:
        return JSONResponse({"error": "query required"}, status_code=400)
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", "python", str(BASE / "tools" / "discover.py"),
        "sources", query, f"--depth={depth}",
        cwd=str(BASE),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
    if proc.returncode != 0:
        return JSONResponse({"error": stderr.decode(errors="replace")[:300]}, status_code=500)
    return json.loads(stdout.decode(errors="replace"))


@app.get("/api/discover/suggestions")
async def get_suggestions():
    path = OUTPUT / "config_suggestions.json"
    if not path.exists():
        return {"topics": [], "sources": [], "generated_at": None}
    return _read_json(path) or {"topics": [], "sources": [], "generated_at": None}
```

- [ ] **Step 4: Smoke test discover.py**

```bash
uv run python tools/discover.py topics "OT cyber attacks wind energy" --depth=quick
```

Expected: JSON array of 3-5 topic suggestions with `id`, `type`, `keywords`, `regions`, `rationale`.

- [ ] **Step 5: Commit**

```bash
git add tools/discover.py tools/suggest_config.py server.py
git commit -m "feat: add discover.py, suggest_config.py, and discovery API endpoints"
```

---

## Chunk 4: Config Tab Frontend — Discovery UI

### Task 5: Wire discovery search boxes into Intelligence Sources panels

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`

- [ ] **Step 1: Add search box + results area to Topics panel in index.html**

Find the Topics panel header div and add below the table divs (before the closing `</div>` of the Topics panel):

```html
<!-- Topics discovery -->
<div style="border-top:1px solid #21262d;padding:10px 14px;flex-shrink:0">
  <div style="font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:6px">Discover Topics</div>
  <div style="display:flex;gap:6px">
    <input id="topic-discover-input" type="text" placeholder="e.g. OT cyber attacks energy sector"
      style="flex:1;background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:4px 8px;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px"
      onkeydown="if(event.key==='Enter')discoverTopics()">
    <button onclick="discoverTopics()" id="btn-discover-topics"
      style="font-size:10px;color:#79c0ff;background:#0d1f36;border:1px solid #1f6feb;padding:2px 10px;border-radius:2px;cursor:pointer">Search</button>
  </div>
  <div id="topic-discover-loading" style="display:none;font-size:10px;color:#6e7681;margin-top:6px">Researching...</div>
  <div id="topic-discover-error" style="display:none;font-size:10px;color:#ff7b72;margin-top:6px"></div>
  <div id="topic-discover-results"></div>
</div>
```

Do the same for the Sources panel (replace `topic` with `source` in all IDs, `discoverTopics` with `discoverSources`):

```html
<!-- Sources discovery -->
<div style="border-top:1px solid #21262d;padding:10px 14px;flex-shrink:0">
  <div style="font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:6px">Discover Channels</div>
  <div style="display:flex;gap:6px">
    <input id="source-discover-input" type="text" placeholder="e.g. geopolitical risk wind energy APAC"
      style="flex:1;background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:4px 8px;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px"
      onkeydown="if(event.key==='Enter')discoverSources()">
    <button onclick="discoverSources()" id="btn-discover-sources"
      style="font-size:10px;color:#79c0ff;background:#0d1f36;border:1px solid #1f6feb;padding:2px 10px;border-radius:2px;cursor:pointer">Search</button>
  </div>
  <div id="source-discover-loading" style="display:none;font-size:10px;color:#6e7681;margin-top:6px">Researching...</div>
  <div id="source-discover-error" style="display:none;font-size:10px;color:#ff7b72;margin-top:6px"></div>
  <div id="source-discover-results"></div>
</div>
```

Also add a suggestions section at the bottom of each panel — loaded from `/api/discover/suggestions`:

```html
<div id="topics-suggestions" style="border-top:1px solid #21262d;padding:10px 14px">
  <div style="font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:6px">Post-Run Suggestions</div>
  <div id="topics-suggestions-body" style="font-size:11px;color:#6e7681">No suggestions yet — run the pipeline to generate.</div>
</div>
```

- [ ] **Step 2: Add discovery JS functions to app.js**

Append to the Config Tab section in `app.js`:

```js
// ── Discovery ──────────────────────────────────────────────────────────
async function discoverTopics() {
  const query = $('topic-discover-input').value.trim();
  if (!query) return;
  $('btn-discover-topics').disabled = true;
  $('topic-discover-loading').style.display = 'block';
  $('topic-discover-error').style.display = 'none';
  $('topic-discover-results').innerHTML = '';
  try {
    const r = await fetch('/api/discover/topics', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ query, depth: 'quick' }),
    });
    const results = await r.json();
    if (!r.ok) throw new Error(results.error || 'Discovery failed');
    $('topic-discover-results').innerHTML = renderDiscoverResults(results, 'topic');
  } catch(err) {
    $('topic-discover-error').textContent = err.message;
    $('topic-discover-error').style.display = 'block';
  } finally {
    $('btn-discover-topics').disabled = false;
    $('topic-discover-loading').style.display = 'none';
  }
}

async function discoverSources() {
  const query = $('source-discover-input').value.trim();
  if (!query) return;
  $('btn-discover-sources').disabled = true;
  $('source-discover-loading').style.display = 'block';
  $('source-discover-error').style.display = 'none';
  $('source-discover-results').innerHTML = '';
  try {
    const r = await fetch('/api/discover/sources', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ query, depth: 'quick' }),
    });
    const results = await r.json();
    if (!r.ok) throw new Error(results.error || 'Discovery failed');
    $('source-discover-results').innerHTML = renderDiscoverResults(results, 'source');
  } catch(err) {
    $('source-discover-error').textContent = err.message;
    $('source-discover-error').style.display = 'block';
  } finally {
    $('btn-discover-sources').disabled = false;
    $('source-discover-loading').style.display = 'none';
  }
}

function renderDiscoverResults(items, type) {
  if (!items.length) return '<p style="font-size:11px;color:#6e7681;margin-top:6px">No suggestions found.</p>';
  return items.map((item, i) => `
    <div style="background:#0d1117;border:1px solid #21262d;border-radius:3px;padding:8px 10px;margin-top:6px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <span style="font-size:11px;color:#e6edf3">${esc(item.id || item.name || item.channel_id || '')}</span>
        <button onclick="addDiscoveredItem(${i}, '${type}')"
          style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:1px 8px;border-radius:2px;cursor:pointer">+ Add</button>
      </div>
      ${item.rationale ? `<div style="font-size:10px;color:#6e7681">${esc(item.rationale)}</div>` : ''}
      ${type === 'topic' && item.keywords ? `<div style="font-size:10px;color:#8b949e;margin-top:2px">${esc(item.keywords.join(', '))}</div>` : ''}
    </div>
  `).join('');
}

// Store last discover results for Add button access
let _lastDiscoverResults = { topic: [], source: [] };

async function _runAndStoreTopics() {
  // Called after fetch — store results for addDiscoveredItem
}

function addDiscoveredItem(i, type) {
  const items = _lastDiscoverResults[type];
  if (!items[i]) return;
  if (type === 'topic') {
    const t = { ...items[i], _isNew: true };
    delete t.rationale;
    cfgState.topics.push(t);
    renderTopicsTable();
    markDirty('topics');
    showToast('Topic added — review and save');
  } else {
    const s = { ...items[i] };
    delete s.rationale;
    cfgState.sources.push(s);
    renderSourcesTable();
    markDirty('sources');
    showToast('Source added — review and save');
  }
}

async function loadSuggestions() {
  const data = await fetchJSON('/api/discover/suggestions');
  if (!data || (!data.topics?.length && !data.sources?.length)) return;

  // Topics suggestions
  if (data.topics?.length) {
    _lastDiscoverResults.topic = data.topics;
    $('topics-suggestions-body').innerHTML = renderDiscoverResults(data.topics, 'topic') +
      (data.generated_at ? `<div style="font-size:9px;color:#6e7681;margin-top:6px">Generated ${fmtTime(data.generated_at)}</div>` : '');
  }
  // Sources suggestions — render in sources panel
  const sourcesSugg = $('sources-suggestions-body');
  if (sourcesSugg && data.sources?.length) {
    _lastDiscoverResults.source = data.sources;
    sourcesSugg.innerHTML = renderDiscoverResults(data.sources, 'source') +
      (data.generated_at ? `<div style="font-size:9px;color:#6e7681;margin-top:6px">Generated ${fmtTime(data.generated_at)}</div>` : '');
  }
}
```

- [ ] **Step 3: Call loadSuggestions from loadConfigTab**

In `loadConfigTab`, add after `renderPromptsPanel()`:

```js
  loadSuggestions(); // async, non-blocking
```

Also update `discoverTopics` and `discoverSources` to store results in `_lastDiscoverResults` before rendering:

```js
// In discoverTopics, after const results = await r.json():
_lastDiscoverResults.topic = results;

// In discoverSources, after const results = await r.json():
_lastDiscoverResults.source = results;
```

- [ ] **Step 4: Verify in browser**

1. Open Config tab → Intelligence Sources
2. Type "OT cyber attacks energy sector" in Discover Topics box → press Enter
3. Expected: "Researching..." appears, then 3-5 suggestion cards with rationale and "+ Add" buttons
4. Click "+ Add" on one → row appears in Topics table, Save button activates
5. Run pipeline → open Config tab → Post-Run Suggestions section shows auto-generated suggestions

- [ ] **Step 5: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat: discovery search boxes + post-run suggestions in Config tab"
```

---

## Final Verification Checklist

- [ ] `uv run python tools/deep_research.py APAC geo --depth=quick` writes valid `geo_signals.json`
- [ ] `uv run python tools/discover.py topics "wind energy OT threats"` returns JSON array
- [ ] `uv run python tools/suggest_config.py` writes `output/config_suggestions.json`
- [ ] `/api/discover/topics` POST returns suggestions (requires TAVILY_API_KEY + ANTHROPIC_API_KEY)
- [ ] Config tab → Discover Topics search → results render inline with Add buttons
- [ ] Add button copies suggestion into table and marks dirty
- [ ] Post-run suggestions load automatically when Config tab opens after a pipeline run
- [ ] Deep research progress appears in Agent Activity Console during `--deep` pipeline runs
- [ ] All existing tests still pass: `uv run pytest -v`
