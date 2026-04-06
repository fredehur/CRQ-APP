# Sources Architecture — Full Redesign Plan
**Date:** 2026-04-01  
**Status:** Milestone 1 in progress  
**Structure:** 5 milestones, not 13 phases

---

## Three source domains, one architecture

| Domain | What | Cadence | Storage |
|---|---|---|---|
| **OSINT** | Tavily/YouTube automated collection | Every pipeline run | `sources.db` + signal files |
| **Benchmark** | DBIR/IBM/CISA/Dragos annual reports | Annual, on-demand | `validation_sources.json` + `validation_cache/` + `sources.db` (Milestone 3) |
| **Seerist** | Structured geopolitical events | Future | `seerist_events` table — stays separate |

---

## Where sources surface

| Surface | Question | Domain |
|---|---|---|
| Region card badge | "Is this run's evidence credible?" | OSINT only (benchmark excluded from scoring) |
| Brief view — evidence panel | "What backed this escalation?" | OSINT |
| Validate tab — scenario rows | "Is VaCR right AND is the threat active now?" | Benchmark verdict + OSINT signal + velocity |
| Trends tab — heatmap annotation | "Is quality consistent over time?" | OSINT (one line, run_count ≥ 3, time-gated) |
| CISO docx — reference list | "Where did this come from?" | OSINT + Benchmark tier labels |
| Source Audit tab | Admin/audit — full registry | All types |

---

## Milestone 1 — Fix the broken stuff ✅ IN PROGRESS
*Analyst experience after: "Validate tab shows real verdicts. Flagging junk works next run. No broken panels."*

### M1-A: Remove broken UI panels + rename tab

**`static/app.js`**
- Remove `loadValSourceAttribution()` function entirely
- Remove it from `renderValidateTab()` Promise.all (keep loadValScenarios, loadValSources, loadValCandidates)
- Remove `sourceVelocityHtml` variable and `_vtierBadge` helper from `renderTrends()`
- Revert `renderTrends()` to single `fetch('/api/trends')` — remove Promise.all wrapper
- Keep `applyRegionFilterAndSwitch(region)` — reused in Milestone 4

**`static/index.html`**
- Remove `<!-- Source attribution from pipeline registry -->` div block from tab-validate
- Rename nav tab: `Sources` → `Source Audit`
- Add description in tab header: "Full source registry across pipeline runs. Audit quality, flag junk, and block sources."

**`server.py`**
- Keep `/api/sources/attribution` and `/api/sources/velocity` — reused in Milestone 4

**Done when:** No attribution table in Validate tab, no velocity grid in Trends, tab reads "Source Audit", no JS console errors.

---

### M1-B: Fix benchmark extraction

**Reality check on paywalls:** Verizon DBIR and IBM Cost of Data Breach are paywalled PDFs. Direct URL fetch (Tier A) will fail or return a login page. DDG fallback (Tier B) returns press release summaries and news coverage — this is sufficient for ballpark benchmarking. We are validating VaCR numbers against *reported figures*, not full datasets. That's honest and useful.

**`tools/source_harvester.py`**
- Confirm `--mock` flag is not passed when called from `server.py _run_validation()`
- Verify DDG fallback fires correctly when URL fetch fails
- Log which tier (A/B/C) succeeded for each source

**`tools/benchmark_extractor.py`**
- Verify extraction prompt handles DDG-style summary text (short paragraphs, not full PDFs)
- Add logging: number of financial figures extracted per source

**`server.py` — `_run_validation()` (lines 878–915)**
- After source_harvester step: emit count of sources with non-empty raw_text
- After benchmark_extractor step: emit total benchmark figures extracted
- After crq_comparator step: emit summary (N supported, N challenged, N no_data)

**`data/validation_sources.json`**
- Verify Dragos ICS/OT report has `scenario_tags` including `"System intrusion"` — add if missing
- Verify all 7 sources have at least one `scenario_tag` matching SCENARIO_KEYWORDS in `crq_comparator.py`

**Done when:** At least 3/9 scenarios have non-null `benchmark_median_usd` in validation_flags.json. Progress bar in Validate tab shows meaningful step messages.

---

### M1-C: Close the junk feedback loop

**Architecture decision:** Blocked URLs stored as `data/blocked_urls.txt` (one URL per line). This is the operational blocklist read by `research_collector.py` at startup. The DB (`blocked=1` column) is the authoritative record; the flat file is derived from it. Benefits: no SQLite dependency in the collection hot path, fully versionable in git, easy to audit.

