# Seerist + RSM POC Slice (MED region)

Self-contained slice of the AeroGrid CRQ workspace, carved out so the **Seerist API** and the **RSM brief pipeline** can be tested on a different machine — specifically a workstation running VSCode + GitHub Copilot Enterprise where Claude Code is not available.

This slice is **MED-only**. The site registry, mock fixtures, and runtime behavior are all narrowed to the Mediterranean region.

## What is in this folder

| Path | Purpose |
|---|---|
| `tools/seerist_client.py` | Typed client for the Seerist HTTP API (`https://app.seerist.com/hyperionapi/`) |
| `tools/seerist_collector.py` | Pulls all Tier-1 Seerist data types and writes `output/regional/{region}/seerist_signals.json` |
| `tools/osint_physical_collector.py` | Tavily + Firecrawl OSINT collector (physical pillar) — has a mock mode |
| `tools/poi_proximity.py` | Joins Seerist + OSINT events with site coordinates → distance + cascade output |
| `tools/rsm_dispatcher.py` | Async per-region fan-out, emits placeholder mock briefs in `--mock` mode |
| `tools/rsm_input_builder.py` | Builds the structured input manifest the RSM formatter agent reads |
| `tools/notifier.py` | SMTP delivery (mock-friendly) |
| `tools/config.py` | Path constants used by the dispatcher |
| `tools/briefs/templates/` | Jinja2 brief templates (`rsm.html.j2`, `_partials.html.j2`) |
| `static/design/styles/rsm.css` | Brief styling |
| `data/aerowind_sites.json` | **MED-filtered** site registry — 3 sites (Casablanca, Palermo, Málaga) |
| `data/company_profile.json` | Crown jewels + footprint, used by the formatter |
| `data/mock_osint_fixtures/med_*.json` | Offline data so the pipeline runs without API keys |
| `docs/seerist/api-blueprint.apib` | Full Seerist API reference (Apiary blueprint) |
| `.claude/agents/rsm-*.md` | RSM agent prompts — see "Working without Claude Code" below |
| `tests/test_seerist_*.py` | Unit tests for the client and collector |

## Important: working directory

**Every command in this README assumes your shell is in `poc/seerist-rsm/`.** The Python files use `from tools.X` imports plus `Path(__file__).resolve().parent.parent` for repo-root resolution; both of those expect this folder to be the project root. If you run from a parent or child directory, imports and file lookups will silently fail.

```
cd poc/seerist-rsm
```

## Setup — option A: uv (recommended)

```
uv sync
uv run playwright install chromium    # only needed if you render PDFs
```

## Setup — option B: plain venv + pip (fallback)

```
python -m venv .venv
.venv\Scripts\activate                  # Windows
# source .venv/bin/activate             # macOS / Linux
pip install -r requirements.txt
playwright install chromium             # only if rendering PDFs
```

## Mock walkthrough — no API keys needed

This walks through the full RSM pipeline using the offline fixtures shipped in `data/mock_osint_fixtures/`. Every command writes a real artifact under `output/`.

```
# 1) Collect Seerist signals (reads med_seerist.json fixture)
python tools/seerist_collector.py MED --mock

# 2) Collect OSINT physical-pillar signals
python tools/osint_physical_collector.py MED --mock

# 3) Join events with the 3 MED sites and compute cascades
python tools/poi_proximity.py MED --mock

# 4) Run the daily dispatcher — produces mock placeholder briefs
python tools/rsm_dispatcher.py --daily --mock --region MED
```

After step 4 you should see:

```
output/regional/med/seerist_signals.json
output/regional/med/osint_physical_signals.json
output/regional/med/poi_proximity.json
output/regional/med/rsm_brief_med_<date>.md
output/delivery_log.json
```

Run the tests:

```
pytest tests/ -q
```

Note: `test_client_none_without_key` reads from the environment after `load_dotenv()` has already populated `os.environ`. On a fresh clone with no `.env` it passes; if you have a `SEERIST_API_KEY` exported in your shell or a `.env` further up the directory tree, that one test will fail. The other 7 cover the actual client logic.

## Live walkthrough — Seerist API

1. Copy the example env file and fill in your Seerist key:

   ```
   copy .env.example .env       # Windows
   # cp .env.example .env       # macOS / Linux
   ```

2. Edit `.env` and set `SEERIST_API_KEY=...`. (Optional: set `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `FIRECRAWL_API_KEY` to exercise the full live OSINT path.)

3. Run the same commands as above **without** `--mock`:

   ```
   python tools/seerist_collector.py MED
   python tools/osint_physical_collector.py MED
   python tools/poi_proximity.py MED
   python tools/rsm_dispatcher.py --daily --region MED
   ```

The collectors fall back to mock fixtures if the relevant API key is missing — so you can do a partial live test (e.g. Seerist live, OSINT mock) without errors.

## Working without Claude Code

The `.claude/agents/rsm-formatter-agent.md` and `.claude/agents/rsm-weekly-synthesizer.md` files are agent prompts originally invoked by Claude Code's subagent system. **They will not auto-execute under VSCode + Copilot.** Two options:

1. **Skip the agent layer.** `rsm_dispatcher.py --mock` writes placeholder briefs and works fine without a model in the loop. This is the right path for testing the Seerist API + data pipeline.

2. **Drive the formatter manually with Copilot.** When you want a real (non-placeholder) brief:
   - Run `python -c "from tools.rsm_input_builder import build_rsm_inputs; import json; print(json.dumps(build_rsm_inputs('MED', cadence='daily'), indent=2))"` to produce the input manifest.
   - Open `.claude/agents/rsm-formatter-agent.md` in VSCode.
   - Paste the agent prompt body (everything below the YAML frontmatter) into your Copilot chat, prepend `REGION: MED`, `CADENCE: daily`, `BRIEF_PATH: output/regional/med/rsm_brief_med.md`, and append the JSON manifest from the previous step.
   - The model writes the brief content; copy/save it to `BRIEF_PATH`.

## What's NOT in this slice

To keep this carve narrow and runnable, the following are intentionally absent:

- The full 5-region pipeline (`tools/orchestrator.py`, the global synthesis layer, `global-builder-agent`, `global-validator-agent`)
- The risk register, source librarian, and validation pipeline
- The board / CISO PDF brief renderers and their templates
- The CRQ Overview / Reports dashboard (`server.py`, the FastAPI app)
- The full test suite — only the two Seerist tests are included
- All `.claude/hooks/` (stop-hook validators, telemetry). The `Stop:` hook reference inside `rsm-formatter-agent.md` will not resolve — ignore it; it has no effect outside Claude Code.

If you need any of those, pull from the parent repo (branch `poc/seerist-rsm-med` was carved from `main`).

## Limitations

- This slice does not run the global synthesis or validation layers — output is regional only.
- Briefs in `--mock` mode are placeholders, not analyst-quality. To produce real briefs you must drive the formatter with Copilot or another model.
- `tools/notifier.py` will silently no-op on missing SMTP env vars.
