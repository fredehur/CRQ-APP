# Register Validator Pipeline Redesign — Implementation Plan

> **For agentic workers:** superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Haiku hallucination in `register_validator.py` with a two-phase real OSINT pipeline: Phase 1 refreshes known validated sources via targeted Tavily search, Phase 2 runs a wider register-context-aware search, with IQR outlier filtering and Sonnet-generated analyst recommendations.

**Architecture:** `register_validator.py` is a self-contained script. It gains: (1) a `_search_web()` primitive (same Tavily→DDG pattern as `vacr_researcher.py`), (2) `phase1_refresh_known_sources()` that searches known DB sources by domain, (3) `phase2_osint_search()` that builds queries from `register.company_context` + scenario tags, (4) `filter_outliers()` using IQR to remove wild benchmark values, (5) `_build_recommendation_sonnet()` that replaces template strings with a Sonnet analyst paragraph. Output schema is backwards-compatible — only `recommendation` field content changes plus a new `phase` tag on each source.

**Tech Stack:** Python `uv`, Anthropic SDK (Haiku + Sonnet), Tavily API, DuckDuckGo fallback, SQLite (`data/sources.db`).

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `tools/register_validator.py` | Full pipeline redesign — all new functions replace existing discovery logic |

No other files need changes. Output schema is backwards-compatible with `server.py` and `static/app.js`.

---

## Task 1: Add `_search_web()` primitive

**Files:**
- Modify: `tools/register_validator.py`

- [ ] **Step 1: Add imports and constants**

Add after the existing `load_dotenv()` line:

```python
import os
import sys
from urllib.parse import urlparse

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"
```

- [ ] **Step 2: Add `_search_web()` after the constants block**

```python
def _search_web(query: str, max_results: int = 5) -> list[dict]:
    """Search using Tavily if key available, else DuckDuckGo fallback."""
    tavily_key = os.environ.get("TAVILY_API_KEY", "")
    if tavily_key:
        try:
            import requests
            resp = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "max_results": max_results, "search_depth": "basic"},
                timeout=20,
            )
            results = resp.json().get("results", [])
            return [{"title": r.get("title", ""), "content": r.get("content", ""), "url": r.get("url", "")} for r in results]
        except Exception as e:
            print(f"[register_validator] Tavily failed: {e}", file=sys.stderr)
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [{"title": r.get("title", ""), "content": r.get("body", ""), "url": r.get("href", "")} for r in results]
    except Exception as e:
        print(f"[register_validator] DDG failed: {e}", file=sys.stderr)
        return []
```

- [ ] **Step 3: Smoke-test the function**

```python
# temporary test at bottom of file
if __name__ == "__main__":
    results = _search_web("ransomware cost energy sector 2024 USD", max_results=2)
    print(len(results), "results")
    for r in results:
        print(r["title"][:80])
```

Run: `uv run python tools/register_validator.py`
Expected: 2 results with titles printed, no errors.

- [ ] **Step 4: Remove the temporary test block — restore original `if __name__ == "__main__"` block**

- [ ] **Step 5: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat(validator): add _search_web Tavily+DDG primitive"
```

---

## Task 2: Add Haiku figure extractors

**Files:**
- Modify: `tools/register_validator.py`

- [ ] **Step 1: Add `_extract_financial_figures()` after `_search_web()`**

```python
_FIN_EXTRACTION_PROMPT = """\
You are extracting financial impact data from a cybersecurity industry report.

Extract all dollar-denominated financial impact figures for cyber incidents. For each figure found:
- scenario_tag: classify into one of: System intrusion, Ransomware, Accidental disclosure, Physical threat, Insider misuse, DoS attack, Scam or fraud, Defacement, System failure
- sector: the industry sector this applies to (e.g. "manufacturing", "energy", "all")
- cost_low_usd: lower bound in USD as integer (null if not stated)
- cost_median_usd: median or average in USD as integer (null if not stated)
- cost_high_usd: upper bound in USD as integer (null if not stated)
- note: brief description of what this figure represents
- raw_quote: the exact text excerpt (max 200 chars)

Return ONLY a JSON array. If no financial figures found, return [].

Text to analyze:
{raw_text}"""


