# Company Context — Swap Guide

This slice ships with **AEROWIND** as the mock company (renewable energy / offshore wind). Three mock sites in the MED region: Casablanca, Palermo, Málaga. The pipeline works end-to-end against this mock company. When you want to point it at a different real company, this doc tells you exactly what to change.

Two kinds of context get swapped: (A) **structured data** in JSON files — straightforward, schema-driven; (B) **brand strings** in prompts, templates, and code defaults — find/replace work.

---

## A. Structured data (JSON files)

### A.1 Sites / factories / plants — `data/aerowind_sites.json`

This is the canonical site registry. Each entry is one operational location the RSM cares about — a factory, a wind farm, an HQ, a substation, a port operations base. Fields per site:

| Field | What it is | Example |
|---|---|---|
| `site_id` | Stable opaque key | `"med-pal"` |
| `name` | Display name in briefs | `"Palermo Offshore Ops"` |
| `region` | One of APAC, AME, LATAM, MED, NCE | `"MED"` |
| `country` | ISO-2 country code | `"IT"` |
| `lat`, `lon` | Decimal degrees | `38.12, 13.36` |
| `poi_radius_km` | Site exposure radius (Seerist POI search) | `50` |
| `personnel_count` | Total headcount on site | `210` |
| `expat_count` | Non-local employees (duty-of-care) | `14` |
| `criticality` | `crown_jewel` / `major` / `standard` | `"crown_jewel"` |
| `tier` | `crown_jewel` / `minor` | `"crown_jewel"` |
| `notable_dates` | Optional list of `{date, event, risk}` for the next-7-days horizon | `[{"date":"2026-06-15","event":"shareholder visit","risk":"..."}]` |
| `relevant_seerist_categories` | Event categories to watch for this site | `["labour_dispute","civil_unrest"]` |

To swap: replace the `sites` array with the new company's facilities. Same schema. The pipeline picks it up automatically — no code changes needed for site swaps within an existing region. If your company is in a different region than the five we support (APAC/AME/LATAM/MED/NCE), see Section C.

Readers of this file (update if you rename it):
- `tools/seerist_collector.py` — POI block reads `data/aerowind_sites.json`
- `tools/rsm_input_builder.py` — manifest builder reads it
- `prompts/rsm_formatter_daily.md` — references file in input-list prose
- `.claude/agents/rsm-formatter-agent.md` — optional Claude wrapper, only if in use

### A.2 Crown jewels + footprint — `data/company_profile.json`

Holds the company name, industry, regional footprint, and a list of crown-jewel assets (the things whose loss would be material). The formatter agent reads this to ground brief language. Swap the fields directly:

```json
{
  "company_name": "Your Company Name",
  "industry": "Your industry — affects formatter analogies",
  "global_footprint": ["MED", "NCE"],
  "crown_jewels": ["Asset 1 description", "Asset 2 description"],
  "employee_count": 0,
  "risk_appetite": "...",
  "strategic_priorities": "..."
}
```

### A.3 Mock fixtures — `data/mock_osint_fixtures/*.json`

These are used only in mock-mode runs. They include example events keyed to AEROWIND sites. For live PoC use against a real company, you don't need to regenerate these — live Seerist data replaces them. If you want clean mock runs for the new company, regenerate fixtures with the new site names.

---

## B. Brand strings (find/replace)

Every place "AEROWIND" or "aerowind" appears in PROSE (not data). Use grep first to confirm the list hasn't drifted:

```
grep -ril "aerowind" --include="*.md" --include="*.py" --include="*.j2" .
```

Then replace in these specific files:

