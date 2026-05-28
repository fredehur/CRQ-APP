#!/usr/bin/env python3
"""Render an RSM daily brief markdown into an email-safe HTML body.

Usage:
    uv run python tools/render_brief_html.py BRIEF_MD MANIFEST_JSON --out OUTPUT_HTML
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from html import escape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "tools" / "briefs" / "templates"
TEMPLATE_NAME = "rsm_email.html.j2"

# Brand is parameterized: capture it so region-guided / neutrally-branded briefs
# render. Group order: brand, region, date_z.
_HEADER_RE = re.compile(r"^(?P<brand>.+?) // (?P<region>\S+) DAILY // (?P<date>\S+)\s*$")
_STAT_RE = re.compile(
    r"^PULSE:\s*(.+?)\s*\|\s*ADM:\s*(.+?)\s*\|\s*NEW:\s*"
    r"(\d+)\s*EVT.*?(\d+)\s*HOT.*?(\d+)\s*CYB\s*$"
)
_SECTION_HEADER_RE = re.compile(r"^█\s*(.+?)\s*$")

# Vestas semantic palette for severity emphasis.
_SEVERITY_COLORS = {
    "CRITICAL": "#772219",
    "HIGH": "#E17D28",
    "MED": "#005AFF",
    "LOW": "#606D7B",
}

# Vestas-approved cyber chip mappings.
_SURFACE_CHIPS = {
    "OT/ICS": ("background:#96C8F0;color:#1F3144", "OT/ICS"),
    "IT": ("background:#4BA6F7;color:#FFFFFF", "IT"),
    "Supply chain": ("background:#E3E5E8;color:#1F3144", "Supply chain"),
    "Workforce": ("background:#19736E;color:#FFFFFF", "Workforce"),
    "Baseline": ("background:#E3E5E8;color:#606D7B", "Baseline"),
}

_CHIP_BASE_STYLE = (
    "display:inline-block;padding:2px 8px;border-radius:0;"
    "font-size:11px;font-weight:600;text-transform:uppercase;"
)

# V1: match `[BAND · ...]` — first bracket group on a bullet line
# Handles both plain `[BAND · sev N · confidence]` and cyber double-bracket `[surface] [BAND · ...]`
_BAND_RE = re.compile(r"\[([A-Z]+)\s+·\s+sev\s+\d+\s+·\s+[^\]]+\]")
# V2: matches a `[surface_tag]` immediately after an optional `- ` bullet prefix
_SURFACE_TAG_RE = re.compile(r"^(-\s+)?\[([A-Za-z/\s]+)\]\s+")
# V9: numeric body citation, e.g. `[1]` or `[1, 2]` — produced by normalize_citations.py
_CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
# V9: APPENDIX entry line, e.g. `[1] snippet text — sig:id (label)`
_APPENDIX_ENTRY_RE = re.compile(r"^\[(\d+)\]\s+(.+)$")
_SIGNAL_ID_RE = re.compile(r"\b(?:osint|seerist):[A-Za-z0-9_:\-]+\b")
_URL_FIELDS = ("url", "source_url", "article_url", "web_url", "href", "link")

_SUP_STYLE = (
    "font-size:10px;vertical-align:super;line-height:0;color:#005AFF;"
    "font-family:VestasSans,Helvetica Neue,Helvetica,Arial,sans-serif;"
)
_ANCHOR_STYLE = "color:#005AFF;text-decoration:none;"


def _load_vestas_logo_data_uri() -> str:
    """Return a configured brand logo as a data URI when available.

    The renderer intentionally does not ship a Vestas logo file. Set
    VESTAS_LOGO_PATH or CRQ_BRAND_LOGO_PATH locally, or provide a repo-local
    static/design/logo/Vestas_Primary_Logo_RGB.png file in deployments that are
    allowed to distribute the logo asset.
    """
    candidates: list[Path] = []
    for env_name in ("VESTAS_LOGO_PATH", "CRQ_BRAND_LOGO_PATH"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value))
    candidates.extend([
        REPO_ROOT / "static" / "design" / "logo" / "Vestas_Primary_Logo_RGB.png",
        REPO_ROOT / "static" / "design" / "logo" / "brand-logo.png",
    ])

    logo_path = next((path for path in candidates if path.exists()), None)
    if logo_path is None:
        return ""
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _load_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _iter_signal_dicts(value: object):
    """Yield nested dictionaries that carry a signal_id."""
    if isinstance(value, dict):
        if value.get("signal_id"):
            yield value
        for child in value.values():
            yield from _iter_signal_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_signal_dicts(child)


def _collect_signal_urls(manifest: dict) -> dict[str, str]:
    """Build signal_id -> URL map from manifest inlines and referenced signal files."""
    urls: dict[str, str] = {}

    def _absorb(doc: object) -> None:
        for signal in _iter_signal_dicts(doc):
            signal_id = str(signal.get("signal_id") or "")
            if not signal_id or signal_id in urls:
                continue
            for field in _URL_FIELDS:
                url = signal.get(field)
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    urls[signal_id] = url
                    break

    _absorb(manifest)
    optional = manifest.get("optional", {}) if isinstance(manifest, dict) else {}
    if isinstance(optional, dict):
        for key in ("osint_physical_signals", "seerist_signals"):
            path_value = optional.get(key)
            if isinstance(path_value, str):
                loaded = _load_json(Path(path_value))
                if loaded is not None:
                    _absorb(loaded)

    return urls


def _link_appendix_sources(entry: str, source_urls: dict[str, str]) -> str:
    """Link signal IDs in an escaped appendix entry when a source URL exists."""
    def _replace(match: re.Match) -> str:
        signal_id = match.group(0)
        url = source_urls.get(signal_id)
        if not url:
            return signal_id
        safe_url = escape(url, quote=True)
        return (
            f'<a href="{safe_url}" target="_blank" '
            f'style="color:#005AFF;text-decoration:underline;">{signal_id}</a>'
        )

    return _SIGNAL_ID_RE.sub(_replace, entry)


def _apply_severity_color(text: str) -> str:
    """Wrap the BAND word in a severity-colored span inside `[BAND · ...]` brackets."""
    def _replace(m: re.Match) -> str:
        inner = m.group(0)  # full `[BAND · sev N · confidence]`
        # Extract BAND word — first token after `[`
        band_match = re.match(r"\[([A-Z]+)\s", inner)
        if not band_match:
            return inner
        band = band_match.group(1)
        color = _SEVERITY_COLORS.get(band)
        if not color:
            return inner
        colored_band = f'<span style="color:{color};font-weight:600;">{band}</span>'
        return inner.replace(f"[{band}", f"[{colored_band}", 1)
    return _BAND_RE.sub(_replace, text)


def _apply_citation_anchors(text: str) -> str:
    """Transform body `[N]` / `[N, M]` cites into superscript anchors that jump
    to `#ref-N` in the rendered APPENDIX block. Idempotent on text with no
    numeric brackets; leaves severity bands and surface chips untouched (those
    contain letters or non-comma separators)."""
    def _replace(m: re.Match) -> str:
        inner = m.group(1)
        nums = [n.strip() for n in inner.split(",")]
        linked = ", ".join(
            f'<a href="#ref-{n}" style="{_ANCHOR_STYLE}">{n}</a>' for n in nums
        )
        return f'<sup style="{_SUP_STYLE}">[{linked}]</sup>'
    return _CITATION_RE.sub(_replace, text)


def _render_appendix_block(body: str, source_urls: dict[str, str]) -> str:
    """Render the APPENDIX body as a list of anchored `<div id="ref-N">` rows.

    Body lines are expected to be either `[N] entry_text` rows or a single
    `No sources cited this window.` sentinel. Anything else passes through as
    a plain styled line.
    """
    rows: list[str] = []
    for line in body.split("\n"):
        line = line.rstrip()
        if not line:
            continue
        m = _APPENDIX_ENTRY_RE.match(line)
        if not m:
            rows.append(
                f'<div style="font-size:12px;line-height:1.6;color:#525252;font-style:italic;">'
                f'{line}</div>'
            )
            continue
        n, entry = m.group(1), _link_appendix_sources(m.group(2), source_urls)
        rows.append(
            f'<div id="ref-{n}" style="font-size:12px;line-height:1.55;color:#374151;'
            f'margin-bottom:4px;padding-left:4px;">'
            f'<span style="color:#005AFF;font-weight:600;">[{n}]</span> {entry}'
            f'</div>'
        )
    return "\n".join(rows)


def _apply_surface_chip(line: str) -> str:
    """Replace a `[surface_tag]` that follows an optional `- ` bullet prefix with a chip span."""
    m = _SURFACE_TAG_RE.match(line)
    if not m:
        return line
    bullet_prefix = m.group(1) or ""  # `- ` or empty
    raw_tag = m.group(2)
    chip_info = _SURFACE_CHIPS.get(raw_tag)
    if not chip_info:
        return line
    chip_style, label = chip_info
    chip = f'<span style="{_CHIP_BASE_STYLE}{chip_style};">{label}</span>'
    return bullet_prefix + chip + " " + line[m.end():]


def _render_body_with_spans(body: str, *, is_cyber: bool = False) -> str:
    """Apply V1 severity colors and V2 surface chips to a section body string.

    The body has already been html.escape()'d by the caller, so angle brackets
    inside plain text are safe. We inject <span> tags deliberately here.
    """
    lines = body.split("\n")
    result = []
    for line in lines:
        # V2: surface chip on cyber bullets (leading `[surface]`)
        if is_cyber:
            line = _apply_surface_chip(line)
        # V1: severity color on `[BAND · sev N · confidence]`
        line = _apply_severity_color(line)
        result.append(line)
    return "\n".join(result)


def _split_exposure_into_site_blocks(body: str) -> list[str]:
    """Split AEROWIND EXPOSURE body into per-site blocks for V5 border styling.

    Each block starts with a `▪ ` site marker line and includes its indented
    sub-lines (├─ / └─ / plain continuation).
    """
    lines = body.split("\n")
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("▪ "):
            if current:
                blocks.append(current)
            current = [line]
        else:
            if current:
                current.append(line)
            elif stripped:
                # Pre-site preamble (shouldn't normally exist, but handle gracefully)
                current = [line]
    if current:
        blocks.append(current)
    return ["\n".join(b) for b in blocks]


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
        raise ValueError("Brief is missing the '<BRAND> // <REGION> DAILY // <date>' header band or PULSE stat strip.")

    for s in sections:
        s["body"] = "\n".join(s["body_lines"]).strip()
        del s["body_lines"]

    return {
        "brand": header_match.group("brand"),
        "region": header_match.group("region"),
        "date_z": header_match.group("date"),
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
    source_urls = _collect_signal_urls(manifest)

    # Intentional design: Jinja autoescape is OFF for the .j2 template (it's a
    # whole-document HTML scaffold; we don't want Jinja escaping the table
    # markup we authored). All user-supplied text fields are manually escaped
    # here BEFORE template render. The template's `white-space: pre-wrap`
    # preserves the tree-glyph layout (├─ └─ ▪) in the rendered output.
    parsed["brand"] = escape(parsed["brand"])
    parsed["pulse_summary"] = escape(parsed["pulse_summary"])
    parsed["admiralty"] = escape(parsed["admiralty"])
    for s in parsed["sections"]:
        s["header"] = escape(s["header"])
        is_cyber = "CYBER" in s["header"]
        # Only the AEROWIND EXPOSURE (physical) section uses site_blocks.
        # The CYBER — ACTIVE EXPOSURE section also contains "EXPOSURE" but
        # must fall through to the prose-rendering branch so spans, surface
        # chips, and citation anchors get applied to its body.
        is_exposure = "AEROWIND EXPOSURE" in s["header"]
        is_appendix = "APPENDIX" in s["header"]
        raw_body = escape(s["body"])

        if is_appendix:
            # V9: APPENDIX renders as anchored entry rows. No citation anchors
            # applied inside the appendix itself (those would self-link).
            s["appendix_html"] = _render_appendix_block(raw_body, source_urls)
            s["body"] = raw_body
            s["site_blocks"] = []
        elif is_exposure:
            # V5: split into per-site blocks; each gets border-left styling in template
            site_blocks = _split_exposure_into_site_blocks(raw_body)
            # V1 severity spans + V9 citation anchors per block
            s["site_blocks"] = [
                _apply_citation_anchors(_apply_severity_color(b)) for b in site_blocks
            ]
            s["body"] = raw_body  # fallback, not used when site_blocks present
            s["appendix_html"] = ""
        else:
            # V1 + V2 + V9: apply span decorations and citation anchors to the escaped body
            decorated = _render_body_with_spans(raw_body, is_cyber=is_cyber)
            s["body"] = _apply_citation_anchors(decorated)
            s["site_blocks"] = []
            s["appendix_html"] = ""

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,
        keep_trailing_newline=True,
    )
    template = env.get_template(TEMPLATE_NAME)
    return template.render(
        subject=subject,
        logo_data_uri=_load_vestas_logo_data_uri(),
        **parsed,
    )


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
