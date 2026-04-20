# CISO Brief — Claude Design Brief

**Purpose:** Monthly geopolitical + cyber risk briefing to the AeroGrid Wind Solutions Chief Information Security Officer.

**Cadence:** Monthly.

**Primary reader:** CISO. Secondary: security leadership team (VP security, head of threat intel, head of GRC).

**Setting:** CISO reads solo first (focused, 15–20 minutes). Then shares with security leads for team review in the next 1:1s. Digital-first with occasional print for in-person review.

**Length:** Target 6–10 pages. Expert reader — density is a feature.

---

## Your Task (Claude Design)

Design this brief end-to-end. You decide:
- Page order and information hierarchy
- Section anatomy and layout grammar
- Visual treatments, typography rhythm, where charts belong and where prose wins
- How content is chunked across pages
- Whether regional views, scenario views, or cross-cutting themes lead the brief

The content contract and brand are fixed. Everything else is yours.

## Visual System (inherit exactly)

CRQ Design System v1.0 — same tokens you used for prior AeroGrid work. No new tokens. No new palette.

## Visual North Star

- **Expert reader, high bandwidth** — do not over-explain. Do not soften language. Do not use bullet walls to compensate for weak prose.
- **Strategic, not technical** — this is a geopolitical + cyber risk brief. Zero SOC-engineer language. Zero budget framing. Zero "what CISOs need to know" tone. The reader *is* the CISO.
- **Cross-cutting framing matters** — a monthly brief should surface patterns across regions that no single regional report would catch. Design for that.
- **Typography does the work** — hierarchies via weight + size + ramp, not boxes. The CISO should be able to scan the brief in 3 minutes and read it in 15, from the same layout.

## Content Contract

Every CISO Brief must cover the following. How you organise it, split it across pages, or visualise it is your call.

### Cover material
- Title, month (e.g., April 2026), issue date, classification (`INTERNAL — AEROGRID SECURITY LEADERSHIP`), preparer mark, version

### Opening
- One-sentence characterisation of the month (the "state of risk" line)
- Overall posture (confidence + admiralty)
- The month's 2–4 CISO-level takeaways

### Cross-regional intelligence picture
- What patterns appeared across regions this month (the CISO-specific lens — this is what the CISO reads that RSMs don't)
- Which regions moved, which held, which diverged from baseline
- A "why clear" treatment for quiet regions — a regional silence is information, not an absence. The brief must say *why* a region is quiet (baseline stable + no new triggers + watchlist cold) rather than omit it.

### Cyber-specific surface
- Sector-targeting campaigns affecting AeroGrid's footprint
- Actor activity — what moved on the watchlist this month
- Vulnerability signal — CVEs and advisories material to AeroGrid's stack (OT/ICS, SCADA, turbine control, grid management, identity, perimeter)
- Any cyber-to-physical join (e.g., state-actor scanning in a country where we have crown-jewel physical exposure)

### Scenario watch
- 3–5 risk scenarios the CISO should have current context on this month
- Each: scenario number, region, headline, driver context, current assessment, any delta vs. last month
- If a scenario moved (severity shift, new evidence, changed watch posture), that delta is the point — design for it

### Evidence appendix
- Sectioned: Physical (E-prefix) and Cyber (C-prefix)
- Per-entry fields: ref ID, headline, source, admiralty rating, timestamp, URL (optional), one-line "why it's here"
- Every assertion in the brief traces here

### Mock content for your design session (realistic April 2026)

**State-of-risk line:** *"April 2026 was shaped by North African political volatility, sustained EU renewables ransomware pressure, and a quieting APAC transit picture; the cross-cutting theme is rising geopolitical-cyber coupling — state-actor cyber scanning tracking state-actor-of-interest physical activity."*

**Confidence:** HIGH. **Admiralty:** B2. **Change from March:** MED admiralty tightened one notch (B3 → B2) on improved Seerist coverage.

**CISO takeaways (3):**
1. The Moroccan election window is the month's dominant signal — both physical (crown-jewel site on raised watch) and cyber (APT28 scanning coincident with election calendar).
2. SolarGlare ransomware campaign now confirmed at multiple EU wind operators; NCE sites should be treated as exposed, not hypothetical.
3. Three of our five regions are in "stable baseline" this month — and that is material: the brief should reinforce that silence is itself an intelligence product.

**Cross-regional picture (4 items):**
- **MED moved** — Morocco election + Italy port strike. Raised posture through May.
- **NCE held but under cyber pressure** — physical quiet; cyber sector-targeting active.
- **APAC quieted** — transit corridor stability improved; supply chain watch remains.
- **LATAM + AME in baseline** — stable; no new triggers; watchlist cold.

**Why clear — LATAM (example treatment):** *"LATAM registers no regional escalation this month. Host-country baselines stable across Brazil, Chile, Peru. Watchlist actors quiet. No new CVE or sector campaign material to portfolio. Regional admiralty unchanged at C2. Next review: mid-May."*

**Cyber surface:**
- **Sector campaign:** SolarGlare — confirmed at 2 German wind operators; TTP pattern observed; 4 additional EU operators reported probable targeting. AeroGrid NCE sites — no confirmed impact, increased monitoring.
- **Actor activity:** APT28 — scanning Moroccan energy ASNs through April, coincident with election. Observed cadence increased 3x over March. Cape Wind SOC — no anomalies observed.
- **Vulnerability signal:** CVE-2026-1847 (turbine SCADA, Vendor X v4.2) — patch available, portfolio rollout at 40%. CVE-2026-1722 (grid HMI) — workaround only, 2 sites affected.
- **Cyber-physical join:** APT28 activity in Morocco during election = coupled risk. State-actor cyber posture mirroring state-actor physical interest. Treat as joint intelligence signal, not two separate streams.

**Scenarios watched (4):**
- **S-07 MED — Sustained civil unrest near Cape Wind.** Drivers: post-election coalition friction. Current: HIGH / MEDIUM likelihood. Delta: moved from MEDIUM severity last month.
- **S-11 NCE — Cyber intrusion via OT vendor.** Drivers: SolarGlare + unpatched SCADA. Current: HIGH / MEDIUM-HIGH. Delta: new evidence this month (Germany operator confirmation).
- **S-09 AME — Third-party vendor compromise.** Current: MEDIUM / MEDIUM. Delta: none; included for continuity.
- **S-14 APAC — Supply chain disruption (blades).** Current: MEDIUM / LOW-MEDIUM. Delta: improved — transit stabilisation reduced short-term likelihood.

**Evidence entries:** Fill an appendix with ~10 physical (E1–E10) and ~6 cyber (C1–C6), each plausible publisher + admiralty + timestamp + "why it's here". Mix Seerist Verified, CERT-EU, CISA, Reuters, Le360, Bloomberg, Der Spiegel, Nikkei, etc.

## Output

Single multi-page HTML document, print-styled, A4. Export HTML — we'll wire it into the Jinja2 + Playwright → PDF pipeline (same pattern as Board). DOCX becomes the legacy export.

## Explicit permissions

- Break convention where it serves the reader. A monthly CISO brief should not look like a quarterly report compressed.
- Use cross-cutting framing devices if they serve — a "regions grid" that shows all five regions' posture at a glance on p1, a "delta ribbon" across the top of scenario pages showing what moved, a "cyber-physical join" sidebar where it applies.
- If a region is quiet, the "why clear" treatment is mandatory — don't omit quiet regions, treat their silence as signal.
- The expert reader is your design partner here. Trust them.
