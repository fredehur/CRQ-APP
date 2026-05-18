# MED RSM 7-Day PoC — Design

**Date:** 2026-05-17
**Status:** Draft — review pass 2 applied
**Scope:** MED region only. 5 business days (Mon–Fri) of daily HTML-email intelligence briefs delivered to the MED RSM, generated from Seerist live data with a 5–10 minute human QA pass each morning. Optional Sat/Sun sends only if the RSM explicitly says he reads weekend mail. Internal proof to greenlight further build investment.

**Working directory:** All implementation paths in this spec are relative to `poc/seerist-rsm/` (the MED slice). Doc paths under `docs/superpowers/...` and `docs/poc/...` live at the parent `crq-agent-workspace/` root. This carve was made because the slice can run on a Copilot-only workstation; implementation work for this PoC happens inside the slice, not the parent.

---

## 1. Purpose & success criteria

### Value proposition (what the RSM is meant to feel)

The product is **AI-gathered intelligence delivered proactively**, not a formatted news digest. Seerist's AI (Events AI, Hotspots AI, Pulse AI, Verified Events) plus a **two-step agent chain (regional analyst → formatter)** reasons over the past 24h of MED activity, joins it to AEROWIND's site registry, and surfaces what matters before the RSM has to look. The chain is sequential operator-in-the-loop (each step is a request-file the operator hands to whatever model workbench they have), not parallel subagents — restoring the parent CRQ pipeline's analytical depth without locking the runtime to Claude Code's `TeamCreate` harness. Each morning the RSM opens his inbox to a brief that says "this is what changed near your sites overnight, here's what it means."

If the RSM finishes a week of these emails and his takeaway is *"I didn't have to go fishing — it found things I would have missed,"* the value prop is felt. If he reads them as "another newsletter," the prop hasn't landed.

### Audience hierarchy

- **Primary recipient:** the MED RSM (real person, real email). His feedback is the evidence we collect.
- **Real decision-maker:** internal sponsor (you / your principal). The 7-day artifact set + RSM feedback is what gets handed up for a go/pivot/kill call on a wider build.

### Success criterion

End of week 1, sponsor has enough evidence to greenlight v2 build. Evidence = the 7 emails as shipped, the 7 sets of RSM feedback, and a one-page sponsor memo synthesising both with a recommendation.

This is **not** a daily-operational-value test, **not** a stakeholder adoption test, **not** a structured-focus-group. It's a green-light decision support pack.

### Out of scope

- Any region other than MED (carved out by the slice already)
- Cyber pillar — explicitly deferred, acknowledged in the email body once
- Scribe AI enrichment, AskAnna, WoD targeted search
- Pulse-delta baseline, `since`-parameter incremental collection
- PDF or Word output
- Weekly INTSUM synthesis
- Automated dispatcher (`rsm_dispatcher.py --daily`) — the Windows subprocess→`claude` CLI bug remains unfixed; we work around it by having the operator manually run the daily `formatter_request.md` in whatever agentic environment is available (Claude Code, Codex CLI, GitHub Copilot IDE, or another model workbench)
- **SMTP / email automation** — the operator handles email send manually. Pipeline produces `email.html`; operator opens it in browser, copies, pastes into Gmail/Outlook compose, sets recipient, sends. No code touches the mail server, no recipient lists in git, no `notifier.py` changes.
- Other 4 regions, global synthesis, validators beyond the existing stop hook

### IDE / agentic-environment independence (explicit)

This PoC does **not** depend on Claude Code specifically. The codebase owns the deterministic parts (collection, manifest generation, validation, HTML rendering). The agentic/model layer owns exactly one task per morning: read the daily `formatter_request.md` + manifest, then write `brief.md` in the required SITREP shape.

Supported daily-formatter environments:

- **Claude Code / Pi** (subagent or inline dispatch against the canonical prompt or the optional `.claude/agents/rsm-formatter-agent.md` wrapper)
- **Codex CLI** (run/review the request from the slice working directory)
- **GitHub Copilot IDE** (open the request in VSCode + Copilot Chat or Agent mode against this repository)
- **Any model workbench** that can read the bundled request and either write `brief.md` directly or return the markdown for the operator to save

The canonical prompt lives at `prompts/rsm_formatter_daily.md` and is bundled into each day's `formatter_request.md` by `poc_runner.py --collect`. Claude-specific files under `.claude/agents/` are convenience wrappers, not load-bearing.

