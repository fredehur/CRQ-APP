"""Centralised path constants for the CRQ pipeline."""
from pathlib import Path

REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]

SEVERITY_MAP = {"CRITICAL": 3, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

# Data paths
COMPANY_PROFILE_PATH = "data/company_profile.json"
MASTER_SCENARIOS_PATH = "data/master_scenarios.json"
MOCK_CRQ_DATABASE_PATH = "data/mock_crq_database.json"
MOCK_FEEDS_DIR = "data/mock_threat_feeds"

# ── Root directories ──────────────────────────────────────────────────────────
OUTPUT_DIR        = Path("output")
DELIVERABLES_DIR  = OUTPUT_DIR / "deliverables"
PIPELINE_DIR      = OUTPUT_DIR / "pipeline"
VALIDATION_DIR    = OUTPUT_DIR / "validation"
LOGS_DIR          = OUTPUT_DIR / "logs"
REGIONAL_DIR      = OUTPUT_DIR / "regional"
RUNS_DIR          = OUTPUT_DIR / "runs"

# ── Deliverables ──────────────────────────────────────────────────────────────
CISO_BRIEF_PATH   = DELIVERABLES_DIR / "ciso_brief.docx"
BOARD_PDF_PATH    = DELIVERABLES_DIR / "board_report.pdf"
BOARD_PPTX_PATH   = DELIVERABLES_DIR / "board_report.pptx"

# ── Pipeline artifacts ────────────────────────────────────────────────────────
DASHBOARD_PATH         = PIPELINE_DIR / "dashboard.html"
GLOBAL_REPORT_JSON     = PIPELINE_DIR / "global_report.json"
GLOBAL_REPORT_MD       = PIPELINE_DIR / "global_report.md"
MANIFEST_PATH          = PIPELINE_DIR / "run_manifest.json"
ROUTING_PATH           = PIPELINE_DIR / "routing_decisions.json"
TREND_BRIEF_PATH       = PIPELINE_DIR / "trend_brief.json"
TREND_ANALYSIS_PATH    = PIPELINE_DIR / "trend_analysis.json"
FEEDBACK_TRENDS_PATH   = PIPELINE_DIR / "feedback_trends.json"
HISTORY_PATH           = PIPELINE_DIR / "history.json"

# ── Legacy aliases (kept for backwards compatibility) ─────────────────────────
GLOBAL_REPORT_PATH = GLOBAL_REPORT_JSON

# ── Validation ────────────────────────────────────────────────────────────────
VALIDATION_CACHE_DIR      = VALIDATION_DIR / "cache"
VALIDATION_FLAGS_JSON     = VALIDATION_DIR / "flags.json"
VALIDATION_FLAGS_MD       = VALIDATION_DIR / "flags.md"
VALIDATION_CANDIDATES_JSON = VALIDATION_DIR / "candidates.json"

# ── Logs ──────────────────────────────────────────────────────────────────────
TRACE_LOG_PATH     = LOGS_DIR / "system_trace.log"
TOOL_TRACE_LOG_PATH = LOGS_DIR / "tool_trace.log"
