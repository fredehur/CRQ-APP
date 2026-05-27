# Product Vision — Operational Risk Model

**Status:** Aspirational. Not the current scope. This is the endgame the daily-brief PoC is a downpayment on.

**Current scope:** Daily regional brief, RSM as primary reader, MED region demonstrably grounded with site context, the other four regions producing region-guided briefs from the same pipeline. Proof of work that we can ingest Seerist + OSINT and produce a credible, decision-grade brief.

This file captures the bigger picture we want to come back to once the brief PoC is delivered.

---

## The reframe

The current product is a **better newsletter**. The endgame is a **continuous operational risk model of an org plus the world, with the brief as one of many lenses on that model.**

The newsletter has a real ceiling — mostly mid-market consulting engagements, somewhere in the low-to-mid six figures of ARR for a small team. The model has a different ceiling: every product (brief, dashboard, chatbot, decision packets, multi-persona views, underwriter feeds) is a lightweight consumer of the same spine. That's the same insight that made Bloomberg, Stripe, and Tableau category-definers — own the abstraction layer, let downstream products be small.

## What "model" actually means

A continuously updated, queryable representation of the org's exposure surface, evaluated against the world.

**Three layers:**

1. **Org surface** — declarative representation of what the operator cares about:
   - Sites (location, criticality, personnel, expat count, shift pattern, dependencies, customer commitments, country lead, embassy contact, notable dates, standing notes)
   - Customers / contracts (PPAs, SLAs, penalty clauses, exposure rating)
   - Vendors / supply chain (single-point-of-failure flags, geography, criticality tier)
   - Routes (shipping lanes, road corridors, air mobility)
   - People (key personnel, knowledge holders, travel posture, family location)
   - Single-points-of-failure (people, vendors, geographies, IP)

