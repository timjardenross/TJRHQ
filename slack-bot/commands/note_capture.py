"""Captain's Notebook — /note command handler (EXEC-010C WP4).

Slack shortcut: /note <content>
Inserts an intelligence note into intelligence_notes (status=CAPTURED) via the
service role Supabase client. Returns ephemeral confirmation with note ID.

Public API:
    handle_note_capture(text, user_id, channel_id, supabase_client) -> str
    register(app, supabase_client) -> None
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def handle_note_capture(
    text: str,
    user_id: str,
    channel_id: str,
    supabase_client: Any | None,
) -> str:
    """Insert a notebook note. Returns a confirmation string (ephemeral)."""
    content = (text or "").strip()
    if not content:
        return (
            ":notebook: *Usage:* `/note <content>` — captures an intelligence note.\n"
            "_Example: `/note Explore API-first auth approach for mobile clients`_"
        )

    if supabase_client is None:
        return ":warning: Supabase not configured — note capture unavailable."

    record: dict[str, Any] = {
        "raw_content": content,
        "source":      "slack",
        "status":      "CAPTURED",
        "tags":        [],
    }

    try:
        result = supabase_client.table("intelligence_notes").insert(record).execute()
        rows = result.data or []
        if rows:
            note_id: str = rows[0]["id"]
            short_id = note_id[:8]
            log.info("[note-capture] Note %s captured by %s in %s", note_id, user_id, channel_id)
            return (
                f":notebook: Note captured — `{short_id}…`\n"
                "_Status: CAPTURED — officer review begins in the next pipeline cycle._\n"
                "_View and route at /captains-notebook_"
            )
        return ":warning: Note capture returned no data — check RLS policies."
    except Exception as exc:
        log.warning("[note-capture] Insert failed: %s", exc)
        return f":x: Note capture failed: {exc}"


def register(app: Any, supabase_client: Any | None) -> None:
    """Register /note with the Slack Bolt app."""

    @app.command("/note")
    def note_command(ack, command, respond):
        ack()
        text = (command.get("text") or "").strip()
        user_id = command.get("user_id", "unknown")
        channel_id = command.get("channel_id", "unknown")

        reply = handle_note_capture(text, user_id, channel_id, supabase_client)
        respond({"text": reply, "response_type": "ephemeral"})
