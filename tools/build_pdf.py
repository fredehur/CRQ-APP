"""
CRQ CISO Brief — PDF renderer (v2)
====================================

Playwright + Jinja2 pipeline. Implements the CRQ Design System v1.0
as defined by Claude Design (tools/design/).

Design system: tools/design/tokens.css + tools/design/system.css
Reference:     tools/design/index.html

v2 changes vs v1:
  - Full token ramp (paper/ink-50…ink-900) from design system
  - pill-combo format: single pill "CRITICAL · MED · NEW"
  - Category circles: all navy (design spec P·03 — letter only, no per-cat colour)
  - Exec summary: sev-card white-bordered cards
  - Scatter chart: pure CSS (no Matplotlib dependency for chart page)
  - IBM Plex Sans type scale locked per design system
"""

import sys
from pathlib import Path
import base64
import json
import tempfile

import jinja2
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from brief_data import BRIEF_DATA  # noqa: E402

HERE    = Path(__file__).parent
OUT_DIR = HERE.parent / "output" / "deliverables"

# ─── HTML template (design system v1.0 inline) ─────────────────────────────

TEMPLATE_SRC = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ brief.title }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">

<style>
/* ── Design tokens (CRQ Design System v1.0) ─────────────────────────── */
:root {
  --brand-navy:   #1B2D6E;
  --brand-bright: #2E5BFF;

  --sev-critical: #d1242f;
  --sev-high:     #cf6f12;
  --sev-medium:   #9a7300;
  --sev-monitor:  #0969da;

  --sev-critical-tint: #FBE9EB;
  --sev-high-tint:     #FBEEDF;
  --sev-medium-tint:   #F6EED6;
  --sev-monitor-tint:  #E1EDFB;

  --ink-900: #0E1530;
  --ink-700: #1B2D6E;
  --ink-500: #4A5275;
  --ink-400: #6E7596;
  --ink-300: #A8ADC4;
  --ink-200: #D6D9E5;
  --ink-150: #E4E6EF;
  --ink-100: #EEF0F6;
  --ink-50:  #F5F6FA;
  --paper:   #FBFBFD;
  --white:   #FFFFFF;

  --font-sans: "IBM Plex Sans", system-ui, -apple-system, sans-serif;

  --fs-display: 40pt;
  --fs-h1:      22pt;
  --fs-h2:      16pt;
  --fs-h3:      12pt;
  --fs-body:    10pt;
  --fs-small:   9pt;
  --fs-xs:      8pt;
  --fs-label:   8pt;
  --fs-label-sm: 7.5pt;

  --tr-label:   0.10em;
  --tr-meta:    0.07em;
  --tr-heading: -0.01em;

  --lh-tight: 1.15;
  --lh-body:  1.45;
  --lh-loose: 1.55;

  --r-pill: 999pt;
  --r-md:   3pt;
  --r-card: 5pt;
}

/* ── Page setup ─────────────────────────────────────────────────────── */
@page {
  size: A4;
  margin: 20mm 16mm 20mm 16mm;
  @bottom-left   { content: "{{ brief.footer_left }}"; font-family: 'IBM Plex Sans', sans-serif; font-size: 7pt; color: var(--ink-400); letter-spacing: var(--tr-meta); text-transform: uppercase; }
  @bottom-center { content: "CRQ COMMAND CENTER"; font-family: 'IBM Plex Sans', sans-serif; font-size: 7pt; color: var(--ink-400); letter-spacing: var(--tr-meta); text-transform: uppercase; }
  @bottom-right  { content: counter(page) " / " counter(pages); font-family: 'IBM Plex Sans', sans-serif; font-size: 7pt; color: var(--ink-400); }
}
@page :first { @bottom-left { content: none; } @bottom-center { content: none; } @bottom-right { content: none; } }

