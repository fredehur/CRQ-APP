# Board Report — Claude Design Brief

**Purpose:** Quarterly geopolitical + cyber risk briefing to the AeroGrid Wind Solutions Board of Directors.

**Cadence:** Quarterly.

**Primary reader:** Full board (chair + directors). Audit + risk committee members read more deeply; other directors scan.

**Setting:** Distributed as printed pre-read 48 hours before the board meeting. Brought into the room on paper. Select pages may be projected during the risk discussion.

**Length:** Target 8–14 pages. Density earns pages; scaffolding does not.

---

## Your Task (Claude Design)

Design this report end-to-end. You decide:
- Page order and information hierarchy
- Section anatomy and layout grammar
- Visual treatments, typography rhythm, use of charts and visual devices
- How content is chunked across pages

The content contract and brand are fixed. Everything else is yours.

## Visual System (inherit exactly)

CRQ Design System v1.0 — same tokens you used for prior AeroGrid work:
- IBM Plex Sans typography
- Brand navy `#1B2D6E`
- Severity palette: CRITICAL `#d1242f`, HIGH `#cf6f12`, MEDIUM `#9a7300`, MONITOR `#0969da`
- Standard ink ramp, pill/badge treatment, A4 page-grid spacing

No new tokens. No new palette. One design system across the AeroGrid intelligence product family.

## Visual North Star

- **IC-briefing tier** — feels like a serious intelligence community product, not a marketing deck and not a McKinsey slide set. Directors reading this should feel respected, not pitched to.
- **Density over whitespace** — the board is not scrolling on a phone. Pages should reward re-reading.
- **Typography as structure** — hierarchy via weight + size + ramp, not boxes and borders.
- **Charts earn their space** — a chart is only worth the page if it replaces 200 words of prose.

## Content Contract

Every Board Report must cover the following. How you organise it, split it across pages, or visualise it is your call.

### Cover material
- Report title, quarter (e.g., Q2 2026), issue date, classification (`INTERNAL — BOARD DISTRIBUTION`), preparer mark, version

### Executive framing
- One-sentence characterisation of the quarter (the "state of risk" line)
- Overall posture (confidence level + admiralty rating)
- The 3–5 board-level takeaways from the quarter

### Intelligence picture
- Key developments of the quarter (4–6 items) — what moved, where, and what it means for AeroGrid
- Items the board is "also tracking" (2–4 items) — context, not yet decision-grade
- Forward-looking watch items (2–3 items) — what may reach the board next quarter

### Risk scenarios
- The 3 most board-relevant risk scenarios this quarter
- Each with: scenario number, region, headline, drivers, type, body narrative, organisational implications, proposed actions or governance asks, evidence anchors
- The scenarios must be readable as distinct, standalone units — a director flipping to one should not need the others for context

### Risk matrix
- A visual positioning of ~8 scenarios on two axes (likelihood × impact, or similar two-axis framing)
- Headline + bottom-line line + reading guidance for the matrix
- This replaces a full-page risk register dump — the matrix is the register view for the board

### Methodology
- One page (or less) on: sources, rating system, confidence framework, what the board should read into versus past

### Mock content for your design session (realistic Q2 2026)

**State-of-risk line:** *"Q2 2026 saw elevated North African unrest, sustained EU renewables cyber pressure, and a material stabilisation of APAC transit corridors; the AeroGrid portfolio remains materially exposed to Moroccan political volatility and a widening EU ransomware campaign."*

**Confidence:** HIGH. **Admiralty:** B2.

**Key developments (5):**
1. Moroccan general election (April) — outcome elevated short-term unrest risk around Casablanca corridor; Cape Wind (crown-jewel) remains on raised watch through Q3.
2. SolarGlare ransomware campaign confirmed at two German wind operators; campaign now on active monitoring for NCE sites.
3. Taranto Offshore commissioning on track; storm-season preparations complete.
4. APT28 scanning activity against Moroccan and Spanish energy ASNs — no observed AeroGrid impact; SOC monitoring in place.
5. EU Commission draft legislation on OT/ICS resilience — Q3 submission deadline; compliance cost estimate pending.

**Also tracking (3):**
- Greek local election (late May) — 3 minor AeroGrid sites in region
- Turkish currency instability — vendor payment exposure under review
- US IRA tariff adjustments — indirect supply chain effect under assessment

**Watch next quarter (3):**
- Moroccan post-election coalition stability (6–12 weeks)
- CVE-2026-1847 (turbine SCADA) — patch deployment rollout across portfolio
- Winter season onset for MED offshore sites

**Scenarios (3):**
- **S-07 MED** — *Sustained civil unrest near Cape Wind.* Drivers: post-election coalition friction, youth unemployment, regional economic stress. Type: political-security. Body: [1 paragraph]. Implications: offtake continuity, expat safety, local reputation. Actions: continue raised watch through Q3, reassess at October board.
- **S-11 NCE** — *Cyber intrusion via OT vendor.* Drivers: SolarGlare campaign, unpatched SCADA, third-party vendor access. Type: cyber. Body: [1 paragraph]. Implications: generation availability, data integrity, regulatory reporting. Actions: accelerate CVE-2026-1847 patching, vendor access review.
- **S-14 APAC** — *Supply chain disruption — turbine blades.* Drivers: single-source Chinese supplier, geopolitical export restriction risk. Type: supply chain. Body: [1 paragraph]. Implications: 2027 project delivery timeline. Actions: qualify second-source supplier, target Q4 2026.

**Matrix dots (~8 scenarios):** positions on a 0–100 × 0–100 grid — you pick the exact coords; roughly S-07 upper-mid-right, S-11 upper-right, S-14 mid-mid, five others spread across the grid at varying severities.

**Matrix headline:** *"Concentration in MED political and NCE cyber — supply chain exposure stable but strategically watched."*
**Bottom line:** *"Two scenarios warrant board-level action this quarter; six remain within management authority."*

**Methodology:** Sources — Seerist (Control Risks), Firecrawl + Tavily discovery, internal RSM reporting. Rating — Admiralty system + NATO confidence framework. What the board reads into: a move from B2 to A1 on a scenario = treat as near-certain; a move from MEDIUM to HIGH severity = warrants governance conversation.

## Output

Single multi-page HTML document, print-styled, A4. Export HTML so we can wire into the existing Jinja2 + Playwright → PDF pipeline and keep PPTX parity via `tools/build_pptx.py`.

## Explicit permissions

- Break convention where it serves the reader. A board report does not need to look like other board reports.
- Use visual devices sparingly but without fear — one strong chart is worth three weak ones.
- If a section is not needed for a given quarter, skip it. The brief should not carry empty scaffolding.
- If you invent a layout element (e.g., a "quarterly delta bar" across the top, a sidebar footnote system, a single-page standalone scenario card), use it if it earns the space.
