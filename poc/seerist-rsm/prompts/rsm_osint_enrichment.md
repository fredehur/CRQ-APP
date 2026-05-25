# OSINT Physical-Pillar Enrichment — Provider-Agnostic Prompt

You enrich RAW OSINT physical-pillar signals for a regional risk brief. Run in
Claude Code, Codex, GitHub Copilot, or any model workbench with repo access.

## Typed inputs
| Variable | Type | Description |
|---|---|---|
| OSINT_PATH | file | raw `osint_physical_signals.json` — each signal: `signal_id`, `title`, `url`, `content_excerpt` |
| SEERIST_PATH | file | the day's `seerist_signals.json` (may be absent) |

Read OSINT_PATH and (if present) SEERIST_PATH. Rewrite OSINT_PATH enriched, and
write OSINT_DROPPED_PATH (sibling `osint_dropped.json`).

## What to produce
For each raw signal, decide if it is genuinely relevant to the region's PHYSICAL
risk (unrest, armed conflict/terrorism, maritime/shipping disruption, natural
disaster affecting the region). Drop off-region / off-topic items (US-domestic,
healthcare/Medicare, generic explainers).

Rewrite `osint_physical_signals.json` as:
```json
{
  "region": "<REGION>", "pillar": "physical",
  "seerist_unavailable": <true if SEERIST_PATH absent>,
  "dropped_count": <int>,
  "signals": [
    {"signal_id": "...", "title": "...", "url": "...", "outlet": "...",
     "published_at": "...", "content_excerpt": "...",
     "summary": "<1-2 sentence factual digest of content_excerpt>",
     "corroborates_event": "<a SEERIST signal_id this item supports, or null>",
     "pillar": "physical", "category": "physical"}
  ]
}
```
Write `osint_dropped.json`: `{"region": "...", "dropped": [{"title","url","relevance_reason"}]}`.

## Rules
- Keep only relevant signals; renumber kept `signal_id`s as `osint:physical:<region>-001..NNN`.
- `summary` must be grounded in `content_excerpt` — do not invent.
- `corroborates_event` only if an item clearly supports a listed Seerist event; else null.
- Do NOT assign severity or a brief-section role — those are the analyst's job.
- If SEERIST_PATH is absent, set `seerist_unavailable: true` and all `corroborates_event` to null.
- **Cross-region maritime is in-scope when it cascades.** Strait of Hormuz / Suez
  Canal / Bab-el-Mandeb disruption affects MED shipping even though the incident
  is in AME. Keep these items and use `corroborates_event` to link to any MED-side
  Seerist event (e.g., a Suez backlog notice). If no MED-side cascade is observable,
  drop the item with `relevance_reason: "off-region; no MED cascade"`.
- **Outlet attribution:** `outlet` now contains a publication name (NPR, Reuters,
  Wikipedia, etc.), not a URL. Use it verbatim in `summary` when attribution helps.
- **Date:** `published_at` is best-effort — empty when both Tavily and Firecrawl
  return no date. Do not invent dates.
