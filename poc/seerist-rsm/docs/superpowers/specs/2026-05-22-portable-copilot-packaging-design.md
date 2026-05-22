# Portable Copilot Packaging Layer — Design

**Date:** 2026-05-22
**Slice:** `poc/seerist-rsm`
**Status:** Draft for review (revised after independent design review + `/prime-dev` boundary alignment)

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
- **Orchestration lives in code, not the prompt file.** `agent-boundary-principles.md`
  names "orchestration in a markdown file an LLM follows" as the #1 failure mode
  ("works 90% of the time; the other 10% is invisible"). So the region loop,
  phase sequencing, config→flags translation, date threading, and `--require-live`
  enforcement are owned by a new deterministic orchestrator, **`tools/crq_run.py`**.
  The Copilot agent owns only the two genuine judgment steps (analyst, formatter).
  This adds one new tool (`crq_run.py`); the only existing tools touched are the
  OSINT additions (`osint_physical_collector.py` self-contained primitives +
  `poc_runner.py` `--osint` wiring — see the OSINT section).

## Architecture

Two layers:

1. **Code orchestrator** — `tools/crq_run.py` (new). Owns everything
   deterministic: read `crq.config.json` + per-run args, resolve today's date
   once, expand/validate the region list, translate config→`poc_runner` flags
   (`--no-org-context`, `--brand`, `--require-live`), sequence the phases across
   regions, and persist run state. Unit-testable Python. **Pauses** at the two
   points that require judgment (analyst, formatter) by exiting after a batch
   with a clear "AGENT STEP REQUIRED" message.
2. **Markdown packaging** under `.github/prompts/` — three authored prompt files
   (`install`, `setup`, `create-skill`) + one generated (`crq-run`). The
   generated `crq-run` skill is now **thin**: it collects the operator's per-run
   answers, calls `crq_run.py` for each deterministic batch, and performs the two
   authoring steps in between. It contains no loops, sequencing, or flag logic.

Config in `crq.config.json` (defaults) + `.env` (secrets). The agent runs in
agent mode with file-edit + terminal tools (frontmatter contract below).

## OSINT physical-pillar mode (per-run, added)

A second optional mode, asked per run alongside region + org/region-guided:
**include the OSINT physical pillar** (web/news enrichment via Tavily + Firecrawl)
or run Seerist-only. Mirrors the org-context pattern: a `osint_default` in
`crq.config.json` set by `/setup`, overridable per run in `/crq-run`.

**Making OSINT genuinely live (the real fix).** `osint_physical_collector.py`
today imports `_tavily_search` / `_firecrawl_extract` from `tools.osint_collector`
— **functions that do not exist there**, so its live path always falls back to
mock. `osint_collector.py` itself is a heavy 3-LLM-call loop (deps: `anthropic`,
`collection_gate`, `osint_search`, `firecrawl_scraper`, several data files) and
is the wrong thing to port. Instead, make `osint_physical_collector.py`
self-contained: replace the broken import with two in-file primitives mirroring
the working code —
- `_tavily_search(query, max_results)` → `httpx` POST to `https://api.tavily.com/search`
  (mirrors `osint_search.py:search_tavily`),
- `_firecrawl_extract(url)` → `FirecrawlApp(...).scrape_url(...)` returning main
  content + location (mirrors `firecrawl_scraper.py:_call_firecrawl`).
The slice already declares `httpx`, `firecrawl-py`, `tavily-python` in
`pyproject.toml`, so no new deps. OSINT queries are **region-keyed**
(`"{region} unrest protest 2026"` etc.), so the mode is safe in both
org-grounded and region-guided runs (no site names).

**Fail loudly on missing keys.** When OSINT is requested for a live run and
`TAVILY_API_KEY` (and Firecrawl) are absent, stop with a clear message —
mirroring the Seerist `--require-live` guard. No silent mock fallback. Add a
`require_live` path to `osint_physical_collector.collect()` (and a guard in
`poc_runner.phase_collect`) so the live-only guarantee holds for OSINT too.

**Plumbing (mirrors org-context exactly):**
- `crq.config.json` gains `osint_default: bool`.
- `/setup` asks for it; `crq.config.example.json` documents it.
- `crq_run.py collect` gains `--osint` / `--no-osint` (override; default from
  config), resolved like org-context, and threads `--osint` into the
  `poc_runner --collect` argv.
