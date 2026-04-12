# Firecrawl Integration Implementation Plan

**Goal:** Add Firecrawl as a depth layer between Tavily search and LLM synthesis so the pipeline works from full article text instead of 200-char snippets.

**Architecture:** New standalone module `tools/firecrawl_scraper.py` is imported directly by `osint_collector.py` and `vacr_researcher.py`. Tavily remains the discovery layer; Firecrawl scrapes the top-5 URLs sorted by Tavily relevance score. Failed scrapes fall back to the Tavily snippet with no hard failure.

**Tech Stack:** `firecrawl-py` SDK, `concurrent.futures.ThreadPoolExecutor`, `unittest.mock.patch`, `uv` for package management.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/osint_search.py` | Modify | Prereq: add `score` field to `search_tavily` return |
| `data/mock_osint_fixtures/firecrawl_apac.json` | Create | Mock fixtures for APAC scrapes |
| `data/mock_osint_fixtures/firecrawl_ame.json` | Create | Mock fixtures for AME scrapes |
| `data/mock_osint_fixtures/firecrawl_latam.json` | Create | Mock fixtures for LATAM scrapes |
| `data/mock_osint_fixtures/firecrawl_med.json` | Create | Mock fixtures for MED scrapes |
| `data/mock_osint_fixtures/firecrawl_nce.json` | Create | Mock fixtures for NCE scrapes |
| `data/mock_osint_fixtures/firecrawl_vacr.json` | Create | Mock fixtures for VaCR researcher scrapes |
| `tools/firecrawl_scraper.py` | Create | Scraper wrapper: retry, truncation, concurrency, mock dispatch |
| `tests/test_firecrawl_scraper.py` | Create | Unit tests for the scraper wrapper |
| `tools/osint_collector.py` | Modify | Add scrape stage in `run_live_mode`; add `source_note` param to `synthesize_signals` |
| `tools/vacr_researcher.py` | Modify | Add scrape call in `research_scenario` after `_search_web` |
| `tools/validate_env.py` | Modify | Add optional `FIRECRAWL_API_KEY` check in live mode |
| `.env.example` | Modify | Document `FIRECRAWL_API_KEY` |

---

## Task 1: Prereq — add Tavily score to `osint_search.py`

**Files:**
- Modify: `tools/osint_search.py:122-130`

`search_tavily` currently strips the `score` field Tavily returns. Without it, "top N by relevance" is undefined. This is an isolated one-line fix that must land before any Firecrawl URL selection.

- [ ] **Step 1: Add `score` to the return dict**

In `tools/osint_search.py`, change the list comprehension in `search_tavily` (lines 122–130) from:

```python
        return [
            {
                "title": r.get("title", ""),
                "summary": r.get("content", ""),
                "url": r.get("url", ""),
                "published_date": r.get("published_date", ""),
            }
            for r in data.get("results", [])
        ]
```

to:

```python
        return [
            {
                "title": r.get("title", ""),
                "summary": r.get("content", ""),
                "url": r.get("url", ""),
                "published_date": r.get("published_date", ""),
                "score": r.get("score", 0.0),
            }
            for r in data.get("results", [])
        ]
