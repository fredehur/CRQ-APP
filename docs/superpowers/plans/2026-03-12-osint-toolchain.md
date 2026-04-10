# OSINT Tool Chain Implementation Plan


**Goal:** Build a 4-tool OSINT signal collection layer that generates `geo_signals.json`, `cyber_signals.json`, and `scenario_map.json` per region from mock fixture data, with a clean seam for live search.

**Architecture:** `osint_search.py` is the only file that knows about mock vs. live — it loads fixtures in mock mode and will call Tavily in live mode. Collectors call it as a subprocess and parse stdout JSON. The normalization logic runs in both modes; only the data source changes when going live.

**Tech Stack:** Python 3.12, `uv`, stdlib only (`subprocess`, `json`, `os`, `sys`) — no new deps for mock mode.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `data/mock_osint_fixtures/apac_geo.json` | Create | Raw geo search fixtures for APAC |
| `data/mock_osint_fixtures/apac_cyber.json` | Create | Raw cyber search fixtures for APAC |
| `data/mock_osint_fixtures/ame_geo.json` | Create | Raw geo search fixtures for AME |
| `data/mock_osint_fixtures/ame_cyber.json` | Create | Raw cyber search fixtures for AME |
| `data/mock_osint_fixtures/latam_geo.json` | Create | Raw geo search fixtures for LATAM |
| `data/mock_osint_fixtures/latam_cyber.json` | Create | Raw cyber search fixtures for LATAM |
| `data/mock_osint_fixtures/med_geo.json` | Create | Raw geo search fixtures for MED |
| `data/mock_osint_fixtures/med_cyber.json` | Create | Raw cyber search fixtures for MED |
| `data/mock_osint_fixtures/nce_geo.json` | Create | Raw geo search fixtures for NCE |
| `data/mock_osint_fixtures/nce_cyber.json` | Create | Raw cyber search fixtures for NCE |
| `tools/osint_search.py` | Create | Search primitive — mock/live seam |
| `tools/geo_collector.py` | Create | Geo signal collector + normalizer |
| `tools/cyber_collector.py` | Create | Cyber signal collector + normalizer |
| `tools/scenario_mapper.py` | Create | Scenario cross-reference + confidence scorer |
| `tests/test_osint_search.py` | Create | Unit tests for search primitive |
| `tests/test_geo_collector.py` | Create | Integration tests for geo collector |
| `tests/test_cyber_collector.py` | Create | Integration tests for cyber collector |
| `tests/test_scenario_mapper.py` | Create | Integration tests for scenario mapper |

---

## Chunk 1: Fixtures + `osint_search.py`

### Task 1: Create fixture files

**Files:**
- Create: `data/mock_osint_fixtures/apac_geo.json`
- Create: `data/mock_osint_fixtures/apac_cyber.json`
- Create: `data/mock_osint_fixtures/ame_geo.json`
- Create: `data/mock_osint_fixtures/ame_cyber.json`
- Create: `data/mock_osint_fixtures/latam_geo.json`
- Create: `data/mock_osint_fixtures/latam_cyber.json`
- Create: `data/mock_osint_fixtures/med_geo.json`
- Create: `data/mock_osint_fixtures/med_cyber.json`
- Create: `data/mock_osint_fixtures/nce_geo.json`
- Create: `data/mock_osint_fixtures/nce_cyber.json`

Each file is a JSON array of 4–6 objects shaped like a real DDG/Tavily result: `{title, summary, source, date}`. Content must be region-appropriate and relevant to AeroGrid's crown jewels (turbine manufacturing IP, OT/SCADA, predictive maintenance, wind farm telemetry). DO NOT copy from `data/mock_threat_feeds/` — write raw article-style content.

- [ ] **Step 1: Create fixture directory**

```bash
mkdir -p data/mock_osint_fixtures
```

- [ ] **Step 2: Write `apac_geo.json`**

```json
[
  {
    "title": "South China Sea tensions drive manufacturing supply chain restructuring",
    "summary": "Escalating territorial disputes in the South China Sea are prompting multinational manufacturers to accelerate supply chain diversification away from single-region dependencies. Wind energy components face significant exposure.",
    "source": "Financial Times Asia",
    "date": "2026-03-10"
  },
  {
    "title": "China-Taiwan strait risk assessment: industrial sector exposure",
    "summary": "State-sponsored industrial espionage campaigns have intensified across APAC manufacturing hubs. Proprietary engineering designs and production IP are the primary targets of coordinated state-directed operations.",
    "source": "Reuters",
    "date": "2026-03-09"
  },
  {
    "title": "Australia tightens foreign investment screening for energy technology",
    "summary": "The Australian government has expanded critical infrastructure protection rules to include offshore wind farm operations and associated digital control systems, reflecting growing geopolitical concern over energy sector sovereignty.",
    "source": "Australian Financial Review",
    "date": "2026-03-08"
  },
  {
    "title": "Japan-South Korea trade frictions disrupt rare earth component flows",
    "summary": "Ongoing trade tensions between Japan and South Korea are creating upstream pressure on renewable energy manufacturers reliant on rare earth materials for turbine blade and generator production.",
    "source": "Nikkei Asia",
    "date": "2026-03-07"
  },
  {
    "title": "APAC state actors expand industrial targeting beyond traditional sectors",
    "summary": "Intelligence assessments indicate state-sponsored actors in the APAC region are broadening their targeting mandates to include renewable energy infrastructure, with wind turbine OT networks identified as a high-value objective.",
    "source": "Strait Times",
    "date": "2026-03-06"
  }
]
```

- [ ] **Step 3: Write `apac_cyber.json`**