| File | What to change |
|---|---|
| `README.md` | Top-level slice description + any header band examples |
| `tools/briefs/templates/rsm.html.j2` | `AEROWIND //` header band |
| `tools/briefs/templates/rsm_email.html.j2` | `AEROWIND //` header band + footer signoff |
| `prompts/rsm_regional_analyst_daily.md` | **Canonical provider-agnostic ANALYST prompt** (runs first in the daily chain). "AEROWIND" in voice instructions + "Palermo / Casablanca" in any exemplars. Change here first. |
| `prompts/rsm_formatter_daily.md` | **Canonical provider-agnostic FORMATTER prompt** (runs second in the daily chain). "AEROWIND //" header in the required-output-shape block + "Palermo / Casablanca" in consequence-line and TODAY'S-CALL exemplars. Change here first. |
| `.claude/agents/rsm-formatter-agent.md` | **Optional Claude convenience wrapper.** If you use it, mirror changes from `prompts/rsm_formatter_daily.md`. If you don't, ignore. |
| `.claude/agents/rsm-regional-analyst-agent.md` | **Optional Claude convenience wrapper** for the analyst. Same rule. |
| `.claude/agents/rsm-weekly-synthesizer.md` | Same as above — Claude convenience only, not load-bearing |
| `tools/notifier.py` | Default `from` address `noreply@aerowind.com` (unused in this PoC since you send manually, but rename for cleanliness) |
| `docs/poc/med-rsm-week/sponsor_memo.md` | Company-name mentions in the template (currently AEROWIND) |

Also rename these FILENAMES (and update every code reference that opens them — grep first to find them):

| Current filename | New filename suggestion |
|---|---|
| `data/aerowind_sites.json` | `data/<newcompany>_sites.json` OR generic `data/company_sites.json` (preferred — survives future renames) |

If you rename `aerowind_sites.json`, update these readers (listed above in A.1).

---

## C. Region swap (if the new company isn't in MED)

This slice is MED-only by carve. The MED region maps to Seerist's MENA AoI and filters by countries `IT, ES, GR, TR, MA, EG` (see `REGION_COUNTRY_FILTER` in `tools/seerist_client.py` line ~50).

If the new company operates in APAC / AME / LATAM / NCE:

1. Put new sites under the right `region` value in your renamed sites JSON.
2. Replace `MED` with the new region in CLI invocations: `poc_runner.py NEWREGION ...`.
3. Regenerate the mock fixtures path: `data/mock_osint_fixtures/<newregion>_*.json`.
4. Verify Seerist client AOI mapping for that region in `tools/seerist_client.py`:
   - `REGION_AOI_MAP` (line ~24) — CRQ region → Seerist AoI code
   - `REGION_COUNTRIES` (line ~33) — per-country endpoint lists
   - `REGION_COUNTRY_FILTER` (line ~50) — derived from `_REGION_COUNTRY_ORDER`; LATAM, MED, NCE use multi-country `aoiId` via `_aoi_param_for_region`; APAC and AME map directly to single Seerist AoIs.

If the new company operates in a region not in our five (APAC/AME/LATAM/MED/NCE), you need to extend `_aoi_param_for_region` and `REGION_COUNTRY_FILTER` in `tools/seerist_client.py`, plus add the region to `REGION_COUNTRIES` for Pulse calls. This is a real code change, not a config swap — be aware.

---

## D. Verification after swap

Run these in order; each should succeed before moving on:

```
uv run pytest tests/ -q
uv run python tools/seerist_collector.py NEWREGION --window 7   # mock OK if no SEERIST_API_KEY
uv run python tools/poc_runner.py NEWREGION 2026-MM-DD --collect
```

Then inspect `output/regional/<newregion>/seerist_signals.json` — the `poi_alerts[].facility` values should be the new company's site names. If they still say "Palermo" / "Casablanca" / "Málaga", you missed an `aerowind_sites.json` swap.

---

## E. What NOT to change

- `tools/seerist_client.py` — endpoint URLs, AOI mapping, normalization logic. These describe Seerist's API, not your company.
- `tools/poi_proximity.py` — generic geometry.
- `tools/validate_brief.py` — generic validator. The required-section list could be tweaked if your brief shape changes, but defaults are reasonable.
- `tests/` — the assertions key off generic schemas, not brand. Should pass against the new company's data unchanged.
