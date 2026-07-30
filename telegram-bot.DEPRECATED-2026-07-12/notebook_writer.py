"""Append-only notebook writer for the Telegram agent (EXEC-010C WP3).

Inserts notes into intelligence_notes via the standard Supabase Python SDK
using the service role key. The existing supabase_readonly client is restricted
to SELECT + build_request_inbox only, so this module provides a dedicated
write-path for notebook capture.

Only the intelligence_notes insert path is exposed. No reads, no updates,
no deletes.

Public API:
    capture_note(raw_content, source="telegram", title=None, tags=None) -> str | None
        Returns the new note's UUID, or None on failure.
    get_client_or_none() -> supabase.Client | None
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)


def get_client_or_none() -> Any | None:
    """Build a standard Supabase client using service role key, or None."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        log.warning("[notebook-writer] SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set — notebook capture disabled")
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as exc:
        log.warning("[notebook-writer] Failed to create Supabase client: %s", exc)
        return None


def capture_note(
    raw_content: str,
    source: str = "telegram",
    title: str | None = None,
    tags: list[str] | None = None,
    client: Any | None = None,
) -> str | None:
    """Insert a note into intelligence_notes. Returns the new note UUID or None."""
    if not raw_content or not raw_content.strip():
        log.warning("[notebook-writer] Empty content — skipping capture")
        return None

    supabase = client or get_client_or_none()
    if supabase is None:
        return None

    record: dict[str, Any] = {
        "raw_content": raw_content.strip(),
        "source":      source,
        "status":      "CAPTURED",
        "tags":        tags or [],
    }
    if title and title.strip():
        record["title"] = title.strip()[:255]

    try:
        result = supabase.table("intelligence_notes").insert(record).execute()
        rows = result.data or []
        if rows:
            note_id: str = rows[0]["id"]
            log.info("[notebook-writer] Note captured: %s (source=%s)", note_id, source)
            return note_id
        log.warning("[notebook-writer] Insert returned no rows — check RLS policies")
        return None
    except Exception as exc:
        log.warning("[notebook-writer] Failed to insert note: %s", exc)
        return None