**`tools/update_source_registry.py`**
- Add `blocked INTEGER DEFAULT 0` column to `sources_registry` CREATE TABLE
- Add migration: `ALTER TABLE sources_registry ADD COLUMN blocked INTEGER DEFAULT 0` (run if column missing)
- Add function `sync_blocked_urls(db_path, output_path)`: queries `SELECT url FROM sources_registry WHERE blocked=1`, writes to `data/blocked_urls.txt`
- Call `sync_blocked_urls()` at end of main ingest run

**`tools/research_collector.py`**
- At startup, before any Tavily fetch: read `data/blocked_urls.txt` if it exists → build a set
- Merge into `_is_junk_url()` check: if URL in blocked set → return True (skip it)
- File read is one I/O operation at startup — no DB dependency

**`server.py` — `POST /api/sources/{id}/flag` (line 1043)**
- When `junk=True`: also set `blocked=1` in DB
- After DB write: immediately sync `data/blocked_urls.txt` (call sync function inline or via subprocess)
- When `junk=False`: set `blocked=0` and remove URL from `blocked_urls.txt`

**`static/app.js`**
- Flag button in Sources tab: when source is blocked, show `🚫 blocked` badge alongside junk badge
- Unblock action available (calls flag API with `junk=false`)

**Done when:** Flag a source as junk in UI → `data/blocked_urls.txt` is updated → next `research_collector.py` run skips that URL.

---

## Milestone 2 — Scenario health picture
*Depends on: nothing (reads existing files). Do next session.*
*Analyst experience: "Validate tab shows: benchmark verdict + which regions escalated this scenario this week + run-over-run rate."*

**Validate tab scenario rows gain 2 columns:**
- **OSINT Signal**: regions where `data.json.primary_scenario` matches + `gatekeeper_decision=ESCALATED` this run
- **Velocity**: `scenario_frequency[scenario]` / `run_count` from `trend_analysis.json` → `↑ 8/8 runs`

`server.py GET /api/validation/flags` enriched with osint_signal + velocity per scenario row.

---

## Milestone 3 — One registry
*Depends on: Milestone 1 (benchmark extraction working). Do after Milestone 2.*
*Analyst experience: "Sources tab shows 108 sources: 101 OSINT + 7 Benchmark anchors, clearly labelled."*

- Add `collection_type TEXT DEFAULT 'osint'` to `sources_registry`
- `source_harvester.py` upserts benchmark sources into DB with `collection_type='benchmark'`, `credibility_tier='A'`
- **Critical:** benchmark sources are EXCLUDED from OSINT quality scoring (region card badge)
- Verify canonical names in signal files after one live run — explicit check for "Tavily Research" generics
- Add Benchmark badge (gold) to Sources tab type filter

---

## Milestone 4 — Source context in outputs ✅ COMPLETE (2026-04-06)

- `source_quality` flowing correctly into all regional data.json — fix: `.upper()` on region param in `_compute_source_quality`
- Fix B: cluster sources enriched with `{url, credibility_tier}` via `_enrich_cluster_sources`
- CISO docx reference list: `[A]/[B]/[C]` tier labels in reference section
- Evidence panel HTML wired in app.js (`_fetchEvidence` / `evidence-list-${region}`)

---

## Milestone 5 — Longitudinal quality
*Depends on: Milestone 4 + 3 pipeline runs with source_quality populated. Time-gated: ~3 weeks.*
*Analyst experience: "Trends tab shows APAC has had 8 Tier A sources consistently across 10 runs."*

- `source_appearances` gains `cluster_name` + `indicator_text` — populated from `signal_clusters.json`
- `cited=1` set via URL match in clusters (not prose match)
- Trends heatmap: one-line quality annotation per region — raw facts, no score, absent if run_count < 3

---

## DB schema — target state

```sql
CREATE TABLE sources_registry (
    id               TEXT PRIMARY KEY,
    url              TEXT UNIQUE NOT NULL,
    name             TEXT NOT NULL,
    domain           TEXT,
    source_type      TEXT,
    collection_type  TEXT DEFAULT 'osint',   -- NEW: osint | benchmark
    credibility_tier TEXT DEFAULT 'B',
    junk             INTEGER DEFAULT 0,
    blocked          INTEGER DEFAULT 0,      -- NEW: feeds blocked_urls.txt
    first_seen       TEXT,
    last_seen        TEXT,
    appearance_count INTEGER DEFAULT 0,
    cited_count      INTEGER DEFAULT 0
);

CREATE TABLE source_appearances (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT REFERENCES sources_registry(id),
    run_id          TEXT,
    region          TEXT,
    pillar          TEXT,
    cluster_name    TEXT,                    -- NEW (Milestone 5)
    indicator_text  TEXT,                    -- NEW (Milestone 5)
    headline        TEXT,                    -- kept for compat, stop populating
    cited           INTEGER DEFAULT 0,
    collected_at    TEXT
);
```
