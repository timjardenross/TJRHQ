"""MSN-0040A: Mission logging hook for Supabase Command Memory.

Called after mission creation to save to Supabase (non-blocking).
"""

import logging
from command_memory_integration import save_mission_to_memory
"""MSN-0040A: Save mission to Command Memory after creation.

Hook that writes mission data to Supabase Command Memory whenever a mission
is created through Slack Commander.

Public API:
    save_mission_after_creation(mission_id, title, user_id) -> None
"""

from __future__ import annotations

import logging

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
def save_mission_after_creation(mission_id: str, title: str, user_id: str) -> None:
    """Save mission to Command Memory after creation (non-blocking).

    This is called immediately after a mission is created via /mission-capture
    or other mission creation commands. Failures are logged but don't block
    Slack Commander operation.

    Args:
        mission_id: Mission ID (M-YYYYMMDD-HHMMSS)
        title: Mission title
        user_id: Slack user ID of mission creator
    """
    try:
        from command_memory_integration import save_mission_to_command_memory

        success = save_mission_to_command_memory(
            mission_id=mission_id,
            title=title,
            created_by=user_id,
            owner=user_id,
        )

        if success:
            log.info(f"[mission-to-memory] Saved mission {mission_id} to Command Memory")
        else:
            log.warning(f"[mission-to-memory] Could not save mission {mission_id} to Command Memory")

    except Exception as e:
        log.error(f"[mission-to-memory] Error saving mission {mission_id}: {e}")
        # Non-blocking failure — mission still created in local registry