```json
[
  {
    "title": "State-sponsored actors expand targeting to renewable energy operational networks",
    "summary": "Security researchers have documented new intrusion campaigns targeting operational technology networks in the Asia-Pacific manufacturing sector. Wind turbine control systems and predictive maintenance platforms are among the identified targets.",
    "source": "Recorded Future",
    "date": "2026-03-10"
  },
  {
    "title": "Supply chain compromise vector identified in APAC industrial software updates",
    "summary": "A sophisticated supply chain attack was identified targeting industrial automation software widely used in APAC wind energy manufacturing. The intrusion vector allowed persistent access to blade production line control systems.",
    "source": "SecurityWeek",
    "date": "2026-03-09"
  },
  {
    "title": "Spear-phishing campaign targets wind energy engineering teams in Southeast Asia",
    "summary": "A coordinated spear-phishing campaign is targeting senior engineers at renewable energy manufacturers across Southeast Asia. Lures reference confidential turbine design documents to harvest credentials with access to proprietary IP repositories.",
    "source": "BleepingComputer",
    "date": "2026-03-08"
  },
  {
    "title": "OT network segmentation failures expose turbine management platforms",
    "summary": "Assessments of APAC wind farm operators reveal persistent IT/OT segmentation weaknesses that allow cross-network propagation from enterprise networks into turbine management and telemetry platforms.",
    "source": "Industrial Cybersecurity Advisory",
    "date": "2026-03-07"
  }
]
```

- [ ] **Step 4: Write `ame_geo.json`**

```json
[
  {
    "title": "US executive order expands critical infrastructure designation to offshore wind",
    "summary": "A new executive order designates offshore wind farm operations as critical national infrastructure, triggering mandatory cybersecurity reporting requirements for operators and their technology supply chains.",
    "source": "Wall Street Journal",
    "date": "2026-03-10"
  },
  {
    "title": "Canada-US energy policy divergence creates regulatory compliance burden",
    "summary": "Diverging renewable energy regulations between Canada and the United States are creating compliance complexity for cross-border wind energy operators, with conflicting cybersecurity incident disclosure timelines.",
    "source": "Globe and Mail",
    "date": "2026-03-09"
  },
  {
    "title": "Congressional hearing highlights ransomware threat to US energy grid operators",
    "summary": "Testimony before the Senate Energy Committee identified ransomware as the primary near-term cyber threat to US energy infrastructure, with wind farm operations specifically cited as underprotected.",
    "source": "Politico",
    "date": "2026-03-08"
  },
  {
    "title": "CISA issues warning on critical infrastructure targeting by foreign actors",
    "summary": "CISA has issued an advisory warning that foreign state-sponsored actors are actively reconnaissance energy sector targets across North America, with a focus on operational disruption rather than data theft.",
    "source": "CISA",
    "date": "2026-03-07"
  },
  {
    "title": "IRA incentive structures accelerate wind capacity growth, expanding attack surface",
    "summary": "Rapid expansion of US wind energy capacity under IRA incentives is outpacing security investment, creating a growing attack surface of newly deployed turbine control networks with inconsistent security baselines.",
    "source": "Bloomberg Green",
    "date": "2026-03-06"
  }
]
```

- [ ] **Step 5: Write `ame_cyber.json`**

```json
[
  {
    "title": "Ransomware group targets North American energy operator, demands $22M",
    "summary": "A ransomware group known for targeting operational technology environments has successfully encrypted business systems at a North American energy operator. The group demanded $22M and threatened to release proprietary turbine efficiency data.",
    "source": "The Record",
    "date": "2026-03-10"
  },
  {
    "title": "Double-extortion ransomware hits wind energy maintenance platform",
    "summary": "A double-extortion ransomware campaign encrypted and exfiltrated data from a wind energy predictive maintenance platform. Recovery took 18 days and required full OT network rebuild at three facilities.",
    "source": "Wired",
    "date": "2026-03-09"
  },
  {
    "title": "FBI warns energy sector of escalating ransomware-as-a-service campaigns",
    "summary": "The FBI has issued a private industry notification warning energy sector operators of a significant increase in ransomware-as-a-service activity targeting operational systems, with initial access sold via compromised remote access credentials.",
    "source": "FBI PIN",
    "date": "2026-03-08"
  },
  {
    "title": "RDP exploitation drives initial access in energy sector ransomware incidents",
    "summary": "Analysis of recent ransomware incidents in the North American energy sector shows Remote Desktop Protocol exploitation as the dominant initial access vector, with turbine management networks frequently reachable from improperly segmented corporate environments.",
    "source": "Mandiant",
    "date": "2026-03-07"
  }
]
```

- [ ] **Step 6: Write `latam_geo.json`**

```json
[
  {
    "title": "Brazil wind energy sector shows stable political and regulatory environment",
    "summary": "Brazil's renewable energy regulatory framework remains stable following recent elections, with continued government support for wind energy expansion and no material geopolitical disruption to manufacturing operations.",
    "source": "Reuters Brazil",
    "date": "2026-03-10"
  },
  {
    "title": "LATAM regional trade agreements benefit wind energy component supply chains",
    "summary": "Recently ratified trade agreements across Latin America are reducing tariff barriers for wind energy components, improving supply chain economics without introducing material geopolitical risk.",
    "source": "Latin Finance",
    "date": "2026-03-08"
  },
  {
    "title": "Chile and Argentina renewable energy cooperation agreement signed",
    "summary": "Chile and Argentina have signed a bilateral renewable energy cooperation agreement, creating a stable regulatory environment for cross-border wind energy projects in Patagonia.",
    "source": "BN Americas",
    "date": "2026-03-06"
  },
  {
    "title": "LATAM political stability index remains high for energy sector operators",
    "summary": "Regional political stability indices for LATAM energy sector operations remain at multi-year highs, with no active geopolitical events materially affecting wind energy manufacturing or service operations.",
    "source": "Control Risks",
    "date": "2026-03-05"
  }
]
```

- [ ] **Step 7: Write `latam_cyber.json`**

