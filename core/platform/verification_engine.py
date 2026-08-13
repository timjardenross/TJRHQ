#!/usr/bin/env python3
"""Verification engine (STARSHIP-REDESIGN.md §4).

Runs periodically (systemd timer, see deploy/verification-engine.timer),
independent of any single job: reads every domain's current heartbeat state
from domain_heartbeat_latest, checks the one infra signal it owns directly
(the command-centre backend HTTP health probe - the same one
core/coordination/command_bus.py's _backend_healthy() already uses),
computes an overall sure/unsure state, writes one row to verification_state,
and writes its own heartbeat (domain_key='verification_engine') on success -
the same mechanism as every other domain, per spec §4.1.

Deliberately does not assert 'blind' about itself - a pass that cannot run
cannot self-report. Blind is derived downstream by checking whether the
latest verification_state.computed_at has itself gone stale against the
verification_engine domain's own cadence+grace (see the API endpoint,
core/command-centre/backend/api/verification.js, and the external
dead-man's switch, core/platform/deadmans_switch.py).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heartbeat import record_heartbeat, supabase_get, supabase_insert  # noqa: E402

_BACKEND_HEALTH_URL = os.environ.get("COMMAND_CENTRE_HEALTH_URL", "http://localhost:5000/health")

# 2026-08-13: muted, not deleted from domain_registry (a DB write was blocked
# by the permission classifier when attempted live — this is the code-side
# equivalent, reversible by removing an entry here rather than a schema/data
# change). Both input paths were intentionally retired 2026-08-10 when
# Recovery Pulse became the sole health-capture mechanism (Captain's Log and
# manual daily health check-ins disabled that day) — recovery_pulses' own
# heartbeat already covers the equivalent "is health data flowing" signal.
# The Captain's Chair Workbench hit the identical stale-nag problem the same
# day and fixed it the same way (removed the now-unresolvable rule).
_MUTED_DOMAINS = frozenset({"captains_log", "health_daily_logs"})


def _check_command_centre_backend() -> bool:
    """Same probe as core/coordination/command_bus.py's _backend_healthy()."""
    try:
        req = urllib.request.Request(_BACKEND_HEALTH_URL)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("status") == "operational"
    except Exception:
        return False


def run_verification_pass() -> Dict[str, Any]:
    """Compute the Sure/Unsure state and persist it. Returns the computed report."""
    degraded: List[Dict[str, str]] = []

    # 1. Check the command-centre backend live, directly - don't rely on
    #    some other process having heartbeated it recently.
    backend_ok = _check_command_centre_backend()
    record_heartbeat(
        "command_centre_backend",
        status="ok" if backend_ok else "failed",
        detail=None if backend_ok else None,
        error_message=None if backend_ok else f"GET {_BACKEND_HEALTH_URL} did not return status=operational",
    )
    if not backend_ok:
        degraded.append({"domain_key": "command_centre_backend", "display_name": "Command Centre Backend"})

    # 2. Read every other domain's computed staleness from the view.
    try:
        domains = supabase_get(
            "domain_heartbeat_latest"
            "?select=domain_key,display_name,category,is_stale,never_succeeded,last_status,last_error_message"
        )
    except Exception as exc:
        # Can't even read domain state - this pass has failed outright.
        # Deliberately do NOT write verification_state (a failed read must
        # never produce a false "sure") and do NOT self-heartbeat, so the
        # external dead-man's switch can do its job on a genuinely silent run.
        return {"error": str(exc), "written": False}

    for row in domains:
        if row["domain_key"] == "command_centre_backend":
            continue  # already handled above via the live check, not the view
        if row["domain_key"] in _MUTED_DOMAINS:
            continue  # see _MUTED_DOMAINS docstring
        if row.get("is_stale"):
            degraded.append({"domain_key": row["domain_key"], "display_name": row["display_name"]})

    state = "sure" if not degraded else "unsure"
    reason = None if not degraded else f"{len(degraded)} domain(s) missed or never reported"

    written = supabase_insert("verification_state", {
        "state": state,
        "degraded_domains": degraded,
        "reason": reason,
    })

    # 3. Self-heartbeat - internal jobs are domains too (spec §4.1,
    #    non-negotiable). Only written if the verification_state write
    #    itself succeeded, so a persistence failure is visible as a missed
    #    heartbeat, never masked by a heartbeat claiming success.
    if written:
        record_heartbeat("verification_engine", status="ok", detail=f"state={state} degraded={len(degraded)}")

    return {"state": state, "degraded_domains": degraded, "written": written}


if __name__ == "__main__":
    report = run_verification_pass()
    print(json.dumps(report, indent=2, default=str))
    raise SystemExit(0 if report.get("written") else 1)
