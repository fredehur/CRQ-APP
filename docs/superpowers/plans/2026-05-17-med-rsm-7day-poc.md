# MED RSM 7-Day PoC — Implementation Plan

**Goal:** Deliver 5 business days (Mon–Fri, optionally 7) of daily HTML-email intelligence briefs (MED region, AeroGrid sites) to one real RSM, generated from Seerist live data with a 5–10 min QA pass each morning. End-of-week artifact + RSM feedback becomes the sponsor greenlight pack.

**Architecture:** Day 0 hardens the MED-only pipeline (POI proximity haversine fix, MED multi-country AOI patch, HTML email rendering, local brief validator, provider-agnostic analyst + formatter prompts). Days 1–7 run a thin per-day orchestrator (`poc_runner.py`) in THREE phases bracketing TWO operator-in-the-loop LLM steps:

1. `--collect` (deterministic): seerist + POI + manifest + write `analyst_request.md`.
2. **Operator step 1**: run `analyst_request.md` in the available IDE (Claude Code, Codex, GitHub Copilot, etc.) → produces `claims.json` + `analyst_report.md`.
3. `--prep-format` (deterministic): read analyst output, write `formatter_request.md`.
4. **Operator step 2**: run `formatter_request.md` in the IDE → produces `brief.md`.
5. `--render` (deterministic): `validate_brief.py` + render `email.html`.
6. **Operator step 3** (no LLM): copy email.html into Gmail/Outlook compose, send.

