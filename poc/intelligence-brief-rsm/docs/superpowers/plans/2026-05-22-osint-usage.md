# OSINT Smart Enrichment — Implementation Plan

> **Execution:** Built via the `/prime-dev` blueprint — the orchestrator (Opus) owns ALL Bash (runs every test and check); Builders (Sonnet, no Bash) write files and report `files_written` + `verify` commands; a Validator (Sonnet, read-only) checks each unit against this plan and the spec before acceptance. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the OSINT physical collector into a smart, low-noise layer (geographic queries → Firecrawl scrape w/ truncated excerpt → one Haiku enrichment pass that drops noise, summarizes, and proposes Seerist corroboration) and wire the enriched signals into the manifest + analyst prompt.

**Architecture:** All collection-side logic lives in `tools/osint_physical_collector.py` as small pure helpers (query map, truncation, seerist-event load, enrichment-apply) plus one Anthropic call; `build_rsm_inputs` inlines the result into the manifest; the analyst prompt is told to consume it. Severity/section-routing stay with the analyst (single judgment layer).

**Tech Stack:** Python 3.11 + uv, `anthropic` (Haiku 4.5), `tavily-python`, `firecrawl-py` v4, pytest. LLM/network calls are mocked in unit tests.

Spec: `docs/superpowers/specs/2026-05-22-osint-usage-design.md`. All paths relative to `poc/seerist-rsm/`; commands run from there. Local test runner is `python -m pytest` (the project venv; `uv run` re-syncs and can fail behind a proxy).

---

## File structure

- `tools/osint_physical_collector.py` — add: `REGION_QUERY_TERMS`, `_geo_terms`, `_build_queries`, `_truncate`, `_load_seerist_events`, `_call_llm`, `_enrich`, `_apply_enrichment`; rewrite `_live_collect` to chain them; add `ANTHROPIC_API_KEY` to `REQUIRED_LIVE_KEYS`.
- `tools/rsm_input_builder.py` — inline enriched OSINT into the manifest + a `manifest_summary` line.
- `tools/poc_runner.py` — add `ANTHROPIC_API_KEY` to the `--osint --require-live` guard.
- `prompts/rsm_regional_analyst_daily.md` — typed-input row + routing instructions.
- `.env.example`, `.github/prompts/setup.prompt.md`, `README.md` — ANTHROPIC required for OSINT.
- `tests/test_osint_enrichment.py` — new unit tests (LLM/network mocked).

---

## Task 1: Geographic query construction

**Files:**
- Modify: `tools/osint_physical_collector.py`
- Test: `tests/test_osint_enrichment.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_osint_enrichment.py
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import osint_physical_collector as opc  # noqa: E402


def test_geo_terms_maps_code_to_geography():
    assert "Mediterranean" in opc._geo_terms("MED")
    assert opc._geo_terms("med") == opc._geo_terms("MED")


def test_build_queries_use_geo_not_raw_code():
    qs = opc._build_queries("MED")
    assert len(qs) == 4
    # the raw region code must NOT appear as a standalone query token
    assert all("Mediterranean" in q for q in qs)
    assert not any(q.startswith("MED ") for q in qs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_osint_enrichment.py -k "geo or build_queries" -q`
Expected: FAIL — `AttributeError: module 'tools.osint_physical_collector' has no attribute '_geo_terms'`.

- [ ] **Step 3: Write minimal implementation**

Add near the top of `tools/osint_physical_collector.py` (after the constants block, e.g. after `FIXTURES_DIR = ...`):

```python
REGION_QUERY_TERMS = {
    "MED": "Mediterranean (Italy, Spain, Greece, Turkey, Morocco, Egypt)",
    "APAC": "Asia-Pacific",
    "AME": "Africa and Middle East",
    "LATAM": "Latin America",
    "NCE": "Northern and Central Europe",
}
_OSINT_TOPICS = [
    "unrest protest",
    "armed conflict terrorism",
    "maritime shipping disruption",
    "natural disaster",
]


def _geo_terms(region: str) -> str:
    return REGION_QUERY_TERMS.get(region.upper(), region)


def _build_queries(region: str) -> list[str]:
    geo = _geo_terms(region)
    return [f"{geo} {topic} 2026" for topic in _OSINT_TOPICS]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_osint_enrichment.py -k "geo or build_queries" -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/osint_physical_collector.py tests/test_osint_enrichment.py
git commit -m "feat(osint): geographic query construction (kills MED->medical noise)"
```

