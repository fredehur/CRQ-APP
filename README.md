# CRQ Geopolitical Intelligence Pipeline

A Top-Down Cyber Risk Quantification (CRQ) agentic pipeline built entirely with native Claude Code features. No LangChain, LangGraph, or CrewAI — just subagents, hooks, and Python tools.

---

## Core Philosophy

This system answers one question for every region it analyzes:

> **"How does this threat affect the company's ability to deliver business results?"**

Every output is a board-level executive brief. Technical jargon is forbidden by design — no CVEs, no malware hashes, no SOC terminology. Every threat is anchored to a **Value-at-Cyber-Risk (VaCR)** dollar figure so executives can make financial decisions, not security ones.

The jargon auditor hook enforces this automatically. If an agent produces a report with forbidden language, it is forced to rewrite it before the output is accepted.

---

## Agent Hierarchy

```
run-crq  (Orchestrator — opus)
├── gatekeeper-agent  (Triage — haiku)
│     Returns YES/NO: is there a credible active threat for this region?
│     Fast and cheap. Skips regions with no active trigger.
│
├── regional-analyst-agent  (Analysis — sonnet)  ×5 regions
│     Writes a 2–3 paragraph executive brief anchored to the VaCR figure.
│     └── Stop hook → jargon-auditor.py
│           Blocks approval if technical/SOC/budget language is detected.
│           Circuit breaker caps retries at 3 per region.
│
└── global-analyst-agent  (Synthesis — opus)
      Reads all approved regional briefs and cross-regional delta.
      Writes global_report.md and dashboard.html.
      └── Stop hook → jargon-auditor.py
            Same audit rules applied to the global report.
```

**Five operational regions:** APAC · AME (North America) · LATAM · MED (Mediterranean) · NCE (Northern & Central Europe)

---

## Quickstart

### Prerequisites

- [Claude Code](https://claude.ai/code) installed
- [uv](https://docs.astral.sh/uv/) installed

### Install dependencies

```bash
uv sync
```

### Run the full pipeline

```
/run-crq
```

This single command runs the complete pipeline:

| Phase | Action |
|-------|--------|
| 0 | Validate CRQ database schema |
| 1 | Gatekeeper triage → Regional analysis × 5 |
| 2 | Cross-regional delta brief |
| 3 | Global executive report + HTML dashboard |
| 4 | Export to PDF and PowerPoint |
| 5 | Report all output file paths |

### Run individual agents

```
/gatekeeper-agent          # Returns YES or NO for a given region/asset
/regional-analyst-agent    # Produces a single regional executive brief
/global-analyst-agent      # Synthesizes all regional briefs into a global report
```

---

## Output Files

All outputs are written to the `output/` directory:

```
output/
  regional/
    apac_draft.md          # Approved regional brief — APAC
    ame_draft.md           # Approved regional brief — AME
    latam_draft.md         # Approved regional brief — LATAM
    med_draft.md           # Approved regional brief — MED
    nce_draft.md           # Approved regional brief — NCE
  global_report.md         # Synthesized global board report
  dashboard.html           # Static HTML executive dashboard (no external deps)
  board_report.pdf         # PDF export for board distribution
  board_report.pptx        # PowerPoint export for board presentation
  .retries/                # Circuit breaker counters (auto-managed)
```

---

## Tools

| Tool | Description |
|------|-------------|
| `tools/regional_search.py <REGION> --mock` | Loads mock threat feed for a region |
| `tools/geopolitical_context.py <REGION>` | Returns static geopolitical risk context |
| `tools/threat_scorer.py <REGION>` | Returns max threat severity (1 / 2 / 3) |
| `tools/report_differ.py` | Cross-regional keyword delta brief |
| `tools/export_pdf.py <input.md> <output.pdf>` | Exports a markdown report to PDF |
| `tools/export_pptx.py <input.md> <output.pptx>` | Exports a markdown report to PowerPoint |

---

## Hooks

| Hook | Trigger | Action |
|------|---------|--------|
| `jargon-auditor.py` | Stop event on `regional-analyst-agent` | Audits `output/regional_draft_current.md` for forbidden language |
| `jargon-auditor.py` | Stop event on `global-analyst-agent` | Audits `output/global_report.md` for forbidden language |
| `crq-schema-validator.py` | Manual / Phase 0 | Validates `data/mock_crq_database.json` schema before pipeline runs |

The auditor checks for three categories of forbidden content:

- **Technical cyber jargon** — CVE identifiers, IP addresses, malware hashes
- **SOC operational language** — TTPs, IoCs, MITRE ATT&CK, lateral movement, C2
- **Unsolicited budget advice** — procurement, vendor recommendations, tool purchases

An audit failure returns `exit(2)`, which forces Claude Code to regenerate the output. A circuit breaker at `output/.retries/{label}.retries` caps retries at 3 to prevent infinite loops.

---

## Data

```
data/
  mock_crq_database.json          # CRQ scenarios keyed by region
  mock_threat_feeds/
    apac_threats.json             # Mock threat intelligence — APAC
    ame_threats.json              # Mock threat intelligence — AME
    latam_threats.json            # Mock threat intelligence — LATAM
    med_threats.json              # Mock threat intelligence — MED
    nce_threats.json              # Mock threat intelligence — NCE
```

All agents run in mock mode by default. No live API keys or external data sources are required.

---

## Architecture Notes

- **Model assignment is fixed in YAML frontmatter** — haiku for triage, sonnet for regional analysis, opus for orchestration and synthesis. Models cannot be overridden at runtime.
- **Regional analysts always write to a fixed temp path** (`output/regional_draft_current.md`) so the static Stop hook command can reference it by name. The orchestrator archives the approved draft to the region-specific path.
- **The global analyst is synthesis-only** — it reads from `output/regional/` and never touches raw threat feeds directly.
- **Dashboard uses inline CSS only** — no external frameworks, no CDN dependencies. Renders fully offline.

---

## Dependencies

Managed via `uv`. Defined in `pyproject.toml`.

| Package | Purpose |
|---------|---------|
| `fpdf2` | PDF export |
| `python-pptx` | PowerPoint export |
| `python-dotenv` | Environment variable management |