def _extract_financial_figures(text: str, source_name: str) -> list[dict]:
    """Run Haiku over text to extract USD financial figures."""
    if not text.strip():
        return []
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": _FIN_EXTRACTION_PROMPT.format(raw_text=text[:10_000])}],
        )
        content = resp.content[0].text.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        figures = json.loads(content.strip())
        for f in figures:
            f["_source_name"] = source_name
        return figures
    except Exception as e:
        print(f"[register_validator] Haiku fin extraction failed ({source_name[:40]}): {e}", file=sys.stderr)
        return []
```

- [ ] **Step 2: Add `_extract_probability_figures()` immediately after**

```python
_PROB_EXTRACTION_PROMPT = """\
You are extracting incident probability data from a cybersecurity industry report.

Extract all percentage figures that represent incident frequency or probability:
- Annual incident probability (% of organizations affected per year)
- Incident frequency rates
- Prevalence rates for cyber incidents

For each figure found:
- scenario_tag: classify into one of: System intrusion, Ransomware, Accidental disclosure, Physical threat, Insider misuse, DoS attack, Scam or fraud, Defacement, System failure
- sector: the industry sector this applies to
- probability_pct: the percentage value as a float
- note: brief description of what this percentage represents
- raw_quote: the exact text excerpt (max 200 chars)

Return ONLY a JSON array. If no probability figures found, return [].

Text to analyze:
{raw_text}"""


def _extract_probability_figures(text: str, source_name: str) -> list[dict]:
    """Run Haiku over text to extract incident probability percentages."""
    if not text.strip():
        return []
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": _PROB_EXTRACTION_PROMPT.format(raw_text=text[:10_000])}],
        )
        content = resp.content[0].text.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        figures = json.loads(content.strip())
        for f in figures:
            f["_source_name"] = source_name
        return figures
    except Exception as e:
        print(f"[register_validator] Haiku prob extraction failed ({source_name[:40]}): {e}", file=sys.stderr)
        return []
```

- [ ] **Step 3: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat(validator): add Haiku financial + probability figure extractors"
```

---

## Task 3: Add `build_register_queries()`

**Files:**
- Modify: `tools/register_validator.py`

- [ ] **Step 1: Add `build_register_queries()` after the extractors**

```python
def build_register_queries(scenario: dict, register: dict) -> dict:
    """
    Build register-contextualized Tavily search queries.
    Uses company_context and search_tags to shape queries for the specific register type.
    Returns {"financial": [q1, q2, ...], "probability": [q1, q2, ...]}
    """
    name = scenario["scenario_name"]
    context = register.get("company_context", "")
    tags = scenario.get("search_tags", [])

    # Derive sector terms from tags and context
    tag_terms = " ".join(t.replace("_", " ") for t in tags if t not in ("energy_operator",))[:80]

    financial = [
        f'"{name}" average cost USD million 2024 2025 {tag_terms}',
        f'"{name}" financial impact industry report 2024 benchmark USD',
        f'"{name}" total cost incident energy sector 2024 2025',
    ]
    probability = [
        f'"{name}" annual probability percentage organizations 2024 2025',
        f'"{name}" incident rate percentage Verizon DBIR OR Dragos OR CISA 2024',
        f'"{name}" frequency rate 2024 2025 {tag_terms}',
    ]

    # OT/SCADA context: add targeted ICS queries
    ot_tags = {"ot_systems", "scada", "wind_farm", "industrial_control"}
    if ot_tags & set(tags):
        financial.append(f'"{name}" OT ICS operational technology cost USD 2024 2025')
        probability.append(f'"{name}" ICS OT incident rate 2024 Dragos OR CISA OR S4x')

    # Manufacturing context: add supply chain angle
    if "manufacturing" in context.lower():
        financial.append(f'"{name}" manufacturing plant cost USD 2024 2025')

    return {"financial": financial[:4], "probability": probability[:4]}
```

- [ ] **Step 2: Verify output looks sane**

```python
# Temporary test
if __name__ == "__main__":
    import json
    reg = json.loads(open("data/registers/wind_power_plant.json").read())
    scenario = reg["scenarios"][1]  # Ransomware
    q = build_register_queries(scenario, reg)
    for dim, queries in q.items():
        print(f"\n{dim}:")
        for query in queries:
            print(f"  {query}")
```

