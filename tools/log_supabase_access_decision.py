#!/usr/bin/env python3
"""Log the Supabase Backend-Only Access decision to the decisions table.

This script creates a formal decision record in Supabase documenting the
approved backend-only access model for USS TJR.

Run with:
    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... python log_supabase_access_decision.py
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

# Fleet Engineering Review 2026-08-11: ROOT here is tools/ (this file's own
# parent), so ROOT / "tools" / "supabase" pointed at the nonexistent
# tools/tools/supabase — this bare `import client` only ever worked if
# tools/supabase was already on sys.path from something else run earlier.
# It also collided with tools/paperclip/client.py under the same bare name
# when it did resolve. Fixed to load its actual sibling unambiguously.
ROOT = Path(__file__).resolve().parent
_TOOLS_SUPABASE = ROOT / "supabase"
if str(_TOOLS_SUPABASE) not in sys.path:
    sys.path.insert(0, str(_TOOLS_SUPABASE))
from _local_import_supabase import import_sibling

_client = import_sibling("client")
CommanderSupabaseClient = _client.CommanderSupabaseClient
SupabaseWriteResult = _client.SupabaseWriteResult


def main():
    """Log the Supabase backend-only access decision."""

    client = CommanderSupabaseClient()

    if not client.is_enabled():
        print("❌ Supabase not configured (missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY)")
        print("   Skipping decision log.")
        return False

    # Generate decision ID
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    decision_id = f"DEC-{ts}"

    # Decision record
    decision_payload = {
        "id": decision_id,
        "statement": "Supabase access model shall remain backend-only with RLS enabled and no user-based policies until a specific frontend use case requires them.",
        "rationale": (
            "Evidence-based audit (MSN-RLS-HARDENING-2026-06-10) confirmed USS TJR is already "
            "backend-only: all Supabase access routes through Python services using SUPABASE_SERVICE_ROLE_KEY. "
            "RLS is enabled on all 12 operational tables; SERVICE_ROLE_KEY bypasses RLS so no policies needed for "
            "current backend-only usage. SUPABASE_ANON_KEY is not used. Zero frontend/browser code exists. "
            "Smoke tests passed; runtime risk is low. Decision: maintain this secure model; defer RLS policies "
            "until proven frontend use case requires them. Control Deck and MVLL will route through Python backend "
            "API wrappers (not direct client). No breaking changes required."
        ),
        "created_by": "claude-audit",
        "owner": "Captain TJR",
        "status": "Active",
        "alternatives": json.dumps([
            {
                "name": "Add RLS policies for anon access now",
                "assessment": "Rejected — no frontend code exists; policies unnecessary for current backend-only usage; creates maintenance burden without immediate benefit"
            },
            {
                "name": "Disable RLS",
                "assessment": "Rejected — less secure; RLS is already enabled and working; no reason to disable"
            },
            {
                "name": "Expose ANON_KEY to frontend clients",
                "assessment": "Rejected — security risk; backend-only access is more secure and simpler to operate"
            }
        ]),
        "updated_by": None
    }

    print(f"📝 Logging decision: {decision_id}")
    print(f"   Statement: {decision_payload['statement'][:80]}...")

    result = client.insert("decisions", decision_payload)

    if result.ok:
        print(f"✅ Decision logged successfully: {decision_id}")
        print(f"   Table: {result.table}")
        print(f"   Status: {result.ok}")
        return True
    else:
        print(f"❌ Failed to log decision")
        print(f"   Error: {result.error}")
        print(f"   Enabled: {result.enabled}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
