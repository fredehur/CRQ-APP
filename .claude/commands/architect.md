CRQ Multi-Agent Geopolitical Intelligence System — Architect Build Spec

---
name: architect
description: Autonomously builds the entire CRQ Multi-Agent Geopolitical Intelligence System.
tools: Bash, Write, Read
model: opus
---

# Token-Safe Build Strategy

Build and test in 4 phases. Complete and verify each phase before proceeding to the next. Run `/compact` between phases to conserve context window.

After each phase passes its tests, run the jCodeMunch MCP index so Claude can navigate new files by symbol rather than reading full files into context:
```
mcp__jcodemunch-mcp__index_folder (path: ".")
```
This keeps token usage low in later phases.

**Phase 1 — Data & Validator** (Steps 1–2)
Build: mock data + CRQ database + schema validator.
Test: `uv run python .claude/hooks/validators/crq-schema-validator.py data/mock_crq_database.json`
✅ Pass: `SCHEMA VALID: 5 scenarios across 5 regions (APAC, AME, LATAM, MED, NCE).`

**Phase 2 — Gatekeeper** (Step 3 partial + Step 5a)
Build: `regional_search.py`, `geopolitical_context.py`, `threat_scorer.py`, and `gatekeeper-agent.md`.
Test: Run `/gatekeeper-agent` for APAC with asset `SAP ERP`.
✅ Pass: Single word `YES` — no explanation, no prose.

**Phase 3 — Regional Analyst + Auditor** (Step 4a + Step 5b)
Build: `jargon-auditor.py` and `regional-analyst-agent.md`.
Test: Run `/regional-analyst-agent` for APAC, then: `uv run python .claude/hooks/validators/jargon-auditor.py output/regional_draft_current.md current`
✅ Pass: `AUDIT PASSED: [current] report is clean and compliant.` Draft contains `$42,000,000` and zero SOC/technical terms.

**Phase 4 — Orchestrator + Global + Exports** (Steps 3d–3f + Steps 5c–5d + Step 6)
Build: `report_differ.py`, `export_pdf.py`, `export_pptx.py`, `global-analyst-agent.md`, `run-crq.md`.
Test: Run `/run-crq` and verify all outputs.
✅ Pass: 5 regional drafts in `output/regional/`, `global_report.md` with aggregated dollar figure, `dashboard.html` renders in browser, `board_report.pdf` and `board_report.pptx` are non-zero bytes.

# Testing Checklist Per Phase

**Phase 1**
- `crq-schema-validator.py` exits 0 with SCHEMA VALID message
- All 5 regions present, all required JSON keys present

**Phase 2**
- `regional_search.py APAC --mock` prints threat headlines with severity
- `geopolitical_context.py APAC` prints risk bullets with confidence level
- `/gatekeeper-agent` returns exactly `YES` or `NO` — nothing else

**Phase 3**
- `output/regional_draft_current.md` is created after `/regional-analyst-agent` runs
- Auditor exits 0 (AUDIT PASSED)
- Draft contains VaCR dollar figure, zero words: CVE, TTP, IoC, lateral, MITRE, hash
- Circuit breaker file `output/.retries/current.retries` is deleted on pass

**Phase 4**
- All 5 `output/regional/*_draft.md` files exist
- `output/pipeline/global_report.md` contains aggregated dollar exposure figure
- `output/pipeline/dashboard.html` opens in browser without broken layout
- `output/deliverables/board_report.pdf` and `output/deliverables/board_report.pptx` are non-zero bytes
- `report_differ.py` shows systemic themes across 2+ regions

---

# Directives

You are the Lead AI Project Architect. Execute every step below in exact sequence. Use Bash to create directories and run commands. Use Write to create files. Do not ask for permission. Do not skip any step.

## CRITICAL YAML RULE
All generated `.md` subagent files MUST use ONLY these valid frontmatter keys: name, description, tools, model, hooks.
Do NOT use: color, argument-hint, or any other non-standard key.

---

## Step 1: Initialize Environment & Directories

Run these commands in sequence:

1. `uv init`
2. `uv add fpdf2 python-pptx python-dotenv`
3. `mkdir -p .claude/commands .claude/hooks/validators data/mock_threat_feeds tools output/regional output/.retries`

---

## Step 2: Write Mock Data

### 2a. Write to `data/mock_crq_database.json`

