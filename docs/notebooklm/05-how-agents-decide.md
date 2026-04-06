# How the AI Agents Make Decisions

## The Decision Chain

Every regional threat assessment passes through three decision points before it reaches the board. Each point has a different agent, a different question, and a different output.

```
Raw OSINT signals
      ↓
Gatekeeper Agent — "Is this worth escalating?"
      ↓
Regional Analyst Agent — "What does this mean for the business?"
      ↓
Global Validator Agent — "Does the global picture add up?"
      ↓
Board Report
```

---

## Decision Point 1 — The Gatekeeper (Triage)

**Agent:** Gatekeeper (Claude Haiku — fast, binary)
**Question:** Does this signal cross the financial impact threshold?
**Output:** ESCALATE / MONITOR / CLEAR + Admiralty rating

### The escalation rule
A region is escalated if and only if the dominant scenario ranks in the **top 4 globally by financial impact**:
- #1 Ransomware (37.6% of losses) → ESCALATE
- #2 Accidental disclosure (36.1% of losses) → ESCALATE
- #3 System intrusion (21.4% of losses) → ESCALATE
- #4 Insider misuse (4.4% of losses) → ESCALATE
- #5 and below → MONITOR or CLEAR

### The Admiralty Rating System
Every gatekeeper decision includes an Admiralty rating — a two-part code used by intelligence services to express confidence:

**Source reliability (letter):**
- A = Completely reliable
- B = Usually reliable
- C = Fairly reliable
- D = Not usually reliable
- E = Unreliable
- F = Cannot be judged

**Information credibility (number):**
- 1 = Confirmed by other sources
- 2 = Probably true
- 3 = Possibly true
- 4 = Doubtful
- 5 = Improbable
- 6 = Cannot be judged

All three escalated regions in the current run are rated **B2** — usually reliable source, information probably true.

---

## Decision Point 2 — The Regional Analyst (Business Translation)

**Agent:** Regional Analyst (Claude Sonnet — reasoning depth required)
**Question:** How does this threat affect AeroGrid's ability to deliver business results?
**Output:** Executive brief structured as Why → How → So What

### The three-part brief structure

**Why** — The geopolitical or economic driver behind the threat
*(Example: State-directed technology collection driven by South China Sea competition)*

**How** — Which business assets are exposed and the access pathway
*(Example: Supply chain compromise through industrial automation software updates)*

**So What** — The business impact in plain language, anchored to a dollar figure
*(Example: $18.5M exposure. Risk to blade manufacturing schedules and permanent IP loss)*

### What the analyst is forbidden from writing
- Technical jargon (CVEs, IP addresses, hashes, TTPs, IoCs)
- SOC/security engineering language (MITRE ATT&CK, lateral movement, C2)
- Budget or procurement recommendations
- Any statistic not sourced from the master scenario baseline

---

## Decision Point 3 — The Global Validator (Devil's Advocate)

**Agent:** Global Validator (Claude Haiku — fast, read-only)
**Question:** Does the global synthesis accurately reflect the regional data?
**Output:** APPROVED or REWRITE with specific failure list

### What the validator checks
- Admiralty ratings are consistent between regional data and global report
- VaCR figures match regional data.json files exactly
- Scenario mappings are plausible given the signal files
- No region is missing from the synthesis
- Executive summary reflects the compound risk posture, not just individual regions

### The circuit breaker
If the validator forces 3 rewrites without approval, the circuit breaker fires: the report is force-approved and the failure is flagged to the human operator. The pipeline never hangs indefinitely.

---

## What Agents Are Not Allowed to Do

The pipeline enforces strict behavioral constraints on every agent:

| Prohibited behavior | Why |
|---|---|
| Invent statistics | All numbers must come from the master scenario baseline |
| Write technical jargon | Reports are for business operators, not security engineers |
| Give budget advice | Agents assess risk; humans decide spend |
| Claim completion without proof | Every agent output is verified by a deterministic hook before acceptance |
| Run indefinitely on failure | Circuit breakers cap retries at 3 per stage |
