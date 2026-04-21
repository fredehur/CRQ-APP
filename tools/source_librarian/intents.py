"""Intent yaml + publishers yaml loaders, with pydantic validation."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field


class ScenarioIntent(BaseModel):
    name: str
    threat_terms: list[str] = Field(min_length=1)
    asset_terms: list[str] = Field(min_length=1)
    industry_terms: list[str] = Field(min_length=1)
    time_focus_years: int = Field(ge=1, le=10)
    notes: str = ""


class Geography(BaseModel):
    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)


class QueryModifiers(BaseModel):
    news_set: list[str] = Field(min_length=1)
    doc_set: list[str] = Field(min_length=1)


class Intent(BaseModel):
    register_id: str
    register_name: str
    industry: str
    sub_industry: str
    geography: Geography
    scenarios: dict[str, ScenarioIntent]
    query_modifiers: QueryModifiers
    raw_yaml: str = ""  # populated by loader; not part of the source yaml shape


class SeedEntry(BaseModel):
    url: str
    title: str
    snippet: str = ""


class Publishers(BaseModel):
    """Prefix-matched URL → tier resolver."""
    t1: list[str] = Field(default_factory=list)
    t2: list[str] = Field(default_factory=list)
    t3: list[str] = Field(default_factory=list)
    seeded: list[SeedEntry] = Field(default_factory=list)

    def _normalized(self, url: str) -> str:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        path = parsed.path or ""
        return f"{host}{path}"

    def _matches(self, norm: str, prefix: str) -> bool:
        if "/" in prefix:
            # path-bearing prefix → must match exactly or at a path boundary
            return norm == prefix or norm.startswith(prefix + "/") or norm.startswith(prefix + "?")
        # bare host → first path segment must equal the prefix
        host_only = norm.split("/", 1)[0]
        return host_only == prefix

    def tier_for(self, url: str) -> Optional[str]:
        norm = self._normalized(url)
        for tier_name, entries in (("T1", self.t1), ("T2", self.t2), ("T3", self.t3)):
            for prefix in entries:
                if self._matches(norm, prefix):
                    return tier_name
        return None

    def publisher_for(self, url: str) -> Optional[str]:
        """Return the canonical publisher entry that matched, e.g. 'ibm.com/security'."""
        norm = self._normalized(url)
        for entries in (self.t1, self.t2, self.t3):
            for prefix in entries:
                if self._matches(norm, prefix):
                    return prefix
        return None


def load_intent_file(path: Path) -> Intent:
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return Intent.model_validate({**data, "raw_yaml": text})


def load_publishers_file(path: Path) -> Publishers:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    tiers = data.get("tiers", {})
    raw_seeded = data.get("seeded", []) or []
    seeded = [SeedEntry(**s) if isinstance(s, dict) else SeedEntry(url=s, title="") for s in raw_seeded]
    return Publishers(
        t1=list(tiers.get("T1") or []),
        t2=list(tiers.get("T2") or []),
        t3=list(tiers.get("T3") or []),
        seeded=seeded,
    )


REPO_ROOT = Path(__file__).resolve().parents[2]
INTENTS_DIR = REPO_ROOT / "data" / "research_intents"


def load_intent(register_id: str) -> Intent:
    # Re-read INTENTS_DIR at call time so monkeypatch in tests works
    from . import intents as _mod
    return load_intent_file(_mod.INTENTS_DIR / f"{register_id}.yaml")


def load_publishers() -> Publishers:
    from . import intents as _mod
    return load_publishers_file(_mod.INTENTS_DIR / "publishers.yaml")


def intent_hash_current(register_id: str) -> str:
    """Return the 8-char sha256 hash of the intent yaml currently on disk."""
    from . import intents as _mod
    from .snapshot import intent_hash
    path = _mod.INTENTS_DIR / f"{register_id}.yaml"
    return intent_hash(path.read_text(encoding="utf-8"))
