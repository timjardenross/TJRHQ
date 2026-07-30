"""Audit Service (SUOC Wave 2 Platform Service, MSN-0210F Part 4).

General-purpose audit event recording, separate from
core/governance/authority_validator.py's audit_authority_action() (which
stays permission-check-specific — its authority_audit_log schema, migration
0053, has officer/action/approved/captain_override columns that don't fit
a non-permission event like "notification sent").

This module's audit_events table (migration 0054) takes any event via a
category discriminator + free-form details: permission decisions, approval
decisions, notification activity, or anything else worth a durable record.

Additive only — not yet called from any production code path. Wiring this
into the two confirmed gaps found during discovery (comms/pipeline.py's
Captain-approval transitions, telegram_build_executor.py's /approve flow)
is separate, explicitly-gated Wave 2 follow-up work (item B in the MSN-0210F
review), not part of this change.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


def record_audit_event(
    category: str,
    actor: str,
    action: str,
    outcome: str,
    details: Optional[dict[str, Any]] = None,
    mission_id: Optional[str] = None,
) -> bool:
    """Record a general audit event. Non-blocking — never raises.

    Args:
        category:   e.g. 'permission', 'approval', 'notification'
        actor:      who/what performed the action (officer slug, service name, etc.)
        action:     what was done
        outcome:    e.g. 'approved', 'denied', 'sent', 'failed'
        details:    free-form structured context
        mission_id: optional mission reference

    Returns:
        True if the record was persisted, False otherwise (including when
        Supabase is disabled — this never raises so callers can fire-and-forget).
    """
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        if not client.is_enabled():
            log.info("[audit-service] Supabase disabled; event not persisted")
            return False

        result = client.insert(
            "audit_events",
            {
                "category": category,
                "actor": actor,
                "action": action,
                "outcome": outcome,
                "details": details or {},
                "mission_id": mission_id,
            },
        )
        if not result.ok:
            log.warning("[audit-service] Write failed: %s", result.error)
        return result.ok
    except Exception as exc:
        log.warning("[audit-service] record_audit_event failed (non-blocking): %s", exc)
        return False


__all__ = ["record_audit_event"]
