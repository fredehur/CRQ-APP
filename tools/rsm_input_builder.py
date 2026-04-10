"""
tools/rsm_input_builder.py

Assembles the RSM agent input manifest with explicit fallbacks.
Code owns the fallback routing. Agent owns the writing.

Usage:
    from tools.rsm_input_builder import build_rsm_inputs, manifest_summary
    manifest = build_rsm_inputs("APAC")
    # manifest is a dict: {region, required, optional, fallback_flags, fallback_instructions}
"""
from __future__ import annotations

from pathlib import Path


def build_rsm_inputs(region: str, output_dir: str = "output") -> dict:
    """
    Build the input manifest for rsm-formatter-agent.

    Returns:
        {
            "region": "APAC",
            "required": {
                "osint_signals": "/abs/path" | None,
                "data_json":     "/abs/path" | None,
            },
            "optional": {
                "seerist_signals": "/abs/path" | None,
                "region_delta":    "/abs/path" | None,
                "aerowind_sites":  "/abs/path" | None,
                "audience_config": "/abs/path" | None,
            },
            "fallback_flags": {
                "seerist_signals": True,   # True = file absent, fallback in use
                "region_delta":    True,
                "aerowind_sites":  False,
                "audience_config": False,
            },
            "fallback_instructions": {
                "seerist_signals": "...",
                "region_delta":    "...",
            }
        }

    Raises:
        FileNotFoundError: if any required input is missing.
    """
    _PROJECT_ROOT = Path(__file__).parent.parent
    region_lower = region.lower()
    base = _PROJECT_ROOT / output_dir / "regional" / region_lower
    data_dir = _PROJECT_ROOT / "data"

    # ── Required inputs ──────────────────────────────────────────────────────
    osint_path = base / "osint_signals.json"
    data_path  = base / "data.json"

    required = {
        "osint_signals": str(osint_path) if osint_path.exists() else None,
        "data_json":     str(data_path)  if data_path.exists()  else None,
    }

    missing_required = [k for k, v in required.items() if v is None]
    if missing_required:
        raise FileNotFoundError(
            f"RSM input builder: required files missing for {region}: {missing_required}"
        )

    # ── Optional inputs ───────────────────────────────────────────────────────
    seerist_path  = base / "seerist_signals.json"
    delta_path    = base / "region_delta.json"
    sites_path    = data_dir / "aerowind_sites.json"
    audience_path = data_dir / "audience_config.json"

    optional = {
        "seerist_signals": str(seerist_path)  if seerist_path.exists()  else None,
        "region_delta":    str(delta_path)    if delta_path.exists()    else None,
        "aerowind_sites":  str(sites_path)    if sites_path.exists()    else None,
        "audience_config": str(audience_path) if audience_path.exists() else None,
    }

    fallback_flags = {k: v is None for k, v in optional.items()}

    # ── Fallback instructions (passed to agent as context) ────────────────────
    fallback_instructions: dict[str, str] = {}

    if fallback_flags["seerist_signals"]:
        fallback_instructions["seerist_signals"] = (
            "seerist_signals.json is absent. "
            "Use osint_signals.json for the PHYSICAL & GEOPOLITICAL section."
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
        "region": region.upper(),
        "required": required,
        "optional": optional,
        "fallback_flags": fallback_flags,
        "fallback_instructions": fallback_instructions,
    }


def manifest_summary(manifest: dict) -> str:
    """
    Return a human-readable summary for prepending to the agent task prompt.
    The agent reads this block and follows fallback instructions exactly.
    """
    lines = [f"RSM INPUT MANIFEST — {manifest['region']}"]

    lines.append("\nRequired inputs (all present):")
    for k, v in manifest["required"].items():
        lines.append(f"  {k}: {v}")

    lines.append("\nOptional inputs:")
    for k, v in manifest["optional"].items():
        status = "ABSENT — fallback active" if manifest["fallback_flags"][k] else f"present: {v}"
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
