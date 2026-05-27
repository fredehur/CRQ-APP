---
description: Bootstrap the CRQ pipeline — check prerequisites, install deps, scaffold .env.
agent: agent
tools: ['editFiles', 'runCommands']
---

# /install — Bootstrap the CRQ pipeline

> Frontmatter keys are version-sensitive (see /setup note).

Do the following, in order. Run all terminal commands from the repo root
(`poc/seerist-rsm/`).

1. Check `python --version` (need 3.11+) and `uv --version`. If `uv` is missing,
   tell the operator to install it (`https://docs.astral.sh/uv/`) and STOP.
2. Run `uv sync` to install dependencies.
3. If `.env` does not exist, copy `.env.example` to `.env`.
4. Tell the operator the remaining manual steps (prompt files are invoked by the
   user — this prompt cannot run them for you):
   - Fill `SEERIST_API_KEY` in `.env`.
   - Run `/setup` to configure brand + org-context default.
   - Run `/create-skill` to generate the `/intel-brief` skill.
   - Then run `/intel-brief` to produce briefs.
