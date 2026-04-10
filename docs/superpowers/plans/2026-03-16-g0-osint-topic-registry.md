# Phase G-0: Shared OSINT Topic Registry Implementation Plan


**Goal:** Create a shared `data/osint_topics.json` registry and retrofit both OSINT collectors to run one focused search per active topic per region, producing a `matched_topics` field in their output for analyst traceability.

**Architecture:** A single JSON file defines what the platform watches — topics with keywords, region scope, and active flag. Both `geo_collector.py` and `cyber_collector.py` load this file at runtime, filter to active topics for the current region, and run one extra search per topic. Results merge into the existing article pool (deduplicated by title). A `matched_topics` list of topic IDs is written into each signal output file. The `regional-analyst-agent` reads matched topic IDs to link clusters to the registry.

**Tech Stack:** Python 3.12, `uv` package manager, `pytest` for tests. No new dependencies.

---

## Chunk 1: Topic Registry + Schema Tests

### Task 1: Create `data/osint_topics.json`

**Files:**
- Create: `data/osint_topics.json`

- [ ] **Step 1: Write `data/osint_topics.json`**

Write the file with exactly this content:

```json
[
  {
    "id": "ot-ics-cyber-attacks",
    "label": "OT/ICS Cyber Attacks on Energy Sector",
    "type": "trend",
    "keywords": ["OT security", "ICS attack", "SCADA", "operational technology", "industrial control"],
    "regions": ["AME", "NCE", "APAC"],
    "active": true
  },
  {
    "id": "ransomware-energy-grid",
    "label": "Ransomware Targeting Energy Grid Operators",
    "type": "event",
    "keywords": ["ransomware", "energy grid", "wind farm", "power operator", "double extortion"],
    "regions": ["AME", "NCE"],
    "active": true
  },
  {
    "id": "state-actor-wind-ip-theft",
    "label": "State-Sponsored IP Theft Targeting Wind Technology",
    "type": "trend",
    "keywords": ["state-sponsored", "IP theft", "wind turbine design", "espionage", "technology transfer"],
    "regions": ["APAC", "NCE"],
    "active": true
  },
  {
    "id": "supply-chain-wind-components",
    "label": "Supply Chain Disruption — Wind Component Sourcing",
    "type": "trend",
    "keywords": ["wind turbine supply chain", "rare earth metals", "component shortage", "manufacturing disruption"],
    "regions": ["AME", "LATAM", "MED"],
    "active": true
  },
  {
    "id": "eu-critical-infrastructure-directive",
    "label": "EU Critical Infrastructure Security Directive",
    "type": "trend",
    "keywords": ["EU CER directive", "critical infrastructure", "energy security regulation", "NIS2"],
    "regions": ["NCE", "MED"],
    "active": true
  },
  {
    "id": "iran-strait-energy-routes",
    "label": "Iran–Strait of Hormuz Energy Route Pressure",
    "type": "event",
    "keywords": ["Iran", "Strait of Hormuz", "energy shipping", "Middle East escalation", "Gulf tension"],
    "regions": ["MED", "APAC"],
    "active": true
  }
]
```

- [ ] **Step 2: Verify the file parses cleanly**

```bash
uv run python -c "import json; d=json.load(open('data/osint_topics.json')); print(f'{len(d)} topics loaded')"
```
Expected output: `6 topics loaded`

---

### Task 2: Write schema validation tests

**Files:**
- Create: `tests/test_osint_topics.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_osint_topics.py` with exactly this content:

