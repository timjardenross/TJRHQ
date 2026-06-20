"""
Escalation Manager — WP1: Repeated Escalation Management

Prevents alert fatigue by tracking escalation lifecycle and enforcing
notification cadence rules. Same condition is never pushed daily.

Persistence: SQLite at REPO_ROOT/notifications.db (alongside missions.db)

Notification cadence:
  Day 1  → initial notification
  Day 3  → reminder
  Day 7  → escalation (severity promoted)
  Day 14+ → every 7 days thereafter

Severity progression by notification count:
  1st push: original severity (WARNING)
  2nd push: ALERT
  3rd+ push: CRITICAL

Configuration (.env):
  ESCALATION_DB_PATH = /path/to/notifications.db   # override default
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]

import os
_DB_PATH = Path(os.environ.get("ESCALATION_DB_PATH", "") or _REPO_ROOT / "notifications.db")

# Notification cadence: days since first_detected
_CADENCE_DAYS = [0, 3, 7]        # initial, reminder, escalation
_REPEAT_INTERVAL_DAYS = 7         # every 7 days after escalation

# Severity progression
from captain_notifications import (
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SEVERITY_ALERT,
    SEVERITY_CRITICAL,
    _SEVERITY_ORDER,
    max_severity,
)

_PROGRESSION = {
    1: lambda s: s,                                      # 1st: keep original
    2: lambda s: max_severity(s, SEVERITY_ALERT),        # 2nd: at least ALERT
    3: lambda s: SEVERITY_CRITICAL,                      # 3rd+: always CRITICAL
}


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS escalation_history (
            id TEXT PRIMARY KEY,
            mission_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            original_severity TEXT NOT NULL,
            current_severity TEXT NOT NULL,
            first_detected TEXT NOT NULL,
            last_notified TEXT,
            notification_count INTEGER NOT NULL DEFAULT 0,
            resolved_at TEXT
        );

        CREATE TABLE IF NOT EXISTS alert_events (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_key TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_at TEXT NOT NULL,
            metadata TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_escalation_mission
            ON escalation_history(mission_id);
        CREATE INDEX IF NOT EXISTS idx_escalation_resolved
            ON escalation_history(resolved_at);
        CREATE INDEX IF NOT EXISTS idx_events_alert_key
            ON alert_events(alert_key);
        CREATE INDEX IF NOT EXISTS idx_events_event_at
            ON alert_events(event_at);
    """)
    conn.commit()


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        _init_db(conn)
        yield conn
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _alert_key(mission_id: str, alert_type: str) -> str:
    return f"{mission_id}:{alert_type}"


# ---------------------------------------------------------------------------
# Core escalation logic
# ---------------------------------------------------------------------------

def _escalated_severity(original: str, count: int) -> str:
    """Return the severity to use for notification number `count`."""
    fn = _PROGRESSION.get(count, _PROGRESSION[3])
    return fn(original)


def _should_notify_now(row: sqlite3.Row, today: date) -> bool:
    """
    Return True if this escalation is due for another notification.
    Uses cadence: Day 0, Day 3, Day 7, then every 7 days after.
    """
    first = datetime.fromisoformat(row["first_detected"]).date()
    age_days = (today - first).days
    count = row["notification_count"]

    # Not yet notified
    if count == 0:
        return True

    # Within cadence schedule
    if count < len(_CADENCE_DAYS):
        return age_days >= _CADENCE_DAYS[count]

    # Past initial schedule: notify every _REPEAT_INTERVAL_DAYS days
    last_notified = row["last_notified"]
    if last_notified:
        last = datetime.fromisoformat(last_notified).date()
        return (today - last).days >= _REPEAT_INTERVAL_DAYS

    return False


