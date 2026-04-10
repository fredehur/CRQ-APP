# Regional Structure Brainstorm — How Regions Tie Into Output Formats

**Status:** Brainstorm only — no implementation decisions made yet. Review and continue tomorrow.

**Core question:** Should CISO, Board, and RSM formats be structured region-first (one section per region) or event/scenario-first (top N events across all regions, labeled by region)?

---

## The Problem With Region-First Throughout

The current pipeline runs five regional analysts and assembles five regional blocks in every output format. This made sense to build with — the pipeline fan-out is regional. But it's the wrong reading experience for two of the three audiences.

**A CISO reading a region-first brief has to:**
1. Read APAC section — learn one escalated scenario
2. Read AME section — learn it's CLEAR
3. Read LATAM section — learn it's CLEAR
4. Read MED section — learn one escalated scenario
5. Read NCE section — learn one escalated scenario
6. *Then* mentally synthesize: "three escalated regions, two scenarios overlap"

That synthesis is done by the `global_builder_agent` — but it lives in a separate `global_report.json` that isn't integrated into the CISO brief. The CISO is doing manual cross-regional pattern matching that the system already did.

**A board member reading a region-first brief:**
- Five regions × three paragraphs = fifteen paragraphs to read to understand one question: "what are our two biggest risks right now and where?"

**An RSM reading a region-first brief:**
- This is actually correct. An RSM owns a geography. They need everything about their patch.
- The only gap: they don't see when the same scenario is active in other regions (coordination signal).

---

## Proposed Organizing Principle Per Format

| Format | Organizing principle | Region role |
|---|---|---|
| **Overview tab** | Region-first | Primary axis. Analyst thinks in regions — this is their workspace |
| **CISO brief** | Scenario/severity-first | Label on each item — "System intrusion — APAC, NCE" |
| **Board summary** | Top N events globally | Label — "3 of 5 regions escalated · 2 scenarios active" |
| **RSM alert** | Region-first (their patch) | Primary axis + cross-regional watch block |

---

## Option A: Event-First for CISO + Board

**Structure:**
1. Global status line: "3 of 5 regions escalated this cycle — APAC, MED, NCE"
2. Top events ranked by `financial_rank × seerist_strength`:
   - **[1] System intrusion** — APAC + NCE `[ESCALATED — GEO-LED, B2]`
   - **[2] Supply chain compromise** — MED `[ESCALATED — CYBER-LED, C3]`
3. Clear regions: "AME, LATAM: no escalated scenarios this cycle"
4. Cross-regional pattern (from `global_report.json`): "System intrusion appearing in two regions simultaneously — assess as coordinated campaign risk"

**Pros:**
- CISO reads the most important thing first
- Natural de-duplication: if System intrusion is active in APAC and NCE, it appears once with both labels — not as two separate regional sections saying the same thing
- Board format: the "3 of 5 escalated" line is the headline — the rest is evidence
- The `global_builder_agent` synthesis becomes the organizing frame, not an appendix

**Cons:**
- Bigger change to the pipeline's output assembly
- Loses per-region granularity in CISO brief — analyst may need to dig into regional detail
- The ranking function (`financial_rank × seerist_strength`) needs to be defined and tested

**Open question:** Does CISO need the full per-region Why/How/So What for each scenario, or just the headline + key bullets? If full detail is needed, event-first becomes a long document.

**Possible answer:** Two-tier CISO brief — executive summary (event-first, 1 page) + regional detail appendix (region-first, existing structure). CISO reads the summary; regional ops consults the appendix.

---

## Option B: Hybrid — Summary Event-First, Detail Region-First

**Structure:**
- **Page 1 (all formats):** Event-first summary — top N scenarios, ranked, cross-regional pattern
- **Page 2+ (CISO/Board):** Regional detail — existing Why/How/So What per escalated region
- **RSM:** Regional detail only (their patch) + cross-regional watch block

The `brief_headlines` from the source split plan (`why_summary`, `how_summary`, `so_what_summary`) become the building blocks for the event-first summary page. Each scenario's summary is drawn from the analyst's three summary sentences — written once, rendered in two places.

**Pros:**
- CISO gets the one-page executive view they want AND can drill to per-region detail
- No loss of granularity
- `brief_headlines` plan becomes the connective tissue — not a cosmetic change but a structural one
- Extensible: the event-first summary is easy to generate because it pulls from existing structured data

**Cons:**
- Longer documents overall
- Requires the `global_builder_agent` output to drive the summary page, not just sit in `global_report.json`

---

## Option C: Keep Region-First, Fix the Global Integration

**Minimal change:** Keep region-first structure as-is. Fix the real problem: integrate `global_report.json` as the opening section of CISO and Board formats, before the regional sections.

Currently `global_report.json` exists but is rendered separately (board PDF only). Adding it as a structured opening to the CISO docx and board card would give:
- "Here is the cross-regional picture" (from global_builder)
- "Here is APAC in detail" / "Here is NCE in detail"

**Pros:**
- Minimal pipeline change — the global synthesis is already being produced
- Preserves existing regional section structure that's already working
- Quick to implement

**Cons:**
- Doesn't solve the redundancy problem (System intrusion appears in APAC section AND NCE section as separate items)
- CISO still reads two full regional sections that are partially about the same scenario
- The "fix" is additive, not structural

---

## RSM Specific: Cross-Regional Watch Block

Regardless of which option is chosen for CISO/Board, the RSM format has a gap that all three options should address: **RSMs don't currently see when their scenario is active in other regions.**

Proposed addition to every RSM brief:

```
## Cross-Regional Watch
System intrusion (your primary scenario) is also active in NCE this cycle.
Assess whether there is a coordinated campaign dimension before treating as isolated.
```

This pulls from `global_report.json` — the global builder already identifies cross-regional patterns. It just needs to be routed into the RSM input builder.

---

## Questions to Resolve Tomorrow

1. **CISO format:** Event-first summary + regional detail appendix (Option B), or just add global summary block (Option C)?

2. **Ranking function:** If we go event-first, how do we rank scenarios across regions?
   - Option: `financial_rank` (from master_scenarios.json, immutable) × `seerist_strength` (high=3, low=1, none=0)
   - Should ESCALATED regions get a boost vs MONITOR?
   - Who computes this — `global_builder_agent` or a deterministic Python tool?

3. **Deduplication:** If System intrusion is active in APAC and NCE, does it appear as one entry labeled "APAC + NCE" or two separate entries? One entry is cleaner but loses per-region nuance.

4. **Board format:** How much detail does the board actually need? Is the event-first summary page enough, or do they need regional detail too?

5. **`brief_headlines` dependency:** Option B assumes summary sentences exist per region. This depends on the `brief_structure` plan (Task 1 of `2026-04-10-overview-source-split-brief-structure.md`) being completed first. If we don't ship that, the event-first summary has no content to pull from.

6. **`global_report.json` readiness:** The global builder produces a JSON with `executive_summary`, `regional_briefs`, `cross_regional_patterns`, `compound_risks`. Is this structured enough to drive the event-first summary, or does the global builder need to produce a separate ranked events list?

---

## Related Plans

- `2026-04-10-overview-source-split-brief-structure.md` — `brief_headlines` plan; Task 1 (analyst summary fields) is a prerequisite for Option B
- `2026-04-10-seerist-source-hierarchy.md` — complete; `seerist_strength` scores available per region, can be used in ranking function