```python
"""Tests for Phase G-0 — Shared OSINT Topic Registry.

Covers:
- data/osint_topics.json schema validation
- matched_topics field in geo_signals.json and cyber_signals.json (added in Task 5)
"""
import json
import os
import subprocess
import sys

PYTHON = sys.executable
CWD = "c:/Users/frede/crq-agent-workspace"
TOPICS_PATH = os.path.join(CWD, "data/osint_topics.json")

REQUIRED_KEYS = {"id", "label", "type", "keywords", "regions", "active"}
VALID_TYPES = {"event", "trend"}
VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}


# ── Topic registry schema ────────────────────────────────────────────────────

def test_topics_file_exists():
    assert os.path.exists(TOPICS_PATH), f"data/osint_topics.json not found at {TOPICS_PATH}"


def test_topics_is_valid_json():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list), "Expected a JSON array of topics"


def test_topics_required_keys():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = json.load(f)
    for t in topics:
        missing = REQUIRED_KEYS - t.keys()
        assert not missing, f"Topic '{t.get('id', '?')}' missing keys: {missing}"


def test_topics_valid_types():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = json.load(f)
    for t in topics:
        assert t["type"] in VALID_TYPES, \
            f"Topic '{t['id']}' has invalid type '{t['type']}' — must be 'event' or 'trend'"


def test_topics_keywords_are_nonempty_lists():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = json.load(f)
    for t in topics:
        assert isinstance(t["keywords"], list) and len(t["keywords"]) >= 1, \
            f"Topic '{t['id']}' keywords must be a non-empty list"


def test_topics_regions_valid_values():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = json.load(f)
    for t in topics:
        assert isinstance(t["regions"], list) and len(t["regions"]) >= 1, \
            f"Topic '{t['id']}' regions must be a non-empty list"
        for r in t["regions"]:
            assert r in VALID_REGIONS, \
                f"Topic '{t['id']}' has invalid region '{r}'"


def test_topics_ids_unique():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = json.load(f)
    ids = [t["id"] for t in topics]
    duplicates = {x for x in ids if ids.count(x) > 1}
    assert not duplicates, f"Duplicate topic IDs found: {duplicates}"


def test_at_least_one_active_topic():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = json.load(f)
    active = [t for t in topics if t.get("active")]
    assert len(active) >= 1, "At least one topic must be active"


def test_active_field_is_boolean():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = json.load(f)
    for t in topics:
        assert isinstance(t["active"], bool), \
            f"Topic '{t['id']}' active field must be a boolean, got {type(t['active'])}"


# ── Collector matched_topics integration tests ───────────────────────────────

def _run(tool, args):
    return subprocess.run(
        [PYTHON, f"tools/{tool}"] + args,
        capture_output=True, text=True, encoding="utf-8", cwd=CWD,
    )


def test_geo_collector_outputs_matched_topics_for_ame():
    """geo_collector AME must write matched_topics list — AME has 3 active topics."""
    result = _run("geo_collector.py", ["AME", "--mock"])
    assert result.returncode == 0, f"geo_collector AME failed: {result.stderr}"
    out_path = os.path.join(CWD, "output/regional/ame/geo_signals.json")
    with open(out_path, encoding="utf-8") as f:
        data = json.load(f)
    assert "matched_topics" in data, "geo_signals.json missing 'matched_topics'"
    assert isinstance(data["matched_topics"], list)
    assert len(data["matched_topics"]) > 0, "AME should have at least one matched topic"


def test_geo_collector_matched_topics_are_valid_ids():
    """All matched_topics entries must be valid IDs from the registry."""
    _run("geo_collector.py", ["AME", "--mock"])
    with open(TOPICS_PATH, encoding="utf-8") as f:
        known_ids = {t["id"] for t in json.load(f)}
    out_path = os.path.join(CWD, "output/regional/ame/geo_signals.json")
    with open(out_path, encoding="utf-8") as f:
        data = json.load(f)
    for tid in data["matched_topics"]:
        assert tid in known_ids, f"matched_topics contains unrecognised ID '{tid}'"


def test_cyber_collector_outputs_matched_topics_for_ame():
    """cyber_collector AME must write matched_topics list."""
    result = _run("cyber_collector.py", ["AME", "--mock"])
    assert result.returncode == 0, f"cyber_collector AME failed: {result.stderr}"
    out_path = os.path.join(CWD, "output/regional/ame/cyber_signals.json")
    with open(out_path, encoding="utf-8") as f:
        data = json.load(f)
    assert "matched_topics" in data, "cyber_signals.json missing 'matched_topics'"
    assert isinstance(data["matched_topics"], list)


def test_geo_collector_latam_matched_topics():
    """LATAM has supply-chain-wind-components in scope — matched_topics must include it."""
    result = _run("geo_collector.py", ["LATAM", "--mock"])
    assert result.returncode == 0, f"geo_collector LATAM failed: {result.stderr}"
    out_path = os.path.join(CWD, "output/regional/latam/geo_signals.json")
    with open(out_path, encoding="utf-8") as f:
        data = json.load(f)
    assert "matched_topics" in data
    assert "supply-chain-wind-components" in data["matched_topics"]


def test_geo_collector_all_regions_produce_matched_topics():
    """All 5 regions must produce a matched_topics list (may be empty for regions with no topics)."""
    for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        result = _run("geo_collector.py", [region, "--mock"])
        assert result.returncode == 0, f"geo_collector {region} failed: {result.stderr}"
        out_path = os.path.join(CWD, f"output/regional/{region.lower()}/geo_signals.json")
        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
        assert "matched_topics" in data, f"{region} geo_signals.json missing 'matched_topics'"
        assert isinstance(data["matched_topics"], list), f"{region} matched_topics must be a list"


def test_missing_topics_file_does_not_crash_collector(tmp_path):
    """If osint_topics.json is missing, collector must still succeed with empty matched_topics."""
    topics_path = os.path.join(CWD, "data/osint_topics.json")
    backup_path = os.path.join(CWD, "data/osint_topics.json.bak")
    os.rename(topics_path, backup_path)
    try:
        result = _run("geo_collector.py", ["AME", "--mock"])
        assert result.returncode == 0, f"geo_collector crashed without topics file: {result.stderr}"
        out_path = os.path.join(CWD, "output/regional/ame/geo_signals.json")
        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("matched_topics") == [], \
            f"Expected empty matched_topics when file missing, got {data.get('matched_topics')}"
    finally:
        os.rename(backup_path, topics_path)
```