```json
[
  {
    "title": "LATAM cyber threat landscape remains low intensity for industrial operators",
    "summary": "Regional cyber threat assessments for Latin America indicate a low-intensity threat environment for industrial operators, with no active campaigns targeting wind energy infrastructure identified.",
    "source": "CrowdStrike",
    "date": "2026-03-10"
  },
  {
    "title": "Brazil's renewable energy operators report minimal cybersecurity incidents in 2025",
    "summary": "Brazilian renewable energy operators reported the lowest cybersecurity incident rate in five years during 2025, attributed to improved network segmentation practices and regional threat actor disinterest in the sector.",
    "source": "TechCrunch Brazil",
    "date": "2026-03-08"
  },
  {
    "title": "No active OT threat campaigns targeting LATAM wind energy sector",
    "summary": "Threat intelligence providers confirm no active operational technology campaigns targeting wind energy infrastructure in Latin America. The region remains a low-priority target for known threat actor groups.",
    "source": "Dragos",
    "date": "2026-03-06"
  },
  {
    "title": "LATAM phishing activity stable, no energy sector targeting observed",
    "summary": "Regional phishing activity in Latin America remains at baseline levels with no observed targeting of wind energy sector employees or systems in the current reporting period.",
    "source": "Proofpoint",
    "date": "2026-03-05"
  }
]
```

- [ ] **Step 8: Write `med_geo.json`**

```json
[
  {
    "title": "Mediterranean geopolitical tensions affect energy infrastructure confidence",
    "summary": "Ongoing geopolitical tensions in the Mediterranean region are creating uncertainty for energy infrastructure investment. Disputed maritime zones overlap with planned offshore wind development areas.",
    "source": "Euractiv",
    "date": "2026-03-10"
  },
  {
    "title": "EU regulatory scrutiny of third-country wind component suppliers intensifies",
    "summary": "The European Commission has intensified scrutiny of wind energy component suppliers from third countries under its foreign subsidies regulation, affecting procurement decisions for Mediterranean operators.",
    "source": "Politico Europe",
    "date": "2026-03-09"
  },
  {
    "title": "North Africa instability creates supply chain risk for MED wind operators",
    "summary": "Political instability in North Africa is creating low-level supply chain disruption risk for Mediterranean wind energy operators dependent on cross-Mediterranean logistics networks.",
    "source": "Le Monde",
    "date": "2026-03-08"
  },
  {
    "title": "Turkey-EU energy relations introduce procurement compliance complexity",
    "summary": "Strained Turkey-EU relations are introducing compliance complexity for wind energy operators with procurement exposure to Turkish-manufactured components under new EU screening mechanisms.",
    "source": "Financial Times",
    "date": "2026-03-07"
  }
]
```

- [ ] **Step 9: Write `med_cyber.json`**

```json
[
  {
    "title": "Insider threat incident at MED energy operator highlights access control gaps",
    "summary": "An insider misuse incident at a Mediterranean energy operator resulted in unauthorized access to wind farm telemetry data. A former maintenance contractor retained active system credentials for six months post-departure.",
    "source": "Dark Reading",
    "date": "2026-03-10"
  },
  {
    "title": "Privileged access misuse risk elevated at Mediterranean wind service providers",
    "summary": "Third-party service providers with privileged access to Mediterranean wind farm operational systems present an elevated insider misuse risk, particularly where access reviews are infrequent.",
    "source": "Gartner",
    "date": "2026-03-08"
  },
  {
    "title": "MED region identity and access management audit reveals orphaned credentials",
    "summary": "An audit of identity and access management practices at Mediterranean energy operators identified widespread orphaned credentials held by former employees and contractors with access to OT systems.",
    "source": "SC Magazine",
    "date": "2026-03-07"
  },
  {
    "title": "Disgruntled employee risk in energy sector elevated amid restructuring",
    "summary": "Workforce restructuring across European energy operators is elevating the risk of insider misuse incidents, as disgruntled employees with system access represent a known data exfiltration and sabotage vector.",
    "source": "Cybersecurity Insiders",
    "date": "2026-03-06"
  }
]
```

- [ ] **Step 10: Write `nce_geo.json`**

```json
[
  {
    "title": "Northern Europe wind energy sector operates in stable geopolitical environment",
    "summary": "NATO alignment and strong bilateral energy cooperation agreements across Northern and Central Europe provide a stable geopolitical environment for wind energy operators, with no active state-level threats identified.",
    "source": "Handelsblatt",
    "date": "2026-03-10"
  },
  {
    "title": "EU energy independence strategy reinforces NCE wind energy investment",
    "summary": "The EU's strategic energy independence agenda continues to reinforce investment in Northern and Central European wind energy, with strong regulatory frameworks providing operational stability.",
    "source": "Euractiv",
    "date": "2026-03-08"
  },
  {
    "title": "Germany's offshore wind expansion proceeds without geopolitical disruption",
    "summary": "Germany's offshore wind expansion program is proceeding on schedule with no material geopolitical disruptions. Baltic Sea maritime agreements with neighboring states remain stable.",
    "source": "Der Spiegel",
    "date": "2026-03-07"
  },
  {
    "title": "NCE regulatory environment remains most favorable for wind energy globally",
    "summary": "Northern and Central Europe maintains the most favorable regulatory environment for wind energy operations globally, with no material geopolitical risk events affecting the sector in the current period.",
    "source": "BloombergNEF",
    "date": "2026-03-06"
  }
]
```

- [ ] **Step 11: Write `nce_cyber.json`**

