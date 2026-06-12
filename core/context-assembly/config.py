import os
from pathlib import Path

REPO_ROOT = Path(os.getenv("USSTJROS_REPO", Path(__file__).resolve().parents[2]))

# Existing paths
MISSIONS_ACTIVE   = REPO_ROOT / "Missions" / "Active"
MISSIONS_COMPLETE = REPO_ROOT / "Missions" / "Completed"
ADR_DIR           = REPO_ROOT / "core" / "governance" / "architecture-decision-records"
CAPABILITY_FILE   = REPO_ROOT / "capability-inventory.md"
DECISIONS_DIR     = REPO_ROOT / "governance" / "decisions"  # DECISION-*.md moved here P6B

# WP3: Health context
HEALTH_SUMMARY_PATH = REPO_ROOT / "memory" / "Health-Summary.md"

# WP4: Decision and log context
DECISION_REGISTER_PATH = REPO_ROOT / "memory" / "Decision-Register.md"
CAPTAINS_LOG_DIR       = REPO_ROOT / "Captains-Log"

# WP6: Python context service port (consumed by JS backend)
CONTEXT_SERVICE_PORT = int(os.getenv("CONTEXT_SERVICE_PORT", "5001"))

CONFIDENCE_THRESHOLD = 0.5
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

SCHEMAS_DIR = Path(__file__).parent / "schemas"
