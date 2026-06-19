"""Engineering Dept Bot — @starship_endeavour_bot

Primary crew communications: operations status, mission updates, recovery reminders.
Phase 1 capability: recovery pulse dispatch + operations status commands.

Run:  python -m telegram_bots.engineering-dept.app
Env:  telegram-bots/engineering-dept/.env
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ── Load env ──────────────────────────────────────────────────────────────────

_BOT_DIR   = Path(__file__).parent
_REPO_ROOT = _BOT_DIR.parents[1]

load_dotenv(_BOT_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = int(os.environ["TELEGRAM_CHAT_ID"])
SUPABASE_URL       = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY       = os.environ.get("SUPABASE_KEY", "")

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("engineering-dept-bot")

# ── Shared modules ────────────────────────────────────────────────────────────

sys.path.insert(0, str(_REPO_ROOT))

from telegram_bots.recovery_officer.engagement_dispatcher import (
    get_recovery_status,
    build_daily_summary,
    build_pulse_reminder,
    run_dispatch_check,
)

# ── Telegram + scheduler ──────────────────────────────────────────────────────

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ── Supabase ──────────────────────────────────────────────────────────────────

_supabase = None

def _get_supabase():
    global _supabase
    if _supabase is None and SUPABASE_URL and SUPABASE_KEY:
        try:
            from supabase import create_client
            _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as exc:
            log.warning("Supabase client failed: %s", exc)
    return _supabase


def _escape(text: str) -> str:
    result = []
    for ch in text:
        if ch in r"\`[]()~>#+=|{}.!-" and ch not in ("*", "_"):
            result.append("\\" + ch)
        else:
            result.append(ch)
    return "".join(result)


class _BotAdapter:
    def __init__(self, bot):
        self._bot = bot

    def send_message(self, chat_id, text, parse_mode="Markdown"):
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(
                self._bot.send_message(
                    chat_id=chat_id,
                    text=_escape(text),
                    parse_mode="MarkdownV2",
                )
            )
        except Exception as exc:
            log.error("send_message failed: %s", exc)


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"*Engineering Dept — @starship\\_endeavour\\_bot*\n\n"
        f"Primary crew channel online\\.\n\n"
        f"Your chat ID: `{chat_id}`\n\n"
        f"Available commands:\n"
        f"/recovery\\_status — today's recovery confidence\n"
        f"/recovery\\_pulse — log a recovery pulse\n"
        f"/operations\\_status — active missions across all departments\n"
        f"/dispatch — manual dispatch check\n"
        f"/help — this message",
        parse_mode="MarkdownV2",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*Engineering Dept Bot — Commands*\n\n"
        "*Recovery*\n"
        "/recovery\\_status — today's confidence and pulse status\n"
        "/recovery\\_pulse — log a recovery pulse\n"
        "/dispatch — manual dispatch check\n\n"
        "*Operations*\n"
        "/operations\\_status — active missions all departments\n",
        parse_mode="MarkdownV2",
    )


async def cmd_recovery_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = get_recovery_status(_get_supabase())
    await update.message.reply_text(_escape(build_daily_summary(status)), parse_mode="MarkdownV2")


async def cmd_recovery_pulse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = get_recovery_status(_get_supabase())
    next_pulse = status.next_suggested_pulse
    if next_pulse:
        text = build_pulse_reminder(status, next_pulse)
        await update.message.reply_text(
            _escape(text) + "\n\n_Log via LCARS portal → Medical Bay → Recovery Pulse_",
            parse_mode="MarkdownV2",
        )
    else:
        await update.message.reply_text(
            "✅ All 4 pulses logged today\\. Recovery telemetry complete\\.",
            parse_mode="MarkdownV2",
        )


async def cmd_operations_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _get_supabase()
    if not db:
        await update.message.reply_text("⚠️ Supabase unavailable\\.", parse_mode="MarkdownV2")
        return
    try:
        result = db.table("missions").select(
            "mission_id,title,status,department"
        ).in_("status", ["ACTIVE", "IN_PROGRESS", "ASSIGNED", "BLOCKED"]).order(
            "department"
        ).limit(15).execute()

        missions = result.data or []
        if not missions:
            await update.message.reply_text("*Operations Status*\n\nNo active missions\\.", parse_mode="MarkdownV2")
            return

        lines = ["*Operations Status — All Active Missions*\n"]
        for m in missions:
            icon = "🔴" if m.get("status") == "BLOCKED" else "🟢"
            dept = _escape(m.get("department") or "?")
            mid  = _escape(m.get("mission_id") or "?")
            title = _escape(m.get("title") or "?")
            lines.append(f"{icon} `{mid}` \\[{dept}\\] {title}")

        await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")
    except Exception as exc:
        log.error("operations_status query failed: %s", exc)
        await update.message.reply_text("⚠️ Failed to fetch operations status\\.", parse_mode="MarkdownV2")


async def cmd_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Running dispatch check…")
    result = run_dispatch_check(
        _BotAdapter(context.bot),
        TELEGRAM_CHAT_ID,
        supabase_client=_get_supabase(),
    )
    conf  = result.get("confidence", 0)
    action = result.get("action", "none")
    sent  = result.get("message_sent", False)
    await update.message.reply_text(
        f"Dispatch complete\\.\nConfidence: {conf}%\nAction: {_escape(action)}\nSent: {'yes' if sent else 'no'}",
        parse_mode="MarkdownV2",
    )


async def _scheduled_dispatch(bot) -> None:
    log.info("[scheduler] engineering-dept dispatch tick")
    try:
        run_dispatch_check(_BotAdapter(bot), TELEGRAM_CHAT_ID, supabase_client=_get_supabase())
    except Exception as exc:
        log.error("[scheduler] dispatch failed: %s", exc)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("Engineering Dept Bot starting — token ...%s", TELEGRAM_BOT_TOKEN[-6:])

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",              cmd_start))
    app.add_handler(CommandHandler("help",               cmd_help))
    app.add_handler(CommandHandler("recovery_status",    cmd_recovery_status))
    app.add_handler(CommandHandler("recovery_pulse",     cmd_recovery_pulse))
    app.add_handler(CommandHandler("operations_status",  cmd_operations_status))
    app.add_handler(CommandHandler("dispatch",           cmd_dispatch))

    scheduler = AsyncIOScheduler(timezone="Australia/Brisbane")
    bot = app.bot
    scheduler.add_job(lambda: _scheduled_dispatch(bot), CronTrigger(hour=7,  minute=0),  id="morning")
    scheduler.add_job(lambda: _scheduled_dispatch(bot), CronTrigger(hour=12, minute=30), id="midday")
    scheduler.add_job(lambda: _scheduled_dispatch(bot), CronTrigger(hour=16, minute=0),  id="eod")
    scheduler.add_job(lambda: _scheduled_dispatch(bot), CronTrigger(hour=20, minute=0),  id="evening")
    scheduler.start()

    log.info("Engineering Dept Bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
