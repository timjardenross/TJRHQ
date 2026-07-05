"""Task Engine (SUOC Wave 3 Platform Runtime, Workstream A).

Universal task model — one canonical lifecycle for research, engineering,
health, content, operations, and future execution-engine (Hermes or
otherwise) tasks. Generalises vm-transfer's proven batches/files_state/
transfer_log schema (MSN-0210C §8) into two tables (`tasks`, `task_events`),
using self-referential `parent_task_id` instead of a separate batch table.

Status vocabulary and ownership model are informed by the Wave 3 discovery
pass's two closest existing precedents — `decision_followup_queue`'s simple
enqueued/processing/completed/failed states, and `delivery_reconciler.py`'s
NEXT_ACTOR pattern (naming who's responsible for the next step) — neither
of which is replaced by this engine; both keep their own domain-specific
tables and can migrate onto this one later if that's ever wanted.

Standalone module. Not yet wired into any production task source — the
designated first pilot adopter is `core/infrastructure/vm-processing/`
(Wave 3 sequencing), not part of this build.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)

_VALID_STATUSES = {"pending", "in_progress", "blocked", "completed", "failed", "cancelled"}
_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def create_task(
    task_type: str,
    domain: str,
    owner: str,
    *,
    parent_task_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    linked_mission_id: Optional[str] = None,
) -> Optional[str]:
    """Create a task in 'pending' status. Non-blocking — never raises.

    Returns the new task_id, or None if the write failed (including a
    duplicate idempotency_key, which is treated as "already exists").
    """
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        if not client.is_enabled():
            log.info("[task-engine] Supabase disabled; task not created")
            return None

        payload = {
            "task_type": task_type,
            "domain": domain,
            "owner": owner,
            "parent_task_id": parent_task_id,
            "idempotency_key": idempotency_key,
            "metadata": metadata or {},
            "linked_mission_id": linked_mission_id,
        }
        result = client.insert("tasks", payload, returning=True)
        if not result.ok or not result.data:
            log.warning("[task-engine] create_task failed: %s", result.error)
            return None
        task_id = result.data[0].get("task_id")
        _log_task_event(client, task_id, "created", {"task_type": task_type, "domain": domain, "owner": owner})
        return task_id
    except Exception as exc:
        log.warning("[task-engine] create_task failed (non-blocking): %s", exc)
        return None


def transition_task(
    task_id: str,
    new_status: str,
    *,
    error: Optional[str] = None,
    confidence: Optional[int] = None,
    delegated_to: Optional[str] = None,
) -> bool:
    """Move a task to a new lifecycle status, recording a task_event.

    Sets started_at on first transition into 'in_progress', completed_at
    on any transition into a terminal status. Increments `attempts` on
    every transition into 'failed'. Delegation (delegated_to) can be set
    independently of a status change.
    """
    if new_status not in _VALID_STATUSES:
        log.warning("[task-engine] transition_task: invalid status %r", new_status)
        return False
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        if not client.is_enabled():
            return False

        now = datetime.now(timezone.utc).isoformat()
        update: dict[str, Any] = {"status": new_status, "updated_at": now}
        if new_status == "in_progress":
            update["started_at"] = now
        if new_status in _TERMINAL_STATUSES:
            update["completed_at"] = now
        if new_status == "failed":
            rows = client.get(f"tasks?task_id=eq.{task_id}&select=attempts")
            attempts = (rows[0].get("attempts") if rows else 0) or 0
            update["attempts"] = attempts + 1
        if error is not None:
            update["last_error"] = error
        if confidence is not None:
            update["confidence"] = confidence
        if delegated_to is not None:
            update["delegated_to"] = delegated_to

        ok = client._patch(f"tasks?task_id=eq.{task_id}", update)
        if not ok:
            return False
        _log_task_event(
            client, task_id,
            "delegated" if delegated_to is not None else "status_changed",
            {"new_status": new_status, "error": error, "delegated_to": delegated_to},
        )
        return True
    except Exception as exc:
        log.warning("[task-engine] transition_task failed (non-blocking): %s", exc)
        return False


def complete_task(task_id: str, *, confidence: Optional[int] = None) -> bool:
    """Convenience wrapper: transition to 'completed'."""
    return transition_task(task_id, "completed", confidence=confidence)


def get_task(task_id: str) -> Optional[dict[str, Any]]:
    """Fetch a single task's current state. Returns None on any failure."""
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        rows = client.get(f"tasks?task_id=eq.{task_id}&select=*")
        return rows[0] if rows else None
    except Exception as exc:
        log.warning("[task-engine] get_task failed (non-blocking): %s", exc)
        return None


def get_task_by_idempotency_key(idempotency_key: str) -> Optional[dict[str, Any]]:
    """Fetch a task by its idempotency_key. Returns None on any failure or if
    no task with that key exists. For adopters that don't want to thread a
    task_id through their own call chain — vm-transfer-style callers can
    correlate purely on their own natural key (e.g. source_path)."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        import urllib.parse

        client = CommanderSupabaseClient()
        rows = client.get(f"tasks?idempotency_key=eq.{urllib.parse.quote(idempotency_key, safe='')}&select=*")
        return rows[0] if rows else None
    except Exception as exc:
        log.warning("[task-engine] get_task_by_idempotency_key failed (non-blocking): %s", exc)
        return None


def get_child_tasks(parent_task_id: str) -> list[dict[str, Any]]:
    """Fetch all tasks delegated/grouped under a parent (the batch/delegation model)."""
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        return client.get(f"tasks?parent_task_id=eq.{parent_task_id}&select=*")
    except Exception as exc:
        log.warning("[task-engine] get_child_tasks failed (non-blocking): %s", exc)
        return []


def get_task_history(task_id: str) -> list[dict[str, Any]]:
    """Fetch a task's full event history, oldest first."""
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        return client.get(f"task_events?task_id=eq.{task_id}&select=*&order=occurred_at.asc")
    except Exception as exc:
        log.warning("[task-engine] get_task_history failed (non-blocking): %s", exc)
        return []


def _log_task_event(client, task_id: str, event_type: str, detail: dict[str, Any]) -> None:
    try:
        client.insert("task_events", {"task_id": task_id, "event_type": event_type, "detail": detail})
    except Exception as exc:
        log.warning("[task-engine] _log_task_event failed (non-blocking): %s", exc)


__all__ = [
    "create_task",
    "transition_task",
    "complete_task",
    "get_task",
    "get_task_by_idempotency_key",
    "get_child_tasks",
    "get_task_history",
]
