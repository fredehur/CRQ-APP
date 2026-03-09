"""Shared constants for CRQ pipeline tools."""

REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]

SEVERITY_MAP = {"CRITICAL": 3, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

# Data paths
COMPANY_PROFILE_PATH = "data/company_profile.json"
MASTER_SCENARIOS_PATH = "data/master_scenarios.json"
MOCK_CRQ_DATABASE_PATH = "data/mock_crq_database.json"
MOCK_FEEDS_DIR = "data/mock_threat_feeds"

# Output paths
OUTPUT_DIR = "output"
REGIONAL_DIR = "output/regional"
TRACE_LOG_PATH = "output/system_trace.log"
MANIFEST_PATH = "output/run_manifest.json"
GLOBAL_REPORT_PATH = "output/global_report.json"
