"""Captain's Inbox — Slack Event Handlers (WP2)

Registers message and file_shared event handlers for the #captains-inbox channel.
Call register_captains_inbox_handlers(app) once at startup.

Design:
  - Only processes events in CAPTAINS_INBOX_CHANNEL_ID
  - Skips bot messages, edits, and subtypes that aren't user posts
  - Capture is synchronous (store-first); ack to Slack is best-effort
  - file_shared events supplemented with files.info API call for metadata
"""

from __future__ import annotations

import logging
import os
import threading

from lib.captains_inbox_capture import (
    capture_item,
    ack_to_slack,
    alert_capture_failure,
    extract_first_url,
    extract_urls,
    detect_item_type,
)

log = logging.getLogger(__name__)

CAPTAINS_INBOX_CHANNEL_ID = os.environ.get("CAPTAINS_INBOX_CHANNEL_ID", "")


# ---------------------------------------------------------------------------
# Internal dispatch — run capture in a thread so Slack's 3s ack deadline
# is never at risk. The @app.event handler itself returns immediately;
# the thread does the synchronous Supabase write + Slack ack.
# ---------------------------------------------------------------------------

def _dispatch(capture_event: dict, client) -> None:
    channel = capture_event["source_channel_id"]
    thread_ts = capture_event.get("source_message_ts", capture_event["source_message_id"])

    def _run():
        try:
            item_id = capture_item(capture_event)
            ack_to_slack(client, channel, thread_ts)
            # Async enrichment (classification, governance) — best-effort
            if item_id:
                try:
                    from core.inbox.orchestrator import process_captured_item
                    process_captured_item(item_id)
                except Exception as orch_exc:
                    log.warning("[captains-inbox] Orchestration failed (non-blocking): %s", orch_exc)
        except Exception as exc:
            log.error("[captains-inbox] Permanent capture failure: %s", exc)
            alert_capture_failure(client, channel, thread_ts)

    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_captains_inbox_handlers(app) -> None:
    """Register #captains-inbox event handlers on the Bolt app."""

    if not CAPTAINS_INBOX_CHANNEL_ID:
        log.warning(
            "[captains-inbox] CAPTAINS_INBOX_CHANNEL_ID not set — "
            "Captain's Inbox intake is DISABLED"
        )

    @app.event("file_shared")
    def handle_captains_inbox_file(body, client, logger):
        event = body.get("event", {})
        channel = event.get("channel_id") or event.get("channel")

        if not CAPTAINS_INBOX_CHANNEL_ID or channel != CAPTAINS_INBOX_CHANNEL_ID:
            return

        file_id = event.get("file_id")
        if not file_id:
            logger.warning("[captains-inbox] file_shared event missing file_id")
            return

        try:
            info = client.files_info(file=file_id)
            file_data = info.get("file", {})
        except Exception as exc:
            logger.warning("[captains-inbox] files_info failed for %s: %s", file_id, exc)
            file_data = {}

        message_ts = (
            event.get("message_ts")
            or event.get("event_ts")
            or event.get("ts")
        )

        capture_event = {
            "source_type": "channel_file",
            "item_type": detect_item_type(file_data.get("mimetype")),
            "title": file_data.get("name") or file_data.get("title") or "Uploaded file",
            "source_channel_id": channel,
            "source_message_id": file_id,
            "source_message_ts": message_ts or file_id,
            "source_message_permalink": file_data.get("permalink"),
            "captured_by": event.get("user_id"),
        }

        logger.info("[captains-inbox] file_shared: file_id=%s", file_id)
        _dispatch(capture_event, client)

    @app.event({"type": "message", "channel": CAPTAINS_INBOX_CHANNEL_ID} if CAPTAINS_INBOX_CHANNEL_ID else {"type": "message", "channel": "__disabled__"})
    def handle_captains_inbox_message(body, client, logger):
        event = body.get("event", {})

        # Skip bot messages and message edits/deletes
        if event.get("bot_id") or event.get("subtype") in (
            "message_changed", "message_deleted", "bot_message", "slackbot_response"
        ):
            return

        # Skip thread replies (top-level posts only for MVP)
        if event.get("thread_ts") and event.get("thread_ts") != event.get("ts"):
            return

        message_ts = event.get("ts")
        message_text = event.get("text") or ""
        user_id = event.get("user")
        channel = event.get("channel")

        if not message_ts or not channel:
            return

        urls = extract_urls(message_text)
        item_type = "url" if urls else "text_note"
        first_url = urls[0] if urls else None

        capture_event = {
            "source_type": "channel_message",
            "item_type": item_type,
            "source_channel_id": channel,
            "source_message_id": message_ts,
            "source_message_ts": message_ts,
            "raw_text": message_text,
            "source_url": first_url,
            "captured_by": user_id,
        }

        logger.info(
            "[captains-inbox] message: ts=%s item_type=%s user=%s",
            message_ts, item_type, user_id,
        )
        _dispatch(capture_event, client)
