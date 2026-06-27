"""
Escalation Manager — MSN-BOT-SOR: Supabase-backed

Prevents alert fatigue by tracking escalation lifecycle and enforcing
notification cadence rules. Same condition is never pushed daily.

Persistence: Supabase escalation_history + escalation_events tables.
             notifications.db (SQLite) is retired — do not copy to VPS.

Notification cadence:
  Day 0  → initial notification
  Day 3  → reminder
  Day 7  → escalation (severity promoted)
  Day 14+ → every 7 days thereafter

Severity progression by notification count:
  1st push: original severity (WARNING)
  2nd push: ALERT
  3rd+ push: CRITICAL
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Notification cadence: days since first_detected
_CADENCE_DAYS = [0, 3, 7]
_REPEAT_INTERVAL_DAYS = 7

from captain_notifications import (
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SEVERITY_ALERT,
    SEVERITY_CRITICAL,
    _SEVERITY_ORDER,
    max_severity,
)

_PROGRESSION = {
    1: lambda s: s,
    2: lambda s: max_severity(s, SEVERITY_ALERT),
    3: lambda s: SEVERITY_CRITICAL,
}


# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------

def _client():
    sys.path.insert(0, str(_REPO_ROOT / "tools" / "supabase"))
    from client import CommanderSupabaseClient
    return CommanderSupabaseClient()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _alert_key(mission_id: str, alert_type: str) -> str:
    return f"{mission_id}:{alert_type}"


# ---------------------------------------------------------------------------
# Core escalation logic
# ---------------------------------------------------------------------------

def _escalated_severity(original: str, count: int) -> str:
    fn = _PROGRESSION.get(count, _PROGRESSION[3])
    return fn(original)


def _should_notify_now(row: dict, today: date) -> bool:
    """Return True if this escalation is due for another notification."""
    first_str = row.get("first_detected", "")
    try:
        first = datetime.fromisoformat(first_str).date()
    except Exception:
        return True
    age_days = (today - first).days
    count = row.get("notification_count", 0)

    if count == 0:
        return True
    if count < len(_CADENCE_DAYS):
        return age_days >= _CADENCE_DAYS[count]

    last_notified = row.get("last_notified")
    if last_notified:
        try:
            last = datetime.fromisoformat(last_notified).date()
            return (today - last).days >= _REPEAT_INTERVAL_DAYS
        except Exception:
            pass
    return False


def process_escalations(
    active_escalations: list[dict],
) -> list[dict]:
    """
    Main entry point.

    Given the raw escalation list from captain_notifications.get_mission_escalations(),
    applies cadence rules and returns only those that should be notified NOW.

    Side effects:
    - Creates new escalation records for first-time alerts
    - Updates notification_count and last_notified on existing records
    - Records events in escalation_events
    - Closes resolved escalations (those no longer in active_escalations)

    Returns filtered list of escalation dicts with current_severity and
    notification_count added.
    """
    today = date.today()
    now_str = _now_iso()

    try:
        client = _client()
        if not client.is_enabled():
            log.warning("[escalation] Supabase not configured — escalation tracking disabled.")
            return active_escalations  # pass-through without cadence enforcement

        # Build lookup of active alert keys
        active_keys = {
            _alert_key(e["id"], at): e
            for e in active_escalations
            for at in _derive_alert_types(e)
        }

        to_notify: list[dict] = []

        # --- Close resolved escalations ---
        open_rows = client.get("escalation_history?resolved_at=is.null&select=*")
        for row in (open_rows or []):
            if row["id"] not in active_keys:
                client._patch(
                    f"escalation_history?id=eq.{_url_encode(row['id'])}",
                    {"resolved_at": now_str},
                )
                client.insert("escalation_events", {
                    "escalation_id": row["id"],
                    "event_type":    "resolved",
                    "event_at":      now_str,
                })
                log.info("[escalation] Auto-closed: %s", row["id"])

        # --- Process active escalations ---
        for key, escalation in active_keys.items():
            alert_type = key.split(":", 1)[1]
            existing = client.get(f"escalation_history?id=eq.{_url_encode(key)}&select=*")
            row = existing[0] if existing else None

            if row is None:
                # First time — create record
                client.insert("escalation_history", {
                    "id":                 key,
                    "mission_id":         escalation["id"],
                    "alert_type":         alert_type,
                    "original_severity":  escalation["severity"],
                    "current_severity":   escalation["severity"],
                    "first_detected":     now_str,
                    "last_notified":      None,
                    "notification_count": 0,
                })
                client.insert("escalation_events", {
                    "escalation_id": key,
                    "event_type":    "created",
                    "event_at":      now_str,
                })
                # Re-fetch to get the row we just created
                fresh = client.get(f"escalation_history?id=eq.{_url_encode(key)}&select=*")
                row = fresh[0] if fresh else {
                    "id": key, "first_detected": now_str,
                    "notification_count": 0, "last_notified": None,
                    "original_severity": escalation["severity"],
                }

            if _should_notify_now(row, today):
                new_count = row.get("notification_count", 0) + 1
                new_severity = _escalated_severity(
                    row.get("original_severity", escalation["severity"]), new_count
                )
                client._patch(
                    f"escalation_history?id=eq.{_url_encode(key)}",
                    {
                        "notification_count": new_count,
                        "last_notified":      now_str,
                        "current_severity":   new_severity,
                    },
                )
                client.insert("escalation_events", {
                    "escalation_id": key,
                    "event_type":    "notified",
                    "severity":      new_severity,
                    "event_at":      now_str,
                    "metadata":      json.dumps({"count": new_count, "severity": new_severity}),
                })
                enriched = {
                    **escalation,
                    "current_severity":   new_severity,
                    "notification_count": new_count,
                    "alert_type":         alert_type,
                }
                to_notify.append(enriched)
            else:
                log.debug(
                    "[escalation] Suppressed (cadence): %s (count=%d)",
                    key, row.get("notification_count", 0),
                )

        return to_notify

    except Exception as exc:
        log.error("[escalation] process_escalations failed: %s", exc)
        return active_escalations  # fail-open: return all so nothing is silently dropped


def _url_encode(value: str) -> str:
    """Percent-encode a value for use in PostgREST query strings."""
    import urllib.parse
    return urllib.parse.quote(str(value), safe="")


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
    if not types:
        types.append("general")
    return list(dict.fromkeys(types))


# ---------------------------------------------------------------------------
# Manual acknowledgement / resolution
# ---------------------------------------------------------------------------

def acknowledge_escalation(alert_key: str) -> bool:
    """Mark an escalation as acknowledged (does not close it)."""
    try:
        client = _client()
        if not client.is_enabled():
            return False
        existing = client.get(
            f"escalation_history?id=eq.{_url_encode(alert_key)}&resolved_at=is.null&select=id"
        )
        if not existing:
            return False
        client.insert("escalation_events", {
            "escalation_id": alert_key,
            "event_type":    "acknowledged",
            "event_at":      _now_iso(),
        })
        return True
    except Exception as exc:
        log.error("[escalation] acknowledge_escalation failed: %s", exc)
        return False


def resolve_escalation(alert_key: str) -> bool:
    """Manually resolve an escalation."""
    try:
        client = _client()
        if not client.is_enabled():
            return False
        existing = client.get(
            f"escalation_history?id=eq.{_url_encode(alert_key)}&resolved_at=is.null&select=id"
        )
        if not existing:
            return False
        now_str = _now_iso()
        client._patch(
            f"escalation_history?id=eq.{_url_encode(alert_key)}",
            {"resolved_at": now_str},
        )
        client.insert("escalation_events", {
            "escalation_id": alert_key,
            "event_type":    "resolved",
            "event_at":      now_str,
        })
        return True
    except Exception as exc:
        log.error("[escalation] resolve_escalation failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_open_escalations() -> list[dict]:
    """Return all currently open (unresolved) escalations."""
    try:
        client = _client()
        if not client.is_enabled():
            return []
        rows = client.get(
            "escalation_history?resolved_at=is.null&order=first_detected.asc&select=*"
        )
        return rows or []
    except Exception as exc:
        log.error("[escalation] get_open_escalations failed: %s", exc)
        return []


def get_escalation_history(limit: int = 50) -> list[dict]:
    """Return recent escalation records (open and closed)."""
    try:
        client = _client()
        if not client.is_enabled():
            return []
        rows = client.get(
            f"escalation_history?order=first_detected.desc&limit={limit}&select=*"
        )
        return rows or []
    except Exception as exc:
        log.error("[escalation] get_escalation_history failed: %s", exc)
        return []