---

## Task 2: Excerpt truncation

**Files:**
- Modify: `tools/osint_physical_collector.py`
- Test: `tests/test_osint_enrichment.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_osint_enrichment.py
def test_truncate_short_text_unchanged():
    assert opc._truncate("hello", 100) == "hello"
    assert opc._truncate("", 100) == ""
    assert opc._truncate(None, 100) == ""


def test_truncate_long_text_middle_elided_and_capped():
    text = "A" * 5000 + "B" * 5000
    out = opc._truncate(text, 1000)
    assert len(out) <= 1000 + 40  # cap + marker slack
    assert out.startswith("A") and out.endswith("B")
    assert "truncated" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_osint_enrichment.py -k truncate -q`
Expected: FAIL — no attribute `_truncate`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to tools/osint_physical_collector.py
def _truncate(text: str | None, max_chars: int = 3000) -> str:
    """Middle-truncate scraped content so the enrichment LLM call cannot blow
    past context/cost. Mirrors firecrawl_scraper._truncate in the parent repo."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n…[truncated]…\n" + text[-half:]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_osint_enrichment.py -k truncate -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/osint_physical_collector.py tests/test_osint_enrichment.py
git commit -m "feat(osint): middle-truncate excerpts before the LLM call"
```

---

## Task 3: Seerist-events loader + availability flag

**Files:**
- Modify: `tools/osint_physical_collector.py`
- Test: `tests/test_osint_enrichment.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_osint_enrichment.py
def test_load_seerist_events_present(tmp_path):
    reg = tmp_path / "regional" / "med"
    reg.mkdir(parents=True)
    (reg / "seerist_signals.json").write_text(json.dumps({
        "situational": {"events": [
            {"signal_id": "seerist:event:med-0043", "title": "Port strike", "category": "Labour"}
        ]}
    }), encoding="utf-8")
    events, unavailable = opc._load_seerist_events("MED", output_root=tmp_path)
    assert unavailable is False
    assert events[0]["signal_id"] == "seerist:event:med-0043"
    assert events[0]["category"] == "Labour"


def test_load_seerist_events_absent(tmp_path):
    events, unavailable = opc._load_seerist_events("MED", output_root=tmp_path)
    assert unavailable is True
    assert events == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_osint_enrichment.py -k load_seerist -q`
Expected: FAIL — no attribute `_load_seerist_events`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to tools/osint_physical_collector.py
def _load_seerist_events(region: str, output_root: Path | None = None) -> tuple[list[dict], bool]:
    """Return (events, seerist_unavailable). events is a compact list for the
    enrichment prompt's corroboration step. Absent file → ([], True)."""
    root = output_root or OUTPUT_ROOT
    path = root / "regional" / region.lower() / "seerist_signals.json"
    if not path.exists():
        return [], True
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [], True
    events = [
        {
            "signal_id": e.get("signal_id", ""),
            "title": e.get("title", ""),
            "category": e.get("category", ""),
        }
        for e in doc.get("situational", {}).get("events", [])
    ]
    return events, False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_osint_enrichment.py -k load_seerist -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/osint_physical_collector.py tests/test_osint_enrichment.py
git commit -m "feat(osint): seerist-events loader + unavailable flag"
```

---

## Task 4: Apply enrichment verdicts (pure)

**Files:**
- Modify: `tools/osint_physical_collector.py`
- Test: `tests/test_osint_enrichment.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_osint_enrichment.py
def test_apply_enrichment_keeps_relevant_drops_rest():
    scraped = [
        {"title": "Hormuz shipping disruption", "url": "http://a", "source": "http://a",
         "published_date": "2026-05-20", "content": "body A"},
        {"title": "US Medicare 2026 plans", "url": "http://b", "source": "http://b",
         "published_date": "", "content": "body B"},
    ]
    verdicts = [
        {"index": 0, "relevant": True, "relevance_reason": "MED maritime",
         "summary": "Hormuz disruption reroutes MED freight.", "corroborates_event": None},
        {"index": 1, "relevant": False, "relevance_reason": "US Medicare, not MED physical risk"},
    ]
    signals, dropped = opc._apply_enrichment("MED", scraped, verdicts)
    assert len(signals) == 1 and len(dropped) == 1
    s = signals[0]
    assert s["signal_id"] == "osint:physical:med-001"
    assert s["summary"].startswith("Hormuz")
    assert s["content_excerpt"] == "body A"
    assert s["corroborates_event"] is None
    assert dropped[0]["url"] == "http://b" and "Medicare" in dropped[0]["relevance_reason"]