def process_escalations(
    active_escalations: list[dict],
) -> list[dict]:
    """
    Main entry point for WP1.

    Given the raw escalation list from captain_notifications.get_mission_escalations(),
    applies cadence rules and returns only those that should be notified NOW.

    Side effects:
    - Creates new escalation records for first-time alerts
    - Updates notification_count and last_notified on existing records
    - Records events in alert_events
    - Closes resolved escalations (those no longer in active_escalations)

    Returns filtered list of escalation dicts (same shape as input, with
    `current_severity` and `notification_count` added).
    """
    today = date.today()
    now_str = _now_iso()

    # Build lookup of active alert keys
    active_keys = {
        _alert_key(e["id"], at): e
        for e in active_escalations
        for at in _derive_alert_types(e)
    }

    to_notify: list[dict] = []

    with _db() as conn:
        # --- Close resolved escalations ---
        open_rows = conn.execute(
            "SELECT * FROM escalation_history WHERE resolved_at IS NULL"
        ).fetchall()
        for row in open_rows:
            if row["id"] not in active_keys:
                conn.execute(
                    "UPDATE escalation_history SET resolved_at=? WHERE id=?",
                    (now_str, row["id"]),
                )
                conn.execute(
                    "INSERT INTO alert_events (alert_key, event_type, event_at) VALUES (?,?,?)",
                    (row["id"], "resolved", now_str),
                )
                log.info("[escalation] Auto-closed: %s", row["id"])
        conn.commit()

        # --- Process active escalations ---
        for key, escalation in active_keys.items():
            alert_type = key.split(":", 1)[1]
            row = conn.execute(
                "SELECT * FROM escalation_history WHERE id=?", (key,)
            ).fetchone()

            if row is None:
                # First time this alert is detected — create record
                conn.execute(
                    """INSERT INTO escalation_history
                       (id, mission_id, alert_type, original_severity, current_severity,
                        first_detected, last_notified, notification_count)
                       VALUES (?,?,?,?,?,?,NULL,0)""",
                    (key, escalation["id"], alert_type,
                     escalation["severity"], escalation["severity"], now_str),
                )
                conn.execute(
                    "INSERT INTO alert_events (alert_key, event_type, event_at) VALUES (?,?,?)",
                    (key, "created", now_str),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM escalation_history WHERE id=?", (key,)
                ).fetchone()

            if _should_notify_now(row, today):
                new_count = row["notification_count"] + 1
                new_severity = _escalated_severity(row["original_severity"], new_count)

                conn.execute(
                    """UPDATE escalation_history
                       SET notification_count=?, last_notified=?, current_severity=?
                       WHERE id=?""",
                    (new_count, now_str, new_severity, key),
                )
                conn.execute(
                    "INSERT INTO alert_events (alert_key, event_type, event_at, metadata) VALUES (?,?,?,?)",
                    (key, "notified", now_str,
                     json.dumps({"count": new_count, "severity": new_severity})),
                )
                conn.commit()

                enriched = {**escalation, "current_severity": new_severity,
                            "notification_count": new_count, "alert_type": alert_type}
                to_notify.append(enriched)
            else:
                log.debug("[escalation] Suppressed (cadence): %s (count=%d)", key, row["notification_count"])

    return to_notify


def _derive_alert_types(escalation: dict) -> list[str]:
    """Derive one or more alert_type strings from an escalation dict's reasons."""
    types = []
    status = escalation.get("status", "").lower()
    if "blocked" in status:
        types.append("blocked")
    if "awaiting xo" in status:
        types.append("awaiting_xo")
    if "awaiting number one" in status:
        types.append("awaiting_nr1")
    for reason in escalation.get("reasons", []):
        r = reason.lower()
        if "no activity" in r:
            types.append("stale_48h")
        elif "open for" in r or "open" in r:
            types.append("open_days")
    # Ensure at least one type
    if not types:
        types.append("general")
    return list(dict.fromkeys(types))  # deduplicate preserving order


# ---------------------------------------------------------------------------
# Manual acknowledgement / resolution
# ---------------------------------------------------------------------------

def acknowledge_escalation(alert_key: str) -> bool:
    """Mark an escalation as acknowledged (does not close it)."""
    now_str = _now_iso()
    with _db() as conn:
        row = conn.execute(
            "SELECT id FROM escalation_history WHERE id=? AND resolved_at IS NULL",
            (alert_key,)
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "INSERT INTO alert_events (alert_key, event_type, event_at) VALUES (?,?,?)",
            (alert_key, "acknowledged", now_str),
        )
        conn.commit()
    return True


def resolve_escalation(alert_key: str) -> bool:
    """Manually resolve an escalation."""
    now_str = _now_iso()
    with _db() as conn:
        row = conn.execute(
            "SELECT id FROM escalation_history WHERE id=? AND resolved_at IS NULL",
            (alert_key,)
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE escalation_history SET resolved_at=? WHERE id=?",
            (now_str, alert_key),
        )
        conn.execute(
            "INSERT INTO alert_events (alert_key, event_type, event_at) VALUES (?,?,?)",
            (alert_key, "resolved", now_str),
        )
        conn.commit()
    return True


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_open_escalations() -> list[dict]:
    """Return all currently open (unresolved) escalations."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM escalation_history WHERE resolved_at IS NULL ORDER BY first_detected"
        ).fetchall()
        return [dict(r) for r in rows]


def get_escalation_history(limit: int = 50) -> list[dict]:
    """Return recent escalation records (open and closed)."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM escalation_history ORDER BY first_detected DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
