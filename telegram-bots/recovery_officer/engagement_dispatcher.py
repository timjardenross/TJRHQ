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
    python -m telegram_bots.recovery_officer.engagement_dispatcher --dispatch

2026-08-10: now actually scheduled — intelligence/scheduler.py's
_wellness_reminder_job() calls run_dispatch_check() on an interval (see
that module for the live wiring), using _StandaloneTelegramBot below as the
`bot` argument since the scheduler daemon has no live python-telegram-bot
Application/event loop to reuse. run_dispatch_check() de-dups per
(Brisbane day, pulse window, action) via the wellness_reminder_log table
(migration 0118), so it's safe to call on a timer without re-sending an
identical reminder while a pulse window stays open and unlogged.

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

def _brisbane_today() -> str:
    """Return today's date string in Australia/Brisbane time."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Australia/Brisbane")).date().isoformat()
    except Exception:
        return date.today().isoformat()
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
    pulses_completed: int          # 0–3 (Captain directive 2026-08-10: reduced from 4)
    pulses_missing: int            # 0–3
    morning_done: bool
    midday_done: bool
    evening_done: bool
    confidence_label: str
    latest_energy: str | None
    latest_nervous_system: str | None
    latest_body_signals: str | None
    latest_readiness: str | None
    last_pulse_at: str | None

    @property
    def escalation_level(self) -> int:
        """0=none, 1=friendly reminder, 2=RO notification, 3=critical.

        MSN-0305: delegates to the canonical implementation in
        wellness_officer/intelligence.py — was one of 3 independent copies
        of this exact logic (MSN-0302 finding).
        """
        from telegram_bots.wellness_officer.intelligence import escalation_level as _escalation_level
        return _escalation_level(self.recovery_confidence, self.pulses_completed)

    @property
    def next_suggested_pulse(self) -> str | None:
        """Return the type of the next pulse not yet completed."""
        if not self.morning_done: return "morning"
        if not self.midday_done:  return "midday"
        if not self.evening_done: return "evening"
        return None


_STATUS_DEFAULTS = RecoveryStatus(
    recovery_confidence=0,
    pulses_completed=0,
    pulses_missing=3,
    morning_done=False,
    midday_done=False,
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
                pulses_missing=row.get("pulses_missing", 3),
                morning_done=row.get("morning_done", False),
                midday_done=row.get("midday_done", False),
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
    "morning": "🌅 Morning Readiness",
    "midday":  "🌤 Midday Status",
    "evening": "🌃 Evening Recovery",
}

_PULSE_HINTS = {
    "morning": "Sets the posture for today's missions. Takes under 60 seconds.",
    "midday":  "Course correction checkpoint. How is capacity holding?",
    "evening": "Recovery completion loop. Close the day with intention.",
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
        "🟣" if status.morning_done else "⚪",
        "🟣" if status.midday_done  else "⚪",
        "🟣" if status.evening_done else "⚪",
    ])

    lines = [
        f"📡 *Recovery Pulse — {_brisbane_today()}*",
        "",
        f"Confidence: `{_bar(status.recovery_confidence)}` {status.recovery_confidence}%",
        f"Pulses: {done_str}  ({status.pulses_completed}/3 complete)",
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
    today = _brisbane_today()

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
            f"{status.pulses_completed}/3 pulses logged.\n\n"
            f"*Missing:* "
            + ", ".join(filter(None, [
                "Morning" if not status.morning_done else None,
                "Midday"  if not status.midday_done  else None,
                "Evening" if not status.evening_done else None,
            ]))
            + "\n\nLow confidence may trigger mission deferral recommendations."
        )

    return f"{header}\n\n{body}"


def build_daily_summary(status: RecoveryStatus) -> str:
    """Build an end-of-day confidence summary message."""
    today = _brisbane_today()
    done_str = " ".join([
        "✅" if status.morning_done else "❌",
        "✅" if status.midday_done  else "❌",
        "✅" if status.evening_done else "❌",
    ])
    lines = [
        f"📊 *Recovery Summary — {today}*",
        "",
        f"Confidence: `{_bar(status.recovery_confidence)}` {status.recovery_confidence}%",
        f"Pulses:  {done_str}",
        f"         AM · Mid · PM",
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


# ── De-duplication ────────────────────────────────────────────────────────────
#
# run_dispatch_check() is a pure function of *current* pulse state — nothing
# below this line changes that. What changes is that every send is now gated
# on "has this exact (Brisbane day, pulse window, action) already gone out?",
# persisted to Supabase (wellness_reminder_log, migration 0118) rather than
# in-memory, so the guarantee survives scheduler restarts. See module
# docstring: this is what makes it safe to call run_dispatch_check() on a
# timer instead of only ever from a human-triggered /dispatch.

_REMINDER_LOG_TABLE = "wellness_reminder_log"


def _brisbane_now() -> datetime:
    """Brisbane-local now(), matching pulse_time.py's and
    wellness_officer/intelligence.py::escalation_level()'s own tz handling
    (MSN-0305 fixed escalation_level's naive-local-time drift risk; the hour
    used for this module's own should_remind gating had the identical bug
    and is fixed the same way here)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Australia/Brisbane"))
    except Exception:
        return datetime.now()


