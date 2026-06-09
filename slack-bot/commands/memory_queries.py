"""MSN-0040A: Slack command endpoints for Command Memory.

Slack commands for reading from and updating Command Memory:
  - /missions-active: List active missions
  - /decisions-active: List active decisions
  - /memory-search: Full-text search across missions and decisions
  - /mission-status: Update a mission's status in Command Memory

Public API:
    handle_missions_active(ack, respond) -> None
    handle_decisions_active(ack, respond) -> None
    handle_memory_search(ack, respond, command) -> None
    handle_mission_status(ack, respond, command) -> None
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Allowed mission statuses (mirrors the missions table CHECK constraint).
VALID_MISSION_STATUSES = (
    "Draft", "Planned", "Active", "Blocked", "Review", "Completed", "Archived",
)


def handle_missions_active(ack, respond) -> None:
    """Slack command: /missions-active

    Lists all active missions from Command Memory.

    Args:
        ack: Slack acknowledgment function
        respond: Slack response function
    """
    ack()

    try:
        from command_memory_integration import get_active_missions

        missions = get_active_missions()

        if not missions:
            respond("No active missions in Command Memory")
            return

        # Format for Slack
        text = "🚀 *Active Missions:*\n"
        for mission in missions:
            mission_id = mission.get("id", "?")
            title = mission.get("title", "?")
            owner = mission.get("owner", "?")
            text += f"• `{mission_id}`: {title} (owner: {owner})\n"

        respond(text)
        log.info(f"[memory-queries] Returned {len(missions)} active missions")

    except Exception as e:
        log.error(f"[memory-queries] Error in /missions-active: {e}")
        respond(f"❌ Query failed: {e}")


def handle_decisions_active(ack, respond) -> None:
    """Slack command: /decisions-active

    Lists all active decisions from Command Memory (last 5).

    Args:
        ack: Slack acknowledgment function
        respond: Slack response function
    """
    ack()

    try:
        from command_memory_integration import get_active_decisions

        decisions = get_active_decisions()

        if not decisions:
            respond("No active decisions in Command Memory")
            return

        # Format for Slack
        text = "📋 *Active Decisions:*\n"
        for decision in decisions:
            decision_id = decision.get("id", "?")
            statement = decision.get("statement", "?")
            owner = decision.get("owner", "?")
            text += f"• `{decision_id}`: {statement}\n"
            text += f"  _owner: {owner}_\n"

        respond(text)
        log.info(f"[memory-queries] Returned {len(decisions)} active decisions")

    except Exception as e:
        log.error(f"[memory-queries] Error in /decisions-active: {e}")
        respond(f"❌ Query failed: {e}")


def handle_memory_search(ack, respond, command) -> None:
    """Slack command: /memory-search <keyword>

    Searches missions and decisions by keyword (case-insensitive).

    Args:
        ack: Slack acknowledgment function
        respond: Slack response function
        command: Slack command dict with 'text' field
    """
    ack()

    query = (command.get("text") or "").strip()

    if not query:
        respond("Usage: `/memory-search <keyword>`")
        return

    try:
        from command_memory_integration import search_memory

        results = search_memory(query)
        missions = results.get("missions", [])
        decisions = results.get("decisions", [])

        if not (missions or decisions):
            respond(f"No results found for '{query}'")
            return

        # Format for Slack
        text = f"🔍 *Search Results for '{query}':*\n"

        if missions:
            text += f"\n*Missions* ({len(missions)}):\n"
            for mission in missions[:3]:  # Limit to 3
                mission_id = mission.get("id", "?")
                title = mission.get("title", "?")
                text += f"• `{mission_id}`: {title}\n"

        if decisions:
            text += f"\n*Decisions* ({len(decisions)}):\n"
            for decision in decisions[:3]:  # Limit to 3
                decision_id = decision.get("id", "?")
                statement = decision.get("statement", "?")
                text += f"• `{decision_id}`: {statement}\n"

        respond(text)
        log.info(f"[memory-queries] Search for '{query}' returned {len(missions)} missions, {len(decisions)} decisions")

    except Exception as e:
        log.error(f"[memory-queries] Error in /memory-search: {e}")
        respond(f"❌ Search failed: {e}")


def handle_mission_status(ack, respond, command) -> None:
    """Slack command: /mission-status <mission-id> <status>

    Updates a mission's status in Command Memory. The write is non-blocking:
    if Command Memory is unavailable, or the mission ID is not found, the user
    is told the update did not take effect rather than the command erroring.

    Args:
        ack: Slack acknowledgment function
        respond: Slack response function
        command: Slack command dict with 'text' and 'user_id' fields
    """
    ack()

    text = (command.get("text") or "").strip()
    user_id = command.get("user_id") or "unknown"

    valid_list = ", ".join(VALID_MISSION_STATUSES)
    parts = text.split()
    if len(parts) < 2:
        respond(
            "Usage: `/mission-status <mission-id> <status>`\n"
            "Example: `/mission-status USS-TJR-MSN-0040 Active`\n"
            f"Valid statuses: {valid_list}"
        )
        return

    mission_id = parts[0]
    requested = parts[1]

    # Case-insensitive match against the allowed statuses.
    new_status = next(
        (s for s in VALID_MISSION_STATUSES if s.lower() == requested.lower()),
        None,
    )
    if new_status is None:
        respond(
            f"❌ Invalid status `{requested}`.\n"
            f"Valid statuses: {valid_list}"
        )
        return

    try:
        from command_memory_integration import update_mission_status_in_command_memory

        success = update_mission_status_in_command_memory(
            mission_id=mission_id,
            new_status=new_status,
            user_id=user_id,
        )

        if success:
            respond(f"✅ Mission `{mission_id}` status → *{new_status}*")
            log.info(f"[memory-queries] Mission {mission_id} status updated to {new_status}")
        else:
            respond(
                f"⚠️ Could not update `{mission_id}`.\n"
                "The mission may not exist in Command Memory, or Command Memory "
                "is temporarily unavailable. No change was made."
            )
            log.warning(f"[memory-queries] Mission {mission_id} status update did not apply")

    except Exception as e:
        log.error(f"[memory-queries] Error in /mission-status: {e}")
        respond(f"❌ Status update failed: {e}")