def test_apply_enrichment_missing_verdict_drops_item():
    scraped = [{"title": "x", "url": "http://x", "source": "", "published_date": "", "content": "c"}]
    signals, dropped = opc._apply_enrichment("MED", scraped, [])
    assert signals == [] and len(dropped) == 1


def test_apply_enrichment_corroboration_link_preserved():
    scraped = [{"title": "Casablanca port strike confirmed", "url": "http://c", "source": "http://c",
                "published_date": "", "content": "c"}]
    verdicts = [{"index": 0, "relevant": True, "relevance_reason": "MED",
                 "summary": "Confirms Casablanca port strike.",
                 "corroborates_event": "seerist:event:med-0043"}]
    signals, _ = opc._apply_enrichment("MED", scraped, verdicts)
    assert signals[0]["corroborates_event"] == "seerist:event:med-0043"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_osint_enrichment.py -k apply_enrichment -q`
Expected: FAIL — no attribute `_apply_enrichment`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to tools/osint_physical_collector.py
def _apply_enrichment(region: str, scraped: list[dict], verdicts: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split scraped items into kept signals (relevant) and dropped items, using
    the LLM verdicts (keyed by index). Re-numbers kept signal_ids 001..N."""
    by_index = {v.get("index"): v for v in verdicts}
    signals: list[dict] = []
    dropped: list[dict] = []
    seq = 0
    for i, item in enumerate(scraped):
        v = by_index.get(i, {"relevant": False, "relevance_reason": "no enrichment verdict"})
        if not v.get("relevant"):
            dropped.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "relevance_reason": v.get("relevance_reason", ""),
            })
            continue
        seq += 1
        signals.append({
            "signal_id": f"osint:physical:{region.lower()}-{seq:03d}",
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "outlet": item.get("source", ""),
            "published_at": item.get("published_date", ""),
            "content_excerpt": item.get("content", ""),
            "summary": v.get("summary", ""),
            "corroborates_event": v.get("corroborates_event"),
            "pillar": "physical",
            "category": "physical",
        })
    return signals, dropped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_osint_enrichment.py -k apply_enrichment -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/osint_physical_collector.py tests/test_osint_enrichment.py
git commit -m "feat(osint): apply enrichment verdicts -> signals + dropped"
```

---

## Task 5: LLM call + enrichment prompt (Anthropic Haiku)