```json
[
  {
    "title": "NCE wind energy sector cyber threat activity at baseline levels",
    "summary": "Cyber threat activity targeting Northern and Central European wind energy infrastructure remains at baseline levels, with no active campaigns identified against OT systems or manufacturing IP repositories.",
    "source": "ENISA",
    "date": "2026-03-10"
  },
  {
    "title": "Germany BSI reports no material incidents at wind energy operators in Q1 2026",
    "summary": "The German Federal Office for Information Security reports no material cybersecurity incidents at wind energy operators in Q1 2026, with sector-wide security posture assessed as adequate.",
    "source": "BSI",
    "date": "2026-03-08"
  },
  {
    "title": "Nordic wind operators lead industry in OT/IT segmentation maturity",
    "summary": "Nordic wind energy operators score highest globally on OT/IT network segmentation maturity assessments, significantly reducing the attack surface for threat actors targeting turbine management systems.",
    "source": "IEC Report",
    "date": "2026-03-07"
  },
  {
    "title": "NCE phishing campaigns at seasonal baseline, no wind sector targeting",
    "summary": "Phishing activity across Northern and Central Europe remains at expected seasonal baseline levels with no campaigns specifically targeting wind energy sector employees or systems identified.",
    "source": "Proofpoint",
    "date": "2026-03-06"
  }
]
```

- [ ] **Step 12: Validate all 10 fixture files parse as JSON**

```bash
python -c "
import json, glob, sys
ok = True
for path in sorted(glob.glob('data/mock_osint_fixtures/*.json')):
    data = json.load(open(path, encoding='utf-8'))
    assert isinstance(data, list), f'{path}: expected array, got {type(data)}'
    assert len(data) >= 4, f'{path}: expected >= 4 articles, got {len(data)}'
    for article in data:
        for key in ('title', 'summary', 'source', 'date'):
            assert key in article, f'{path}: article missing key {key!r}'
    print(f'OK: {path} ({len(data)} articles)')
print('All fixtures valid.')
"
```

Expected: 10 lines of `OK: data/mock_osint_fixtures/...` followed by `All fixtures valid.`

- [ ] **Step 13: Commit fixtures**

```bash
git add data/mock_osint_fixtures/
git commit -m "feat: add mock OSINT fixture files for all 5 regions (geo + cyber)"
```

---

### Task 2: `tools/osint_search.py`

**Files:**
- Create: `tools/osint_search.py`
- Create: `tests/test_osint_search.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_osint_search.py`:

```python
"""Tests for osint_search.py — the search primitive and mock/live seam."""
import json
import subprocess
import sys

PYTHON = sys.executable


def run(args):
    """Run osint_search.py with given args, return (returncode, stdout, stderr)."""
    result = subprocess.run(
        [PYTHON, "tools/osint_search.py"] + args,
        capture_output=True, text=True, encoding="utf-8"
    )
    return result.returncode, result.stdout, result.stderr


def test_mock_geo_returns_valid_json_array():
    code, out, _ = run(["APAC", "wind turbine supply chain", "--type", "geo", "--mock"])
    assert code == 0
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) >= 4


def test_mock_cyber_returns_valid_json_array():
    code, out, _ = run(["APAC", "OT security", "--type", "cyber", "--mock"])
    assert code == 0
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) >= 4


def test_each_article_has_required_keys():
    _, out, _ = run(["APAC", "query", "--type", "geo", "--mock"])
    data = json.loads(out)
    for article in data:
        assert "title" in article
        assert "summary" in article
        assert "source" in article
        assert "date" in article


def test_all_five_regions_geo():
    for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        code, out, _ = run([region, "query", "--type", "geo", "--mock"])
        assert code == 0, f"Failed for region {region}"
        assert json.loads(out)


def test_all_five_regions_cyber():
    for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        code, out, _ = run([region, "query", "--type", "cyber", "--mock"])
        assert code == 0, f"Failed for region {region}"
        assert json.loads(out)


def test_invalid_region_exits_nonzero():
    code, _, err = run(["INVALID", "query", "--type", "geo", "--mock"])
    assert code != 0


def test_missing_type_flag_exits_nonzero():
    code, _, err = run(["APAC", "query", "--mock"])
    assert code != 0


def test_no_args_exits_nonzero():
    code, _, _ = run([])
    assert code != 0
```

- [ ] **Step 2: Run test — verify it fails**

```bash
uv run pytest tests/test_osint_search.py -v
```

Expected: Positive tests (`test_mock_geo_returns_valid_json_array` etc.) fail with `json.JSONDecodeError` — subprocess returns empty stdout because `tools/osint_search.py` does not exist. Error-exit tests may spuriously PASS (subprocess exits nonzero for a different reason) — confirm each test's failure reason before proceeding.

- [ ] **Step 3: Implement `tools/osint_search.py`**

```python
#!/usr/bin/env python3
"""OSINT search primitive — returns raw search results as JSON array to stdout.

Usage:
    osint_search.py REGION QUERY --type geo|cyber [--mock]

Mock mode loads data/mock_osint_fixtures/{region_lower}_{type}.json.
Live mode calls Tavily API (requires TAVILY_API_KEY env var).
"""
import json
import os
import sys

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
VALID_TYPES = {"geo", "cyber"}


def load_fixture(region: str, type_: str) -> list:
    path = f"data/mock_osint_fixtures/{region.lower()}_{type_}.json"
    if not os.path.exists(path):
        print(f"[osint_search] fixture not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def search_live(region: str, query: str, type_: str) -> list:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        print("[osint_search] TAVILY_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    # Tavily integration point — swap this block when going live
    raise NotImplementedError("Live search not yet implemented")


def parse_args(argv: list) -> tuple:
    """Return (region, query, type_, mock) or exit on bad args."""
    if len(argv) < 3:
        print("Usage: osint_search.py REGION QUERY --type geo|cyber [--mock]",
              file=sys.stderr)
        sys.exit(1)

    region = argv[0].upper()
    query = argv[1]
    type_ = None
    mock = False

    i = 2
    while i < len(argv):
        if argv[i] == "--type" and i + 1 < len(argv):
            type_ = argv[i + 1]
            i += 2
        elif argv[i] == "--mock":
            mock = True
            i += 1
        else:
            i += 1

    if region not in VALID_REGIONS:
        print(f"[osint_search] invalid region '{region}'. Valid: {sorted(VALID_REGIONS)}",
              file=sys.stderr)
        sys.exit(1)

    if type_ not in VALID_TYPES:
        print(f"[osint_search] --type must be one of {sorted(VALID_TYPES)}",
              file=sys.stderr)
        sys.exit(1)

    return region, query, type_, mock


def main():
    region, query, type_, mock = parse_args(sys.argv[1:])

    if mock:
        results = load_fixture(region, type_)
    else:
        results = search_live(region, query, type_)

    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_osint_search.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Smoke test from CLI**

```bash
uv run python tools/osint_search.py APAC "wind turbine supply chain" --mock --type geo
```

Expected: JSON array printed to stdout, exit 0. (This is the exact command from Acceptance Criterion 4 in the spec.)

- [ ] **Step 6: Commit**

```bash
git add tools/osint_search.py tests/test_osint_search.py
git commit -m "feat: add osint_search.py search primitive with mock fixture routing"
```

---

## Chunk 2: `geo_collector.py` + `cyber_collector.py`

### Task 3: `tools/geo_collector.py`

**Prerequisite:** Tasks 1 and 2 complete — fixture files in `data/mock_osint_fixtures/` and `tools/osint_search.py` must exist before running these tests.

**Files:**
- Create: `tools/geo_collector.py`
- Create: `tests/test_geo_collector.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_geo_collector.py`:

```python
"""Tests for geo_collector.py — geo signal collection and normalization."""
import json
import os
import subprocess
import sys