/* ── Base ───────────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0;
  font-family: var(--font-sans);
  font-size: var(--fs-body);
  line-height: var(--lh-body);
  color: var(--ink-900);
  background: var(--paper);
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
  font-feature-settings: "ss02", "cv11";
  -webkit-font-smoothing: antialiased;
}
h1, h2, h3, h4 { margin: 0; font-weight: 600; color: var(--ink-700); letter-spacing: var(--tr-heading); }
p { margin: 0 0 5pt 0; }

.section {
  page-break-after: always;
  break-inside: avoid;
  page-break-inside: avoid;
}
.section:last-child { page-break-after: auto; }

/* ── Typography utilities ────────────────────────────────────────────── */
.t-display { font-size: var(--fs-display); line-height: var(--lh-tight); font-weight: 600; letter-spacing: var(--tr-heading); color: var(--ink-700); }
.t-h1      { font-size: var(--fs-h1); line-height: var(--lh-tight); font-weight: 600; color: var(--ink-700); }
.t-h2      { font-size: var(--fs-h2); line-height: var(--lh-tight); font-weight: 600; color: var(--ink-700); }
.t-h3      { font-size: var(--fs-h3); line-height: 1.3; font-weight: 600; color: var(--ink-900); }
.t-body    { font-size: var(--fs-body); line-height: var(--lh-body); color: var(--ink-900); }
.t-small   { font-size: var(--fs-small); line-height: 1.45; color: var(--ink-500); }
.t-xs      { font-size: var(--fs-xs); color: var(--ink-400); }
.t-label   { font-size: var(--fs-label); font-weight: 600; letter-spacing: var(--tr-label); text-transform: uppercase; }
.t-label-sm { font-size: var(--fs-label-sm); font-weight: 600; letter-spacing: var(--tr-label); text-transform: uppercase; color: var(--ink-400); }
.c-navy   { color: var(--brand-navy); }
.c-bright { color: var(--brand-bright); }
.c-mute   { color: var(--ink-500); }
.c-faint  { color: var(--ink-400); }
.eyebrow  { font-size: var(--fs-label-sm); font-weight: 600; letter-spacing: var(--tr-label); text-transform: uppercase; color: var(--ink-400); margin-bottom: 4pt; }

/* ── Dividers ────────────────────────────────────────────────────────── */
.hr       { height: 1px; background: var(--ink-200); border: 0; margin: 8pt 0; }
.hr-navy  { height: 1px; background: var(--ink-700); border: 0; margin: 8pt 0; }

/* ── Pill bands (design system 02.1) ────────────────────────────────── */
/* Single-grade pill */
.pill {
  display: inline-flex; align-items: center; gap: 5pt;
  height: 16pt; padding: 0 8pt;
  border-radius: var(--r-pill);
  font-size: var(--fs-label); font-weight: 600;
  letter-spacing: var(--tr-label); text-transform: uppercase;
  color: var(--white); white-space: nowrap; line-height: 1;
}
.pill--critical { background: var(--sev-critical); }
.pill--high     { background: var(--sev-high); }
.pill--medium   { background: var(--sev-medium); }
.pill--monitor  { background: var(--sev-monitor); }
.pill--navy     { background: var(--brand-navy); }
.pill--ghost    { background: transparent; color: var(--ink-700); box-shadow: inset 0 0 0 1pt var(--ink-200); }

/* Compound pill-combo: CRITICAL · MED · NEW in one band */
.pill-combo {
  display: inline-flex; align-items: center;
  height: 16pt; padding: 0 8pt;
  border-radius: var(--r-pill);
  font-size: var(--fs-label); font-weight: 600;
  letter-spacing: var(--tr-label); text-transform: uppercase;
  color: var(--white); line-height: 1; gap: 6pt;
}
.pill-combo .sep { opacity: 0.6; font-weight: 400; }

/* Full-width section band pill */
.band-pill {
  display: block; width: 100%;
  padding: 5pt 10pt;
  border-radius: var(--r-pill);
  font-size: var(--fs-label); font-weight: 600;
  letter-spacing: var(--tr-label); text-transform: uppercase;
  color: var(--white); text-align: center; line-height: 1.2;
  margin: 6pt 0;
}

/* ── Severity dots (design system 02.2) ─────────────────────────────── */
.sdot {
  display: inline-block; width: 8pt; height: 8pt; border-radius: 50%; vertical-align: middle;
}
.sdot--lg { width: 11pt; height: 11pt; }
.sdot--xl { width: 14pt; height: 14pt; }
.sdot--critical { background: var(--sev-critical); }
.sdot--high     { background: var(--sev-high); }
.sdot--medium   { background: var(--sev-medium); }
.sdot--monitor  { background: var(--sev-monitor); }

