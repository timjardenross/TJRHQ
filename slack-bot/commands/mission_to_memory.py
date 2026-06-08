"""MSN-0040A: Mission logging hook for Supabase Command Memory.

Called after mission creation to save to Supabase (non-blocking).
"""

import logging
from command_memory_integration import save_mission_to_memory

log = logging.getLogger(__name__)


def save_mission_after_creation(
    mission_id: str,
    title: str,
    user_id: str = "slack-bot",
) -> None:
    """Save mission to Command Memory after creation.

    This hook is called from mission_logger.py after a mission is created.
    Failure does NOT affect mission creation (non-blocking).

    Args:
        mission_id: Mission ID (e.g., 'M-20260608-120000')
        title: Mission title
        user_id: User who created the mission
    """
    try:
        save_mission_to_memory(
            mission_id=mission_id,
            title=title,
            status="draft",
            user_id=user_id,
        )
        log.debug(f"[mission-to-memory] Mission {mission_id} logged to Command Memory")
    except Exception as e:
        log.error(f"[mission-to-memory] Failed to log mission: {e}")
        # Non-blocking failure — mission still created locally