2. **World signals** — continuous ingestion:
   - Seerist (analyst-vetted events, hotspots, scribe, risk ratings, threat actor context)
   - OSINT (Tavily + Firecrawl + future: multi-language, local sources)
   - Future: internal feeds (HR system → who's where; procurement → vendor changes; ERP → production criticality; CRM → customer events)
   - Future: weather, insurance premium feeds, court rulings, election calendars, regulatory pipelines

3. **Scoring engine** — maps world signals to org surface elements:
   - Per-element exposure score, updated continuously
   - Trajectory state per active narrative
   - Cascade graph (how an event in node A propagates to nodes B, C, D in the org graph)
   - Threshold detection (when does an exposure cross "act now")

The brief is then a templated *view* over this model. Other views fall out for free.

## The big bets that flow from the model

Ordered by upside-vs-effort for our 2-person shape:

### 1. Question-answer mode

Chat interface backed by the same model. The RSM doesn't only read briefs — they ask:
- *"Is there any reason to delay Karim's Madrid trip Tuesday?"*
- *"Which PPAs are most exposed in Q3?"*
- *"Show me everywhere we've had a port-related event in the last 90 days."*

The brief becomes one query template among many. Massive productivity multiplier with the same underlying data.

### 2. Decision packets (event-driven, not clock-driven)

No daily push. Instead: every change above a per-org threshold generates a decision packet:
> Casablanca strike enters day 2. Affects med-casablanca-ops + ONEE PPA.
> Decision points: (1) hold nacelle shipment Y/N · (2) elevate guard rotation Y/N · (3) brief Karim Benali Y/N.
> Each option carries expected cost + impact estimate.

The RSM clears their morning by approving/denying packets, not reading prose. Cadence follows events, not the clock.

### 3. Trajectory intelligence (narratives, not events)

Unit of intel is not "event" but "live narrative" with a state machine. Each region carries 4–8 active narratives:

> Casablanca port action — Day 3, Phase: spreading, Forecast: 4-6d resolution.
> Watchpoints: Tangier sympathy strike · ONEE response · Royal intervention.

Narratives update; events are state transitions. Far higher information density than event lists.

### 4. Counterfactual briefing

Current brief is descriptive ("this happened"). Endgame is prescriptive: each item pairs an observation with credible counterfactuals.

> If you do nothing, by Friday this likely escalates to Tangier.
> If you pre-route nacelles via Tangier-Med port, you absorb 60% of the disruption, cost ~$X.

This is where LLM-as-analyst adds unique value — generating credible alternatives, not just summaries.

### 5. Network intelligence (2nd / 3rd-order effects)

Treat the org as a graph: sites → customers → contracts → cash flow; sites → vendors → continuity; people → roles → single-point-of-failure. A risk event isn't local — it propagates.

> Casablanca strike → ONEE PPA delayed → penalty clauses → Q3 cash flow impact $X.

Surface the chain. Highest value for portfolio operators, infrastructure investors, multi-customer service businesses — the kinds of buyers who care most about regional risk.

### 6. Adversarial red-team cell

A second LLM agent continuously challenges the analyst's assumptions:
> "You think Casablanca is the only exposure? What if the strike spreads to Tangier? What if there's an opportunistic cyber event while ops is distracted?"

The brief carries a "red-team challenges" section surfacing counterfactuals the analyst missed. This is how real intel orgs operate (Team A / Team B).

### 7. Multi-persona views from one spine

Same data engine, different lenses, priced and packaged separately:

| Persona | View |
|---|---|
| RSM | Operational daily brief |
| CISO | Cyber-emphasis cut |
| Country lead | Single-site / single-country brief |
| Insurance / underwriting | Quarterly trend report, per-asset risk-rating |
| Sales / account exec | Sanitized customer-facing risk-of-doing-business piece |
| Board | Quarterly exposure roll-up + counterfactual scenarios |
| HR mobility | Personnel-travel risk feed |
| M&A / diligence | One-off exposure report on a target geography or asset |

The model is the durable IP. Views are productized differently per buyer segment.

### 8. Auto-drafting downstream artifacts

Beyond the brief, the system auto-drafts the operator's *next* artifacts:
- Email to country lead
- Memo to the board
- Slack to duty officer
- Procurement hold order
- Insurance notification

The RSM's job becomes review/approve/edit, not write-from-scratch. Productivity multiplier without removing the human.

## Architectural difference (newsletter vs model)

**Newsletter shape (today):**
```
Seerist + OSINT → Collectors → Per-region manifest → Analyst LLM → Formatter LLM → email.html
```
Pipeline is per-run, per-region, per-day. State lives in the day's output folder.

**Model shape (endgame):**
```
Org surface (declarative) ─┐
World signals (continuous) ─┼→ Scoring engine ─→ Live model ─→ Views (brief, chat, packets, dashboard, reports)
Internal feeds (continuous) ─┘
```
Model is continuous. State lives in a durable store. Views read the model.

The pivot point isn't a feature — it's the move from per-run pipeline to persistent model with views.

## Why this isn't the current scope

Three reasons:

1. **Proof of work first.** Until we can produce a credible brief, no one cares about the model. The brief is the demo that earns the right to talk about the bigger product.

2. **The org surface needs maturing.** Today only MED has site data. The model only becomes useful when the surface is real. Putting model infrastructure ahead of surface data is premature.

3. **2-person team economics.** A model-spine product is roughly an order of magnitude more engineering than a brief generator. We need revenue/conviction from the brief shape before the larger build is responsible.

## How the current work feeds the bigger picture

The PoC is not throwaway — almost every piece carries forward:

| Current asset | Role in the model future |
|---|---|
| `aerowind_sites.json` site_registry | First version of the org surface (sites layer) |
| Seerist + OSINT collectors | World-signals ingestion layer (no change) |
| Per-region manifest builder | Templated view-builder; one of many views in the future |
| Claims.json schema (severity, confidence, pillar, surface, geographic_resonance) | Scoring engine output shape — most of the abstractions are already correct |
| Citation discipline (signal_id, claim_id, appendix) | Provenance layer — load-bearing in any production-grade risk product |
| Brief auditors / validators | Quality gates that survive the pivot |
| Per-region collector config (REGION_COUNTRIES, REGION_NEGATIVE_TERMS) | Region-aware ingestion config — survives |
| Org-grounded vs region-guided modes | Multi-persona scaffolding — the seed of view-templates |

What we *don't* have yet and would need for the model future:
- Persistent state store (events, narratives, exposure scores across time)
- Trajectory / narrative state machine
- Org graph (customers, vendors, dependencies — currently sites-only)
- Threshold + alerting engine
- Query interface
- Multi-view templating

## When this becomes relevant

Probably after:
- The brief proof of work is shipped and seen by at least 2-3 friendly evaluators (RSM personas)
- We have signal that the brief shape is genuinely valued (not just polite interest)
- The first paying engagement (or strong intent) is in place
- We've added per-region site data for at least 2-3 of the 4 currently empty regions, so we have surface-area to model

At that point the model architecture becomes the next big design decision.

## The honest one-liner

**Today we're proving we can produce a credible regional brief. The reason we're doing this is to earn the right to build the operational risk model that briefs are one downstream view of.**

Both versions of the product are real. Both can ship. The order matters.
