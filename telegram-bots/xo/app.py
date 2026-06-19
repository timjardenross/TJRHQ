"""XO Bot — @Starship_endeavour_xO_bot

Executive Officer: mission governance, capacity awareness, recovery gating.
First live capability: Recovery Officer pulse reminders (MSN-0055).

Run:  python telegram-bots/xo/app.py
Env:  telegram-bots/xo/.env
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ── Load env ──────────────────────────────────────────────────────────────────

_BOT_DIR  = Path(__file__).parent
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
log = logging.getLogger("xo-bot")

# ── Recovery Officer dispatcher ───────────────────────────────────────────────

sys.path.insert(0, str(_REPO_ROOT))

from telegram_bots.recovery_officer.engagement_dispatcher import (
    get_recovery_status,
    build_daily_summary,
    build_pulse_reminder,
    run_dispatch_check,
)

# ── Telegram + APScheduler imports ───────────────────────────────────────────

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ── Supabase client (shared) ──────────────────────────────────────────────────

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


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"*XO — @Starship\\_endeavour\\_xO\\_bot*\n\n"
        f"Executive Officer online.\n\n"
        f"Your chat ID: `{chat_id}`\n\n"
        f"Use this in `TELEGRAM_CHAT_ID` in the bot `.env` file.\n\n"
        f"Available commands:\n"
        f"/recovery\\_status — today's recovery confidence\n"
        f"/recovery\\_pulse — log a recovery pulse\n"
        f"/dispatch — run a manual dispatch check\n"
        f"/help — this message",
        parse_mode="MarkdownV2",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*XO Bot — Available Commands*\n\n"
        "/recovery\\_status — today's recovery confidence and pulse status\n"
        "/recovery\\_pulse — log a recovery pulse \\(opens portal link\\)\n"
        "/dispatch — manual dispatch check \\(same as scheduled job\\)\n"
        "/help — this message\n\n"
        "_Mission approval commands coming in MSN\\-0056\\._",
        parse_mode="MarkdownV2",
    )


async def cmd_recovery_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = get_recovery_status(_get_supabase())
    text = build_daily_summary(status)
    await update.message.reply_text(_escape(text), parse_mode="MarkdownV2")


async def cmd_recovery_pulse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = get_recovery_status(_get_supabase())
    next_pulse = status.next_suggested_pulse
    if next_pulse:
        reminder = build_pulse_reminder(status, next_pulse)
        await update.message.reply_text(
            _escape(reminder) + "\n\n_Log via LCARS portal → Medical Bay → Recovery Pulse_",
            parse_mode="MarkdownV2",
        )
    else:
        await update.message.reply_text(
            "✅ All 4 pulses logged today\\. Recovery telemetry complete\\.",
            parse_mode="MarkdownV2",
        )


async def cmd_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manual trigger of the scheduled dispatch check."""
    await update.message.reply_text("Running dispatch check…")
    result = run_dispatch_check(
        _TelegramBotAdapter(context.bot),
        TELEGRAM_CHAT_ID,
        supabase_client=_get_supabase(),
        force_summary=False,
    )
    action = result.get("action", "none")
    sent   = result.get("message_sent", False)
    conf   = result.get("confidence", 0)
    await update.message.reply_text(
        f"Dispatch complete\\.\n"
        f"Confidence: {conf}%\n"
        f"Action: {_escape(action)}\n"
        f"Message sent: {'yes' if sent else 'no'}",
        parse_mode="MarkdownV2",
    )


# ── Telegram adapter shim ─────────────────────────────────────────────────────

class _TelegramBotAdapter:
    """Wraps python-telegram-bot Bot so run_dispatch_check can call send_message."""

    def __init__(self, bot):
        self._bot = bot

    def send_message(self, chat_id, text, parse_mode="Markdown"):
        import asyncio
        # run_dispatch_check is sync; schedule coroutine on running loop
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


# ── MarkdownV2 escaping ───────────────────────────────────────────────────────

_ESCAPE_CHARS = r"\_*[]()~`>#+=|{}.!-"

def _escape(text: str) -> str:
    """Escape special chars for Telegram MarkdownV2, preserving intentional bold/italic."""
    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        # Preserve *bold* and _italic_ markers
        if ch in ("*", "_") and (i == 0 or text[i-1] != "\\"):
            result.append(ch)
        elif ch in r"\`[]()~>#+=|{}.!-" and ch not in ("*", "_"):
            result.append("\\" + ch)
        else:
            result.append(ch)
        i += 1
    return "".join(result)


# ── Scheduled dispatch ────────────────────────────────────────────────────────

async def _scheduled_dispatch(bot) -> None:
    log.info("[scheduler] dispatch tick")
    adapter = _TelegramBotAdapter(bot)
    try:
        result = run_dispatch_check(
            adapter,
            TELEGRAM_CHAT_ID,
            supabase_client=_get_supabase(),
        )
        log.info("[scheduler] action=%s sent=%s conf=%s%%",
                 result.get("action"), result.get("message_sent"), result.get("confidence"))
    except Exception as exc:
        log.error("[scheduler] dispatch failed: %s", exc)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("XO Bot starting — token ...%s", TELEGRAM_BOT_TOKEN[-6:])

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",            cmd_start))
    app.add_handler(CommandHandler("help",             cmd_help))
    app.add_handler(CommandHandler("recovery_status",  cmd_recovery_status))
    app.add_handler(CommandHandler("recovery_pulse",   cmd_recovery_pulse))
    app.add_handler(CommandHandler("dispatch",         cmd_dispatch))

    # ── Scheduler (AEST = UTC+10, no DST for Brisbane) ────────────────────────
    scheduler = AsyncIOScheduler(timezone="Australia/Brisbane")

    bot = app.bot
    scheduler.add_job(lambda: _scheduled_dispatch(bot), CronTrigger(hour=7,  minute=0),  id="morning")
    scheduler.add_job(lambda: _scheduled_dispatch(bot), CronTrigger(hour=12, minute=30), id="midday")
    scheduler.add_job(lambda: _scheduled_dispatch(bot), CronTrigger(hour=16, minute=0),  id="eod")
    scheduler.add_job(lambda: _scheduled_dispatch(bot), CronTrigger(hour=20, minute=0),  id="evening")

    scheduler.start()
    log.info("Scheduler running — 4 daily dispatch windows (AEST)")

    log.info("XO Bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