PYTHON = sys.executable


def run(args):
    result = subprocess.run(
        [PYTHON, "tools/geo_collector.py"] + args,
        capture_output=True, text=True, encoding="utf-8"
    )
    return result.returncode, result.stdout, result.stderr


def read_output(region):
    path = f"output/regional/{region.lower()}/geo_signals.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_apac_writes_geo_signals():
    code, _, err = run(["APAC", "--mock"])
    assert code == 0, f"stderr: {err}"
    data = read_output("APAC")
    assert "summary" in data
    assert "lead_indicators" in data
    assert "dominant_pillar" in data


def test_geo_signals_types():
    run(["APAC", "--mock"])
    data = read_output("APAC")
    assert isinstance(data["summary"], str) and len(data["summary"]) > 10
    assert isinstance(data["lead_indicators"], list) and len(data["lead_indicators"]) >= 1
    assert data["dominant_pillar"] in {"Geopolitical", "Cyber", "Regulatory"}


def test_all_five_regions():
    for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        code, _, err = run([region, "--mock"])
        assert code == 0, f"Failed for {region}: {err}"
        data = read_output(region)
        assert all(k in data for k in ["summary", "lead_indicators", "dominant_pillar"])


def test_no_args_exits_nonzero():
    code, _, _ = run([])
    assert code != 0


def test_invalid_region_exits_nonzero():
    code, _, _ = run(["INVALID", "--mock"])
    assert code != 0
```

- [ ] **Step 2: Run test — verify it fails**

```bash
uv run pytest tests/test_geo_collector.py -v
```

Expected: `AssertionError` on `code == 0` — subprocess returns nonzero because `tools/geo_collector.py` does not exist yet.

- [ ] **Step 3: Implement `tools/geo_collector.py`**

```python
#!/usr/bin/env python3
"""Geo signal collector — calls osint_search.py, normalizes to geo_signals.json.

Usage:
    geo_collector.py REGION [--mock]
"""
import json
import os
import subprocess
import sys

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}

# Keyword sets for dominant pillar inference
GEO_KEYWORDS = {
    "geopolit", "state", "trade", "territorial", "sanction", "political",
    "government", "minister", "treaty", "conflict", "dispute", "tension"
}
CYBER_KEYWORDS = {
    "cyber", "ot", "scada", "intrusion", "ransomware", "malware",
    "phishing", "breach", "attack", "hack", "threat", "apt"
}
REGULATORY_KEYWORDS = {
    "regulat", "compliance", "law", "policy", "legislat", "directive",
    "requirement", "gdpr", "mandate"
}


def run_search(region: str, query: str, mock: bool) -> list:
    cmd = [sys.executable, "tools/osint_search.py", region, query,
           "--type", "geo"]
    if mock:
        cmd.append("--mock")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"[geo_collector] search failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def infer_dominant_pillar(articles: list) -> str:
    text = " ".join(
        f"{a.get('title', '')} {a.get('summary', '')}".lower()
        for a in articles
    )
    scores = {
        "Geopolitical": sum(1 for kw in GEO_KEYWORDS if kw in text),
        "Cyber": sum(1 for kw in CYBER_KEYWORDS if kw in text),
        "Regulatory": sum(1 for kw in REGULATORY_KEYWORDS if kw in text),
    }
    return max(scores, key=scores.get)


def normalize(articles: list) -> dict:
    if not articles:
        return {
            "summary": "No geopolitical signals detected in current period.",
            "lead_indicators": [],
            "dominant_pillar": "Geopolitical"
        }

    # Summary: join the first two article summaries
    top = articles[:2]
    summary = " ".join(
        a.get("summary", a.get("title", ""))[:250] for a in top
    ).strip()

    # Lead indicators: titles of the first 3 articles
    lead_indicators = [
        a["title"] for a in articles[:3] if a.get("title")
    ]

    dominant_pillar = infer_dominant_pillar(articles)

    return {
        "summary": summary,
        "lead_indicators": lead_indicators,
        "dominant_pillar": dominant_pillar,
    }


