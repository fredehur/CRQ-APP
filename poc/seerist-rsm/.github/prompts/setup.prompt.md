---
description: Configure the CRQ regional-brief pipeline (brand, org-context default, live API key).
agent: agent
tools: ['editFiles', 'runCommands']
---

# /setup — Configure the CRQ pipeline

> Frontmatter keys are version-sensitive. If this VS Code build does not honor
> `agent:` or the `editFiles` / `runCommands` toolset names, substitute the
> correct identifiers for this build before relying on the prompt.

Do the following, in order:

1. Ask the operator for a **brand label** — the name shown on the brief header.
   Use the client/company name, or `REGIONAL RISK INTELLIGENCE` for a neutral
   brief (e.g. for a prospect). Default to `REGIONAL RISK INTELLIGENCE` if they
   have no preference.
2. Ask which kind of brief they want by default, in plain terms:
   - **org-grounded** — the brief names their specific sites, people, and exposure
     (uses the site registry).
   - **region-guided** — the brief covers the region's risk landscape only, with
     no company details (good for prospects who haven't shared their sites).
   This is only the *default*; `/crq-run` asks again each run, so they can switch
   per brief.
3. Ask whether to include the **OSINT physical pillar** by default — extra
   web/news enrichment (protests, conflict, maritime, disasters) on top of the
   Seerist signals. It needs `TAVILY_API_KEY` + `FIRECRAWL_API_KEY` + `ANTHROPIC_API_KEY`
   (enrichment) in `.env`. Default **off** if they have no preference. Again, only
   the *default* — `/crq-run` asks per run.
4. **Verify the keys.** Confirm `.env` exists and contains a non-empty
   `SEERIST_API_KEY`. If `.env` is missing, copy `.env.example` to `.env` and tell
   the operator to fill `SEERIST_API_KEY`, then STOP — do not write config until a
   key is present. This pipeline is **live-only**; there is no mock fallback.
   - `SEERIST_API_KEY` is always required — briefs are built from Seerist signals.
   - `TAVILY_API_KEY` + `FIRECRAWL_API_KEY` + `ANTHROPIC_API_KEY` (enrichment) are
     required ONLY when OSINT is used (the default from step 3, or a per-run choice
     in `/crq-run`). All three or OSINT runs fail loudly. If the OSINT default is
     on, verify all three are present; if absent, warn the operator that OSINT runs
     will fail loudly until they set them.
5. Write `crq.config.json` at the repo root with exactly:

   ```json
   {
     "brand_label": "<their brand>",
     "org_context_default": <true|false>,
     "osint_default": <true|false>
   }
   ```

6. Confirm: "Setup complete. Next: run `/create-skill`."

Re-running `/setup` overwrites the config and re-checks the key.
