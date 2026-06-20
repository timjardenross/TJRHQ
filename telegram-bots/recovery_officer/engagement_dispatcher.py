"""D-055 Recovery Officer — Telegram engagement dispatcher.

This module is bot-agnostic. Import it into any of the three existing
Telegram bots (@starship_endeavour_bot, @Starship_endeavour_xO_bot,
@Starship_ChiefEngineer_bot) or use standalone via the CLI entry point.

Usage (from an existing bot):
    from telegram_bots.recovery_officer.engagement_dispatcher import (
        get_recovery_status,
        build_pulse_reminder,
        build_escalation_message,
        run_dispatch_check,
    )

Standalone (cron / APScheduler):
    python -m telegram_bots.recovery_officer.engagement_dispatcher

Environment variables required (set in bot's .env):
    SUPABASE_URL       — Supabase project URL
    SUPABASE_KEY       — Supabase anon or service-role key
    TELEGRAM_BOT_TOKEN — Bot token for the bot running this dispatcher
    TELEGRAM_CHAT_ID   — Captain's chat / DM ID to send reminders to
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Supabase ──────────────────────────────────────────────────────────────────

def _get_supabase_client():
    """Return a supabase-py client using env vars directly (no CommanderSupabaseClient dependency)."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        log.warning("[recovery-dispatcher] SUPABASE_URL or SUPABASE_KEY not set")
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except ImportError:
        log.error("[recovery-dispatcher] supabase-py not installed. Run: pip install supabase")
        return None
    except Exception as exc:
        log.error("[recovery-dispatcher] Supabase client error: %s", exc)
        return None


# ── Recovery status model ─────────────────────────────────────────────────────

@dataclass
class RecoveryStatus:
    recovery_confidence: int       # 0–100
    pulses_completed: int          # 0–4
    pulses_missing: int            # 0–4
    morning_done: bool
    midday_done: bool
    end_of_day_done: bool
    evening_done: bool
    confidence_label: str
    latest_energy: str | None
    latest_nervous_system: str | None
    latest_body_signals: str | None
    latest_readiness: str | None
    last_pulse_at: str | None

    @property
    def escalation_level(self) -> int:
        """0=none, 1=friendly reminder, 2=RO notification, 3=critical."""
        if self.recovery_confidence == 0 and self.pulses_completed == 0:
            # No data at all
            hour = datetime.now().hour
            if hour >= 14:
                return 3  # Afternoon with zero pulses — critical
            if hour >= 9:
                return 2  # Mid-morning with no morning pulse
            return 1
        if self.recovery_confidence <= 25:
            return 2
        if self.recovery_confidence <= 50:
            return 1
        return 0

    @property
    def next_suggested_pulse(self) -> str | None:
        """Return the type of the next pulse not yet completed."""
        if not self.morning_done:    return "morning"
        if not self.midday_done:     return "midday"
        if not self.end_of_day_done: return "end_of_day"
        if not self.evening_done:    return "evening"
        return None


_STATUS_DEFAULTS = RecoveryStatus(
    recovery_confidence=0,
    pulses_completed=0,
    pulses_missing=4,
    morning_done=False,
    midday_done=False,
    end_of_day_done=False,
    evening_done=False,
    confidence_label="No telemetry today",
    latest_energy=None,
    latest_nervous_system=None,
    latest_body_signals=None,
    latest_readiness=None,
    last_pulse_at=None,
)


def get_recovery_status(supabase_client: Any | None = None) -> RecoveryStatus:
    """Fetch today's recovery confidence from Supabase view."""
    client = supabase_client or _get_supabase_client()
    if client is None:
        return _STATUS_DEFAULTS
    try:
        result = client.table("recovery_confidence_today").select("*").execute()
        if result.data:
            row = result.data[0]
            return RecoveryStatus(
                recovery_confidence=row.get("recovery_confidence", 0),
                pulses_completed=row.get("pulses_completed", 0),
                pulses_missing=row.get("pulses_missing", 4),
                morning_done=row.get("morning_done", False),
                midday_done=row.get("midday_done", False),
                end_of_day_done=row.get("end_of_day_done", False),
                evening_done=row.get("evening_done", False),
                confidence_label=row.get("confidence_label", "Unknown"),
                latest_energy=row.get("latest_energy"),
                latest_nervous_system=row.get("latest_nervous_system"),
                latest_body_signals=row.get("latest_body_signals"),
                latest_readiness=row.get("latest_readiness"),
                last_pulse_at=row.get("last_pulse_at"),
            )
    except Exception as exc:
        log.error("[recovery-dispatcher] get_recovery_status failed: %s", exc)
    return _STATUS_DEFAULTS


