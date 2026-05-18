# MED RSM PoC — Sponsor Memo

**PoC week:** _2026-05-DD to 2026-05-DD_
**Recipient:** _MED RSM (real recipient name)_
**Author:** _your name_
**Decision asked:** Greenlight / Pivot / Kill on v2 build

---

## What we delivered

- 7 daily HTML emails sent to the MED RSM, one per morning at the agreed slot.
- Artifact archive: `output/poc/med/2026-05-DD..DD/`
- Each email: Seerist live data → AeroGrid site grounding (POI proximity) → provider-agnostic formatter request executed in an available model workbench → operator-QA'd HTML.

## What the RSM said

_Roll up `feedback_log.md` here. 3 bullets max._

- ...

## What the pipeline does today (proven by this PoC)

- Seerist live API integration: events, verified events, hotspots, pulse, analysis reports
- MED-specific multi-country `aoiId` (no broader-region leakage)
- Per-site POI proximity with haversine grouping — each site gets its own alert with matching events
- Provider-agnostic formatter prompt produces `brief.md` following the SITREP shape ex-military RSMs expect (via Claude Code, Codex, GitHub Copilot IDE, or another suitable model workbench)
- Email-safe HTML rendering (renders correctly in Gmail web + mobile + Outlook web — verified manually each day in `_qa_log.md`)
- Site-name discipline enforced at render time (no out-of-registry site names can ship)
- HTML email-body rendering (`render_brief_html.py`); operator emails manually via Gmail/Outlook compose

## What it can't do today (deferred to v2)

- Cyber pillar — explicitly deferred, acknowledged in every email
- Scribe AI enrichment, AskAnna, WoD targeted search
- `since`-parameter delta collection
- Automated daily dispatch (Windows subprocess→`claude` CLI bug)
- Automated email send (operator copy-pastes from `email.html` into Gmail/Outlook each morning — SMTP automation deferred to v2)
- Other 4 regions
- Weekly INTSUM synthesis (rsm-weekly-synthesizer agent not invoked)

## Recommendation

_Choose one:_

- **GREENLIGHT v2 with scope X** — based on (specific RSM feedback / specific operational signal / specific gap that's worth closing)
- **PIVOT to scope Y** — because the PoC revealed (specific finding)
- **KILL** — because (specific finding)

## Estimated cost to v2-ready

_Rough effort estimate based on what feedback revealed. Include cyber sourcing decision, scribe integration, automated dispatch, weekly synthesis, multi-region scale-out._