- [ ] **Step 2: Run schema tests only (collector tests will fail until Task 3-4 done)**

```bash
uv run pytest tests/test_osint_topics.py::test_topics_file_exists tests/test_osint_topics.py::test_topics_is_valid_json tests/test_osint_topics.py::test_topics_required_keys tests/test_osint_topics.py::test_topics_valid_types tests/test_osint_topics.py::test_topics_keywords_are_nonempty_lists tests/test_osint_topics.py::test_topics_regions_valid_values tests/test_osint_topics.py::test_topics_ids_unique tests/test_osint_topics.py::test_at_least_one_active_topic tests/test_osint_topics.py::test_active_field_is_boolean -v
```

Expected: 9 tests PASS

- [ ] **Step 3: Commit**

```bash
git add data/osint_topics.json tests/test_osint_topics.py
git commit -m "feat: add osint_topics.json registry with 6 tracked topics + schema tests"
```

---

## Chunk 2: Collector Retrofits + Integration Tests

### Task 3: Retrofit `tools/geo_collector.py`

**Files:**
- Modify: `tools/geo_collector.py`

The retrofit adds two things to `geo_collector.py`:
1. A `_load_topics_for_region(region)` helper that reads `data/osint_topics.json` and returns active topics scoped to the given region.
2. In `collect()`, after the two baseline searches, loop over matched topics and run one `run_search()` per topic. Merge results into the deduplication pool. Add `matched_topics` (list of topic IDs searched) to the output dict.

- [ ] **Step 1: Add `from pathlib import Path` import**

In `tools/geo_collector.py`, after `from dotenv import load_dotenv`, add:

```python
from pathlib import Path
```

- [ ] **Step 2: Add `_load_topics_for_region()` helper**

After the `REGULATORY_KEYWORDS` list and before `def run_search(`, insert:

```python
def _load_topics_for_region(region: str) -> list:
    """Return active topics from data/osint_topics.json scoped to this region."""
    path = Path("data/osint_topics.json")
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            all_topics = json.load(f)
        return [t for t in all_topics if t.get("active") and region in t.get("regions", [])]
    except (json.JSONDecodeError, KeyError):
        return []
```

- [ ] **Step 3: Replace `collect()` body**

Replace the existing `collect()` function with:

```python
def collect(region, mock, window=None):
    articles1 = run_search(region, f"{region} geopolitical risk wind energy", mock, window)
    articles2 = run_search(region, f"{region} trade tensions manufacturing", mock, window)

    # Topic-focused pass: one search per active topic scoped to this region.
    # Baseline catches unexpected events; topic queries deepen focus on known ones.
    topics = _load_topics_for_region(region)
    topic_articles = []
    for topic in topics:
        query = " ".join(topic["keywords"][:4])  # max 4 keywords per query
        results = run_search(region, query, mock, window)
        topic_articles.extend(results)

    # Deduplicate across baseline + topic results by title
    seen = set()
    articles = []
    for a in articles1 + articles2 + topic_articles:
        key = a.get("title", "")
        if key not in seen:
            seen.add(key)
            articles.append(a)

    base = normalize(articles)
    # Record which topic IDs were searched for traceability
    base["matched_topics"] = [t["id"] for t in topics]

    # Seerist enrichment (only when SEERIST_API_KEY is set)
    if not mock and os.environ.get("SEERIST_API_KEY"):
        try:
            from tools.seerist_client import get_full_intelligence
            seerist_data = get_full_intelligence(region)
            seerist_payload = {k: v for k, v in seerist_data.items() if v is not None}
            if seerist_payload:
                base["seerist"] = seerist_payload
                events = seerist_data.get("events") or []
                if events:
                    seerist_indicators = [
                        f"[{e.get('category', 'Event')}] {e.get('title', '')}"
                        for e in events[:3] if e.get("title")
                    ]
                    base["lead_indicators"] = seerist_indicators + base["lead_indicators"]
                if seerist_data.get("scribe"):
                    base["seerist_assessment"] = seerist_data["scribe"]
                if seerist_data.get("hotspots"):
                    base["anomaly_detected"] = True
        except Exception as e:
            print(f"[geo_collector] Seerist enrichment failed: {e}", file=sys.stderr)

    return base
```

- [ ] **Step 4: Smoke test geo_collector**

```bash
uv run python tools/geo_collector.py AME --mock
```

Expected: exits 0, `output/regional/ame/geo_signals.json` written

- [ ] **Step 5: Verify matched_topics present**

```bash
uv run python -c "
import json
d = json.load(open('output/regional/ame/geo_signals.json'))
print('matched_topics:', d.get('matched_topics'))
assert isinstance(d.get('matched_topics'), list), 'missing matched_topics'
print('OK')
"
```

Expected: `matched_topics: ['ot-ics-cyber-attacks', 'ransomware-energy-grid', 'supply-chain-wind-components']`

---

### Task 4: Retrofit `tools/cyber_collector.py`

**Files:**
- Modify: `tools/cyber_collector.py`

Same two-part retrofit as geo_collector. The Seerist block differs — preserve it exactly.

- [ ] **Step 1: Add `from pathlib import Path` import**

In `tools/cyber_collector.py`, after `from dotenv import load_dotenv`, add:

```python
from pathlib import Path
```

- [ ] **Step 2: Add `_load_topics_for_region()` helper**

After the `ASSET_KEYWORDS` dict and before `def run_search(`, insert:

```python
def _load_topics_for_region(region: str) -> list:
    """Return active topics from data/osint_topics.json scoped to this region."""
    path = Path("data/osint_topics.json")
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            all_topics = json.load(f)
        return [t for t in all_topics if t.get("active") and region in t.get("regions", [])]
    except (json.JSONDecodeError, KeyError):
        return []
```

- [ ] **Step 3: Replace `collect()` body**