- `poc_runner.phase_collect` gains an `osint` param + `--osint` CLI flag. When
  set, after the Seerist collect it guards the keys (fail loudly) and runs the
  OSINT collector, writing `output/regional/{region}/osint_physical_signals.json`
  — which `build_rsm_inputs` already reads (the downstream wiring exists; the
  manifest's "skip the physical-OSINT layer" fallback fires only when OSINT is off).
- `/crq-run` asks the operator "Include OSINT physical-pillar enrichment?" and
  passes the override.

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

`crq_run.py` reads and validates this config (a small typed loader with a unit
test). Missing/invalid → `crq_run.py` exits non-zero with a message telling the
operator to run `/setup`.

### 0. `tools/crq_run.py` (the code orchestrator) — the one new tool

Owns all deterministic orchestration the prompt file must NOT. Three
subcommands mirroring the pipeline's natural batch boundaries:

| Subcommand | What it does (code-owned) | Then |
|---|---|---|
| `crq_run.py collect --regions MED NCE \| ALL [--region-guided]` | Load config; resolve **today's date once**; expand/validate regions (`ALL`→5 codes); translate flags; for each region run `poc_runner.py <R> <DATE> --collect --require-live [--no-org-context] --brand "<brand>"`; write `crq_run_state.json` (date, regions, org_context, brand). | Print each region's `analyst_request.md` path + "AGENT STEP REQUIRED: write claims.json + analyst_report.md, then run `crq_run.py prep`." |
| `crq_run.py prep` | Read run-state; for each region run `poc_runner.py <R> <DATE> --prep-format`. | Print each `formatter_request.md` path + "AGENT STEP REQUIRED: write brief.md, then run `crq_run.py render`." |
| `crq_run.py render` | Read run-state; for each region run `poc_runner.py <R> <DATE> --render`. | Print each `email.html` path. |

Why three subcommands and not one unattended run: the two judgment steps
(analyst, formatter) must happen *between* phases and require the agent. Code
owns the loop, sequencing, flags, date, and state; the agent owns only the two
authoring steps. `crq_run.py` performs **no LLM calls** and makes **no judgment**
— it is pure orchestration, fully unit-testable.

Inputs: `crq.config.json`, `.env`, CLI args (regions, `--region-guided` /
`--org-grounded` overriding the config default, optional `--date`). Outputs:
per-region `poc_runner` invocations + `crq_run_state.json`. Failure modes:
missing/invalid config → exit non-zero (point to `/setup`); unknown region →
exit non-zero; `poc_runner` non-zero (e.g. `--require-live` with no key) →
surface verbatim and stop.

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
2. Generate the **thin** `.github/prompts/crq-run.prompt.md` (see §5), emitting
   **the correct frontmatter into the generated file** (`agent: agent`,
   `tools: ['editFiles', 'runCommands']`) — not just a body. The generated skill
   delegates all orchestration to `crq_run.py` (which reads `crq.config.json`
   itself at run time), so it does not hard-code config values — it only carries
   the operator Q&A and the two authoring steps.
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

### 5. The generated `crq-run.prompt.md` — the run skill (thin)

With orchestration in `crq_run.py`, the run skill is now a short conversational
wrapper. It contains **no loops, no phase sequencing, no flag logic** — only the
operator Q&A and the two authoring steps:

1. Ask the operator: which region(s)? org-grounded or region-guided (default
   from `org_context_default`)?
2. Run `uv run python tools/crq_run.py collect --regions <...> [--region-guided]`.
3. For **each** `analyst_request.md` path it prints: read it and **write
   `claims.json` + `analyst_report.md`** per the authoring contract below.
4. Run `uv run python tools/crq_run.py prep`.
5. For **each** `formatter_request.md` path it prints: read it and **write
   `brief.md`** per the authoring contract.
6. Run `uv run python tools/crq_run.py render`; report the `email.html` paths.

All sequencing, the region loop, the single shared date, flag translation, and
`--require-live` live in `crq_run.py` — the skill just relays the operator's
answers in and the LLM authoring out. The two authoring steps (3 and 5) are
**distinct prompts read at different times**: `formatter_request.md` does not
exist until `crq_run.py prep` runs.

#### Agent authoring contract (what the run skill must tell the agent)

`crq_run.py render` → `poc_runner --render` enforces deterministic gates the
agent cannot see while writing. The generated `crq-run` skill must spell these
out so agent-authored files pass on the first try:

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
  → /create-skill (generates the thin crq-run.prompt.md)
  → (reload window if needed)
  → /crq-run      (asks region(s) + org/region-guided, then:
                     crq_run.py collect → agent writes claims/report
                   → crq_run.py prep    → agent writes brief
                   → crq_run.py render  → email.html per region)
```

## Error handling

- **install:** missing Python/`uv` → stop with install guidance.
- **setup:** missing/empty `SEERIST_API_KEY` → stop, point to `.env.example`.
  No mock fallback.
- **create-skill:** missing/invalid `crq.config.json` → stop, point to `/setup`.
- **crq_run.py:** missing/invalid config or unknown region → exit non-zero with a
  pointer to `/setup`; any `poc_runner` non-zero exit (e.g. `--require-live` with
  no key, or a missing phase-precondition file) is surfaced verbatim and stops
  the run. `--require-live` is always passed on collect, so a missing key fails
  loudly rather than silently falling back to mock.
- **Date consistency:** the resolved date is stated explicitly to the operator
  and reused; a re-run on a later day starts a fresh dated directory. Caveat:
  `rsm_input_builder._filter_notable_dates` keys its 7-day horizon off the real
  UTC "today", not the supplied `date_iso` — so backfilling a non-today date
  filters notable dates against the wrong anchor. Low impact for same-day runs;
  noted so it isn't mistaken for a bug.

## Testing / verification

Moving orchestration into `crq_run.py` makes the previously-untestable parts
**unit-testable** — the core win of this revision. Verification splits three ways:

- **`crq_run.py` unit tests (`tests/test_crq_run.py`)** — the real coverage:
  - config load + validation (valid, missing, malformed → correct exit).
  - region expansion: `ALL` → the 5 region codes; unknown region → non-zero exit.
  - **flag translation**: `--region-guided` → `--no-org-context`; `--brand` always
    passed; `--require-live` always on collect. Assert the exact `poc_runner`
    argv built per region (mock/patch the subprocess call — no live API needed).
  - single shared **date** threaded across collect/prep/render via `crq_run_state.json`.
  - run-state round-trip (collect writes it; prep/render read it).
- **Static checks (authoring time):**
  - `crq.config.example.json` validates against the schema.
  - the generated `crq-run.prompt.md` has well-formed frontmatter (`agent: agent`,
    `tools: ['editFiles', 'runCommands']`) and a body, and contains no orchestration
    logic (delegates to `crq_run.py`).
- **Operator acceptance walkthrough (live, manual):** clone → /install → /setup
  (real key) → /create-skill → /crq-run for MED → confirm `email.html` is
  produced. (Full live run can't execute in the authoring env: no live
  `SEERIST_API_KEY`, and `truststore` is absent, so the live collector path
  can't run locally — hence the unit tests mock the subprocess boundary.)

## Out of scope (future specs)

- Other IDEs (Claude Code, Codex) — would extend `create-skill` to emit
  per-IDE artifacts.
- Mock mode in the operator flow.
- Weekly cadence / `rsm_dispatcher` integration.
- Multi-region fixture parity (only relevant if mock is ever reintroduced).

## Files added

```
tools/crq_run.py                         (committed — the code orchestrator)
tests/test_crq_run.py                    (committed — unit tests)
.github/prompts/install.prompt.md        (committed)
.github/prompts/setup.prompt.md          (committed)
.github/prompts/create-skill.prompt.md   (committed)
crq.config.example.json                  (committed — neutral defaults to copy)
crq.config.json                          (per-install artifact — gitignored)
crq_run_state.json                       (per-run artifact — gitignored)
.github/prompts/crq-run.prompt.md        (generated by /create-skill — gitignored)
docs/.../<this spec>                      (committed)
```

`crq.config.json` holds **no secrets** (only `brand_label` + a bool), but it is a
**per-install artifact** (brand differs per client), so it — along with the
generated `crq-run.prompt.md` and the per-run `crq_run_state.json` — is added to
`.gitignore`. A committed `crq.config.example.json` documents the shape. Secrets
remain solely in `.env` (already gitignored).

**`tools/` change scope:** adds one new file, `tools/crq_run.py` (the
orchestrator). The existing tools (`poc_runner.py`, `seerist_collector.py`,
`rsm_input_builder.py`, validators, renderer) are **unchanged** — `crq_run.py`
drives them through their existing CLIs.
