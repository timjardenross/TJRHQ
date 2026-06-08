"""MSN-0040A: Decision logging hooks for Supabase Command Memory.

Called after decision logging to save decisions (non-blocking).
"""

import logging
from command_memory_integration import save_decision_to_memory

log = logging.getLogger(__name__)


def save_decision_after_logging(
    statement: str,
    rationale: str = "",
    user_id: str = "slack-bot",
) -> bool:
    """Save decision to Command Memory after logging.

    This hook is called from commands/decision_log.py after a decision is saved.
    Failure does NOT affect decision logging (non-blocking).

    Args:
        statement: Decision statement (e.g., "We will use Supabase")
        rationale: Why this decision was made
        user_id: Slack user ID of decision authority

    Returns:
        True if successfully saved to Command Memory, False otherwise
    """
    try:
        success = save_decision_to_memory(
            decision_text=statement,
            status="Active",
            user_id=user_id,
        )
        if success:
            log.info(f"[decision-to-memory] Decision saved to Command Memory")
        else:
            log.warning(f"[decision-to-memory] Command Memory unavailable, decision persisted locally only")
        return success
    except Exception as e:
        log.error(f"[decision-to-memory] Failed to log decision: {e}")
        return False
        # Non-blocking failure — decision still created locally
