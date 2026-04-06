# Task 4 — RSM Brief Fallback Contract
**Assigned to:** Session B (runs in parallel with Task 3)
**Blocks:** Nothing
**Blocked by:** Nothing — start immediately (fully independent)
**Master plan:** `docs/superpowers/plans/2026-04-05-master-build-plan.md`

---

## What You Are Building

The RSM formatter agent has an incomplete skill contract. It declares 6 inputs, 3 of which are frequently absent (`seerist_signals.json`, `region_delta.json`, `audience_config.json`). When these are missing, the agent guesses what to do. Fallback routing is code territory — the agent should receive clean inputs and write.

You will:
1. Create `tools/rsm_input_builder.py` — code-owned fallback handler that assembles clean inputs for the agent
2. Update `rsm-formatter-agent.md` with a typed skill contract: declared required/optional inputs, explicit fallback per optional input, quality gate

This task is completely independent of Tasks 1–3. Start immediately.

---

## Files to Read First

Read these in full before touching anything:

1. `.claude/agents/rsm-formatter-agent.md` — understand current input list and structure
2. `tools/notifier.py` — understand how RSM briefs are currently dispatched
3. `output/regional/apac/` — check which files actually exist vs. which are declared as inputs
4. `data/audience_config.json` — check if this file exists and what it contains
5. `data/aerowind_sites.json` — check if this file exists
6. `output/regional/apac/region_delta.json` — check if this exists
7. `output/regional/apac/seerist_signals.json` — check if this exists

**Key question to answer before building:** Which of the 6 inputs reliably exist after a pipeline run, and which are frequently absent? Verify against the actual `output/` directory.

---

## Change 1 — Create `tools/rsm_input_builder.py`

New file. Code owns all fallback routing. The agent never decides what to do when a file is missing.

```python
"""
tools/rsm_input_builder.py

Assembles the RSM agent input manifest with explicit fallbacks.
Code owns the fallback routing. Agent owns the writing.

Usage:
    from tools.rsm_input_builder import build_rsm_inputs
    manifest = build_rsm_inputs("APAC", "output")
    # manifest is a dict of {input_name: path_or_none, fallback_flags: {input: bool}}
"""
from __future__ import annotations

import json
from pathlib import Path


def build_rsm_inputs(region: str, output_dir: str = "output") -> dict:
    """
    Build the input manifest for rsm-formatter-agent.

    Returns:
        {
            "region": "APAC",
            "required": {
                "geo_signals": "/path/or/None",
                "cyber_signals": "/path/or/None",
                "data_json": "/path/or/None",
            },
            "optional": {
                "seerist_signals": "/path/or/None",
                "region_delta": "/path/or/None",
                "aerowind_sites": "/path/or/None",
                "audience_config": "/path/or/None",
            },
            "fallback_flags": {
                "seerist_signals": True,   # True = file absent, fallback in use
                "region_delta": True,
                "aerowind_sites": False,
                "audience_config": False,
            },
            "fallback_instructions": {
                "seerist_signals": "Use geo_signals.json for PHYSICAL & GEO section.",
                "region_delta": "Write 'No comparative data for this period.' in SITUATION. Write 'No pre-media anomalies detected this period.' in EARLY WARNING.",
            }
        }
    """
    # Use absolute paths from project root — relative Path("data") breaks if CWD is not project root
    _PROJECT_ROOT = Path(__file__).parent.parent
    region_lower = region.lower()
    base = _PROJECT_ROOT / output_dir / "regional" / region_lower
    data_dir = _PROJECT_ROOT / "data"

    # ── Required inputs ──────────────────────────────────────────────
    geo_path    = base / "geo_signals.json"
    cyber_path  = base / "cyber_signals.json"
    data_path   = base / "data.json"

    required = {
        "geo_signals":   str(geo_path)   if geo_path.exists()   else None,
        "cyber_signals": str(cyber_path) if cyber_path.exists() else None,
        "data_json":     str(data_path)  if data_path.exists()  else None,
    }

    missing_required = [k for k, v in required.items() if v is None]
    if missing_required:
        raise FileNotFoundError(
            f"RSM input builder: required files missing for {region}: {missing_required}"
        )

    # ── Optional inputs ──────────────────────────────────────────────
    seerist_path      = base / "seerist_signals.json"
    delta_path        = base / "region_delta.json"
    sites_path        = data_dir / "aerowind_sites.json"
    audience_path     = data_dir / "audience_config.json"

    optional = {
        "seerist_signals": str(seerist_path)  if seerist_path.exists()  else None,
        "region_delta":    str(delta_path)    if delta_path.exists()    else None,
        "aerowind_sites":  str(sites_path)    if sites_path.exists()    else None,
        "audience_config": str(audience_path) if audience_path.exists() else None,
    }

    fallback_flags = {k: v is None for k, v in optional.items()}

    # ── Fallback instructions (passed to agent as context) ───────────
    fallback_instructions = {}
    if fallback_flags["seerist_signals"]:
        fallback_instructions["seerist_signals"] = (
            "seerist_signals.json is absent. "
            "Use geo_signals.json for the PHYSICAL & GEOPOLITICAL section."
        )
    if fallback_flags["region_delta"]:
        fallback_instructions["region_delta"] = (
            "region_delta.json is absent. "
            "Write 'No comparative data for this period.' in SITUATION. "
            "Write 'No pre-media anomalies detected this period.' in EARLY WARNING."
        )
    if fallback_flags["aerowind_sites"]:
        fallback_instructions["aerowind_sites"] = (
            "aerowind_sites.json is absent. "
            "Refer to 'AeroGrid regional operations' generically."
        )
    if fallback_flags["audience_config"]:
        fallback_instructions["audience_config"] = (
            "audience_config.json is absent. "
            "Address brief to 'Regional Security Manager' generically."
        )

    return {
        "region": region,
        "required": required,
        "optional": optional,
        "fallback_flags": fallback_flags,
        "fallback_instructions": fallback_instructions,
    }


def manifest_summary(manifest: dict) -> str:
    """Return a human-readable summary for passing to the agent as context."""
    lines = [f"RSM INPUT MANIFEST — {manifest['region']}"]
    lines.append("\nRequired inputs (all present):")
    for k, v in manifest["required"].items():
        lines.append(f"  {k}: {v}")
    lines.append("\nOptional inputs:")
    for k, v in manifest["optional"].items():
        status = "ABSENT — fallback active" if manifest["fallback_flags"][k] else "present"
        lines.append(f"  {k}: {status}")
    if manifest["fallback_instructions"]:
        lines.append("\nFallback instructions for agent:")
        for k, instr in manifest["fallback_instructions"].items():
            lines.append(f"  [{k}] {instr}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    region = sys.argv[1] if len(sys.argv) > 1 else "APAC"
    manifest = build_rsm_inputs(region)
    print(manifest_summary(manifest))
```

