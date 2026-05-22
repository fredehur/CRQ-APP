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

1. Ask the operator for a **brand label** (the header band brand, e.g. the client
   company name, or `REGIONAL RISK INTELLIGENCE` for a neutral/prospect brief).
   Default to `REGIONAL RISK INTELLIGENCE` if they have no preference.
2. Ask whether briefs should default to **org-grounded** (uses the client's site
   registry) or **region-guided** (no org context — region is the only scope).
   This is only the *default*; `/crq-run` asks again per run.
3. **Verify the live key.** Confirm `.env` exists and contains a non-empty
   `SEERIST_API_KEY`. If `.env` is missing, copy `.env.example` to `.env` and tell
   the operator to fill `SEERIST_API_KEY`, then STOP — do not write config until a
   key is present. This pipeline is **live-only**; there is no mock fallback.
   Note: only `SEERIST_API_KEY` is required. The OSINT layer (TAVILY/FIRECRAWL)
   degrades by design — its absence yields a thinner brief, not an error. The
   analyst/formatter LLM work is done by you (the agent), so no ANTHROPIC key is
   needed.
4. Write `crq.config.json` at the repo root with exactly:

   ```json
   {
     "brand_label": "<their brand>",
     "org_context_default": <true|false>
   }
   ```

5. Confirm: "Setup complete. Next: run `/create-skill`."

Re-running `/setup` overwrites the config and re-checks the key.
