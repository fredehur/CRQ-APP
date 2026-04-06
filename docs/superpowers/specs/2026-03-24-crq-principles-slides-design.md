# CRQ Principles Slides — Design Spec

**Date:** 2026-03-24
**Purpose:** HTML mockup of 13 slides for a 45-minute government meeting introducing the Foundational Principles of Quantitative Cyber Risk Modelling.

## Context

- **Audience:** Non-technical government officials (senior civil servants, ministers, policy decision-makers)
- **Duration:** 45 minutes (~3 min/slide)
- **Goal:** Communicate the 10 foundational principles only — practical application is covered in a separate session
- **Output format:** Single self-contained HTML file (no external CDN links; all CSS and JS inline). User will recreate in PowerPoint.

## Slide Layout

Each slide is full-viewport. Three layout types:

**Opening slide:** Centred title + subtitle only, vertically centred.

**Principle slides:**
- Small muted label top-left: e.g. "Principle 1 of 10"
- Large bold headline (the principle title)
- Divider line
- 2–3 bullet points
- Vertical arrangement: label → headline → divider → bullets, with generous whitespace between each

**Summary + Closing slides:** Headline centred, content below.

Slide number indicator bottom-right on all slides (e.g. "2 / 13").
Keyboard navigation: left/right arrow keys. On-screen prev/next buttons bottom-left/right.

## Visual Style

- White background, near-black text (#1a1a1a)
- Font: clean system sans-serif (e.g. `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`)
- Large readable font. Generous whitespace. No images, no icons, no decoration.
- Bullet points plain — no icons or coloured markers

## Deliverable

Single self-contained file: `output/crq-principles-slides.html`
All CSS and JS in `<style>` and `<script>` tags. No external dependencies.

---

## Full Slide Content

### Slide 1 — Opening
**Title:** Quantitative Cyber Risk Model
**Subtitle:** Foundational Principles

---

### Slide 2 — Principle 1
**Label:** Principle 1 of 10
**Headline:** Risk Is Continuous, Not Binary

- Digital risk is not a switch that flips between "secure" and "compromised" — it is a dynamic state
- Cyber risk fluctuates over time rather than resolving into a permanent safe state
- This reframes security as ongoing risk management, not a project milestone or maturity target

---

### Slide 3 — Principle 2
**Label:** Principle 2 of 10
**Headline:** Intentional Adversaries Drive Digital Risk

- Digital risks emerge from adversaries pursuing specific goals
- Defences influence adversary behaviour by increasing the economic effort required to succeed
- The goal is to raise this effort until attacks become unappealing or unprofitable

---

### Slide 4 — Principle 3
**Label:** Principle 3 of 10
**Headline:** Scenarios Are the Fundamental Unit of Risk

- We cannot manage "digital risk" in the abstract
- We articulate risk through concrete, well-defined scenarios based on public threat intelligence
- Scenario-based framing ensures we speak consistently about what could occur and what it would mean

---

### Slide 5 — Principle 4
**Label:** Principle 4 of 10
**Headline:** We Anchor Our Understanding in Peer Reality First

- Before we consider our unique environment, we begin with peer-benchmark data
- Industry-wide probabilities, financial loss ranges observed across comparable organisations
- This establishes a baseline grounded in publicly observable evidence rather than internal assumptions

---

### Slide 6 — Principle 5
**Label:** Principle 5 of 10
**Headline:** Our Own Environment Shapes Likelihood

- Once the peer baseline is defined, we interpret it through the lens of our own environment
- Our architecture, processes, governance, technology estate, and organisational choices
- Every safeguard alters the effort required for an incident to succeed — changing the likelihood

---

### Slide 7 — Principle 6
**Label:** Principle 6 of 10
**Headline:** Impact Is Expressed in Financial Terms

- Digital risk becomes meaningful when translated into the business language: financial impact
- We quantify consequences through direct, measurable changes in financial performance
- Results are objective, auditable, and comparable to other risks

---

### Slide 8 — Principle 7
**Label:** Principle 7 of 10
**Headline:** Risk Is Communicated as Distributions, Not Singular Values

- No single number can meaningfully express digital risk
- We use a set of complementary metrics: expected annual loss, worst-case thresholds, and the full shape of uncertainty across all loss levels
- Each metric answers a different question and supports different governance needs

---

### Slide 9 — Principle 8
**Label:** Principle 8 of 10
**Headline:** Risk Communication Must Be Standardised and Actionable

Every significant risk statement includes four components:
- The scenario name
- The organisation-specific likelihood
- The financial impact view
- The key levers that would materially reduce that risk

---

### Slide 10 — Principle 9
**Label:** Principle 9 of 10
**Headline:** Transparency and Traceability Are Non-Negotiable

- All quantitative outputs must be explainable, traceable, and supported by documented assumptions
- Linked back to peer data, scenario definitions, and organisational context
- Every stakeholder should be able to trace a financial figure back to its origin

---

### Slide 11 — Principle 10
**Label:** Principle 10 of 10
**Headline:** The Framework Is Living and Must Adapt

- The digital landscape evolves rapidly. So must the model.
- We maintain a regular governance cadence to refresh scenario definitions, peer benchmark data, and organisational context
- Digital risk quantification is never "finished" — it is continuously maintained

---

### Slide 12 — How These Principles Are Used
**Headline:** How These Principles Are Used

- **Alignment** — every stakeholder understands the philosophical basis of the model before engaging with any technical detail
- **Interpretation** — guides how outputs should be read, communicated, and applied in decision-making
- **Governance** — defines expectations for transparency, refresh cycles, and communication standards across the organisation

---

### Slide 13 — Close
**Quote (centred):**
"With this foundation in place, stakeholders can engage with the model confidently — knowing not just what it does, but why it works the way it does."