/* ── Category icon circles (design system 02.3) — all navy ──────────── */
.cat {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18pt; height: 18pt; border-radius: 50%;
  background: var(--brand-navy);
  color: var(--white); font-weight: 700; font-size: 9pt;
  vertical-align: middle; flex-shrink: 0;
}
.cat--lg { width: 22pt; height: 22pt; font-size: 10.5pt; }
.cat--xl { width: 30pt; height: 30pt; font-size: 13pt; }

/* ── Driver lists (design system 02.4) ──────────────────────────────── */
.drivers { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6pt; }
.drivers li { display: flex; align-items: flex-start; gap: 7pt; }
.drivers .d-main { font-size: var(--fs-body); font-weight: 600; color: var(--ink-900); line-height: 1.25; }
.drivers .d-sub  { font-size: var(--fs-small); color: var(--ink-500); margin-top: 1pt; }

/* ── Executive summary cards (design system 02.5) ───────────────────── */
.sev-card {
  background: var(--white);
  border: 1pt solid var(--ink-150);
  border-radius: var(--r-card);
  padding: 8pt 10pt;
  display: flex; flex-direction: column; gap: 4pt;
  break-inside: avoid;
}
.sev-card .title { font-size: var(--fs-h3); font-weight: 600; color: var(--ink-900); line-height: 1.25; }
.sev-card .body  { font-size: var(--fs-small); color: var(--ink-500); line-height: var(--lh-body); }

/* ── Meta rail (design system 02.6) ─────────────────────────────────── */
.meta-rail {
  font-size: var(--fs-xs);
  font-weight: 500;
  letter-spacing: var(--tr-meta);
  text-transform: uppercase;
  color: var(--ink-400);
  font-variant-numeric: tabular-nums;
  border-top: 1pt solid var(--ink-200);
  padding-top: 5pt;
  margin-top: 8pt;
}
.meta-rail .dot { color: var(--ink-300); }

/* ── Confidence badge ────────────────────────────────────────────────── */
.confidence-badge {
  display: inline-block;
  font-size: var(--fs-label); font-weight: 600;
  letter-spacing: var(--tr-label); text-transform: uppercase;
  color: var(--ink-700);
  padding: 4pt 9pt;
  border: 1pt solid var(--ink-700);
  border-radius: 2pt;
}

/* ── Scatter chart — pure CSS (design system 02.7) ──────────────────── */
.scatter {
  position: relative;
  width: 100%; aspect-ratio: 1.7;
  background: var(--white);
  border: 1pt solid var(--ink-200);
  border-radius: var(--r-md);
  padding: 36pt 36pt 36pt 48pt;
}
.scatter .canvas {
  position: absolute;
  inset: 36pt 36pt 36pt 48pt;
  background:
    linear-gradient(to right, var(--ink-700) 0, var(--ink-700) 1pt, transparent 1pt) 50% 0/1pt 100% no-repeat,
    linear-gradient(to top,   var(--ink-700) 0, var(--ink-700) 1pt, transparent 1pt) 0 50%/100% 1pt no-repeat;
}
/* Top-right quadrant diagonal hatching */
.scatter .canvas::before {
  content: "";
  position: absolute;
  top: 0; right: 0; width: 50%; height: 50%;
  background: repeating-linear-gradient(45deg, rgba(209,36,47,0.06) 0 5pt, transparent 5pt 10pt);
  pointer-events: none;
}
.scatter .dot {
  position: absolute;
  border-radius: 50%;
  transform: translate(-50%, 50%);
  box-shadow: 0 0 0 2pt var(--white);
}
.scatter .dot-label {
  position: absolute;
  font-size: 7.5pt; font-weight: 600;
  letter-spacing: var(--tr-label); text-transform: uppercase;
  color: var(--ink-700);
  transform: translate(8pt, 50%);
  white-space: nowrap;
}
.scatter .axis-x, .scatter .axis-y {
  position: absolute;
  font-size: var(--fs-label-sm); color: var(--ink-400);
  letter-spacing: var(--tr-label); text-transform: uppercase;
  font-weight: 600;
}
.scatter .axis-x { bottom: 11pt; left: 48pt; right: 36pt; display: flex; justify-content: space-between; }
.scatter .axis-y { top: 36pt; left: 11pt; bottom: 36pt; writing-mode: vertical-rl; transform: rotate(180deg); display: flex; justify-content: space-between; }
.scatter .legend {
  position: absolute; top: 10pt; right: 10pt;
  display: flex; gap: 10pt; align-items: center;
  font-size: var(--fs-label-sm); letter-spacing: var(--tr-label); text-transform: uppercase; color: var(--ink-500);
}
.scatter .legend span { display: inline-flex; align-items: center; gap: 4pt; }