```json
{
    "APAC": [
        {
            "scenario_id": "APAC-001",
            "department": "Supply Chain",
            "scenario_name": "Semiconductor Supply Disruption",
            "critical_assets": ["SAP ERP", "Supplier Portal"],
            "value_at_cyber_risk": "$42,000,000"
        }
    ],
    "AME": [
        {
            "scenario_id": "AME-001",
            "department": "Financial Operations",
            "scenario_name": "Critical Infrastructure Attack",
            "critical_assets": ["Salesforce CRM", "Okta SSO"],
            "value_at_cyber_risk": "$28,000,000"
        }
    ],
    "LATAM": [
        {
            "scenario_id": "LATAM-001",
            "department": "Regional Sales",
            "scenario_name": "Banking System Ransomware Wave",
            "critical_assets": ["Payment Gateway", "Customer Database"],
            "value_at_cyber_risk": "$8,500,000"
        }
    ],
    "MED": [
        {
            "scenario_id": "MED-001",
            "department": "Logistics",
            "scenario_name": "Port Infrastructure Disruption",
            "critical_assets": ["Logistics Platform", "Customs System"],
            "value_at_cyber_risk": "$19,000,000"
        }
    ],
    "NCE": [
        {
            "scenario_id": "NCE-001",
            "department": "Energy Division",
            "scenario_name": "Energy Grid Targeting Campaign",
            "critical_assets": ["Operations Platform", "Remote Monitoring System"],
            "value_at_cyber_risk": "$33,000,000"
        }
    ]
}
```

### 2b. Write to `data/mock_threat_feeds/apac_threats.json`

```json
{
    "region": "APAC",
    "threats": [
        {
            "headline": "State-aligned group intensifies targeting of Taiwan-based semiconductor suppliers",
            "severity": 3,
            "business_context": "Export restrictions and coordinated disruption threaten semiconductor availability, placing Q3 production targets at direct risk."
        },
        {
            "headline": "Coordinated reconnaissance detected across Australian logistics and energy sectors",
            "severity": 2,
            "business_context": "Persistent access campaigns targeting port and energy infrastructure suggest preparation for disruptive action during peak trade periods."
        }
    ]
}
```

### 2c. Write to `data/mock_threat_feeds/ame_threats.json`

```json
{
    "region": "AME",
    "threats": [
        {
            "headline": "US financial sector on heightened alert following coordinated infrastructure targeting",
            "severity": 3,
            "business_context": "Disruption to financial clearing systems and identity platforms could halt revenue operations and delay quarterly close processes."
        },
        {
            "headline": "Ransomware campaign sweeping North American retail and logistics sectors",
            "severity": 2,
            "business_context": "Cross-sector campaign demonstrates capability to disrupt customer-facing operations and interrupt sales cycles."
        }
    ]
}
```

### 2d. Write to `data/mock_threat_feeds/latam_threats.json`

```json
{
    "region": "LATAM",
    "threats": [
        {
            "headline": "Government-linked ransomware activity targeting banking infrastructure across Brazil and Mexico",
            "severity": 2,
            "business_context": "Payment processing disruptions in key LATAM markets risk delayed revenue collection and customer trust erosion."
        },
        {
            "headline": "Currency volatility compounded by cyber-enabled financial fraud surge",
            "severity": 1,
            "business_context": "Combined macroeconomic and cyber pressure increases exposure for regional operations dependent on local banking systems."
        }
    ]
}
```

### 2e. Write to `data/mock_threat_feeds/med_threats.json`

```json
{
    "region": "MED",
    "threats": [
        {
            "headline": "Major Mediterranean port operations disrupted by coordinated cyber event",
            "severity": 3,
            "business_context": "Shipping delays at key Mediterranean ports create cascading supply chain disruption, directly threatening product delivery commitments."
        },
        {
            "headline": "Energy infrastructure in Southern Europe targeted amid regional conflict escalation",
            "severity": 2,
            "business_context": "Energy supply instability threatens operational continuity for manufacturing and logistics facilities across the MED region."
        }
    ]
}
```

### 2f. Write to `data/mock_threat_feeds/nce_threats.json`

```json
{
    "region": "NCE",
    "threats": [
        {
            "headline": "State-sponsored campaign targets Northern European energy grid operators",
            "severity": 3,
            "business_context": "Targeting of energy distribution infrastructure poses direct risk to operational continuity for facilities across Northern and Central Europe."
        },
        {
            "headline": "EU sanctions enforcement triggers retaliatory cyber operations against corporate networks",
            "severity": 2,
            "business_context": "Retaliatory activity linked to sanctions creates elevated risk for multinational corporations with visible EU-based operations."
        }
    ]
}
```

