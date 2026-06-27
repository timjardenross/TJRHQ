"""
Alert Resolution Metrics — MSN-BOT-SOR: Supabase-backed

Computes notification effectiveness from escalation_events and
escalation_history tables in Supabase.

notifications.db (SQLite) is retired — do not copy to VPS.

API:
  get_notification_metrics(days=7)   → 7-day window
  get_notification_metrics(days=30)  → 30-day window
  get_notification_metrics()         → lifetime

  format_metrics_summary(metrics)    → human-readable Slack string
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _client():
    sys.path.insert(0, str(_REPO_ROOT / "tools" / "supabase"))
    from client import CommanderSupabaseClient
    return CommanderSupabaseClient()


def _since_iso(days: Optional[int]) -> Optional[str]:
    if days is None:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# Core metrics computation
# ---------------------------------------------------------------------------

def get_notification_metrics(days: Optional[int] = 7) -> dict:
    """
    Compute notification effectiveness metrics from Supabase.

    Returns dict with:
        window_days, alerts_created, alerts_notified, alerts_acknowledged,
        alerts_resolved, alerts_outstanding, avg_time_to_ack_hours,
        avg_time_to_resolve_hours, resolution_rate_pct, oldest_open_days,
        generated_at
    """
    now_str = datetime.now(timezone.utc).isoformat()
    since = _since_iso(days)

    try:
        client = _client()
        if not client.is_enabled():
            return _empty_metrics(days, now_str)

        # Fetch all events in window
        events_query = "escalation_events?select=escalation_id,event_type,event_at"
        if since:
            events_query += f"&event_at=gte.{since}"
        events = client.get(events_query) or []

        # Aggregate in Python
        by_type: dict[str, set] = {
            "created": set(),
            "notified": set(),
            "acknowledged": set(),
            "resolved": set(),
        }
        all_events_by_key: dict[str, list] = {}
        for ev in events:
            et = ev.get("event_type", "")
            eid = ev.get("escalation_id", "")
            if et in by_type:
                by_type[et].add(eid)
            all_events_by_key.setdefault(eid, []).append(ev)

        alerts_created = len(by_type["created"])
        alerts_notified = len(by_type["notified"])
        alerts_acknowledged = len(by_type["acknowledged"])
        alerts_resolved = len(by_type["resolved"])

        # Outstanding = open escalations (not time-windowed)
        open_rows = client.get("escalation_history?resolved_at=is.null&select=id,first_detected") or []
        alerts_outstanding = len(open_rows)

        # Avg time to acknowledge and resolve
        avg_ack_hours = _avg_time_between_event_types(all_events_by_key, "created", "acknowledged")
        avg_resolve_hours = _avg_time_between_event_types(all_events_by_key, "created", "resolved")

        # Resolution rate
        total = alerts_created
        resolution_rate = (alerts_resolved / total * 100) if total else 0.0

        # Oldest open
        oldest_open_days: Optional[float] = None
        if open_rows:
            try:
                oldest_str = min(r["first_detected"] for r in open_rows if r.get("first_detected"))
                first = datetime.fromisoformat(oldest_str)
                if first.tzinfo is None:
                    first = first.replace(tzinfo=timezone.utc)
                oldest_open_days = round(
                    (datetime.now(timezone.utc) - first).total_seconds() / 86400, 1
                )
            except Exception:
                pass

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


def _avg_time_between_event_types(
    events_by_key: dict[str, list],
    from_type: str,
    to_type: str,
) -> Optional[float]:
    """Compute average hours between two event types for the same escalation_id."""
    durations = []
    for eid, evs in events_by_key.items():
        from_events = sorted(
            [e for e in evs if e.get("event_type") == from_type],
            key=lambda e: e.get("event_at", ""),
        )
        to_events = sorted(
            [e for e in evs if e.get("event_type") == to_type],
            key=lambda e: e.get("event_at", ""),
        )
        if not from_events or not to_events:
            continue
        try:
            t_from = datetime.fromisoformat(from_events[0]["event_at"])
            # Find first to_type event after from_type
            for te in to_events:
                t_to = datetime.fromisoformat(te["event_at"])
                if t_to > t_from:
                    durations.append((t_to - t_from).total_seconds() / 3600)
                    break
        except Exception:
            continue
    return round(sum(durations) / len(durations), 1) if durations else None


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
    window = f"Last {m['window_days']} Days" if m.get("window_days") else "Lifetime"
    lines = [f":bar_chart: *Alert Metrics — {window}*"]

    created     = m["alerts_created"]
    resolved    = m["alerts_resolved"]
    acked       = m["alerts_acknowledged"]
    outstanding = m["alerts_outstanding"]
    rate        = m["resolution_rate_pct"]

    if created == 0:
        lines.append("No alerts recorded in this period.")
        return "\n".join(lines)

    lines.append(
        f"{created} alert{'s' if created != 1 else ''} raised, "
        f"{resolved} resolved, {outstanding} outstanding."
    )
    if acked:
        lines.append(f"{acked} acknowledged.")
    if m["avg_time_to_resolve_hours"] is not None:
        days_val = m["avg_time_to_resolve_hours"] / 24
        lines.append(f"Average resolution time: {days_val:.1f} day{'s' if days_val != 1 else ''}.")
    if m["avg_time_to_ack_hours"] is not None:
        lines.append(f"Average time to acknowledge: {m['avg_time_to_ack_hours']:.1f} hours.")
    lines.append(f"Resolution rate: {rate}%.")
    if m.get("oldest_open_days") is not None:
        lines.append(f"Oldest open alert: {m['oldest_open_days']:.0f} days.")
    return "\n".join(lines)


def get_metrics_block_for_brief() -> str:
    """Return a compact metrics line for the morning brief."""
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
