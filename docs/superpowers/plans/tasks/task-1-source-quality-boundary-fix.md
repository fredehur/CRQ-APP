# Task 1 — Source Quality Boundary Fix
**Assigned to:** Session A
**Blocks:** Task 2 (must complete before Task 2 starts)
**Blocked by:** Nothing — start immediately
**Master plan:** `docs/superpowers/plans/2026-04-05-master-build-plan.md`

---

## What You Are Building

Move `source_quality` computation out of the regional analyst agent (boundary violation) into deterministic Python code. URL pattern matching and arithmetic are code territory — not agent territory.

The analyst agent currently has a "Deriving `source_quality` counts" block that instructs it to scan signal URLs, classify tiers, count uniques, and write `source_quality` to `data.json`. This will eventually hallucinate a count with no stack trace. Fix it.

---

## Files to Read First

Before touching anything, read these in full:

1. `.claude/agents/regional-analyst-agent.md` — find and understand the source_quality block to remove
2. `tools/update_source_registry.py` — understand existing structure before adding to it
3. `.claude/commands/run-crq.md` — understand pipeline phase order
4. `output/regional/apac/data.json` — see what source_quality should look like when populated
5. `data/sources.db` schema — understand `source_appearances` and `sources_registry` tables (read via `uv run python -c "import sqlite3; ..."` or check `tools/update_source_registry.py` CREATE TABLE statements)

---

## Change 1 — Remove source_quality from analyst agent

**File:** `.claude/agents/regional-analyst-agent.md`

Remove:
- The entire "Deriving `source_quality` counts" section (URL scanning, tier classification rules, counting instructions)
- `source_quality` from the self-validation checklist
- Any instruction to write `source_quality` to `data.json`

**Do NOT remove anything else.** The agent still writes:
- `report.md` — full prose brief
- `data.json` — all existing fields (primary_scenario, severity, admiralty, rationale, signal_type, dominant_pillar, etc.)
- `signal_clusters.json` — cluster names, pillars, convergence, source names + headlines

---

## Change 2 — Add `enrich_region_data()` to `update_source_registry.py`

Add four new functions at the bottom of `tools/update_source_registry.py`. Do not modify any existing functions.

### Function 1: `_compute_source_quality(conn, region, run_id) -> dict`

```python
def _compute_source_quality(conn, region: str, run_id: str) -> dict:
    """Query source_appearances for this region+run, count by credibility_tier."""
    cur = conn.execute("""
        SELECT credibility_tier, COUNT(DISTINCT source_id)
        FROM source_appearances
        WHERE region = ? AND run_id = ?
        GROUP BY credibility_tier
    """, (region, run_id))
    counts = {row[0]: row[1] for row in cur.fetchall()}
    return {
        "tier_a": counts.get("A", 0),
        "tier_b": counts.get("B", 0),
        "tier_c": counts.get("C", 0),
        "total": sum(counts.values()),
    }
```

### Function 2: `_enrich_cluster_sources(conn, region) -> int`

```python
def _enrich_cluster_sources(conn, region: str) -> int:
    """
    For each source in signal_clusters.json, look up url + credibility_tier
    from sources_registry and add them to the source object.
    Returns count of resolved sources.
    """
    import json
    from pathlib import Path

    clusters_path = Path("output") / "regional" / region.lower() / "signal_clusters.json"
    if not clusters_path.exists():
        return 0

    data = json.loads(clusters_path.read_text(encoding="utf-8"))
    resolved = 0

    for cluster in data.get("clusters", []):
        for source in cluster.get("sources", []):
            name = source.get("name", "").strip()
            if not name:
                continue
            # Exact match first
            cur = conn.execute(
                "SELECT url, credibility_tier FROM sources_registry WHERE LOWER(name) = LOWER(?)",
                (name,)
            )
            row = cur.fetchone()
            if row:
                source["url"] = row[0]
                source["credibility_tier"] = row[1]
                resolved += 1
            else:
                # Leave null — log as unresolved
                source.setdefault("url", None)
                source.setdefault("credibility_tier", None)

    clusters_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return resolved
```

### Function 3: `_set_cited_flags(conn, region, run_id) -> int`

```python
def _set_cited_flags(conn, region: str, run_id: str) -> int:
    """
    For each source in enriched signal_clusters.json that has a url,
    set cited=1 in source_appearances.
    Returns count of updated rows.
    """
    import json
    from pathlib import Path

    clusters_path = Path("output") / "regional" / region.lower() / "signal_clusters.json"
    if not clusters_path.exists():
        return 0

    data = json.loads(clusters_path.read_text(encoding="utf-8"))
    updated = 0

    for cluster in data.get("clusters", []):
        for source in cluster.get("sources", []):
            url = source.get("url")
            if not url:
                continue
            cur = conn.execute(
                "SELECT id FROM sources_registry WHERE url = ?", (url,)
            )
            row = cur.fetchone()
            if row:
                conn.execute(
                    "UPDATE source_appearances SET cited=1 WHERE source_id=? AND run_id=? AND region=?",
                    (row[0], run_id, region)
                )
                updated += 1

    conn.commit()
    return updated
```

