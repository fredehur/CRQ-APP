"""Tools for loading site and signal data from disk."""
from __future__ import annotations
import json
import types
from datetime import date
from pathlib import Path

from tools.briefs.models import (
    SiteContext,
    PhysicalSignal,
    CyberIndicator,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "data"
_OUTPUT_DIR = _REPO_ROOT / "output" / "regional"


def load_sites_for_region(region: str) -> list[SiteContext]:
    """Read aerowind_sites.json and return all sites for the given region."""
    path = _DATA_DIR / "aerowind_sites.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        SiteContext.model_validate(s)
        for s in raw["sites"]
        if s["region"].upper() == region.upper()
    ]


def load_physical_signals(region: str) -> list[PhysicalSignal]:
    """Read osint_physical_signals.json for the region. Returns [] if file missing."""
    path = _OUTPUT_DIR / region.lower() / "osint_physical_signals.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    signals = raw.get("signals", [])
    result = []
    for s in signals:
        try:
            result.append(PhysicalSignal.model_validate(s))
        except Exception:
            continue
    return result


def load_cyber_indicators(region: str) -> list[CyberIndicator]:
    """Read cyber_signals.json for the region. Returns [] if file missing."""
    path = _OUTPUT_DIR / region.lower() / "cyber_signals.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    indicators = raw.get("lead_indicators", [])
    result = []
    for ind in indicators:
        try:
            result.append(CyberIndicator.model_validate(ind))
        except Exception:
            continue
    return result


def load_calendar(region: str) -> list:
    """Build calendar items (duck-typed with .country/.date_str/.label) from notable_dates."""
    sites = load_sites_for_region(region)
    result = []
    seen = set()
    for site in sites:
        for nd in site.notable_dates:
            date_str = nd.get("date", "")
            label = nd.get("event", "")
            key = (date_str, label, site.country)
            if key in seen:
                continue
            seen.add(key)
            result.append(types.SimpleNamespace(
                country=site.country,
                date_str=date_str,
                label=label,
            ))
    return result
