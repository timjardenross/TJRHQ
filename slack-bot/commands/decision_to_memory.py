"""MSN-0040A: Decision logging hooks for Supabase Command Memory.

Called after decision logging and mission status changes (non-blocking).
"""

import logging
from command_memory_integration import (
    save_decision_to_memory,
    update_mission_status_in_memory,
)

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
            mission_id=mission_id,
            new_status=new_status,
            user_id=user_id,
        )
        log.debug(f"[decision-to-memory] Mission status updated in Command Memory")
    except Exception as e:
        log.error(f"[decision-to-memory] Failed to update mission status: {e}")
        # Non-blocking failure — status change still applied locally
