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
import time
from typing import Any

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
# Health state — updated on every successful capture
# ---------------------------------------------------------------------------
_health: dict[str, Any] = {
    "last_capture_ts": None,       # epoch float of last successful capture
    "last_capture_item_id": None,  # Supabase item id
    "capture_count": 0,
    "capture_failures": 0,
    "channel_id": CAPTAINS_INBOX_CHANNEL_ID,
    "enabled": bool(CAPTAINS_INBOX_CHANNEL_ID),
}


def get_inbox_health() -> dict[str, Any]:
    """Return a snapshot of Captain's Inbox operational health."""
    return dict(_health)


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
            _health["last_capture_ts"] = time.time()
            _health["last_capture_item_id"] = item_id
            _health["capture_count"] += 1
            ack_to_slack(client, channel, thread_ts)
            # Async enrichment (classification, governance) — best-effort
            if item_id:
                try:
                    from core.inbox.orchestrator import process_captured_item
                    process_captured_item(item_id)
                except Exception as orch_exc:
                    log.warning("[captains-inbox] Orchestration failed (non-blocking): %s", orch_exc)
        except Exception as exc:
            _health["capture_failures"] += 1
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

    # Message events are handled by handle_message_events in app.py — Bolt v1.x
    # only dispatches to the first matching listener, so the single dispatcher
    # in app.py calls inbox_dispatch() directly rather than registering here.