The sequential analyst→formatter chain restores the analytical depth of the parent CRQ pipeline (which used parallel subagents via Claude Code's `TeamCreate`) but is platform-agnostic — each agent step is a request-file the operator hands to whatever model workbench they have. **No SMTP code in this PoC.** Day 8 produces the sponsor memo.

**Tech Stack:** Python 3.13, `httpx` (Seerist client), `uv`, `pytest`, Jinja2 (email template), manual Gmail/Outlook send by operator, provider-agnostic LLM/agentic IDE for the formatter step (Claude Code, Codex, GitHub Copilot IDE, etc.; model access required outside this codebase).

**Spec:** `docs/superpowers/specs/2026-05-17-med-rsm-7day-poc-design.md`

---

## Working directory and path conventions

**All shell commands assume your current working directory is `C:\Users\frede\crq-agent-workspace\poc\seerist-rsm\`** (per the slice's README — Python imports and `Path(__file__).resolve().parent.parent` rely on it).

| Path style in this plan | Means |
|---|---|
| `tools/foo.py`, `tests/foo.py`, `data/foo.json` | relative to `poc/seerist-rsm/` |
| `docs/...`, `output/...` | when prefixed `docs/superpowers/...` they live at the parent `crq-agent-workspace/` root; `output/...` lives inside `poc/seerist-rsm/output/` |

The spec and this plan live at `crq-agent-workspace/docs/superpowers/`; everything else this plan touches is inside the `poc/seerist-rsm/` slice.

---

## Agentic formatter layer — platform-agnostic contract

This PoC does **not** depend on Claude Code specifically. The codebase owns the deterministic parts: collection, manifest generation, validation, and HTML rendering. The agentic/model layer owns exactly one task: read the daily `formatter_request.md` + manifest, then write `brief.md` in the required SITREP shape.

Supported operator environments include:
- Claude Code / Pi subagent flow
- Codex CLI or Codex IDE workflow
- GitHub Copilot Chat/Agent mode inside VSCode
- Any other model workbench that can read the request/manifest and write or return markdown

The requirement is not a product-specific API. The requirement is capability:
1. Access to a suitable model.
2. Ability to read the daily `formatter_request.md` and `_rsm_manifest_daily.json`.
3. Ability to write `brief.md` at the requested path, or return markdown that the operator saves there.
4. No invented sources/sites; `tools/validate_brief.py` remains the required quality gate before rendering.

Claude-specific `.claude/agents/*` files may exist as convenience wrappers, but the canonical prompt contract for this PoC is the provider-neutral file `prompts/rsm_formatter_daily.md`, copied into each day's `formatter_request.md` by `poc_runner.py --collect`.

---

## File Structure

**Created:**
- `tests/test_seerist_poi.py` — POI parameterisation + per-site haversine grouping tests (mocked)
- `tests/test_seerist_med_aoi.py` — MED multi-country `aoiId` parameterisation test
- `tests/test_render_brief_html.py` — snapshot test that rendered HTML contains all section headers + no out-of-registry site names
- `tests/test_validate_brief.py` — local validator: site-name discipline, personnel-count match, cyber-line literal-match
- `tools/render_brief_html.py` — reads `brief.md` + manifest, renders email-safe HTML via Jinja
- `tools/validate_brief.py` — replaces the absent parent-repo stop hook with a local validator script
- `tools/poc_runner.py` — per-day orchestrator with THREE phases: `--collect` (writes `analyst_request.md`), `--prep-format` (reads analyst output, writes `formatter_request.md`), `--render` (validates + renders email.html). Two operator-in-the-loop LLM steps bracket the deterministic phases.
- `tools/briefs/templates/rsm_email.html.j2` — NEW email-safe Jinja template, inline CSS only, G14 reply taxonomy footer
- `prompts/rsm_regional_analyst_daily.md` — canonical provider-agnostic ANALYST prompt (Task 5a). Bundled into each day's `analyst_request.md` by `poc_runner.py --collect`.
- `prompts/rsm_formatter_daily.md` — canonical provider-agnostic FORMATTER prompt (Task 5, updated by Task 5b to read analyst output). Bundled into each day's `formatter_request.md` by `poc_runner.py --prep-format`.
- `CONTEXT.md` (at slice root) — swap guide for porting to a new company (Task 8a)
- `../../docs/poc/med-rsm-week/_qa_log.md` — appended each morning during QA, columns include G14 reply class
- `../../docs/poc/med-rsm-week/feedback_log.md` — appended when RSM replies (classified per G14)
- `../../docs/poc/med-rsm-week/sponsor_memo.md` — template scaffold, filled D8

**Modified:**
- `tools/seerist_client.py` — add `_aoi_param_for_region`, switch MED-touching methods to use it
- `tools/seerist_collector.py` lines 41–73 — replace POI block with haversine-grouped per-site assignment

**Untouched (was in earlier draft, now out of scope):**
- `tools/notifier.py` — operator handles email manually; SMTP path not used in this PoC
- `data/audience_config.*.json` — no audience config file; operator already knows the recipient
- `.claude/agents/rsm-formatter-agent.md`, `.claude/agents/rsm-regional-analyst-agent.md` — OPTIONAL Claude convenience wrappers. Canonical prompts for this PoC are the provider-agnostic files under `prompts/`. May be mirrored if you want Claude-Code-native subagent ergonomics, but not required and not load-bearing.

**Conventions:**
- Tests live in `tests/` next to existing `test_seerist_*.py`. Use `pytest` with mocks (`unittest.mock`).
- Live API tests gated behind `--live-seerist` pytest flag (skip by default). The Day 0 dry-run uses `--live-seerist`.
- One commit per task (not per step). Commit message format follows the repo's `type(scope): subject` convention visible in git log.

---

## Task 1 — POI proximity: per-site haversine grouping

**Why first:** Without this, `matching_events` in `seerist_signals.json` is always empty and the AEROWIND EXPOSURE section in the daily brief has nothing to render — the entire value prop of the PoC depends on this.

**Files:**
- Modify: `tools/seerist_collector.py:41–73` (the POI block inside `_live_collect`)
- Create: `tests/test_seerist_poi.py`

### Steps

- [ ] **Step 1: Write the failing test**

Create `tests/test_seerist_poi.py`:

```python
"""POI proximity — per-site haversine grouping tests."""
import json
from unittest.mock import MagicMock, patch

from tools import seerist_collector


def _feature(lon, lat, title="evt", severity=3):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "title": title,
            "severity": severity,
            "countryCode": "ITA",
            "publishDate": "2026-05-17T00:00:00Z",
            "sourcesCount": 4,
        },
    }


def test_poi_alerts_group_events_to_nearest_site(monkeypatch):
    """Two MED sites + two events, one near each. Each alert references its
    own site and only its own matching events."""
    sites = {"sites": [
        {"site_id": "med-pal", "name": "Palermo", "region": "MED",
         "lat": 38.13, "lon": 13.34, "poi_radius_km": 50,
         "criticality": "crown_jewel", "personnel": 120, "expat_count": 8},
        {"site_id": "med-mal", "name": "Malaga", "region": "MED",
         "lat": 36.72, "lon": -4.42, "poi_radius_km": 50,
         "criticality": "tier_one", "personnel": 85, "expat_count": 4},
    ]}
    monkeypatch.setattr("pathlib.Path.read_text",
                        lambda self, **kw: json.dumps(sites))

    fake_client = MagicMock()
    fake_client.get_pulse.return_value = {}
    fake_client.get_events.return_value = []
    fake_client.get_verified_events.return_value = []
    fake_client.get_breaking_events.return_value = []
    fake_client.get_news.return_value = []
    fake_client.get_hotspots.return_value = []
    fake_client.get_analysis_reports.return_value = []
    fake_client.get_risk_ratings.return_value = {}
    fake_client.search_poi.return_value = [
        _feature(13.35, 38.14, "near_palermo"),   # ~1km from Palermo
        _feature(-4.40, 36.73, "near_malaga"),    # ~2km from Malaga
    ]
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None

    # NOTE: _live_collect imports SeeristClient INSIDE the function, so patching
    # `seerist_collector.SeeristClient` does not intercept the import — patch on
    # the source module instead.
    with patch("tools.seerist_client.SeeristClient.create", return_value=fake_client), \
         patch("tools.seerist_client.REGION_COUNTRIES",
               {"MED": ["IT", "ES", "GR", "TR", "MA", "EG"]}):
        result = seerist_collector._live_collect("MED", window_days=1)

    alerts = result["poi_alerts"]
    assert {a["facility"] for a in alerts} == {"Palermo", "Malaga"}

    palermo = next(a for a in alerts if a["facility"] == "Palermo")
    malaga = next(a for a in alerts if a["facility"] == "Malaga")

    assert any(e["title"] == "near_palermo" for e in palermo["matching_events"])
    assert not any(e["title"] == "near_malaga" for e in palermo["matching_events"])
    assert any(e["title"] == "near_malaga" for e in malaga["matching_events"])

    assert 0 < palermo["nearest_event_km"] < 5
    assert 0 < malaga["nearest_event_km"] < 5


def test_poi_alert_with_no_nearby_events_records_zero(monkeypatch):
    """Site with no events inside its radius still gets an alert row — with
    empty matching_events and nearest_event_km=None (sentinel)."""
    sites = {"sites": [
        {"site_id": "med-cas", "name": "Casablanca", "region": "MED",
         "lat": 33.57, "lon": -7.59, "poi_radius_km": 50,
         "criticality": "tier_two", "personnel": 40, "expat_count": 2},
    ]}
    monkeypatch.setattr("pathlib.Path.read_text",
                        lambda self, **kw: json.dumps(sites))

    fake_client = MagicMock()
    fake_client.get_pulse.return_value = {}
    fake_client.get_events.return_value = []
    fake_client.get_verified_events.return_value = []
    fake_client.get_breaking_events.return_value = []
    fake_client.get_news.return_value = []
    fake_client.get_hotspots.return_value = []
    fake_client.get_analysis_reports.return_value = []
    fake_client.get_risk_ratings.return_value = {}
    # Event 1000km from Casablanca — outside the 50km radius
    fake_client.search_poi.return_value = [_feature(13.35, 38.14, "far_away")]
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None

    # NOTE: _live_collect imports SeeristClient INSIDE the function, so patching
    # `seerist_collector.SeeristClient` does not intercept the import — patch on
    # the source module instead.
    with patch("tools.seerist_client.SeeristClient.create", return_value=fake_client), \
         patch("tools.seerist_client.REGION_COUNTRIES",
               {"MED": ["IT", "ES", "GR", "TR", "MA", "EG"]}):
        result = seerist_collector._live_collect("MED", window_days=1)

    alerts = result["poi_alerts"]
    assert len(alerts) == 1
    assert alerts[0]["facility"] == "Casablanca"
    assert alerts[0]["matching_events"] == []
    assert alerts[0]["nearest_event_km"] is None
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_seerist_poi.py -v
```

Expected: both tests FAIL. The current code (lines 54–71 in `tools/seerist_collector.py`) assigns every event to `facilities[0]` and leaves `matching_events: []` hardcoded.

- [ ] **Step 3: Add `_haversine_km` helper at module top of `seerist_collector.py`**

Add immediately after the `FIXTURES_DIR = …` line:

```python
import math


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in kilometres between two (lon, lat) points."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
```

- [ ] **Step 4: Replace the POI block in `_live_collect`**

In `tools/seerist_collector.py`, find the block currently at lines 53–73:

```python
    # Load facility coords for POI search
    poi_alerts = []
    try:
        sites_doc = json.loads(Path("data/aerowind_sites.json").read_text(encoding="utf-8"))
        facilities = [s for s in sites_doc.get("sites", []) if s["region"] == region]
        if facilities:
            pois = [[f["lon"], f["lat"], f["poi_radius_km"]] for f in facilities]
            poi_features = client.search_poi(pois, days=window_days)
            for i, f in enumerate(poi_features):
                props = f.get("properties", {})
                fac = facilities[0]  # nearest facility
                poi_alerts.append({
                    "signal_id": f"seerist:poi:{region.lower()}-{i + 1:03d}",
                    "facility": fac["name"],
                    "coordinates": [fac["lon"], fac["lat"]],
                    "radius_km": fac["poi_radius_km"],
                    "matching_events": [],
                    "nearest_event_km": 0,
                })
    except Exception as e:
        print(f"[seerist_collector] POI search error: {e}", file=sys.stderr)
```

Replace it entirely with:

```python
    # Load facility coords for POI search — group events by nearest facility
    poi_alerts = []
    try:
        sites_doc = json.loads(Path("data/aerowind_sites.json").read_text(encoding="utf-8"))
        facilities = [s for s in sites_doc.get("sites", []) if s["region"] == region]
        if facilities:
            pois = [[f["lon"], f["lat"], f["poi_radius_km"]] for f in facilities]
            poi_features = client.search_poi(pois, days=window_days)
            for fac in facilities:
                fac_events = []
                nearest_km = float("inf")
                for feature in poi_features:
                    coords = feature.get("geometry", {}).get("coordinates", [0, 0])
                    if len(coords) < 2:
                        continue
                    d = _haversine_km(fac["lon"], fac["lat"], coords[0], coords[1])
                    if d <= fac["poi_radius_km"]:
                        props = feature.get("properties", {})
                        fac_events.append({
                            "title": props.get("title") or props.get("name", ""),
                            "severity": props.get("severity", 0),
                            "distance_km": round(d, 2),
                            "verified": props.get("eventType") == "verified",
                            "source_count": props.get("cluster_size") or props.get("sourcesCount", 0),
                            "timestamp": props.get("initialPublishedDate") or props.get("publishDate", ""),
                        })
                        nearest_km = min(nearest_km, d)
                poi_alerts.append({
                    "signal_id": f"seerist:poi:{region.lower()}-{fac['site_id']}",
                    "facility": fac["name"],
                    "site_id": fac["site_id"],
                    "coordinates": [fac["lon"], fac["lat"]],
                    "radius_km": fac["poi_radius_km"],
                    "matching_events": fac_events,
                    "nearest_event_km": round(nearest_km, 2) if nearest_km != float("inf") else None,
                })
    except Exception as e:
        print(f"[seerist_collector] POI search error: {e}", file=sys.stderr)
```

- [ ] **Step 5: Run tests to verify they pass**

```
uv run pytest tests/test_seerist_poi.py -v
```

Expected: both tests PASS.

- [ ] **Step 6: Run the existing test suite to confirm no regression**

```
uv run pytest tests/ -q
```

Expected: all existing tests still pass.

- [ ] **Step 7: Commit**

```
git add tools/seerist_collector.py tests/test_seerist_poi.py
git commit -m "fix(seerist): POI proximity grounds events to nearest site per-site

Haversine-grouped per-facility assignment replaces the broken block that
hardcoded matching_events=[] and assigned every event to facilities[0].
Sites with no events inside radius get an alert row with nearest_event_km=None.

Refs MED RSM PoC plan Task 1."
```

---

## Task 2 — MED multi-country `aoiId` patch in client

**Why now:** MED maps to `MENA` in `REGION_AOI_MAP`, which is too broad and includes many neighbouring countries. The slice already has the ISO-2 `REGION_COUNTRY_FILTER` and `_feature_country_iso2` normalizer for defense-in-depth. We add an `_aoi_param_for_region` helper so MED calls Seerist with `aoiId="IT,ES,GR,TR,MA,EG"` directly — Seerist filters upstream and we keep the post-filter on. This pairs neatly with the existing normalizer.

**Files:**
- Modify: `tools/seerist_client.py` — add helper + swap MED-touching methods
- Create: `tests/test_seerist_med_aoi.py`

### Steps

- [ ] **Step 1: Write the failing test**

Create `tests/test_seerist_med_aoi.py`:

```python
"""MED-specific multi-country aoiId parameterisation."""
from unittest.mock import MagicMock


def test_aoi_param_for_region_med():
    """MED resolves to a comma-separated ISO-2 country list, not 'MENA'."""
    from tools.seerist_client import _aoi_param_for_region
    assert _aoi_param_for_region("MED") == "IT,ES,GR,TR,MA,EG"


def test_aoi_param_for_region_passthrough_for_direct_regions():
    """APAC/AME still resolve directly to their Seerist AoIs."""
    from tools.seerist_client import _aoi_param_for_region
    assert _aoi_param_for_region("APAC") == "APAC"
    assert _aoi_param_for_region("AME") == "AMER"


def test_get_events_uses_country_list_for_med():
    """get_events('MED', …) sends aoiId='IT,ES,GR,TR,MA,EG' upstream."""
    from tools.seerist_client import SeeristClient
    client = SeeristClient.__new__(SeeristClient)
    client._client = MagicMock()
    client._client.get.return_value.json.return_value = {"features": []}
    client._client.get.return_value.raise_for_status = MagicMock()

    client.get_events("MED", days=7)

    args, kwargs = client._client.get.call_args
    assert kwargs["params"]["aoiId"] == "IT,ES,GR,TR,MA,EG"


def test_iso2_normalizer_handles_both_endpoint_schemas():
    """_feature_country_iso2 maps cluster (nested ISO-2) and WoD (top-level
    ISO-3) to the same ISO-2 representation. Confirms why the filter set
    only needs ISO-2."""
    from tools.seerist_client import _feature_country_iso2
    cluster = {"properties": {"location_metadata": {"countryCode": "IT"}}}
    wod = {"properties": {"countryCode": "ITA"}}
    assert _feature_country_iso2(cluster) == "IT"
    assert _feature_country_iso2(wod) == "IT"
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_seerist_med_aoi.py -v
```

Expected: the first three FAIL (`_aoi_param_for_region` does not exist; `get_events` still sends `aoiId="MENA"`). The fourth (`test_iso2_normalizer_handles_both_endpoint_schemas`) is a sanity check on existing code — it should PASS already.

- [ ] **Step 3: Add `_aoi_param_for_region` helper in `seerist_client.py`**

In `tools/seerist_client.py`, immediately after the `_ISO3_TO_ISO2` mapping (around line 53), add:

```python
# Some Seerist AoIs are too broad for our regional carve. For sub-regions,
# pass a comma-separated ISO-2 country list as aoiId — Seerist accepts this
# and filters upstream. The existing `_filter_by_country` stays as
# defense-in-depth (and handles the cluster-endpoint normalization via
# `_feature_country_iso2`).
def _aoi_param_for_region(region: str) -> str:
    """Return the aoiId param value for a CRQ region."""
    direct = {"APAC": "APAC", "AME": "AMER"}
    if region in direct:
        return direct[region]
    countries = REGION_COUNTRY_FILTER.get(region)
    if not countries:
        # Fall back to the legacy broad AoI for any region we haven't
        # carved (currently: none — APAC/AME/LATAM/MED/NCE all covered)
        return REGION_AOI_MAP[region]
    # REGION_COUNTRY_FILTER is a set; sort for deterministic test assertions
    return ",".join(sorted(countries))
```

NOTE on the ordering: `REGION_COUNTRY_FILTER["MED"] = {"IT", "ES", "GR", "TR", "MA", "EG"}` (a set). Sorted alphabetically that's `"EG,ES,GR,IT,MA,TR"`. Update the test to match alphabetical order, OR convert to a list-ordered helper. Simplest: switch to a tuple at the top of the file that preserves the spec order, then build the filter set from it.

Right above `REGION_COUNTRY_FILTER`, add:

```python
# Country lists per CRQ region, in spec order (used for aoiId construction).
# Sets below are derived from these for defense-in-depth filtering.
_REGION_COUNTRY_ORDER = {
    "LATAM": ("BR", "CL", "CO", "AR", "PE"),
    "MED":   ("IT", "ES", "GR", "TR", "MA", "EG"),
    "NCE":   ("DE", "PL", "DK", "SE", "NO", "FI"),
}
```

Change `REGION_COUNTRY_FILTER` to derive from this:

```python
REGION_COUNTRY_FILTER = {r: set(cs) for r, cs in _REGION_COUNTRY_ORDER.items()}
```

Then `_aoi_param_for_region` uses `_REGION_COUNTRY_ORDER` instead of the set, preserving order:

```python
def _aoi_param_for_region(region: str) -> str:
    """Return the aoiId param value for a CRQ region."""
    direct = {"APAC": "APAC", "AME": "AMER"}
    if region in direct:
        return direct[region]
    ordered = _REGION_COUNTRY_ORDER.get(region)
    if not ordered:
        return REGION_AOI_MAP[region]
    return ",".join(ordered)
```

- [ ] **Step 4: Swap `REGION_AOI_MAP[region]` → `_aoi_param_for_region(region)` in MED-touching methods**

These are the affected lines (verified by grep earlier):

| Method | Line (approx) |
|---|---|
| `get_events` | 253 |
| `get_verified_events` | 267 |
| `get_hotspots` | 280 |
| `get_analysis_reports` | 334 |
| `get_breaking_events` | 378 (around) |
| `get_news` | 399 (around) |
| `search_wod` | 428 (around) |
| `get_events_since` | 465 |

In each method, find:

```python
aoi = REGION_AOI_MAP[region]
```

Replace with:

```python
aoi = _aoi_param_for_region(region)
```

Leave `get_pulse` and `get_risk_ratings` alone — those call per-country endpoints and don't use `aoiId`.

- [ ] **Step 5: Run the new tests + the existing client tests**

```
uv run pytest tests/test_seerist_med_aoi.py tests/test_seerist_client.py -v
```

Expected: new MED tests PASS, existing tests still PASS.

- [ ] **Step 6: Live smoke check (requires SEERIST_API_KEY)**

The post-filter relies on `location_metadata.countryCode` for cluster/hotspot endpoints. If Seerist sometimes omits that nested field, MED events could still be dropped silently after the upstream `aoiId` filter. Verify with a one-shot live call:

```
SEERIST_API_KEY=$SEERIST_API_KEY python -c "
from tools.seerist_client import SeeristClient
c = SeeristClient.create()
assert c is not None, 'SEERIST_API_KEY not set'
with c:
    events = c.get_events('MED', days=7)
    hotspots = c.get_hotspots('MED', days=14)
print(f'events: {len(events)} (non-zero expected for a 7-day MED window)')
print(f'hotspots: {len(hotspots)} (zero is OK — hotspots are sparse)')
assert len(events) > 0, 'MED events empty — _filter_by_country may be over-filtering. Inspect feature.properties.location_metadata.countryCode in a raw response.'
print('OK')
"
```

Expected: prints `events: N (non-zero…)` with N > 0 and `OK`. If `events: 0`, inspect a raw response to see whether `location_metadata.countryCode` is present; if Seerist is now returning it under a different key for MED, update `_feature_country_iso2` or relax the post-filter for clusters/hotspots (the upstream `aoiId` is already trustworthy).

If you don't have `SEERIST_API_KEY` set yet, skip this step and re-run it as part of Task 9 (Day 0 dry-run) — but block on it before Day 1 live PoC.

- [ ] **Step 7: Commit**

```
git add tools/seerist_client.py tests/test_seerist_med_aoi.py
git commit -m "feat(seerist): MED uses multi-country aoiId, not broad 'MENA'

_aoi_param_for_region resolves MED to 'IT,ES,GR,TR,MA,EG' so Seerist
filters upstream instead of returning all-MENA features for client-side
filtering. Existing _feature_country_iso2 normalizer stays as
defense-in-depth (handles cluster nested ISO-2 + WoD ISO-3 in one set).

Refs MED RSM PoC plan Task 2."
```

---

## Task 3 — Email-safe HTML template

**Files:**
- Create: `tools/briefs/templates/rsm_email.html.j2`

The existing `rsm.html.j2` is for the dashboard/PDF path and uses external CSS — unsafe for email clients that strip `<style>` blocks. This is a NEW sibling template, inline-CSS only, single-column.

### Steps

- [ ] **Step 1: Create the template**

`tools/briefs/templates/rsm_email.html.j2`:

```jinja
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ subject }}</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:-apple-system,Segoe UI,system-ui,sans-serif;color:#1a1a1a;">
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#f4f4f4;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="640" style="max-width:640px;background:#ffffff;border:1px solid #d4d4d4;">

          {# Header band #}
          <tr>
            <td style="background:#0f1419;color:#f4f4f4;padding:18px 20px;font-family:SF Mono,Menlo,Consolas,monospace;font-size:13px;letter-spacing:0.06em;">
              AEROWIND // {{ region }} DAILY // {{ date_z }}
            </td>
          </tr>

          {# Stat strip #}
          <tr>
            <td style="background:#1f2937;color:#cbd5e1;padding:10px 20px;font-family:SF Mono,Menlo,Consolas,monospace;font-size:12px;">
              PULSE: {{ pulse_summary }} &nbsp;|&nbsp;
              ADM: {{ admiralty }} &nbsp;|&nbsp;
              NEW: {{ n_events }} EVT · {{ n_hotspots }} HOT · {{ n_cyber }} CYB
            </td>
          </tr>

          {% for section in sections %}
          <tr>
            <td style="padding:18px 20px;border-top:1px solid #e5e5e5;">
              <div style="font-family:SF Mono,Menlo,Consolas,monospace;font-size:12px;color:#374151;letter-spacing:0.08em;margin:0 0 10px;">
                █ {{ section.header }}
              </div>
              <div style="font-size:14px;line-height:1.55;color:#1a1a1a;white-space:pre-wrap;">{{ section.body }}</div>
            </td>
          </tr>
          {% endfor %}

          {# Footer — G14 reply taxonomy #}
          <tr>
            <td style="background:#fafafa;color:#525252;padding:14px 20px;border-top:1px solid #e5e5e5;font-size:12px;line-height:1.5;">
              <strong>Reply with one of:</strong> USEFUL · NOISE · MISSED CONTEXT · FALSE POSITIVE<br>
              + one sentence (what would make tomorrow's better)<br><br>
              AeroGrid Intelligence // {{ region }} RSM<br>
              <span style="color:#737373;font-style:italic;">PoC v1 — cyber feed deferred to v2. Feedback welcome at this address.</span>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

- [ ] **Step 2: Commit**

```
git add tools/briefs/templates/rsm_email.html.j2
git commit -m "feat(briefs): email-safe HTML template for RSM daily

Inline-CSS only, single column, 640px max width. Sibling of rsm.html.j2
(which targets dashboard/PDF and uses external CSS).

Refs MED RSM PoC plan Task 3."
```

---

## Task 4 — `render_brief_html.py`

**Files:**
- Create: `tools/render_brief_html.py`
- Create: `tests/test_render_brief_html.py`

The renderer reads the formatter-agent's markdown output (`brief.md`) + the manifest, splits the markdown into header / stat-strip / sections, and feeds them to the Jinja template.

### Steps

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_brief_html.py`:

```python
"""HTML brief renderer — section parsing + site-name discipline."""
import json
from pathlib import Path

from tools import render_brief_html


SAMPLE_BRIEF = """AEROWIND // MED DAILY // 2026-05-17Z
PULSE: 6.2 (▲ +0.3) | ADM: B2 | NEW: 3 EVT · 1 HOT · 0 CYB

█ SITUATION
Quiet night across MED with one new incident near Palermo.

█ AEROWIND EXPOSURE
▪ Palermo [CROWN_JEWEL · 120 personnel, 8 expat]
   ├─ Port strike escalates — 2.1km, severity MED, , 4 sources
   └─ Consequence: Inbound shipments delayed 24-48h.

█ PHYSICAL & GEOPOLITICAL — LAST 24H
▪ [UNREST][MED] Palermo — Port strike escalates.

█ CYBER — LAST 24H
Cyber not collected in PoC v1 — see footer.

█ EARLY WARNING — NEW
No new anomalies.

█ TODAY'S CALL
Track Palermo port reopening window. No site action required today.
"""


def test_render_returns_html_with_all_section_headers(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text(SAMPLE_BRIEF, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "region": "MED",
        "cadence": "daily",
        "site_registry": [
            {"site_id": "med-pal", "name": "Palermo"},
            {"site_id": "med-mal", "name": "Malaga"},
            {"site_id": "med-cas", "name": "Casablanca"},
        ],
    }))

    html = render_brief_html.render(brief, manifest, subject="TEST")

    for header in ["SITUATION", "AEROWIND EXPOSURE",
                   "PHYSICAL &amp; GEOPOLITICAL", "CYBER",
                   "EARLY WARNING", "TODAY"]:
        assert header in html, f"missing section header: {header}"
    assert "Palermo" in html
    assert "<html" in html


def test_render_rejects_out_of_registry_site_name(tmp_path):
    """If the brief mentions a site name not in the manifest's site_registry,
    render() raises a ValueError — anti-hallucination guard at render time."""
    brief = tmp_path / "brief.md"
    bad_brief = SAMPLE_BRIEF.replace("Palermo", "Genoa")  # Genoa not in MED registry
    brief.write_text(bad_brief, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "region": "MED",
        "cadence": "daily",
        "site_registry": [
            {"site_id": "med-pal", "name": "Palermo"},
            {"site_id": "med-mal", "name": "Malaga"},
            {"site_id": "med-cas", "name": "Casablanca"},
        ],
    }))

    import pytest
    with pytest.raises(ValueError, match="Genoa"):
        render_brief_html.render(brief, manifest, subject="TEST")


def test_render_extracts_pulse_admiralty_counters_from_strip(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text(SAMPLE_BRIEF, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "region": "MED", "cadence": "daily", "site_registry": []
    }))

    html = render_brief_html.render(brief, manifest, subject="TEST")
    assert "6.2" in html and "▲ +0.3" in html
    assert "B2" in html
    assert "3 EVT" in html and "1 HOT" in html and "0 CYB" in html
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_render_brief_html.py -v
```

Expected: ImportError (`render_brief_html` doesn't exist yet).

- [ ] **Step 3: Implement `render_brief_html.py`**

Create `tools/render_brief_html.py`:

```python
#!/usr/bin/env python3
"""Render an RSM daily brief markdown into an email-safe HTML body.

Usage:
    uv run python tools/render_brief_html.py BRIEF_MD MANIFEST_JSON --out OUTPUT_HTML
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html import escape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "tools" / "briefs" / "templates"
TEMPLATE_NAME = "rsm_email.html.j2"

_HEADER_RE = re.compile(r"^AEROWIND // (\S+) DAILY // (\S+)\s*$")
_STAT_RE = re.compile(
    r"^PULSE:\s*(.+?)\s*\|\s*ADM:\s*(.+?)\s*\|\s*NEW:\s*"
    r"(\d+)\s*EVT.*?(\d+)\s*HOT.*?(\d+)\s*CYB\s*$"
)
_SECTION_HEADER_RE = re.compile(r"^█\s*(.+?)\s*$")


def _parse_brief(text: str) -> dict:
    lines = text.splitlines()
    header_match = None
    stat_match = None
    sections: list[dict] = []
    current: dict | None = None
    for raw in lines:
        line = raw.rstrip()
        if not line:
            if current is not None:
                current["body_lines"].append("")
            continue
        if header_match is None:
            m = _HEADER_RE.match(line)
            if m:
                header_match = m
                continue
        if stat_match is None:
            m = _STAT_RE.match(line)
            if m:
                stat_match = m
                continue
        sh = _SECTION_HEADER_RE.match(line)
        if sh:
            if current is not None:
                sections.append(current)
            current = {"header": sh.group(1), "body_lines": []}
            continue
        if current is not None:
            current["body_lines"].append(line)
    if current is not None:
        sections.append(current)

    if header_match is None or stat_match is None:
        raise ValueError("Brief is missing AEROWIND header band or PULSE stat strip.")

    for s in sections:
        s["body"] = "\n".join(s["body_lines"]).strip()
        del s["body_lines"]

    return {
        "region": header_match.group(1),
        "date_z": header_match.group(2),
        "pulse_summary": stat_match.group(1),
        "admiralty": stat_match.group(2),
        "n_events": stat_match.group(3),
        "n_hotspots": stat_match.group(4),
        "n_cyber": stat_match.group(5),
        "sections": sections,
    }


def _check_site_discipline(brief_text: str, manifest: dict) -> None:
    """Reject the brief if any mentioned AeroGrid site name is outside
    the manifest's site_registry. Mirrors the stop-hook check at render time."""
    registered = {s["name"] for s in manifest.get("site_registry", [])}
    # Heuristic: AeroGrid site names appear at the start of EXPOSURE blocks,
    # prefixed by `▪ `. Pull every name in that position.
    candidate_names = set(
        re.findall(r"^\s*▪\s+([A-Za-z][\w \-]+?)\s*\[", brief_text, re.M)
    )
    illegal = candidate_names - registered
    if illegal:
        raise ValueError(
            f"Brief mentions site names outside manifest registry: {sorted(illegal)}. "
            f"Allowed: {sorted(registered)}"
        )


def render(brief_md: Path, manifest_json: Path, *, subject: str) -> str:
    """Render the brief markdown into an HTML string ready for operator copy-paste into Gmail/Outlook."""
    brief_text = brief_md.read_text(encoding="utf-8")
    manifest = json.loads(manifest_json.read_text(encoding="utf-8"))
    _check_site_discipline(brief_text, manifest)
    parsed = _parse_brief(brief_text)

    # Intentional design: Jinja autoescape is OFF for the .j2 template (it's a
    # whole-document HTML scaffold; we don't want Jinja escaping the table
    # markup we authored). All user-supplied text fields are manually escaped
    # here BEFORE template render. The template's `white-space: pre-wrap`
    # preserves the tree-glyph layout (├─ └─ ▪) in the rendered output.
    parsed["pulse_summary"] = escape(parsed["pulse_summary"])
    parsed["admiralty"] = escape(parsed["admiralty"])
    for s in parsed["sections"]:
        s["header"] = escape(s["header"])
        s["body"] = escape(s["body"])

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=("j2",), default=False),
        keep_trailing_newline=True,
    )
    template = env.get_template(TEMPLATE_NAME)
    return template.render(subject=subject, **parsed)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("brief_md", type=Path)
    p.add_argument("manifest_json", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--subject", default="AEROWIND // Daily Intelligence")
    args = p.parse_args()
    html = render(args.brief_md, args.manifest_json, subject=args.subject)
    args.out.write_text(html, encoding="utf-8")
    print(f"[render_brief_html] wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_render_brief_html.py -v
```

Expected: all three tests PASS.

Note: the second test checks for `Genoa` in the error message. `_check_site_discipline` uses regex that matches names appearing in `▪ {name} [...]` position, so this test exercises both detection and rejection.

- [ ] **Step 5: Commit**

```
git add tools/render_brief_html.py tests/test_render_brief_html.py
git commit -m "feat(briefs): HTML email renderer for RSM daily

Parses the brief.md (header band, stat strip, █ sections) into a Jinja
context and renders rsm_email.html.j2. Enforces site-name discipline at
render time: rejects briefs mentioning sites outside the manifest registry.

Refs MED RSM PoC plan Task 4."
```

---

## Task 5 — Provider-agnostic formatter prompt contract

**Why:** The model/agent layer must not be tied to Claude Code. The same daily request should work in Claude Code/Pi, Codex, GitHub Copilot IDE, or any capable model workbench. The deterministic code writes a self-contained `formatter_request.md`; the selected agentic environment reads it and writes (or returns) `brief.md`.

**Files:**
- Create: `prompts/rsm_formatter_daily.md`
- Optional convenience only: mirror this prompt into `.claude/agents/rsm-formatter-agent.md` if you want Claude Code subagent ergonomics. Do not make `.claude/` the canonical source of truth.

### Steps

- [ ] **Step 1: Create the canonical provider-neutral prompt**

Create `prompts/rsm_formatter_daily.md`:

```markdown
# RSM Daily Formatter — Provider-Agnostic Prompt Contract

You are formatting a daily MED RSM intelligence brief from a prepared manifest.
This prompt may be run in Claude Code, Codex, GitHub Copilot IDE, or another
model workbench. Do not assume any platform-specific tool exists.

## Inputs supplied by the daily formatter request

The daily `formatter_request.md` will provide:
- REGION
- CADENCE
- BRIEF_PATH
- MANIFEST_PATH

Read `MANIFEST_PATH`. Write the final markdown brief to `BRIEF_PATH`. If your
environment cannot write files directly, return only the complete markdown brief
so the operator can save it to `BRIEF_PATH` manually.

## Required output shape

AEROWIND // MED DAILY // {date}Z
PULSE: {pulse} | ADM: {admiralty or n/a} | NEW: {n} EVT · {n} HOT · 0 CYB

█ SITUATION
{one-sentence narrative — what changed in the last 24h}

█ AEROWIND EXPOSURE
{one block per registered MED site. Sites with no matching events must say
"No new events within radius this period."}

█ PHYSICAL & GEOPOLITICAL — LAST 24H
{severity-labeled event bullets}

█ CYBER — LAST 24H
Cyber not collected in PoC v1 — see footer.

█ EARLY WARNING — NEW
{new hotspots/anomalies, or "No new anomalies."}

█ TODAY'S CALL
{1-2 operational sentences}

## Site and source discipline

- Use only site names from `site_registry` in the manifest.
- Do not invent sites, personnel counts, expat counts, or source counts.
- Do not invent cyber findings. Cyber is explicitly deferred in PoC v1.
- If evidence is absent, say so plainly.
- Prefer concise operational language over strategic commentary.

## Consequence-line standard (anti-generic)

A good Consequence line names: (a) the operational asset affected, (b) the
specific timeframe, (c) the action implication. A bad line restates the event
or says "monitoring continues."

Good:
   └─ Consequence: Inbound blade shipments at Palermo delayed 24-48h; alternate routing not required today.
   └─ Consequence: Site access road blocked during morning shift change; expat commute requires the southern bypass through Friday.

Bad:
   └─ Consequence: Continue monitoring the situation.
   └─ Consequence: This may affect operations at the Palermo facility.

If you cannot say something specific to THIS site in the next 24-48h, write:
`└─ Consequence: No direct site impact assessed in 24h window.`

## TODAY'S CALL standard

Operational, not strategic. Name one concrete thing to do or watch today.
Avoid "continue monitoring" and "situation remains fluid."

Good:
   Track Palermo port reopening window — first ship cleared at 06:00 local. No site action required today.
   Confirm expat headcount at Casablanca by EOD; protest route passes within 800m of compound entrance.

Bad:
   Situation remains fluid; monitor for escalation.
   No significant changes today.

If genuinely nothing actionable: write `Routine posture. No action required today.`

## Reply taxonomy footer context

The rendered email template asks the RSM to reply with one of:
USEFUL · NOISE · MISSED CONTEXT · FALSE POSITIVE.
Do not add a separate footer to the markdown unless the manifest/request asks for it.
```

- [ ] **Step 2: Optional provider wrappers**

If working in Claude Code, you MAY update `.claude/agents/rsm-formatter-agent.md` to reference or mirror `prompts/rsm_formatter_daily.md`. If working in Codex or GitHub Copilot IDE, no wrapper is required: use the `formatter_request.md` generated by `poc_runner.py --collect`.

- [ ] **Step 3: Commit**

```
git add prompts/rsm_formatter_daily.md
# Optional only if you deliberately updated Claude convenience wrapper:
# git add .claude/agents/rsm-formatter-agent.md

git commit -m "feat(poc): provider-agnostic RSM formatter prompt contract

Canonical formatter instructions now live in prompts/rsm_formatter_daily.md
so the daily brief generation step can run through Claude Code, Codex,
GitHub Copilot IDE, or any model workbench that can read the manifest and
write/return brief.md. Claude-specific agent files are convenience wrappers,
not the source of truth.

Refs MED RSM PoC plan Task 5."
```

---

## Task 5a — Regional analyst prompt contract (precedes the formatter)

**Why:** The current single-step formatter does both analysis and formatting in one LLM pass — that's shallow. The user wants real analytical depth: a dedicated regional-analyst step reasons over the strong Seerist signals, writes a structured claims registry + analytical narrative, and the formatter then dresses that for the RSM. Same provider-agnostic pattern as the formatter (`prompts/rsm_regional_analyst_daily.md` + per-day `analyst_request.md` bundle). Operator runs analyst FIRST, then formatter, both via whichever agentic IDE they have available.

**Files:**
- Create: `prompts/rsm_regional_analyst_daily.md` — canonical provider-neutral analyst prompt

### Steps

- [ ] **Step 1: Create the canonical analyst prompt**

Create `prompts/rsm_regional_analyst_daily.md`:

```markdown
# RSM Regional Analyst — Provider-Agnostic Prompt Contract

You are the MED regional analyst for AEROWIND. You reason over today's Seerist signals + the AEROWIND site exposure data and produce TWO outputs the formatter will consume:

1. `claims.json` — a structured registry of claims with signal-id citations (hallucination guard)
2. `analyst_report.md` — analytical narrative (free-form prose for the formatter's context)

This prompt may be run in Claude Code, Codex, GitHub Copilot IDE, or another model workbench. Do not assume any platform-specific tool exists.

## Inputs supplied by the daily analyst request

The daily `analyst_request.md` will provide:
- REGION
- CADENCE
- MANIFEST_PATH (full RSM input manifest — site registry, notable dates, brief headlines)
- SIGNALS_PATH (the day's `seerist_signals.json`)
- POI_PATH (the day's `poi_proximity.json`)
- CLAIMS_PATH (where to write claims.json)
- REPORT_PATH (where to write analyst_report.md)

Read MANIFEST_PATH, SIGNALS_PATH, POI_PATH. Write CLAIMS_PATH and REPORT_PATH. If your environment cannot write files, return both outputs in clearly delimited code blocks so the operator can save them manually.

## Required output 1 — claims.json schema

```json
{
  "region": "MED",
  "generated_at": "2026-05-17T07:05:00Z",
  "admiralty": "B2",
  "primary_scenario": "Short scenario tag — e.g. 'Mediterranean port disruption' or 'Maghreb civil unrest'. One line.",
  "claims": [
    {
      "claim_id": "med-001",
      "claim_type": "fact",
      "pillar": "physical",
      "text": "Concrete one-sentence claim. No hedge language unless claim_type is assessment/estimate.",
      "signal_ids": ["seerist:events_ai:med-001", "seerist:verified:med-002"],
      "confidence": "Confirmed",
      "site_id": "med-pal"
    }
  ],
  "bullets": [
    {"text": "Operational bullet for the formatter's PHYSICAL & GEOPOLITICAL section", "section": "intel"},
    {"text": "Site-specific impact bullet", "section": "impact", "site_id": "med-pal"},
    {"text": "What to watch tomorrow", "section": "watch"}
  ]
}
```

Field rules:
- `claim_type`: `fact` (cited evidence) | `assessment` (analyst judgement based on cited evidence) | `estimate` (no firm citation, acknowledged speculation)
- `pillar`: `physical` | `cyber` | `early_warning` — cyber claims should be EMPTY in PoC v1 (cyber feed deferred)
- `signal_ids`: required for `fact` and `assessment`; may be empty for `estimate`. Every signal_id MUST exist in the day's seerist_signals.json (the formatter validator will check).
- `confidence`: `Confirmed` | `Probable` | `Possible`
- `site_id`: optional. Required if the claim is site-specific. Must match a `site_id` in the manifest's site_registry.
- `bullets[].section`: `intel` | `adversary` | `impact` | `watch` — these feed the formatter's section ordering

## Required output 2 — analyst_report.md shape

Free-form analytical prose, ~200–400 words, with these required headings:

```
# MED Regional Analyst Report — {date}

## Posture
{2–3 sentences: overall MED posture this 24h window. Is anything material changing?}

## Site exposure
{Per-site paragraph for any site with new events inside radius. Each paragraph names the site, the event(s), and your analytical read of the implication. Sites with zero new events get one line: "No new events within radius this period."}

## Early warning
{1–2 sentences on Seerist hotspot anomalies. If none: "No pre-media anomalies detected."}

## Tomorrow's watch
{1–2 sentences: what would you want to know about tomorrow that you don't know today?}
```

## Site and source discipline

- Use only site names from `site_registry` in the manifest. Do not invent AEROWIND facilities.
- Personnel and expat counts come from the manifest. Do not invent or modify.
- Every fact-class claim must cite at least one signal_id from `seerist_signals.json`. The downstream validator will reject claims with phantom signal_ids.
- If evidence is absent for a topic, say so plainly. Empty/quiet days are legitimate and your job is to surface that honestly, not to manufacture analysis.
- Do not invent cyber findings. Cyber is explicitly deferred in PoC v1.
- Geographic names (cities, ports, countries) in narrative prose are FINE — these refer to real-world events the brief describes. Only AEROWIND facility names are tightly constrained.

## Analytical voice

- Senior intelligence analyst briefing a peer (the formatter). Terse, evidenced, no hedging-for-hedging's-sake.
- No corporate prose. No "it is important to note." No "leveraging." No "synergies."
- Distinguish CONFIRMED from ASSESSED. The claim_type field carries this; the prose should reflect it.

## What you do NOT write

- The RSM SITREP brief itself — that's the formatter's job downstream
- Cyber claims or analysis (deferred to v2)
- Cross-regional patterns (single-region PoC)
- Strategic recommendations (operational only)
```

- [ ] **Step 2: Optional Claude convenience wrapper**

If working in Claude Code, you MAY create `.claude/agents/rsm-regional-analyst-agent.md` mirroring `prompts/rsm_regional_analyst_daily.md`. Not required; not load-bearing.

- [ ] **Step 3: Commit**

```
git add prompts/rsm_regional_analyst_daily.md
git commit -m "feat(poc): provider-agnostic regional analyst prompt

Adds the analyst step that precedes the formatter in the daily chain.
Operator runs analyst first (writes claims.json + analyst_report.md),
then formatter (reads analyst output, writes brief.md). Both steps
work in Claude Code, Codex, GitHub Copilot IDE, or any model workbench.

Refs MED RSM PoC plan Task 5a."
```

---

## Task 5b — Update formatter prompt to consume analyst output

**Why:** With the analyst step in front of the formatter, the formatter no longer reads raw signals + manifest — it reads the analyst's `claims.json` + `analyst_report.md` (plus the manifest for site discipline). The formatter becomes a focused "dress this for the RSM" step.

**Files:**
- Modify: `prompts/rsm_formatter_daily.md`

### Steps

- [ ] **Step 1: Update the formatter input contract**

In `prompts/rsm_formatter_daily.md`, replace the "Inputs supplied by the daily formatter request" section with:

```markdown
## Inputs supplied by the daily formatter request

The daily `formatter_request.md` will provide:
- REGION
- CADENCE
- BRIEF_PATH (where to write the final brief.md)
- MANIFEST_PATH (RSM input manifest — site registry, notable dates)
- CLAIMS_PATH (the analyst's claims.json — your authoritative source of factual claims)
- REPORT_PATH (the analyst's analyst_report.md — narrative context for tone/depth)

Read MANIFEST_PATH, CLAIMS_PATH, REPORT_PATH. Write BRIEF_PATH. If your environment cannot write files directly, return only the completed markdown brief so the operator can save it to BRIEF_PATH manually.

You do NOT read seerist_signals.json directly. The analyst already extracted the relevant claims. If a claim isn't in claims.json, do not put it in the brief.
```

- [ ] **Step 2: Add a "Sourcing rule" paragraph**

After the "Site and source discipline" section, add:

```markdown
## Sourcing rule (works from analyst output, not raw signals)

- Every event row in PHYSICAL & GEOPOLITICAL or AEROWIND EXPOSURE must trace to a claim in claims.json. If you find yourself wanting to mention something not in claims.json, do not invent it — that's a hallucination guard violation.
- Use `analyst_report.md` for tone, framing, and the "what does this mean" voice. Use `claims.json` for the structured facts and bullets that fill the brief sections.
- The analyst's `bullets[]` array maps directly to the formatter's section bullets:
  - `bullets[].section == "intel"` → use in PHYSICAL & GEOPOLITICAL or AEROWIND EXPOSURE evidence rows
  - `section == "impact"` → use in Consequence lines (favor site-specific bullets with `site_id`)
  - `section == "watch"` → use in TODAY'S CALL
  - `section == "adversary"` → if present, weave into PHYSICAL & GEOPOLITICAL context
```

- [ ] **Step 3: Commit**

```
git add prompts/rsm_formatter_daily.md
git commit -m "feat(poc): formatter prompt now consumes analyst output, not raw signals

Formatter input contract switched from MANIFEST_PATH alone to
MANIFEST_PATH + CLAIMS_PATH + REPORT_PATH. The formatter no longer
reads seerist_signals.json directly — the analyst step has already
extracted claims with signal_id citations. Formatter becomes a
focused 'dress for RSM' step on already-analyzed data.

Refs MED RSM PoC plan Task 5b."
```

---

## Task 6 — `validate_brief.py` (replaces the absent stop-hook validator)

**Why:** The slice's README confirms `.claude/hooks/` is intentionally not carved in, so the parent repo's `rsm-formatter-stop.py` validator may silently no-op here. We replace it with a local Python script that `poc_runner.py` invokes before render. Non-zero exit blocks HTML generation and therefore blocks the operator from sending a validated PoC email.

**Files:**
- Create: `tools/validate_brief.py`
- Create: `tests/test_validate_brief.py`

### Steps

- [ ] **Step 1: Write the failing test**

Create `tests/test_validate_brief.py`:

```python
"""validate_brief.py — site-name discipline + personnel match + cyber line."""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


CYBER_LINE = "Cyber not collected in PoC v1 — see footer."

GOOD_BRIEF = f"""AEROWIND // MED DAILY // 2026-05-17Z
PULSE: 6.2 | ADM: B2 | NEW: 1 EVT · 0 HOT · 0 CYB

█ SITUATION
Quiet day.

█ AEROWIND EXPOSURE
▪ Palermo [CROWN_JEWEL · 120 personnel, 8 expat]
   └─ No new events within radius this period.

█ PHYSICAL & GEOPOLITICAL — LAST 24H
No new events.

█ CYBER — LAST 24H
{CYBER_LINE}

█ EARLY WARNING — NEW
No new anomalies.

█ TODAY'S CALL
Routine posture. No action required today.
"""


def _write_pair(tmp_path: Path, brief_text: str) -> tuple[Path, Path]:
    brief = tmp_path / "brief.md"
    brief.write_text(brief_text, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "region": "MED",
        "cadence": "daily",
        "site_registry": [
            {"site_id": "med-pal", "name": "Palermo",
             "personnel": 120, "expat_count": 8, "criticality": "crown_jewel"},
            {"site_id": "med-mal", "name": "Malaga",
             "personnel": 85, "expat_count": 4, "criticality": "tier_one"},
            {"site_id": "med-cas", "name": "Casablanca",
             "personnel": 40, "expat_count": 2, "criticality": "tier_two"},
        ],
    }))
    return brief, manifest


def _run_validate(brief: Path, manifest: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "tools/validate_brief.py", str(brief), str(manifest)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_clean_brief_passes(tmp_path):
    brief, manifest = _write_pair(tmp_path, GOOD_BRIEF)
    r = _run_validate(brief, manifest)
    assert r.returncode == 0, r.stderr


def test_out_of_registry_site_rejected(tmp_path):
    bad = GOOD_BRIEF.replace("Palermo", "Genoa")
    brief, manifest = _write_pair(tmp_path, bad)
    r = _run_validate(brief, manifest)
    assert r.returncode != 0
    assert "Genoa" in r.stderr


def test_personnel_mismatch_rejected(tmp_path):
    bad = GOOD_BRIEF.replace("120 personnel, 8 expat", "200 personnel, 8 expat")
    brief, manifest = _write_pair(tmp_path, bad)
    r = _run_validate(brief, manifest)
    assert r.returncode != 0
    assert "personnel" in r.stderr.lower()


def test_missing_cyber_line_rejected(tmp_path):
    bad = GOOD_BRIEF.replace(CYBER_LINE, "No cyber items.")
    brief, manifest = _write_pair(tmp_path, bad)
    r = _run_validate(brief, manifest)
    assert r.returncode != 0
    assert "cyber" in r.stderr.lower()


def test_missing_section_header_rejected(tmp_path):
    bad = GOOD_BRIEF.replace("█ TODAY'S CALL\n", "")
    brief, manifest = _write_pair(tmp_path, bad)
    r = _run_validate(brief, manifest)
    assert r.returncode != 0
    assert "today" in r.stderr.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_validate_brief.py -v
```

Expected: 5 FAIL with "No such file or directory" (the validator doesn't exist).

- [ ] **Step 3: Implement `validate_brief.py`**

Create `tools/validate_brief.py`:

```python
#!/usr/bin/env python3
"""Local pre-send validator for the RSM daily brief.

Replaces the parent repo's .claude/hooks/validators/rsm-formatter-stop.py,
which is intentionally absent from this slice. Run by poc_runner.py before
render — non-zero exit blocks the render output.

Scope of the site-name discipline check:
    STRICT: AeroGrid FACILITY names (the rows formatted as `▪ Name [...]`
            in AEROWIND EXPOSURE) must match the manifest's site_registry
            exactly. An invented facility name is a hallucination and gets
            rejected.
    LENIENT: Geographic, port, city, and country names appearing in
             narrative prose (SITUATION, consequence lines, TODAY'S CALL)
             are allowed — those mirror real-world events the brief is
             describing. For example, "reroute via Genoa not viable" is
             fine even if Genoa isn't an AeroGrid site, because it refers
             to a port, not a facility we operate.

Usage:
    uv run python tools/validate_brief.py BRIEF_MD MANIFEST_JSON
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = [
    "SITUATION",
    "AEROWIND EXPOSURE",
    "PHYSICAL & GEOPOLITICAL",
    "CYBER",
    "EARLY WARNING",
    "TODAY",  # matches "TODAY'S CALL"
]

CYBER_DEFERRED_LINE = "Cyber not collected in PoC v1 — see footer."

_SITE_ROW_RE = re.compile(
    r"^\s*▪\s+(?P<name>[A-Za-z][\w \-]+?)\s*"
    r"\[\s*(?P<crit>[A-Z_]+)\s*·\s*(?P<personnel>\d+)\s*personnel"
    r"(?:,\s*(?P<expat>\d+)\s*expat)?",
    re.M,
)


class ValidationError(Exception):
    pass


def _check_sections(brief: str) -> None:
    for header in REQUIRED_SECTIONS:
        if f"█ {header}" not in brief and header == "TODAY":
            # explicit TODAY'S CALL variant
            if "█ TODAY'S CALL" not in brief:
                raise ValidationError(f"Missing required section: TODAY'S CALL")
        elif f"█ {header}" not in brief:
            raise ValidationError(f"Missing required section: {header}")


def _check_cyber_line(brief: str) -> None:
    # The cyber section must contain the literal deferred line — proves the
    # formatter agent followed the PoC v1 fixed-line instruction.
    if CYBER_DEFERRED_LINE not in brief:
        raise ValidationError(
            f"CYBER section missing the PoC v1 fixed line: {CYBER_DEFERRED_LINE!r}"
        )


def _check_site_discipline(brief: str, manifest: dict) -> None:
    registered = {s["name"]: s for s in manifest.get("site_registry", [])}
    mentioned = list(_SITE_ROW_RE.finditer(brief))

    if not mentioned and manifest.get("site_registry"):
        # No EXPOSURE rows at all — OK (quiet day) but only if explicit "No new
        # events within radius this period." style line is present somewhere in
        # the AEROWIND EXPOSURE section
        if "No new events within radius" not in brief:
            raise ValidationError(
                "AEROWIND EXPOSURE has no site rows and no 'No new events' line. "
                "Brief is ambiguous about whether sites have exposure."
            )
        return

    illegal = []
    mismatches = []
    for m in mentioned:
        name = m.group("name").strip()
        if name not in registered:
            illegal.append(name)
            continue
        site = registered[name]
        personnel = int(m.group("personnel"))
        if personnel != site.get("personnel", -1):
            mismatches.append(
                f"{name}: brief says {personnel} personnel, registry says {site.get('personnel')}"
            )
        expat = m.group("expat")
        if expat is not None:
            expat_int = int(expat)
            if expat_int != site.get("expat_count", -1):
                mismatches.append(
                    f"{name}: brief says {expat_int} expat, registry says {site.get('expat_count')}"
                )

    if illegal:
        raise ValidationError(
            f"Brief mentions site names outside registry: {sorted(set(illegal))}. "
            f"Allowed: {sorted(registered)}"
        )
    if mismatches:
        raise ValidationError("Personnel/expat count mismatches: " + "; ".join(mismatches))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("brief_md", type=Path)
    p.add_argument("manifest_json", type=Path)
    args = p.parse_args()

    brief = args.brief_md.read_text(encoding="utf-8")
    manifest = json.loads(args.manifest_json.read_text(encoding="utf-8"))

    try:
        _check_sections(brief)
        _check_cyber_line(brief)
        _check_site_discipline(brief, manifest)
    except ValidationError as e:
        print(f"[validate_brief] FAIL: {e}", file=sys.stderr)
        return 1

    print(f"[validate_brief] OK: {args.brief_md}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_validate_brief.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```
git add tools/validate_brief.py tests/test_validate_brief.py
git commit -m "feat(validate): local pre-render brief validator

Replaces the parent repo's rsm-formatter-stop.py hook (absent from this
slice). Checks: required section headers, cyber-deferred fixed line,
site-name discipline against manifest registry, personnel/expat count
match. poc_runner.py --render invokes this before render output; non-zero exit
blocks email.html generation.

Refs MED RSM PoC plan Task 6."
```

---

## Task 7 — `poc_runner.py` per-day orchestrator (three phases)

**Why:** Each morning the operator runs the agent chain (analyst → formatter) plus the deterministic surrounding steps. Without an orchestrator that's ~7 commands and several paths to remember in the right order. The runner has THREE phases bracketing TWO operator-in-the-loop LLM steps.

**Files:**
- Create: `tools/poc_runner.py`

```
--collect       deterministic: seerist + POI + manifest + write analyst_request.md
                  ↓
                [operator: run analyst_request.md in IDE → produces claims.json + analyst_report.md]
                  ↓
--prep-format   deterministic: reads claims.json + analyst_report.md → writes formatter_request.md
                  ↓
                [operator: run formatter_request.md in IDE → produces brief.md]
                  ↓
--render        deterministic: validate_brief → render email.html
                  ↓
                [operator: copy email.html into Gmail compose, send]
```

### Steps

- [ ] **Step 1: Implement the orchestrator**

Create `tools/poc_runner.py`:

```python
#!/usr/bin/env python3
"""Per-day MED RSM PoC orchestrator — three deterministic phases bracketing
two operator-in-the-loop LLM steps (analyst + formatter).

Usage:
    # Phase A: collect signals + build analyst_request.md
    uv run python tools/poc_runner.py MED 2026-05-17 --collect

    # [Operator step 1: run analyst_request in IDE → claims.json + analyst_report.md]

    # Phase B: read analyst output + build formatter_request.md
    uv run python tools/poc_runner.py MED 2026-05-17 --prep-format

    # [Operator step 2: run formatter_request in IDE → brief.md]

    # Phase C: validate + render email.html
    uv run python tools/poc_runner.py MED 2026-05-17 --render

All three phases write to output/poc/med/<date>/:
    seerist_signals.json     (--collect)
    poi_proximity.json       (--collect)
    _rsm_manifest_daily.json (--collect)
    analyst_request.md       (--collect — operator runs in IDE)
    claims.json              (between --collect and --prep-format, by operator+model)
    analyst_report.md        (between --collect and --prep-format, by operator+model)
    formatter_request.md     (--prep-format — operator runs in IDE)
    brief.md                 (between --prep-format and --render, by operator+model)
    email.html               (--render — operator copies + sends manually)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = REPO_ROOT / "output"
POC_ROOT = OUTPUT_ROOT / "poc"


def _day_dir(region: str, date_iso: str) -> Path:
    d = POC_ROOT / region.lower() / date_iso
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run(cmd: list[str]) -> None:
    print(f"[poc_runner] $ {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        raise SystemExit(f"[poc_runner] command failed: {' '.join(cmd)} (exit {result.returncode})")


def phase_collect(region: str, date_iso: str, *, window_days: int, require_live: bool) -> None:
    """Phase A: collect, compute POI, build manifest, write formatter request. Stop before model formatting."""
    day = _day_dir(region, date_iso)
    print(f"[poc_runner] PHASE A — collect for {region} / {date_iso} (window={window_days}d)",
          file=sys.stderr)

    # Live-mode guard: seerist_collector silently falls back to mock when
    # SEERIST_API_KEY is absent. For the live PoC week, fail loudly instead.
    if require_live and not os.environ.get("SEERIST_API_KEY"):
        raise SystemExit(
            "[poc_runner] SEERIST_API_KEY is not set, but --require-live was passed. "
            "Refusing to silently fall back to mock fixtures. "
            "Set the key in .env or drop --require-live for a mock-mode rehearsal."
        )

    # 1. Seerist collect (window configurable: --window 1 daily, --window 7 for Day 0 variety)
    _run(["uv", "run", "python", "tools/seerist_collector.py", region, "--window", str(window_days)])
    canonical = OUTPUT_ROOT / "regional" / region.lower() / "seerist_signals.json"
    if not canonical.exists():
        raise SystemExit(f"[poc_runner] expected {canonical} after collect")
    shutil.copy2(canonical, day / "seerist_signals.json")

    # 2. POI proximity (downstream tool)
    _run(["uv", "run", "python", "tools/poi_proximity.py", region])
    poi_canonical = OUTPUT_ROOT / "regional" / region.lower() / "poi_proximity.json"
    if poi_canonical.exists():
        shutil.copy2(poi_canonical, day / "poi_proximity.json")

    # 3. Build the manifest
    from tools.rsm_input_builder import build_rsm_inputs
    manifest = build_rsm_inputs(region, cadence="daily")
    manifest_path = day / "_rsm_manifest_daily.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"[poc_runner] manifest written: {manifest_path}", file=sys.stderr)

    # 4. Build provider-agnostic ANALYST request. This is the FIRST of two
    # operator-in-the-loop LLM steps. Output: claims.json + analyst_report.md.
    analyst_prompt_path = REPO_ROOT / "prompts" / "rsm_regional_analyst_daily.md"
    analyst_prompt = analyst_prompt_path.read_text(encoding="utf-8")
    signals_path = day / "seerist_signals.json"
    poi_path = day / "poi_proximity.json"
    claims_path = day / "claims.json"
    report_path = day / "analyst_report.md"
    analyst_request_path = day / "analyst_request.md"
    analyst_request_path.write_text(
        f"# Analyst request — {region.upper()} {date_iso}\n\n"
        f"REGION: {region.upper()}\n"
        f"CADENCE: daily\n"
        f"MANIFEST_PATH: {manifest_path}\n"
        f"SIGNALS_PATH: {signals_path}\n"
        f"POI_PATH: {poi_path}\n"
        f"CLAIMS_PATH: {claims_path}\n"
        f"REPORT_PATH: {report_path}\n\n"
        "## Operator/model instruction\n\n"
        "Run this request in Claude Code, Codex, GitHub Copilot IDE, or another "
        "model workbench with access to this repository. Read MANIFEST_PATH, "
        "SIGNALS_PATH, POI_PATH. Write CLAIMS_PATH and REPORT_PATH. If the "
        "environment cannot write files directly, return both outputs in clearly "
        "delimited code blocks so the operator can save them manually.\n\n"
        "## Canonical analyst prompt\n\n"
        f"{analyst_prompt}\n",
        encoding="utf-8",
    )
    print(f"[poc_runner] analyst request written: {analyst_request_path}", file=sys.stderr)

    print(
        "\n[poc_runner] PHASE A COMPLETE — READY TO RUN ANALYST REQUEST\n"
        f"  ANALYST_REQUEST: {analyst_request_path}\n"
        f"  CLAIMS_PATH:     {claims_path}\n"
        f"  REPORT_PATH:     {report_path}\n"
        "\n"
        "  Open/paste analyst_request.md in your available agentic environment\n"
        "  (Claude Code, Codex, GitHub Copilot IDE, etc.). When it writes or\n"
        "  returns claims.json + analyst_report.md, save them and run Phase B:\n"
        f"    uv run python tools/poc_runner.py {region} {date_iso} --prep-format\n",
        file=sys.stderr,
    )


def phase_prep_format(region: str, date_iso: str) -> None:
    """Phase B: read analyst output, build formatter_request.md. No model call."""
    day = _day_dir(region, date_iso)
    claims_path = day / "claims.json"
    report_path = day / "analyst_report.md"
    manifest_path = day / "_rsm_manifest_daily.json"

    if not claims_path.exists():
        raise SystemExit(
            f"[poc_runner] {claims_path} not found — did your analyst environment write or return it?"
        )
    if not report_path.exists():
        raise SystemExit(
            f"[poc_runner] {report_path} not found — did your analyst environment write or return it?"
        )
    if not manifest_path.exists():
        raise SystemExit(f"[poc_runner] {manifest_path} not found — run --collect first.")

    # Build formatter request. The formatter prompt has been updated (Task 5b)
    # to read CLAIMS_PATH + REPORT_PATH alongside MANIFEST_PATH; it no longer
    # touches raw seerist_signals.json.
    formatter_prompt_path = REPO_ROOT / "prompts" / "rsm_formatter_daily.md"
    formatter_prompt = formatter_prompt_path.read_text(encoding="utf-8")
    brief_path = day / "brief.md"
    formatter_request_path = day / "formatter_request.md"
    formatter_request_path.write_text(
        f"# Formatter request — {region.upper()} {date_iso}\n\n"
        f"REGION: {region.upper()}\n"
        f"CADENCE: daily\n"
        f"BRIEF_PATH: {brief_path}\n"
        f"MANIFEST_PATH: {manifest_path}\n"
        f"CLAIMS_PATH: {claims_path}\n"
        f"REPORT_PATH: {report_path}\n\n"
        "## Operator/model instruction\n\n"
        "Run this request in Claude Code, Codex, GitHub Copilot IDE, or another "
        "model workbench with access to this repository. Read MANIFEST_PATH, "
        "CLAIMS_PATH, REPORT_PATH. Write the completed markdown brief to "
        "BRIEF_PATH. If the environment cannot write files directly, return only "
        "the completed markdown so the operator can save it to BRIEF_PATH manually.\n\n"
        "## Canonical formatter prompt\n\n"
        f"{formatter_prompt}\n",
        encoding="utf-8",
    )
    print(f"[poc_runner] formatter request written: {formatter_request_path}", file=sys.stderr)

    print(
        "\n[poc_runner] PHASE B COMPLETE — READY TO RUN FORMATTER REQUEST\n"
        f"  FORMATTER_REQUEST: {formatter_request_path}\n"
        f"  BRIEF_PATH:        {brief_path}\n"
        "\n"
        "  Open/paste formatter_request.md in your available agentic environment.\n"
        "  When it writes or returns brief.md, save it to BRIEF_PATH and run Phase C:\n"
        f"    uv run python tools/poc_runner.py {region} {date_iso} --render\n",
        file=sys.stderr,
    )


def phase_render(region: str, date_iso: str) -> None:
    """Phase B: validate the brief, render HTML. No SMTP — operator handles email."""
    day = _day_dir(region, date_iso)
    brief_path = day / "brief.md"
    if not brief_path.exists():
        raise SystemExit(
            f"[poc_runner] {brief_path} not found — did your formatter environment write or return the brief?"
        )
    manifest_path = day / "_rsm_manifest_daily.json"
    if not manifest_path.exists():
        raise SystemExit(f"[poc_runner] {manifest_path} not found — run --collect first.")

    # 1. Validate brief BEFORE render (non-zero exit blocks)
    _run([
        "uv", "run", "python", "tools/validate_brief.py",
        str(brief_path), str(manifest_path),
    ])

    # 2. Render HTML
    html_path = day / "email.html"
    subject = f"AEROWIND // {region} Daily Intelligence — {date_iso}"
    _run([
        "uv", "run", "python", "tools/render_brief_html.py",
        str(brief_path), str(manifest_path),
        "--out", str(html_path),
        "--subject", subject,
    ])

    print(
        f"\n[poc_runner] PHASE B COMPLETE — READY TO SEND\n"
        f"  HTML email body:   {html_path}\n"
        f"  Suggested subject: {subject}\n"
        "\n"
        "  Open the HTML file in your browser, Ctrl+A → Ctrl+C, paste into Gmail\n"
        "  compose, set recipient, hit Send. Then record the send in ../../docs/poc/\n"
        "  med-rsm-week/_qa_log.md.\n",
        file=sys.stderr,
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("region")
    p.add_argument("date_iso", help="YYYY-MM-DD for the brief")
    p.add_argument("--collect", action="store_true",
                   help="Phase A: collect signals + write analyst_request.md")
    p.add_argument("--prep-format", action="store_true", dest="prep_format",
                   help="Phase B: read analyst output + write formatter_request.md")
    p.add_argument("--render", action="store_true",
                   help="Phase C: validate + render email.html (operator sends manually)")
    p.add_argument("--window", type=int, default=1,
                   help="Seerist collection window in days (default 1; use 7 for Day 0 variety)")
    p.add_argument("--require-live", action="store_true",
                   help="Fail if SEERIST_API_KEY is absent (prevents silent mock fallback)")
    args = p.parse_args()

    if not (args.collect or args.prep_format or args.render):
        raise SystemExit("Specify --collect, --prep-format, or --render")

    if args.collect:
        phase_collect(args.region, args.date_iso,
                      window_days=args.window, require_live=args.require_live)
    if args.prep_format:
        phase_prep_format(args.region, args.date_iso)
    if args.render:
        phase_render(args.region, args.date_iso)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke-check (no live API call)**

This is a structural check — it should fail with a clear "formatter environment did not produce brief.md" message rather than crashing on imports.

```
uv run python tools/poc_runner.py MED 2026-05-17 --render
```

Expected: `[poc_runner] .../brief.md not found — did your formatter environment write or return the brief?`

If you get an ImportError or stack trace, fix the runner before committing.

- [ ] **Step 3: Commit**

```
git add tools/poc_runner.py
git commit -m "feat(poc): per-day orchestrator (collect / render phases)

Phase A (--collect): seerist_collect + poi_proximity + manifest, copies
canonical outputs into dated PoC archive, writes formatter_request.md,
then pauses for manual formatter handoff (the model/agent environment is
provider-agnostic and operator-run, not Python-reachable).
--window N flag for collection days (default 1, use 7 for Day 0 variety).
--require-live flag fails fast if SEERIST_API_KEY is absent, preventing
silent fallback to mock fixtures during the live week.

Phase B (--render): validate_brief → render HTML → print path. No SMTP;
operator opens the HTML, copies, pastes into Gmail compose, sends manually.

Writes per-day artifacts under output/poc/<region>/<date>/.

Refs MED RSM PoC plan Task 7."
```

---

## Task 8 — PoC docs scaffolding (qa_log, feedback_log, sponsor_memo)

**Files:**
- Create: `../../docs/poc/med-rsm-week/_qa_log.md` — IMPORTANT: this lives at the repo root `crq-agent-workspace/docs/poc/...`, NOT inside the slice. From the slice working directory (`poc/seerist-rsm/`), that's `../../docs/poc/...`. Create the directory first if it doesn't exist: `mkdir -p ../../docs/poc/med-rsm-week`.
- Create: `../../docs/poc/med-rsm-week/feedback_log.md`
- Create: `../../docs/poc/med-rsm-week/sponsor_memo.md`

### Steps

- [ ] **Step 1: Create `_qa_log.md`** (path is `../../docs/poc/med-rsm-week/_qa_log.md` from the slice)

`../../docs/poc/med-rsm-week/_qa_log.md`:

```markdown
# MED RSM PoC — QA Log

One row per planned day. Use `—` when a column doesn't apply yet.

Since there is no SMTP delivery log, this file is the AUTHORITATIVE record of
what was sent when. After each send, verify the message appears in your Sent
Mail folder and record the sent timestamp in the `Sent UTC` column.

| Date | Artifact | Sent? | Sent UTC | QA time | Corrections made | RSM replied? | Reply class | Sponsor-worthy? | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 2026-05-DD | `poc/seerist-rsm/output/poc/med/2026-05-DD/email.html` | yes/no/skip | 2026-05-DDT07:32Z | 7m | "fixed Palermo personnel count" | yes/no | useful / noise / missed context / false positive | yes/no | free-form |

Notes on columns:
- `Artifact` — path to the rendered `email.html` (the SOURCE artifact). The
  operator-sent email is the DELIVERED artifact and lives in your mail
  client's Sent folder — not on disk.
- `Sent?` — `yes` = pasted and sent, `no` = blocked (validator/QA), `skip` =
  planned skip (e.g. weekend, agreed with RSM).
- `Sent UTC` — verify from your Sent Mail timestamp after sending, not from
  when you ran the runner.
- `Reply class` — the G14 taxonomy. `Sponsor-worthy?` flags rows that should
  be quoted verbatim in the sponsor memo.
```

- [ ] **Step 2: Create `feedback_log.md`** (`../../docs/poc/med-rsm-week/feedback_log.md`)

`../../docs/poc/med-rsm-week/feedback_log.md`:

```markdown
# MED RSM PoC — Feedback Log

One entry per RSM reply, in chronological order. Quote the reply text verbatim; add your G14 classification and interpretation below.

## Day N — YYYY-MM-DD HH:MM

**Reply text:**
> (paste here)

**Class (G14 taxonomy):** USEFUL / NOISE / MISSED CONTEXT / FALSE POSITIVE

**Interpretation:**
- (1–3 bullets — what does this tell us about the value prop / brief quality / cadence)

---
```

- [ ] **Step 3: Create `sponsor_memo.md`** (`../../docs/poc/med-rsm-week/sponsor_memo.md`)

`../../docs/poc/med-rsm-week/sponsor_memo.md`:

```markdown
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
```

- [ ] **Step 4: Commit**

```
git add ../../docs/poc/med-rsm-week/_qa_log.md ../../docs/poc/med-rsm-week/feedback_log.md ../../docs/poc/med-rsm-week/sponsor_memo.md
git commit -m "docs(poc): scaffold QA + feedback + sponsor-memo templates

Templates filled during the live PoC week (qa_log.md, feedback_log.md)
and at Day 8 (sponsor_memo.md).

Refs MED RSM PoC plan Task 8."
```

---

## Task 8a — `CONTEXT.md` rename/swap guide for new companies

**Why:** This slice was carved with AEROWIND-specific mock data (sites, brand, domain). When the project is ported to another IDE/machine for use against a real company, a new agent (or you working with a new agent) needs to know every file to change. Without a pointer doc, the swap requires hunting brand strings with grep and remembering which JSON files hold operational data. A short `CONTEXT.md` at the slice root makes the swap mechanical.

`CONTEXT.md` is a one-time-read pointer doc, not load-bearing for runtime. The pipeline keeps working as-is until the operator runs the rename steps.

**Files:**
- Create: `CONTEXT.md` (at the slice root: `poc/seerist-rsm/CONTEXT.md`)

### Steps

- [ ] **Step 1: Create `CONTEXT.md`**

```markdown
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
| `name` | Display name in briefs | `"Palermo Blade Manufacturing"` |
| `region` | One of APAC, AME, LATAM, MED, NCE | `"MED"` |
| `lat`, `lon` | Decimal degrees | `38.13, 13.34` |
| `poi_radius_km` | Site exposure radius (Seerist POI search) | `50` |
| `criticality` | `crown_jewel` / `tier_one` / `tier_two` | `"crown_jewel"` |
| `personnel` | Total headcount on site | `120` |
| `expat_count` | Non-local employees (duty-of-care) | `8` |
| `notable_dates` | Optional list of `{date, label}` for the next-7-days horizon | `[{"date":"2026-06-15","label":"shareholder visit"}]` |

To swap: replace the `sites` array with the new company's facilities. Same schema. The pipeline picks it up automatically — no code changes needed for site swaps within an existing region. If your company is in a different region than the five we support (APAC/AME/LATAM/MED/NCE), see Section C.

### A.2 Crown jewels + footprint — `data/company_profile.json`

Holds the company name, industry, regional footprint, and a list of crown-jewel assets (the things whose loss would be material). The formatter agent reads this to ground brief language. Swap the fields directly:

\`\`\`json
{
  "company_name": "Your Company Name",
  "industry": "Your industry — affects formatter analogies",
  "global_footprint": ["MED", "NCE"],
  "crown_jewels": ["Asset 1 description", "Asset 2 description"]
}
\`\`\`

### A.3 Mock fixtures — `data/mock_osint_fixtures/*.json`

These are used only in mock-mode runs. They include example events keyed to AEROWIND sites. For live PoC use against a real company, you don't need to regenerate these — live Seerist data replaces them. If you want clean mock runs for the new company, regenerate fixtures with the new site names.

---

## B. Brand strings (find/replace)

Every place "AEROWIND" or "aerowind" appears in PROSE (not data). Use grep first to confirm the list hasn't drifted:

\`\`\`
grep -ril "aerowind" --include="*.md" --include="*.py" --include="*.j2" .
\`\`\`

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
| `docs/poc/med-rsm-week/sponsor_memo.md` | "AEROWIND" mentions in the template |

Also rename these FILENAMES (and update every code reference that opens them — grep first to find them):

| Current filename | New filename suggestion |
|---|---|
| `data/aerowind_sites.json` | `data/<newcompany>_sites.json` OR generic `data/company_sites.json` (preferred — survives future renames) |

If you rename `aerowind_sites.json`, update these readers:
- `tools/seerist_collector.py` (POI block reads `data/aerowind_sites.json`)
- `tools/rsm_input_builder.py` (manifest builder reads it)
- `prompts/rsm_formatter_daily.md` (any reference to the file in input-list prose)
- `.claude/agents/rsm-formatter-agent.md` (only if you're using the optional Claude wrapper)

---

## C. Region swap (if the new company isn't in MED)

This slice is MED-only by carve. If the new company operates in APAC / AME / LATAM / NCE:

1. Put new sites under the right `region` value in your renamed sites JSON.
2. Replace `MED` with the new region in CLI invocations: `poc_runner.py NEWREGION ...`.
3. Regenerate the mock fixtures path: `data/mock_osint_fixtures/<newregion>_*.json`.
4. Verify Seerist client AOI mapping for that region in `tools/seerist_client.py` (LATAM and NCE use the same multi-country `_aoi_param_for_region` pattern as MED; APAC and AME map directly to single Seerist AoIs).

If the new company operates in a region not in our five (APAC/AME/LATAM/MED/NCE), you need to extend `_aoi_param_for_region` and `REGION_COUNTRY_FILTER` in `tools/seerist_client.py`, plus add the region to `REGION_COUNTRIES` for Pulse calls. This is a real code change, not a config swap — be aware.

---

## D. Verification after swap

Run these in order; each should succeed before moving on:

\`\`\`
uv run pytest tests/ -q
uv run python tools/seerist_collector.py NEWREGION --window 7   # mock OK if no SEERIST_API_KEY
uv run python tools/poc_runner.py NEWREGION 2026-MM-DD --collect
\`\`\`

Then inspect `output/regional/<newregion>/seerist_signals.json` — the `poi_alerts[].facility` values should be the new company's site names. If they still say "Palermo" / "Casablanca" / "Málaga", you missed an `aerowind_sites.json` swap.

---

## E. What NOT to change

- `tools/seerist_client.py` — endpoint URLs, AOI mapping, normalization logic. These describe Seerist's API, not your company.
- `tools/poi_proximity.py` — generic geometry.
- `tools/validate_brief.py` — generic validator. The required-section list could be tweaked if your brief shape changes, but defaults are reasonable.
- `tests/` — the assertions key off generic schemas, not brand. Should pass against the new company's data unchanged.
```

Note for the implementing agent: the triple-backtick fences inside the CONTEXT.md content are escaped above (`\`\`\``) so that this plan's task can show CONTEXT.md as a code block. When you write the actual `CONTEXT.md` file, use real triple-backticks (no escaping) for the JSON, bash, and grep examples.

- [ ] **Step 2: Verify the file is at the slice root**

```
ls poc/seerist-rsm/CONTEXT.md
```

Expected: file exists. From inside the slice working dir, that's `ls CONTEXT.md`.

- [ ] **Step 3: Commit**

```
git add CONTEXT.md
git commit -m "docs(context): swap guide for new-company onboarding

CONTEXT.md at slice root tells a future agent (in any IDE) exactly which
files to change when porting the pipeline to a different company:
structured data files (sites, profile), brand strings (templates, prompts),
region swap mechanics, post-swap verification steps. One-time-read pointer
doc, not load-bearing for runtime.

Refs MED RSM PoC plan Task 8a."
```

---

## Task 9 — Day 0 dry-run: end-to-end test send to yourself

**Why:** Before Day 1 (real recipient), prove every link works end-to-end against your own inbox.

**Files:**
- Use existing files only. No commits in this task — this is operator verification.

### Steps

- [ ] **Step 1: Set up `.env` with the Seerist API key**

In `poc/seerist-rsm/.env` (file is gitignored — verify with `git check-ignore -v .env`), add:

```
SEERIST_API_KEY=<the real key>
```

No SMTP credentials needed — the operator handles email manually after rendering.

- [ ] **Step 2: Run Phase A for today's date with `--require-live`**

```
uv run python tools/poc_runner.py MED 2026-05-17 --collect --require-live
```

Expected: live Seerist call completes (no mock fallback because `--require-live`), POI proximity computes, manifest written, `analyst_request.md` generated, runner prints `PHASE A COMPLETE — READY TO RUN ANALYST REQUEST`.

Verify the artifacts:

```
ls output/poc/med/2026-05-17/
```

Expected: `seerist_signals.json`, `poi_proximity.json` (may be absent if poi_proximity tool errored — non-fatal), `_rsm_manifest_daily.json`, `analyst_request.md`.

- [ ] **Step 3: Confirm POI grounding works on this Day 0 run**

```
python -c "
import json
d = json.load(open('output/poc/med/2026-05-17/seerist_signals.json', encoding='utf-8'))
print('events:', len(d['situational']['events']))
print('verified:', len(d['situational']['verified_events']))
print('hotspots:', len(d['analytical']['hotspots']))
for a in d.get('poi_alerts', []):
    print(f'  {a[\"facility\"]}: {len(a[\"matching_events\"])} matching, nearest_km={a.get(\"nearest_event_km\")}')
"
```

Expected: at least one MED site shows `matching_events > 0` (proves POI grouping works end-to-end against live data). If all three sites show 0 matching, widen the collection window for this verification run only:

```
uv run python tools/poc_runner.py MED 2026-05-17 --collect --require-live --window 7
```

Repeat the verification. A 7-day window across a busy Mediterranean basin should reliably produce site-near events.

- [ ] **Step 4: Run the analyst request (LLM step 1 of 2)**

Open the generated request:

```
output/poc/med/2026-05-17/analyst_request.md
```

Run it in whichever agentic environment is available:

- **Claude Code / Pi:** paste or open `analyst_request.md` and ask the agent/subagent to write `CLAIMS_PATH` and `REPORT_PATH`.
- **Codex CLI:** run/review from the slice working directory; give it `analyst_request.md` as the task prompt.
- **GitHub Copilot IDE:** open the slice in VSCode, open `analyst_request.md`, use Copilot Chat or Agent mode to read the request + signals/POI/manifest and create both output files.
- **Other model workbench:** paste the request; if it cannot write files, have it return both outputs in clearly delimited code blocks and save them manually to `CLAIMS_PATH` + `REPORT_PATH`.

Expected outputs:

```
output/poc/med/2026-05-17/claims.json
output/poc/med/2026-05-17/analyst_report.md
```

Skim both before continuing:
- Open `claims.json`. Spot-check that every `fact`-class claim's `signal_ids` actually exist in `seerist_signals.json`. If you see a `signal_id` like `seerist:events_ai:med-XYZ` that's NOT in the day's signals file, the analyst hallucinated — iterate the prompt or edit the file by hand.
- Open `analyst_report.md`. Does it sound like a senior analyst? Is the per-site exposure section honest about quiet sites? Iterate if not.

- [ ] **Step 5: Run `--prep-format` to build the formatter request**

```
uv run python tools/poc_runner.py MED 2026-05-17 --prep-format
```

Expected: runner reads `claims.json` + `analyst_report.md`, writes `output/poc/med/2026-05-17/formatter_request.md`, prints `PHASE B COMPLETE — READY TO RUN FORMATTER REQUEST`.

If the runner errors with "claims.json not found" or "analyst_report.md not found," go back to Step 4 — your analyst environment didn't write the file (or didn't write it to the exact path). Save manually if needed and re-run `--prep-format`.

- [ ] **Step 6: Run the formatter request (LLM step 2 of 2)**

Open `output/poc/med/2026-05-17/formatter_request.md` in your agentic environment (same options as Step 4). The formatter reads claims/report/manifest and writes `BRIEF_PATH`.

Expected output:

```
output/poc/med/2026-05-17/brief.md
```

Read `brief.md`. If anything is off, edit it manually or iterate `prompts/rsm_formatter_daily.md` / the generated request before continuing.

- [ ] **Step 7: Run `--render` and review email.html**

```
uv run python tools/poc_runner.py MED 2026-05-17 --render
```

Expected: validator passes, `email.html` is written to `output/poc/med/2026-05-17/email.html`, runner prints `PHASE B COMPLETE — READY TO SEND` with the file path and suggested subject.

Open `email.html` in your browser. Read it on desktop. Verify:
- All section headers render (SITUATION, AEROWIND EXPOSURE, PHYSICAL & GEOPOLITICAL, CYBER, EARLY WARNING, TODAY'S CALL)
- Per-site EXPOSURE blocks look right
- The cyber-deferred line is in the right place
- Footer with G14 reply taxonomy is present
- Typography is readable, no visual glitches

If anything looks wrong: iterate `rsm_email.html.j2` or `render_brief_html.py`, re-run `--render`, repeat.

- [ ] **Step 8: Copy-paste test send to yourself — and verify three render surfaces**

In the browser viewing `email.html`: Ctrl+A → Ctrl+C. Switch to Gmail (or your normal mail client). Compose a new message. Paste. Set:
- To: your own email address
- Subject: the suggested subject from the runner output

Before clicking Send, **inspect the compose window** — this is where Gmail often quietly strips inline CSS during paste. The three render surfaces to verify:

1. **`email.html` in browser** — the SOURCE render. Should be perfect.
2. **Gmail compose window after paste** — the PRE-SEND render. Gmail's WYSIWYG editor can drop some inline styles (background colors, border-radius, padding can degrade).
3. **Received email in your own inbox**, on desktop AND mobile — the DELIVERED render. Sometimes survives compose intact, sometimes degrades again.

For each surface, check: tree glyphs (`├─ └─ ▪`) intact, severity coloring intact, monospace header band intact, single-column layout intact.

If 2 or 3 mangle the formatting: iterate `rsm_email.html.j2` toward more conservative HTML (e.g. `<table>` layouts and explicit `<br>` instead of pre-wrap; Gmail prefers tables to flexbox). Re-render, re-paste, re-send to yourself, re-check. Iterate until ALL THREE surfaces look right.

Note: the operator-sent email is the actual deliverable. `email.html` looking perfect doesn't help if Gmail breaks it during paste.

- [ ] **Step 9: Document the dry-run result in `_qa_log.md`**

Add a row to `../../docs/poc/med-rsm-week/_qa_log.md` describing the Day 0 dry-run outcome — what worked, what needed iteration, whether you're ready to ship Day 1.

No commit needed in this task — these are all rehearsal artifacts.

---

## Days 1–7 runbook (operational, no engineering)

For each morning of the live PoC. The engineering plan above produced everything you need; this is the routine.

**Time slot:** operator-chosen, kept consistent across the week. Suggested: `07:30 Europe/Rome` so the RSM sees it as part of his morning routine.

### Daily routine (T = send slot)

| Clock | Action |
|---|---|
| T−45 | `uv run python tools/poc_runner.py MED <today> --collect --require-live` |
| T−40 | Open today's `analyst_request.md` in your available agentic environment (Claude Code, Codex, GitHub Copilot IDE, etc.). The agent reads signals/POI/manifest and writes `claims.json` + `analyst_report.md`. Skim both: any out-of-registry sites? any phantom signal_ids? if so, iterate. |
| T−25 | `uv run python tools/poc_runner.py MED <today> --prep-format` |
| T−20 | Open today's `formatter_request.md` in your IDE. The agent reads claims/report/manifest and writes `brief.md`. |
| T−15 | `uv run python tools/poc_runner.py MED <today> --render`, open `email.html` in browser, **5–10 min QA read** |
| T−5  | If QA passes: Ctrl+A → Ctrl+C, paste into Gmail/Outlook compose, **inspect the compose window** (Gmail can drop some inline CSS during paste), set recipient + subject, hit Send |
| T+1  | Verify the message in your Sent folder; record Sent UTC timestamp + artifact path in `_qa_log.md` |
| T+anytime | When RSM replies: copy verbatim into `feedback_log.md`, classify per G14 |

**Operator-attention time:** roughly 20–30 min wall-clock per morning. Two LLM steps (analyst ~5–10 min including review, formatter ~5–10 min) + render QA (5–10 min) + paste/send (~2 min). The deterministic phases (`--collect`, `--prep-format`, `--render`) each take well under 60 seconds.

**Source vs delivered artifact:** `email.html` is the rendered SOURCE artifact (lives on disk in the per-day archive). The DELIVERED artifact is the email in the RSM's inbox (lives in your Sent folder + his inbox). The two can differ if Gmail compose strips inline CSS during paste — that's why QA happens twice: once on `email.html` in the browser, again on the compose window before Send.

### Day 4 mid-week nudge (only if RSM is silent)

If by morning of Day 4 the RSM has not replied to any email: send a single short follow-up:

> Still useful? Three days in — any quick reaction (yes / no / change X) helps me know what to fix for the rest of the week.

Don't escalate further. Silence by Day 5 is itself a finding and goes in the sponsor memo.

### Weekend cadence

Default: skip Saturday and Sunday (most RSMs aren't reading work email then). Document the decision in `_qa_log.md`. PoC ships 5 emails, Mon–Fri.

If the RSM explicitly says he reads weekend mail, run all 7 days.

---

## Day 8 — Sponsor memo + decision

- [ ] **Step 1: Fill in `sponsor_memo.md`**

Open `../../docs/poc/med-rsm-week/sponsor_memo.md` (from slice working directory). Fill every section. Roll up `feedback_log.md` into the "What the RSM said" section — quote one or two replies verbatim, then summarise.

- [ ] **Step 2: Make a clear recommendation**

GREENLIGHT / PIVOT / KILL with one sentence why. Don't hedge.

- [ ] **Step 3: Send the memo to the sponsor**

Out of scope for this plan — your call on channel.

- [ ] **Step 4: Final commit**

```
git add ../../docs/poc/med-rsm-week/sponsor_memo.md ../../docs/poc/med-rsm-week/feedback_log.md ../../docs/poc/med-rsm-week/_qa_log.md
git commit -m "docs(poc): MED RSM PoC sponsor memo + week artifacts

Refs MED RSM PoC plan Day 8."
```

---

## Acceptance criteria (PoC done = all true)

**Engineering gates (Day 0):**

1. `uv run pytest tests/ -q` is green (Tasks 1, 2, 4, 6 each add tests).
2. Day 0 representative collect (window=7d for variety) produces `seerist_signals.json` with `poi_alerts[].matching_events` non-empty for at least one MED site — proves POI grouping works. This is a **one-time gate**, not a daily one: real quiet days legitimately have zero site-near events.
3. Day 0 end-to-end dry-run completes: copy-paste into Gmail compose, send to yourself, HTML reads correctly in Gmail web + mobile.

**Operational gates (live PoC):**

4. Cadence delivered: default 5 business days (Mon–Fri); optional Sat/Sun only if the RSM said he reads weekend mail. Minimum acceptable: 4 of 5–7 operator-sent emails. Each missed day has an explanatory row in `_qa_log.md`.
5. Every operator-sent email was preceded by `validate_brief.py` exit-code 0. Zero send-time validation bypasses.
6. Operator records each day's send in `_qa_log.md` (date, sent? = yes/no/skip, QA time, corrections made, RSM reply class if any). Send is operator-observable, not pipeline-observable; `_qa_log.md` is the authoritative record.
7. Each email's HTML rendered correctly in Gmail web + mobile (manual confirmation per day in `_qa_log.md`).
8. `feedback_log.md` contains every RSM reply, classified per G14 taxonomy (USEFUL / NOISE / MISSED CONTEXT / FALSE POSITIVE).

**Sponsor decision gate:**

9. `sponsor_memo.md` is filled and contains a recommendation (Greenlight / Pivot / Kill) with one-sentence rationale.
10. You can answer "yes" without hedging to: *would I be embarrassed if my sponsor opened any one of these emails at random?*

---

## Out-of-band caveats

- **Live API quota.** Each PoC morning hits ~6 Seerist endpoints × 1 region ≈ 6 calls + per-country Pulse (3 calls). 9 calls/day × 7 days = 63 calls/week. Should be well inside any reasonable quota.
- **Windows TLS.** httpx uses certifi, not Windows schannel. If httpx ever returns `CERTIFICATE_VERIFY_FAILED`, that's a separate problem — diagnose, don't bypass.
- **Don't commit `.env`.** Verify with `git check-ignore .env` before each commit.
- **Site name discipline.** The required gate is `tools/validate_brief.py` (Task 6), invoked by `poc_runner.py --render`. The parent repo's stop hook is optional and may not run from inside the slice. If `validate_brief.py` rejects a brief, fix the formatter prompt — do not bypass.
- **Real RSM care.** If a brief contains a real factual error: acknowledge the reply same-day, fix in tomorrow's brief, note in `feedback_log.md`. Trust matters more than the streak.
