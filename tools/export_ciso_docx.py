"""
tools/export_ciso_docx.py
Exports a CISO-grade weekly intelligence update as a Word (.docx) document.

Usage:
    uv run python tools/export_ciso_docx.py [output.docx]
    Defaults to output/ciso_brief.docx
"""
import sys
import os
import re
import json
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from report_builder import build, ReportData, RegionEntry, RegionStatus, _split_sentences
from tools.config import CISO_BRIEF_PATH

DEFAULT_OUT = str(CISO_BRIEF_PATH)
OUTPUT_DIR  = "output"

# ── Colours ────────────────────────────────────────────────────────────────────
NAVY  = RGBColor(0x1e, 0x3a, 0x5f)
RED   = RGBColor(0xdc, 0x26, 0x26)
AMBER = RGBColor(0xd9, 0x77, 0x06)
GREEN = RGBColor(0x16, 0xa3, 0x4a)
GREY  = RGBColor(0x6b, 0x72, 0x80)
BLACK = RGBColor(0x11, 0x11, 0x11)

# ── Region display names ───────────────────────────────────────────────────────
REGION_NAMES = {
    "AME":   "Americas, Europe & Middle East",
    "APAC":  "Asia-Pacific",
    "MED":   "Mediterranean",
    "NCE":   "Northern & Central Europe",
    "LATAM": "Latin America",
}

# ── Credibility tier inference ────────────────────────────────────────────────
_TIER_A_DOMAINS = (".gov", "enisa.europa.eu", "nist.gov", "cisa.gov",
                   "eur-lex.europa.eu", "nato.int", "un.org", "interpol.int")
_TIER_C_DOMAINS = ("youtube.com", "twitter.com", "reddit.com", "facebook.com")


def _infer_tier(url: str | None) -> str:
    """Return credibility tier A/B/C based on URL domain patterns."""
    if not url:
        return "B"
    low = url.lower()
    for domain in _TIER_A_DOMAINS:
        if domain in low:
            return "A"
    for domain in _TIER_C_DOMAINS:
        if domain in low:
            return "C"
    return "B"


# Sources to skip when building the reference list (generic collector labels)
_SKIP_SOURCES = {
    "tavily research", "cyber signal", "geo signal", "youtube signal",
    "research collection", "osint collection",
}
_SKIP_PREFIXES = ("cyber signal", "geo signal", "youtube signal", "tavily")

# Bracket patterns that are NOT citations
_NON_CITATION_RE = re.compile(r"^(ESCALATED|MONITOR|CLEAR|UNKNOWN)$")

# ── Source registry ────────────────────────────────────────────────────────────
class SourceRegistry:
    """Global numbered reference registry for in-text citations."""

    def __init__(self, url_map: dict[str, str] | None = None):
        self._refs: dict[str, dict] = {}
        self._counter = 0
        # name.lower() → url, populated from signal source files
        self._url_map: dict[str, str] = url_map or {}

    def _key(self, name: str) -> str:
        return name.strip().lower()

    def register(self, name: str, headline: str | None = None) -> int:
        k = self._key(name)
        if k not in self._refs:
            self._counter += 1
            self._refs[k] = {
                "num": self._counter,
                "name": name.strip(),
                "headline": headline or "",
                "url": self._url_map.get(k, ""),
            }
        else:
            if headline and not self._refs[k]["headline"]:
                self._refs[k]["headline"] = headline
            if not self._refs[k].get("url"):
                self._refs[k]["url"] = self._url_map.get(k, "")
        return self._refs[k]["num"]

    def lookup(self, name: str) -> int | None:
        return self._refs.get(self._key(name), {}).get("num")

    def all_refs(self) -> list[dict]:
        return sorted(self._refs.values(), key=lambda r: r["num"])


# ── Load signal sources (geo + cyber) → name → url map ────────────────────────
def _load_signal_sources(region_lower: str) -> dict[str, str]:
    """Read osint_signals.json for a region.

    Returns a dict mapping source name.lower() → url.
    Returns empty dict if file is absent or the `sources` field is missing.
    """
    url_map: dict[str, str] = {}
    for filename in ("osint_signals.json",):
        path = Path(OUTPUT_DIR) / "regional" / region_lower / filename
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for src in data.get("sources", []):
            name = src.get("name", "").strip()
            url  = src.get("url", "").strip()
            if name and url:
                url_map[name.lower()] = url
    return url_map