---

## 2. The product

### What lands in the RSM's inbox each morning

A single email. HTML body, no attachments. Clean monospace-leaning typography that mirrors the existing markdown brief shape (preserves the SITREP feel ex-military RSMs are trained to read).

**Subject line:** `AEROWIND // MED Daily Intelligence — {date}`

**From:** `AeroGrid Intelligence <intel@aerowind.example>` (real sender TBD in `audience_config.json`)

**Send slot:** consistent morning time, MED-friendly. Default: 07:30 CET. Decision deferred to plan-time.

### Body structure (HTML, single-column, ≤640px content width)

```
[Header band — dark, AEROWIND // MED DAILY // {date}Z]

[Stat strip — PULSE arrow | ADM | NEW counter]

█ SITUATION
  {one-sentence narrative — what changed in the last 24h}

█ AEROWIND EXPOSURE
  {per-site blocks — only sites with new events inside radius}
  ▪ {site name} [{CRITICALITY} · {personnel} personnel, {expat} expat]
     ├─ {event title} — {distance}km, severity {LABEL}, {✓ verified}, {n} sources
     └─ Consequence: {one line — what this means for THIS site}

  {if a site has zero new events:}
  ▪ {site name} [...]  — No new events within radius this period.

█ PHYSICAL & GEOPOLITICAL — LAST 24H
  {event bullets, severity-labeled}

█ CYBER — LAST 24H
  Cyber not collected in PoC v1 — see footer.

█ EARLY WARNING — NEW
  {Seerist hotspots first detected last 24h, or "No new anomalies"}

█ TODAY'S CALL
  {1–2 sentences. Operational not strategic.}

[Footer]
  Reply with one of: USEFUL · NOISE · MISSED CONTEXT · FALSE POSITIVE
  + one sentence (what would make tomorrow's better)
  AeroGrid Intelligence // MED RSM
  PoC v1 — cyber feed deferred to v2. Feedback welcome at this address.
```

The four-class reply taxonomy (USEFUL / NOISE / MISSED CONTEXT / FALSE POSITIVE) lets the operator classify each reply quickly and roll it up in the sponsor memo without inventing a coding scheme on the fly. Reply count zero is a finding; reply distribution skew is a finding.

### Design rules

- Single column. No images. No tracking pixels. No share buttons.
- Color used sparingly: severity chips (`LOW=neutral`, `MED=amber`, `HIGH=orange`, `CRITICAL=red`) and a green or red PULSE arrow.
- Monospace font (`SF Mono`, `Menlo`, `Consolas`, `monospace`) for header band, stat strip, and event rows — gives the SITREP feel without making body prose painful to read. Body prose in default sans (`-apple-system`, `Segoe UI`, `system-ui`).
- Inline CSS only (email-client safe). Conform to the subset that renders in Outlook, Gmail web, Gmail mobile, Apple Mail.

---

## 3. Architecture

### What stays as-is

```
data/aerowind_sites.json           ← MED-filtered, 3 sites: Casablanca, Palermo, Málaga
data/company_profile.json          ← crown jewels, footprint
data/mock_osint_fixtures/med_*.json ← offline data for dry runs
tools/seerist_client.py            ← Seerist HTTP client (with patches below)
tools/seerist_collector.py         ← collector (with patches below)
tools/poi_proximity.py             ← downstream of collector (no change)
tools/rsm_input_builder.py         ← formatter manifest (no change)
tools/briefs/templates/rsm.html.j2 ← Jinja brief template (will be adapted for email)
static/design/styles/rsm.css       ← brief styling (will be subsetted for email)
prompts/rsm_regional_analyst_daily.md ← CANONICAL provider-agnostic ANALYST prompt (NEW).
                                     Runs FIRST in the daily chain. Bundled into each day's
                                     `analyst_request.md` by `poc_runner.py --collect`.
prompts/rsm_formatter_daily.md     ← CANONICAL provider-agnostic FORMATTER prompt (NEW).
                                     Runs SECOND in the daily chain. Reads analyst output (claims.json +
                                     analyst_report.md) plus the manifest. Bundled into each day's
                                     `formatter_request.md` by `poc_runner.py --prep-format`.
.claude/agents/rsm-*.md            ← OPTIONAL Claude Code convenience wrappers.
                                     If working in Claude Code, may mirror the canonical prompts
                                     for subagent-dispatch ergonomics. Not required; not load-bearing.
```