def _current_pulse_window(hour: int) -> str:
    """Canonical morning/midday/evening bucket for the given Brisbane hour —
    reuses telegram_bots.xo.pulse_time.pulse_type_for_hour(), the single
    source of truth for the 3x/day pulse schedule (Captain directive
    2026-08-10), rather than a second, drifting copy of the same split.
    Falls back to an inline copy of the identical bucketing only if the
    import itself fails (e.g. run outside the repo's package layout)."""
    try:
        import sys
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from telegram_bots.xo.pulse_time import pulse_type_for_hour
        return pulse_type_for_hour(hour)
    except Exception:
        if 5 <= hour < 12:
            return "morning"
        if 12 <= hour < 20:
            return "midday"
        return "evening"


def _reminder_already_sent(client, window_date: str, pulse_window: str, action: str) -> bool:
    """Has this exact (day, pulse window, action) already been dispatched?

    Fails CLOSED (treated as "already sent" -> caller skips) on a missing
    client or any Supabase error — same fail-closed contract as
    intelligence/adhd/task_nudge_scheduler.py's NudgeRateLimiter.should_nudge
    ("don't nudge if we can't check"). A reminder skipped this check comes
    back next window; a Telegram message that already went out cannot be
    un-sent, so an uncertain check must never resolve to "send".
    """
    if client is None:
        log.warning("[recovery-dispatcher] no Supabase client for dedup check — failing closed (no send)")
        return True
    try:
        result = (
            client.table(_REMINDER_LOG_TABLE)
            .select("id")
            .eq("window_date", window_date)
            .eq("pulse_window", pulse_window)
            .eq("action", action)
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception as exc:
        log.error("[recovery-dispatcher] dedup check failed, failing closed (no send): %s", exc)
        return True


def _record_reminder_sent(
    client, window_date: str, pulse_window: str, action: str, confidence: int | None,
) -> None:
    """Persist the dedup marker immediately after a real send. Best-effort:
    if this write fails the message has already gone out and can't be
    un-sent — at worst the next check re-sends once more (visible via
    duplicate wellness-coaching heartbeat detail in the logs), which is the
    same "log and continue" contract every other best-effort write in this
    module already uses (see record_heartbeat() in _emit_and_return)."""
    if client is None:
        return
    try:
        client.table(_REMINDER_LOG_TABLE).insert({
            "window_date": window_date,
            "pulse_window": pulse_window,
            "action": action,
            "confidence_at_send": confidence,
        }).execute()
    except Exception as exc:
        log.warning("[recovery-dispatcher] failed to persist reminder dedup marker: %s", exc)


class _StandaloneTelegramBot:
    """Minimal synchronous `bot.send_message(chat_id, text, parse_mode)`
    adapter for callers with no live python-telegram-bot Application/event
    loop (e.g. intelligence/scheduler.py's BlockingScheduler daemon) — raw
    HTTP POST to the Bot API, same idiom as
    core/platform/notification_service.py::_send_telegram() and
    core/coordination/command_bus.py's private senders. Drop-in for the
    live-bot _BotAdapter that telegram-bots/xo/app.py's /dispatch command
    handler uses, satisfying the exact duck-typed contract _send() below
    expects."""

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")

    def send_message(self, chat_id, text, parse_mode="Markdown") -> None:
        import json
        import urllib.request

        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": parse_mode}).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass


# ── Dispatch logic ────────────────────────────────────────────────────────────

def run_dispatch_check(
    bot,
    chat_id: str | int,
    *,
    supabase_client: Any | None = None,
    force_summary: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Core dispatch logic. Call this from any bot's scheduled job or command handler.

    Args:
        bot:              python-telegram-bot Bot instance (or any object with
                          send_message(chat_id, text, parse_mode) method)
        chat_id:          Telegram chat/user ID to send messages to
        supabase_client:  Optional pre-built Supabase client; creates one if None
        force_summary:    Send full summary regardless of escalation level
        dry_run:          Evaluate the full decision, including the de-dup
                          check, but never actually call bot.send_message()
                          or persist the de-dup marker. Use this to verify
                          what a scheduled check WOULD do against live data
                          without risking a real Telegram send.

    Returns:
        dict with keys: confidence, level, action, message_sent, pulse_window,
        window_date, deduped, would_send, and (dry_run only) dry_run=True.
    """
    client = supabase_client or _get_supabase_client()
    status = get_recovery_status(client)
    level  = status.escalation_level
    now    = _brisbane_now()
    hour   = now.hour
    window_date  = now.date().isoformat()
    pulse_window = _current_pulse_window(hour)

    result = {
        "confidence": status.recovery_confidence,
        "level": level,
        "action": "none",
        "message_sent": False,
        "pulse_window": pulse_window,
        "window_date": window_date,
        "deduped": False,
        "would_send": False,
    }

    def _dispatch(action: str, msg: str) -> dict:
        result["action"] = action
        if _reminder_already_sent(client, window_date, pulse_window, action):
            result["deduped"] = True
            log.info(
                "[recovery-dispatcher] skip send: %s already dispatched for %s/%s",
                action, window_date, pulse_window,
            )
            return _emit_and_return(result)
        result["would_send"] = True
        if dry_run:
            result["dry_run"] = True
            log.info("[recovery-dispatcher] DRY RUN — would send %s to chat_id=%s", action, chat_id)
            return _emit_and_return(result)
        _send(bot, chat_id, msg)
        _record_reminder_sent(client, window_date, pulse_window, action, status.recovery_confidence)
        result["message_sent"] = True
        return _emit_and_return(result)

    # All 3 pulses done — send end-of-day summary once (at evening time)
    if status.pulses_completed == 3 or force_summary:
        return _dispatch("daily_summary", build_daily_summary(status))

    # L3: Critical — no pulses and it's afternoon+
    if level == 3:
        return _dispatch("escalation_l3", build_escalation_message(status, level=3))

    # L2: Low confidence (1 pulse logged, or no pulses before midday)
    if level == 2:
        return _dispatch("escalation_l2", build_escalation_message(status, level=2))

    # L1: Friendly reminder — only during appropriate hours
    next_pulse = status.next_suggested_pulse
    if next_pulse:
        # Only remind during relevant windows
        should_remind = (
            (next_pulse == "morning" and 7  <= hour < 12) or
            (next_pulse == "midday"  and 12 <= hour < 19) or
            (next_pulse == "evening" and 19 <= hour < 23)
        )
        if should_remind:
            return _dispatch(f"reminder_{next_pulse}", build_pulse_reminder(status, next_pulse))

    return _emit_and_return(result)


def _emit_and_return(result: dict) -> dict:
    """MSN-0305: thin, non-blocking Event Bus emission alongside the
    existing dispatch result — no domain-owned write to mirror here (this
    domain has no Supabase write of its own, only Telegram dispatch), so
    the dispatch decision itself is the emission point.

    Deliberately does NOT populate core_events.confidence from
    `result["confidence"]` (= status.recovery_confidence) — that value is
    a pulse-completion percentage, not the platform Confidence capability's
    "how trustworthy is this claim" concept, and conflating the two here
    would be the exact naming collision this same mission's Confidence
    review names as unresolved (see the Confidence Naming Decision).
    `recovery_pulse_completion` carries the raw value under its own name
    instead, in linked_entities, until that decision lands.
    """
    try:
        import sys
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from core.platform.event_bus import publish_event
        pulse_completion = result.get("confidence")
        publish_event(
            "wellness.escalation.dispatched",
            domain="wellness-coaching",
            source="engagement_dispatcher",
            importance=(100 - pulse_completion) if pulse_completion is not None else None,
            linked_entities=[f"recovery_pulse_completion:{pulse_completion}"] if pulse_completion is not None else [],
            recommended_action=result.get("action"),
        )
    except Exception:
        pass

    # Chief Engineer 2026-08-09 EOD alert verification: the domain_registry
    # comment (migration 0083) claimed this publish_event() call above
    # already fed domain_heartbeats via the Event Bus mirror — it doesn't;
    # event_bus.py only self-heartbeats its own "core_events" domain, never
    # the caller's domain string. record_heartbeat() had zero call sites for
    # "wellness-coaching" anywhere in the repo, so it always read
    # never_succeeded=true regardless of how many escalations fired here.
    try:
        import sys
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from core.platform.heartbeat import record_heartbeat
        record_heartbeat("wellness-coaching", status="ok", detail=f"action={result.get('action')}")
    except Exception:
        pass
    return result


def _send(bot: Any, chat_id: str | int, text: str) -> None:
    try:
        bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        log.info("[recovery-dispatcher] Sent message to chat_id=%s", chat_id)
    except Exception as exc:
        log.error("[recovery-dispatcher] send_message failed: %s", exc)


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    """Standalone check.

    Default (no flags): status preview only, never sends Telegram messages
    or touches the de-dup ledger — safe to run any time.

    --dispatch:          run the real run_dispatch_check() decision,
                          including the de-dup gate, against
                          TELEGRAM_CHAT_ID. Add --dry-run to see exactly
                          what it WOULD do without an actual Telegram send
                          or de-dup write.
    """
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="Recovery Officer engagement dispatcher")
    parser.add_argument("--dispatch", action="store_true", help="Run the real dispatch decision")
    parser.add_argument("--dry-run", action="store_true", help="With --dispatch: evaluate only, never send/record")
    args = parser.parse_args()

    if args.dispatch:
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not chat_id:
            print("TELEGRAM_CHAT_ID not set — cannot dispatch")
            sys.exit(1)
        bot = _StandaloneTelegramBot()
        result = run_dispatch_check(bot, chat_id, dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
    else:
        status = get_recovery_status()
        print(build_daily_summary(status))
        print(f"\nEscalation level: {status.escalation_level}")
        if status.next_suggested_pulse:
            print(f"\n--- L1 Reminder preview ---")
            print(build_pulse_reminder(status))