def _build_signal_url_map() -> dict[str, str]:
    """Merge signal source URL maps across all regions."""
    merged: dict[str, str] = {}
    for region in ["apac", "ame", "med", "nce", "latam"]:
        for k, v in _load_signal_sources(region).items():
            if k not in merged:
                merged[k] = v
    return merged


# ── Load source clusters ───────────────────────────────────────────────────────
def _load_clusters(region_lower: str) -> dict[str, str]:
    path = Path(OUTPUT_DIR) / "regional" / region_lower / "signal_clusters.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    result: dict[str, str] = {}
    for cluster in data.get("clusters", []):
        for src in cluster.get("sources", []):
            name     = src.get("name", "").strip()
            headline = src.get("headline", "").strip()
            if name and name.lower() not in _SKIP_SOURCES:
                result[name.lower()] = headline
    return result


def _build_cluster_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for region in ["apac", "ame", "med", "nce", "latam"]:
        for k, v in _load_clusters(region).items():
            if k not in mapping:
                mapping[k] = v
    return mapping


# ── Citation processing ────────────────────────────────────────────────────────
_BRACKET_RE = re.compile(r"\[([^\]]+)\]")
# Matches "Evidenced by [N]: " or "Corroborated by [N]: " prefixes
_ATTRIBUTION_RE = re.compile(
    r"(?:Evidenced by|Corroborated by|Source:|Cited by|Confirmed by)"
    r"\s+(\[\d+(?:,\s*\d+)*\]):\s*",
    re.IGNORECASE,
)


def _process_citations(text: str, registry: SourceRegistry,
                        cluster_map: dict[str, str]) -> str:
    """Replace [Source Name] with [N] and clean attribution prefixes."""
    def _register_one(name: str) -> int:
        return registry.register(name, cluster_map.get(name.lower(), ""))

    def replace(match: re.Match) -> str:
        raw = match.group(1).strip()
        if _NON_CITATION_RE.match(raw):
            return match.group(0)
        if raw.lower() in _SKIP_SOURCES:
            return match.group(0)
        if any(raw.lower().startswith(p) for p in _SKIP_PREFIXES):
            return match.group(0)
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if len(parts) > 1:
            return "[" + ", ".join(str(_register_one(p)) for p in parts) + "]"
        return f"[{_register_one(raw)}]"

    # Step 1: replace source names with numbers
    text = _BRACKET_RE.sub(replace, text)
    # Step 2: reformat "Evidenced by [N]: text" → "text [N]."
    # Move the citation number to end-of-clause and drop the attribution prefix
    def move_citation(m: re.Match) -> str:
        nums = m.group(1)   # already replaced: "[1]" or "[1, 2]"
        return ""           # strip prefix; citation stays inline after the clause

    text = _ATTRIBUTION_RE.sub(move_citation, text)
    return text


# ── Status label with dominant pillar ─────────────────────────────────────────
def _status_colour(status: RegionStatus, dominant_pillar: str | None = None) -> RGBColor:
    if status == RegionStatus.ESCALATED:
        return RED
    if status == RegionStatus.MONITOR:
        return AMBER
    if status == RegionStatus.CLEAR:
        return GREEN
    return GREY


def _status_label(status: RegionStatus, dominant_pillar: str | None = None) -> str:
    if status == RegionStatus.ESCALATED:
        if dominant_pillar == "Geopolitical":
            return "ESCALATED — GEO-LED"
        if dominant_pillar == "Cyber":
            return "ESCALATED — CYBER-LED"
        return "ESCALATED"
    if status == RegionStatus.MONITOR:
        return "MONITOR"
    if status == RegionStatus.CLEAR:
        return "CLEAR"
    return "UNKNOWN"


# ── Document helpers ───────────────────────────────────────────────────────────
def _font(run, size: int, bold: bool = False, italic: bool = False,
          colour: RGBColor | None = None) -> None:
    run.font.size   = Pt(size)
    run.font.bold   = bold
    run.font.italic = italic
    if colour:
        run.font.color.rgb = colour


def _add_divider(doc: Document) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(4)
    pPr  = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bot  = OxmlElement("w:bottom")
    bot.set(qn("w:val"),   "single")
    bot.set(qn("w:sz"),    "6")
    bot.set(qn("w:space"), "1")
    bot.set(qn("w:color"), "D1D5DB")
    pBdr.append(bot)
    pPr.append(pBdr)


def _add_label_value(doc: Document, label: str, value: str,
                     value_colour: RGBColor | None = None) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    r1 = p.add_run(f"{label}: ")
    _font(r1, 10, bold=True)
    r2 = p.add_run(value)
    _font(r2, 10, colour=value_colour)


