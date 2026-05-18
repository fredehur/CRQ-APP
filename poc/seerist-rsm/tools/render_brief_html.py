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

from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "tools" / "briefs" / "templates"
TEMPLATE_NAME = "rsm_email.html.j2"

_HEADER_RE = re.compile(r"^AEROWIND // (\S+) DAILY // (\S+)\s*$")
_STAT_RE = re.compile(
    r"^PULSE:\s*(.+?)\s*\|\s*ADM:\s*(.+?)\s*\|\s*NEW:\s*"
    r"(\d+)\s*EVT.*?(\d+)\s*HOT.*?(\d+)\s*CYB\s*$"
)
_SECTION_HEADER_RE = re.compile(r"^█\s*(.+?)\s*$")

# V1: severity band → color
_SEVERITY_COLORS = {
    "CRITICAL": "#b91c1c",
    "HIGH": "#c2410c",
    "MED": "#a16207",
    "LOW": "#525252",
}

# V2: cyber surface tag → chip colors
_SURFACE_CHIPS = {
    "OT/ICS": ("background:#dbeafe;color:#1e40af", "OT/ICS"),
    "IT": ("background:#fce7f3;color:#9d174d", "IT"),
    "Supply chain": ("background:#fef3c7;color:#92400e", "Supply chain"),
    "Workforce": ("background:#dcfce7;color:#15803d", "Workforce"),
    "Baseline": ("background:#f1f5f9;color:#475569", "Baseline"),
}

_CHIP_BASE_STYLE = (
    "display:inline-block;padding:2px 8px;border-radius:3px;"
    "font-size:11px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;"
)

# V1: match `[BAND · ...]` — first bracket group on a bullet line
# Handles both plain `[BAND · sev N · confidence]` and cyber double-bracket `[surface] [BAND · ...]`
_BAND_RE = re.compile(r"\[([A-Z]+)\s+·\s+sev\s+\d+\s+·\s+[^\]]+\]")
# V2: matches a `[surface_tag]` immediately after an optional `- ` bullet prefix
_SURFACE_TAG_RE = re.compile(r"^(-\s+)?\[([A-Za-z/\s]+)\]\s+")


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
        is_cyber = "CYBER" in s["header"]
        is_exposure = "EXPOSURE" in s["header"]
        raw_body = escape(s["body"])

        if is_exposure:
            # V5: split into per-site blocks; each gets border-left styling in template
            site_blocks = _split_exposure_into_site_blocks(raw_body)
            # Apply V1 severity spans within each block
            s["site_blocks"] = [_apply_severity_color(b) for b in site_blocks]
            s["body"] = raw_body  # fallback, not used when site_blocks present
        else:
            # V1 + V2: apply span decorations to the escaped body
            s["body"] = _render_body_with_spans(raw_body, is_cyber=is_cyber)
            s["site_blocks"] = []

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,
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
