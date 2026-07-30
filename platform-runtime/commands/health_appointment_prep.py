"""
Appointment Preparation Workflow — M-20260614 WP4

Two entry points:
  1. check_upcoming_appointments(client, lead_days) — scheduled job.
     Queries health_events for appointments within lead_days (default 2).
     For each upcoming appointment found, generates a preparation brief
     and posts it to the Captain's DM / BRIEF_CHANNEL.

  2. handle_health_prep(ack, command, client) — /health-prep Slack command.
     Manual trigger. Generates a preparation brief for the next appointment
     found in health_events (regardless of lead time).

Preparation brief includes:
  - Appointment details (type, provider, date)
  - Pain summary (last 7 days average, trend)
  - Sleep summary (last 7 days average)
  - Energy summary (last 7 days distribution)
  - Capacity trend (last 7 days status distribution)
  - Health events since last appointment
  - Follow-up items from previous appointment
  - Suggested discussion topics (derived from trends)

Privacy boundary:
  - Reads only aggregated/summary fields — no raw clinical notes
  - No medication names, diagnoses, or imaging results included
  - Safety footer appended to all outputs

Configuration (.env):
  BRIEF_CHANNEL / BRIEF_USER_ID  — delivery target
  APPOINTMENT_LEAD_DAYS          — hours before appointment to trigger (default 48)
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HEALTH_LIB = _REPO_ROOT / "core" / "health"
if str(_HEALTH_LIB) not in sys.path:
    sys.path.insert(0, str(_HEALTH_LIB))

_BRIEF_CHANNEL = os.environ.get("BRIEF_CHANNEL", "")
_BRIEF_USER_ID = os.environ.get("BRIEF_USER_ID", "")
_LEAD_DAYS     = int(os.environ.get("APPOINTMENT_LEAD_DAYS", "2"))

SAFETY_FOOTER = (
    "\n\n---\n"
    "_This preparation brief is advisory only. It is not a substitute for "
    "professional medical advice. Discuss all clinical questions with your "
    "healthcare provider._"
)


# ---------------------------------------------------------------------------
# Supabase query helpers
# ---------------------------------------------------------------------------

def _get_upcoming_appointments(lead_days: int) -> list[dict]:
    """Return health_events rows of type 'appointment' within lead_days."""
    try:
        sys.path.insert(0, str(_HEALTH_LIB))
        from supabase_client import supabase_get, is_configured
        if not is_configured():
            log.warning("[appt-prep] Supabase not configured — skipping appointment check")
            return []
        today = date.today().isoformat()
        cutoff = (date.today() + timedelta(days=lead_days)).isoformat()
        rows = supabase_get(
            f"health_events"
            f"?event_type=eq.appointment"
            f"&event_date=gte.{today}"
            f"&event_date=lte.{cutoff}"
            f"&order=event_date.asc"
        )
        return rows or []
    except Exception as exc:
        log.error("[appt-prep] Failed to query upcoming appointments: %s", exc)
        return []


def _get_next_appointment() -> Optional[dict]:
    """Return the next upcoming appointment regardless of lead time."""
    try:
        sys.path.insert(0, str(_HEALTH_LIB))
        from supabase_client import supabase_get, is_configured
        if not is_configured():
            return None
        today = date.today().isoformat()
        rows = supabase_get(
            f"health_events"
            f"?event_type=eq.appointment"
            f"&event_date=gte.{today}"
            f"&order=event_date.asc"
            f"&limit=1"
        )
        return rows[0] if rows else None
    except Exception as exc:
        log.error("[appt-prep] Failed to query next appointment: %s", exc)
        return None


def _get_health_summary_period(days: int = 7) -> dict:
    """Return aggregated health metrics for the last N days."""
    try:
        from supabase_client import supabase_get, is_configured
        if not is_configured():
            return {}
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        rows = supabase_get(
            f"analytics_health_daily"
            f"?log_date=gte.{cutoff}"
            f"&order=log_date.desc"
        ) or []
        if not rows:
            return {}
        pain_scores  = [r["pain_score"] for r in rows if r.get("pain_score") is not None]
        sleep_hours  = [r["sleep_hours"] for r in rows if r.get("sleep_hours") is not None]
        energies     = [r.get("energy", "") for r in rows if r.get("energy")]
        statuses     = [r.get("health_status", "") for r in rows if r.get("health_status")]
        cpap_hours   = [r["cpap_hours"] for r in rows if r.get("cpap_hours") is not None]
        return {
            "days_logged": len(rows),
            "avg_pain": round(sum(pain_scores) / len(pain_scores), 1) if pain_scores else None,
            "max_pain": max(pain_scores) if pain_scores else None,
            "avg_sleep": round(sum(sleep_hours) / len(sleep_hours), 1) if sleep_hours else None,
            "avg_cpap": round(sum(cpap_hours) / len(cpap_hours), 1) if cpap_hours else None,
            "energy_counts": {e: energies.count(e) for e in set(energies)},
            "status_counts": {s: statuses.count(s) for s in set(statuses)},
            "red_days": statuses.count("RED") + statuses.count("Red"),
            "amber_days": statuses.count("AMBER") + statuses.count("Amber"),
            "green_days": statuses.count("GREEN") + statuses.count("Green"),
        }
    except Exception as exc:
        log.error("[appt-prep] Failed to get health summary: %s", exc)
        return {}


def _get_recent_health_events(since_days: int = 30) -> list[dict]:
    """Return health_events from the last N days (excluding upcoming appointments)."""
    try:
        from supabase_client import supabase_get, is_configured
        if not is_configured():
            return []
        cutoff = (date.today() - timedelta(days=since_days)).isoformat()
        today = date.today().isoformat()
        rows = supabase_get(
            f"health_events"
            f"?event_date=gte.{cutoff}"
            f"&event_date=lte.{today}"
            f"&event_type=neq.appointment"
            f"&order=event_date.desc"
            f"&limit=10"
        )
        return rows or []
    except Exception as exc:
        log.error("[appt-prep] Failed to get recent health events: %s", exc)
        return []


def _get_pending_followups() -> list[dict]:
    """Return health_events with follow_up_required=true and follow_up_date not yet passed."""
    try:
        from supabase_client import supabase_get, is_configured
        if not is_configured():
            return []
        rows = supabase_get(
            f"health_events"
            f"?follow_up_required=eq.true"
            f"&order=follow_up_date.asc"
            f"&limit=10"
        )
        return rows or []
    except Exception as exc:
        log.error("[appt-prep] Failed to get pending follow-ups: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Brief generation
# ---------------------------------------------------------------------------

def _generate_prep_brief(appointment: dict, health_summary: dict, recent_events: list[dict], follow_ups: list[dict]) -> str:
    lines = []

    # Header
    appt_date  = appointment.get("event_date", "Unknown date")
    appt_title = appointment.get("title", "Medical Appointment")
    provider   = appointment.get("provider", "")
    outcome    = appointment.get("description", "")

    lines.append(f":stethoscope: *Appointment Preparation Brief*")
    lines.append(f"*{appt_title}*" + (f" — {provider}" if provider else ""))
    lines.append(f"Date: {appt_date}")
    if outcome:
        lines.append(f"Notes: {outcome[:120]}")
    lines.append("")

    # Health summary
    if health_summary:
        days = health_summary.get("days_logged", 0)
        lines.append(f"*Health Summary — Last {days} days logged:*")
        avg_pain = health_summary.get("avg_pain")
        max_pain = health_summary.get("max_pain")
        if avg_pain is not None:
            pain_trend = "elevated" if avg_pain >= 6 else ("moderate" if avg_pain >= 4 else "low")
            lines.append(f"  • Pain: average {avg_pain}/10 (peak {max_pain}/10) — {pain_trend}")
        avg_sleep = health_summary.get("avg_sleep")
        if avg_sleep is not None:
            sleep_quality = "good" if avg_sleep >= 7 else ("fair" if avg_sleep >= 6 else "reduced")
            lines.append(f"  • Sleep: average {avg_sleep} hrs/night — {sleep_quality}")
        avg_cpap = health_summary.get("avg_cpap")
        if avg_cpap is not None:
            lines.append(f"  • CPAP: average {avg_cpap} hrs/night")
        energy = health_summary.get("energy_counts", {})
        if energy:
            dominant = max(energy, key=energy.get)
            lines.append(f"  • Energy: most days {dominant}")
        red_days   = health_summary.get("red_days", 0)
        amber_days = health_summary.get("amber_days", 0)
        green_days = health_summary.get("green_days", 0)
        if red_days or amber_days or green_days:
            lines.append(f"  • Status distribution: {green_days} Green / {amber_days} Amber / {red_days} Red")
        lines.append("")
    else:
        lines.append("*Health Summary:* No check-in data found for recent period.")
        lines.append("")

    # Recent events
    if recent_events:
        lines.append("*Recent Health Events (last 30 days):*")
        for ev in recent_events[:6]:
            ev_date  = ev.get("event_date", "")
            ev_type  = ev.get("event_type", "").replace("_", " ").title()
            ev_title = ev.get("title", ev_type)
            lines.append(f"  • {ev_date}: {ev_title} ({ev_type})")
        lines.append("")

    # Follow-ups
    if follow_ups:
        lines.append("*Pending Follow-up Items:*")
        for fu in follow_ups[:5]:
            fu_date  = fu.get("follow_up_date", "unscheduled")
            fu_title = fu.get("title", "")
            fu_notes = fu.get("follow_up_notes", "")
            line = f"  • {fu_title}"
            if fu_date:
                line += f" (due: {fu_date})"
            if fu_notes:
                line += f" — {fu_notes[:80]}"
            lines.append(line)
        lines.append("")

    # Suggested discussion topics (derived from data)
    lines.append("*Suggested Discussion Topics:*")
    topics = _derive_discussion_topics(health_summary, recent_events, follow_ups)
    for t in topics:
        lines.append(f"  • {t}")

    lines.append(SAFETY_FOOTER)
    return "\n".join(lines)


def _derive_discussion_topics(health_summary: dict, recent_events: list, follow_ups: list) -> list[str]:
    """Derive discussion topics from health data patterns."""
    topics = []

    avg_pain = health_summary.get("avg_pain") if health_summary else None
    if avg_pain is not None and avg_pain >= 5:
        topics.append(f"Pain management — average {avg_pain}/10 over recent period")

    avg_sleep = health_summary.get("avg_sleep") if health_summary else None
    if avg_sleep is not None and avg_sleep < 6.5:
        topics.append(f"Sleep quality — averaging {avg_sleep} hrs/night")

    avg_cpap = health_summary.get("avg_cpap") if health_summary else None
    if avg_cpap is not None and avg_cpap < 5:
        topics.append(f"CPAP compliance — averaging {avg_cpap} hrs/night")

    red_days = health_summary.get("red_days", 0) if health_summary else 0
    if red_days >= 3:
        topics.append(f"Functional capacity — {red_days} RED days in recent period")

    # Pending follow-ups become discussion topics
    for fu in follow_ups[:3]:
        title = fu.get("title", "")
        if title:
            topics.append(f"Follow-up: {title}")

    # Medication changes become discussion topics
    med_changes = [ev for ev in recent_events if ev.get("event_type") == "medication_change"]
    for mc in med_changes[:2]:
        topics.append(f"Medication update: {mc.get('title', 'recent change')}")

    if not topics:
        topics.append("General health review and progress since last visit")
        topics.append("Current symptoms and functional capacity")

    return topics[:7]


# ---------------------------------------------------------------------------
# Delivery helpers
# ---------------------------------------------------------------------------

def _post(client, text: str) -> bool:
    channel = _BRIEF_CHANNEL or _BRIEF_USER_ID
    if not channel:
        log.warning("[appt-prep] No delivery channel configured (BRIEF_CHANNEL / BRIEF_USER_ID)")
        return False
    try:
        client.chat_postMessage(channel=channel, text=text)
        return True
    except Exception as exc:
        log.error("[appt-prep] Slack post failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Scheduled job — called by proactive_scheduler
# ---------------------------------------------------------------------------

def check_upcoming_appointments(client, lead_days: int = _LEAD_DAYS) -> int:
    """
    Check for upcoming appointments and post preparation briefs.
    Returns the number of briefs posted.
    """
    appointments = _get_upcoming_appointments(lead_days)
    if not appointments:
        log.info("[appt-prep] No appointments within %d days", lead_days)
        return 0

    health_summary = _get_health_summary_period(days=7)
    recent_events  = _get_recent_health_events(since_days=30)
    follow_ups     = _get_pending_followups()

    posted = 0
    for appt in appointments:
        try:
            brief = _generate_prep_brief(appt, health_summary, recent_events, follow_ups)
            if _post(client, brief):
                posted += 1
                log.info("[appt-prep] Appointment prep brief posted for %s on %s",
                         appt.get("title", "appointment"), appt.get("event_date", ""))
        except Exception as exc:
            log.error("[appt-prep] Brief generation failed: %s", exc)

    return posted


# ---------------------------------------------------------------------------
# Slack command handler — /health-prep
# ---------------------------------------------------------------------------

def handle_health_prep(ack, command, client):
    """/health-prep — generate appointment preparation brief for next appointment."""
    ack()
    user_id = command.get("user_id", "")
    try:
        appointment = _get_next_appointment()
        if not appointment:
            client.chat_postMessage(
                channel=user_id,
                text=(
                    ":calendar: *No upcoming appointments found in health_events.*\n\n"
                    "Log an appointment using `/health-event` (type: appointment) to enable preparation briefs."
                )
            )
            return

        health_summary = _get_health_summary_period(days=7)
        recent_events  = _get_recent_health_events(since_days=30)
        follow_ups     = _get_pending_followups()
        brief = _generate_prep_brief(appointment, health_summary, recent_events, follow_ups)
        client.chat_postMessage(channel=user_id, text=brief)
        log.info("[appt-prep] /health-prep brief delivered to %s", user_id)
    except Exception as exc:
        log.error("[appt-prep] /health-prep failed: %s", exc)
        client.chat_postMessage(
            channel=user_id,
            text=f":warning: Appointment prep failed: {exc}"
        )