def _add_subheading(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after  = Pt(3)
    run = p.add_run(text)
    _font(run, 10, bold=True, colour=NAVY)


def _add_bullet(doc: Document, text: str) -> None:
    p = doc.add_paragraph(style="List Bullet")
    run = p.add_run(text)
    _font(run, 10)


def _add_normal(doc: Document, text: str, italic: bool = False,
                colour: RGBColor | None = None) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text)
    _font(run, 10, italic=italic, colour=colour)


# ── Section builders ───────────────────────────────────────────────────────────
def _build_cover(doc: Document, data: ReportData) -> None:
    doc.add_paragraph()

    p = doc.add_paragraph()
    r = p.add_run("CYBER RISK INTELLIGENCE BRIEF")
    _font(r, 22, bold=True, colour=NAVY)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    r = p.add_run("Weekly Intelligence Update  —  CONFIDENTIAL")
    _font(r, 12, colour=GREY)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    date_str = (data.timestamp[:10]
                if data.timestamp and data.timestamp != "unknown"
                else datetime.now().strftime("%Y-%m-%d"))
    p = doc.add_paragraph()
    r = p.add_run(f"AeroGrid Wind Solutions  |  {date_str}")
    _font(r, 11, colour=GREY)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()

    total = data.escalated_count + data.monitor_count + data.clear_count
    p = doc.add_paragraph()
    r = p.add_run(
        f"Regions analysed: {total}     "
        f"Escalated: {data.escalated_count}     "
        f"Monitor: {data.monitor_count}     "
        f"Clear: {data.clear_count}"
    )
    _font(r, 10, colour=GREY)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_page_break()


def _build_exec_summary(doc: Document, data: ReportData,
                         registry: SourceRegistry,
                         cluster_map: dict[str, str]) -> None:
    p = doc.add_paragraph()
    r = p.add_run("Executive Summary")
    _font(r, 16, bold=True, colour=NAVY)

    # ── Purpose line ──────────────────────────────────────────────────────────
    date_str = (data.timestamp[:10]
                if data.timestamp and data.timestamp != "unknown"
                else datetime.now().strftime("%Y-%m-%d"))
    purpose = (
        f"This weekly brief informs the CISO of active geopolitical and cyber threats "
        f"relevant to AeroGrid Wind Solutions' global operations. "
        f"Intelligence was gathered via open-source signals for the cycle ending {date_str}."
    )
    _add_normal(doc, purpose, italic=True, colour=GREY)

    doc.add_paragraph()

    # ── BLUF block — scannable status at a glance ─────────────────────────────
    p = doc.add_paragraph()
    r = p.add_run("Bottom Line Up Front")
    _font(r, 11, bold=True, colour=NAVY)

    total = data.escalated_count + data.monitor_count + data.clear_count
    _add_bullet(doc, f"Global posture: {data.escalated_count} of {total} regions escalated, "
                     f"{data.monitor_count} at monitor, {data.clear_count} clear.")

    for entry in data.regions:
        if entry.status == RegionStatus.ESCALATED:
            actor  = entry.threat_actor or "Unknown — under assessment"
            label  = entry.signal_type_label or "Under Assessment"
            _add_bullet(doc,
                f"{entry.name}: {entry.scenario_match or 'Scenario TBD'} — "
                f"{actor} — {label}")

    for m in data.monitor_regions:
        _add_bullet(doc, f"{m.get('region', '')}: At monitor — no escalation threshold reached.")

    doc.add_paragraph()

    # ── Detailed exec summary ─────────────────────────────────────────────────
    p = doc.add_paragraph()
    r = p.add_run("Detail")
    _font(r, 11, bold=True, colour=NAVY)

    for s in _split_sentences(data.exec_summary):
        processed = _process_citations(s, registry, cluster_map)
        _add_bullet(doc, processed)

    _add_divider(doc)


