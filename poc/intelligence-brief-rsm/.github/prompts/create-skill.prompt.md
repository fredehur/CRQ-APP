---
description: Generate the thin /intel-brief skill from crq.config.json.
agent: agent
tools: ['editFiles']
---

# /create-skill — Generate the /intel-brief skill

> Frontmatter keys are version-sensitive (see /setup note).

1. Read `crq.config.json`. If it is missing or invalid, STOP and tell the operator
   to run `/setup` first.
2. Write `.github/prompts/intel-brief.prompt.md` with EXACTLY the content below
   (verbatim — it delegates all orchestration to `tools/crq_run.py` and carries
   only the operator Q&A + the two authoring steps):

   ```markdown
   ---
   description: Produce live regional risk brief(s) for today.
   agent: agent
   tools: ['editFiles', 'runCommands']
   ---

   # /intel-brief — Produce today's regional brief(s)

   1. Ask the operator four things:
      - Timeframe: Daily brief (1 day lookback) or Weekly brief (7 day lookback)?
        Default comes from crq.config.json (`window_days_default`: 1=Daily, 7=Weekly).
        If no preference, use the default.
      - Which region(s) for today's brief? (APAC / AME / LATAM / MED / NCE, or ALL.)
      - Org-grounded (names their sites + people) or region-guided (region only,
        no company details)? Default comes from crq.config.json.
      - Include OSINT physical-pillar enrichment (extra web/news on protests,
        conflict, maritime, disasters)? It needs Tavily + Firecrawl keys. Default
        comes from crq.config.json.
      For any choice where they have no preference, just use the default (omit the
      override flag).
   2. Run: `uv run python tools/crq_run.py collect --regions <THEIR REGIONS> [--window 1|7]`
      Map Daily => `--window 1`, Weekly => `--window 7`.
      If operator chose default timeframe, omit `--window` and let config default apply.
      Add overrides ONLY when they differ from the defaults:
      `--region-guided` / `--org-grounded`, and `--osint` / `--no-osint`.
   3. IF OSINT is on, the command prints `osint_enrich_request.md` path(s). For EACH:
      read it and rewrite `osint_physical_signals.json` enriched (+ `osint_dropped.json`)
      per the enrichment prompt it embeds — relevance-drop, `summary`,
      `corroborates_event`; do NOT assign severity.
   4. Run: `uv run python tools/crq_run.py analyze` (builds the manifest from the
      enriched OSINT + prints analyst_request paths).
   5. For EACH `analyst_request.md`: write `claims.json` + `analyst_report.md` (AUTHORING CONTRACT).
   6. Run: `uv run python tools/crq_run.py prep`
      It prints one `formatter_request.md` path per region.
   7. For EACH printed `formatter_request.md`: read it and write `brief.md` into
      the SAME directory, following the AUTHORING CONTRACT.
   8. Run: `uv run python tools/crq_run.py render`; report the `email.html` paths.
      The render step also writes `intel_decisions.md` next to `email.html` —
      it logs which intel was pulled, which was used in claims, and which was
      dropped (with reasons). Surface this path to the operator alongside
      `email.html` so they can audit the run.

   ## Output structure

   Every run lands at `output/briefs/<YYYY-MM-DD>/<REGION>/` and contains:
   - `email.html` — the finished brief (open in browser, copy/paste into Gmail)
   - `brief.md` — the markdown source
   - `intel_decisions.md` — per-run transparency log (kept/dropped intel + reasons)
   - `claims.json` — analyst's structured claims registry (powers the appendix)
   - `analyst_report.md` — analyst's narrative read
   - `osint_physical_signals.json` / `osint_dropped.json` — kept/dropped OSINT
   - `seerist_signals.json` — the Seerist payload the analyst worked from
   - `_rsm_manifest_daily.json` — the manifest the analyst + formatter consumed
   - The `*_request.md` files used by each agent step (osint_enrich / analyst / formatter)

   ## AUTHORING CONTRACT (the render step fails if you break these)
   - Body citations use `[<claim_id>]` form (e.g. `[med-001]`) — NEVER raw numbers.
     Code renumbers them to `[1]…[N]` and builds the APPENDIX. Every body cite must
     map to a claim in claims.json, and every appended claim must be cited at least once.
   - The CYBER section must be non-empty — always include the standing watchlist
     baseline claim (sector_baseline, regional, estimate), even on a quiet day.
   - Org-grounded briefs: site rows must match `▪ <Name> [<CRIT> · <N>p / <M> expat(s)]`
     and personnel/expat counts must equal the manifest site_registry exactly.
     Region-guided briefs have NO site rows — write region-level prose under
     `█ REGIONAL EXPOSURE` instead.
   - Stop at the end of the WATCH section. Do not add a footer, trailer, or reply
     taxonomy — the template injects those and the validator rejects them in the body.
   ```

3. Tell the operator: "Generated `/intel-brief`. You may need to reload the VSCode
   window before it appears in the `/` list. Then run `/intel-brief`."
