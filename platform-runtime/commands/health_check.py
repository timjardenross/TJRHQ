"""ROS-001 v1.1 — /health-check command handler.

Captures the daily health check-in via a Block Kit modal and writes to
health_daily_logs in Supabase.

Public API:
    MODAL_CALLBACK_ID        — view callback_id registered in app.py
    build_health_check_modal() -> dict
    handle_health_check_submit(values, user_id, client)
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ── Supabase client ───────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from lib.tz import today_brisbane_iso

def _make_supabase():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        return CommanderSupabaseClient()
    except Exception as exc:
        log.warning("[health-check] Supabase client unavailable: %s", exc)
        return None

# ── Modal ─────────────────────────────────────────────────────────────────────

MODAL_CALLBACK_ID = "health_check_modal"


def build_health_check_modal() -> dict:
    """Return the Block Kit view dict for the daily health check-in modal."""
    today = today_brisbane_iso()
    return {
        "type": "modal",
        "callback_id": MODAL_CALLBACK_ID,
        "title": {"type": "plain_text", "text": "Daily Check-In"},
        "submit": {"type": "plain_text", "text": "Log Check-In"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [

            # ── Context note ─────────────────────────────────────────────────
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{today}*  —  Recovery Operating System check-in.\n"
                        "The Captain is not broken. Recovery is not repair.\n"
                        "The nervous system is doing its job.\n"
                        "_The conditions around it need to change, not the Captain._"
                    ),
                },
            },
            {"type": "divider"},

            # ── Nervous system state ──────────────────────────────────────────
            {
                "type": "input",
                "block_id": "nervous_system_state",
                "label": {"type": "plain_text", "text": "Nervous system right now"},
                "hint": {
                    "type": "plain_text",
                    "text": "No right or wrong answer. This is data, not a grade.",
                },
                "element": {
                    "type": "static_select",
                    "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {
                            "text": {"type": "plain_text", "text": "Calm — settled, present"},
                            "value": "calm",
                        },
                        {
                            "text": {"type": "plain_text", "text": "Activated — alert, some urgency"},
                            "value": "activated",
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Dysregulated — overwhelmed, high activation",
                            },
                            "value": "dysregulated",
                        },
                    ],
                },
            },

            # ── Energy ───────────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "energy",
                "label": {"type": "plain_text", "text": "Energy level"},
                "element": {
                    "type": "static_select",
                    "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Low"}, "value": "low"},
                        {"text": {"type": "plain_text", "text": "Moderate"}, "value": "moderate"},
                        {"text": {"type": "plain_text", "text": "High"}, "value": "high"},
                    ],
                },
            },

            # ── Mood ─────────────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "mood",
                "label": {"type": "plain_text", "text": "Mood"},
                "element": {
                    "type": "static_select",
                    "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Low"}, "value": "low"},
                        {"text": {"type": "plain_text", "text": "Stable"}, "value": "stable"},
                        {"text": {"type": "plain_text", "text": "Positive"}, "value": "positive"},
                    ],
                },
            },

            # ── Sleep ────────────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "sleep_hours",
                "label": {"type": "plain_text", "text": "Sleep last night (hours)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "e.g. 7.5"},
                },
            },
            {
                "type": "input",
                "block_id": "sleep_quality",
                "label": {"type": "plain_text", "text": "Sleep quality"},
                "element": {
                    "type": "static_select",
                    "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Poor"}, "value": "poor"},
                        {"text": {"type": "plain_text", "text": "Fair"}, "value": "fair"},
                        {"text": {"type": "plain_text", "text": "Good"}, "value": "good"},
                    ],
                },
            },

            # ── CPAP ─────────────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "cpap_used",
                "label": {"type": "plain_text", "text": "CPAP used last night?"},
                "element": {
                    "type": "static_select",
                    "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Yes"}, "value": "yes"},
                        {"text": {"type": "plain_text", "text": "No"}, "value": "no"},
                    ],
                },
                "optional": True,
            },
            {
                "type": "input",
                "block_id": "cpap_hours",
                "label": {"type": "plain_text", "text": "CPAP hours (if used)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "e.g. 6"},
                },
                "optional": True,
            },

            # ── Body signals (pain_score) ─────────────────────────────────────
            {
                "type": "input",
                "block_id": "pain_score",
                "label": {"type": "plain_text", "text": "Body signals today (0 = none, 10 = severe)"},
                "hint": {
                    "type": "plain_text",
                    "text": "Body signals are context for capacity planning, not a performance metric.",
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "0–10"},
                },
                "optional": True,
            },

            # ── Sitting tolerance ─────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "sitting_tolerance_minutes",
                "label": {"type": "plain_text", "text": "Max sitting tolerance today (minutes)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "e.g. 45"},
                },
                "optional": True,
            },

            # ── Workload constraint ───────────────────────────────────────────
            {
                "type": "input",
                "block_id": "workload_constraint",
                "label": {"type": "plain_text", "text": "Workload constraint today"},
                "element": {
                    "type": "static_select",
                    "action_id": "value",
                    "initial_option": {
                        "text": {"type": "plain_text", "text": "Unknown"},
                        "value": "unknown",
                    },
                    "options": [
                        {"text": {"type": "plain_text", "text": "Normal"}, "value": "normal"},
                        {"text": {"type": "plain_text", "text": "Modified"}, "value": "modified"},
                        {"text": {"type": "plain_text", "text": "Reduced"}, "value": "reduced"},
                        {"text": {"type": "plain_text", "text": "Unknown"}, "value": "unknown"},
                    ],
                },
                "optional": True,
            },

            # ── Work location ─────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "work_location",
                "label": {"type": "plain_text", "text": "Work location today"},
                "element": {
                    "type": "static_select",
                    "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Home"}, "value": "home"},
                        {"text": {"type": "plain_text", "text": "Office"}, "value": "office"},
                        {"text": {"type": "plain_text", "text": "Travel"}, "value": "travel"},
                        {"text": {"type": "plain_text", "text": "Other"}, "value": "other"},
                    ],
                },
                "optional": True,
            },

            # ── Movement notes ────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "movement_notes",
                "label": {"type": "plain_text", "text": "Movement notes (optional)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "multiline": False,
                    "placeholder": {"type": "plain_text", "text": "e.g. short walk, stretching"},
                },
                "optional": True,
            },

            # ── Notes ─────────────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "notes",
                "label": {"type": "plain_text", "text": "Notes (optional)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Anything else the Medical Officer should know today.",
                    },
                },
                "optional": True,
            },
        ],
    }


# ── Submission handler ────────────────────────────────────────────────────────

def _extract(values: dict, block_id: str) -> str | None:
    """Pull the first action value from Block Kit state values."""
    block = values.get(block_id, {})
    for action in block.values():
        v = action.get("selected_option") or action.get("value")
        if isinstance(v, dict):
            return v.get("value")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def handle_health_check_submit(values: dict, user_id: str, client) -> None:
    """Write check-in to health_daily_logs and DM confirmation to user."""
    today = today_brisbane_iso()

    # ── Parse modal values ────────────────────────────────────────────────────
    def _int(val: str | None) -> int | None:
        try:
            return int(float(val)) if val is not None else None
        except (ValueError, TypeError):
            return None

    def _float(val: str | None) -> float | None:
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    nervous_system_state = _extract(values, "nervous_system_state")
    energy               = _extract(values, "energy")
    mood                 = _extract(values, "mood")
    sleep_quality        = _extract(values, "sleep_quality")
    sleep_hours          = _float(_extract(values, "sleep_hours"))
    cpap_used_raw        = _extract(values, "cpap_used")
    cpap_used            = True if cpap_used_raw == "yes" else (False if cpap_used_raw == "no" else None)
    cpap_hours           = _float(_extract(values, "cpap_hours"))
    pain_score           = _int(_extract(values, "pain_score"))
    sitting_tolerance    = _int(_extract(values, "sitting_tolerance_minutes"))
    workload_constraint  = _extract(values, "workload_constraint") or "unknown"
    work_location        = _extract(values, "work_location")
    movement_notes       = _extract(values, "movement_notes")
    notes                = _extract(values, "notes")

    payload: dict = {
        "log_date":              today,
        "source":                "slack",
        "nervous_system_state":  nervous_system_state,
        "energy":                energy,
        "mood":                  mood,
        "sleep_quality":         sleep_quality,
        "workload_constraint":   workload_constraint,
    }
    if sleep_hours is not None:    payload["sleep_hours"]                = sleep_hours
    if cpap_used is not None:      payload["cpap_used"]                  = cpap_used
    if cpap_hours is not None:     payload["cpap_hours"]                 = cpap_hours
    if pain_score is not None:     payload["pain_score"]                 = max(0, min(10, pain_score))
    if sitting_tolerance is not None: payload["sitting_tolerance_minutes"] = sitting_tolerance
    if work_location:              payload["work_location"]              = work_location
    if movement_notes:             payload["movement_notes"]             = movement_notes
    if notes:                      payload["notes"]                      = notes

    # ── Write to Supabase ─────────────────────────────────────────────────────
    db = _make_supabase()
    saved = False
    if db and db.is_enabled():
        # Upsert on log_date so re-submitting today updates the record
        try:
            result = db.raw_client.table("health_daily_logs").upsert(
                payload, on_conflict="log_date"
            ).execute()
            saved = True
            log.info("[health-check] Upserted health_daily_logs for %s", today)
        except Exception as exc:
            log.error("[health-check] Supabase upsert failed: %s", exc)
            # Fall back to insert
            result = db.insert("health_daily_logs", payload)
            saved = result.ok
    else:
        log.warning("[health-check] Supabase unavailable — check-in not persisted")

    if saved:
        # ADR-024 second-pass audit: 'health_daily_logs' domain_registry row
        # (migration 0071) has had zero record_heartbeat() calls anywhere in
        # the repo — never_succeeded in verification_state despite this write
        # path being live. Non-blocking, never affects check-in delivery.
        try:
            sys.path.insert(0, str(_REPO_ROOT / "core" / "platform"))
            from heartbeat import record_heartbeat
            record_heartbeat("health_daily_logs", status="ok", detail=f"log_date={today}")
        except Exception:
            pass

    # ── Build confirmation message ────────────────────────────────────────────
    ns_label = {
        "calm": "Calm",
        "activated": "Activated",
        "dysregulated": "Dysregulated",
    }.get(nervous_system_state or "", nervous_system_state or "—")

    energy_label = (energy or "—").capitalize()
    mood_label   = (mood or "—").capitalize()
    sleep_str    = f"{sleep_hours}h" if sleep_hours is not None else "—"
    sq_label     = (sleep_quality or "—").capitalize()

    status_line = ":white_check_mark: Check-in logged." if saved else ":warning: Check-in received but could not be saved to database."

    dm_text = (
        f"{status_line}\n\n"
        f"*{today} — Daily Check-In Summary*\n\n"
        f"• *Nervous system:* {ns_label}\n"
        f"• *Energy:* {energy_label}\n"
        f"• *Mood:* {mood_label}\n"
        f"• *Sleep:* {sleep_str} · {sq_label}\n"
    )
    if sitting_tolerance is not None:
        dm_text += f"• *Sitting tolerance:* {sitting_tolerance} min\n"
    if pain_score is not None:
        dm_text += f"• *Body signals:* {pain_score}/10\n"
    dm_text += (
        "\n_The Captain is not broken. Recovery is not repair.\n"
        "The nervous system is doing its job._"
    )

    try:
        client.chat_postMessage(channel=user_id, text=dm_text)
    except Exception as exc:
        log.error("[health-check] DM failed: %s", exc)
