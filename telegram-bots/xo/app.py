"""XO Bot — @Starship_endeavour_xO_bot

Executive Officer: Captain's primary Telegram companion.
Recovery-gated mission governance. Conversational via Ollama Cloud.
Inline pulse logging (tap buttons — no portal required).
Recovery dispatch lives here only (CE and Eng-Dept do not run dispatch).

Run:  python -m telegram_bots.xo.app
Env:  telegram-bots/xo/.env
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

# ── Env ───────────────────────────────────────────────────────────────────────

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
log = logging.getLogger("xo-bot")

# ── Shared modules ────────────────────────────────────────────────────────────

sys.path.insert(0, str(_REPO_ROOT))

from telegram_bots.recovery_officer.engagement_dispatcher import (
    RecoveryStatus,
    build_daily_summary,
    get_recovery_status,
    run_dispatch_check,
)
from telegram_bots.llm import generate_async

# ── Telegram ──────────────────────────────────────────────────────────────────

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
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


# ── MarkdownV2 escaping ───────────────────────────────────────────────────────

def _escape(text: str) -> str:
    result = []
    for ch in text:
        if ch in r"\`[]()~>#+=|{}.!-" and ch not in ("*", "_"):
            result.append("\\" + ch)
        else:
            result.append(ch)
    return "".join(result)


def _bar(pct: int) -> str:
    return "█" * int(pct / 10) + "░" * (10 - int(pct / 10))


# ── XO system prompt ──────────────────────────────────────────────────────────

def _xo_system_prompt(status: RecoveryStatus) -> str:
    signals = ", ".join(filter(None, [
        f"energy={status.latest_energy}"    if status.latest_energy    else None,
        f"mood={status.latest_mood}"        if status.latest_mood      else None,
        f"stress={status.latest_stress}"    if status.latest_stress    else None,
    ])) or "no signals yet today"

    return (
        "You are the Executive Officer (XO) of USS TJR, a personal command vessel.\n"
        "You serve Captain TJR (Tim Jardenross), who operates on ROS-001 v1.1 — "
        "currently in Stage 1 Stabilisation, moving toward Stage 2 Capacity Restoration.\n\n"
        "RECOVERY FIRST. Mission work is gated by the Captain's capacity. Never push beyond it.\n\n"
        f"Today's recovery state:\n"
        f"- Confidence: {status.recovery_confidence}% [{_bar(status.recovery_confidence)}]\n"
        f"- Pulses: {status.pulses_completed}/4 complete\n"
        f"- Signals: {signals}\n"
        f"- Escalation: L{status.escalation_level} (0=clear 1=low 2=concern 3=critical)\n\n"
        "Your role:\n"
        "- Primary daily companion. The Captain talks to you first.\n"
        "- Help make decisions through a capacity lens — can we do this given recovery state?\n"
        "- Surface mission concerns and recommend deferrals when confidence is low.\n"
        "- Receive direction: 'defer that mission', 'what's my capacity today', 'anything blocking?'\n"
        "- Speak with authority and care. Concise, direct, no fluff.\n\n"
        "Keep responses SHORT. This is Telegram on mobile — 2-4 sentences max unless "
        "detail is genuinely needed. Respond as XO, not as an AI. No disclaimers."
    )


# ── Inline pulse flow ─────────────────────────────────────────────────────────
# Callback data format: pl|pt=<type>|e=<energy>|m=<mood>|s=<stress>
# Steps: energy → mood → stress → write to DB

_PULSE_LABELS = {
    "morning":    "🌅 Morning Readiness",
    "midday":     "🌤 Midday Status",
    "end_of_day": "🌇 End of Workday",
    "evening":    "🌃 Evening Recovery",
}

def _current_pulse_type() -> str:
    h = datetime.now().hour
    if 5  <= h < 12: return "morning"
    if 12 <= h < 16: return "midday"
    if 16 <= h < 20: return "end_of_day"
    return "evening"

def _parse_cb(data: str) -> dict:
    result = {}
    for part in data.split("|")[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            result[k] = v
    return result

def _kb_energy(pt: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⚡ High",   callback_data=f"pl|pt={pt}|e=high"),
        InlineKeyboardButton("〜 Medium", callback_data=f"pl|pt={pt}|e=medium"),
        InlineKeyboardButton("🔋 Low",    callback_data=f"pl|pt={pt}|e=low"),
    ]])

def _kb_mood(pt: str, e: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("😊 Positive", callback_data=f"pl|pt={pt}|e={e}|m=positive"),
        InlineKeyboardButton("😐 Neutral",  callback_data=f"pl|pt={pt}|e={e}|m=neutral"),
        InlineKeyboardButton("😔 Low",      callback_data=f"pl|pt={pt}|e={e}|m=low"),
    ]])

def _kb_stress(pt: str, e: str, m: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✨ Low",      callback_data=f"pl|pt={pt}|e={e}|m={m}|s=low"),
        InlineKeyboardButton("⚡ Moderate", callback_data=f"pl|pt={pt}|e={e}|m={m}|s=moderate"),
        InlineKeyboardButton("🔥 High",     callback_data=f"pl|pt={pt}|e={e}|m={m}|s=high"),
    ]])


async def _write_pulse(pt: str, energy: str, mood: str, stress: str) -> tuple[bool, RecoveryStatus]:
    db = _get_supabase()
    saved = False
    if db:
        try:
            db.table("recovery_pulses").upsert(
                {
                    "log_date":   date.today().isoformat(),
                    "pulse_type": pt,
                    "energy":     energy,
                    "mood":       mood,
                    "stress":     stress,
                    "source":     "telegram",
                },
                on_conflict="log_date,pulse_type",
            ).execute()
            saved = True
            log.info("Pulse written: %s energy=%s mood=%s stress=%s", pt, energy, mood, stress)
        except Exception as exc:
            log.error("pulse upsert failed: %s", exc)
    status = get_recovery_status(db)
    return saved, status


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"*XO online* — @Starship\\_endeavour\\_xO\\_bot\n\n"
        f"Chat ID: `{update.effective_chat.id}`\n\n"
        "/recovery\\_status · /recovery\\_pulse · /dispatch · /help\n\n"
        "_Or just talk to me\\._",
        parse_mode="MarkdownV2",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*XO — Commands*\n\n"
        "/recovery\\_status — today's confidence and pulse status\n"
        "/recovery\\_pulse — log a pulse inline \\(tap buttons, no portal\\)\n"
        "/dispatch — manual dispatch check\n\n"
        "_Or just talk to me — I understand plain English\\._",
        parse_mode="MarkdownV2",
    )


async def cmd_recovery_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = get_recovery_status(_get_supabase())
    await update.message.reply_text(_escape(build_daily_summary(status)), parse_mode="MarkdownV2")


async def cmd_recovery_pulse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = get_recovery_status(_get_supabase())
    pt = status.next_suggested_pulse or _current_pulse_type()
    label = _PULSE_LABELS.get(pt, pt)
    conf = status.recovery_confidence
    await update.message.reply_text(
        f"📡 *{_escape(label)}*\n\n"
        f"Confidence: `{_escape(_bar(conf))}` {conf}%\n\n"
        "How's your energy right now?",
        parse_mode="MarkdownV2",
        reply_markup=_kb_energy(pt),
    )


async def cmd_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Running dispatch check…")
    result = run_dispatch_check(
        _BotAdapter(context.bot),
        TELEGRAM_CHAT_ID,
        supabase_client=_get_supabase(),
    )
    conf   = result.get("confidence", 0)
    action = result.get("action", "none")
    sent   = result.get("message_sent", False)
    await update.message.reply_text(
        f"Dispatch: {_escape(action)} \\| conf={conf}% \\| sent={'yes' if sent else 'no'}",
        parse_mode="MarkdownV2",
    )


# ── Free-text conversation ────────────────────────────────────────────────────

async def cmd_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if not text:
        return
    status = get_recovery_status(_get_supabase())
    await update.message.chat.send_action("typing")
    reply = await generate_async(text, _xo_system_prompt(status))
    if reply:
        await update.message.reply_text(_escape(reply), parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(
            "XO here\\. LLM unreachable — use /recovery\\_status or /dispatch for now\\.",
            parse_mode="MarkdownV2",
        )


# ── Inline pulse callbacks ────────────────────────────────────────────────────

async def handle_pulse_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("pl|"):
        return

    f = _parse_cb(data)
    pt = f.get("pt", _current_pulse_type())
    e  = f.get("e")
    m  = f.get("m")
    s  = f.get("s")
    label = _PULSE_LABELS.get(pt, pt)

    if e and m and s:
        saved, status = await _write_pulse(pt, e, m, s)
        icon = "✅" if saved else "⚠️"
        conf = status.recovery_confidence
        done = " ".join([
            "✅" if status.morning_done    else "❌",
            "✅" if status.midday_done     else "❌",
            "✅" if status.end_of_day_done else "❌",
            "✅" if status.evening_done    else "❌",
        ])
        e_cap = _escape(e.capitalize())
        m_cap = _escape(m.capitalize())
        s_cap = _escape(s.capitalize())
        await query.edit_message_text(
            f"{icon} *{_escape(label)} logged*\n\n"
            f"Energy: {e_cap} · Mood: {m_cap} · Stress: {s_cap}\n\n"
            f"Confidence: `{_escape(_bar(conf))}` {conf}%\n"
            f"Pulses: {_escape(done)}  AM · Mid · EOD · PM",
            parse_mode="MarkdownV2",
        )
        return

    if e and m:
        await query.edit_message_text(
            f"📡 *{_escape(label)}*\n\n"
            f"Energy: {_escape(e.capitalize())} · Mood: {_escape(m.capitalize())}\n\n"
            "Stress level?",
            parse_mode="MarkdownV2",
            reply_markup=_kb_stress(pt, e, m),
        )
        return

    if e:
        await query.edit_message_text(
            f"📡 *{_escape(label)}*\n\n"
            f"Energy: {_escape(e.capitalize())}\n\n"
            "How's your mood?",
            parse_mode="MarkdownV2",
            reply_markup=_kb_mood(pt, e),
        )
        return


# ── Telegram adapter ──────────────────────────────────────────────────────────

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


# ── Scheduled dispatch (XO only) ──────────────────────────────────────────────

async def _scheduled_dispatch(bot) -> None:
    log.info("[scheduler] xo dispatch tick")
    try:
        result = run_dispatch_check(_BotAdapter(bot), TELEGRAM_CHAT_ID, supabase_client=_get_supabase())
        log.info("[scheduler] action=%s sent=%s conf=%s%%",
                 result.get("action"), result.get("message_sent"), result.get("confidence"))
    except Exception as exc:
        log.error("[scheduler] dispatch failed: %s", exc)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("XO Bot starting")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",           cmd_start))
    app.add_handler(CommandHandler("help",            cmd_help))
    app.add_handler(CommandHandler("recovery_status", cmd_recovery_status))
    app.add_handler(CommandHandler("recovery_pulse",  cmd_recovery_pulse))
    app.add_handler(CommandHandler("dispatch",        cmd_dispatch))
    app.add_handler(CallbackQueryHandler(handle_pulse_callback, pattern=r"^pl\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_message))

    scheduler = AsyncIOScheduler(timezone="Australia/Brisbane")
    bot = app.bot
    scheduler.add_job(lambda: _scheduled_dispatch(bot), CronTrigger(hour=7,  minute=0),  id="morning")
    scheduler.add_job(lambda: _scheduled_dispatch(bot), CronTrigger(hour=12, minute=30), id="midday")
    scheduler.add_job(lambda: _scheduled_dispatch(bot), CronTrigger(hour=16, minute=0),  id="eod")
    scheduler.add_job(lambda: _scheduled_dispatch(bot), CronTrigger(hour=20, minute=0),  id="evening")
    scheduler.start()

    log.info("XO Bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