```

- [ ] **Step 2: Verify DDG return is score-free (expected)**

`search_ddg` returns results without a score field — that's intentional. The `score_lookup.get(url, 0.0)` default in downstream code handles missing scores gracefully. No change needed there.

- [ ] **Step 3: Commit**

```bash
git add tools/osint_search.py
git commit -m "feat: preserve Tavily score field in search_tavily return"
```

---

## Task 2: Create mock Firecrawl fixtures

**Files:**
- Create: `data/mock_osint_fixtures/firecrawl_apac.json`
- Create: `data/mock_osint_fixtures/firecrawl_ame.json`
- Create: `data/mock_osint_fixtures/firecrawl_latam.json`
- Create: `data/mock_osint_fixtures/firecrawl_med.json`
- Create: `data/mock_osint_fixtures/firecrawl_nce.json`
- Create: `data/mock_osint_fixtures/firecrawl_vacr.json`

Each fixture maps URL → `{markdown, title, status}`. Include one `"ok"` entry, one `"failed"` entry (exercises fallback path), and one paywalled entry. Unknown URLs get a synthetic snippet placeholder at runtime — no need to enumerate every possible URL.

- [ ] **Step 1: Create `data/mock_osint_fixtures/firecrawl_apac.json`**

```json
{
  "https://www.reuters.com/article/apac-wind-energy-cyber": {
    "markdown": "# APAC Wind Energy Cyber Threat Report\n\nState-sponsored threat actors operating from China have intensified targeting of renewable energy infrastructure across the Asia-Pacific region. The VOLT TYPHOON campaign, documented by CISA in early 2025, targeted operational technology networks in Australian wind farm operators.\n\nKey findings:\n- 14 confirmed intrusions into SCADA systems managing wind turbine arrays\n- Exfiltration of grid synchronisation protocols\n- Persistent access maintained for an average of 47 days before detection\n\nThe Australian Cyber Security Centre (ACSC) has issued advisory ASD-2025-0021 recommending immediate network segmentation between IT and OT environments.",
    "title": "APAC Wind Energy Under Sustained Cyber Campaign",
    "status": "ok"
  },
  "https://www.paywall-journal.com/restricted-article": {
    "markdown": "",
    "title": "",
    "status": "failed"
  },
  "https://www.scada-security.org/apac-ot-threats-2025": {
    "markdown": "# OT Security in APAC Renewable Energy Sector\n\nThe proliferation of internet-connected wind turbine management systems has expanded the attack surface for threat actors targeting critical infrastructure. Recent analysis of 200 wind farm operators across APAC reveals that 67% use legacy SCADA systems with unpatched vulnerabilities.\n\nNotable incidents Q1 2025:\n- March: Unnamed Australian operator reported ransomware deployment in business IT network with attempted lateral movement to OT\n- February: South Korean wind farm control systems accessed via VPN credential stuffing\n\nRecommendations focus on zero-trust architecture and OT-specific EDR deployment.",
    "title": "OT Threat Landscape: APAC Renewable Energy 2025",
    "status": "ok"
  }
}
```

- [ ] **Step 2: Create `data/mock_osint_fixtures/firecrawl_ame.json`**

```json
{
  "https://www.cisa.gov/news-events/cybersecurity-advisories/aa25-ame-wind": {
    "markdown": "# CISA Advisory: Threat to Wind Energy Operators in Americas Region\n\nCISA, in coordination with FBI and NSA, is releasing this advisory to warn operators of wind energy infrastructure of increased threat actor interest in ICS/SCADA systems.\n\nThe advisory covers threat actor TTPs observed targeting US and Canadian wind farm operators:\n- Spearphishing campaigns targeting engineering staff with turbine management credentials\n- Exploitation of CVE-2024-38819 in Siemens SIMATIC WinCC OA\n- Deployment of custom malware on historian servers\n\nAffected sectors: Wind energy generation, Grid interconnection operators",
    "title": "CISA Advisory AA25-AME: Wind Energy ICS Threats",
    "status": "ok"
  },
  "https://www.paywalled-energy-report.com/ame-cyber-2025": {
    "markdown": "",
    "title": "",
    "status": "failed"
  },
  "https://www.e-isac.com/ame-wind-threat-brief-q1-2025": {
    "markdown": "# E-ISAC Wind Energy Threat Brief Q1 2025\n\nElectricity Information Sharing and Analysis Center threat brief for wind energy operators in the Americas region.\n\nThreat landscape summary:\n- Ransomware targeting business IT with increasing attempts to pivot to OT\n- Nation-state pre-positioning activity detected in 3 US wind operators\n- Supply chain risk: compromised firmware update mechanism in third-party SCADA vendor\n\nVaCR benchmark: Average incident cost for system intrusion in energy sector: $4.5M (IBM X-Force 2024).",
    "title": "E-ISAC AME Wind Energy Threat Brief Q1 2025",
    "status": "ok"
  }
}
```

- [ ] **Step 3: Create `data/mock_osint_fixtures/firecrawl_latam.json`**

```json
{
  "https://www.latam-energy-news.com/wind-cyber-threat-2025": {
    "markdown": "# Latin America Wind Energy Sector Cyber Threats 2025\n\nThe rapid expansion of wind energy capacity across Brazil, Mexico, and Chile has attracted threat actor attention to the sector. Limited cybersecurity maturity among regional operators increases risk exposure.\n\nKey observations:\n- Brazilian wind farm operators report 340% increase in phishing attempts targeting OT credentials (CERT.br, Q1 2025)\n- Mexican grid operator CFE issued internal advisory on APT targeting\n- Chilean operator Enel Green Power reported network intrusion attempt, successfully contained\n\nRegulatory context: Brazil ANEEL cybersecurity requirements effective June 2025.",
    "title": "LATAM Wind Energy Cyber Threat Landscape 2025",
    "status": "ok"
  },
  "https://www.restricted-latam-report.com/2025": {
    "markdown": "",
    "title": "",
    "status": "failed"
  }
}
```

- [ ] **Step 4: Create `data/mock_osint_fixtures/firecrawl_med.json`**

```json
{
  "https://www.enisa.europa.eu/med-energy-cyber-2025": {
    "markdown": "# ENISA: Mediterranean Energy Sector Cyber Threat Landscape 2025\n\nThe European Union Agency for Cybersecurity (ENISA) has published its threat landscape assessment for the Mediterranean energy sector, covering operators in Spain, Italy, Greece, Turkey, and North Africa.\n\nKey findings:\n- Russian-aligned threat actors (Sandworm, Gamaredon) maintain targeting interest in Southern European energy infrastructure\n- Wind energy OT networks in Spain and Italy targeted via exposed Modbus/TCP interfaces\n- Supply chain: 3 incidents involving compromised industrial control system software updates\n\nNIS2 directive implications: Wind energy operators with >50 employees now classified as 'essential entities' subject to mandatory incident reporting within 24 hours.",
    "title": "ENISA Mediterranean Energy Cyber Threat Landscape 2025",
    "status": "ok"
  },
  "https://www.paywalled-med-security.com/wind-2025": {
    "markdown": "",
    "title": "",
    "status": "failed"
  }
}
```

- [ ] **Step 5: Create `data/mock_osint_fixtures/firecrawl_nce.json`**

```json
{
  "https://www.ncsc.gov.uk/news/nce-wind-energy-advisory-2025": {
    "markdown": "# NCSC Advisory: Threats to Northern/Central European Wind Energy Operators\n\nThe National Cyber Security Centre, in cooperation with BSI (Germany), NCSC-NL, and the Danish Centre for Cyber Security, is issuing this advisory to Northern and Central European wind energy operators.\n\nThe advisory addresses sustained threat actor interest in the North Sea offshore wind corridor, which now supplies approximately 18% of regional electricity demand.\n\nThreat actor activity:\n- Russian GRU-affiliated actors (APT28/Fancy Bear) scanning OT-exposed endpoints in Danish and German offshore wind operators\n- Persistent access maintained in 2 unnamed Northern European energy companies\n- Hacktivism: pro-Russian groups conducted DDoS against wind operator customer portals\n\nRecommended actions: Air-gap OT networks, disable direct internet connectivity on turbine management systems.",
    "title": "NCSC Advisory: NCE Wind Energy Threat Landscape 2025",
    "status": "ok"
  },
  "https://www.bsi.bund.de/nce-energy-restricted": {
    "markdown": "",
    "title": "",
    "status": "failed"
  }
}
```

- [ ] **Step 6: Create `data/mock_osint_fixtures/firecrawl_vacr.json`**

```json
{
  "https://www.ibm.com/reports/data-breach-2024": {
    "markdown": "# IBM Cost of a Data Breach Report 2024\n\nThe average cost of a data breach reached $4.88 million in 2024, a 10% increase over the prior year and the highest total ever recorded.\n\nBy industry sector:\n- Energy and utilities: $5.29 million average breach cost (highest across sectors)\n- Manufacturing: $4.73 million\n- Healthcare: $9.77 million\n\nBy incident type:\n- System intrusion: $4.62 million median\n- Ransomware: $5.13 million median (excluding ransom payment)\n- Accidental disclosure: $3.17 million median\n\nGeographic breakdown for energy sector:\n- North America: $6.21 million\n- Europe: $4.84 million\n- Asia-Pacific: $3.98 million\n\nRaw quote: 'Energy sector breaches cost an average of $5.29 million in 2024, reflecting the high operational and regulatory costs associated with critical infrastructure incidents.'",
    "title": "IBM Cost of a Data Breach Report 2024",
    "status": "ok"
  },
  "https://www.verizon.com/business/resources/reports/dbir/2024": {
    "markdown": "# Verizon 2024 Data Breach Investigations Report\n\nThe 2024 DBIR analyzed 30,458 security incidents and 10,626 confirmed data breaches across 94 countries.\n\nKey findings for the energy sector:\n- System intrusion pattern accounts for 72% of energy sector breaches\n- Median financial impact of system intrusion: $46,000 (25th percentile) to $4.2M (75th percentile)\n- Ransomware present in 32% of energy sector breaches\n- OT-targeting incidents up 87% year-over-year\n\nRaw quote: 'In the energy sector, system intrusion incidents have a median financial impact of $1.4M, with 25% of incidents exceeding $4.2M in total losses including downtime, remediation, and regulatory penalties.'",
    "title": "Verizon 2024 Data Breach Investigations Report",
    "status": "ok"
  },
  "https://www.mandiant.com/resources/reports/restricted-2025": {
    "markdown": "",
    "title": "",
    "status": "failed"
  }
}
```

- [ ] **Step 7: Commit**

```bash
git add data/mock_osint_fixtures/firecrawl_apac.json \
        data/mock_osint_fixtures/firecrawl_ame.json \
        data/mock_osint_fixtures/firecrawl_latam.json \
        data/mock_osint_fixtures/firecrawl_med.json \
        data/mock_osint_fixtures/firecrawl_nce.json \
        data/mock_osint_fixtures/firecrawl_vacr.json
