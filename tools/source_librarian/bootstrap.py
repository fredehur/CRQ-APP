"""One-shot Haiku-driven intent yaml bootstrap.

Reads data/registers/<register_id>.json and asks Haiku to generate an initial
intent yaml. The user edits the yaml manually and commits it. This is NEVER
run as part of run_snapshot."""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

try:
    import anthropic  # type: ignore
except Exception:
    anthropic = None  # tests inject a mock module via patch

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTERS_DIR = REPO_ROOT / "data" / "registers"
INTENTS_DIR = REPO_ROOT / "data" / "research_intents"

HAIKU_MODEL = "claude-haiku-4-5-20251001"

_BOOTSTRAP_PROMPT = """\
You are a research librarian setting up a per-scenario reading list config.

Given the risk register JSON below, produce a YAML intent file describing the
threat / asset / industry terms a search engine should look for to find
authoritative reports for each scenario.

REQUIRED YAML SHAPE:

register_id: <id>
register_name: <name>
industry: <slug>
sub_industry: <slug>
geography:
  primary: [list of regions]
  secondary: [list of regions]
scenarios:
  <SCENARIO_ID>:
    name: "<scenario_name>"
    threat_terms: [3-5 short phrases describing the attack type]
    asset_terms: [3-5 short phrases describing the targeted asset]
    industry_terms: [3-5 short phrases describing the industry vertical]
    time_focus_years: 2 or 3
    notes: |
      One paragraph of analyst notes.
query_modifiers:
  news_set:
    - "{{threat}} {{asset}} attack {{year}}"
    - "{{industry}} {{threat}} {{year}}"
    - "{{threat}} {{asset}} {{industry}}"
  doc_set:
    - "{{threat}} {{asset}} report pdf"
    - "{{industry}} {{threat}} assessment"
    - "{{threat}} {{asset}} impact cost"

Output ONLY valid yaml. No prose, no markdown fences.

REGISTER JSON:
{register_json}
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def bootstrap_intent_yaml(register_id: str) -> Path:
    """Generate an intent yaml for a register via Haiku. Returns the written path."""
    reg_path = REGISTERS_DIR / f"{register_id}.json"
    if not reg_path.exists():
        raise FileNotFoundError(f"register not found: {reg_path}")

    register_json = reg_path.read_text(encoding="utf-8")
    if anthropic is None:
        raise RuntimeError("anthropic SDK not available")

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": _BOOTSTRAP_PROMPT.format(register_json=register_json),
        }],
    )
    text = (resp.content[0].text or "").strip()
    text = _strip_fences(text)

    try:
        yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Haiku returned invalid yaml: {exc}\n\n{text[:500]}") from exc

    INTENTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = INTENTS_DIR / f"{register_id}.yaml"
    out_path.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
    return out_path