/* ── Page compositions ───────────────────────────────────────────────── */

/* Cover */
.cover { display: flex; flex-direction: column; min-height: 237mm; }
.cover .brand { font-weight: 700; font-size: var(--fs-label); letter-spacing: var(--tr-label); text-transform: uppercase; color: var(--brand-navy); }
.cover .brand-sub { font-size: var(--fs-xs); color: var(--ink-400); margin-top: 2pt; letter-spacing: var(--tr-meta); text-transform: uppercase; }
.cover .title-block { margin-top: 64mm; }
.cover .doc-type { font-size: var(--fs-label); font-weight: 600; letter-spacing: var(--tr-label); text-transform: uppercase; color: var(--ink-400); margin-bottom: 6pt; }
.cover .cover-title { font-size: 52pt; line-height: var(--lh-tight); font-weight: 600; color: var(--brand-navy); letter-spacing: var(--tr-heading); margin: 0 0 8pt 0; }
.cover .cover-sub { font-size: var(--fs-h2); color: var(--ink-500); font-weight: 400; }
.cover .meta-row { margin-top: auto; display: flex; gap: 14mm; border-top: 1pt solid var(--ink-200); padding-top: 7pt; }
.cover .meta-row .m-label { font-size: var(--fs-label-sm); font-weight: 600; letter-spacing: var(--tr-label); text-transform: uppercase; color: var(--ink-400); }
.cover .meta-row .m-value { font-size: var(--fs-h3); font-weight: 600; color: var(--ink-900); margin-top: 2pt; }

/* Executive summary */
.exec-top { font-size: var(--fs-h2); line-height: 1.35; color: var(--ink-700); font-weight: 400; margin: 5pt 0 4pt; max-width: 155mm; }
.exec-grid { display: flex; gap: 10mm; margin-top: 8pt; }
.exec-main { flex: 1.5; display: flex; flex-direction: column; gap: 6pt; }
.exec-side { flex: 1; display: flex; flex-direction: column; gap: 10pt; }
.also-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 5pt; }
.also-list li { font-size: var(--fs-small); color: var(--ink-900); line-height: 1.35; display: flex; gap: 5pt; align-items: flex-start; }
.also-list .region { font-weight: 600; color: var(--ink-500); font-size: var(--fs-xs); letter-spacing: var(--tr-label); text-transform: uppercase; }
.watch-panel { background: var(--ink-100); border-radius: var(--r-md); padding: 8pt 10pt; }
.watch-panel .wlabel { font-size: var(--fs-label-sm); font-weight: 600; letter-spacing: var(--tr-label); text-transform: uppercase; color: var(--ink-700); margin-bottom: 4pt; }
.watch-panel p { font-size: var(--fs-small); color: var(--ink-700); line-height: var(--lh-loose); margin: 0; }

/* Scenario pages */
.scenario-title { font-size: var(--fs-h1); line-height: var(--lh-tight); font-weight: 600; color: var(--ink-700); margin: 4pt 0 8pt; }
.impli-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8mm; margin-top: 4pt; }
.impli-grid ul { list-style: none; margin: 5pt 0 0; padding: 0; }
.impli-grid li { font-size: var(--fs-small); color: var(--ink-900); line-height: 1.4; margin-bottom: 4pt; padding-left: 9pt; position: relative; }
.impli-grid li::before { content: "▸"; position: absolute; left: 0; color: var(--ink-300); font-size: 6pt; top: 2pt; }
.impli-grid li b { color: var(--ink-900); font-weight: 600; }

