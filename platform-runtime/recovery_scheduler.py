"""D-055 — Proactive recovery dispatch for Slack.

Fires at 3 windows per day (matching Telegram). Sends DMs only for L2/L3
escalations — Telegram handles L0/L1 friendly reminders.

Env vars:
    CAPTAIN_SLACK_USER_ID — Slack user ID to DM (U0123ABCDE)

# LOCAL SCHEDULER: tightly coupled to Slack bot process — cannot migrate to
# canonical scheduler (intelligence/scheduler.py). start_recovery_scheduler()
# receives a live Slack WebClient; _dispatch_check() delivers via
# slack_client.chat_postMessage(). Additionally, this scheduler is RETIRED
# (D-3C-04, 2026-06-27) — recovery gap notifications are owned by the
# Command Centre notification engine. The BackgroundScheduler is still
# started by platform-runtime/app.py for backward compatibility but the
# jobs log RETIRED and are otherwise inert.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger(__name__)


def _escalation_level(confidence: int, pulses: int) -> int:
    """MSN-0305: delegates to the canonical implementation in
    wellness_officer/intelligence.py — was one of 3 independent copies of
    this logic (MSN-0302 finding), and the only one using naive local
    system time instead of Australia/Brisbane, a real silent-drift risk
    (this VM's system time is CEST, not AEST — "afternoon" resolved
    differently here than in the other 2 copies)."""
    import sys
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from telegram_bots.wellness_officer.intelligence import escalation_level as _canonical
    return _canonical(confidence, pulses)


def _dispatch_check(slack_client: Any) -> None:
    """Check recovery state and DM Captain at L2/L3 only."""
    user_id = os.environ.get("CAPTAIN_SLACK_USER_ID", "")
    if not user_id:
        log.warning("[recovery-scheduler] CAPTAIN_SLACK_USER_ID not set — skipping")
        return

    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools.supabase.client import CommanderSupabaseClient
        db = CommanderSupabaseClient()
        if not db.is_enabled():
            return
    except Exception as exc:
        log.warning("[recovery-scheduler] Supabase unavailable: %s", exc)
        return

    try:
        result = db.raw_client.table("recovery_confidence_today").select("*").execute()
        if not result.data:
            return
        row    = result.data[0]
        conf   = row.get("recovery_confidence", 0)
        pulses = row.get("pulses_completed", 0)
        level  = _escalation_level(conf, pulses)
    except Exception as exc:
        log.error("[recovery-scheduler] status fetch failed: %s", exc)
        return

    if level < 2:
        log.info("[recovery-scheduler] L%d — no Slack alert (Telegram handles this)", level)
        return

    try:
        from zoneinfo import ZoneInfo as _ZI
        today = datetime.now(_ZI("Australia/Brisbane")).strftime("%Y-%m-%d")
    except Exception:
        today = datetime.now().strftime("%Y-%m-%d")
    bar_filled = int(conf / 10)
    bar        = "█" * bar_filled + "░" * (10 - bar_filled)

    if level == 3:
        msg = (
            f":red_circle: *Recovery Officer — Critical Alert*\n\n"
            f"No recovery pulses logged today ({today}).\n"
            f"Confidence: `{bar}` 0%\n\n"
            f"Log at least one pulse to restore telemetry baseline.\n"
            f"</recovery-pulse|Log pulse now>"
        )
    else:
        missing = row.get("pulses_missing", 0)
        msg = (
            f":large_orange_circle: *Recovery Officer — Confidence Low*\n\n"
            f"Recovery confidence: `{bar}` {conf}%  ·  {pulses}/3 pulses\n"
            f"{missing} pulse{'s' if missing != 1 else ''} remaining today.\n\n"
            f"</recovery-pulse|Log a pulse>"
        )

    try:
        slack_client.chat_postMessage(channel=user_id, text=msg)
        log.info("[recovery-scheduler] L%d alert sent", level)
    except Exception as exc:
        log.error("[recovery-scheduler] DM failed: %s", exc)


def start_recovery_scheduler(slack_client: Any) -> BackgroundScheduler:
    """RETIRED — D-3C-04. Returns an inert scheduler. See notification-engine.js."""
    log.info("[recovery-scheduler] RETIRED (D-3C-04) — recovery gap notifications owned by Command Centre")
    scheduler = BackgroundScheduler(timezone="Australia/Brisbane")
    scheduler.add_job(lambda: _dispatch_check(slack_client), CronTrigger(hour=7,  minute=0),  id="rec_morning")
    scheduler.add_job(lambda: _dispatch_check(slack_client), CronTrigger(hour=12, minute=30), id="rec_midday")
    scheduler.add_job(lambda: _dispatch_check(slack_client), CronTrigger(hour=20, minute=0),  id="rec_evening")
    scheduler.start()
    log.info("[recovery-scheduler] Running — L2/L3 dispatch at 07:00, 12:30, 20:00 AEST")
    return scheduler