---

## Step 3: Write Tools

### 3a. Write to `tools/regional_search.py`

```python
import sys
import json
import os

def search(region, mock=True):
    if not mock:
        print("Live search not configured. Re-run with --mock flag.")
        sys.exit(1)
    feed_path = f"data/mock_threat_feeds/{region.lower()}_threats.json"
    if not os.path.exists(feed_path):
        print(f"No threat feed found for region: {region}")
        sys.exit(0)
    with open(feed_path) as f:
        data = json.load(f)
    threats = data.get("threats", [])
    if not threats:
        print(f"No active threats recorded for {region}.")
        return
    print(f"=== Threat Intelligence: {region} ===")
    for t in threats:
        print(f"\n[Severity {t['severity']}/3] {t['headline']}")
        print(f"Business Context: {t['business_context']}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: regional_search.py <REGION> [--mock]")
        sys.exit(1)
    region = sys.argv[1].upper()
    mock = "--mock" in sys.argv
    search(region, mock)
```

### 3b. Write to `tools/geopolitical_context.py`

```python
import sys

CONTEXT = {
    "APAC": {
        "risks": [
            "Taiwan Strait tensions at multi-year high",
            "Semiconductor export controls tightening",
            "ASEAN supply chain fragmentation accelerating"
        ],
        "confidence": "HIGH"
    },
    "AME": {
        "risks": [
            "US critical infrastructure on heightened federal alert",
            "Ransomware targeting financial and identity systems",
            "Federal contractor data exposure risk elevated"
        ],
        "confidence": "HIGH"
    },
    "LATAM": {
        "risks": [
            "Banking sector ransomware wave active across Brazil and Mexico",
            "Government portal breaches creating downstream third-party risk",
            "Currency instability amplifying business continuity exposure"
        ],
        "confidence": "MEDIUM"
    },
    "MED": {
        "risks": [
            "Port and shipping infrastructure under active targeting",
            "Energy supply disruption risk from regional conflict escalation",
            "Undersea cable infrastructure at elevated risk"
        ],
        "confidence": "HIGH"
    },
    "NCE": {
        "risks": [
            "EU-Russia sanctions creating direct retaliatory cyber risk",
            "Energy grid operators targeted by state-sponsored campaigns",
            "NATO eastern flank on sustained elevated alert"
        ],
        "confidence": "HIGH"
    }
}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: geopolitical_context.py <REGION>")
        sys.exit(1)
    region = sys.argv[1].upper()
    ctx = CONTEXT.get(region)
    if not ctx:
        print(f"No context data available for region: {region}")
        sys.exit(0)
    print(f"=== Geopolitical Risk Context: {region} (Confidence: {ctx['confidence']}) ===")
    for risk in ctx["risks"]:
        print(f"  - {risk}")
```

### 3c. Write to `tools/threat_scorer.py`

```python
import sys
import json
import os

def score(region):
    feed_path = f"data/mock_threat_feeds/{region.lower()}_threats.json"
    if not os.path.exists(feed_path):
        print(1)
        return
    with open(feed_path) as f:
        data = json.load(f)
    threats = data.get("threats", [])
    if not threats:
        print(1)
        return
    print(max(t.get("severity", 1) for t in threats))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(1)
        sys.exit(0)
    score(sys.argv[1].upper())
```

### 3d. Write to `tools/report_differ.py`

```python
import os
import re

REGIONS = ["apac", "ame", "latam", "med", "nce"]
STOPWORDS = {"the", "and", "that", "this", "with", "from", "have", "will",
             "their", "which", "been", "into", "across", "business", "risk"}

def load_reports():
    reports = {}
    for region in REGIONS:
        path = f"output/regional/{region}_draft.md"
        if os.path.exists(path):
            with open(path) as f:
                reports[region] = f.read().lower()
    return reports

def extract_keywords(text):
    words = re.findall(r'\b[a-z]{7,}\b', text)
    return set(w for w in words if w not in STOPWORDS)

def diff_reports():
    reports = load_reports()
    if not reports:
        print("No approved regional reports found in output/regional/")
        return
    word_map = {}
    for region, content in reports.items():
        for word in extract_keywords(content):
            word_map.setdefault(word, []).append(region)

    print("=== CROSS-REGIONAL DELTA BRIEF ===\n")
    print(f"Active regions: {', '.join(r.upper() for r in reports)}\n")

    print("SYSTEMIC THEMES (present in 2+ regions):")
    shown = 0
    for word, regions in sorted(word_map.items(), key=lambda x: -len(x[1])):
        if len(regions) < 2 or shown >= 10:
            continue
        print(f"  - '{word}' found in: {', '.join(r.upper() for r in regions)}")
        shown += 1

    print("\nREGION-UNIQUE SIGNALS:")
    for region in reports:
        unique = [w for w, r in word_map.items() if r == [region]]
        print(f"  {region.upper()}: {len(unique)} unique signals")

if __name__ == "__main__":
    diff_reports()
```