# ── Message builders ──────────────────────────────────────────────────────────

_PULSE_LABELS = {
    "morning":    "🌅 Morning Readiness",
    "midday":     "🌤 Midday Status",
    "end_of_day": "🌇 End of Workday",
    "evening":    "🌃 Evening Recovery",
}

_PULSE_HINTS = {
    "morning":    "Sets the posture for today's missions. Takes under 60 seconds.",
    "midday":     "Course correction checkpoint. How is capacity holding?",
    "end_of_day": "Transition to recovery mode. Mark the workday closed.",
    "evening":    "Recovery completion loop. Close the day with intention.",
}


def _bar(pct: int) -> str:
    filled = int(pct / 10)
    return "█" * filled + "░" * (10 - filled)


def build_pulse_reminder(status: RecoveryStatus, pulse_type: str | None = None) -> str:
    """Build a friendly L1 pulse reminder message."""
    target = pulse_type or status.next_suggested_pulse or "morning"
    label  = _PULSE_LABELS.get(target, target.replace("_", " ").title())
    hint   = _PULSE_HINTS.get(target, "")

    done_str = " ".join([
        "🟣" if status.morning_done    else "⚪",
        "🟣" if status.midday_done     else "⚪",
        "🟣" if status.end_of_day_done else "⚪",
        "🟣" if status.evening_done    else "⚪",
    ])

    lines = [
        f"📡 *Recovery Pulse — {date.today().isoformat()}*",
        "",
        f"Confidence: `{_bar(status.recovery_confidence)}` {status.recovery_confidence}%",
        f"Pulses: {done_str}  ({status.pulses_completed}/4 complete)",
        "",
        f"⏰ *Next up: {label}*",
        f"_{hint}_",
        "",
        "Log your pulse in the LCARS portal → Medical Bay → Recovery Pulse",
        "or use `/recovery-pulse` in Slack.",
        "",
        "_Missed pulses are information, not failure._",
    ]
    return "\n".join(lines)


def build_escalation_message(status: RecoveryStatus, level: int) -> str:
    """Build an escalation message for L2 or L3 scenarios."""
    today = date.today().isoformat()

    if level == 3:
        header = "🔴 *Recovery Officer — Critical Alert*"
        body = (
            f"No recovery pulses logged today ({today}).\n"
            f"Recovery confidence is at {status.recovery_confidence}%.\n\n"
            "This affects mission planning accuracy and crew capacity assessment.\n\n"
            "*Action required:* Log at least one pulse to restore telemetry baseline.\n"
            "Portal: Medical Bay → Recovery Pulse\n"
            "Slack: `/recovery-pulse`"
        )
    else:
        header = "🟠 *Recovery Officer — Confidence Low*"
        body = (
            f"Recovery confidence is at {status.recovery_confidence}% ({today}).\n"
            f"{status.pulses_completed}/4 pulses logged.\n\n"
            f"*Missing:* "
            + ", ".join(filter(None, [
                "Morning"    if not status.morning_done    else None,
                "Midday"     if not status.midday_done     else None,
                "End of day" if not status.end_of_day_done else None,
                "Evening"    if not status.evening_done    else None,
            ]))
            + "\n\nLow confidence may trigger mission deferral recommendations."
        )

    return f"{header}\n\n{body}"