```python
def collect(region, mock, window=None):
    articles1 = run_search(region, f"{region} cyber threat industrial control systems", mock, window)
    articles2 = run_search(region, f"{region} OT security wind energy", mock, window)

    # Topic-focused pass: one search per active topic scoped to this region
    topics = _load_topics_for_region(region)
    topic_articles = []
    for topic in topics:
        query = " ".join(topic["keywords"][:4])
        results = run_search(region, query, mock, window)
        topic_articles.extend(results)

    # Deduplicate across baseline + topic results by title
    seen = set()
    articles = []
    for a in articles1 + articles2 + topic_articles:
        key = a.get("title", "")
        if key not in seen:
            seen.add(key)
            articles.append(a)

    base = normalize(articles)
    base["matched_topics"] = [t["id"] for t in topics]

    # Seerist +Cyber enrichment (requires SEERIST_API_KEY + SEERIST_CYBER_ADDON=true)
    if not mock and os.environ.get("SEERIST_API_KEY") and os.environ.get("SEERIST_CYBER_ADDON", "").lower() == "true":
        try:
            from tools.seerist_client import get_cyber_risk
            cyber_data = get_cyber_risk(region)
            if cyber_data:
                base["seerist_cyber"] = cyber_data
        except Exception as e:
            print(f"[cyber_collector] Seerist +Cyber enrichment failed: {e}", file=sys.stderr)

    return base
```

- [ ] **Step 4: Smoke test cyber_collector**

```bash
uv run python tools/cyber_collector.py AME --mock
```

Expected: exits 0, `output/regional/ame/cyber_signals.json` written

- [ ] **Step 5: Verify matched_topics present**

```bash
uv run python -c "
import json
d = json.load(open('output/regional/ame/cyber_signals.json'))
assert isinstance(d.get('matched_topics'), list)
print('matched_topics:', d['matched_topics'])
print('OK')
"
```

---

### Task 5: Run all collector integration tests

**Files:**
- No new files — tests were written in Task 2

- [ ] **Step 1: Run full test_osint_topics.py**

```bash
uv run pytest tests/test_osint_topics.py -v
```

Expected: 15 tests PASS (9 schema + 6 collector integration)

- [ ] **Step 2: Run existing window param tests to confirm no regression**