### 3e. Write to `tools/export_pdf.py`

```python
import sys
from fpdf import FPDF

def export(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    pdf = FPDF()
    pdf.set_margins(20, 20, 20)
    pdf.add_page()
    for line in lines:
        line = line.rstrip()
        if line.startswith('# '):
            pdf.set_font("Helvetica", 'B', 18)
            pdf.multi_cell(0, 12, line[2:])
            pdf.ln(2)
        elif line.startswith('## '):
            pdf.set_font("Helvetica", 'B', 14)
            pdf.multi_cell(0, 10, line[3:])
            pdf.ln(1)
        elif line.startswith('- ') or line.startswith('* '):
            pdf.set_font("Helvetica", size=10)
            pdf.multi_cell(0, 7, f"  \u2022 {line[2:]}")
        elif line:
            pdf.set_font("Helvetica", size=11)
            pdf.multi_cell(0, 7, line)
        else:
            pdf.ln(4)
    pdf.output(output_path)
    print(f"PDF exported: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: export_pdf.py <input.md> <output.pdf>")
        sys.exit(1)
    export(sys.argv[1], sys.argv[2])
```

### 3f. Write to `tools/export_pptx.py`

```python
import sys
from pptx import Presentation

def export(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    prs = Presentation()
    layout = prs.slide_layouts[1]
    current_title = "Executive Brief"
    current_body = []

    def flush_slide():
        if not current_body:
            return
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = current_title
        slide.placeholders[1].text_frame.text = "\n".join(current_body)

    for line in lines:
        line = line.rstrip()
        if line.startswith('# ') or line.startswith('## '):
            flush_slide()
            current_title = line.lstrip('#').strip()
            current_body = []
        elif line.startswith('- ') or line.startswith('* '):
            current_body.append(f"\u2022 {line[2:]}")
        elif line:
            current_body.append(line)
    flush_slide()
    prs.save(output_path)
    print(f"PowerPoint exported: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: export_pptx.py <input.md> <output.pptx>")
        sys.exit(1)
    export(sys.argv[1], sys.argv[2])
```

---

## Step 4: Write Hooks

### 4a. Write to `.claude/hooks/validators/jargon-auditor.py`

This hook takes two arguments: the report file path and a label (used for the region-scoped circuit breaker file).

```python
import sys
import re
import os

FORBIDDEN_CYBER = [
    r'cve-\d{4}-\d+',
    r'\bip address\b',
    r'\bmalware hash\b',
    r'\bsha256\b',
    r'\bmd5 hash\b',
]

FORBIDDEN_SOC = [
    r'threat actor ttps',
    r'indicators? of compromise',
    r'\biocs?\b',
    r'mitre att.ck',
    r'\blateral movement\b',
    r'command and control',
    r'\bc2 server\b',
    r'persistence mechanism',
    r'zero.day exploit',
    r'privilege escalation',
]

FORBIDDEN_BUDGET = [
    'allocate budget', 'purchase', 'buy tools', 'hire a ', 'procure'
]

def audit_report(file_path, label):
    os.makedirs("output/.retries", exist_ok=True)
    retry_file = f"output/.retries/{label}.retries"
    retries = 0
    if os.path.exists(retry_file):
        try:
            retries = int(open(retry_file).read().strip())
        except ValueError:
            retries = 0

    if retries >= 3:
        print(f"AUDIT: Max retries exceeded for [{label}]. Forcing approval to break loop.", file=sys.stderr)
        os.remove(retry_file)
        sys.exit(0)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().lower()
    except FileNotFoundError:
        print(f"AUDIT ERROR: Report not found at {file_path}", file=sys.stderr)
        sys.exit(1)

    fail_msg = None

    for pattern in FORBIDDEN_CYBER:
        if re.search(pattern, content):
            fail_msg = "AUDIT FAILED: Technical cyber jargon detected. Rewrite using business language only. No CVEs, IPs, or hashes."
            break

    if not fail_msg:
        for pattern in FORBIDDEN_SOC:
            if re.search(pattern, content):
                fail_msg = "AUDIT FAILED: SOC operational language detected. This is a board-level brief. Remove all technical security terminology."
                break

    if not fail_msg:
        if any(w in content for w in FORBIDDEN_BUDGET):
            fail_msg = "AUDIT FAILED: Unsolicited budget or procurement advice detected. Remove it entirely."

    if fail_msg:
        print(fail_msg, file=sys.stderr)
        with open(retry_file, "w") as f:
            f.write(str(retries + 1))
        sys.exit(2)

    print(f"AUDIT PASSED: [{label}] report is clean and compliant.")
    if os.path.exists(retry_file):
        os.remove(retry_file)
    sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: jargon-auditor.py <report_path> <label>")
        sys.exit(1)
    audit_report(sys.argv[1], sys.argv[2])
```

