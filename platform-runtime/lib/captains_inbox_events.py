"""Captain's Inbox — health-state tracking (WP2)

2026-09-26: Slack fully decommissioned (Captain confirmed). This module
previously registered Slack Bolt `file_shared`/message event handlers
for the #captains-inbox channel (register_captains_inbox_handlers()),
but that function had zero production callers repo-wide (no Slack Bolt
`app` is ever instantiated in this repo any more) — confirmed again on
this pass, so the whole function (plus its Bolt-coupled `_dispatch()`
helper, the `client.files_info` call, and the `@app.event("file_shared")`
handler) has been deleted rather than left as flagged-dead-code.

What remains is just the operational health-state snapshot
(get_inbox_health()), kept as a generic, transport-agnostic surface in
case a future non-Slack capture path (Telegram/email) wants to report
into it.
"""

from __future__ import annotations

import os
from typing import Any

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