git commit -m "feat: add Firecrawl mock fixtures for all regions and VaCR"
```

---

## Task 3: Scaffold `firecrawl_scraper.py` — truncation + `ScrapedItem`

**Files:**
- Create: `tools/firecrawl_scraper.py`
- Create: `tests/test_firecrawl_scraper.py`

Write the failing truncation tests first, then implement the module scaffold with `ScrapedItem` and `_truncate`.

- [ ] **Step 1: Create `tests/test_firecrawl_scraper.py` with truncation tests**

```python
"""Unit tests for tools/firecrawl_scraper.py."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import firecrawl_scraper
from firecrawl_scraper import scrape_urls, _truncate


class TestTruncate(unittest.TestCase):
    def test_short_content_unchanged(self):
        text = "hello world"
        assert _truncate(text) == text

    def test_exactly_at_limit_unchanged(self):
        text = "x" * 12_000
        assert _truncate(text) == text

    def test_long_content_middle_truncated(self):
        # 12,200 chars: first 6100 'A', last 6100 'B'
        text = "A" * 6_100 + "B" * 6_100
        result = _truncate(text)
        assert "[…truncated…]" in result
        # Head preserved
        assert result.startswith("A" * 6_000)
        # Tail preserved
        assert result.endswith("B" * 6_000)
        # Total shorter than input
        assert len(result) < len(text)

    def test_truncation_marker_appears_once(self):
        text = "Z" * 20_000
        result = _truncate(text)
        assert result.count("[…truncated…]") == 1


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
uv run pytest tests/test_firecrawl_scraper.py -v
```

Expected: `ModuleNotFoundError: No module named 'firecrawl_scraper'`

- [ ] **Step 3: Create `tools/firecrawl_scraper.py` scaffold with `_truncate` and `ScrapedItem`**

```python
#!/usr/bin/env python3
"""Firecrawl scraper — depth layer for OSINT collection.