```bash
uv run pytest tests/test_window_param.py -v
```

Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add tools/geo_collector.py tools/cyber_collector.py
git commit -m "feat: retrofit collectors with topic-focused pass + matched_topics output"
```

---

## Chunk 3: Mock Fixture Updates + Agent Prompt

### Task 6: Update 5 mock fixtures with topic-representative articles

**Files:**
- Modify: `data/mock_osint_fixtures/ame_geo.json`
- Modify: `data/mock_osint_fixtures/latam_geo.json`
- Modify: `data/mock_osint_fixtures/nce_geo.json`
- Modify: `data/mock_osint_fixtures/nce_cyber.json`
- Modify: `data/mock_osint_fixtures/med_geo.json`

Adds 1 article to each fixture to ensure topic-relevant keyword coverage. Other 5 fixtures (ame_cyber, apac_geo, apac_cyber, latam_cyber, med_cyber) already have sufficient coverage.

- [ ] **Step 1: Update `data/mock_osint_fixtures/ame_geo.json`** — add ICS/SCADA article

Full file content:

```json
[
  {"title": "US executive order expands critical infrastructure designation to offshore wind", "summary": "A new executive order designates offshore wind farm operations as critical national infrastructure, triggering mandatory cybersecurity reporting requirements for operators and their technology supply chains.", "source": "Wall Street Journal", "date": "2026-03-10"},
  {"title": "Canada-US energy policy divergence creates regulatory compliance burden", "summary": "Diverging renewable energy regulations between Canada and the United States are creating compliance complexity for cross-border wind energy operators, with conflicting cybersecurity incident disclosure timelines.", "source": "Globe and Mail", "date": "2026-03-09"},
  {"title": "Congressional hearing highlights ransomware threat to US energy grid operators", "summary": "Testimony before the Senate Energy Committee identified ransomware as the primary near-term cyber threat to US energy infrastructure, with wind farm operations specifically cited as underprotected.", "source": "Politico", "date": "2026-03-08"},
  {"title": "CISA issues warning on critical infrastructure targeting by foreign actors", "summary": "CISA has issued an advisory warning that foreign state-sponsored actors are actively reconnaissance energy sector targets across North America, with a focus on operational disruption rather than data theft.", "source": "CISA", "date": "2026-03-07"},
  {"title": "IRA incentive structures accelerate wind capacity growth, expanding attack surface", "summary": "Rapid expansion of US wind energy capacity under IRA incentives is outpacing security investment, creating a growing attack surface of newly deployed turbine control networks with inconsistent security baselines.", "source": "Bloomberg Green", "date": "2026-03-06"},
  {"title": "ICS/SCADA targeting of US wind energy grid infrastructure identified", "summary": "CISA and sector ISACs have identified active ICS/SCADA scanning activity targeting US wind energy grid management systems. Operational technology networks at turbine farms are the primary focus, consistent with a sustained campaign against energy sector control infrastructure.", "source": "CISA ICS-CERT", "date": "2026-03-11"}
]
```

- [ ] **Step 2: Update `data/mock_osint_fixtures/latam_geo.json`** — add supply chain article

Full file content:

```json
[
  {"title": "Brazil wind energy sector shows stable political and regulatory environment", "summary": "Brazil's renewable energy regulatory framework remains stable following recent elections, with continued government support for wind energy expansion and no material geopolitical disruption to manufacturing operations.", "source": "Reuters Brazil", "date": "2026-03-10"},
  {"title": "LATAM regional trade agreements benefit wind energy component supply chains", "summary": "Recently ratified trade agreements across Latin America are reducing tariff barriers for wind energy components, improving supply chain economics without introducing material geopolitical risk.", "source": "Latin Finance", "date": "2026-03-08"},
  {"title": "Chile and Argentina renewable energy cooperation agreement signed", "summary": "Chile and Argentina have signed a bilateral renewable energy cooperation agreement, creating a stable regulatory environment for cross-border wind energy projects in Patagonia.", "source": "BN Americas", "date": "2026-03-06"},
  {"title": "LATAM political stability index remains high for energy sector operators", "summary": "Regional political stability indices for LATAM energy sector operations remain at multi-year highs, with no active geopolitical events materially affecting wind energy manufacturing or service operations.", "source": "Control Risks", "date": "2026-03-05"},
  {"title": "Wind turbine supply chain resilience improving in Latin America despite rare earth pressures", "summary": "Latin American wind turbine manufacturers are diversifying rare earth metal sourcing to reduce manufacturing disruption risk from Chinese export controls. Component shortage risk remains present but manageable for near-term delivery schedules.", "source": "BloombergNEF", "date": "2026-03-11"}
]
```

- [ ] **Step 3: Update `data/mock_osint_fixtures/nce_geo.json`** — add EU CER/NIS2 article

Full file content:

```json
[
  {"title": "Northern Europe wind energy sector operates in stable geopolitical environment", "summary": "NATO alignment and strong bilateral energy cooperation agreements across Northern and Central Europe provide a stable geopolitical environment for wind energy operators, with no active state-level threats identified.", "source": "Handelsblatt", "date": "2026-03-10"},
  {"title": "EU energy independence strategy reinforces NCE wind energy investment", "summary": "The EU's strategic energy independence agenda continues to reinforce investment in Northern and Central European wind energy, with strong regulatory frameworks providing operational stability.", "source": "Euractiv", "date": "2026-03-08"},
  {"title": "Germany's offshore wind expansion proceeds without geopolitical disruption", "summary": "Germany's offshore wind expansion program is proceeding on schedule with no material geopolitical disruptions. Baltic Sea maritime agreements with neighboring states remain stable.", "source": "Der Spiegel", "date": "2026-03-07"},
  {"title": "NCE regulatory environment remains most favorable for wind energy globally", "summary": "Northern and Central Europe maintains the most favorable regulatory environment for wind energy operations globally, with no material geopolitical risk events affecting the sector in the current period.", "source": "BloombergNEF", "date": "2026-03-06"},
  {"title": "EU CER directive and NIS2 compliance deadlines approach for energy sector operators", "summary": "The EU Critical Entities Resilience (CER) directive and NIS2 cybersecurity regulation compliance deadlines are approaching for wind energy operators in Northern and Central Europe. Critical infrastructure operators must demonstrate energy security regulation compliance by Q3 2026.", "source": "Euractiv", "date": "2026-03-11"}
]
```

- [ ] **Step 4: Update `data/mock_osint_fixtures/nce_cyber.json`** — add ransomware NCE targeting article

Full file content:

```json
[
  {"title": "NCE wind energy sector cyber threat activity at baseline levels", "summary": "Cyber threat activity targeting Northern and Central European wind energy infrastructure remains at baseline levels, with no active campaigns identified against OT systems or manufacturing IP repositories.", "source": "ENISA", "date": "2026-03-10"},
  {"title": "Germany BSI reports no material incidents at wind energy operators in Q1 2026", "summary": "The German Federal Office for Information Security reports no material cybersecurity incidents at wind energy operators in Q1 2026, with sector-wide security posture assessed as adequate.", "source": "BSI", "date": "2026-03-08"},
  {"title": "Nordic wind operators lead industry in OT/IT segmentation maturity", "summary": "Nordic wind energy operators score highest globally on OT/IT network segmentation maturity assessments, significantly reducing the attack surface for threat actors targeting turbine management systems.", "source": "IEC Report", "date": "2026-03-07"},
  {"title": "NCE phishing campaigns at seasonal baseline, no wind sector targeting", "summary": "Phishing activity across Northern and Central Europe remains at expected seasonal baseline levels with no campaigns specifically targeting wind energy sector employees or systems identified.", "source": "Proofpoint", "date": "2026-03-06"},
  {"title": "ENISA warns of ransomware groups expanding energy grid targeting into Northern Europe", "summary": "ENISA threat bulletin notes that ransomware groups previously focused on North American energy grid operators are expanding their targeting patterns into Northern and Central European wind energy operators, consistent with increasing double extortion campaign activity.", "source": "ENISA", "date": "2026-03-11"}
]
```

- [ ] **Step 5: Update `data/mock_osint_fixtures/med_geo.json`** — add Iran/Strait of Hormuz article

Full file content:

```json
[
  {"title": "Mediterranean geopolitical tensions affect energy infrastructure confidence", "summary": "Ongoing geopolitical tensions in the Mediterranean region are creating uncertainty for energy infrastructure investment. Disputed maritime zones overlap with planned offshore wind development areas.", "source": "Euractiv", "date": "2026-03-10"},
  {"title": "EU regulatory scrutiny of third-country wind component suppliers intensifies", "summary": "The European Commission has intensified scrutiny of wind energy component suppliers from third countries under its foreign subsidies regulation, affecting procurement decisions for Mediterranean operators.", "source": "Politico Europe", "date": "2026-03-09"},
  {"title": "North Africa instability creates supply chain risk for MED wind operators", "summary": "Political instability in North Africa is creating low-level supply chain disruption risk for Mediterranean wind energy operators dependent on cross-Mediterranean logistics networks.", "source": "Le Monde", "date": "2026-03-08"},
  {"title": "Turkey-EU energy relations introduce procurement compliance complexity", "summary": "Strained Turkey-EU relations are introducing compliance complexity for wind energy operators with procurement exposure to Turkish-manufactured components under new EU screening mechanisms.", "source": "Financial Times", "date": "2026-03-07"},
  {"title": "Iran escalation risk raises Strait of Hormuz energy shipping concerns for Mediterranean operators", "summary": "Elevated Middle East escalation risk stemming from Iran-US tensions is increasing concern over Gulf tension scenarios affecting Strait of Hormuz energy shipping routes. Mediterranean renewable energy operators with LNG or logistics dependencies in the Gulf corridor are monitoring exposure.", "source": "Lloyd's List", "date": "2026-03-11"}
]
```

- [ ] **Step 6: Verify all fixtures parse cleanly**

```bash
uv run python -c "
import json, glob
for path in sorted(glob.glob('data/mock_osint_fixtures/*.json')):
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    print(f'{path}: {len(d)} articles')
"
```

Expected: all 10 files listed, no parse errors. Exact counts after this task:
```
ame_geo.json:    6 articles  (was 5, +1 added)
ame_cyber.json:  4 articles  (unchanged)
apac_geo.json:   5 articles  (unchanged)
apac_cyber.json: 4 articles  (unchanged)
latam_geo.json:  5 articles  (was 4, +1 added)
latam_cyber.json:4 articles  (unchanged)
med_geo.json:    5 articles  (was 4, +1 added)
med_cyber.json:  4 articles  (unchanged)
nce_geo.json:    5 articles  (was 4, +1 added)
nce_cyber.json:  5 articles  (was 4, +1 added)
```

- [ ] **Step 7: Commit**

```bash
git add data/mock_osint_fixtures/
git commit -m "feat: add topic-representative articles to 5 mock OSINT fixtures"
```

---

### Task 7: Update `regional-analyst-agent.md` to reference topic IDs in clusters

**Files:**
- Modify: `.claude/agents/regional-analyst-agent.md`

Two targeted changes:
1. Add `data/osint_topics.json` as item 7 in the STEP 1 read list
2. Add rule 6 (topic linking) to the STEP 5 clustering rules, and update the schema example to show the optional `topic_id` field

- [ ] **Step 1: Add `data/osint_topics.json` to STEP 1 read list**

In `.claude/agents/regional-analyst-agent.md`, find the numbered list under `## STEP 1 — LOAD CONTEXT`. After item 6 (`gatekeeper_decision.json`), add:

