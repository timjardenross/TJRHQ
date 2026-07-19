"""Staff autonomy logger — records self-directed actions to staff_autonomy_log.

Call this whenever taking action within granted authority without a direct
Captain instruction in the current session (pairs with [SD] commit prefix).

Usage:
    from lib.autonomy_log import log_autonomous_action
    log_autonomous_action(
        supabase_client,
        actor="EDO",
        action="Dispatched 5 aging planned missions to in_progress",
        rationale="Missions stalled >48h; dispatch authority granted by MSN-EDO-003",
        commit_sha="abc123def456",
        branch="main",
        mission_ref="MSN-EDO-003",
    )
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def log_autonomous_action(
    supabase_client: Any,
    actor: str,
    action: str,
    rationale: str | None = None,
    commit_sha: str | None = None,
    branch: str | None = None,
    mission_ref: str | None = None,
) -> bool:
    """Insert a row into staff_autonomy_log. Returns True on success."""
    if not supabase_client:
        log.warning("[autonomy-log] No supabase client — action not recorded: %s / %s", actor, action)
        return False
    try:
        supabase_client.table("staff_autonomy_log").insert({
            "actor":       actor,
            "action":      action,
            "rationale":   rationale,
            "commit_sha":  commit_sha[:12] if commit_sha else None,
            "branch":      branch,
            "mission_ref": mission_ref,
        }).execute()
        log.info("[autonomy-log] Logged self-directed action: [%s] %s", actor, action)
        return True
    except Exception as exc:
        log.warning("[autonomy-log] Failed to log action: %s", exc)
        return False