### 4b. Write to `.claude/hooks/validators/crq-schema-validator.py`

```python
import sys
import json

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
REQUIRED_KEYS = {"scenario_id", "department", "scenario_name", "critical_assets", "value_at_cyber_risk"}

def validate(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"SCHEMA ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"SCHEMA ERROR: Invalid JSON — {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict):
        print("SCHEMA ERROR: Root element must be a JSON object with region keys.", file=sys.stderr)
        sys.exit(1)

    for region, scenarios in data.items():
        if region not in VALID_REGIONS:
            print(f"SCHEMA ERROR: Unknown region '{region}'. Valid: {VALID_REGIONS}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(scenarios, list):
            print(f"SCHEMA ERROR: '{region}' must map to a list of scenarios.", file=sys.stderr)
            sys.exit(1)
        for i, scenario in enumerate(scenarios):
            missing = REQUIRED_KEYS - set(scenario.keys())
            if missing:
                print(f"SCHEMA ERROR: Scenario {i} in {region} missing fields: {missing}", file=sys.stderr)
                sys.exit(1)

    total = sum(len(v) for v in data.values())
    print(f"SCHEMA VALID: {total} scenarios across {len(data)} regions ({', '.join(data.keys())}).")
    sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: crq-schema-validator.py <path_to_json>")
        sys.exit(1)
    validate(sys.argv[1])
```

---

## Step 5: Write Subagent Files

### 5a. Write to `.claude/commands/gatekeeper-agent.md`

Write this file with the following exact content (the lines between the triple dashes are the YAML frontmatter):

name: gatekeeper-agent
description: Fast triage agent — determines if a credible geopolitical or cyber threat exists for a given region and asset.
tools: Bash
model: haiku

Body: You are a Strategic Geopolitical Triage Analyst. Your only job is to determine if a credible, active threat exists.

You will be given a REGION and a CRITICAL ASSET.

1. Run: uv run python tools/regional_search.py {REGION} --mock
2. Run: uv run python tools/geopolitical_context.py {REGION}
3. Review both outputs. If there is a credible active threat that could disrupt the critical asset, respond with ONLY the word: YES
4. If no credible threat exists, respond with ONLY the word: NO

Do not explain. Do not analyze. Return YES or NO only.

### 5b. Write to `.claude/commands/regional-analyst-agent.md`

Write this file with the following YAML frontmatter and body. The hook fires the jargon auditor on the draft report after every response. Note: the agent always writes to output/regional_draft_current.md — the orchestrator handles archiving to the region-specific path after approval.

name: regional-analyst-agent
description: Translates regional geopolitical and cyber threat intelligence into a strategic business risk brief.
tools: Bash, Write, Read
model: sonnet
hooks:
  Stop:
    - type: command
      command: "uv run python .claude/hooks/validators/jargon-auditor.py output/regional_draft_current.md current"

Body:
You are a Strategic Geopolitical and Cyber Risk Analyst. You are NOT a Security Operations Center engineer.

Your singular goal: answer "How does this threat affect the company's ability to deliver business results?"

You will receive: REGION, CRITICAL ASSET, geopolitical context, threat intelligence, severity score (1-3), and Value-at-Cyber-Risk (VaCR).

RULES — NON-NEGOTIABLE:
- Zero technical jargon: no CVEs, no IP addresses, no malware hashes
- Zero SOC language: no TTPs, no IoCs, no MITRE references, no lateral movement
- Zero budget advice: do not suggest tools, vendors, or budgets
- Financial anchor: explicitly connect the threat to the VaCR figure in dollars
- Tone: board-level executive brief, not a security report
- Length: 2-3 paragraphs. Concise and decisive.

