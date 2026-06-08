"""MSN-0040A: Decision logging hooks for Supabase Command Memory.

Called after decision logging and mission status changes (non-blocking).
"""

import logging
from command_memory_integration import (
    save_decision_to_memory,
    update_mission_status_in_memory,
)
"""MSN-0040A: Save decisions to Command Memory.

Hook that writes decision data to Supabase Command Memory whenever a decision
is made through Slack Commander.

Public API:
    save_decision_after_logging(statement, rationale, user_id) -> str | None
    update_mission_status_after_change(mission_id, new_status, user_id) -> None
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def save_decision_after_logging(
    decision_text: str,
    markdown_path: str,
    user_id: str = "slack-bot",
) -> None:
    """Save decision to Command Memory after logging.

    This hook is called from commands/decision_log.py after a decision is saved.
    Failure does NOT affect decision logging (non-blocking).

    Args:
        decision_text: Decision statement
        markdown_path: Path where decision was saved
        user_id: User who logged the decision
    """
    try:
        save_decision_to_memory(
            decision_text=decision_text,
            status="proposed",
            user_id=user_id,
            metadata={"markdown_path": markdown_path},
        )
        log.debug(f"[decision-to-memory] Decision logged to Command Memory")
    except Exception as e:
        log.error(f"[decision-to-memory] Failed to log decision: {e}")
        # Non-blocking failure — decision still created locally
    statement: str,
    rationale: str,
    user_id: str,
) -> str | None:
    """Save decision to Command Memory (non-blocking).

    This is called when a decision is recorded via Slack Commander.
    Failures are logged but don't block Slack Commander operation.

    Args:
        statement: Decision statement (e.g., "We will use Supabase")
        rationale: Why this decision was made
        user_id: Slack user ID of decision authority

    Returns:
        Decision ID if successful, None otherwise (non-blocking).
    """
    try:
        from command_memory_integration import log_decision_to_command_memory

        decision_id = log_decision_to_command_memory(
            statement=statement,
            rationale=rationale,
            owner=user_id,
        )

        if decision_id:
            log.info(f"[decision-to-memory] Saved decision {decision_id} to Command Memory")
            return decision_id
        else:
            log.warning(f"[decision-to-memory] Could not save decision to Command Memory")
            return None

    except Exception as e:
        log.error(f"[decision-to-memory] Error saving decision: {e}")
        # Non-blocking failure
        return None


def update_mission_status_after_change(
    mission_id: str,
    new_status: str,
    user_id: str = "slack-bot",
) -> None:
    """Update mission status in Command Memory after status change.

    This hook is called from mission_executor.py after mission status is updated.
    Failure does NOT affect status change (non-blocking).

    Args:
        mission_id: Mission ID to update
        new_status: New status value
        user_id: User making the update
    """
    try:
        update_mission_status_in_memory(
    user_id: str,
) -> None:
    """Update mission status in Command Memory (non-blocking).

    This is called when a mission status changes through Slack Commander.
    Failures are logged but don't block Slack Commander operation.

    Args:
        mission_id: Mission ID to update
        new_status: New status (Draft|Planned|Active|Blocked|Review|Completed)
        user_id: Slack user ID making the change
    """
    try:
        from command_memory_integration import update_mission_status_in_command_memory

        success = update_mission_status_in_command_memory(
            mission_id=mission_id,
            new_status=new_status,
            user_id=user_id,
        )
        log.debug(f"[decision-to-memory] Mission status updated in Command Memory")
    except Exception as e:
        log.error(f"[decision-to-memory] Failed to update mission status: {e}")
        # Non-blocking failure — status change still applied locally

        if success:
            log.info(f"[decision-to-memory] Updated mission {mission_id} status to {new_status}")
        else:
            log.warning(f"[decision-to-memory] Could not update mission {mission_id} status")

    except Exception as e:
        log.error(f"[decision-to-memory] Error updating mission status: {e}")
        # Non-blocking failure
