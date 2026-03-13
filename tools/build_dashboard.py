import json
import sys
import os
from datetime import datetime, timezone
from config import REGIONS, GLOBAL_REPORT_PATH, MANIFEST_PATH, TRACE_LOG_PATH

# Static Tailwind class mapping — dynamic interpolation breaks Tailwind CDN purging
SEVERITY_STYLES = {
    "Critical": {"border": "border-red-600", "bg": "bg-red-600", "text": "text-red-600"},
    "High":     {"border": "border-red-500", "bg": "bg-red-500", "text": "text-red-500"},
    "Medium":   {"border": "border-amber-500", "bg": "bg-amber-500", "text": "text-amber-500"},
    "Low":      {"border": "border-gray-400", "bg": "bg-gray-400", "text": "text-gray-400"},
}
DEFAULT_STYLE = {"border": "border-gray-400", "bg": "bg-gray-400", "text": "text-gray-400"}

VELOCITY_ARROW = {
    "accelerating": ("↑", "text-red-500", "Accelerating"),
    "stable":       ("→", "text-amber-500", "Stable"),
    "improving":    ("↓", "text-green-500", "Improving"),
    "unknown":      ("–", "text-gray-400", "No history"),
}

ADMIRALTY_LABEL = {
    "A": "Completely reliable",
    "B": "Usually reliable",
    "C": "Fairly reliable",
    "D": "Not usually reliable",
    "E": "Unreliable",
    "F": "Cannot be judged",
}
CREDIBILITY_LABEL = {
    "1": "Confirmed",
    "2": "Probably true",
    "3": "Possibly true",
    "4": "Doubtful",
    "5": "Improbable",
    "6": "Unverifiable",
}


def load_gatekeeper_data(region):
    """Return parsed gatekeeper_decision.json or None if absent."""
    path = f"output/regional/{region.lower()}/gatekeeper_decision.json"
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_scenario_map(region):
    """Return parsed scenario_map.json or None if absent."""
    path = f"output/regional/{region.lower()}/scenario_map.json"
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def decision_intelligence_block(region_name, gatekeeper_data, scenario_map_data):
    """Return HTML for the Decision Intelligence block, or '' if data absent."""
    gk = gatekeeper_data.get(region_name) if gatekeeper_data else None
    sm = scenario_map_data.get(region_name) if scenario_map_data else None
    if not gk:
        return ""

    decision = gk.get("decision", "")
    admiralty = gk.get("admiralty", {})
    if isinstance(admiralty, dict):
        admiralty_rating = admiralty.get("rating", "")
    else:
        admiralty_rating = str(admiralty) if admiralty else ""
    scenario_match = gk.get("scenario_match", "")
    dominant_pillar = gk.get("dominant_pillar", "")
    rationale = gk.get("rationale", "")
    financial_rank = sm.get("financial_rank", "") if sm else ""
    confidence = (sm.get("confidence", "") or "").upper() if sm else ""

    decision_color = {
        "ESCALATE": "text-red-300 bg-red-900/30 border-red-700",
        "MONITOR":  "text-amber-300 bg-amber-900/30 border-amber-700",
        "CLEAR":    "text-green-300 bg-green-900/20 border-green-800",
    }.get(decision, "text-gray-300 bg-gray-800 border-gray-700")

    rank_txt = f"Rank #{financial_rank}" if financial_rank else ""
    conf_txt = f"Confidence: {confidence}" if confidence else ""
    meta_parts = [p for p in [scenario_match, rank_txt, conf_txt] if p]
    meta_line = " · ".join(meta_parts)

    admiralty_span = f'<span class="font-mono font-bold ml-1">{admiralty_rating}</span>' if admiralty_rating else ""
    pillar_span = f'<span class="text-gray-400 ml-1 text-xs">{dominant_pillar}</span>' if dominant_pillar else ""
    meta_div = f'<div class="text-xs text-gray-400 mb-1">{meta_line}</div>' if meta_line else ""
    rationale_div = f'<div class="text-xs italic">&ldquo;{rationale}&rdquo;</div>' if rationale else ""

    return f"""
        <div class="mt-3 p-2 border rounded text-xs {decision_color}">
            <div class="flex items-center gap-1 mb-1 font-bold uppercase text-xs">{decision}{admiralty_span}{pillar_span}</div>
            {meta_div}{rationale_div}
        </div>"""


