---
description: Generate the thin /crq-run skill from crq.config.json.
agent: agent
tools: ['editFiles']
---

# /create-skill — Generate the /crq-run skill

> Frontmatter keys are version-sensitive (see /setup note).

1. Read `crq.config.json`. If it is missing or invalid, STOP and tell the operator
   to run `/setup` first.
2. Write `.github/prompts/crq-run.prompt.md` with EXACTLY the content below
   (verbatim — it delegates all orchestration to `tools/crq_run.py` and carries
   only the operator Q&A + the two authoring steps):

   ```markdown
   ---
   description: Produce live regional risk brief(s) for today.
   agent: agent
   tools: ['editFiles', 'runCommands']
   ---

   # /crq-run — Produce today's regional brief(s)

   1. Ask the operator: which region(s)? (APAC / AME / LATAM / MED / NCE, or ALL.)
      And org-grounded or region-guided for this run? (Default comes from
      crq.config.json — if they have no preference, omit the override.)
   2. Run: `uv run python tools/crq_run.py collect --regions <THEIR REGIONS>`
      Add `--region-guided` or `--org-grounded` only if they chose to override
      the default. The command prints one `analyst_request.md` path per region.
   3. For EACH printed `analyst_request.md`: read it and write `claims.json` +
      `analyst_report.md` into the SAME directory. Follow the AUTHORING CONTRACT
      below — the render step enforces it deterministically.
   4. Run: `uv run python tools/crq_run.py prep`
      It prints one `formatter_request.md` path per region.
   5. For EACH printed `formatter_request.md`: read it and write `brief.md` into
      the SAME directory, following the AUTHORING CONTRACT.
   6. Run: `uv run python tools/crq_run.py render`
      Report the `email.html` path it prints for each region.

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

3. Tell the operator: "Generated `/crq-run`. You may need to reload the VSCode
   window before it appears in the `/` list. Then run `/crq-run`."
