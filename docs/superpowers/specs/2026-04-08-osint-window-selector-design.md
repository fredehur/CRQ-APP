# OSINT Window Selector — Design Spec

**Date:** 2026-04-08
**Status:** Approved (v2 — principles-informed update)
**Scope:** Interactive time-window selection for OSINT data collection in the CRQ pipeline

---

## Problem

`/run-crq` silently defaults to a 7-day collection window. The operator has no visibility into this choice and no way to adjust it without knowing the `--window` flag syntax. The operational reality is a **daily run pattern** — meaning a 7-day default pulls 6 days of stale signals every time.

Secondary problem: `--window` is currently threaded as a CLI flag through every Phase 1 tool invocation. This is fragile state-passing that violates the "filesystem as state" principle and breaks on edge cases (empty-string arg when window is "all").

---

## Solution

**Phase 0** asks the operator to choose a window (via `AskUserQuestion`), then writes the selection to `output/pipeline/run_config.json` — a single deterministic state file read by all downstream tools. CLI flag `--window` remains valid as an override for scripted/automated invocations.

This approach is ZTE-ready: when the pipeline moves to the app, the app writes `run_config.json` directly and the orchestrator skips the prompt entirely.

---

## Window Options

| Choice | Label | `run_config.json` value | Downstream behaviour |
|--------|-------|-------------------------|----------------------|
| 1 | 1 day — today's signals (daily ops) | `"1d"` | DDG `timelimit=d`, Tavily `days=1` |
| 2 | 1 week | `"7d"` | DDG `timelimit=w`, Tavily `days=7` |
| 3 | 1 month | `"30d"` | DDG `timelimit=m`, Tavily `days=30` |
| 4 | 3 months | `"90d"` | DDG `timelimit=y`, Tavily `days=90` |
| 5 | All — no date filter (baseline sweep) | `"all"` | No timelimit/days param sent |

---

## Architecture

### run_config.json (new — written in Phase 0)

```json
{
  "window": "1d",
  "osint_mode": "mock",
  "pipeline_id": "..."
}
```

Written to `output/pipeline/run_config.json` at the end of Phase 0. All tools that need `window` read this file. CLI flag `--window` overrides the config value when present (back-compat).

This is the **proof artifact** for window selection — readable by stop hooks, audit scripts, and the manifest.

### run-crq.md — Phase 0 changes

1. Add `AskUserQuestion` to the `tools:` frontmatter.
2. If `--window` was NOT passed in invocation args: use `AskUserQuestion` to present the 5-option menu. Map response to window value (`1` → `1d`, `2` → `7d`, `3` → `30d`, `4` → `90d`, `5` → `all`).
3. If `--window` was passed: use that value directly. Accept `all` as valid.
4. Write `run_config.json` with `window`, `osint_mode`, and `pipeline_id`.
5. In Phase 1 tool invocations: pass `--window {window}` only when `window != "all"`. Omit `--window` entirely for `all` (tools already handle `window=None` as no-filter).
6. Phase 6 `write_manifest.py`: reads `window` from `run_config.json` — no CLI arg needed, no empty-arg edge case.

### crq-region.md — Phase 0 changes (parity)

Same pattern: if `--window` not passed, use `AskUserQuestion`. Write `run_config.json`. All regional tool invocations read from it.

### Tools — no changes needed

`geo_collector.py`, `cyber_collector.py`, `research_collector.py`, `osint_search.py` — all already handle `window=None` as no-filter. The orchestrator simply omits `--window` for the `all` case. Zero changes to these files.

`write_manifest.py` — reads `window` from `run_config.json` instead of CLI arg. This fixes the empty-arg edge case and aligns with filesystem-as-state.

---

## Data Flow

```
/run-crq (no --window)
  → AskUserQuestion → operator picks 1–5
  → WINDOW resolved ("1d" / "7d" / "30d" / "90d" / "all")
  → Phase 0 writes output/pipeline/run_config.json
  → Phase 1: collectors receive --window {WINDOW} or no flag (all case)
  → Phase 6: write_manifest.py reads window from run_config.json
  → run_config.json archived with run artifacts for audit

/run-crq --window 30d  (explicit override)
  → skip prompt, write run_config.json with window="30d"
  → same flow as above
```

---

## Future: App UI

The interactive prompt is a **Claude Code interim implementation**. When the pipeline moves into the web app:

1. The run-trigger panel exposes a window selector (dropdown or segmented control).
2. On run, the app writes `run_config.json` and calls the pipeline.
3. The orchestrator detects `run_config.json` already exists → skips `AskUserQuestion` entirely.
4. No other changes needed.

The `run_config.json` contract is the bridge. The CLI flag `--window` remains valid for scripted/scheduled runs.

---

## Out of Scope

- Persisting last-used window between runs (always ask fresh for now)
- `180d` / 6-month option (not supported by DDG/Tavily; `90d` → year tier is the ceiling)
- Scheduled/automated runs (future work — will use configured default in `run_config.json`, not a prompt)
- Refactoring other tools to read `run_config.json` (only `write_manifest.py` changes; others keep CLI flags)
