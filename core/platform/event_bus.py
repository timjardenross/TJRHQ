"""Event Bus (SUOC Wave 3 Platform Runtime, Workstream B).

Canonical cross-platform event log, designed in MSN-0210C §6 / MSN-0210 §9,
built here for the first time. A thin index over domain-specific detail
tables — domain services keep their own rich records (research_memory,
intelligence_events, decision_outcomes, etc.) and additionally publish a
thin `core_events` row pointing back at them via linked_entities/missions/
documents.

This is a POLL-BASED bus, not a push/message-broker system — consistent
with the rest of this platform (systemd timers, no message queue exists
anywhere in the stack). "Subscribing" means querying "events since I last
checked", not registering a callback. If a real-time push model is ever
needed, that's a new capability, not a change to this one.

Standalone module. Not yet wired into any production emitter — Operational
Resilience Intelligence (intelligence/) is the designated first pilot
emitter per MSN-0210 §21, not part of this build.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)

_VALID_STATUSES = {"new", "acknowledged", "acted_on", "dismissed", "superseded"}


def publish_event(
    event_type: str,
    domain: str,
    source: str,
    *,
    importance: Optional[int] = None,
    confidence: Optional[int] = None,
    relevance: Optional[int] = None,
    time_sensitivity: Optional[int] = None,
    linked_entities: Optional[list[str]] = None,
    linked_missions: Optional[list[str]] = None,
    linked_documents: Optional[list[str]] = None,
    recommended_action: Optional[str] = None,
    metrics: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Publish one event. Non-blocking — never raises.

    Args:
        event_type: e.g. 'mission.approved', 'research.completed', 'task.created'
        domain: which Intelligence Domain / Platform Capability, or 'system'
        source: originating module name
        importance/confidence/relevance/time_sensitivity: 0-100, all optional.
            time_sensitivity added MSN-0308 — how time-critical this event is,
            independent of importance; absent means no signal, not zero.
        linked_entities/missions/documents: lists of reference strings
        recommended_action: optional free-text or structured-action reference
        metrics: MSN-0328 Wave 2 — optional structured detail (counts,
            scores, bands) a presentation layer can render without
            parsing prose, e.g. {"high_risk_count": 3, "open_count": 12}.
            Absent/empty is normal, not every domain has this.

    Returns:
        The new event_id (str) if persisted, None otherwise (including when
        Supabase is disabled).
    """
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        if not client.is_enabled():
            log.info("[event-bus] Supabase disabled; event not persisted")
            return None

        result = client.insert(
            "core_events",
            {
                "event_type": event_type,
                "domain": domain,
                "source": source,
                "importance": importance,
                "confidence": confidence,
                "time_sensitivity": time_sensitivity,
                "relevance": relevance,
                "linked_entities": linked_entities or [],
                "linked_missions": linked_missions or [],
                "linked_documents": linked_documents or [],
                "recommended_action": recommended_action,
                "metrics": metrics or {},
            },
            returning=True,
        )
        if not result.ok or not result.data:
            log.warning("[event-bus] publish_event write failed: %s", result.error)
            return None
        return result.data[0].get("event_id")
    except Exception as exc:
        log.warning("[event-bus] publish_event failed (non-blocking): %s", exc)
        return None


def poll_events(
    *,
    since: Optional[datetime] = None,
    event_type: Optional[str] = None,
    domain: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Poll-based subscription: fetch events matching the given filters.

    A "subscriber" is any caller that periodically calls this with an
    advancing `since` timestamp — there is no push/callback mechanism.
    Returns an empty list on any error or if Supabase is disabled.
    """
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        raw = client.raw_client
        if raw is None:
            log.info("[event-bus] Supabase disabled; poll returns empty")
            return []

        query = raw.table("core_events").select("*").order("occurred_at", desc=True).limit(limit)
        if since is not None:
            query = query.gte("occurred_at", since.astimezone(timezone.utc).isoformat())
        if event_type is not None:
            query = query.eq("event_type", event_type)
        if domain is not None:
            query = query.eq("domain", domain)
        if status is not None:
            query = query.eq("status", status)
        result = query.execute()
        return list(result.data or [])
    except Exception as exc:
        log.warning("[event-bus] poll_events failed (non-blocking): %s", exc)
        return []


def mark_event_status(event_id: str, status: str) -> bool:
    """Advance an event's status (new -> acknowledged -> acted_on/dismissed/superseded)."""
    if status not in _VALID_STATUSES:
        log.warning("[event-bus] mark_event_status: invalid status %r", status)
        return False
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        raw = client.raw_client
        if raw is None:
            return False
        raw.table("core_events").update({"status": status}).eq("event_id", event_id).execute()
        return True
    except Exception as exc:
        log.warning("[event-bus] mark_event_status failed (non-blocking): %s", exc)
        return False


__all__ = ["publish_event", "poll_events", "mark_event_status"]