/* Matrix */
.bottom-line { font-size: var(--fs-body); line-height: var(--lh-body); color: var(--ink-900); margin: 8pt 0 12pt; }
.matrix-wrap { display: flex; flex-direction: column; gap: 6mm; }
.matrix-chart { width: 100%; }
.matrix-footer { display: flex; gap: 16mm; align-items: flex-start; font-size: var(--fs-small); margin-top: 10mm; }
.matrix-reading { flex: 2; }
.matrix-legend  { flex: 1; }
.legend-item  { display: flex; align-items: center; gap: 5pt; font-size: var(--fs-small); margin-bottom: 3pt; }

/* Methodology */
.method-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8mm; margin-top: 8pt; }
.method-item { margin-bottom: 6pt; }
.method-label { font-size: var(--fs-label-sm); font-weight: 600; letter-spacing: var(--tr-label); text-transform: uppercase; color: var(--ink-400); }
.method-value { font-size: var(--fs-body); color: var(--ink-900); margin-top: 1pt; }
.source-list  { list-style: none; margin: 0; padding: 0; }
.source-list li { display: flex; align-items: center; gap: 5pt; font-size: var(--fs-small); margin-bottom: 4pt; }
.adm-pill { display: inline-flex; align-items: center; justify-content: center; background: var(--brand-navy); color: var(--white); font-size: 6.5pt; font-weight: 700; padding: 2pt 5pt; border-radius: 10pt; min-width: 18pt; }
.change-list  { list-style: none; margin: 0; padding: 0; }
.change-list li { display: flex; gap: 5pt; font-size: var(--fs-small); margin-bottom: 4pt; }
.change-marker { font-weight: 700; color: var(--brand-navy); flex-shrink: 0; }
.footer-note  { margin-top: 10mm; padding-top: 6pt; border-top: 1pt solid var(--ink-200); font-size: var(--fs-xs); color: var(--ink-400); font-style: italic; line-height: var(--lh-body); }
</style>
</head>
<body>

<!-- ── PAGE 1: COVER ──────────────────────────────────────────────────────── -->
<section class="section cover">
  <div class="brand">CRQ COMMAND CENTER</div>
  <div class="brand-sub">Cyber Risk Quantification · Threat Intelligence</div>

  <div class="title-block">
    <div class="doc-type">{{ brief.doc_type }}</div>
    <h1 class="cover-title">{{ brief.cover_title }}</h1>
    <div class="cover-sub">{{ brief.cover_subtitle }}</div>
  </div>

  <div class="meta-row">
    <div>
      <div class="m-label">PUBLISHED</div>
      <div class="m-value">{{ brief.published_date }}</div>
    </div>
    <div>
      <div class="m-label">PREPARED BY</div>
      <div class="m-value">{{ brief.prepared_by }}</div>
    </div>
    <div>
      <div class="m-label">VERSION</div>
      <div class="m-value">{{ brief.version }}</div>
    </div>
  </div>
</section>

<!-- ── PAGE 2: EXECUTIVE SUMMARY ─────────────────────────────────────────── -->
<section class="section">
  <div class="eyebrow">EXECUTIVE SUMMARY · CYCLE {{ brief.cycle }}</div>
  <p class="exec-top">{{ brief.exec_top_line }}</p>
  <hr class="hr-navy">

  <div class="exec-grid">
    <div class="exec-main">
      <div class="t-label-sm" style="margin-bottom:4pt;">KEY DEVELOPMENTS</div>
      {% for e in brief.key_developments %}
      <div class="sev-card">
        <div>
          <span class="pill-combo pill--{{ e.severity|lower }}">
            {{ e.severity }}<span class="sep">·</span>{{ e.region }}{% if e.is_new %}<span class="sep">·</span>NEW{% endif %}
          </span>
        </div>
        <div class="title">{{ e.headline }}</div>
        {% if e.impact %}<div class="body">{{ e.impact }}</div>{% endif %}
      </div>
      {% endfor %}
    </div>

    <div class="exec-side">
      <div>
        <div class="t-label-sm" style="margin-bottom:6pt;">ALSO TRACKING</div>
        <ul class="also-list">
          {% for a in brief.also_tracking %}
          <li>
            <span class="sdot sdot--{{ a.severity|lower }}" style="margin-top:3pt; flex-shrink:0;"></span>
            <span><span class="region">{{ a.region }}</span> — {{ a.text }}</span>
          </li>
          {% endfor %}
        </ul>
      </div>

      <div class="watch-panel">
        <div class="wlabel">WATCH NEXT</div>
        <p>{{ brief.watch_next }}</p>
      </div>

      <div>
        <span class="confidence-badge">CONFIDENCE: {{ brief.confidence }} · ADMIRALTY {{ brief.admiralty }}</span>
      </div>
    </div>
  </div>
