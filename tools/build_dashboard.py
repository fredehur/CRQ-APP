import json
import sys
import os
from datetime import datetime, timezone

REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]

def build():
    # Read global report JSON
    json_path = "output/global_report.json"
    if not os.path.exists(json_path):
        print(f"ERROR: {json_path} not found.")
        sys.exit(1)
    with open(json_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    # Read run manifest if available
    manifest = None
    manifest_path = "output/run_manifest.json"
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

    # Read system trace log
    trace_lines = []
    trace_path = "output/system_trace.log"
    if os.path.exists(trace_path):
        with open(trace_path, 'r', encoding='utf-8') as f:
            trace_lines = [line.strip() for line in f.readlines() if line.strip()]

    # Read per-region data.json files
    region_data = {}
    for region in REGIONS:
        data_path = f"output/regional/{region.lower()}/data.json"
        if os.path.exists(data_path):
            with open(data_path, encoding='utf-8') as f:
                region_data[region] = json.load(f)

    total_vacr = report.get("total_vacr_exposure", 0)
    summary = report.get("executive_summary", "")
    threat_regions = report.get("regional_threats", [])
    report_date = report.get("reporting_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    # Count escalated vs clear from data.json files
    escalated_count = sum(1 for r in region_data.values() if r.get("status") == "escalated")
    clear_count = sum(1 for r in region_data.values() if r.get("status") == "clear")

    # Build escalated regional cards from global_report.json
    region_cards = ""
    for r in threat_regions:
        scenario_tags = ""
        for s in r.get("scenario_types", []):
            scenario_tags += f'<span class="inline-block bg-red-100 text-red-800 text-xs font-medium px-2.5 py-0.5 rounded mr-1 mb-1">{s}</span>'
        if not scenario_tags and r.get("primary_scenario"):
            scenario_tags = f'<span class="inline-block bg-red-100 text-red-800 text-xs font-medium px-2.5 py-0.5 rounded mr-1 mb-1">{r["primary_scenario"]}</span>'

        sev = r.get("severity", "N/A")
        sev_color = "red" if sev in ("Critical", "High") else "amber" if sev == "Medium" else "gray"
        region_cards += f"""
        <div class="bg-white rounded-lg shadow-md p-6 border-l-4 border-{sev_color}-500">
            <div class="flex justify-between items-start mb-3">
                <h3 class="text-lg font-bold text-gray-900">{r.get("region", "Unknown")}</h3>
                <span class="bg-{sev_color}-600 text-white text-xs font-bold px-3 py-1 rounded-full">{sev}</span>
            </div>
            <p class="text-3xl font-bold text-{sev_color}-600 mb-3">${r.get("vacr_exposure", 0):,.0f}</p>
            <div class="mb-3">{scenario_tags}</div>
            <p class="text-sm text-gray-600 leading-relaxed">{r.get("strategic_assessment", "")}</p>
        </div>"""

    # Build clear region cards from data.json
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
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div class="bg-white rounded-lg shadow-md p-6 text-center border-t-4 border-red-600">
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Total Value at Cyber Risk</p>
                <p class="text-4xl font-black text-red-600">${total_vacr:,.0f}</p>
            </div>
            <div class="bg-white rounded-lg shadow-md p-6 text-center border-t-4 border-blue-600">
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Total Regions</p>
                <p class="text-4xl font-black text-blue-600">{len(REGIONS)}</p>
            </div>
            <div class="bg-white rounded-lg shadow-md p-6 text-center border-t-4 border-red-500">
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Escalated</p>
                <p class="text-4xl font-black text-red-500">{escalated_count}</p>
            </div>
            <div class="bg-white rounded-lg shadow-md p-6 text-center border-t-4 border-green-600">
                <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">Clear</p>
                <p class="text-4xl font-black text-green-600">{clear_count}</p>
            </div>
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
    print(f"Dashboard written to output/dashboard.html ({escalated_count} escalated, {clear_count} clear, {len(trace_lines)} trace events)")

    # Also render a markdown version for PDF/PPTX export compatibility
    md_lines = [
        f"# Global Executive Board Report — Cyber Risk Posture\n",
        f"**Date:** {report_date} | **Classification:** Board Confidential | **Total Global Value at Cyber Risk (VaCR):** ${total_vacr:,.0f}\n",
        f"---\n",
        f"## Executive Summary\n",
        f"{summary}\n",
        f"---\n",
        f"## Escalated Regions\n",
    ]
    for r in threat_regions:
        scenarios = ", ".join(r.get("scenario_types", []))
        if not scenarios and r.get("primary_scenario"):
            scenarios = r["primary_scenario"]
        md_lines.append(f"### {r.get('region', 'Unknown')} — ${r.get('vacr_exposure', 0):,.0f} at Risk | Severity: {r.get('severity', 'N/A')}\n")
        md_lines.append(f"**Primary Scenario:** {scenarios}\n")
        md_lines.append(f"{r.get('strategic_assessment', '')}\n")

    md_lines.append("## Clear Regions\n")
    for region in REGIONS:
        rd = region_data.get(region, {})
        if rd.get("status") == "clear":
            md_lines.append(f"### {region} — Clear\n")
            md_lines.append("No credible threat identified. Region operating within normal risk parameters.\n")

    md_lines.append("---\n")
    md_lines.append(f"*Regions escalated: {escalated_count} | Regions clear: {clear_count} | Source: Enterprise CRQ Application*\n")

    with open("output/global_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print("Markdown export written to output/global_report.md")


if __name__ == "__main__":
    build()
