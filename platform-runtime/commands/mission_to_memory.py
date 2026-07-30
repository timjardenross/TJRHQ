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
    user_id: str,
    description: str | None = None,
) -> None:
    """Save mission to Command Memory after creation (non-blocking).

    This is called immediately after a mission is created via /mission-capture
    or other mission creation commands. Failures are logged but don't block
    Slack Commander operation.

    Args:
        mission_id: Mission ID (M-YYYYMMDD-HHMMSS)
        title: Mission title
        user_id: Slack user ID of mission creator
        description: LLM-generated structured capture body (optional)
    """
    try:
        from command_memory_integration import save_mission_to_command_memory

        success = save_mission_to_command_memory(
            mission_id=mission_id,
            title=title,
            created_by=user_id,
            owner=user_id,
            description=description,
        )

        if success:
            log.info(f"[mission-to-memory] Saved mission {mission_id} to Command Memory")
        else:
            log.warning(f"[mission-to-memory] Could not save mission {mission_id} to Command Memory")

    except Exception as e:
        log.error(f"[mission-to-memory] Error saving mission {mission_id}: {e}")
        # Non-blocking failure — mission still created in local registry
