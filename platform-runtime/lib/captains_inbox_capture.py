"""Captain's Inbox — Synchronous Capture Handler (WP2)

Store-first, process-later. Capture to Supabase is mandatory and synchronous.
Enrichment (classification, summarisation, governance) is async and best-effort.

Reliability contract:
  - Up to 3 retries with exponential backoff on Supabase failures
  - Idempotent: duplicate source_message_id is silently ignored (upsert)
  - Permanent failure triggers ops alert + Slack thread notification
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import urllib.parse
import urllib.request
import json
from typing import Any

log = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s>\"']+")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_urls(text: str) -> list[str]:
    return _URL_RE.findall(text or "")


def extract_first_url(text: str) -> str | None:
    urls = extract_urls(text)
    return urls[0] if urls else None


def detect_item_type(mimetype: str | None) -> str:
    if not mimetype:
        return "file"
    if mimetype.startswith("image/"):
        return "image"
    if mimetype == "application/pdf":
        return "file"
    return "file"


def derive_title(capture_event: dict[str, Any]) -> str:
    """Best-effort title from available fields."""
    if capture_event.get("title"):
        return capture_event["title"][:200]
    url = capture_event.get("source_url")
    if url:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.rstrip("/")
        slug = path.split("/")[-1] if path else ""
        return (slug or parsed.netloc or url)[:200]
    raw = (capture_event.get("raw_text") or "").strip()
    return raw[:100] or "Untitled capture"


# ---------------------------------------------------------------------------
# Supabase write (PostgREST REST + supabase-py fallback)
# ---------------------------------------------------------------------------

class _SupabaseInsert:
    """Thin insert wrapper that prefers supabase-py and falls back to urllib."""

    def __init__(self) -> None:
        self.url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self._client = None
        if self.url and self.key:
            try:
                from supabase import create_client
                self._client = create_client(self.url, self.key)
            except Exception:
                pass

    def enabled(self) -> bool:
        return bool(self.url and self.key)

    def upsert(self, table: str, payload: dict[str, Any], on_conflict: str) -> dict[str, Any]:
        """Upsert row. Raises on failure."""
        if self._client:
            result = (
                self._client.table(table)
                .upsert(payload, on_conflict=on_conflict, ignore_duplicates=True)
                .execute()
            )
            data = result.data
            return data[0] if data else {}

        # urllib fallback
        endpoint = f"{self.url}/rest/v1/{table}?on_conflict={on_conflict}"
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Prefer": "resolution=ignore-duplicates,return=representation",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())[0] if resp.status in (200, 201) else {}


_db = _SupabaseInsert()


# ---------------------------------------------------------------------------
# Core capture (synchronous, mandatory)
# ---------------------------------------------------------------------------

def capture_item(capture_event: dict[str, Any], attempt: int = 0) -> str | None:
    """
    Store capture_event to captured_items. Returns item id on success.
    Retries up to 3× with exponential backoff. Raises on permanent failure.
    """
    if not _db.enabled():
        log.warning("[captains-inbox] Supabase not configured — capture skipped")
        return None

    raw_text = (capture_event.get("raw_text") or "")[:10240]
    title = derive_title(capture_event)

    payload = {
        "source_type": capture_event["source_type"],
        "source_channel_id": capture_event["source_channel_id"],
        "source_message_id": capture_event["source_message_id"],
        "source_message_ts": capture_event.get("source_message_ts", capture_event["source_message_id"]),
        "source_message_permalink": capture_event.get("source_message_permalink"),
        "source_user_id": capture_event.get("captured_by"),
        "captured_by": capture_event.get("captured_by"),
        "item_type": capture_event["item_type"],
        "source_url": capture_event.get("source_url"),
        "title": title,
        "raw_text": raw_text or None,
        "processing_status": "pending",
        "review_status": "unreviewed",
    }

    try:
        row = _db.upsert("captured_items", payload, on_conflict="source_message_id")
        item_id = row.get("id", "")
        log.info("[captains-inbox] Captured item_id=%s source_message_id=%s", item_id, capture_event["source_message_id"])
        return item_id
    except Exception as exc:
        if attempt < 2:
            wait = 2 ** attempt  # 1s, 2s, 4s
            log.warning("[captains-inbox] Capture attempt %d failed (%s), retrying in %ds", attempt + 1, exc, wait)
            time.sleep(wait)
            return capture_item(capture_event, attempt + 1)
        log.error("[captains-inbox] Capture failed permanently after 3 attempts: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Slack acknowledgement (non-blocking — failure here doesn't matter)
# ---------------------------------------------------------------------------

def ack_to_slack(client: Any, channel: str, thread_ts: str) -> None:
    try:
        client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="✅ Captured to intelligence registry.",
        )
    except Exception as exc:
        log.warning("[captains-inbox] Slack ack failed (non-critical): %s", exc)


def alert_capture_failure(client: Any, channel: str, thread_ts: str) -> None:
    try:
        client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="🚨 Capture failed after 3 retries. Contact Number One.",
        )
    except Exception:
        pass