### What changes or is added

```
tools/seerist_client.py            ← ADD _aoi_param_for_region("MED")="IT,ES,GR,TR,MA,EG",
                                     use it in get_events / get_verified_events / get_hotspots /
                                     get_news / get_analysis_reports / get_breaking_events /
                                     search_wod / get_events_since for MED.
                                     KEEP existing `_feature_country_iso2()` normalizer + ISO-2
                                     `REGION_COUNTRY_FILTER["MED"]={"IT","ES","GR","TR","MA","EG"}`
                                     and `_filter_by_country` defense-in-depth on ALL endpoint methods
                                     (clusters + hotspots expose `location_metadata.countryCode` in ISO-2;
                                     WoD endpoints expose top-level `countryCode` in ISO-3 — the
                                     normalizer collapses both to ISO-2 so a single filter set works).

tools/seerist_collector.py         ← ADD _haversine_km helper.
                                     REPLACE POI block (lines 54–71): group events by nearest facility,
                                     populate matching_events + nearest_event_km per site.

tools/notifier.py                  ← UNCHANGED. Not used in this PoC. Operator emails manually.
                                     (Future iteration may revisit; out of scope here.)

(No audience config file. The operator already knows the RSM's address;
 we do not put it in git.)

tools/render_brief_html.py         ← NEW: reads rsm_brief_med_<date>.md + the manifest, renders
                                     email-safe HTML via Jinja into a NEW `rsm_email.html.j2` template
                                     (sibling of existing rsm.html.j2; email template is inline-CSS only,
                                     existing template stays untouched). Writes output/poc/med/<date>/email.html.

tools/validate_brief.py            ← NEW: replaces the parent repo's stop-hook validators (which
                                     are absent from this slice — README says `.claude/hooks/` are
                                     intentionally not carved in). Checks: (a) only site names from
                                     `data/aerowind_sites.json` MED entries appear in the brief,
                                     (b) personnel/expat counts in EXPOSURE blocks match the registry
                                     exactly, (c) required section headers all present, (d) cyber-deferred
                                     line literal-matches the PoC v1 fixed text. Called from poc_runner.py
                                     `--send` BEFORE render and BEFORE notifier. Non-zero exit blocks
                                     send.

tools/poc_runner.py                ← NEW: per-day orchestrator with THREE deterministic phases
                                     bracketing TWO operator-in-the-loop LLM steps (analyst, then
                                     formatter). Python cannot reach an agentic IDE's tool layer
                                     directly regardless of which IDE; the operator runs both LLM
                                     steps manually. The operator ALSO handles the email send
                                     manually after phase C produces `email.html`.
                                     Phase A `--collect`: seerist_collector.py + poi_proximity.py +
                                       rsm_input_builder.py + write `analyst_request.md` bundling the
                                       canonical analyst prompt + signal/POI/manifest/output paths.
                                     [operator: run analyst_request.md in their IDE → claims.json
                                      + analyst_report.md]
                                     Phase B `--prep-format`: validates claims.json + analyst_report.md
                                       exist; writes `formatter_request.md` bundling the canonical
                                       formatter prompt + the analyst output paths + the manifest.
                                     [operator: run formatter_request.md in their IDE → brief.md]
                                     Phase C `--render`: validate_brief.py + render_brief_html.py.
                                       Verifies brief.md exists; non-zero validator exit blocks render.
                                     [operator: open email.html, copy, paste into Gmail compose, send]
                                       Operator records send in _qa_log.md.
                                     Per-day archive: `output/poc/med/<date>/{seerist_signals.json,
                                     poi_proximity.json, _rsm_manifest_daily.json, brief.md, email.html}`.
                                     The canonical `output/regional/med/` outputs stay working-state and
                                     are overwritten each day; the dated PoC dir is the archive. No
                                     delivery.json — operator-send isn't programmatically observable.

tests/test_seerist_poi.py          ← NEW: POI parameterisation + per-site matching (tests from
                                     prior plan 2026-05-06 §Phase 1)

tests/test_seerist_regions.py      ← NEW: MED-specific subset of prior plan §Phase 2 tests
                                     (just test_aoi_param_for_subregion for MED, plus filter_by_country
                                     ISO-3 for MED). Other regions not in scope.

tests/test_render_brief_html.py    ← NEW: snapshot test that rendered HTML contains all section
                                     headers + does not contain any site name outside aerowind_sites.json

docs/poc/med-rsm-week/             ← NEW: per-day QA log + final sponsor memo
  ├─ _qa_log.md                    ← appended each morning during QA pass
  ├─ feedback_log.md               ← appended whenever the RSM replies
  └─ sponsor_memo.md               ← drafted Day 0, filled Day 7

output/regional/med/               ← EXISTING working-state (overwritten each day by collectors)
  ├─ seerist_signals.json           ← canonical output of seerist_collector.py
  └─ poi_proximity.json             ← canonical output of poi_proximity.py

output/poc/med/<YYYY-MM-DD>/       ← NEW per-day archive (poc_runner copies into here)
  ├─ seerist_signals.json           ← copied from output/regional/med/ after collect
  ├─ poi_proximity.json             ← copied from output/regional/med/ after POI
  ├─ _rsm_manifest_daily.json       ← built by rsm_input_builder
  ├─ analyst_request.md             ← Phase A output — operator runs in their IDE
  ├─ claims.json                    ← LLM step 1 output (analyst) — structured claims registry
  ├─ analyst_report.md              ← LLM step 1 output (analyst) — narrative
  ├─ formatter_request.md           ← Phase B output — operator runs in their IDE
  ├─ brief.md                       ← LLM step 2 output (formatter) — RSM SITREP markdown
  └─ email.html                     ← rendered by render_brief_html.py; operator opens + copies + pastes

Rationale: existing tools (`seerist_collector.py`, `poi_proximity.py`) write to fixed canonical paths under `output/regional/<region>/`. We don't parameterise their output paths — `poc_runner.py` copies the artifacts into the dated PoC directory after each step. The canonical paths stay valid working-state for any downstream pipeline tooling.
```