def collect(region: str, mock: bool) -> dict:
    articles1 = run_search(region, f"{region} geopolitical risk wind energy", mock)
    articles2 = run_search(region, f"{region} trade tensions manufacturing", mock)
    return normalize(articles1 + articles2)


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: geo_collector.py REGION [--mock]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    mock = "--mock" in args

    if region not in VALID_REGIONS:
        print(f"[geo_collector] invalid region '{region}'", file=sys.stderr)
        sys.exit(1)

    signals = collect(region, mock)

    out_path = f"output/regional/{region.lower()}/geo_signals.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(signals, f, indent=2, ensure_ascii=False)

    print(f"[geo_collector] wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_geo_collector.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/geo_collector.py tests/test_geo_collector.py
git commit -m "feat: add geo_collector.py with pillar inference and normalization"
```

---

### Task 4: `tools/cyber_collector.py`

**Prerequisite:** Tasks 1 and 2 complete — fixture files in `data/mock_osint_fixtures/` and `tools/osint_search.py` must exist before running these tests.

**Files:**
- Create: `tools/cyber_collector.py`
- Create: `tests/test_cyber_collector.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cyber_collector.py`:

```python
"""Tests for cyber_collector.py — cyber signal collection and normalization."""
import json
import os
import subprocess
import sys

PYTHON = sys.executable


def run(args):
    result = subprocess.run(
        [PYTHON, "tools/cyber_collector.py"] + args,
        capture_output=True, text=True, encoding="utf-8"
    )
    return result.returncode, result.stdout, result.stderr


def read_output(region):
    path = f"output/regional/{region.lower()}/cyber_signals.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_apac_writes_cyber_signals():
    code, _, err = run(["APAC", "--mock"])
    assert code == 0, f"stderr: {err}"
    data = read_output("APAC")
    assert "summary" in data
    assert "threat_vector" in data
    assert "target_assets" in data


def test_cyber_signals_types():
    run(["APAC", "--mock"])
    data = read_output("APAC")
    assert isinstance(data["summary"], str) and len(data["summary"]) > 10
    assert isinstance(data["threat_vector"], str) and len(data["threat_vector"]) > 0
    assert isinstance(data["target_assets"], list) and len(data["target_assets"]) >= 1


def test_all_five_regions():
    for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        code, _, err = run([region, "--mock"])
        assert code == 0, f"Failed for {region}: {err}"
        data = read_output(region)
        assert all(k in data for k in ["summary", "threat_vector", "target_assets"])


def test_no_args_exits_nonzero():
    code, _, _ = run([])
    assert code != 0


def test_invalid_region_exits_nonzero():
    code, _, _ = run(["INVALID", "--mock"])
    assert code != 0
```

- [ ] **Step 2: Run test — verify it fails**

```bash
uv run pytest tests/test_cyber_collector.py -v
```

Expected: `AssertionError` on `code == 0` — subprocess returns nonzero because `tools/cyber_collector.py` does not exist yet.

- [ ] **Step 3: Implement `tools/cyber_collector.py`**

```python
#!/usr/bin/env python3
"""Cyber signal collector — calls osint_search.py, normalizes to cyber_signals.json.

Usage:
    cyber_collector.py REGION [--mock]
"""
import json
import os
import subprocess
import sys

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}

# Crown jewel asset keywords for target_assets extraction (from company_profile.json)
ASSET_KEYWORDS = {
    "turbine": "Turbine manufacturing IP",
    "blade": "Turbine blade design",
    "scada": "OT/SCADA networks",
    "ot network": "OT/SCADA networks",
    "predictive maintenance": "Predictive maintenance platform",
    "telemetry": "Wind farm telemetry",
    "ip repositor": "Proprietary IP repositories",
    "design": "Proprietary engineering designs",
    "production line": "Manufacturing production systems",
    "remote access": "Remote access infrastructure",
}

# Threat vector keywords — pick the most specific match
VECTOR_KEYWORDS = [
    ("spear-phish", "Spear-phishing targeting engineering credentials"),
    ("supply chain", "Supply chain compromise via third-party software"),
    ("ransomware", "Ransomware via compromised remote access credentials"),
    ("rdp", "RDP exploitation for initial access"),
    ("insider", "Insider misuse of privileged system access"),
    ("phish", "Phishing campaign targeting employee credentials"),
    ("intrusion", "Network intrusion targeting OT environments"),
]


def run_search(region: str, query: str, mock: bool) -> list:
    cmd = [sys.executable, "tools/osint_search.py", region, query,
           "--type", "cyber"]
    if mock:
        cmd.append("--mock")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"[cyber_collector] search failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def extract_threat_vector(articles: list) -> str:
    text = " ".join(
        f"{a.get('title', '')} {a.get('summary', '')}".lower()
        for a in articles
    )
    for keyword, label in VECTOR_KEYWORDS:
        if keyword in text:
            return label
    return "Network intrusion targeting operational systems"


def extract_target_assets(articles: list) -> list:
    text = " ".join(
        f"{a.get('title', '')} {a.get('summary', '')}".lower()
        for a in articles
    )
    found = []
    seen = set()
    for keyword, asset in ASSET_KEYWORDS.items():
        if keyword in text and asset not in seen:
            found.append(asset)
            seen.add(asset)
    if not found:
        found = ["Operational technology systems"]
    return found[:3]


def normalize(articles: list) -> dict:
    if not articles:
        return {
            "summary": "No active cyber threat signals detected in current period.",
            "threat_vector": "No active threat vector identified",
            "target_assets": ["Operational technology systems"],
        }

    top = articles[:2]
    summary = " ".join(
        a.get("summary", a.get("title", ""))[:250] for a in top
    ).strip()

    threat_vector = extract_threat_vector(articles)
    target_assets = extract_target_assets(articles)

    return {
        "summary": summary,
        "threat_vector": threat_vector,
        "target_assets": target_assets,
    }


