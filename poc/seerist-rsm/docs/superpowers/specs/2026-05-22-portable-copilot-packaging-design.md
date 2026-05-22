# Portable Copilot Packaging Layer — Design

**Date:** 2026-05-22
**Slice:** `poc/seerist-rsm`
**Status:** Draft for review (revised after independent design review)

## Goal

Make the existing RSM pipeline **installable and runnable inside GitHub Copilot
(VSCode)** via Copilot prompt files, so an operator can stand it up and produce
regional risk briefs without Claude Code. The pipeline already emits
provider-agnostic request files (`analyst_request.md` / `formatter_request.md`)
that name "GitHub Copilot IDE" as a target; this layer wraps install + config +
invocation around it.

**Primary target:** GitHub Copilot in VSCode. Other IDEs (Claude Code, Codex)
are explicitly out of scope for this spec.

**Operating assumptions (decided during brainstorming):**

- **Live-only.** The product runs against the configured APIs. There is no mock
  mode in the operator flow. Setup makes a live `SEERIST_API_KEY` mandatory.
- **Region is chosen per run**, not fixed at setup. Any of APAC / AME / LATAM /
  MED / NCE (one or several) can be requested for "today's" brief.
- **Zero changes to the deterministic tools** (Approach A). The Copilot agent
  reads config and drives `tools/poc_runner.py` exactly as it stands today.

## Architecture

A pure-markdown packaging layer under `.github/prompts/`:

- three **authored** prompt files: `install`, `setup`, `create-skill`;
- one **generated** prompt file: `crq-run` (written by `create-skill`);
- one config file `crq.config.json` (defaults) + `.env` (secrets).

The Copilot agent runs in **agent mode** with file-edit and terminal tools
granted via prompt-file frontmatter. It reads `crq.config.json`, asks the
operator the per-run questions, and shells out to `poc_runner.py`.

### Prompt-file frontmatter contract (version-sensitive — verify against the installed VS Code)

Every authored and generated prompt file uses this frontmatter. The VS Code
Copilot prompt-file format has churned (the chat-mode key was `mode:` in early
2025 and is `agent:` in current docs), so the implementer MUST confirm the keys
against the VS Code build on the target machine before shipping:

```yaml
---
description: <one line>
agent: agent          # chat mode. Current key is `agent:`, not the older `mode:`.
tools: ['editFiles', 'runCommands']   # editFiles = write files; runCommands = terminal
---
```

`editFiles` is required to write `crq.config.json`, the generated
`crq-run.prompt.md`, and the agent-authored `claims.json` / `analyst_report.md`
/ `brief.md`. `runCommands` is required to run `uv sync` and `poc_runner.py`.
If the installed build names these toolsets differently, substitute the correct
identifiers — do not ship prose like "terminal + edit".

### Setup-time vs run-time split

| Configured once — `/setup` → `crq.config.json` + `.env` | Asked each run — `/crq-run` |
|---|---|
| `SEERIST_API_KEY` in `.env` (live — **required**) | Which region(s) today? |
| `brand_label` (client name, or neutral) | Org-grounded or region-guided this brief? |
| `org_context_default` (true/false) | — |

Rationale: brand and the org-context default are stable per install; the region
and the org/region-guided choice vary per brief (e.g. an org-grounded brief for
a client and a region-guided one for a prospect off the same install).

## Components

### 1. `crq.config.json` (the config contract)

```json
{
  "brand_label": "REGIONAL RISK INTELLIGENCE",
  "org_context_default": false
}
```

That is the entire schema. Deliberately minimal:

- **No `regions`** — chosen per run.
- **No `mode`** — always live.
- **No `cadence`** — `poc_runner` hardcodes `cadence="daily"` (`poc_runner.py`
  builds the manifest with `cadence="daily"`) and exposes no cadence flag, so a
  cadence knob would be inert. Weekly lives in `rsm_dispatcher.py`, outside this
  flow.

There is no code loader (Approach A). The agent reads and validates the JSON
against this documented shape. Missing/invalid → the run skill tells the
operator to re-run `/setup`.

### 2. `.github/prompts/setup.prompt.md`

Frontmatter per the contract above (`agent: agent`, `tools: ['editFiles', 'runCommands']`).

Steps the agent performs:
1. Ask `brand_label` (free text; default `REGIONAL RISK INTELLIGENCE`).
2. Ask `org_context_default` (org-grounded vs region-guided).
3. **Verify `SEERIST_API_KEY` is present and non-empty in `.env`.** If absent,
   stop and instruct the operator to copy `.env.example` → `.env` and fill the
   key. Live is mandatory; there is no mock fallback offered.