**Files:**
- Modify: `tools/osint_physical_collector.py`
- Test: `tests/test_osint_enrichment.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_osint_enrichment.py
def test_call_llm_strips_fences_and_parses(monkeypatch):
    import types
    captured = {}

    class FakeBlock:
        text = "```json\n{\"items\": [{\"index\": 0, \"relevant\": true}]}\n```"

    class FakeResp:
        content = [FakeBlock()]

    class FakeMessages:
        def create(self, **kw):
            captured.update(kw)
            return FakeResp()

    class FakeClient:
        def __init__(self, *a, **k):
            self.messages = FakeMessages()

    fake = types.ModuleType("anthropic")
    fake.Anthropic = FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    out = opc._call_llm("prompt text")
    assert out == {"items": [{"index": 0, "relevant": True}]}
    assert captured["model"] == "claude-haiku-4-5-20251001"


def test_call_llm_bad_json_raises(monkeypatch):
    import types

    class FakeBlock:
        text = "not json"

    class FakeResp:
        content = [FakeBlock()]

    class FakeClient:
        def __init__(self, *a, **k):
            self.messages = type("M", (), {"create": lambda self, **kw: FakeResp()})()

    fake = types.ModuleType("anthropic")
    fake.Anthropic = FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    with pytest.raises(ValueError, match="non-JSON"):
        opc._call_llm("prompt")


def test_enrich_builds_prompt_with_events_and_items(monkeypatch):
    captured = {}
    monkeypatch.setattr(opc, "_call_llm", lambda prompt, **k: captured.update(prompt=prompt) or {"items": [{"index": 0, "relevant": True, "summary": "s"}]})
    scraped = [{"title": "Hormuz", "url": "http://a", "content": "body"}]
    events = [{"signal_id": "seerist:event:med-0043", "title": "Port strike", "category": "Labour"}]
    items = opc._enrich("MED", scraped, events)
    assert items[0]["index"] == 0
    assert "seerist:event:med-0043" in captured["prompt"]
    assert "Hormuz" in captured["prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_osint_enrichment.py -k "call_llm or enrich_builds" -q`
Expected: FAIL — no attribute `_call_llm`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to tools/osint_physical_collector.py
import re as _re  # module-level; place with the other imports


def _call_llm(prompt: str, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 2048) -> dict:
    """One Anthropic call; strip markdown fences; parse JSON. Mirrors the parent
    osint_collector._call_llm. Raises ValueError on non-JSON."""
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    text = _re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=_re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"enrichment LLM returned non-JSON: {text[:200]!r}") from exc


def _enrich(region: str, scraped: list[dict], seerist_events: list[dict]) -> list[dict]:
    """Build the enrichment prompt (truncated items + seerist events) and return
    the per-item verdicts list."""
    items_txt = "\n\n".join(
        f"[{i}] {it.get('title', '')} ({it.get('url', '')})\n{it.get('content', '')[:1500]}"
        for i, it in enumerate(scraped)
    ) or "(no items)"
    ev_txt = "\n".join(
        f"- {e['signal_id']}: {e['title']} ({e['category']})" for e in (seerist_events or [])
    ) or "(none available)"
    geo = _geo_terms(region)
    prompt = f"""You are filtering OSINT physical-risk search results for the {region} region ({geo}).

SEERIST EVENTS TODAY (for corroboration):
{ev_txt}

OSINT ITEMS (index, title, url, content excerpt):
{items_txt}

For EACH item, decide if it is genuinely relevant to {region} PHYSICAL risk
(unrest, armed conflict/terrorism, maritime/shipping disruption, natural
disaster affecting the region). Drop items that are off-region or off-topic
(e.g. US-domestic, healthcare/Medicare, generic explainers).

Return ONLY JSON (no markdown fences):
{{"items": [
  {{"index": <int>, "relevant": <bool>, "relevance_reason": "<short>",
    "summary": "<1-2 sentence factual summary of the item body>",
    "corroborates_event": "<a SEERIST signal_id from the list above that this item supports, or null>"}}
]}}
Include one object per OSINT item index. summary/corroborates_event may be omitted when relevant is false."""
    result = _call_llm(prompt)
    return result.get("items", [])
```

Also ensure `import re as _re` sits with the existing imports at the top of the file (move it up if the linter prefers; it must be importable at module load).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_osint_enrichment.py -k "call_llm or enrich_builds" -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/osint_physical_collector.py tests/test_osint_enrichment.py
git commit -m "feat(osint): Haiku enrichment call + prompt"
```

---

## Task 6: Chain it in `_live_collect` + ANTHROPIC key guard

**Files:**
- Modify: `tools/osint_physical_collector.py`
- Test: `tests/test_osint_enrichment.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_osint_enrichment.py
def test_live_collect_chains_search_scrape_enrich(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    # seerist events present
    reg = tmp_path / "regional" / "med"; reg.mkdir(parents=True)
    (reg / "seerist_signals.json").write_text(json.dumps({"situational": {"events": []}}), encoding="utf-8")
    # stub search + scrape + enrich (no network/LLM)
    monkeypatch.setattr(opc, "_tavily_search", lambda q, max_results=5: [
        {"title": "Hormuz disruption", "url": "http://a", "source": "http://a", "published_date": "", "summary": ""}
    ])
    monkeypatch.setattr(opc, "_firecrawl_extract", lambda url: {"content": "C" * 9000, "location": {}})
    monkeypatch.setattr(opc, "_enrich", lambda region, scraped, events: [
        {"index": i, "relevant": (i == 0), "relevance_reason": "r", "summary": "Hormuz reroute.", "corroborates_event": None}
        for i in range(len(scraped))
    ])
    data = opc._live_collect("MED")
    assert data["pillar"] == "physical"
    assert data["seerist_unavailable"] is False
    assert len(data["signals"]) >= 1
    assert data["signals"][0]["signal_id"].startswith("osint:physical:med-")
    # excerpt is truncated, not the full 9000 chars
    assert len(data["signals"][0]["content_excerpt"]) <= 3100
    assert "dropped_count" in data
    # dropped audit file written
    assert (tmp_path / "regional" / "med" / "osint_dropped.json").exists()


def test_collect_require_live_needs_anthropic(tmp_path, monkeypatch):
    monkeypatch.setattr(opc, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setenv("TAVILY_API_KEY", "t")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "f")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        opc.collect("MED", require_live=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_osint_enrichment.py -k "live_collect_chains or require_live_needs_anthropic" -q`
Expected: FAIL — current `_live_collect` has no enrichment / `REQUIRED_LIVE_KEYS` lacks ANTHROPIC.

- [ ] **Step 3: Write minimal implementation**

Replace the body of `_live_collect` (the queries loop + return) with the chained version, and write the dropped file:

```python
def _live_collect(region: str) -> dict:
    """Search (geo queries) -> scrape (truncated excerpt) -> Haiku enrichment.
    Region-keyed, safe in both org-grounded and region-guided runs."""
    scraped: list[dict] = []
    for q in _build_queries(region):
        hits = _tavily_search(q, max_results=5)
        for hit in hits:
            try:
                extracted = _firecrawl_extract(hit.get("url", ""))
            except Exception as e:
                print(f"[osint_physical] extract failed for {hit.get('url', '')} — {e}", file=sys.stderr)
                continue
            if not extracted:
                continue
            scraped.append({
                "title": hit.get("title", ""),
                "url": hit.get("url", ""),
                "source": hit.get("source", ""),
                "published_date": hit.get("published_date", ""),
                "content": _truncate(extracted.get("content", "")),
                "location": extracted.get("location") or {},
            })

    seerist_events, seerist_unavailable = _load_seerist_events(region)
    verdicts = _enrich(region, scraped, seerist_events) if scraped else []
    signals, dropped = _apply_enrichment(region, scraped, verdicts)

    # dropped-items audit trail (so over-aggressive filtering is visible)
    out_dir = OUTPUT_ROOT / "regional" / region.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "osint_dropped.json").write_text(
        json.dumps({"region": region, "dropped": dropped}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "region": region,
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pillar": "physical",
        "seerist_unavailable": seerist_unavailable,
        "dropped_count": len(dropped),
        "signals": signals,
        "source_provenance": "tavily+firecrawl+haiku",
    }
```

Then extend the key guard — change the `REQUIRED_LIVE_KEYS` constant:

```python
REQUIRED_LIVE_KEYS = ("TAVILY_API_KEY", "FIRECRAWL_API_KEY", "ANTHROPIC_API_KEY")
```

(The existing `collect()` guard already iterates `REQUIRED_LIVE_KEYS` and raises `ValueError` listing the missing ones — no other change needed there.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_osint_enrichment.py -q`
Expected: PASS (all osint-enrichment tests).

- [ ] **Step 5: Commit**

```bash
git add tools/osint_physical_collector.py tests/test_osint_enrichment.py
git commit -m "feat(osint): chain search->scrape->enrich; require ANTHROPIC live"
```

---

## Task 7: poc_runner `--osint` ANTHROPIC guard

**Files:**
- Modify: `tools/poc_runner.py`

- [ ] **Step 1: Update the guard**

In `tools/poc_runner.py`, find the OSINT key guard inside `phase_collect` (the block that checks `("TAVILY_API_KEY", "FIRECRAWL_API_KEY")` when `osint and require_live`). Replace that tuple so it reads:

```python
            _missing = [k for k in ("TAVILY_API_KEY", "FIRECRAWL_API_KEY", "ANTHROPIC_API_KEY") if not os.environ.get(k)]
```

(The surrounding `if osint:` / `if require_live:` / `raise SystemExit(...)` lines stay; only the key tuple changes. The message text already interpolates `_missing`.)

- [ ] **Step 2: Verify it compiles**

Run: `python -m py_compile tools/poc_runner.py && echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add tools/poc_runner.py
git commit -m "feat(osint): poc_runner --osint guard requires ANTHROPIC_API_KEY"
```

---

## Task 8: Inline enriched OSINT into the manifest

**Files:**
- Modify: `tools/rsm_input_builder.py`
- Test: `tests/test_osint_enrichment.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_osint_enrichment.py
from tools.rsm_input_builder import build_rsm_inputs, manifest_summary  # noqa: E402


def _seed(output_dir: Path, region: str = "med"):
    reg = output_dir / "regional" / region
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "osint_signals.json").write_text("{}", encoding="utf-8")
    (reg / "data.json").write_text("{}", encoding="utf-8")
    return reg


def test_builder_inlines_osint(tmp_path):
    reg = _seed(tmp_path)
    (reg / "osint_physical_signals.json").write_text(json.dumps({
        "pillar": "physical", "seerist_unavailable": False, "dropped_count": 2,
        "signals": [{"signal_id": "osint:physical:med-001", "summary": "Hormuz reroute.",
                     "corroborates_event": "seerist:event:med-0043"}],
    }), encoding="utf-8")
    m = build_rsm_inputs("MED", "daily", output_dir=str(tmp_path))
    assert isinstance(m.get("osint_physical"), dict)
    assert m["osint_physical"]["signals"][0]["signal_id"] == "osint:physical:med-001"
    summary = manifest_summary(m)
    assert "OSINT physical" in summary


def test_builder_osint_absent_is_none(tmp_path):
    _seed(tmp_path)
    m = build_rsm_inputs("MED", "daily", output_dir=str(tmp_path))
    assert m.get("osint_physical") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_osint_enrichment.py -k builder -q`
Expected: FAIL — manifest has no `osint_physical` inlined key.

- [ ] **Step 3: Write minimal implementation**

In `tools/rsm_input_builder.py`, the function already computes `osint_physical_path = base / "osint_physical_signals.json"` and lists it in `optional`. Add an inline load next to where `poi_proximity` is loaded (search for `poi_proximity = _load_json(`), mirroring it:

```python
    # ── OSINT physical inline (if present) ───────────────────────────────────
    osint_physical = _load_json(osint_physical_path) if osint_physical_path.exists() else None
```

Add `"osint_physical": osint_physical,` to the returned dict (next to `"poi_proximity": poi_proximity,`).

Then in `manifest_summary`, after the POI proximity block, add:

```python
    op = manifest.get("osint_physical")
    if isinstance(op, dict):
        sigs = op.get("signals", []) or []
        corr = sum(1 for s in sigs if s.get("corroborates_event"))
        lines.append(
            f"\nOSINT physical: {len(sigs)} signal(s) "
            f"({corr} corroborating Seerist; {op.get('dropped_count', 0)} dropped)"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_osint_enrichment.py -k builder -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/rsm_input_builder.py tests/test_osint_enrichment.py
git commit -m "feat(osint): inline enriched OSINT into the manifest + summary"
```

---

## Task 9: Wire the analyst prompt + update docs

**Files:**
- Modify: `prompts/rsm_regional_analyst_daily.md`
- Modify: `.env.example`, `.github/prompts/setup.prompt.md`, `README.md`

- [ ] **Step 1: Analyst prompt — add the typed input + routing**

In `prompts/rsm_regional_analyst_daily.md`, add a row to the typed-inputs table (the one listing MANIFEST_PATH / SIGNALS_PATH):

```
| OSINT (in manifest) | inlined | MANIFEST_PATH → `osint_physical` — enriched web/news signals: each has `signal_id`, `summary`, `corroborates_event` (a Seerist signal_id or null) |
```

Then add a section after the "Authoritative POI source" section:

```markdown
## OSINT physical pillar — manifest `osint_physical`

When the manifest has `osint_physical.signals`, use them (already noise-filtered
and summarized — read `summary`, not the raw page):

- **Macro / strategic context** — fold region-wide items (e.g. shipping/maritime
  disruption) into SITUATION and PHYSICAL & GEOPOLITICAL.
- **Corroboration** — if an item has `corroborates_event` set, you MAY cite it
  alongside that Seerist event and raise confidence/Admiralty accordingly.
- **Early warning** — route genuinely emerging items to the EARLY WARNING pillar.

Cite OSINT items by their `signal_id` (e.g. `osint:physical:med-001`) in a
claim's `signal_ids` — they flow into the APPENDIX like Seerist signals. YOU
assign severity and decide the section; the collector does not. If
`osint_physical.seerist_unavailable` is true, corroboration was not attempted —
do not infer absence of overlap.
```

- [ ] **Step 2: Docs — promote ANTHROPIC to OSINT-required**

In `.env.example`, move/relabel `ANTHROPIC_API_KEY` so it reads:

```
# ── REQUIRED IF YOU USE OSINT MODE ─────────────────────────────────────────
# OSINT enrichment (relevance filtering + summaries) uses Anthropic Haiku.
# Required together with TAVILY/FIRECRAWL whenever OSINT is on; the run fails
# loudly if absent. Not needed if you never use OSINT.
ANTHROPIC_API_KEY=
```

In `.github/prompts/setup.prompt.md`, update the OSINT note in the verify-keys step (step 4) to say OSINT requires `TAVILY_API_KEY` + `FIRECRAWL_API_KEY` **+ `ANTHROPIC_API_KEY`** (enrichment), all three or OSINT runs fail loudly.

In `README.md`, in the "Run it in GitHub Copilot" step-2 row and the OSINT blockquote, add `ANTHROPIC_API_KEY` to the OSINT key set ("OSINT enrichment needs Tavily + Firecrawl + Anthropic keys").

- [ ] **Step 3: Static check**

Run:
```bash
python -c "
t=open('prompts/rsm_regional_analyst_daily.md',encoding='utf-8').read()
assert 'osint_physical' in t and 'corroborates_event' in t, 'analyst prompt not wired'
for f in ('.env.example','.github/prompts/setup.prompt.md','README.md'):
    assert 'ANTHROPIC' in open(f,encoding='utf-8').read(), f
print('docs + prompt wired OK')
"
```
Expected: `docs + prompt wired OK`.

- [ ] **Step 4: Commit**

```bash
git add prompts/rsm_regional_analyst_daily.md .env.example .github/prompts/setup.prompt.md README.md
git commit -m "feat(osint): wire analyst prompt to consume OSINT; ANTHROPIC required for OSINT"
```

---

## Task 10: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the OSINT enrichment suite**

Run: `python -m pytest tests/test_osint_enrichment.py -q`
Expected: PASS (all).

- [ ] **Step 2: No regressions in truststore-independent tests**

Run: `python -m pytest tests/test_osint_enrichment.py tests/test_osint_physical.py tests/test_crq_run.py tests/test_no_org_context.py tests/test_validate_brief.py tests/test_render_brief_html.py tests/test_normalize_citations.py tests/test_seerist_collector.py -q`
Expected: PASS (all). (`test_seerist_*` files importing `seerist_client` still fail only on the missing `truststore`/`anthropic` deps locally — that is the pre-existing environment gap, not this change; do not include them in this gate.)

- [ ] **Step 3: Compile the modified tools**

Run: `python -m py_compile tools/osint_physical_collector.py tools/rsm_input_builder.py tools/poc_runner.py && echo OK`
Expected: `OK`.

- [ ] **Step 4: Final commit (if any fixups)**

```bash
git add -A && git commit -m "test(osint): verify enrichment + manifest wiring" || echo "nothing to commit"
```

---

## Notes for the implementer

- **No live run in CI/authoring env**: enrichment, Tavily, and Firecrawl are network/LLM; every test mocks them (`_tavily_search`, `_firecrawl_extract`, `_enrich`/`_call_llm`, the `anthropic` module). Never call them live in tests.
- **Severity/role stay with the analyst** — do NOT add `severity` or `role` fields to the collector output. The collector emits `summary` + `corroborates_event` only.
- **`_re` import**: ensure `import re` (aliased `_re` to avoid clashing if `re` is used elsewhere) is at module top, not inside `_call_llm`, so module load is clean.
- The live end-to-end check (real keys) is the operator acceptance step, per the spec.
