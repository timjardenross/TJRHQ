"""
Alert Resolution Metrics — WP2

Computes notification effectiveness from escalation_manager's event log.

API:
  get_notification_metrics(days=7)   → 7-day window
  get_notification_metrics(days=30)  → 30-day window
  get_notification_metrics()         → lifetime

  format_metrics_summary(metrics)    → human-readable Slack string

No manual data entry required: all data flows from the escalation_manager
events written during process_escalations(), acknowledge_escalation(), and
resolve_escalation().
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, Optional

import os

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = Path(os.environ.get("ESCALATION_DB_PATH", "") or _REPO_ROOT / "notifications.db")


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _since_iso(days: Optional[int]) -> Optional[str]:
    if days is None:
        return None
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Core metrics computation
# ---------------------------------------------------------------------------

def get_notification_metrics(days: Optional[int] = 7) -> dict:
    """
    Compute notification effectiveness metrics.

    Args:
        days: Window in days. None = lifetime.

    Returns dict with:
        window_days          int or None
        alerts_created       int
        alerts_notified      int
        alerts_acknowledged  int
        alerts_resolved      int
        alerts_outstanding   int
        avg_time_to_ack_hours  float or None
        avg_time_to_resolve_hours  float or None
        resolution_rate_pct  float
        oldest_open_days     float or None
        generated_at         str  (ISO)
    """
    since = _since_iso(days)
    now_str = datetime.now().isoformat(timespec="seconds")

    try:
        with _db() as conn:
            # Check tables exist
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            if "escalation_history" not in tables or "alert_events" not in tables:
                return _empty_metrics(days, now_str)

            # alerts_created
            q_created = (
                "SELECT COUNT(*) FROM alert_events WHERE event_type='created'"
                + (" AND event_at >= ?" if since else "")
            )
            alerts_created = conn.execute(q_created, (since,) if since else ()).fetchone()[0]

            # alerts_notified (distinct alert_keys that had ≥1 notify event)
            q_notified = (
                "SELECT COUNT(DISTINCT alert_key) FROM alert_events WHERE event_type='notified'"
                + (" AND event_at >= ?" if since else "")
            )
            alerts_notified = conn.execute(q_notified, (since,) if since else ()).fetchone()[0]

            # alerts_acknowledged
            q_ack = (
                "SELECT COUNT(DISTINCT alert_key) FROM alert_events WHERE event_type='acknowledged'"
                + (" AND event_at >= ?" if since else "")
            )
            alerts_acknowledged = conn.execute(q_ack, (since,) if since else ()).fetchone()[0]

            # alerts_resolved
            q_res = (
                "SELECT COUNT(DISTINCT alert_key) FROM alert_events WHERE event_type='resolved'"
                + (" AND event_at >= ?" if since else "")
            )
            alerts_resolved = conn.execute(q_res, (since,) if since else ()).fetchone()[0]

            # alerts_outstanding (open escalations)
            alerts_outstanding = conn.execute(
                "SELECT COUNT(*) FROM escalation_history WHERE resolved_at IS NULL"
            ).fetchone()[0]

            # avg time to acknowledge
            avg_ack_hours = _avg_time_between_events(conn, "created", "acknowledged", since)

            # avg time to resolve
            avg_resolve_hours = _avg_time_between_events(conn, "created", "resolved", since)

            # resolution rate
            total_closeable = alerts_created
            resolution_rate = (alerts_resolved / total_closeable * 100) if total_closeable else 0.0

            # oldest open escalation
            oldest_row = conn.execute(
                "SELECT first_detected FROM escalation_history WHERE resolved_at IS NULL ORDER BY first_detected ASC LIMIT 1"
            ).fetchone()
            oldest_open_days: Optional[float] = None
            if oldest_row:
                first = datetime.fromisoformat(oldest_row[0])
                oldest_open_days = round((datetime.now() - first).total_seconds() / 86400, 1)

    except Exception as exc:
        log.warning("[metrics] Metrics computation failed: %s", exc)
        return _empty_metrics(days, now_str)

    return {
        "window_days":                days,
        "alerts_created":             alerts_created,
        "alerts_notified":            alerts_notified,
        "alerts_acknowledged":        alerts_acknowledged,
        "alerts_resolved":            alerts_resolved,
        "alerts_outstanding":         alerts_outstanding,
        "avg_time_to_ack_hours":      avg_ack_hours,
        "avg_time_to_resolve_hours":  avg_resolve_hours,
        "resolution_rate_pct":        round(resolution_rate, 1),
        "oldest_open_days":           oldest_open_days,
        "generated_at":               now_str,
    }


def _avg_time_between_events(
    conn: sqlite3.Connection,
    from_type: str,
    to_type: str,
    since: Optional[str],
) -> Optional[float]:
    """Compute average hours between two event types for the same alert_key."""
    try:
        # Get all from_type events
        q = (
            "SELECT alert_key, event_at FROM alert_events WHERE event_type=?"
            + (" AND event_at >= ?" if since else "")
        )
        from_rows = conn.execute(q, (from_type, since) if since else (from_type,)).fetchall()
        if not from_rows:
            return None

        # For each, find earliest to_type event
        durations = []
        for row in from_rows:
            to_row = conn.execute(
                "SELECT event_at FROM alert_events WHERE alert_key=? AND event_type=? AND event_at > ? ORDER BY event_at LIMIT 1",
                (row["alert_key"], to_type, row["event_at"]),
            ).fetchone()
            if to_row:
                t_from = datetime.fromisoformat(row["event_at"])
                t_to   = datetime.fromisoformat(to_row["event_at"])
                durations.append((t_to - t_from).total_seconds() / 3600)

        return round(sum(durations) / len(durations), 1) if durations else None
    except Exception:
        return None


def _empty_metrics(days: Optional[int], now_str: str) -> dict:
    return {
        "window_days": days,
        "alerts_created": 0,
        "alerts_notified": 0,
        "alerts_acknowledged": 0,
        "alerts_resolved": 0,
        "alerts_outstanding": 0,
        "avg_time_to_ack_hours": None,
        "avg_time_to_resolve_hours": None,
        "resolution_rate_pct": 0.0,
        "oldest_open_days": None,
        "generated_at": now_str,
    }


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_metrics_summary(m: dict) -> str:
    """
    Format metrics as a Slack message.

    Example output:
      :bar_chart: *Alert Metrics — Last 7 Days*
      14 alerts raised, 11 resolved, 3 outstanding.
      Average resolution time: 2.4 days.
      Resolution rate: 78.6%.
    """
    window = f"Last {m['window_days']} Days" if m.get("window_days") else "Lifetime"
    lines = [f":bar_chart: *Alert Metrics — {window}*"]

    created    = m["alerts_created"]
    resolved   = m["alerts_resolved"]
    acked      = m["alerts_acknowledged"]
    outstanding = m["alerts_outstanding"]
    rate       = m["resolution_rate_pct"]

    if created == 0:
        lines.append("No alerts recorded in this period.")
        return "\n".join(lines)

    lines.append(f"{created} alert{'s' if created != 1 else ''} raised, {resolved} resolved, {outstanding} outstanding.")

    if acked:
        lines.append(f"{acked} acknowledged.")

    if m["avg_time_to_resolve_hours"] is not None:
        days = m["avg_time_to_resolve_hours"] / 24
        lines.append(f"Average resolution time: {days:.1f} day{'s' if days != 1 else ''}.")

    if m["avg_time_to_ack_hours"] is not None:
        lines.append(f"Average time to acknowledge: {m['avg_time_to_ack_hours']:.1f} hours.")

    lines.append(f"Resolution rate: {rate}%.")

    if m.get("oldest_open_days") is not None:
        lines.append(f"Oldest open alert: {m['oldest_open_days']:.0f} days.")

    return "\n".join(lines)


def get_metrics_block_for_brief() -> str:
    """
    Return a compact metrics line suitable for appending to the morning brief.
    Only shows if there are outstanding or recently resolved alerts.
    """
    try:
        m7  = get_notification_metrics(days=7)
        m30 = get_notification_metrics(days=30)

        outstanding = m7["alerts_outstanding"]
        if outstanding == 0 and m7["alerts_resolved"] == 0:
            return ""

        resolved_7  = m7["alerts_resolved"]
        resolved_30 = m30["alerts_resolved"]
        rate        = m7["resolution_rate_pct"]

        return (
            f":bar_chart: *Alerts:* {outstanding} outstanding | "
            f"{resolved_7} resolved (7d) | {resolved_30} resolved (30d) | "
            f"{rate}% resolution rate"
        )
    except Exception as exc:
        log.debug("[metrics] Brief block failed: %s", exc)
        return ""
