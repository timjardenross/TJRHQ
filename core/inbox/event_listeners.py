"""Captain's Inbox — Cache Invalidation Event Listeners (WP3B)

When governance artefacts change (ADR updated, decision updated), the cached
governance assessments in captured_items can go stale. This module provides:

  1. invalidate_governance_cache_for_artefact(artefact_id) — marks all cached
     items that reference artefact_id as expired (sets governance_cache_expires_at
     to now), triggering re-assessment on next processing pass.

  2. sweep_expired_governance_cache(limit) — re-queues items with expired cache
     for re-processing. Call periodically (e.g. nightly) or after bulk artefact
     changes.

These are standalone functions, not a background daemon — callers decide how
and when to invoke them (cron, event hook, or direct call).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


def _get_client():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def invalidate_governance_cache_for_artefact(artefact_id: str) -> int:
    """
    Mark all cached governance assessments that reference artefact_id as expired.
    Returns the count of rows invalidated.
    """
    client = _get_client()
    if not client:
        log.warning("[inbox-events] Supabase not configured — cache invalidation skipped")
        return 0

    now = datetime.now(timezone.utc).isoformat()

    try:
        # Find items whose governance JSON references this artefact
        result = (
            client.table("captured_items")
            .select("id,governance_assessment_json")
            .gt("governance_cache_expires_at", now)  # Only active caches
            .not_.is_("governance_assessment_json", "null")
            .execute()
        )
        rows = result.data or []
    except Exception as exc:
        log.warning("[inbox-events] Failed to fetch cached items: %s", exc)
        return 0

    stale_ids = []
    for row in rows:
        assessment = row.get("governance_assessment_json") or {}
        if isinstance(assessment, str):
            try:
                assessment = json.loads(assessment)
            except Exception:
                continue
        # Check all artefact types for this artefact_id
        artefacts = assessment.get("artefacts", {})
        for bucket in artefacts.values():
            if any(a.get("artefact_id") == artefact_id for a in (bucket or [])):
                stale_ids.append(row["id"])
                break

    if not stale_ids:
        return 0

    # Expire the cache (set expires_at to now so next processing re-assesses)
    invalidated = 0
    for item_id in stale_ids:
        try:
            client.table("captured_items").update({
                "governance_cache_expires_at": now,
            }).eq("id", item_id).execute()
            invalidated += 1
        except Exception as exc:
            log.warning("[inbox-events] Failed to invalidate cache for %s: %s", item_id, exc)

    log.info(
        "[inbox-events] Invalidated governance cache for %d items referencing artefact %s",
        invalidated, artefact_id,
    )
    return invalidated


def sweep_expired_governance_cache(limit: int = 50) -> list[str]:
    """
    Find items whose governance cache has expired and re-queue them for processing.
    Returns list of item_ids queued.
    """
    client = _get_client()
    if not client:
        return []

    now = datetime.now(timezone.utc).isoformat()

    try:
        result = (
            client.table("captured_items")
            .select("id")
            .lt("governance_cache_expires_at", now)
            .eq("processing_status", "completed")
            .not_.is_("governance_assessment_json", "null")
            .limit(limit)
            .execute()
        )
        rows = result.data or []
    except Exception as exc:
        log.warning("[inbox-events] sweep query failed: %s", exc)
        return []

    item_ids = [r["id"] for r in rows]

    for item_id in item_ids:
        try:
            # Reset to pending so the orchestrator re-runs
            client.table("captured_items").update({
                "processing_status": "pending",
            }).eq("id", item_id).execute()
        except Exception as exc:
            log.warning("[inbox-events] Failed to re-queue %s: %s", item_id, exc)

    if item_ids:
        log.info("[inbox-events] Re-queued %d items with expired governance cache", len(item_ids))

    return item_ids