### Data flow (one morning)

```
07:00 CET   operator runs: uv run python tools/poc_runner.py MED 2026-05-XX --collect
            ├─ Seerist collect for last 24h (live API, ~30 sec)
            ├─ POI proximity (haversine-grouped per site)
            ├─ rsm_input_builder → manifest JSON
            ├─ write analyst_request.md (bundles canonical analyst prompt + paths)
            └─ Prints "PHASE A COMPLETE — READY TO RUN ANALYST REQUEST"

07:05 CET   operator opens output/poc/med/<date>/analyst_request.md in their
            available agentic IDE (Claude Code / Codex CLI / GitHub Copilot
            Chat or Agent mode / other model workbench). The IDE/model reads
            signals + POI + manifest and writes claims.json + analyst_report.md.
            Operator skims both for hallucinations (phantom signal_ids,
            out-of-registry sites) and iterates if needed. ~5–10 min.

07:15 CET   operator runs: uv run python tools/poc_runner.py MED 2026-05-XX --prep-format
            └─ Reads claims.json + analyst_report.md; writes formatter_request.md

07:16 CET   operator opens formatter_request.md in their IDE. The IDE/model
            reads claims + report + manifest and writes brief.md. ~5–10 min.

07:25 CET   operator runs: uv run python tools/poc_runner.py MED 2026-05-XX --render
            ├─ validate_brief.py (non-zero exit blocks render)
            ├─ render_brief_html → email.html
            └─ Prints: "OPEN: output/poc/med/<date>/email.html"

07:27 CET   operator opens email.html in browser, reads — 5–10 min QA.
            If anything's off: edit brief.md, re-run --render, re-read.

07:33 CET   operator: Ctrl+A in browser, Ctrl+C, switch to Gmail compose,
            paste, type recipient + subject, hit Send.

07:35 CET   email in RSM inbox (operator-observable, not pipeline-observable).
            Operator appends row to _qa_log.md: sent? = yes, QA time, corrections.

Throughout the day  whenever the RSM replies, copy reply text into docs/poc/med-rsm-week/feedback_log.md
                    under a dated heading.
```

The agent-dispatch step is a manual context-switch into whichever agentic IDE the operator has available — Claude Code, Codex CLI, GitHub Copilot Chat/Agent in VSCode, or any other model workbench that can read the bundled `formatter_request.md` and write `brief.md`. Acceptable for a 7-day operator-in-the-loop PoC; fully automated dispatch is a separate session (and a per-IDE problem).

---

## 4. Timeline — 7 day PoC + Day 0 prep