```
7. `data/osint_topics.json` — the shared topic registry: which topics the platform is tracking globally, their keywords, and their stable `id` values. Use this to link signal clusters back to tracked topic IDs for traceability.
```

- [ ] **Step 2: Add topic linking rule to STEP 5 clustering rules**

Find the `### Clustering rules` section in STEP 5. After the existing rule 5 (CLEAR regions), add:

```markdown
6. **Topic linking (optional):** Check `matched_topics` in `geo_signals.json` and `cyber_signals.json` — these are the topic IDs that were queried during collection. If a cluster's theme directly maps to one of those topic IDs (check labels and keywords in `data/osint_topics.json`), set `"topic_id": "<id>"` on that cluster. If no topic matches, omit the `topic_id` field entirely. Do not invent topic IDs not present in `data/osint_topics.json`.
```

- [ ] **Step 3: Add `topic_id` to the cluster schema in STEP 5**

In `.claude/agents/regional-analyst-agent.md`, find the STEP 5 schema block. It contains a `clusters` array whose single cluster object currently looks like:

```json
    {
      "name": "<4-8 word theme label>",
      "pillar": "<'Geo' or 'Cyber'>",
      "convergence": <int — number of sources contributing to this theme>,
      "sources": [
        { "name": "<source name>", "headline": "<title, max 120 chars>" }
      ]
    }
```