Run: `uv run python tools/register_validator.py`
Expected: Financial and probability queries printed, OT-specific queries included for the wind plant register.

- [ ] **Step 3: Remove the temporary test block**

- [ ] **Step 4: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat(validator): add register-contextualized query builder"
```

---

## Task 4: Add `phase1_refresh_known_sources()`

**Files:**
- Modify: `tools/register_validator.py`

This replaces `query_existing_sources()`. Instead of just tag-matching in the DB, it does a real Tavily search against the domains of known validated sources.

- [ ] **Step 1: Add `phase1_refresh_known_sources()` — delete old `query_existing_sources()` and replace**

```python
def phase1_refresh_known_sources(
    conn: sqlite3.Connection, scenario: dict
) -> tuple[list[dict], list[dict]]:
    """
    Phase 1: For each known validated source in sources.db matching this scenario's tags,
    run a targeted Tavily search to find new/updated reports from that source.
    Returns (fin_figures, prob_figures) — each item has phase=1.
    """
    search_tags = set(scenario.get("search_tags", []))
    rows = conn.execute(
        "SELECT name, url, source_tags FROM sources_registry WHERE has_quantitative_data = 1"
    ).fetchall()

    # Filter to sources whose tags overlap this scenario
    relevant = []
    for name, url, tags_json in rows:
        try:
            tags = set(json.loads(tags_json or "[]"))
        except Exception:
            tags = set()
        if tags & search_tags:
            relevant.append({"name": name, "url": url or ""})

    fin_figures, prob_figures = [], []
    for source in relevant[:5]:  # cap to avoid excessive API calls
        name = source["name"]
        url = source["url"]
        domain = urlparse(url).netloc if url else ""

        if domain:
            query = f'site:{domain} "{scenario["scenario_name"]}" 2024 2025'
        else:
            query = f'"{name}" "{scenario["scenario_name"]}" report 2024 2025'

        print(f"[register_validator] Phase 1 — {name[:50]}: {query[:70]}", file=sys.stderr)
        results = _search_web(query, max_results=3)
        for r in results:
            content = r.get("content", "")
            src_name = r.get("title") or name
            src_url = r.get("url") or url

            for fig in _extract_financial_figures(content, src_name):
                fig["phase"] = 1
                fig["source_url"] = src_url
                fin_figures.append(fig)

            for fig in _extract_probability_figures(content, src_name):
                fig["phase"] = 1
                fig["source_url"] = src_url
                prob_figures.append(fig)

    return fin_figures, prob_figures
```

- [ ] **Step 2: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat(validator): phase 1 — real Tavily search against known validated sources"
```

---

## Task 5: Add `phase2_osint_search()`

**Files:**
- Modify: `tools/register_validator.py`

This replaces `discover_new_sources()`. Uses `build_register_queries()` for register-contextual search instead of asking Haiku to recall from memory.

- [ ] **Step 1: Delete `discover_new_sources()` and add `phase2_osint_search()` in its place**

```python
def phase2_osint_search(
    scenario: dict, register: dict
) -> tuple[list[dict], list[dict]]:
    """
    Phase 2: Register-contextualized OSINT — broader Tavily search for new benchmark reports.
    Queries are shaped by register.company_context and scenario search_tags.
    Returns (fin_figures, prob_figures) — each item has phase=2.
    """
    queries = build_register_queries(scenario, register)
    fin_figures, prob_figures = [], []

    for query in queries["financial"]:
        print(f"[register_validator] Phase 2 fin — {query[:80]}", file=sys.stderr)
        results = _search_web(query, max_results=4)
        for r in results:
            content = r.get("content", "")
            src_name = r.get("title") or r.get("url", "")
            for fig in _extract_financial_figures(content, src_name):
                fig["phase"] = 2
                fig["source_url"] = r.get("url", "")
                fin_figures.append(fig)

    for query in queries["probability"]:
        print(f"[register_validator] Phase 2 prob — {query[:80]}", file=sys.stderr)
        results = _search_web(query, max_results=4)
        for r in results:
            content = r.get("content", "")
            src_name = r.get("title") or r.get("url", "")
            for fig in _extract_probability_figures(content, src_name):
                fig["phase"] = 2
                fig["source_url"] = r.get("url", "")
                prob_figures.append(fig)

    return fin_figures, prob_figures
```