### Day 0 — Prep (1–3 calendar days before PoC start)

The PoC clock doesn't start until Day 0 is complete and a dry-run email lands in your own inbox.

| Item | Owner | Done when |
|---|---|---|
| POI proximity haversine fix in collector + test passing | code | `pytest tests/test_seerist_poi.py` green |
| MED-AOI helper in client + test passing | code | `pytest tests/test_seerist_med_aoi.py` green |
| `validate_brief.py` written + test passing (site discipline, personnel match, cyber line) | code | `pytest tests/test_validate_brief.py` green |
| `render_brief_html.py` written + email-safe HTML template (with G14 footer) + snapshot test passing | code | `pytest tests/test_render_brief_html.py` green |
| `poc_runner.py` two-phase orchestrator (collect / render) | code | `python tools/poc_runner.py MED <today> --render` returns clear "brief.md not found" error pre-agent |
| Formatter-agent prompt iteration: consequence-line tightening + TODAY'S CALL exemplars + cyber-section fixed line | prompt | one live MED day read end-to-end and you judge it "ship" |
| Pre-week manual paste test: render a dryrun email.html, paste into Gmail compose, send to yourself, read in Gmail web + mobile. Iterate template until it looks right. | manual | "I'd be OK with this in his inbox" |
| `sponsor_memo.md` template scaffolded with empty fill-in sections | docs | file committed |

### Days 1–N — Live PoC (N=5 default, up to 7)

Cadence: **5 business days (Mon–Fri) by default.** Sat + Sun added only if the RSM explicitly says he reads weekend mail. Minimum acceptable run is 4 sends out of 5–7; missed days must have a written reason in `_qa_log.md`.

Same operator routine each morning. Wall-clock ~35–40 minutes from kickoff to send; **operator-attention time is ~20–25 minutes** — two LLM steps (analyst ~5–10 min including review, formatter ~5–10 min) plus rendered-email QA (~5–10 min) plus paste/send (~2 min). The deterministic phases (collect/prep-format/render) each take under 60 seconds. The user accepted this expanded daily cost in exchange for the analytical depth of the two-step chain over the previous single-step formatter.

| Day | Calendar | Operator routine |
|---|---|---|
| 1 | Mon | 07:00 collect+manifest, 07:05 dispatch agent, 07:10 validate→render→QA→send. RSM gets first email. |
| 2 | Tue | Same. Read any RSM reply from Day 1 → log to feedback_log.md (classify per G14 taxonomy). |
| 3 | Wed | Same. Mid-week check: any prompt fixes obvious from 2 days of QA? Apply tonight, not in the morning. |
| 4 | Thu | Same. If RSM is still silent, send one short follow-up: "Three days in — any quick reaction helps." |
| 5 | Fri | Same. Fri evening: schedule the sponsor-memo writeup. |
| 6 | Sat | OPTIONAL — only if RSM said he reads weekend mail. Otherwise skip and log "weekend skip — agreed cadence." |
| 7 | Sun | OPTIONAL — same condition as Sat. |

### Day 8 — Sponsor memo + decision

| Item | Done when |
|---|---|
| Fill `sponsor_memo.md` with: all emails sent (links to archive), feedback received (rolled up + classified from feedback_log.md), pipeline capability summary, recommendation (greenlight/pivot/kill) | sent to sponsor |
| Decide what stays and what gets deleted from the PoC plumbing | followup ticket created |

---

## 5. Pipeline gaps — concrete checklist

Priority order. Each item maps to where it lives in the timeline.