4. Write `crq.config.json`.

Idempotent — re-running overwrites the config and re-checks the key.

**Seerist key is sufficient — and the OSINT layer degrades by design.**
`phase_collect` does not call `osint_physical_collector`; it stubs
`osint_signals.json` / `data.json` with `{}` and lets `rsm_input_builder` fire
its documented fallbacks. So `SEERIST_API_KEY` alone produces a clean run — the
TAVILY / FIRECRAWL / ANTHROPIC keys in `.env.example` are **not** needed (the
Copilot agent itself performs the analyst/formatter LLM work). The brief simply
runs without the OSINT physical layer; setup should state this so a thinner
brief isn't a surprise.

### 3. `.github/prompts/create-skill.prompt.md`

Frontmatter per the contract above (`agent: agent`, `tools: ['editFiles']`).

Steps:
1. Read `crq.config.json`; refuse (point to `/setup`) if missing/invalid.
2. Generate `.github/prompts/crq-run.prompt.md`, emitting **the correct
   frontmatter into the generated file** (`agent: agent`,
   `tools: ['editFiles', 'runCommands']`) — not just a body. The generated skill
   embeds `brand_label` and `org_context_default` from config.
3. Tell the operator they may need to reload the VSCode window before `/crq-run`
   appears in the `/` completion list.

### 4. `.github/prompts/install.prompt.md`

Frontmatter per the contract above (`agent: agent`, `tools: ['editFiles', 'runCommands']`).

Steps:
1. Check Python and `uv` are available; if not, instruct how to install.
2. `uv sync`.
3. If `.env` is missing, copy `.env.example` → `.env`.
4. **Instruct the operator** to run `/setup`, then `/create-skill`, then
   `/crq-run`. (Prompt files are invoked manually by the user; one prompt file
   cannot be relied on to deterministically invoke another — chaining here is
   human guidance, not automated control flow.)

### 5. The generated `crq-run.prompt.md` — the run skill

This is the heart of the layer. It encodes the **real five-step state machine**
that `poc_runner.py` requires, looped per selected region.

Run sequence:
1. **Resolve today's date once** (`YYYY-MM-DD`) and reuse it for every phase and
   region. Output is keyed by `output/poc/<region>/<date>/`, and phases B and C
   re-derive the same directory — so a single consistent date is mandatory.
2. Ask the operator: which region(s) (subset of APAC/AME/LATAM/MED/NCE), and
   org-grounded vs region-guided for this brief (default from
   `org_context_default`).
3. Resolve flags: region-guided → append `--no-org-context`; always pass
   `--brand "<brand_label>"`.
4. **Per region, run the five steps in order:**
   1. `uv run python tools/poc_runner.py <REGION> <DATE> --collect --require-live [--no-org-context] --brand "<brand_label>"`
      — **`--require-live` is mandatory**: without it, a missing/typo'd
      `SEERIST_API_KEY` makes the collector fall back to mock fixtures silently,
      defeating the live-only guarantee. With it, `phase_collect` fails loudly
      when no key is present.
   2. Agent reads `output/poc/<region>/<date>/analyst_request.md` and **writes
      `claims.json` + `analyst_report.md`** to that directory, following the
      **authoring contract** below.
   3. `uv run python tools/poc_runner.py <REGION> <DATE> --prep-format`
      (precondition: `claims.json` + `analyst_report.md` + manifest must exist).
   4. Agent reads `formatter_request.md` and **writes `brief.md`** to that
      directory, following the authoring contract below.
   5. `uv run python tools/poc_runner.py <REGION> <DATE> --render`
      — this first runs `normalize_citations.py` (which **hard-fails if the brief
      cites any `claim_id` absent from `claims.json`**), then `validate_brief.py`,
      then renders. A render can fail for citation/validation reasons, not just
      missing files.
5. Report each region's `output/poc/<region>/<date>/email.html` path.

The two LLM steps (4.2 and 4.4) are **distinct prompts read at different
times** — `formatter_request.md` does not exist until `--prep-format` runs, so
they cannot be fused.

#### Agent authoring contract (what the run skill must tell the agent)

`--render` enforces deterministic gates the agent cannot see while writing.
The generated `crq-run` skill must spell these out so agent-authored files pass
on the first try:

- **Citation bijection** (`validate_brief.py`): body cites must use
  `[<claim_id>]` form (e.g. `[med-001]`), **not** raw numbers — `normalize_citations`
  renumbers them to `[1]…[N]` and synthesizes the APPENDIX. Every body cite must
  map to a claim in `claims.json`, and every claim that reaches the appendix must
  be cited at least once.
- **Mandatory non-empty CYBER section** with at least one claim — always emit the
  standing watchlist baseline claim (sector_baseline, regional, estimate) even on
  a quiet day.
- **Org-grounded briefs only:** site rows must match the exact format
  `▪ <Name> [<CRIT> · <N>p / <M> expat(s)]` and personnel/expat counts must equal
  the manifest `site_registry`. In **region-guided** runs there are no site rows
  (the exposure section is region-level prose under `█ REGIONAL EXPOSURE`), so
  this gate does not apply — which makes region-guided briefs the lower-risk path
  for agent authoring.
- **Stop at the end of WATCH** — no trailer, footer, or reply taxonomy (the
  template injects those; `validate_brief` rejects them in the body).

## Data flow

```
git clone <repo>
  → open in VSCode
  → /install      (uv sync, .env scaffold; instructs next steps)
  → /setup        (writes crq.config.json, verifies live key)
  → /create-skill (generates crq-run.prompt.md)
  → (reload window if needed)
  → /crq-run      (asks region(s) + org/region-guided; runs the 5-step loop live)
```

## Error handling

- **install:** missing Python/`uv` → stop with install guidance.
- **setup:** missing/empty `SEERIST_API_KEY` → stop, point to `.env.example`.
  No mock fallback.
- **create-skill:** missing/invalid `crq.config.json` → stop, point to `/setup`.
- **crq-run:** if a phase precondition file is missing, surface the
  `poc_runner` `SystemExit` message verbatim rather than continuing; if a region
  returns no live signals, report it and continue to the next region.
- **Date consistency:** the resolved date is stated explicitly to the operator
  and reused; a re-run on a later day starts a fresh dated directory. Caveat:
  `rsm_input_builder._filter_notable_dates` keys its 7-day horizon off the real
  UTC "today", not the supplied `date_iso` — so backfilling a non-today date
  filters notable dates against the wrong anchor. Low impact for same-day runs;
  noted so it isn't mistaken for a bug.

## Testing / verification

Prompt files are markdown and run live + LLM-in-the-loop, so full end-to-end
cannot run unattended — and not in the authoring environment (no live
`SEERIST_API_KEY`, and `truststore` is absent here, so the live collector path
cannot execute locally). Verification therefore splits:

- **Static, doable at authoring time:**
  - `crq.config.json` validates against the documented schema.
  - the generated `crq-run.prompt.md` has well-formed frontmatter (`agent: agent`,
    `tools: ['editFiles', 'runCommands']`) and a body.
  - the exact `poc_runner` command strings the run skill emits parse against the
    real CLI: `poc_runner.py <REGION> <DATE> --collect|--prep-format|--render
    [--no-org-context] [--brand ...]` — confirming region+date positionals and
    flag names match `tools/poc_runner.py`.
- **Operator acceptance walkthrough (live):** a documented checklist —
  clone → /install → /setup (real key) → /create-skill → /crq-run for MED →
  confirm `email.html` is produced and neutrally/branded per config.

## Out of scope (future specs)

- Other IDEs (Claude Code, Codex) — would extend `create-skill` to emit
  per-IDE artifacts.
- Mock mode in the operator flow.
- Weekly cadence / `rsm_dispatcher` integration.
- Multi-region fixture parity (only relevant if mock is ever reintroduced).

## Files added

```
.github/prompts/install.prompt.md        (committed)
.github/prompts/setup.prompt.md          (committed)
.github/prompts/create-skill.prompt.md   (committed)
crq.config.example.json                  (committed — neutral defaults to copy)
crq.config.json                          (per-install artifact — gitignored)
.github/prompts/crq-run.prompt.md        (generated by /create-skill — gitignored)
docs/.../<this spec>                      (committed)
```

`crq.config.json` holds **no secrets** (only `brand_label` + a bool), but it is a
**per-install artifact** (brand differs per client), so it is added to
`.gitignore` along with the generated `crq-run.prompt.md`. A committed
`crq.config.example.json` documents the shape. Secrets remain solely in `.env`
(already gitignored).

No changes to any file under `tools/`.
