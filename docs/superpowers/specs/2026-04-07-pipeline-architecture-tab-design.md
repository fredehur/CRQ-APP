# Pipeline Architecture Tab — Design Spec
**Date:** 2026-04-07
**Status:** Draft — awaiting user approval

---

## Purpose

A new top-level tab in the CRQ app that makes the agentic intelligence pipeline fully transparent. Two audiences, one tab:

- **Operators and new analysts** — understand how the system is built, how agents interact, what principles govern the pipeline, why agentic AI produces trustworthy output rather than hallucinated output
- **Senior intelligence analysts** — understand the analytical methodology, how certainty is constructed, what the Admiralty ratings mean at each step, how peer review is enforced structurally

The tab is purely architectural — no live run data. It answers: *"how does this system work and why can I trust what it produces?"* Run evidence lives in the other tabs.

---

## Core Design Principle

**The agentic framework is the foundation. Show it, name it, explain it.**

Concepts like parallel fan-out, stop hooks, builder/validator pairing, deterministic gates, and circuit breakers are not jargon to hide — they are the mechanisms that make the pipeline trustworthy. The tab explains every agentic concept clearly. Similarly, every intelligence methodology concept (Admiralty ratings, corroboration, chain of custody, analytical independence) is explained in full. Neither layer is subordinate to the other. Both are present throughout.

---

## Tab Placement and Navigation

- New top-level nav tab: **"Pipeline"**
- Sits between "Config" and any future tabs
- The Config tab loses its **Prompts sub-tab** (`cfg-nav-prompts` / `cfg-tab-prompts`). Intelligence Sources and Footprint sub-tabs are unchanged.
- Prompt editing moves into the Pipeline tab's side panel as the canonical location for agent configuration.

---

## Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  [fixed header — nav tabs]                                      │
├─────────────────────────────────────────────────────────────────┤
│  [Intelligence Requirement Banner — full width, fixed]          │
│  [Admiralty Scale Legend — full width, fixed]                   │
├──────────────────────────────┬──────────────────────────────────┤
│                              │                                  │
│   Pipeline Flow              │   Side Panel                     │
│   (scrollable, ~62% width)   │   (slides in on node click,     │
│                              │    ~38% width, scrollable)       │
│                              │                                  │
│                              │   [hidden by default]            │
└──────────────────────────────┴──────────────────────────────────┘
```

---

## Fixed Header Elements

### Intelligence Requirement Banner

A single line, always visible below the nav:

> **Analytical Requirement:** Does a credible geopolitical or cyber threat exist in any of AeroGrid's five operational regions that could materially disrupt operations, supply chains, or safety at critical assets?

Styled as a dim, monospace label — not a hero element. Its purpose is to anchor the *why* before the diagram begins.

### Admiralty Scale Legend

A compact, always-visible strip below the banner showing the full 4×4 Admiralty matrix:

- Reliability axis (A–D): Completely Reliable → Not Usually Reliable
- Credibility axis (1–4): Confirmed → Doubtful
- Combined examples: A1 = highest confidence, D4 = lowest
- A note: *"Admiralty ratings are assigned by the Gatekeeper at triage and propagate through the full pipeline. They reflect source quality and corroboration — not model confidence."*

This legend is referenced by every node that mentions an Admiralty rating. It never disappears.

---

## Pipeline Flow Diagram

### Visual structure

Vertical flow, top to bottom. Nodes connected by thin lines with a **subtle animated dot** (CSS `@keyframes` on a pseudo-element — no JS library). The dot travels continuously, indicating live system, not a specific run.

### Color coding — by analytical phase

Four phases, four colors drawn from the existing app palette:

| Phase | Color | Hex | What it covers |
|---|---|---|---|
| Collection | Blue | `#79c0ff` | Signal acquisition, environment validation, OSINT toolchain |
| Assessment | Green | `#3fb950` | Gatekeeper triage, Regional Analyst, Threat Scorer |
| Review | Amber | `#e3b341` | Stop hooks, Jargon Auditor, Global Validator (devil's advocate) |
| Product | Purple | `#a371f7` | Global Builder, Velocity/Trend synthesis, Dashboard, Export, Archive |

### Node anatomy

Each node shows:
```
[phase number badge]  [PHASE NAME]                    [phase color dot]
[one-line analytical role]
[agent/tool label]  [model badge if LLM]  [type badge]
```

**Type badges:**
- `deterministic` — Python tool, no LLM, computed output
- `llm-agent` — Claude sub-agent, model-driven reasoning
- `quality-gate` — validator/auditor, independent check
- `orchestrator` — Opus, coordinates but does not produce content

**Agentic concept labels** appear directly on the diagram as small secondary tags on relevant nodes/connectors:
- `parallel fan-out ×5` on the Phase 1 branch point
- `stop hook` on nodes with exit-code-gated validators
- `builder / validator pair` on the Global Builder + Global Validator connector
- `circuit breaker` on the Global Validator (max 2 rewrite cycles)
- `fan-in` on the post-regional quality gate pass
- `filesystem as state` as a connector annotation explaining how agents communicate

These terms are not explained inline — clicking the node reveals their explanation in the side panel.

### Phase nodes — full list

**Phase 0 — Validate & Initialise** `[deterministic]` `[Collection]`
- Schema validator, environment check, OSINT mode detection, prior feedback load, footprint context build
- Analytical role: *Establish collection parameters. Verify the pipeline has what it needs before any intelligence work begins.*

**Phase 1 — Signal Acquisition** `[parallel fan-out ×5]` `[Collection]`
- Five regional pipelines run simultaneously. Each runs: OSINT collector → YouTube signals → Scenario mapper → Collection quality gate → Geopolitical context builder
- Analytical role: *Acquire raw signals from open sources across all five regions in parallel. No analytical judgment yet — collection only.*
- Shows 5 regional sub-tracks as horizontal rows, each labelled (APAC / AME / LATAM / MED / NCE). Each row shows an illustrative outcome badge (`ESCALATE` / `MONITOR` / `CLEAR`) in severity colors — these are architectural labels explaining what each outcome means, not live run data. Clicking any regional row scopes the side panel to that region's pipeline description.

**Phase 1a — Gatekeeper Triage** `[llm-agent]` `[haiku]` `[Assessment]`
- Reads geo + cyber signals + scenario map. Assigns Admiralty rating. Routes: ESCALATE / MONITOR / CLEAR.
- Analytical role: *Binary triage. Determines whether evidence meets the threshold for full analytical treatment. Assigns confidence grade.*
- Agentic concept: *The Gatekeeper is a lightweight fast model (Haiku). Speed and cost efficiency for a decision that is binary — escalate or don't. No narrative, no report. One word output plus a structured JSON decision file.*

**Phase 1b — Regional Analyst** `[llm-agent]` `[sonnet]` `[stop hook]` `[Assessment]`
- Runs only for ESCALATED regions. Produces report.md, data.json, signal_clusters.json, sections.json.
- Analytical role: *Full analytical treatment. Scenario identification, threat actor attribution, impact assessment, recommended actions. Three-pillar structure: geopolitical context → adversary activity → AeroGrid impact.*
- Agentic concept: *Output is not accepted until it passes a stop hook. The agent cannot mark itself done — an external auditor must pass it first.*

**Phase 1c — Jargon Auditor** `[deterministic]` `[quality-gate]` `[stop hook]` `[Review]`
- Runs on every regional report. Catches: SOC language, pipeline references, generic source labels, fabricated citations, VaCR jargon.
- Analytical role: *Enforces the analytical voice standard. Intelligence briefs must read as assessments, not as system logs.*
- Agentic concept: *A deterministic Python script — no LLM. Exit code 0 = pass. Exit code 2 = fail with violations listed. On failure, the regional analyst is re-delegated with the exact violation list. Caps at 1 rewrite.*

**Phase 2 — Velocity Analysis** `[deterministic]` `[Collection]`
- Reads archived runs. Computes escalation frequency per region. Patches velocity into data.json.
- Analytical role: *Historical pattern — is this region escalating more frequently? Velocity contextualises a single assessment within the run history.*

**Phase 2.5 — Trend Synthesis** `[llm-agent]` `[sonnet]` `[Assessment]`
- Reads all archived run data. Produces trend_analysis.json with longitudinal patterns.
- Analytical role: *Cross-run intelligence — identifies acceleration, stabilisation, or reversal of threat patterns across regions and scenarios.*

**Phase 3 — Cross-Regional Diff** `[deterministic]` `[Assessment]`
- Compares current run to prior run. Produces delta brief highlighting what changed.
- Analytical role: *Change detection. What is new this cycle that was not present last cycle?*

**Phase 4 — Global Builder** `[llm-agent]` `[sonnet]` `[builder/validator pair]` `[Product]`
- Synthesises all approved regional briefs into global_report.json. Stop hooks validate JSON schema + jargon.
- Analytical role: *Cross-regional synthesis. Identifies shared patterns, escalation clusters, velocity trends. Produces the executive intelligence picture.*
- Agentic concept: *The Global Builder is one half of a builder/validator pair. It produces the output. It does not validate its own output. A separate agent does that.*

**Phase 4b — Global Validator** `[llm-agent]` `[haiku]` `[quality-gate]` `[circuit breaker]` `[Review]`
- Devil's advocate. Reads only the finished global_report.json against regional source files. Returns APPROVED or REWRITE.
- Analytical role: *Independent peer review. The validator has no access to the builder's reasoning process — only the finished product and the source material it should reflect.*
- Agentic concept: *Structural independence is the key mechanism here. The validator is spawned as a separate agent with no shared conversation context. It cannot be influenced by the builder's reasoning. If it returns REWRITE twice, a circuit breaker force-approves — preventing infinite loops.*

**Phase 5 — Export** `[deterministic]` `[Product]`
- Generates dashboard.html, board_report.pdf, board_report.pptx, ciso_brief.docx.
- Analytical role: *Format-specific dissemination. Same intelligence product rendered for different audiences: CISO, board, regional security managers.*

**Phase 6 — Archive & Finalise** `[deterministic]` `[Product]`
- Archives run, updates source registry, builds history, generates feedback trends.
- Analytical role: *Institutional memory. Every run is preserved and feeds the next cycle's velocity analysis and trend synthesis.*

**Phase 7 — RSM Briefs** `[llm-agent]` `[sonnet]` `[Product]` `[optional]`
- Conditional on `--rsm` flag. Generates weekly INTSUMs per region for field security managers.
- Analytical role: *Tactical dissemination. Region-specific operational briefs for the people on the ground.*

---

## Side Panel

Slides in from the right when any node is clicked. Remains visible until explicitly closed (×). Scrollable independently of the main flow.

### Structure — three sections, always in this order

---

**Section 1: Intelligence Methodology**
Label: `ANALYTICAL ROLE`

- What analytical function this step performs in plain language
- What question it answers (e.g. "Does a credible threat exist that warrants full analysis?")
- What it contributes to the certainty of the final product
- How it maps to standard intelligence tradecraft (where applicable: collection, triage, assessment, peer review, dissemination)
- Input → Output expressed in analytical terms (not file names)

---

**Section 2: Agentic Architecture**
Label: `HOW THIS IS BUILT`

- Agent type and model (if LLM), or tool name (if deterministic)
- Why that model/approach was chosen (e.g. "Haiku for speed on a binary decision; Sonnet for nuanced analytical synthesis")
- What agentic principles govern this step — each explained in plain language:
  - **Stop hook:** *"The agent's output is rejected by default. An external validator must explicitly pass it before the pipeline continues. The agent cannot self-certify."*
  - **Builder/Validator pair:** *"Two separate agents handle production and review. The validator has no access to the builder's conversation — it reads only the finished output. This prevents the validator from being influenced by the builder's reasoning, intentional or not."*
  - **Circuit breaker:** *"If a rewrite loop runs more than twice, the pipeline force-approves and logs the failure. This prevents infinite loops while preserving the audit trail of what failed."*
  - **Parallel fan-out:** *"Five regional pipelines run simultaneously, each writing to their own output directory. They share no state. This is not just an efficiency choice — it means each region's assessment is independent of the others."*
  - **Filesystem as state:** *"Agents communicate through files, not memory. Each agent reads what the previous one wrote to disk. This means the pipeline is fully auditable — every handoff is a file you can inspect."*
  - **Deterministic gate:** *"This step runs Python code with no LLM involved. The output is computed from the input. It cannot hallucinate."*
- Input files → Output files (exact paths)
- What happens on failure (exit codes, rewrite loops, circuit breakers)

---

**Section 3: System Configuration**
Label: `AGENT CONFIGURATION`

- Only shown for `llm-agent` nodes (not deterministic tools)
- Visual separator and distinct label makes clear this is configuration, not methodology
- Agent selector (pre-selected to the clicked node's agent)
- Frontmatter display: model, tools, hooks — read-only rendered fields
- Prompt body: editable textarea (same functionality as current Config > Prompts)
- Save button — saves to `.claude/agents/{agent}.md`
- Note: *"Changes affect future pipeline runs, not the current architectural description above."*

---

## Agentic Concepts Glossary

A collapsible section at the bottom of the main pipeline flow (before the footer). Not in the side panel — lives in the main flow as a reference for anyone reading the diagram without clicking nodes.

Defines:
- Agent / Sub-agent
- Orchestrator
- Stop hook
- Builder / Validator pair
- Circuit breaker
- Parallel fan-out
- Fan-in
- Deterministic gate
- Filesystem as state
- Model selection (why Haiku vs Sonnet vs Opus for different tasks)

Each definition: 2–3 sentences, no jargon, no hedging.

---

## What Is Removed

| Location | What is removed | Where it moves |
|---|---|---|
| Config tab | Prompts sub-tab (`cfg-nav-prompts`, `cfg-tab-prompts`, agent `<select>`, textarea, save button) | Pipeline tab — side panel Section 3 |
| Config tab nav | "Prompts" nav item | Removed |

Intelligence Sources and Footprint sub-tabs: unchanged.

---

## API Requirements

No new API endpoints required. The side panel prompt editor reuses the existing `/api/agents` read/write endpoints that the Config > Prompts tab already calls.

The pipeline flow diagram is fully static HTML/CSS — no data fetching. Node content (role descriptions, agentic explanations, file paths) is hardcoded in the spec, rendered at page load.

---

## Non-Goals

- No live run data in this tab — run evidence belongs in Overview, Validate, Source Audit, History
- No real-time pipeline progress (that is the progress bar in the header)
- No new backend tooling or log parsing
- No interactive simulation of the pipeline

---

## Success Criteria

A senior analyst who has never seen this system before can, after 10 minutes with this tab:

1. Explain the analytical methodology in their own words
2. Identify which steps use LLM reasoning and which are deterministic
3. Explain what stops the system from producing fabricated intelligence
4. Understand what an Admiralty rating means and where it comes from
5. Know where to go to read or edit an agent's instructions

A developer who is new to agentic systems can, after 10 minutes:

1. Explain what a stop hook is and why it matters
2. Explain why builder/validator separation prevents echo-chamber validation
3. Understand why filesystem-as-state makes the pipeline auditable
4. Know the difference between a deterministic gate and an LLM agent in this context