- [ ] **Step 2: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat(validator): phase 2 — register-contextualized OSINT replaces Haiku hallucination"
```

---

## Task 6: Add `filter_outliers()`

**Files:**
- Modify: `tools/register_validator.py`

Fixes the WP-007 ($2.7B), WP-008 ($50 floor), WP-009 ($74B) benchmark noise from Task 5.

- [ ] **Step 1: Add `filter_outliers()` after the phase functions**

```python
def filter_outliers(values: list[float]) -> list[float]:
    """
    Remove statistical outliers using the IQR method.
    Requires at least 4 values to filter — returns input unchanged if fewer.
    Never returns an empty list.
    """
    if len(values) < 4:
        return values
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    q1 = sorted_vals[n // 4]
    q3 = sorted_vals[(3 * n) // 4]
    iqr = q3 - q1
    if iqr == 0:
        return values
    lo = q1 - 1.5 * iqr
    hi = q3 + 1.5 * iqr
    filtered = [v for v in sorted_vals if lo <= v <= hi]
    return filtered if filtered else values
```

- [ ] **Step 2: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat(validator): IQR outlier filter for benchmark ranges"
```

---

## Task 7: Add Sonnet recommendation

**Files:**
- Modify: `tools/register_validator.py`

Replaces the `_build_recommendation()` template string with a Sonnet paragraph in analyst language, incorporating register context.

- [ ] **Step 1: Delete `_build_recommendation()` and add `_build_recommendation_sonnet()`**

```python
_RECOMMENDATION_PROMPT = """\
You are a cyber risk analyst reviewing VaCR (Value at Cyber Risk) validation results.

Register context: {company_context}
Scenario: {scenario_name}
Description: {scenario_description}

Financial validation:
  - Register VaCR: ${vacr_usd:,}
  - Benchmark range from industry sources: {fin_range}
  - Verdict: {fin_verdict} ({fin_source_count} sources found)

Probability validation:
  - Register probability: {prob_pct}%
  - Benchmark range from industry sources: {prob_range}
  - Verdict: {prob_verdict} ({prob_source_count} sources found)

Write a concise analyst note (2-3 sentences) addressing:
1. Whether the register figures appear well-calibrated for this specific organisation type
2. What the benchmark evidence suggests about direction of revision, if any
3. If verdict is "insufficient", what source types would strengthen this validation

Tone: direct, no jargon, no financial advice language. Plain text only."""


def _build_recommendation_sonnet(
    scenario: dict,
    register: dict,
    fin: dict,
    prob: dict,
) -> str:
    """Generate a Sonnet analyst recommendation paragraph for this scenario."""
    def _fmt_fin_range(r):
        if not r:
            return "no benchmark data found"
        return f"${r[0]:,.0f} \u2013 ${r[1]:,.0f}"

    def _fmt_prob_range(r):
        if not r:
            return "no benchmark data found"
        return f"{r[0]:.1f}% \u2013 {r[1]:.1f}%"

    prompt = _RECOMMENDATION_PROMPT.format(
        company_context=register.get("company_context", ""),
        scenario_name=scenario["scenario_name"],
        scenario_description=scenario.get("description", ""),
        vacr_usd=fin.get("vacr_figure_usd") or 0,
        fin_range=_fmt_fin_range(fin.get("benchmark_range_usd")),
        fin_verdict=fin.get("verdict", "insufficient"),
        fin_source_count=len(fin.get("new_sources", [])),
        prob_pct=prob.get("vacr_probability_pct") or 0,
        prob_range=_fmt_prob_range(prob.get("benchmark_range_pct")),
        prob_verdict=prob.get("verdict", "insufficient"),
        prob_source_count=len(prob.get("new_sources", [])),
    )
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"[register_validator] Sonnet recommendation failed: {e}", file=sys.stderr)
        # Fallback: brief verdict string
        parts = []
        if fin.get("benchmark_range_usd"):
            r = fin["benchmark_range_usd"]
            parts.append(f"Financial {fin['verdict']}: benchmark ${r[0]:,.0f}\u2013${r[1]:,.0f} vs VaCR ${fin.get('vacr_figure_usd', 0):,.0f}.")
        else:
            parts.append("Insufficient financial benchmark sources.")
        if prob.get("benchmark_range_pct"):
            r = prob["benchmark_range_pct"]
            parts.append(f"Probability {prob['verdict']}: benchmark {r[0]:.1f}\u2013{r[1]:.1f}% vs {prob.get('vacr_probability_pct', 0)}%.")
        else:
            parts.append("Insufficient probability benchmark sources.")
        return " ".join(parts)
```

- [ ] **Step 2: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat(validator): Sonnet analyst recommendation replaces template strings"
```

---

## Task 8: Rewrite `validate_scenario()` and `main()`

**Files:**
- Modify: `tools/register_validator.py`

Wires up all new functions. Existing `compute_verdict()` and `_parse_usd()` / `_parse_pct()` helpers are kept unchanged.

- [ ] **Step 1: Replace `validate_scenario()` with the two-phase version**

```python
def validate_scenario(
    conn: sqlite3.Connection,
    scenario: dict,
    register: dict,
) -> dict:
    """
    Full two-phase validation for one scenario.
    Phase 1: known sources in sources.db → Tavily site-search refresh.
    Phase 2: register-contextualized OSINT → broader Tavily search.
    """
    # --- Phase 1 ---
    p1_fin, p1_prob = phase1_refresh_known_sources(conn, scenario)

    # --- Phase 2 ---
    p2_fin, p2_prob = phase2_osint_search(scenario, register)

    # --- Combine and extract scalar values ---
    all_fin_figs = p1_fin + p2_fin
    all_prob_figs = p1_prob + p2_prob

    fin_values: list[float] = []
    for f in all_fin_figs:
        # Prefer cost_median_usd; fall back to cost_low/high average
        val = f.get("cost_median_usd") or (
            (f.get("cost_low_usd", 0) or 0 + f.get("cost_high_usd", 0) or 0) / 2
        ) or None
        if val:
            fin_values.append(float(val))

    prob_values: list[float] = []
    for f in all_prob_figs:
        val = f.get("probability_pct")
        if val:
            prob_values.append(float(val))

    # --- Outlier filter ---
    fin_values = filter_outliers(fin_values)
    prob_values = filter_outliers(prob_values)

    # --- Verdicts ---
    vacr_usd = scenario.get("value_at_cyber_risk_usd")
    vacr_pct = scenario.get("probability_pct")

    fin_verdict, fin_range = compute_verdict(vacr_usd, fin_values)
    prob_verdict, prob_range = compute_verdict(vacr_pct, prob_values)

    # Normalise sources for output (deduplicate by source name, keep phase tag)
    seen_fin, seen_prob = set(), set()
    fin_sources_out, prob_sources_out = [], []
    for f in all_fin_figs:
        key = f.get("_source_name", "")[:60]
        if key not in seen_fin:
            seen_fin.add(key)
            fin_sources_out.append({
                "name": f.get("_source_name", ""),
                "url": f.get("source_url", ""),
                "figure_usd": f.get("cost_median_usd"),
                "note": f.get("note", ""),
                "raw_quote": f.get("raw_quote", ""),
                "phase": f.get("phase", 2),
            })
    for f in all_prob_figs:
        key = f.get("_source_name", "")[:60]
        if key not in seen_prob:
            seen_prob.add(key)
            prob_sources_out.append({
                "name": f.get("_source_name", ""),
                "url": f.get("source_url", ""),
                "figure_pct": f.get("probability_pct"),
                "note": f.get("note", ""),
                "raw_quote": f.get("raw_quote", ""),
                "phase": f.get("phase", 2),
            })

    fin_result = {
        "vacr_figure_usd": vacr_usd,
        "verdict": fin_verdict,
        "benchmark_range_usd": fin_range,
        "existing_sources": [],   # phase 1 results are now in new_sources with phase=1
        "new_sources": fin_sources_out,
        "recommendation": "",     # filled below after Sonnet call
    }
    prob_result = {
        "vacr_probability_pct": vacr_pct,
        "verdict": prob_verdict,
        "benchmark_range_pct": prob_range,
        "existing_sources": [],
        "new_sources": prob_sources_out,
        "recommendation": "",
    }

    # --- Sonnet recommendation (one call covering both dimensions) ---
    recommendation = _build_recommendation_sonnet(scenario, register, fin_result, prob_result)
    fin_result["recommendation"] = recommendation
    prob_result["recommendation"] = recommendation  # same text; UI shows whichever it reads

    return {
        "scenario_id": scenario["scenario_id"],
        "scenario_name": scenario["scenario_name"],
        "financial": fin_result,
        "probability": prob_result,
    }
```

- [ ] **Step 2: Update `main()` to pass `register` to `validate_scenario()`**

```python
def main():
    register = load_active_register()
    conn = sqlite3.connect(str(DB_PATH))

    print(f"[register_validator] Active register: {register['register_id']}")
    print(f"[register_validator] Context: {register.get('company_context', '')[:80]}")
    print(f"[register_validator] Scenarios: {len(register['scenarios'])}")

    scenario_results = []
    for scenario in register["scenarios"]:
        print(f"[register_validator] Validating: {scenario['scenario_id']} - {scenario['scenario_name']}")
        result = validate_scenario(conn, scenario, register)
        scenario_results.append(result)
        fin_v = result["financial"]["verdict"]
        prob_v = result["probability"]["verdict"]
        print(f"  -> financial: {fin_v}  probability: {prob_v}")

    output = {
        "register_id": register["register_id"],
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": scenario_results,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    register["last_validated_at"] = output["validated_at"]
    reg_path = REGISTERS_DIR / f"{register['register_id']}.json"
    reg_path.write_text(json.dumps(register, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[register_validator] Done -> {OUTPUT_PATH}")
    conn.close()
```

- [ ] **Step 3: Run the full pipeline**

```bash
uv run python tools/register_validator.py 2>&1
```

Expected output:
```
[register_validator] Active register: wind_power_plant
[register_validator] Context: Pure wind power plant operator...
[register_validator] Scenarios: 9
[register_validator] Validating: WP-001 - System intrusion
[register_validator] Phase 1 — ...
[register_validator] Phase 2 fin — ...
[register_validator] Phase 2 prob — ...
  -> financial: supports|challenges|insufficient  probability: supports|challenges|insufficient
...
[register_validator] Done -> ...output/validation/register_validation.json
```

No Python errors. File written. Check output has `recommendation` populated for each scenario.

- [ ] **Step 4: Verify outlier filtering worked**

```bash
python -c "
import json
data = json.loads(open('output/validation/register_validation.json').read())
for s in data['scenarios']:
    fin = s['financial']
    prob = s['probability']
    fin_range = fin.get('benchmark_range_usd', [])
    prob_range = prob.get('benchmark_range_pct', [])
    print(f\"{s['scenario_id']} {s['scenario_name']:<22} | fin: {fin['verdict']:<14} range: {[round(v) for v in fin_range]} | prob: {prob['verdict']:<14} range: {prob_range}\")
"
```

Expected: No benchmark_range_usd entry exceeds 3× the median of the range. No single-scenario range spanning orders of magnitude (like [$50, $74B]).

- [ ] **Step 5: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat(validator): two-phase OSINT pipeline — real web search, outlier filter, Sonnet recommendations"
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task |
|---|---|
| Search existing validated sources for new reports | T4 `phase1_refresh_known_sources` |
| Wider OSINT search for new reports | T5 `phase2_osint_search` |
| Register context shapes queries (wind plant vs. enterprise) | T3 `build_register_queries` — uses `company_context` + `search_tags` |
| No Haiku hallucination — real Tavily search only | T1 `_search_web`, T4, T5 |
| Outlier filter | T6 `filter_outliers` |
| Analyst-language recommendation | T7 `_build_recommendation_sonnet` |
| CRQ principles (no fabrication, source attribution, register context) | T3 query context + T7 Sonnet prompt uses company_context |
| Output schema backwards-compatible | T8 — all existing fields preserved, `phase` tag added |

**Placeholder scan:** None found — all steps contain complete code.

**Type consistency:** `validate_scenario(conn, scenario, register)` signature used consistently in T8 main(). `phase1` and `phase2` both return `tuple[list[dict], list[dict]]`.
