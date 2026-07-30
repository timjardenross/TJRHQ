#!/usr/bin/env python3
"""Log the domain-toggled workbench implementation as an autonomous action."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from platform_runtime.lib.autonomy_log import log_autonomous_action
from platform_runtime.lib.supabase_client import get_client

def main():
    sb = get_client()
    if not sb:
        print("ERROR: Could not initialize Supabase client")
        return False
    
    success = log_autonomous_action(
        supabase_client=sb,
        actor="CLAUDE",
        action="Implement domain-toggled Intelligence Workbench for Health + Operational Intelligence modes",
        rationale="Health Intelligence → Operational Intelligence convergence (Phase 1). Toggle in UI top-right corner switches between separate domain views. Health mode uses simple commit/discard workflow (no escalation). Aligns with Architecture Decision Option A.",
        commit_sha="b0e7894a",
        branch="claude/executive-staff-model-36k492",
        mission_ref="HEALTH-INTEL-OPERATIONAL-CONVERGENCE-PHASE-1",
    )
    
    if success:
        print("✓ Autonomous action logged successfully")
        return True
    else:
        print("✗ Failed to log autonomous action")
        return False

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