def build_daily_summary(status: RecoveryStatus) -> str:
    """Build an end-of-day confidence summary message."""
    today = date.today().isoformat()
    done_str = " ".join([
        "✅" if status.morning_done    else "❌",
        "✅" if status.midday_done     else "❌",
        "✅" if status.end_of_day_done else "❌",
        "✅" if status.evening_done    else "❌",
    ])
    lines = [
        f"📊 *Recovery Summary — {today}*",
        "",
        f"Confidence: `{_bar(status.recovery_confidence)}` {status.recovery_confidence}%",
        f"Pulses:  {done_str}",
        f"         AM · Mid · EOD · PM",
        "",
        f"_{status.confidence_label}_",
    ]
    if status.latest_energy or status.latest_nervous_system or status.latest_body_signals:
        lines.append("")
        lines.append("*Latest signals:*")
        if status.latest_energy:          lines.append(f"• Capacity: {status.latest_energy.capitalize()}")
        if status.latest_nervous_system:  lines.append(f"• NS: {status.latest_nervous_system.capitalize()}")
        if status.latest_body_signals:    lines.append(f"• Body: {status.latest_body_signals.capitalize()}")
        if status.latest_readiness:       lines.append(f"• Readiness: {status.latest_readiness.capitalize()}")

    return "\n".join(lines)


# ── Dispatch logic ────────────────────────────────────────────────────────────

def run_dispatch_check(
    bot,
    chat_id: str | int,
    *,
    supabase_client: Any | None = None,
    force_summary: bool = False,
) -> dict:
    """
    Core dispatch logic. Call this from any bot's scheduled job or command handler.

    Args:
        bot:              python-telegram-bot Bot instance (or any object with
                          send_message(chat_id, text, parse_mode) method)
        chat_id:          Telegram chat/user ID to send messages to
        supabase_client:  Optional pre-built Supabase client; creates one if None
        force_summary:    Send full summary regardless of escalation level

    Returns:
        dict with keys: confidence, level, action, message_sent
    """
    status = get_recovery_status(supabase_client)
    level  = status.escalation_level
    hour   = datetime.now().hour

    result = {"confidence": status.recovery_confidence, "level": level, "action": "none", "message_sent": False}

    # All 4 pulses done — send end-of-day summary once (at evening time)
    if status.pulses_completed == 4 or force_summary:
        msg = build_daily_summary(status)
        _send(bot, chat_id, msg)
        result.update(action="daily_summary", message_sent=True)
        return result

    # L3: Critical — no pulses and it's afternoon+
    if level == 3:
        msg = build_escalation_message(status, level=3)
        _send(bot, chat_id, msg)
        result.update(action="escalation_l3", message_sent=True)
        return result

    # L2: Low confidence (1 pulse logged, or no pulses before midday)
    if level == 2:
        msg = build_escalation_message(status, level=2)
        _send(bot, chat_id, msg)
        result.update(action="escalation_l2", message_sent=True)
        return result

    # L1: Friendly reminder — only during appropriate hours
    next_pulse = status.next_suggested_pulse
    if next_pulse:
        # Only remind during relevant windows
        should_remind = (
            (next_pulse == "morning"    and 7  <= hour < 12) or
            (next_pulse == "midday"     and 12 <= hour < 15) or
            (next_pulse == "end_of_day" and 15 <= hour < 19) or
            (next_pulse == "evening"    and 19 <= hour < 23)
        )
        if should_remind:
            msg = build_pulse_reminder(status, next_pulse)
            _send(bot, chat_id, msg)
            result.update(action=f"reminder_{next_pulse}", message_sent=True)

    return result


def _send(bot: Any, chat_id: str | int, text: str) -> None:
    try:
        bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        log.info("[recovery-dispatcher] Sent message to chat_id=%s", chat_id)
    except Exception as exc:
        log.error("[recovery-dispatcher] send_message failed: %s", exc)


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    """Standalone check — prints current status without sending Telegram messages."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from dotenv import load_dotenv
    load_dotenv()

    status = get_recovery_status()
    print(build_daily_summary(status))
    print(f"\nEscalation level: {status.escalation_level}")
    if status.next_suggested_pulse:
        print(f"\n--- L1 Reminder preview ---")
        print(build_pulse_reminder(status))
