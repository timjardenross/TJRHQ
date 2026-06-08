"""MSN-0040A: Command Memory query commands for Slack.

Three new Slack commands for querying Command Memory:
- /missions-active: List active missions (Draft, Planned, Active, Blocked, Review)
- /decisions-active: List active decisions (status=Active)
- /memory-search: Full-text search across missions and decisions
"""

import logging
from command_memory_integration import (
    get_active_missions,
    get_active_decisions,
    search_memory,
)

log = logging.getLogger(__name__)


def handle_missions_active(ack, body, say):
    """Handler for /missions-active Slack command.

    Queries Command Memory for missions with status='active' and displays them.
    """
    ack()

    try:
        missions = get_active_missions()

        if not missions:
            say("*No active missions.* Use `/mission-capture` to create one.")
            return

        # Format as Slack mrkdwn
        message = "*Active Missions:*\n\n"
        for mission in missions:
            mission_id = mission.get("id", "Unknown")
            title = mission.get("title", "Untitled")
            status = mission.get("status", "unknown")
            message += f"• `{mission_id}` — {title} (status: {status})\n"

        say(message)
        log.info("[memory-queries] /missions-active executed")

    except Exception as e:
        log.error(f"[memory-queries] /missions-active failed: {e}")
        say(":warning: Unable to retrieve active missions. Try again later.")


def handle_decisions_active(ack, body, say):
    """Handler for /decisions-active Slack command.

    Queries Command Memory for recent decisions and displays them.
    """
    ack()

    try:
        decisions = get_active_decisions()

        if not decisions:
            say("*No decisions logged yet.* Use `/decision-log-save` to create one.")
            return

        # Format as Slack mrkdwn
        message = "*Recent Decisions:*\n\n"
        for decision in decisions:
            statement = decision.get("statement", "Unknown")[:100]
            status = decision.get("status", "Active")
            message += f"• {statement}... (status: {status})\n"

        say(message)
        log.info("[memory-queries] /decisions-active executed")

    except Exception as e:
        log.error(f"[memory-queries] /decisions-active failed: {e}")
        say(":warning: Unable to retrieve decisions. Try again later.")


def handle_memory_search(ack, body, say):
    """Handler for /memory-search Slack command.

    Full-text search over missions and decisions.
    Usage: /memory-search <query>
    """
    ack()

    # Extract search query from command text
    command_text = body.get("text", "").strip()
    if not command_text:
        say("Usage: `/memory-search <query>`\nExample: `/memory-search kubernetes`")
        return

    try:
        results = search_memory(command_text)

        if not results:
            say(f"No results found for query `{command_text}`.")
            return

        # Format as Slack mrkdwn
        message = f"*Search results for `{command_text}`:*\n\n"
        for result in results:
            # Determine result type based on available fields (schema-compliant field names)
            if "title" in result:
                title = result.get("title", "Untitled")
                mission_id = result.get("id", "Unknown")
                message += f"• Mission: `{mission_id}` — {title}\n"
            elif "statement" in result:
                statement = result.get("statement", "Unknown")[:80]
                message += f"• Decision: {statement}...\n"

        say(message)
        log.info(f"[memory-queries] /memory-search executed (query: {command_text})")

    except Exception as e:
        log.error(f"[memory-queries] /memory-search failed: {e}")
        say(f":warning: Search failed for query `{command_text}`. Try again later.")