Replace that cluster object with (adding `topic_id` after `convergence`):

```json
    {
      "name": "<4-8 word theme label>",
      "pillar": "<'Geo' or 'Cyber'>",
      "convergence": <int — number of sources contributing to this theme>,
      "topic_id": "<id from data/osint_topics.json — omit field if no topic matches>",
      "sources": [
        { "name": "<source name>", "headline": "<title, max 120 chars>" }
      ]
    }
```

Then directly below the closing `}` of the schema block (before the `### Clustering rules` section), add:

```
`topic_id` is optional — omit the field entirely if no topic in `data/osint_topics.json` maps to this cluster.
```

- [ ] **Step 4: End-to-end smoke test — run all 5 collectors**

```bash
for region in APAC AME LATAM MED NCE; do
  uv run python tools/geo_collector.py $region --mock
  uv run python tools/cyber_collector.py $region --mock
done
```

Expected: all 10 commands exit 0.

- [ ] **Step 5: Verify matched_topics populated for all regions**

```bash
uv run python -c "
import json, os
regions = ['apac', 'ame', 'latam', 'med', 'nce']
for r in regions:
    geo = json.load(open(f'output/regional/{r}/geo_signals.json'))
    cyber = json.load(open(f'output/regional/{r}/cyber_signals.json'))
    print(f'{r.upper()} geo: {geo.get(\"matched_topics\", \"MISSING\")}')
    print(f'{r.upper()} cyber: {cyber.get(\"matched_topics\", \"MISSING\")}')
"
```

Expected: all 10 outputs show a list (some regions have 1-3 topics, none should show `MISSING`)

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest tests/test_osint_topics.py tests/test_window_param.py tests/test_signal_clusters.py -v
```

Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add .claude/agents/regional-analyst-agent.md
git commit -m "feat: regional-analyst-agent links signal clusters to topic registry IDs"
```