| # | Gap | Where | Phase |
|---|---|---|---|
| G1 | `_haversine_km` + per-site grouping replaces the broken POI block. Without this, `matching_events` is always empty and the AEROWIND EXPOSURE section has nothing to render. | `tools/seerist_collector.py:54–71` | Day 0 |
| G2 | `_aoi_param_for_region("MED")` returns `"IT,ES,GR,TR,MA,EG"`. Used by all MED-touching client methods. `REGION_AOI_MAP[MED]="MENA"` is too broad and lossy. | `tools/seerist_client.py` | Day 0 |
| G3 | Keep the existing ISO-2 `REGION_COUNTRY_FILTER["MED"]={"IT","ES","GR","TR","MA","EG"}` and `_feature_country_iso2()` normalizer as defense-in-depth on ALL endpoint methods. Cluster + hotspot endpoints DO carry country info (nested `location_metadata.countryCode`, ISO-2); WoD endpoints carry top-level `countryCode` (ISO-3) which the normalizer maps via `_ISO3_TO_ISO2`. Single ISO-2 filter set works for both. | `tools/seerist_client.py` | Day 0 |
| G4 | ~~Audience config~~ — REMOVED. Operator sends mail manually; no recipient list in git, no audience config file. |
| G5 | ~~Notifier multipart/HTML extension~~ — REMOVED. Operator sends mail manually. `notifier.py` is not used in this PoC; left untouched for any future automation revisit. |
| G6 | `render_brief_html.py` — reads `brief.md` and the manifest, renders email-safe HTML via Jinja with inline CSS. Writes `email.html`. | `tools/render_brief_html.py` NEW | Day 0 |
| G7 | Email-safe HTML template at `tools/briefs/templates/rsm_email.html.j2` — NEW file derived from `rsm.html.j2` but with inline CSS only, no `<style>` blocks, no external assets, single column, ≤640px content width. The existing `rsm.html.j2` stays untouched (it's the dashboard/PDF target from earlier work). | `tools/briefs/templates/rsm_email.html.j2` NEW | Day 0 |
| G8 | Two-step provider-agnostic agent chain: (a) `prompts/rsm_regional_analyst_daily.md` (NEW) — regional analyst writes claims.json + analyst_report.md with signal_id citations and analytical narrative. (b) `prompts/rsm_formatter_daily.md` (NEW canonical, updated by Task 5b) — formatter consumes analyst output instead of raw signals, applies sharper consequence-line + TODAY'S CALL instructions + cyber-section honest line. Both prompts are platform-neutral; `.claude/agents/*` files are OPTIONAL Claude convenience wrappers, not load-bearing. Restores the parent CRQ pipeline's analyst+formatter depth without the parallel-subagent harness. | `prompts/rsm_regional_analyst_daily.md` NEW; `prompts/rsm_formatter_daily.md` NEW; `.claude/agents/*` optional | Day 0 |
| G9 | `poc_runner.py` orchestrator with `--resume` mode for the post-agent half of the flow. | `tools/poc_runner.py` NEW | Day 0 |
| G10 | Tests: POI test from prior plan, MED-AOI test, render-snapshot test (HTML contains all section headers, no out-of-registry site names). | `tests/test_seerist_poi.py`, `tests/test_seerist_regions.py`, `tests/test_render_brief_html.py` NEW | Day 0 |
| G11 | `sponsor_memo.md` template + `_qa_log.md` template + `feedback_log.md` template. | `docs/poc/med-rsm-week/` NEW | Day 0 |
| G12 | ~~SMTP credentials~~ — REMOVED. Operator uses their normal mail client; no SMTP code path. |
| G13 | `tools/validate_brief.py` — local replacement for the parent repo's `.claude/hooks/validators/rsm-formatter-stop.py` (absent from this slice per README). Validates the brief.md against the registry + cyber-deferred fixed line BEFORE render/send. Non-zero exit blocks send. | `tools/validate_brief.py` NEW | Day 0 |
| G14 | Feedback taxonomy in email footer and operator log. Email footer reply-prompt: `Reply with: USEFUL · NOISE · MISSED CONTEXT · FALSE POSITIVE (+ one sentence)`. Operator `_qa_log.md` row per day captures: sent?, QA time, corrections made, RSM replied?, RSM reply class (useful/noise/missed/false-positive), sponsor-worthy example?. | `tools/briefs/templates/rsm_email.html.j2`, `docs/poc/med-rsm-week/_qa_log.md` | Day 0 |

### Decision on the cyber gap (G8c)

The cyber section is included as a real `█ CYBER — LAST 24H` block in every brief, with one explicit line:

> Cyber not collected in PoC v1 — see footer.

The footer line reads:

> PoC v1 — cyber feed deferred to v2. Feedback welcome at this address.

This is more honest than dropping the section silently, and avoids the "RSM expected cyber and got nothing" reaction.

---

## 6. Acceptance criteria

PoC is complete when **all of these are true**:

**Day 0 functional gates (engineering-verifiable):**

1. `uv run pytest tests/` is green (POI grouping, MED-AOI, notifier multipart, validate_brief, render_brief_html tests all pass).
2. On a representative Day 0 dry-run, `seerist_collector.py MED --window 7` (wider window for fixture variety) produces a `seerist_signals.json` with `poi_alerts[].matching_events` non-empty for at least one MED site. This proves POI grouping works end-to-end. It is a one-time gate, not a daily gate — a quiet real-world day with zero site-near events is a legitimate brief outcome.
3. Day 0 dry-run end-to-end: own-inbox test send completes; HTML renders correctly in Gmail web AND on phone (noted in `_qa_log.md`).

**Live PoC gates (operational):**

4. Cadence delivered as planned: default 5 business days (Mon–Fri). Optional Sat/Sun only if the RSM said he reads weekend mail. Minimum 4 operator-sent emails out of the planned 5–7 to count as "PoC ran." Each missed day must have an explanation row in `_qa_log.md`.
5. Every operator-sent email was preceded by `validate_brief.py` exit-code 0 (site-name discipline, personnel-count match, fixed cyber line present). Zero send-time validation bypasses.
6. Operator records each day's send in `_qa_log.md` (date, sent? = yes/no/skip, QA time, corrections made). The operator-send is not pipeline-observable; the qa_log is the authoritative record.
7. `feedback_log.md` contains every RSM reply during the week, classified per the G14 taxonomy (useful / noise / missed context / false positive). Zero replies is itself a finding worth logging.

**Sponsor decision gate:**

8. `sponsor_memo.md` is filled with: links to all sent emails, rolled-up RSM feedback, pipeline capability and gap summary, and a recommendation (greenlight / pivot / kill) with one-sentence rationale.
9. You can answer "yes" without hedging to: *would I be embarrassed if my sponsor opened any one of these emails at random?*

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| RSM doesn't reply at all → no feedback signal | Day 4 lightweight nudge: "still useful?" reply. If still silent by Day 5, the silence itself becomes a finding for the sponsor memo. |
| HTML renders broken in Outlook | Day 0 prep includes manual rendering test in Gmail + Outlook web + mobile. Use only the email-safe CSS subset. |
| Seerist API rate limit or outage on a PoC morning | Cache the prior day's collect; on miss, surface a "Seerist degraded today" line in the email so the RSM sees honesty. Do NOT silently skip. |
| Formatter agent generates a site name not in `aerowind_sites.json` | Existing stop hook catches this. If repeated, investigate the prompt, do not bypass the hook. |
| Operator can't run the morning routine one day (sick, travel) | Skip the day; log in `_qa_log.md`. 6 days of email is still PoC-acceptable — don't ship a degraded brief to keep the streak. |
| RSM finds a real factual error → trust loss | Reply immediately acknowledging, fix in tomorrow's brief, note in feedback_log. Trust matters more than the streak. |
| Email goes to spam | Day 0 prep: SPF/DKIM/DMARC alignment for the `from` domain; test sends to a real Gmail account before live. |

---

## 8. Open questions to resolve at plan-time (not now)

These are intentionally NOT decided in this design; they belong in the implementation plan:

- **Exact send slot:** 07:30 CET is the default; confirm against RSM's calendar / time zone.
- **Sender email and display name:** placeholder is `intel@aerowind.example`; real value goes in `audience_config.json`.
- **Reply-handling triage:** does the RSM reply to a shared inbox or directly to you? Affects whether feedback log automation is worth building.
- **Weekend cadence:** Sat + Sun email or skip? Depends on RSM's actual work pattern.
- **Backfill option for Day 1:** if PoC clock starts on a Tuesday but RSM wants to see "Monday too," do we backfill a Monday brief into the Day 1 email or send two emails on Tuesday? Defer to plan-time.

---

## 9. What this design explicitly does NOT do

To prevent scope creep during implementation:

- No PDF generation.
- No weekly INTSUM synthesis (`rsm-weekly-synthesizer.md` agent is not invoked).
- No bundle/archive delivery — every email is standalone.
- No web-archive hosting.
- No automated dispatcher — operator manually runs the daily `formatter_request.md` each morning in whichever agentic IDE is available (Claude Code, Codex CLI, GitHub Copilot IDE, or another model workbench).
- No cyber feed integration. The cyber section says it's deferred.
- No multi-region work. MED only.
- No Scribe, AskAnna, or WoD targeted search.
- No `since`-parameter delta collection. Each morning is a fresh 24h window pull.

These are deliberate scope cuts to fit the "QA pass only (5–10 min/day)" daily budget and the "simple, clean HTML email" format constraint.