def _build_region_escalated(doc: Document, entry: RegionEntry,
                              registry: SourceRegistry,
                              cluster_map: dict[str, str]) -> None:
    sl     = _status_label(entry.status, entry.dominant_pillar)
    colour = _status_colour(entry.status, entry.dominant_pillar)

    p  = doc.add_paragraph()
    r1 = p.add_run(f"{entry.name}  —  {REGION_NAMES.get(entry.name, entry.name)}")
    _font(r1, 14, bold=True, colour=NAVY)
    r2 = p.add_run(f"   [{sl}]")
    _font(r2, 10, bold=True, colour=colour)

    _add_label_value(doc, "Scenario",     entry.scenario_match or "Under assessment")
    _add_label_value(doc, "Threat Actor", entry.threat_actor or "Unknown — under assessment")
    _add_label_value(doc, "Signal Type",  entry.signal_type_label or "Under Assessment")

    def proc(text: str) -> str:
        return _process_citations(text, registry, cluster_map)

    if entry.intel_bullets:
        _add_subheading(doc, "Intelligence Findings")
        for b in entry.intel_bullets:
            _add_bullet(doc, proc(b))

    if entry.adversary_bullets:
        _add_subheading(doc, "Observed Adversary Activity")
        for b in entry.adversary_bullets:
            _add_bullet(doc, proc(b))

    if entry.impact_bullets:
        _add_subheading(doc, "Impact for AeroGrid")
        for b in entry.impact_bullets:
            _add_bullet(doc, proc(b))

    if entry.watch_bullets:
        _add_subheading(doc, "Watch For — Adversary Tradecraft")
        for b in entry.watch_bullets:
            _add_bullet(doc, proc(b))

    if entry.action_bullets:
        _add_subheading(doc, "Recommended Actions")
        for b in entry.action_bullets:
            _add_bullet(doc, b)

    _add_divider(doc)


def _build_monitor_section(doc: Document, monitor_regions: list,
                             registry: SourceRegistry,
                             cluster_map: dict[str, str]) -> None:
    if not monitor_regions:
        return

    p = doc.add_paragraph()
    r = p.add_run("Regions at Monitor")
    _font(r, 13, bold=True, colour=NAVY)

    for m in monitor_regions:
        region    = m.get("region", "")
        rationale = _process_citations(
            m.get("rationale", "No rationale available."), registry, cluster_map
        )
        p  = doc.add_paragraph()
        r1 = p.add_run(f"{region}: ")
        _font(r1, 10, bold=True)
        r2 = p.add_run(rationale)
        _font(r2, 10)
        p.paragraph_format.space_after = Pt(4)

    _add_divider(doc)


def _build_references(doc: Document, registry: SourceRegistry) -> None:
    refs = registry.all_refs()
    if not refs:
        return

    p = doc.add_paragraph()
    r = p.add_run("References")
    _font(r, 13, bold=True, colour=NAVY)

    # Sort by credibility tier: A first, then B, then C — preserve order within tier
    _TIER_ORDER = {"A": 0, "B": 1, "C": 2}
    sorted_refs = sorted(refs, key=lambda r: _TIER_ORDER.get(_infer_tier(r.get("url", "")), 1))

    for ref in sorted_refs:
        name = ref["name"]
        url  = ref.get("url", "")
        tier = _infer_tier(url)

        p = doc.add_paragraph()
        p.paragraph_format.left_indent       = Cm(0.8)
        p.paragraph_format.first_line_indent = Cm(-0.8)
        p.paragraph_format.space_after       = Pt(4)

        r1 = p.add_run(f"[{tier}] ")
        _font(r1, 9, bold=True)

        # Tier-prefixed format: [TIER] Name — URL
        if url:
            body = f"{name} \u2014 {url}"
        else:
            body = name

        r2 = p.add_run(body)
        _font(r2, 9)


def _build_footer_note(doc: Document, data: ReportData) -> None:
    doc.add_paragraph()
    p = doc.add_paragraph()
    r = p.add_run(
        f"Pipeline run: {data.run_id}  |  "
        "Sources: open-source signals (media monitoring, government publications, industry reporting).  |  "
        "Scenario register: AeroGrid CRQ database.  |  "
        "For internal use only."
    )
    _font(r, 8, italic=True, colour=GREY)


# ── Main ───────────────────────────────────────────────────────────────────────
def export(output_path: str = DEFAULT_OUT) -> None:
    data        = build()
    url_map     = _build_signal_url_map()
    registry    = SourceRegistry(url_map=url_map)
    cluster_map = _build_cluster_map()
    doc         = Document()

    for section in doc.sections:
        section.top_margin    = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin   = Cm(2.5)
        section.right_margin  = Cm(2.5)

    _build_cover(doc, data)
    _build_exec_summary(doc, data, registry, cluster_map)

    for entry in data.regions:
        if entry.status == RegionStatus.ESCALATED:
            _build_region_escalated(doc, entry, registry, cluster_map)

    _build_monitor_section(doc, data.monitor_regions, registry, cluster_map)
    _build_references(doc, registry)
    _build_footer_note(doc, data)

    doc.save(output_path)
    print(f"CISO brief exported: {output_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    export(out)