Wraps Firecrawl /scrape. Returns one ScrapedItem per input URL — always.
Failed scrapes fall back to the Tavily snippet tagged source_type: "snippet".

Public interface:
    scrape_urls(urls, tavily_snippets, tavily_scores, region=None) -> list[ScrapedItem]
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

_MAX_CHARS = 12_000
_HEAD_CHARS = 6_000
_TAIL_CHARS = 6_000
_TRUNCATION_MARKER = "\n\n[…truncated…]\n\n"
_TIMEOUT_MS = 30_000   # Firecrawl expects milliseconds
_MAX_WORKERS = 5

_REPO_ROOT = Path(__file__).resolve().parent.parent


class ScrapedItem(TypedDict):
    url: str
    title: str
    source_type: str        # "fulltext" | "snippet"
    content: str
    tavily_score: float


def _truncate(text: str) -> str:
    """Middle-truncate text longer than _MAX_CHARS characters."""
    if len(text) <= _MAX_CHARS:
        return text
    return text[:_HEAD_CHARS] + _TRUNCATION_MARKER + text[-_TAIL_CHARS:]


def _load_mock_fixture(region: str) -> dict:
    """Load Firecrawl mock fixture for a region key (e.g. 'apac', 'vacr')."""
    import json
    fixture_path = _REPO_ROOT / "data" / "mock_osint_fixtures" / f"firecrawl_{region.lower()}.json"
    try:
        return json.loads(fixture_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("[firecrawl_scraper] no fixture at %s", fixture_path)
        return {}


def _scrape_one_mock(
    url: str,
    fixture: dict,
    tavily_snippet: str,
    tavily_score: float,
) -> ScrapedItem:
    entry = fixture.get(url)
    if entry is None:
        return ScrapedItem(
            url=url, title="", source_type="snippet",
            content=tavily_snippet, tavily_score=tavily_score,
        )
    if entry.get("status") == "failed" or not (entry.get("markdown") or "").strip():
        return ScrapedItem(
            url=url, title=entry.get("title", ""), source_type="snippet",
            content=tavily_snippet, tavily_score=tavily_score,
        )
    return ScrapedItem(
        url=url,
        title=entry.get("title", ""),
        source_type="fulltext",
        content=_truncate(entry["markdown"]),
        tavily_score=tavily_score,
    )


def _call_firecrawl(url: str, api_key: str) -> tuple[str, str] | None:
    """One Firecrawl HTTP call. Returns (markdown, title) or None on any failure."""
    try:
        from firecrawl import FirecrawlApp
    except ImportError as exc:
        raise ImportError("firecrawl-py not installed. Run: uv add firecrawl-py") from exc
    try:
        app = FirecrawlApp(api_key=api_key)
        result = app.scrape_url(
            url,
            params={
                "onlyMainContent": True,
                "formats": ["markdown"],
                "timeout": _TIMEOUT_MS,
            },
        )
        markdown = (result.get("markdown") or "").strip()
        if not markdown:
            return None
        title = (result.get("metadata") or {}).get("title", "")
        return markdown, title
    except Exception as exc:
        logger.warning("[firecrawl_scraper] scrape failed for %s: %s", url, exc)
        return None


def _scrape_one_live(
    url: str,
    api_key: str,
    tavily_snippet: str,
    tavily_score: float,
) -> ScrapedItem:
    """Scrape once, retry once on failure, fall back to snippet."""
    result = _call_firecrawl(url, api_key)
    if result is None:
        logger.warning("[firecrawl_scraper] retry for %s", url)
        result = _call_firecrawl(url, api_key)
    if result is None:
        logger.warning("[firecrawl_scraper] falling back to snippet for %s", url)
        return ScrapedItem(
            url=url, title="", source_type="snippet",
            content=tavily_snippet, tavily_score=tavily_score,
        )
    markdown, title = result
    return ScrapedItem(
        url=url, title=title, source_type="fulltext",
        content=_truncate(markdown), tavily_score=tavily_score,
    )


def scrape_urls(
    urls: list[str],
    tavily_snippets: dict[str, str],
    tavily_scores: dict[str, float],
    region: str | None = None,
) -> list[ScrapedItem]:
    """Scrape a list of URLs. Returns one ScrapedItem per input URL — always.

    Mock mode (OSINT_MOCK=1): reads fixtures from data/mock_osint_fixtures/.
    Live mode: calls Firecrawl /scrape concurrently via ThreadPoolExecutor.

    Args:
        urls: URLs to scrape, in priority order.
        tavily_snippets: url → snippet, used as fallback content on failure.
        tavily_scores: url → Tavily relevance score, stored on ScrapedItem.
        region: Region key for fixture lookup ("apac", "ame", etc.) or None for VaCR.
    """
    if not urls:
        return []

    use_mock = os.environ.get("OSINT_MOCK", "").strip().lower() in ("1", "true")

    if use_mock:
        fixture = _load_mock_fixture(region or "vacr")
        return [
            _scrape_one_mock(
                url,
                fixture,
                tavily_snippets.get(url, ""),
                tavily_scores.get(url, 0.0),
            )
            for url in urls
        ]

    api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError(
            "FIRECRAWL_API_KEY is not set. "
            "Set it in .env or pass --mock to use fixture mode."
        )

    results: dict[str, ScrapedItem] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {
            pool.submit(
                _scrape_one_live,
                url,
                api_key,
                tavily_snippets.get(url, ""),
                tavily_scores.get(url, 0.0),
            ): url
            for url in urls
        }
        for future in as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception as exc:
                logger.warning("[firecrawl_scraper] unexpected future error for %s: %s", url, exc)
                results[url] = ScrapedItem(
                    url=url, title="", source_type="snippet",
                    content=tavily_snippets.get(url, ""),
                    tavily_score=tavily_scores.get(url, 0.0),
                )

    return [results[url] for url in urls]   # restore input order
```

- [ ] **Step 4: Run truncation tests — confirm they pass**

```bash
uv run pytest tests/test_firecrawl_scraper.py::TestTruncate -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add tools/firecrawl_scraper.py tests/test_firecrawl_scraper.py
git commit -m "feat: scaffold firecrawl_scraper.py with ScrapedItem and truncation"
```

---

## Task 4: TDD — mock mode dispatch

**Files:**
- Modify: `tests/test_firecrawl_scraper.py`

- [ ] **Step 1: Add mock mode tests to `tests/test_firecrawl_scraper.py`**

Add this class after `TestTruncate`:

```python
class TestMockMode(unittest.TestCase):
    def setUp(self):
        os.environ["OSINT_MOCK"] = "1"

    def tearDown(self):
        os.environ.pop("OSINT_MOCK", None)

    def test_happy_path_returns_fulltext(self):
        fixture = {
            "https://example.com/article": {
                "markdown": "Full article text about wind energy threats",
                "title": "Wind Energy Threat Report",
                "status": "ok",
            }
        }
        with patch.object(firecrawl_scraper, "_load_mock_fixture", return_value=fixture):
            result = scrape_urls(
                ["https://example.com/article"],
                {"https://example.com/article": "short snippet"},
                {"https://example.com/article": 0.9},
                region="apac",
            )
        assert len(result) == 1
        assert result[0]["source_type"] == "fulltext"
        assert result[0]["content"] == "Full article text about wind energy threats"
        assert result[0]["title"] == "Wind Energy Threat Report"
        assert result[0]["tavily_score"] == 0.9
        assert result[0]["url"] == "https://example.com/article"

    def test_failed_fixture_falls_back_to_snippet(self):
        fixture = {
            "https://example.com/paywalled": {
                "markdown": "",
                "title": "Paywalled Article",
                "status": "failed",
            }
        }
        with patch.object(firecrawl_scraper, "_load_mock_fixture", return_value=fixture):
            result = scrape_urls(
                ["https://example.com/paywalled"],
                {"https://example.com/paywalled": "tavily snippet text"},
                {"https://example.com/paywalled": 0.5},
            )
        assert result[0]["source_type"] == "snippet"
        assert result[0]["content"] == "tavily snippet text"

    def test_unknown_url_returns_snippet_placeholder(self):
        with patch.object(firecrawl_scraper, "_load_mock_fixture", return_value={}):
            result = scrape_urls(
                ["https://unknown.com/article"],
                {"https://unknown.com/article": "fallback snippet"},
                {"https://unknown.com/article": 0.3},
            )
        assert result[0]["source_type"] == "snippet"
        assert result[0]["content"] == "fallback snippet"

    def test_empty_url_list_returns_empty(self):
        result = scrape_urls([], {}, {}, region="apac")
        assert result == []

    def test_input_order_preserved_in_mock(self):
        fixture = {f"https://example.com/{i}": {"markdown": f"content {i}", "title": f"T{i}", "status": "ok"}
                   for i in range(5)}
        urls = [f"https://example.com/{i}" for i in range(5)]
        with patch.object(firecrawl_scraper, "_load_mock_fixture", return_value=fixture):
            result = scrape_urls(urls, {u: "" for u in urls}, {u: 0.5 for u in urls})
        assert [r["url"] for r in result] == urls
```

- [ ] **Step 2: Run mock tests — confirm they pass**

```bash
uv run pytest tests/test_firecrawl_scraper.py::TestMockMode -v
```

Expected: 5 PASSED

- [ ] **Step 3: Commit**

```bash
git add tests/test_firecrawl_scraper.py
git commit -m "test: add mock mode tests for firecrawl_scraper"
```

---

## Task 5: TDD — live mode validation (missing API key)

**Files:**
- Modify: `tests/test_firecrawl_scraper.py`

- [ ] **Step 1: Add missing key test**

Add this class after `TestMockMode`:

```python
class TestLiveModeValidation(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OSINT_MOCK", None)
        os.environ.pop("FIRECRAWL_API_KEY", None)

    def test_missing_api_key_raises_environment_error(self):
        with self.assertRaises(EnvironmentError) as ctx:
            scrape_urls(
                ["https://example.com"],
                {"https://example.com": "snippet"},
                {"https://example.com": 0.8},
            )
        assert "FIRECRAWL_API_KEY" in str(ctx.exception)

    def test_empty_url_list_does_not_require_key(self):
        # Empty list short-circuits before key check
        result = scrape_urls([], {}, {})
        assert result == []
```

- [ ] **Step 2: Run validation tests**

```bash
uv run pytest tests/test_firecrawl_scraper.py::TestLiveModeValidation -v
```

Expected: 2 PASSED

- [ ] **Step 3: Commit**

```bash
git add tests/test_firecrawl_scraper.py
git commit -m "test: add live mode API key validation tests"
```

---

## Task 6: TDD — retry-once-then-succeed and retry-once-then-fallback

**Files:**
- Modify: `tests/test_firecrawl_scraper.py`

These tests patch `firecrawl_scraper._call_firecrawl` directly — the retry orchestration lives in `_scrape_one_live`, which is called by `scrape_urls` in live mode.

- [ ] **Step 1: Add retry tests**

Add this class after `TestLiveModeValidation`:

```python
class TestRetryLogic(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OSINT_MOCK", None)
        os.environ["FIRECRAWL_API_KEY"] = "test-key"

    def tearDown(self):
        os.environ.pop("FIRECRAWL_API_KEY", None)

    def test_retry_once_then_succeed(self):
        # First call returns None (failure), second returns content
        side_effects = [None, ("Full article markdown", "Article Title")]
        with patch("firecrawl_scraper._call_firecrawl", side_effect=side_effects) as mock_call:
            result = scrape_urls(
                ["https://example.com"],
                {"https://example.com": "snippet"},
                {"https://example.com": 0.8},
            )
        assert result[0]["source_type"] == "fulltext"
        assert result[0]["content"] == "Full article markdown"
        assert result[0]["title"] == "Article Title"
        assert mock_call.call_count == 2

    def test_retry_twice_then_fallback_to_snippet(self):
        # Both calls return None → snippet fallback
        with patch("firecrawl_scraper._call_firecrawl", return_value=None) as mock_call:
            result = scrape_urls(
                ["https://example.com"],
                {"https://example.com": "tavily snippet fallback"},
                {"https://example.com": 0.7},
            )
        assert result[0]["source_type"] == "snippet"
        assert result[0]["content"] == "tavily snippet fallback"
        assert mock_call.call_count == 2

    def test_successful_first_attempt_no_retry(self):
        with patch("firecrawl_scraper._call_firecrawl", return_value=("content", "title")) as mock_call:
            result = scrape_urls(
                ["https://example.com"],
                {"https://example.com": "snippet"},
                {"https://example.com": 0.9},
            )
        assert result[0]["source_type"] == "fulltext"
        assert mock_call.call_count == 1

    def test_input_order_preserved_with_concurrency(self):
        urls = [f"https://example.com/{i}" for i in range(5)]
        def fake_call(url, api_key):
            return (f"content for {url}", f"title {url}")
        with patch("firecrawl_scraper._call_firecrawl", side_effect=fake_call):
            result = scrape_urls(
                urls,
                {u: "" for u in urls},
                {u: 0.5 for u in urls},
            )
        assert [r["url"] for r in result] == urls

    def test_all_urls_scraped_concurrently_preserve_order(self):
        # Verify that even if futures complete out of order, result matches input order
        import time, random
        urls = [f"https://example.com/{i}" for i in range(5)]
        def fake_call(url, api_key):
            time.sleep(random.uniform(0, 0.01))
            return (f"content for {url}", "title")
        with patch("firecrawl_scraper._call_firecrawl", side_effect=fake_call):
            result = scrape_urls(
                urls,
                {u: "" for u in urls},
                {u: float(i) for i, u in enumerate(urls)},
            )
        for i, (url, item) in enumerate(zip(urls, result)):
            assert item["url"] == url, f"Position {i}: expected {url}, got {item['url']}"
```

- [ ] **Step 2: Run retry tests**

```bash
uv run pytest tests/test_firecrawl_scraper.py::TestRetryLogic -v
```

Expected: 5 PASSED

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
uv run pytest tests/test_firecrawl_scraper.py -v
```

Expected: All PASSED (12 tests)

- [ ] **Step 4: Commit**

```bash
git add tests/test_firecrawl_scraper.py
git commit -m "test: add retry logic and concurrency ordering tests for firecrawl_scraper"
```

---

## Task 7: Install `firecrawl-py` dependency

**Files:**
- Modify: `pyproject.toml` (or `requirements.txt` — whichever manages deps in this project)

- [ ] **Step 1: Check which file manages dependencies**

```bash
ls pyproject.toml requirements*.txt 2>/dev/null
```

- [ ] **Step 2a: If `pyproject.toml` exists, add with uv**

```bash
uv add firecrawl-py
```

- [ ] **Step 2b: If `requirements.txt` exists, append**

```bash
echo "firecrawl-py>=1.0.0" >> requirements.txt
uv pip install firecrawl-py
```

- [ ] **Step 3: Verify import works**

```bash
uv run python -c "from firecrawl import FirecrawlApp; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml  # or requirements.txt
git commit -m "chore: add firecrawl-py dependency"
```

---

## Task 8: Wire into `osint_collector.py`

**Files:**
- Modify: `tools/osint_collector.py:252-340` (`synthesize_signals`)
- Modify: `tools/osint_collector.py:372-467` (`run_live_mode`)

Two changes: (1) add optional `source_note` param to `synthesize_signals` so the prompt can flag fulltext vs snippet items; (2) add the scrape stage in `run_live_mode` between gap-fill and synthesis.

- [ ] **Step 1: Add `source_note` parameter to `synthesize_signals`**

Change the function signature at line 252 from:

```python
def synthesize_signals(
    region: str, working_theory: dict, results: list[dict]
) -> tuple[dict, dict, dict]:
```

to:

```python
def synthesize_signals(
    region: str, working_theory: dict, results: list[dict], source_note: str = ""
) -> tuple[dict, dict, dict]:
```

Then, in the prompt string inside `synthesize_signals`, add the note before `COLLECTED EVIDENCE`. Change:

```python
    prompt = f"""You are synthesizing OSINT collection into structured intelligence signals.

REGION: {region}
WORKING THEORY: {working_theory['hypothesis']}
SCENARIO: {working_theory['scenario_name']} (${working_theory['vacr_usd']:,})
ACTIVE TOPICS: {json.dumps(topic_ids)}

COLLECTED EVIDENCE ({len(results)} results):
{snippets_text}
```

to:

```python
    _source_note_block = f"SOURCE NOTE: {source_note}\n\n" if source_note else ""
    prompt = f"""You are synthesizing OSINT collection into structured intelligence signals.

REGION: {region}
WORKING THEORY: {working_theory['hypothesis']}
SCENARIO: {working_theory['scenario_name']} (${working_theory['vacr_usd']:,})
ACTIVE TOPICS: {json.dumps(topic_ids)}

{_source_note_block}COLLECTED EVIDENCE ({len(results)} results):
{snippets_text}
```

- [ ] **Step 2: Run existing tests to confirm signature change is non-breaking**

```bash
uv run pytest tests/ -v -k "not firecrawl"
```

Expected: all existing tests PASSED (the new param has a default, so existing callers are unaffected).

- [ ] **Step 3: Add the scrape stage to `run_live_mode`**

In `tools/osint_collector.py`, find the line:

```python
    # --- LLM Call 3: Synthesize (Sonnet) ---
    geo_signals, cyber_signals, conclusion = synthesize_signals(region, working_theory, all_results)
```

Replace it with:

```python
    # --- Firecrawl deep extraction ---
    from tools.firecrawl_scraper import scrape_urls as _firecrawl_scrape

    # Build URL pool: junk-filtered, deduplicated, sorted by Tavily score
    _score_lookup: dict[str, float] = {r["url"]: r.get("score", 0.0) for r in all_results if r.get("url")}
    _seen_fc: set[str] = set()
    _candidate_urls: list[str] = []
    for r in all_results:
        u = r.get("url", "")
        if u and u not in _seen_fc and not _is_junk_url(u):
            _seen_fc.add(u)
            _candidate_urls.append(u)

    top5_urls = sorted(_candidate_urls, key=lambda u: _score_lookup.get(u, 0.0), reverse=True)[:5]
    _snippet_lookup: dict[str, str] = {r["url"]: r.get("summary", "") for r in all_results if r.get("url")}

    scraped_items = _firecrawl_scrape(top5_urls, _snippet_lookup, _score_lookup, region)

    # Adapt ScrapedItems for synthesize_signals: source_type tag injected into summary
    synthesis_inputs = [
        {
            "title": s["title"],
            "url": s["url"],
            "summary": f"[{s['source_type']}] {s['content']}",
            "published_date": "",
        }
        for s in scraped_items
    ]

    # Track Firecrawl stats for scratchpad
    _fc_succeeded = sum(1 for s in scraped_items if s["source_type"] == "fulltext")
    _fc_stats = {
        "attempted": len(scraped_items),
        "succeeded": _fc_succeeded,
        "fell_back": len(scraped_items) - _fc_succeeded,
    }

    # --- LLM Call 3: Synthesize (Sonnet) ---
    geo_signals, cyber_signals, conclusion = synthesize_signals(
        region,
        working_theory,
        synthesis_inputs,
        source_note=(
            "Items labeled [fulltext] are main-content extracts up to ~3k tokens. "
            "Items labeled [snippet] are 200-char previews. "
            "Weight fulltext primary sources more heavily when both are available."
        ),
    )
```

- [ ] **Step 4: Add `firecrawl_stats` to the scratchpad write**

Find the `scratchpad` dict construction (around line 452). Inside the `"collection"` sub-dict, add `"firecrawl_stats": _fc_stats`:

```python
    scratchpad = {
        "region": region,
        "collected_at": collected_at,
        "working_theory": working_theory,
        "collection": {
            "pass_1_result_count": len(pass_1_results),
            "gap_assessment": gap_data.get("gap_assessment", ""),
            "gaps_identified": gap_data.get("gaps_identified", []),
            "pass_2_queries": gap_data.get("follow_up_queries", []),
            "pass_2_result_count": len(pass_2_results),
            "total_result_count": len(all_results),
            "firecrawl_stats": _fc_stats,
        },
        "conclusion": conclusion,
    }
```

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all PASSED (Firecrawl mock mode active in test environment via `OSINT_MOCK=1` in test setUp).

- [ ] **Step 6: Commit**

```bash
git add tools/osint_collector.py
git commit -m "feat: wire Firecrawl scrape stage into osint_collector run_live_mode"
```

---

## Task 9: Wire into `vacr_researcher.py`

**Files:**
- Modify: `tools/vacr_researcher.py:169-203` (`research_scenario`)

The scrape call lives in `research_scenario` after `_search_web` returns, before `_extract_figures`. `_search_web` stays search-only. The DDG fallback path has no `score` field — the `if any(...)` guard skips scraping in that case, which is correct (can't sort blind).

- [ ] **Step 1: Add import and scrape call to `research_scenario`**

In `tools/vacr_researcher.py`, find the inner loop in `research_scenario` (around line 182):

```python
    all_figures = []
    for query in queries:
        print(f"[vacr-researcher]   Searching: {query[:80]}...", file=sys.stderr)
        results = _search_web(query, max_results=4)
        for r in results:
            content = r.get("content", "")
            source_name = r.get("title") or r.get("url", "Unknown")
            figures = _extract_figures(content, source_name)
```

Replace with:

```python
    from tools.firecrawl_scraper import scrape_urls as _firecrawl_scrape

    all_figures = []
    for query in queries:
        print(f"[vacr-researcher]   Searching: {query[:80]}...", file=sys.stderr)
        results = _search_web(query, max_results=4)

        # Scrape top 3 by Tavily score if scores are available (Tavily path)
        if results and any(r.get("score") for r in results):
            top3 = sorted(results, key=lambda r: r.get("score", 0.0), reverse=True)[:3]
            snippet_lookup = {r["url"]: r.get("content", "") for r in top3}
            score_lookup = {r["url"]: r.get("score", 0.0) for r in top3}
            scraped = _firecrawl_scrape(
                [r["url"] for r in top3],
                snippet_lookup,
                score_lookup,
            )
            for r, s in zip(top3, scraped):
                r["content"] = s["content"]

        for r in results:
            content = r.get("content", "")
            source_name = r.get("title") or r.get("url", "Unknown")
            figures = _extract_figures(content, source_name)
```

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all PASSED

- [ ] **Step 3: Commit**

```bash
git add tools/vacr_researcher.py
git commit -m "feat: wire Firecrawl scrape into vacr_researcher research_scenario"
```

---

## Task 10: `validate_env.py` + `.env.example`

**Files:**
- Modify: `tools/validate_env.py`
- Modify: `.env.example`

- [ ] **Step 1: Add Firecrawl key check to `validate_env.py`**

In `tools/validate_env.py`, inside the `if live:` block, after the Tavily key check, add:

```python
    if live:
        # Tavily is optional — DDG fallback available
        check("TAVILY_API_KEY", required=False,
              hint="Optional — Tavily gives higher quality results. "
                   "Falling back to DuckDuckGo (free, no key).")

        # Firecrawl is optional — pipeline degrades to snippet-only synthesis if absent
        check("FIRECRAWL_API_KEY", required=False,
              hint="Optional — enables full-text article extraction for richer synthesis. "
                   "Without this key, synthesis uses Tavily snippets (~200 chars) only.")
```

- [ ] **Step 2: Add `FIRECRAWL_API_KEY` to `.env.example`**

After the `TAVILY_API_KEY` block, add:

```
# --- Live OSINT: Deep Article Extraction ---
# Firecrawl API (optional — enables full-text scraping of top Tavily results)
# Without this key, synthesis uses Tavily snippets (~200 chars) only.
# Sign up: https://firecrawl.dev
FIRECRAWL_API_KEY=
```

- [ ] **Step 3: Verify validate_env runs cleanly in mock mode**

```bash
uv run python tools/validate_env.py
```

Expected: `[validate_env] OK — environment valid for MOCK mode` (no Firecrawl check in mock mode)

- [ ] **Step 4: Commit**

```bash
git add tools/validate_env.py .env.example
git commit -m "feat: add optional FIRECRAWL_API_KEY check to validate_env and .env.example"
```

---

## Self-Review Checklist

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Preserve Tavily score in osint_search.py | Task 1 |
| New `tools/firecrawl_scraper.py` module | Task 3 |
| `scrape_urls(urls, snippets, scores, region)` signature | Task 3 |
| `ScrapedItem` TypedDict | Task 3 |
| `ThreadPoolExecutor(max_workers=5)` concurrency | Task 3 |
| Retry-once on failure | Task 3 (impl) + Task 6 (test) |
| Snippet fallback on final failure | Task 3 (impl) + Task 6 (test) |
| Char-based middle-truncation at 12k | Task 3 (impl) + Task 3 (test) |
| Mock mode via `OSINT_MOCK` env var | Task 3 (impl) + Task 4 (test) |
| Per-region fixture files (6 files) | Task 2 |
| Unknown URL → synthetic placeholder | Task 4 |
| Missing `FIRECRAWL_API_KEY` raises cleanly | Task 5 |
| Result order preserved across concurrent scrapes | Task 6 |
| Junk URL filter before scrape selection | Task 8 (uses `_is_junk_url`) |
| Top 5 by Tavily score | Task 8 |
| Scrape stage between gap-fill and synthesis | Task 8 |
| `source_note` injected into `synthesize_signals` | Task 8 |
| `firecrawl_stats` written to scratchpad | Task 8 |
| `vacr_researcher` scrapes top 3 per query | Task 9 |
| DDG fallback skips scraping gracefully | Task 9 |
| `FIRECRAWL_API_KEY` in `validate_env.py` | Task 10 |
| `FIRECRAWL_API_KEY` in `.env.example` | Task 10 |

All spec requirements are covered. No gaps found.

---

## Rollout (post-implementation)

After all tasks are committed and unit tests are green:

1. **Single-region live dry run** (requires `FIRECRAWL_API_KEY` in `.env`):

```bash
uv run python tools/osint_collector.py APAC
```

Check `output/regional/apac/osint_scratchpad.json` for `firecrawl_stats`. Inspect `osint_signals.json` for signal quality improvement.

2. **Full pipeline run** once dry run looks clean:

```bash
# via slash command
/run-crq
```

3. **Revert without code change**: unset `FIRECRAWL_API_KEY` in `.env` → pipeline degrades to snippet-only.