def admiralty_tooltip(rating):
    """Return plain-English tooltip for an Admiralty rating like 'B2'."""
    if not rating or len(rating) != 2:
        return "Assessment pending"
    r, c = rating[0].upper(), rating[1]
    rel = ADMIRALTY_LABEL.get(r, r)
    cred = CREDIBILITY_LABEL.get(c, c)
    return f"{rel} source — {cred}"


def build():
    json_path = GLOBAL_REPORT_PATH
    if not os.path.exists(json_path):
        print(f"ERROR: {json_path} not found.")
        sys.exit(1)
    with open(json_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    manifest = None
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

    trace_lines = []
    if os.path.exists(TRACE_LOG_PATH):
        with open(TRACE_LOG_PATH, 'rb') as f:
            raw = f.read()
        text = raw.decode('utf-8', errors='replace')
        trace_lines = [line.strip() for line in text.splitlines() if line.strip()]

    region_data = {}
    for region in REGIONS:
        data_path = f"output/regional/{region.lower()}/data.json"
        if os.path.exists(data_path):
            with open(data_path, encoding='utf-8') as f:
                region_data[region] = json.load(f)

    gatekeeper_data = {}
    scenario_map_data = {}
    for region in REGIONS:
        gk = load_gatekeeper_data(region)
        if gk:
            gatekeeper_data[region] = gk
        sm = load_scenario_map(region)
        if sm:
            scenario_map_data[region] = sm

    total_vacr = report.get("total_vacr_exposure", 0)
    summary = report.get("executive_summary", "")
    threat_regions = report.get("regional_threats", [])
    monitor_regions = report.get("monitor_regions", [])
    report_date = report.get("reporting_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    escalated_count = sum(1 for r in region_data.values() if r.get("status") == "escalated")
    monitor_count = sum(1 for r in region_data.values() if r.get("status") == "monitor")
    clear_count = sum(1 for r in region_data.values() if r.get("status") == "clear")

    # Build escalated regional cards
    region_cards = ""
    for r in threat_regions:
        scenario = r.get("primary_scenario", "")
        scenario_tag = f'<span class="inline-block bg-red-100 text-red-800 text-xs font-medium px-2.5 py-0.5 rounded mr-1 mb-1">{scenario}</span>' if scenario else ""

        sev = r.get("severity", "N/A")
        style = SEVERITY_STYLES.get(sev, DEFAULT_STYLE)

        # Admiralty badge
        admiralty = r.get("admiralty_rating", "")
        adm_tooltip = admiralty_tooltip(admiralty)
        admiralty_badge = f'<span class="inline-block bg-blue-100 text-blue-800 text-xs font-mono font-bold px-2 py-0.5 rounded" title="{adm_tooltip}">{admiralty}</span>' if admiralty else ""

        # Velocity arrow
        velocity = r.get("velocity", "unknown")
        arrow, arrow_color, arrow_label = VELOCITY_ARROW.get(velocity, VELOCITY_ARROW["unknown"])
        velocity_badge = f'<span class="{arrow_color} text-sm font-bold" title="Trend: {arrow_label}">{arrow} {arrow_label}</span>'

        # Dominant pillar tag
        pillar = r.get("dominant_pillar", "")
        pillar_tag = f'<span class="inline-block bg-gray-100 text-gray-700 text-xs font-medium px-2 py-0.5 rounded">{pillar}</span>' if pillar else ""

        region_cards += f"""
        <div class="bg-white rounded-lg shadow-md p-6 border-l-4 {style['border']}">
            <div class="flex justify-between items-start mb-3">
                <h3 class="text-lg font-bold text-gray-900">{r.get("region", "Unknown")}</h3>
                <span class="{style['bg']} text-white text-xs font-bold px-3 py-1 rounded-full">{sev}</span>
            </div>
            <p class="text-3xl font-bold {style['text']} mb-3">${r.get("vacr_exposure", 0):,.0f}</p>
            <div class="flex flex-wrap gap-2 items-center mb-3">
                {scenario_tag}{admiralty_badge}{pillar_tag}
            </div>
            <div class="mb-3">{velocity_badge}</div>
            <p class="text-sm text-gray-600 leading-relaxed">{r.get("strategic_assessment", "")}</p>
            {decision_intelligence_block(r.get("region", ""), gatekeeper_data, scenario_map_data)}
        </div>"""

    # Build monitor region cards
    monitor_cards = ""
    for m in monitor_regions:
        region_name = m.get("region", "Unknown")
        admiralty = m.get("admiralty_rating", "")
        adm_tooltip = admiralty_tooltip(admiralty)
        admiralty_badge = f'<span class="inline-block bg-blue-100 text-blue-800 text-xs font-mono font-bold px-2 py-0.5 rounded" title="{adm_tooltip}">{admiralty}</span>' if admiralty else ""
        monitor_cards += f"""
        <div class="bg-white rounded-lg shadow-md p-6 border-l-4 border-amber-400">
            <div class="flex justify-between items-start mb-3">
                <h3 class="text-lg font-bold text-gray-900">{region_name}</h3>
                <span class="bg-amber-400 text-white text-xs font-bold px-3 py-1 rounded-full">Watch</span>
            </div>
            <div class="mb-2">{admiralty_badge}</div>
            <p class="text-sm text-gray-600 leading-relaxed">{m.get("rationale", "Elevated indicators below escalation threshold.")}</p>
            {decision_intelligence_block(m.get("region", ""), gatekeeper_data, scenario_map_data)}
        </div>"""

    # Build clear region cards
    clear_cards = ""
    for region in REGIONS:
        rd = region_data.get(region, {})
        if rd.get("status") == "clear":
            clear_cards += f"""
        <div class="bg-white rounded-lg shadow-md p-6 border-l-4 border-green-500">
            <div class="flex justify-between items-start mb-3">
                <h3 class="text-lg font-bold text-gray-900">{region}</h3>
                <span class="bg-green-600 text-white text-xs font-bold px-3 py-1 rounded-full">Clear</span>
            </div>
            <p class="text-3xl font-bold text-green-600 mb-3">$0</p>
            <p class="text-sm text-gray-600 leading-relaxed">No credible threat identified. Gatekeeper assessment: region operating within normal risk parameters.</p>
            {decision_intelligence_block(region, gatekeeper_data, scenario_map_data)}
        </div>"""

    # Build trace log rows
    trace_rows = ""
    for line in trace_lines:
        css_class = "text-gray-600"
        if "GATEKEEPER_NO" in line:
            css_class = "text-green-600 font-medium"
        elif "GATEKEEPER_YES" in line:
            css_class = "text-red-600 font-medium"
        elif "HOOK_FAIL" in line:
            css_class = "text-amber-600 font-medium"
        elif "HOOK_PASS" in line:
            css_class = "text-green-600"
        elif "PIPELINE" in line:
            css_class = "text-blue-600 font-bold"
        trace_rows += f'<div class="{css_class} text-xs font-mono py-1 border-b border-gray-100">{line}</div>\n'

    if not trace_rows:
        trace_rows = '<div class="text-gray-400 text-xs italic">No trace events recorded.</div>'

    # Monitor section HTML — only render if there are monitor regions
    monitor_section = ""
    if monitor_cards:
        monitor_section = f"""
        <h2 class="text-lg font-bold text-gray-900 mb-4">Watch Regions</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
            {monitor_cards}
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CRQ Executive Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen">
    <header class="bg-gray-900 text-white py-6 px-8">
        <div class="max-w-7xl mx-auto flex justify-between items-center">
            <div>
                <h1 class="text-2xl font-bold tracking-tight">Cyber Risk Quantification Dashboard</h1>
                <p class="text-gray-400 text-sm mt-1">Global Executive Board Report &mdash; {report_date}</p>
            </div>
            <div class="text-right">
                <p class="text-xs text-gray-400 uppercase tracking-wider">Classification</p>
                <p class="text-sm font-semibold text-amber-400">Board Confidential</p>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-8 py-8">
        <!-- KPI Strip -->
        <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
            <div class="bg-white rounded-lg shadow-md p-5 text-center border-t-4 border-red-600">
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Total VaCR</p>
                <p class="text-3xl font-black text-red-600">${total_vacr:,.0f}</p>
            </div>
            <div class="bg-white rounded-lg shadow-md p-5 text-center border-t-4 border-blue-600">
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Regions</p>
                <p class="text-3xl font-black text-blue-600">{len(REGIONS)}</p>
            </div>
            <div class="bg-white rounded-lg shadow-md p-5 text-center border-t-4 border-red-500">
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Escalated</p>
                <p class="text-3xl font-black text-red-500">{escalated_count}</p>
            </div>
            <div class="bg-white rounded-lg shadow-md p-5 text-center border-t-4 border-amber-400">
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Watch</p>
                <p class="text-3xl font-black text-amber-400">{monitor_count}</p>
            </div>
            <div class="bg-white rounded-lg shadow-md p-5 text-center border-t-4 border-green-600">
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Clear</p>
                <p class="text-3xl font-black text-green-600">{clear_count}</p>
            </div>
        </div>

        <!-- Admiralty Legend -->
        <div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-8 text-xs text-blue-800">
            <span class="font-bold">Admiralty Scale:</span>
            Reliability A (confirmed) → F (unknown) &nbsp;|&nbsp;
            Credibility 1 (confirmed) → 6 (unverifiable) &nbsp;|&nbsp;
            e.g. <span class="font-mono font-bold">B2</span> = Usually reliable source, probably true
        </div>

        <!-- Executive Summary -->
        <div class="bg-white rounded-lg shadow-md p-6 mb-8">
            <h2 class="text-lg font-bold text-gray-900 mb-3">Executive Summary</h2>
            <p class="text-gray-700 leading-relaxed">{summary}</p>
        </div>

        <!-- Escalated Regional Threat Cards -->
        <h2 class="text-lg font-bold text-gray-900 mb-4">Escalated Regions</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
            {region_cards}
        </div>

        {monitor_section}

        <!-- Clear Region Cards -->
        <h2 class="text-lg font-bold text-gray-900 mb-4">Clear Regions</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
            {clear_cards}
        </div>

        <!-- Audit Trace (Collapsible) -->
        <details class="bg-white rounded-lg shadow-md mb-8">
            <summary class="cursor-pointer p-6 text-lg font-bold text-gray-900 hover:bg-gray-50 rounded-lg">
                System Audit Trace &mdash; {len(trace_lines)} events
            </summary>
            <div class="px-6 pb-6 max-h-96 overflow-y-auto">
                {trace_rows}
            </div>
        </details>

        <footer class="text-center text-xs text-gray-400 py-4">
            Generated by CRQ Agentic Pipeline &mdash; {report_date} &mdash; All financial figures from enterprise CRQ application (immutable source of truth)
        </footer>
    </main>
</body>
</html>"""

    with open("output/dashboard.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard written to output/dashboard.html ({escalated_count} escalated, {monitor_count} watch, {clear_count} clear, {len(trace_lines)} trace events)")

    # Markdown export
    md_lines = [
        f"# Global Executive Board Report — Cyber Risk Posture\n",
        f"**Date:** {report_date} | **Classification:** Board Confidential | **Total Global VaCR:** ${total_vacr:,.0f}\n",
        f"---\n",
        f"## Executive Summary\n",
        f"{summary}\n",
        f"---\n",
        f"## Escalated Regions\n",
    ]
    for r in threat_regions:
        admiralty = r.get("admiralty_rating", "")
        velocity = r.get("velocity", "unknown")
        arrow, _, arrow_label = VELOCITY_ARROW.get(velocity, VELOCITY_ARROW["unknown"])
        pillar = r.get("dominant_pillar", "")
        md_lines.append(f"### {r.get('region', 'Unknown')} — ${r.get('vacr_exposure', 0):,.0f} at Risk | Severity: {r.get('severity', 'N/A')}\n")
        meta = []
        if admiralty:
            meta.append(f"**Intelligence Assessment:** {admiralty} ({admiralty_tooltip(admiralty)})")
        if velocity:
            meta.append(f"**Trend:** {arrow} {arrow_label}")
        if pillar:
            meta.append(f"**Dominant Pillar:** {pillar}")
        if meta:
            md_lines.append(" | ".join(meta) + "\n")
        md_lines.append(f"**Primary Scenario:** {r.get('primary_scenario', '')}\n")
        md_lines.append(f"{r.get('strategic_assessment', '')}\n")

    if monitor_regions:
        md_lines.append("## Watch Regions\n")
        for m in monitor_regions:
            admiralty = m.get("admiralty_rating", "")
            md_lines.append(f"### {m.get('region', 'Unknown')} — Watch\n")
            if admiralty:
                md_lines.append(f"**Intelligence Assessment:** {admiralty} ({admiralty_tooltip(admiralty)})\n")
            md_lines.append(f"{m.get('rationale', '')}\n")

    md_lines.append("## Clear Regions\n")
    for region in REGIONS:
        rd = region_data.get(region, {})
        if rd.get("status") == "clear":
            md_lines.append(f"### {region} — Clear\n")
            md_lines.append("No credible threat identified. Region operating within normal risk parameters.\n")

    md_lines.append("---\n")
    md_lines.append(f"*Escalated: {escalated_count} | Watch: {monitor_count} | Clear: {clear_count} | Source: Enterprise CRQ Application*\n")

    with open("output/global_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print("Markdown export written to output/global_report.md")


if __name__ == "__main__":
    build()