WORKFLOW:
1. Write a strategic executive brief connecting the regional threat to the VaCR
2. Save it to output/regional_draft_current.md using the Write tool
3. The Stop hook will automatically audit your output. If it returns an error, rewrite the report and save again.

### 5c. Write to `.claude/commands/global-analyst-agent.md`

name: global-analyst-agent
description: Synthesizes all approved regional briefs into a Global Executive Board Report and static HTML dashboard.
tools: Bash, Write, Read
model: opus
hooks:
  Stop:
    - type: command
      command: "uv run python .claude/hooks/validators/jargon-auditor.py output/pipeline/global_report.md global"

Body:
You are the Chief Strategic Risk Analyst. You synthesize five regional intelligence briefs into a single global executive narrative.

You will receive: all approved regional briefs and a cross-regional delta brief.

RULES — NON-NEGOTIABLE:
- Zero technical jargon, zero SOC language, zero budget advice (same rules as regional analysts)
- Financial anchor: aggregate and contextualize all regional VaCR figures into a global risk exposure number
- Audience: C-suite and Board of Directors — assume zero technical background
- Tone: decisive, strategic, and concise

WORKFLOW:
1. Read all files in output/regional/ using the Read tool
2. Use the delta brief passed to you to identify systemic vs. region-unique themes
3. Write a cohesive Global Executive Board Report to output/pipeline/global_report.md
4. Write a styled static dashboard to output/pipeline/dashboard.html using inline CSS only — no external dependencies, no frameworks. Make it visually clean and executive-ready.
5. The Stop hook will audit global_report.md. If it fails, rewrite and save again.

### 5d. Write to `.claude/commands/run-crq.md`

name: run-crq
description: Orchestrates the full Top-Down CRQ Geopolitical Intelligence Pipeline across all five regions.
tools: Bash, Agent
model: opus

Body:
You are the Chief Risk Orchestrator. Your persona is a Strategic Geopolitical and Cyber Risk Analyst.

PHASE 0 — VALIDATE INPUT:
Run: uv run python .claude/hooks/validators/crq-schema-validator.py data/mock_crq_database.json
If validation fails, stop immediately and report the error. Do not proceed.

PHASE 1 — REGIONAL ANALYSIS:
Read data/mock_crq_database.json. For each region in order [APAC, AME, LATAM, MED, NCE]:

Step 1 — Geo-Context: Run: uv run python tools/geopolitical_context.py {REGION}
Step 2 — Triage: Delegate to gatekeeper-agent with the region name and its critical assets.
  - If gatekeeper returns NO: log "No active geopolitical trigger for {REGION}. Compute saved." and skip to next region.
  - If gatekeeper returns YES: continue to Step 3.
Step 3 — Score: Run: uv run python tools/threat_scorer.py {REGION}
  Score 1 = brief analysis needed. Score 2 = standard analysis. Score 3 = comprehensive analysis.
Step 4 — Analyze: Delegate to regional-analyst-agent. Provide: region name, critical assets, VaCR, geo-context output, threat feed output, and severity score. The agent will write to output/regional_draft_current.md and its hook will validate automatically.
Step 5 — Archive: Once the hook passes, run: cp output/regional_draft_current.md output/regional/{region_lowercase}_draft.md

PHASE 2 — CROSS-REGIONAL DIFF:
Run: uv run python tools/report_differ.py
Capture the output — this is the delta brief.

PHASE 3 — GLOBAL REPORT:
Delegate to global-analyst-agent. Provide all approved regional briefs and the delta brief.

PHASE 4 — EXPORT:
Run: uv run python tools/export_pdf.py output/pipeline/global_report.md output/deliverables/board_report.pdf
Run: uv run python tools/export_pptx.py output/pipeline/global_report.md output/deliverables/board_report.pptx

PHASE 5 — REPORT SUCCESS:
List all files generated in the output/ directory and confirm the pipeline is complete.

---

## Step 6: Verify

Run the following commands and confirm all files exist:

1. `ls -la .claude/commands`
2. `ls -la .claude/hooks/validators`
3. `ls -la tools`
4. `ls -la data/mock_threat_feeds`
5. `ls -la output/regional`

Report any missing files before declaring success.

---

## Step 7: Report Success

Tell the user:
- All files have been created and verified
- jCodeMunch MCP is already configured externally — no install needed
- Run `/run-crq` to start the full pipeline
- All 5 regions (APAC, AME, LATAM, MED, NCE) will be processed in sequence
- All outputs will be written to the output/ directory