### Function 4: `enrich_region_data(region, run_id, db_path="data/sources.db")` — orchestrator

```python
def enrich_region_data(region: str, run_id: str, db_path: str = "data/sources.db") -> dict:
    """
    Code-owned enrichment gate. Runs after regional-analyst-agent exits.
    1. Computes source_quality from DB and writes to data.json
    2. Enriches signal_clusters.json sources with url + credibility_tier
    3. Sets cited=1 in source_appearances for matched cluster sources

    Raises AssertionError if source_quality validation fails.
    Returns source_quality dict.
    """
    import json
    import sqlite3
    from pathlib import Path

    db = Path(db_path)
    if not db.exists():
        print(f"[enrich_region_data] WARNING: {db_path} not found — skipping enrichment")
        return {}

    conn = sqlite3.connect(str(db))
    try:
        sq = _compute_source_quality(conn, region, run_id)
        resolved = _enrich_cluster_sources(conn, region)
        cited = _set_cited_flags(conn, region, run_id)
    finally:
        conn.close()

    # Write source_quality into data.json
    data_path = Path("output") / "regional" / region.lower() / "data.json"
    if data_path.exists():
        data = json.loads(data_path.read_text(encoding="utf-8"))
        data["source_quality"] = sq
        data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Validate
    _validate_source_quality(json.loads(data_path.read_text(encoding="utf-8")))

    print(f"[enrich_region_data] {region}: source_quality={sq} resolved={resolved} cited={cited}")
    return sq


def _validate_source_quality(data: dict) -> None:
    """Fail hard if source_quality is missing or arithmetic is wrong."""
    sq = data.get("source_quality")
    assert sq is not None, "source_quality missing from data.json"
    assert all(isinstance(sq.get(k), int) for k in ["tier_a", "tier_b", "tier_c", "total"]), \
        f"source_quality fields must be ints: {sq}"
    assert sq["total"] == sq["tier_a"] + sq["tier_b"] + sq["tier_c"], \
        f"source_quality total mismatch: {sq}"
```

---

## Change 3 — Wire into run-crq.md (correct order)

**File:** `.claude/commands/run-crq.md`

**CRITICAL ORDER:** `update_source_registry.py` already exists in the pipeline. `enrich_region_data` must run AFTER it — `source_appearances` must be populated first.

Find where `update_source_registry.py` is called (currently at the end of the global phase). Move it to run per-region, immediately after regional-analyst-agent. Then add `enrich_region_data` directly after it:

```
# Per-region, after regional-analyst-agent:
Run: uv run python tools/update_source_registry.py --region {REGION} --run-id {RUN_ID}

# Then immediately after:
Run: uv run python -c "
import sys; sys.path.insert(0, 'tools')
from update_source_registry import enrich_region_data
enrich_region_data('{REGION}', '{RUN_ID}')
"
```

Adapt to the exact command format already used in that file.

---

## Change 4 — Wire into server.py (correct order)

**File:** `server.py`

Find the pipeline execution handler. The correct order after regional-analyst-agent exits:

```python
# 1. Populate source_appearances FIRST
uv run python tools/update_source_registry.py  # or equivalent in-process call

# 2. Then enrich — source_appearances now has data for this run
from tools.update_source_registry import enrich_region_data
enrich_region_data(region, run_id)

# 3. Then CISO export
```

**Do not** place `enrich_region_data` before `update_source_registry`. The SQL query returns zeros if `source_appearances` is empty.

---

## Done Criteria

- [ ] `regional-analyst-agent.md` has no URL scanning, tier classification, or source_quality instructions
- [ ] `update_source_registry.py` has `enrich_region_data()` + all 4 sub-functions
- [ ] `_validate_source_quality()` raises `AssertionError` if source_quality missing or arithmetic wrong
- [ ] `update_source_registry.py` runs BEFORE `enrich_region_data` in both `run-crq.md` and `server.py`
- [ ] Run `uv run python -c "from tools.update_source_registry import enrich_region_data; print('import OK')"` — no errors
- [ ] After a mock pipeline run: `output/regional/apac/data.json` contains `source_quality` with non-zero `total` (if sources exist in DB)

**Signal to Task 2:** "Task 1 complete. `enrich_region_data()` available. `update_source_registry` runs before it. `data.json` will contain `source_quality` after a full run."