</section>

<!-- ── PAGES 3+: SCENARIO PAGES ──────────────────────────────────────────── -->
{% for s in brief.scenarios %}
<section class="section">
  <div class="eyebrow">{{ s.region }} · SCENARIO {{ s.number }} OF {{ brief.total_scenarios }}</div>
  <h1 class="scenario-title">{{ s.headline }}</h1>

  <div class="t-label-sm" style="margin-bottom:6pt;">KEY DRIVERS &amp; ASSUMPTIONS</div>
  <ul class="drivers" style="margin-bottom:8pt;">
    {% for d in s.drivers %}
    <li>
      <span class="cat cat--lg">{{ d.letter }}</span>
      <div>
        <div class="d-main">{{ d.label }}</div>
        <div class="d-sub">→ {{ d.implication }}</div>
      </div>
    </li>
    {% endfor %}
  </ul>

  <div class="band-pill pill--{{ 'navy' if s.type == 'BASELINE' else ('high' if s.type == 'PLAUSIBLE' else 'critical') }}">
    {{ s.type }} · {{ s.type_subtitle }}
  </div>

  <p style="font-weight:600; font-size:var(--fs-h3); color:var(--ink-900); margin:5pt 0 3pt;">{{ s.bold_conclusion }}</p>
  <p style="font-size:var(--fs-body); color:var(--ink-900); line-height:var(--lh-body); margin-bottom:7pt;">{{ s.body }}</p>

  <div class="band-pill pill--navy">LIKELIHOOD</div>
  <p style="font-weight:600; font-size:var(--fs-body); margin:3pt 0 8pt;">{{ s.likelihood_verdict }}</p>

  <div class="impli-grid">
    <div>
      <div class="band-pill pill--critical" style="font-size:7pt;">BUSINESS IMPLICATIONS</div>
      <ul>
        {% for i in s.implications %}
        <li><b>{{ i.label }}:</b> {{ i.text }}</li>
        {% endfor %}
      </ul>
    </div>
    <div>
      <div class="band-pill pill--high" style="font-size:7pt;">PRIORITY ACTIONS · 0–90 DAYS</div>
      <ul>
        {% for a in s.actions %}
        <li>{{ a }}</li>
        {% endfor %}
      </ul>
    </div>
  </div>

  <div class="meta-rail">{{ s.evidence }}</div>
</section>
{% endfor %}

