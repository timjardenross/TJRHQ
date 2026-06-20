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
from telegram_bots.wellness_officer.intelligence import get_wellness_snapshot
from telegram_bots.wellness_officer.brief import generate_wellness_brief_async

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
    if _supabase is None:
        if not SUPABASE_URL:
            log.warning("SUPABASE_URL not set — Supabase disabled")
        elif not SUPABASE_KEY:
            log.warning("SUPABASE_KEY not set — Supabase disabled")
        else:
            try:
                from supabase import create_client
                _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
                log.info("Supabase client initialised")
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

def _xo_system_prompt(status: RecoveryStatus, snap=None) -> str:
    signals = ", ".join(filter(None, [
        f"energy={status.latest_energy}"    if status.latest_energy    else None,
        f"mood={status.latest_mood}"        if status.latest_mood      else None,
        f"stress={status.latest_stress}"    if status.latest_stress    else None,
    ])) or "no signals yet today"

    wellness_ctx = ""
    if snap is not None:
        parts = []
        if snap.sleep_hours is not None:
            cpap = " (CPAP ✓)" if snap.cpap_compliant else (" (CPAP ✗)" if snap.cpap_compliant is False else "")
            parts.append(f"sleep={snap.sleep_hours}h{cpap}")
        if snap.nervous_system_state:
            parts.append(f"nervous_system={snap.nervous_system_state}")
        if snap.has_insights and snap.risk_flags:
            parts.append(f"risk_flags={'; '.join(snap.risk_flags[:2])}")
        if parts:
            wellness_ctx = f"\nWellness context: {', '.join(parts)}"

    return (
        "You are the Executive Officer (XO) of USS TJR, a personal command vessel.\n"
        "You serve Captain TJR (Tim Jardenross), who operates on ROS-001 v1.1 — "
        "currently in Stage 1 Stabilisation, moving toward Stage 2 Capacity Restoration.\n\n"
        "RECOVERY FIRST. Mission work is gated by the Captain's capacity. Never push beyond it.\n\n"
        f"Today's recovery state:\n"
        f"- Confidence: {status.recovery_confidence}% [{_bar(status.recovery_confidence)}]\n"
        f"- Pulses: {status.pulses_completed}/4 complete\n"
        f"- Signals: {signals}\n"
        f"- Escalation: L{status.escalation_level} (0=clear 1=low 2=concern 3=critical)"
        f"{wellness_ctx}\n\n"
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
        InlineKeyboardButton("⚡ High",     callback_data=f"pl|pt={pt}|e=high"),
        InlineKeyboardButton("〜 Moderate", callback_data=f"pl|pt={pt}|e=moderate"),
        InlineKeyboardButton("🔋 Low",      callback_data=f"pl|pt={pt}|e=low"),
    ]])

