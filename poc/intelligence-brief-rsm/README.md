# Regional Intelligence Brief POC

Portable proof of concept for producing regional security intelligence briefs with VS Code, GitHub Copilot, Seerist, and optional OSINT enrichment.

The pipeline collects regional signals, turns them into an analyst-ready brief, normalizes citations, and renders an email-safe HTML output.

## What It Produces

Each run creates a dated package under:

```text
output/briefs/<date>/<REGION>/
```

Primary output:

```text
email.html
```

Common supporting files:

```text
brief.md
claims.json
analyst_report.md
formatter_request.md
_rsm_manifest_daily.json
intel_decisions.md
```

## Main Workflow

Use the Copilot slash commands in VS Code.

One-time setup:

| Step | Command | Purpose |
|---|---|---|
| 1 | `/install` | Install dependencies and create local environment files. |
| 2 | Edit `.env` | Add required API keys. |
| 3 | `/setup` | Write `crq.config.json` with brand, grounding, timeframe, and OSINT defaults. |
| 4 | `/create-skill` | Create or refresh the `/intel-brief` command. |

Run a brief:

```text
/intel-brief
```

Copilot asks for region, grounding mode, and OSINT mode, then runs the collection, analysis, formatting, and render flow.

## Supported Regions

```text
APAC
AME
LATAM
MED
NCE
ALL
```

The region list is defined in `tools/crq_run.py`.

## Grounding Modes

Region-guided briefs describe the regional risk picture without company-specific exposure.

Organization-grounded briefs include site and company context where site data exists.

If organization grounding is requested for a region without configured sites, the run falls back to region-guided mode for that region.

## OSINT Mode

OSINT mode adds physical-risk web/news enrichment on top of Seerist signals.

Required when OSINT is enabled:

```text
TAVILY_API_KEY
FIRECRAWL_API_KEY
```

Required for live Seerist collection:

```text
SEERIST_API_KEY
```

API keys belong in `.env`.

## Manual CLI

Run commands from the POC folder:

```powershell
cd poc/intelligence-brief-rsm
```

Collect:

```powershell
uv run python tools/crq_run.py collect --regions NCE --osint
```

Analyze:

```powershell
uv run python tools/crq_run.py analyze
```

Prepare formatter inputs:

```powershell
uv run python tools/crq_run.py prep
```

Render:

```powershell
uv run python tools/crq_run.py render
```

Multiple regions:

```powershell
uv run python tools/crq_run.py collect --regions NCE MED APAC --osint
```

All regions:

```powershell
uv run python tools/crq_run.py collect --regions ALL --osint
```

## Setup

Recommended:

```powershell
uv sync
```

Fallback:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Install browser support only if needed for PDF/browser rendering:

```powershell
uv run playwright install chromium
```

## Email Rendering

The active renderer is:

```text
tools/render_brief_html.py
```

The active email template is:

```text
tools/briefs/templates/rsm_email.html.j2
```

The renderer converts `brief.md` into `email.html`, applies inline email-safe styles, creates citation anchors, and links appendix source IDs when URLs are available.

Logo lookup order:

```text
VESTAS_LOGO_PATH
CRQ_BRAND_LOGO_PATH
static/design/logo/Vestas_Primary_Logo_RGB.png
static/design/logo/brand-logo.png
```

If no logo is available, the template renders a text brand mark.

## Important Files

| Path | Purpose |
|---|---|
| `tools/crq_run.py` | Main orchestrator behind `/intel-brief`. |
| `tools/poc_runner.py` | Per-region phase runner. |
| `tools/seerist_client.py` | Seerist API client. |
| `tools/seerist_collector.py` | Seerist signal collection. |
| `tools/osint_physical_collector.py` | OSINT physical-risk collection. |
| `tools/poi_proximity.py` | Site proximity and cascade calculations. |
| `tools/rsm_input_builder.py` | Formatter input manifest builder. |
| `tools/normalize_citations.py` | Citation rewrite and appendix generation. |
| `tools/validate_brief.py` | Brief validation. |
| `tools/render_brief_html.py` | HTML email renderer. |
| `tools/briefs/templates/rsm_email.html.j2` | Active email template. |
| `.github/prompts/*.prompt.md` | Copilot command definitions. |
| `crq.config.example.json` | Example setup config. |
| `data/aerowind_sites.json` | Site registry for organization-grounded briefs. |
| `data/company_profile.json` | Company profile context. |

## Local Artifacts

Runtime files:

```text
.env
.venv/
crq.config.json
crq_run_state.json
output/
```

## Tests

```powershell
uv run pytest tests/ -q
```

Render validation is part of:

```powershell
uv run python tools/crq_run.py render
```

## Scope

This POC covers regional brief generation and email rendering.

Out of scope:

- Production dashboard
- Case management
- Long-term alert storage
- Automated approval workflow
- Global executive synthesis