---

## Change 2 — Update `rsm-formatter-agent.md`

Replace the current input file list (Step 1 — Read input files) with a typed skill contract.

**Replace the current Step 1 section with:**

```markdown
### Input Contract

**Required (pipeline always produces these):**
- `output/regional/{region_lower}/geo_signals.json` — geopolitical signals
- `output/regional/{region_lower}/cyber_signals.json` — cyber threat signals
- `output/regional/{region_lower}/data.json` — admiralty, primary_scenario, financial_rank, velocity

**Optional (use fallback if absent — fallback instructions passed in manifest):**
- `output/regional/{region_lower}/seerist_signals.json`
  → if absent: use `geo_signals.json` for PHYSICAL & GEOPOLITICAL section
- `output/regional/{region_lower}/region_delta.json`
  → if absent: SITUATION = "No comparative data for this period."
               EARLY WARNING = "No pre-media anomalies detected this period."
- `data/aerowind_sites.json`
  → if absent: refer to "AeroGrid regional operations" generically
- `data/audience_config.json`
  → if absent: address brief to "Regional Security Manager"

**Inputs are pre-validated by `rsm_input_builder.py` before this agent runs.**

The orchestrator calls `manifest_summary(manifest)` and **prepends the result to the agent task prompt** before spawning the agent via the Agent tool. The agent receives a prompt that begins with:

```
RSM INPUT MANIFEST — {REGION}

Required inputs (all present):
  geo_signals: output/regional/apac/geo_signals.json
  ...

Optional inputs:
  seerist_signals: ABSENT — fallback active
  region_delta: ABSENT — fallback active
  ...

Fallback instructions for agent:
  [seerist_signals] seerist_signals.json is absent. Use geo_signals.json for PHYSICAL & GEO section.
  [region_delta] region_delta.json is absent. Write 'No comparative data for this period.' ...

--- BEGIN TASK ---
REGION: {REGION}
PRODUCT_TYPE: weekly_intsum
BRIEF_PATH: output/regional/{region}/rsm_brief_{region}_{date}.md
```

Read the manifest at the top. Follow fallback instructions exactly for any absent optional inputs.
```

**Update the quality gate** (stop hook section or self-validation checklist):

Add: "Brief must be structurally complete — all section headers (SITUATION, PHYSICAL & GEOPOLITICAL, CYBER, EARLY WARNING, ASSESSMENT, WATCH LIST) must be present even when optional inputs are absent."

**Skill contract block** — add at top of agent file after the frontmatter:

```markdown
## Skill Contract

| Field | Value |
|---|---|
| **Purpose** | Format weekly INTSUM and flash alerts for ex-military RSMs from pipeline intelligence data |
| **Required inputs** | geo_signals.json, cyber_signals.json, data.json |
| **Optional inputs** | seerist_signals.json, region_delta.json, aerowind_sites.json, audience_config.json |
| **Outputs** | rsm_brief_{region}_{date}.md, rsm_flash_{region}_{datetime}.md |
| **Quality gate** | All section headers present. Brief written even if 3 optional inputs absent. Stop hook: rsm-formatter-stop.py |
| **Fallback owner** | Code (`rsm_input_builder.py`) — agent never decides what to do when a file is missing |
```

---

## Done Criteria

- [ ] `tools/rsm_input_builder.py` exists and imports cleanly
- [ ] `build_rsm_inputs("APAC")` runs without error (even if Seerist/delta absent)
- [ ] `build_rsm_inputs()` raises `FileNotFoundError` if a required input is missing
- [ ] `manifest_summary()` returns a readable string with fallback instructions
- [ ] `rsm-formatter-agent.md` has the skill contract block at the top
- [ ] `rsm-formatter-agent.md` Step 1 shows typed required/optional inputs with explicit fallback per optional
- [ ] Quality gate updated: all section headers required even with absent optional inputs
- [ ] Run `uv run python tools/rsm_input_builder.py APAC` — prints manifest summary, no error