def _kb_mood(pt: str, e: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("😊 Positive", callback_data=f"pl|pt={pt}|e={e}|m=positive"),
        InlineKeyboardButton("😐 Stable",   callback_data=f"pl|pt={pt}|e={e}|m=stable"),
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
            res = db.table("recovery_pulses").upsert(
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
            log.info("Pulse written: %s energy=%s mood=%s stress=%s rows=%s",
                     pt, energy, mood, stress, len(res.data) if res.data else 0)
        except Exception as exc:
            log.error("pulse upsert failed: %s | energy=%s mood=%s stress=%s", exc, energy, mood, stress)
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
        "/log\\_activity — log activity \\(e\\.g\\. `/log_activity walk 30 light`\\)\n"
        "/log\\_weight — log weight \\(e\\.g\\. `/log_weight 82\\.5`\\)\n"
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


async def cmd_log_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick activity log: /log_activity walk 30 light"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "*Log Activity*\n\nUsage: `/log_activity <type> [minutes] [intensity]`\n\n"
            "Types: walk · swim · physio · stretch · strength · cycle · yoga · other\n"
            "Intensity: light · moderate · vigorous\n\n"
            "_Example: `/log_activity walk 30 light`_",
            parse_mode="MarkdownV2",
        )
        return

    valid_types = {"walk","swim","physio","stretch","strength","cycle","yoga","other"}
    activity_type = args[0].lower() if args[0].lower() in valid_types else "other"
    duration = None
    intensity = None
    for arg in args[1:]:
        if arg.isdigit():
            duration = int(arg)
        elif arg.lower() in ("light","moderate","vigorous"):
            intensity = arg.lower()

    db = _get_supabase()
    if not db:
        await update.message.reply_text("⚠️ Supabase unavailable — check SUPABASE\\_KEY in \\`\\.env\\`", parse_mode="MarkdownV2")
        return

    payload = {
        "log_date":      date.today().isoformat(),
        "activity_type": activity_type,
        "source":        "telegram",
        "completed":     True,
    }
    if duration:  payload["duration_minutes"] = duration
    if intensity: payload["intensity"]        = intensity

    try:
        db.table("activity_logs").insert(payload).execute()
        parts = [activity_type]
        if duration:  parts.append(f"{duration} min")
        if intensity: parts.append(intensity)
        await update.message.reply_text(
            f"✅ *Activity logged:* {_escape(' · '.join(parts))}",
            parse_mode="MarkdownV2",
        )
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Failed: {_escape(str(exc))}", parse_mode="MarkdownV2")


async def cmd_log_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick weight log: /log_weight 82.5"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "*Log Weight*\n\nUsage: `/log_weight <kg>`\n\n_Example: `/log_weight 82\\.5`_",
            parse_mode="MarkdownV2",
        )
        return

    try:
        kg = float(args[0])
        assert 30 < kg < 500
    except (ValueError, AssertionError):
        await update.message.reply_text("⚠️ Enter a valid weight in kg \\(e\\.g\\. `/log_weight 82\\.5`\\)", parse_mode="MarkdownV2")
        return

    db = _get_supabase()
    if not db:
        await update.message.reply_text("⚠️ Supabase unavailable — check SUPABASE\\_KEY in \\`\\.env\\`", parse_mode="MarkdownV2")
        return

    try:
        db.table("weight_logs").upsert(
            {"log_date": date.today().isoformat(), "weight_kg": kg, "source": "telegram"},
            on_conflict="log_date",
        ).execute()
        await update.message.reply_text(
            f"✅ *Weight logged:* {_escape(str(kg))} kg",
            parse_mode="MarkdownV2",
        )
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Failed: {_escape(str(exc))}", parse_mode="MarkdownV2")


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
    db     = _get_supabase()
    status = get_recovery_status(db)
    snap   = get_wellness_snapshot(db)
    await update.message.chat.send_action("typing")
    reply = await generate_async(text, _xo_system_prompt(status, snap))
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

async def _scheduled_morning_brief(bot) -> None:
    """07:00 — Wellness & Recovery Officer Daily Brief (insight-over-metrics)."""
    log.info("[scheduler] morning wellness brief")
    try:
        db   = _get_supabase()
        snap = get_wellness_snapshot(db)
        brief = await generate_wellness_brief_async(snap, generate_async)

        today = date.today().strftime("%a %d %b")
        msg = (
            f"🌅 *Daily Wellness Brief — {_escape(today)}*\n\n"
            f"{_escape(brief)}\n\n"
            f"Recovery: `{_escape(_bar(snap.recovery_confidence))}` {snap.recovery_confidence}% · "
            f"{snap.pulses_completed}/4 pulses"
        )
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode="MarkdownV2",
        )
        log.info("[scheduler] morning brief sent, conf=%s%%", snap.recovery_confidence)
    except Exception as exc:
        log.error("[scheduler] morning brief failed: %s", exc)
        # fall back to standard dispatch on error
        await _scheduled_dispatch(bot)


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
    app.add_handler(CommandHandler("log_activity",    cmd_log_activity))
    app.add_handler(CommandHandler("log_weight",      cmd_log_weight))
    app.add_handler(CommandHandler("dispatch",        cmd_dispatch))
    app.add_handler(CallbackQueryHandler(handle_pulse_callback, pattern=r"^pl\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_message))

    scheduler = AsyncIOScheduler(timezone="Australia/Brisbane")
    bot = app.bot
    scheduler.add_job(lambda: _scheduled_morning_brief(bot), CronTrigger(hour=7,  minute=0),  id="morning")
    scheduler.add_job(lambda: _scheduled_dispatch(bot),      CronTrigger(hour=12, minute=30), id="midday")
    scheduler.add_job(lambda: _scheduled_dispatch(bot),      CronTrigger(hour=16, minute=0),  id="eod")
    scheduler.add_job(lambda: _scheduled_dispatch(bot),      CronTrigger(hour=20, minute=0),  id="evening")
    scheduler.start()

    log.info("XO Bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