def collect(region: str, mock: bool) -> dict:
    articles1 = run_search(
        region, f"{region} cyber threat industrial control systems", mock
    )
    articles2 = run_search(
        region, f"{region} OT security wind energy", mock
    )
    return normalize(articles1 + articles2)


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: cyber_collector.py REGION [--mock]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    mock = "--mock" in args

    if region not in VALID_REGIONS:
        print(f"[cyber_collector] invalid region '{region}'", file=sys.stderr)
        sys.exit(1)

    signals = collect(region, mock)

    out_path = f"output/regional/{region.lower()}/cyber_signals.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(signals, f, indent=2, ensure_ascii=False)

    print(f"[cyber_collector] wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_cyber_collector.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/cyber_collector.py tests/test_cyber_collector.py
git commit -m "feat: add cyber_collector.py with vector and asset extraction"
```

---

## Chunk 3: `scenario_mapper.py` + End-to-End

### Task 5: `tools/scenario_mapper.py`

**Files:**
- Create: `tools/scenario_mapper.py`
- Create: `tests/test_scenario_mapper.py`

**Context:** `scenario_mapper.py` reads `geo_signals.json` and `cyber_signals.json` from disk (written by collectors), cross-references `data/master_scenarios.json` to find the closest scenario match, and writes `scenario_map.json`. The `financial_rank` it writes MUST equal the actual `financial_rank` from `master_scenarios.json` for the matched scenario — no invented values.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scenario_mapper.py`:

```python
"""Tests for scenario_mapper.py — scenario matching and financial rank lookup."""
import json
import subprocess
import sys

PYTHON = sys.executable


def run(args):
    result = subprocess.run(
        [PYTHON, "tools/scenario_mapper.py"] + args,
        capture_output=True, text=True, encoding="utf-8"
    )
    return result.returncode, result.stdout, result.stderr


def read_output(region):
    path = f"output/regional/{region.lower()}/scenario_map.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_master():
    with open("data/master_scenarios.json", encoding="utf-8") as f:
        data = json.load(f)
    return {s["incident_type"]: s for s in data["scenarios"]}


def setup_region(region):
    """Run collectors first so signal files exist."""
    for tool in ["tools/geo_collector.py", "tools/cyber_collector.py"]:
        result = subprocess.run(
            [PYTHON, tool, region, "--mock"],
            capture_output=True, text=True, encoding="utf-8"
        )
        assert result.returncode == 0, (
            f"Collector {tool} failed for {region}: {result.stderr}"
        )


def test_apac_writes_scenario_map():
    setup_region("APAC")
    code, _, err = run(["APAC", "--mock"])
    assert code == 0, f"stderr: {err}"
    data = read_output("APAC")
    assert "top_scenario" in data
    assert "confidence" in data
    assert "financial_rank" in data
    assert "rationale" in data


def test_schema_types():
    setup_region("APAC")
    run(["APAC", "--mock"])
    data = read_output("APAC")
    assert isinstance(data["top_scenario"], str)
    assert data["confidence"] in {"high", "medium", "low"}
    assert isinstance(data["financial_rank"], int)
    assert 1 <= data["financial_rank"] <= 9
    assert isinstance(data["rationale"], str) and len(data["rationale"]) > 10


def test_top_scenario_exists_in_master():
    setup_region("APAC")
    run(["APAC", "--mock"])
    data = read_output("APAC")
    master = load_master()
    assert data["top_scenario"] in master, (
        f"'{data['top_scenario']}' not found in master_scenarios.json"
    )


def test_financial_rank_matches_master():
    """financial_rank must equal the rank from master_scenarios.json for the matched scenario."""
    setup_region("APAC")
    run(["APAC", "--mock"])
    data = read_output("APAC")
    master = load_master()
    expected_rank = master[data["top_scenario"]]["financial_rank"]
    assert data["financial_rank"] == expected_rank, (
        f"financial_rank {data['financial_rank']} != master rank {expected_rank} "
        f"for scenario '{data['top_scenario']}'"
    )


def test_all_five_regions():
    master = load_master()
    for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        setup_region(region)
        code, _, err = run([region, "--mock"])
        assert code == 0, f"Failed for {region}: {err}"
        data = read_output(region)
        assert all(k in data for k in ["top_scenario", "confidence", "financial_rank", "rationale"]), \
            f"{region}: missing keys in {list(data.keys())}"
        assert data["top_scenario"] in master, f"{region}: unknown scenario '{data['top_scenario']}'"
        assert data["confidence"] in {"high", "medium", "low"}, f"{region}: bad confidence"
        expected = master[data["top_scenario"]]["financial_rank"]
        assert data["financial_rank"] == expected, \
            f"{region}: financial_rank mismatch (got {data['financial_rank']}, expected {expected})"


def test_no_args_exits_nonzero():
    code, _, _ = run([])
    assert code != 0


def test_invalid_region_exits_nonzero():
    code, _, _ = run(["INVALID", "--mock"])
    assert code != 0
```

- [ ] **Step 2: Run test — verify it fails**

```bash
uv run pytest tests/test_scenario_mapper.py -v
```

Expected: `AssertionError` on `code == 0` — subprocess returns nonzero because `tools/scenario_mapper.py` does not exist yet.

- [ ] **Step 3: Implement `tools/scenario_mapper.py`**

```python
#!/usr/bin/env python3
"""Scenario mapper — maps geo+cyber signals to master scenario, writes scenario_map.json.

Usage:
    scenario_mapper.py REGION [--mock]

Reads:
    output/regional/{region}/geo_signals.json
    output/regional/{region}/cyber_signals.json
    data/master_scenarios.json

Writes:
    output/regional/{region}/scenario_map.json
"""
import json
import os
import sys

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}

# Keyword → scenario name mapping. Keys are lowercased substrings to match.
# Ordered from most specific to least specific.
SCENARIO_KEYWORDS = {
    "Ransomware": [
        "ransomware", "ransom", "encrypt", "extort", "double-extortion"
    ],
    "System intrusion": [
        "intrusion", "apt", "espionage", "supply chain compromise",
        "spear-phish", "exfiltrat", "breach", "persistent access"
    ],
    "Insider misuse": [
        "insider", "disgruntled", "privileged access misuse",
        "orphaned credential", "former employee", "contractor"
    ],
    "Accidental disclosure": [
        "accidental", "disclosure", "leak", "exposure", "misconfigur"
    ],
    "Physical threat": [
        "physical", "sabotage", "vandal", "destruction"
    ],
    "DoS attack": [
        "denial of service", "dos", "ddos", "flood", "availability"
    ],
    "Scam or fraud": [
        "fraud", "scam", "social engineer"
    ],
    "Defacement": [
        "defacement", "deface"
    ],
    "System failure": [
        "system failure", "outage"
    ],
}


def load_master() -> dict:
    path = "data/master_scenarios.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {s["incident_type"]: s for s in data["scenarios"]}


def load_signals(region: str) -> tuple:
    region_lower = region.lower()
    geo_path = f"output/regional/{region_lower}/geo_signals.json"
    cyber_path = f"output/regional/{region_lower}/cyber_signals.json"

    for path in (geo_path, cyber_path):
        if not os.path.exists(path):
            print(f"[scenario_mapper] missing signal file: {path}. "
                  f"Run geo_collector.py and cyber_collector.py first.",
                  file=sys.stderr)
            sys.exit(1)

    with open(geo_path, encoding="utf-8") as f:
        geo = json.load(f)
    with open(cyber_path, encoding="utf-8") as f:
        cyber = json.load(f)

    return geo, cyber


def build_signal_text(geo: dict, cyber: dict) -> str:
    parts = [
        geo.get("summary", ""),
        " ".join(geo.get("lead_indicators", [])),
        cyber.get("summary", ""),
        cyber.get("threat_vector", ""),
        " ".join(cyber.get("target_assets", [])),
    ]
    return " ".join(parts).lower()


def score_scenarios(text: str) -> dict:
    """Return {scenario_name: hit_count} for all scenarios."""
    scores = {}
    for scenario, keywords in SCENARIO_KEYWORDS.items():
        scores[scenario] = sum(1 for kw in keywords if kw in text)
    return scores


def pick_scenario(scores: dict, master: dict) -> tuple:
    """Return (top_scenario_name, confidence, financial_rank, rationale)."""
    top = max(scores, key=scores.get)
    top_score = scores[top]

    if top_score == 0:
        # No keyword match — fall back to highest financial impact scenario
        top = "System intrusion"
        confidence = "low"
        rationale = (
            f"No strong signal match found; defaulting to '{top}' "
            f"(highest financial impact scenario) as a conservative baseline."
        )
    else:
        if top_score >= 3:
            confidence = "high"
        elif top_score >= 1:
            confidence = "medium"
        else:
            confidence = "low"
        rationale = (
            f"Signal text matched {top_score} indicator(s) for '{top}', "
            f"which ranks #{master[top]['financial_rank']} by financial impact globally."
        )

    financial_rank = master[top]["financial_rank"]
    return top, confidence, financial_rank, rationale


def map_scenario(region: str) -> dict:
    master = load_master()
    geo, cyber = load_signals(region)
    text = build_signal_text(geo, cyber)
    scores = score_scenarios(text)
    top, confidence, financial_rank, rationale = pick_scenario(scores, master)
    return {
        "top_scenario": top,
        "confidence": confidence,
        "financial_rank": financial_rank,
        "rationale": rationale,
    }


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: scenario_mapper.py REGION [--mock]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    # --mock is accepted for CLI consistency with other tools but has no effect here.
    # scenario_mapper always reads signal files from disk (written by collectors).

    if region not in VALID_REGIONS:
        print(f"[scenario_mapper] invalid region '{region}'", file=sys.stderr)
        sys.exit(1)

    result = map_scenario(region)

    out_path = f"output/regional/{region.lower()}/scenario_map.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[scenario_mapper] wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_scenario_mapper.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/scenario_mapper.py tests/test_scenario_mapper.py
git commit -m "feat: add scenario_mapper.py with master scenario cross-reference"
```

---

### End-to-End Acceptance Check

- [ ] **Step 1: Run full tool chain for all 5 regions**

```bash
for region in APAC AME LATAM MED NCE; do
  echo "=== $region ==="
  uv run python tools/geo_collector.py $region --mock
  uv run python tools/cyber_collector.py $region --mock
  uv run python tools/scenario_mapper.py $region --mock
done
```

Expected: 15 lines of `[tool] wrote output/regional/{region}/...` to stderr, exit 0 for all.

- [ ] **Step 2: Run all tests together**

```bash
uv run pytest tests/test_osint_search.py tests/test_geo_collector.py tests/test_cyber_collector.py tests/test_scenario_mapper.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Verify output file structure**

```bash
find output/regional -name "*.json" | sort
```

Expected output includes for all 5 regions:
```
output/regional/apac/cyber_signals.json
output/regional/apac/geo_signals.json
output/regional/apac/scenario_map.json
... (same for ame, latam, med, nce)
```

- [ ] **Step 4: Spot-check scenario financial_rank integrity**

```bash
python -c "
import json, glob
master = {s['incident_type']: s for s in json.load(open('data/master_scenarios.json'))['scenarios']}
for path in sorted(glob.glob('output/regional/*/scenario_map.json')):
    d = json.load(open(path))
    expected = master[d['top_scenario']]['financial_rank']
    status = 'OK' if d['financial_rank'] == expected else 'FAIL'
    print(f'{status}: {path} -> {d[\"top_scenario\"]} rank={d[\"financial_rank\"]} (expected {expected})')
"
```

Expected: 5 lines of `OK: output/regional/...`

- [ ] **Step 5: Confirm `.gitignore` covers output artifacts**

`output/` files are generated at runtime and should not be committed — they are archived by `tools/archive_run.py`. Verify `output/regional/` is excluded:

```bash
git status output/regional/
```

Expected: no files staged or tracked. If `output/regional/` is tracked, add it to `.gitignore`.
