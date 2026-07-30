"""
ADHD Task Nudge Scheduler — Issue 26

Scheduled check for stalled high-priority personal tasks.
Sends a brief, non-judgmental nudge via XO Bot/Telegram when:
  - Task urgency ≥ 4 ("ASAP" or "NOW")
  - Task has been in "captured" or "paused" state for >2 hours
  - No nudge already sent within the last 8 hours (rate limit)

Uses core/platform/notification_service for Telegram delivery.
Persists nudge history in a SQLite cache to avoid spam.
"""

import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)


class NudgeRateLimiter:
    """In-memory rate limiter for task nudges (single-process)."""

    def __init__(self):
        self.db_path = os.environ.get("ADHD_NUDGE_DB", "/tmp/adhd_nudges.db")
        self._init_db()

    def _init_db(self):
        """Create nudge history table if not exists."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS task_nudges (
                        task_id TEXT PRIMARY KEY,
                        last_nudge_at INTEGER,
                        nudge_count INTEGER DEFAULT 1
                    )
                    """
                )
                conn.commit()
        except Exception as e:
            log.warning("Failed to init nudge DB: %s", e)

    def should_nudge(self, task_id: str, min_hours_between: int = 8) -> bool:
        """
        Returns True if a nudge should be sent (respecting rate limit).
        Updates the DB on success.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(
                    "SELECT last_nudge_at FROM task_nudges WHERE task_id = ?",
                    (task_id,),
                )
                row = cur.fetchone()
                if not row:
                    return True

                last_nudge_ts = row[0]
                now_ts = int(time.time())
                hours_since = (now_ts - last_nudge_ts) / 3600
                return hours_since >= min_hours_between
        except Exception as e:
            log.warning("Nudge rate limit check failed: %s", e)
            return False  # Fail closed — don't nudge if we can't check

    def record_nudge(self, task_id: str):
        """Record that a nudge was sent for this task."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                now_ts = int(time.time())
                conn.execute(
                    """
                    INSERT INTO task_nudges (task_id, last_nudge_at, nudge_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(task_id) DO UPDATE SET
                        last_nudge_at = excluded.last_nudge_at,
                        nudge_count = nudge_count + 1
                    """,
                    (task_id, now_ts),
                )
                conn.commit()
        except Exception as e:
            log.warning("Failed to record nudge: %s", e)


class TaskNudgeComposer:
    """Composes non-judgmental nudge messages for stalled tasks."""

    NUDGE_TEMPLATES = [
        "Still thinking about this one?",
        "Gently nudging: {title}",
        "This might be ready to start: {title}",
        "One tiny step forward on {title}?",
    ]

    @staticmethod
    def compose(task_title: str, effort_minutes: int) -> str:
        """Compose a short, non-naggy nudge message."""
        import random

        # Pick a random template
        template = random.choice(TaskNudgeComposer.NUDGE_TEMPLATES)
        message = template.format(title=task_title[:60])

        # Add optional time hint if effort is small (<15 min)
        if effort_minutes < 15:
            message += f" (~{effort_minutes}m)"

        return message


def _fetch_stalled_tasks(threshold_ts: str) -> list[dict]:
    """Fetch high-priority stalled personal_tasks via PostgREST directly —
    matches the rest of this codebase's pattern (no supabase-py SDK
    dependency anywhere else); avoids requiring callers to hand in a
    fluent-query-builder client that doesn't exist here."""
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    from intelligence.config import SUPABASE_KEY, SUPABASE_URL

    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("[TaskNudge] Supabase not configured; skipping")
        return []

    query = urllib.parse.urlencode({
        "select": "id,title,effort_minutes,work_state,created_at,updated_at",
        "urgency": "gte.4",
        "work_state": "in.(captured,paused)",
        "updated_at": f"lt.{threshold_ts}",
        "limit": "50",
    })
    url = f"{SUPABASE_URL}/rest/v1/personal_tasks?{query}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        log.error("[TaskNudge] Failed to fetch stalled tasks: %s", exc)
        return []


async def check_and_nudge_stalled_tasks(supabase_client=None) -> dict:
    """
    Main scheduler function: check for stalled tasks, compose nudges, send.

    supabase_client is accepted-but-unused for call-site compatibility with
    platform-runtime/adhd_task_scheduler.py — the actual query goes straight
    to PostgREST (see _fetch_stalled_tasks).

    Returns a summary: {checked: N, nudged: N, errors: [...]}.
    """
    from core.platform.notification_service import notify, Severity

    summary = {"checked": 0, "nudged": 0, "errors": []}
    limiter = NudgeRateLimiter()

    try:
        threshold_ts = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()

        stalled_tasks = _fetch_stalled_tasks(threshold_ts)
        if not stalled_tasks:
            log.info("[TaskNudge] No stalled high-priority tasks found")
            return summary

        summary["checked"] = len(stalled_tasks)

        # For each task, check rate limit and send nudge
        for task in stalled_tasks:
            task_id = task.get("id")
            if not limiter.should_nudge(task_id):
                log.debug("[TaskNudge] Rate-limited: %s", task_id)
                continue

            # Compose message
            message = TaskNudgeComposer.compose(
                task.get("title", "Untitled"),
                task.get("effort_minutes", 30),
            )

            # Send via Telegram
            try:
                notify(
                    body=message,
                    title="Personal Task Nudge",
                    severity=Severity.INFO,
                    template="info",
                )
                limiter.record_nudge(task_id)
                summary["nudged"] += 1
                log.info("[TaskNudge] Nudge sent for %s", task_id)
            except Exception as e:
                error_msg = f"Failed to nudge {task_id}: {e}"
                log.error(error_msg)
                summary["errors"].append(error_msg)

        return summary

    except Exception as e:
        error_msg = f"[TaskNudge] Scheduler error: {e}"
        log.error(error_msg)
        summary["errors"].append(error_msg)
        return summary


def nudge_scheduler_entry_point(supabase_client=None):
    """
    Entry point for cron-style invocation from platform-runtime scheduler.

    Usage in platform-runtime:
      from intelligence.adhd.task_nudge_scheduler import nudge_scheduler_entry_point
      result = nudge_scheduler_entry_point(supabase_client)
    """
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(check_and_nudge_stalled_tasks(supabase_client))
        log.info("[TaskNudge] Result: %s", result)
        return result
    finally:
        loop.close()