<!-- ── MATRIX PAGE ────────────────────────────────────────────────────────── -->
<section class="section">
  <div class="eyebrow">GLOBAL · SCENARIO PORTFOLIO</div>
  <h1 class="t-h1" style="margin:3pt 0 4pt;">{{ brief.matrix.headline }}</h1>
  <hr class="hr-navy">

  <div class="t-label-sm" style="margin-bottom:4pt;">BOTTOM LINE</div>
  <p class="bottom-line">{{ brief.matrix.bottom_line }}</p>

  <div class="matrix-wrap">
    <div class="matrix-chart">
      <div class="scatter">
        <div class="legend">
          <span><span class="sdot sdot--lg sdot--critical"></span>CRITICAL</span>
          <span><span class="sdot sdot--lg sdot--high"></span>HIGH</span>
          <span><span class="sdot sdot--lg sdot--medium"></span>MEDIUM</span>
          <span><span class="sdot sdot--lg sdot--monitor"></span>MONITOR</span>
        </div>
        <div class="canvas">
          {% for dot in brief.matrix.dots %}
          <div class="sdot sdot--lg sdot--{{ dot.severity|lower }} dot"
               style="width:14pt;height:14pt;left:{{ dot.x }}%;bottom:{{ dot.y }}%;"></div>
          <span class="dot-label" style="left:{{ dot.x }}%;bottom:{{ dot.y }}%;">{{ dot.label }}</span>
          {% endfor %}
        </div>
        <div class="axis-x"><span>LOW LIKELIHOOD</span><span>HIGH LIKELIHOOD →</span></div>
        <div class="axis-y"><span>LOW IMPACT</span><span>HIGH IMPACT ↑</span></div>
      </div>
    </div>

    <div class="matrix-footer">
      <div class="matrix-reading">
        <div class="t-label-sm" style="margin-bottom:4pt;">READING THIS CHART</div>
        <p style="font-size:var(--fs-small); color:var(--ink-900); line-height:var(--lh-loose); margin:0;">{{ brief.matrix.reading }}</p>
      </div>
      <div class="matrix-legend">
        <div class="t-label-sm" style="margin-bottom:4pt;">SEVERITY</div>
        {% for sev in ['critical','high','medium','monitor'] %}
        <div class="legend-item">
          <span class="sdot sdot--lg sdot--{{ sev }}"></span>{{ sev|upper }}
        </div>
        {% endfor %}
      </div>
      <div style="align-self:flex-end;">
        <span class="confidence-badge" style="font-size:7pt; padding:3pt 8pt;">ADMIRALTY {{ brief.admiralty }} · REFRESHED {{ brief.refreshed }}</span>
      </div>
    </div>
  </div>
</section>

<!-- ── METHODOLOGY PAGE ───────────────────────────────────────────────────── -->
<section class="section">
  <div class="eyebrow">METHODOLOGY · SOURCES · CHANGE LOG</div>
  <h1 class="t-h1" style="margin:3pt 0 4pt;">How this brief was produced</h1>
  <hr class="hr-navy">

  <div class="method-grid">
    <div>
      <div class="band-pill pill--navy" style="margin-bottom:8pt;">PIPELINE METADATA</div>
      {% for k, v in brief.methodology.meta %}
      <div class="method-item">
        <div class="method-label">{{ k }}</div>
        <div class="method-value">{{ v }}</div>
      </div>
      {% endfor %}
    </div>

    <div>
      <div class="band-pill pill--navy" style="margin-bottom:8pt;">SOURCES (TOP, ABRIDGED)</div>
      <ul class="source-list">
        {% for grade, name in brief.methodology.sources %}
        <li><span class="adm-pill">{{ grade }}</span> {{ name }}</li>
        {% endfor %}
      </ul>
    </div>

    <div>
      <div class="band-pill pill--navy" style="margin-bottom:8pt;">CHANGE vs. {{ brief.previous_cycle }}</div>
      <ul class="change-list">
        {% for marker, text in brief.methodology.changes %}
        <li><span class="change-marker">{{ marker }}</span> {{ text }}</li>
        {% endfor %}
      </ul>
    </div>
  </div>

  <div class="footer-note">
    Full source list, IOC tables, and pipeline trace available as separate appendix artifacts.
    This brief is published per cycle (weekly) and is intended for internal stakeholders only.
  </div>
</section>

</body>
</html>
"""


# ─── Render ────────────────────────────────────────────────────────────────

def render_pdf(out_path: Path) -> None:
    env = jinja2.Environment(autoescape=True)
    tpl = env.from_string(TEMPLATE_SRC)
    html = tpl.render(brief=BRIEF_DATA)

    with tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8"
    ) as tmp:
        tmp.write(html)
        html_path = tmp.name

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(Path(html_path).as_uri(), wait_until="networkidle")
        page.pdf(
            path=str(out_path),
            format="A4",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            prefer_css_page_size=True,
        )
        browser.close()

    print(f"Rendered: {out_path}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "CRQ-cycle-brief-v2.pdf"
    render_pdf(out)


if __name__ == "__main__":
    main()
