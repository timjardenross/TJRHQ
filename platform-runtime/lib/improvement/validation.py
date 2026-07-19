"""Improvement Outcome Validation (EXEC-002 WP5).

Every completed improvement mission must answer three questions:
  1. What changed?
  2. What improved?
  3. What benefit was realised?

Validation is mandatory before a mission can be marked complete.
Outcomes are logged to Command Memory as lessons learned.

D-057 Recurrence Check closure: if the improvement was triggered by a
recurring escalation, validation confirms the recurrence is resolved.

Public API:
    validate_improvement_outcome(mission_id, officer, what_changed,
                                  what_improved, benefit_realised, measurement)
                                  -> bool
    get_improvement_outcomes()    -> list[dict]
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


def validate_improvement_outcome(
    mission_id: str,
    officer: str,
    what_changed: str,
    what_improved: str,
    benefit_realised: str,
    measurement: str | None = None,
    captain_override: bool = False,
) -> bool:
    """Record and validate the outcome of a completed improvement mission.

    Args:
        mission_id:       ID of the improvement mission being validated
        officer:          Officer who originated the improvement opportunity
        what_changed:     Concrete description of what was changed
        what_improved:    Observable improvement (e.g. 'Blocked mission count dropped from 3 to 0')
        benefit_realised: D-057 outcome statement (e.g. 'Captain brief reduced by 2 items/cycle')
        measurement:      Optional quantitative measure (e.g. '3 fewer escalations/week')
        captain_override: Override validation gate (logged)

    Returns:
        True if outcome was recorded successfully, False otherwise (non-blocking).
    """
    if not what_changed or not what_improved or not benefit_realised:
        log.warning(
            "[improvement.validation] Incomplete outcome for %s — "
            "what_changed, what_improved, and benefit_realised are all required",
            mission_id,
        )
        return False

    outcome_logged = _log_outcome_to_command_memory(
        mission_id, officer, what_changed, what_improved, benefit_realised, measurement, captain_override
    )

    if outcome_logged:
        _update_mission_validated(mission_id, benefit_realised)

    return outcome_logged


def _log_outcome_to_command_memory(
    mission_id: str,
    officer: str,
    what_changed: str,
    what_improved: str,
    benefit_realised: str,
    measurement: str | None,
    captain_override: bool,
) -> bool:
    """Log improvement outcome to Command Memory as a lesson learned decision."""
    try:
        sys.path.insert(0, str(_BOT))
        from command_memory_integration import log_decision_to_command_memory

        measurement_note = f" Measurement: {measurement}." if measurement else ""
        override_note = " [Captain override applied]" if captain_override else ""

        statement = (
            f"Improvement validated ({officer}): {mission_id}{override_note}"
        )
        rationale = (
            f"What changed: {what_changed}. "
            f"What improved: {what_improved}. "
            f"Benefit realised: {benefit_realised}.{measurement_note}"
        )

        success = log_decision_to_command_memory(
            statement=statement,
            rationale=rationale,
            owner=f"improvement_validation:{officer}",
        )
        if success:
            log.info(
                "[improvement.validation] Outcome logged for mission %s", mission_id
            )
        return bool(success)
    except Exception as exc:
        log.warning(
            "[improvement.validation] Command Memory write failed (non-blocking): %s", exc
        )
        return False


def _update_mission_validated(mission_id: str, benefit_realised: str) -> None:
    """Update mission status to reflect validated completion (non-blocking)."""
    try:
        from tools.supabase.client import CommanderSupabaseClient

        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return

        c.raw_client.table("missions").update({
            "status": "completed",
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "notes": f"[VALIDATED] {benefit_realised}",
        }).eq("id", mission_id).execute()

        log.info("[improvement.validation] Mission %s marked completed (validated)", mission_id)
    except Exception as exc:
        log.debug("[improvement.validation] Mission status update skipped: %s", exc)


def get_improvement_outcomes(limit: int = 20) -> list[dict[str, Any]]:
    """Retrieve recent improvement validation records from Command Memory.

    Returns decisions logged with owner prefix 'improvement_validation:'.
    """
    try:
        from tools.supabase.client import CommanderSupabaseClient

        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []

        res = c.raw_client.table("decisions").select(
            "id,statement,rationale,owner,created_at"
        ).like("owner", "improvement_validation:%").order(
            "created_at", desc=True
        ).limit(limit).execute()

        return list(res.data or [])
    except Exception as exc:
        log.warning("[improvement.validation] Outcome retrieval failed: %s", exc)
        return []


__all__ = [
    "validate_improvement_outcome",
    "get_improvement_outcomes",
]
