"""Chief Engineer Bot — @Starship_ChiefEngineer_bot

Technical authority. Conversational via Ollama Cloud with CE persona.
No recovery dispatch — that belongs to XO only.
Surfaces engineering decisions and blockers to the Captain.

Run:  python -m telegram_bots.engineer.app
Env:  telegram-bots/engineer/.env
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
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
log = logging.getLogger("engineer-bot")

# ── Shared modules ────────────────────────────────────────────────────────────

sys.path.insert(0, str(_REPO_ROOT))

from telegram_bots.recovery_officer.engagement_dispatcher import (
    build_daily_summary,
    get_recovery_status,
)
from telegram_bots.llm import generate_async

# ── Telegram ──────────────────────────────────────────────────────────────────

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ── Supabase ──────────────────────────────────────────────────────────────────

_supabase      = None
_supabase_err  = None  # last init error, shown in Telegram responses

def _get_supabase():
    global _supabase, _supabase_err
    if _supabase is None:
        if not SUPABASE_URL:
            _supabase_err = "SUPABASE_URL not set"
            log.warning("[supabase] %s", _supabase_err)
        elif not SUPABASE_KEY:
            _supabase_err = "SUPABASE_KEY not set"
            log.warning("[supabase] %s", _supabase_err)
        else:
            try:
                from supabase import create_client
                _supabase     = create_client(SUPABASE_URL, SUPABASE_KEY)
                _supabase_err = None
                log.info("[supabase] client initialised")
            except Exception as exc:
                _supabase_err = str(exc)
                log.warning("[supabase] client failed: %s", exc)
    return _supabase


def _escape(text: str) -> str:
    result = []
    for ch in text:
        if ch in r"\`[]()~>#+=|{}.!-" and ch not in ("*", "_"):
            result.append("\\" + ch)
        else:
            result.append(ch)
    return "".join(result)


# ── CE system prompt ──────────────────────────────────────────────────────────

_CE_SYSTEM_PROMPT = (
    "You are the Chief Engineer of USS TJR. You report directly to Captain TJR.\n\n"
    "Your domain:\n"
    "- All technical and engineering decisions\n"
    "- Build status, repository health, deployment blockers\n"
    "- Engineering mission progress and technical debt\n"
    "- Code architecture, infrastructure, integrations\n\n"
    "Your role:\n"
    "- Surface engineering concerns and blockers clearly and concisely\n"
    "- Answer technical questions with precision\n"
    "- Flag when a technical decision needs the Captain's attention\n"
    "- Recovery is not your domain — defer those questions to XO\n\n"
    "Keep responses SHORT and technical. This is Telegram on mobile.\n"
    "Respond as Chief Engineer, not as an AI. No disclaimers."
)


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"*Chief Engineer online* — @Starship\\_ChiefEngineer\\_bot\n\n"
        f"Chat ID: `{update.effective_chat.id}`\n\n"
        "/engineering\\_status · /recovery\\_status · /help\n\n"
        "_Or ask me a technical question\\._",
        parse_mode="MarkdownV2",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*Chief Engineer — Commands*\n\n"
        "/engineering\\_status — active engineering missions\n"
        "/recovery\\_status — Captain's recovery confidence \\(read\\-only\\)\n"
        "/db\\_status — Supabase connectivity test\n"
        "/restart \\[slack\\|eng\\-dept\\|engineer\\|all\\] — restart engineering services\n\n"
        "_Or just talk to me about engineering matters\\._",
        parse_mode="MarkdownV2",
    )


async def cmd_recovery_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = get_recovery_status(_get_supabase())
    await update.message.reply_text(_escape(build_daily_summary(status)), parse_mode="MarkdownV2")


async def cmd_db_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _get_supabase()
    if not db:
        reason = _escape(_supabase_err or "unknown error")
        await update.message.reply_text(
            f"⚠️ *Supabase: not connected*\n\n`{reason}`",
            parse_mode="MarkdownV2",
        )
        return
    try:
        res  = db.table("recovery_confidence_today").select("recovery_confidence,pulses_completed").execute()
        row  = res.data[0] if res.data else {}
        conf = row.get("recovery_confidence", 0)
        pulses = row.get("pulses_completed", 0)
        await update.message.reply_text(
            f"✅ *Supabase: connected*\n\nrecovery\\_confidence\\_today: {conf}% · {pulses}/4 pulses",
            parse_mode="MarkdownV2",
        )
    except Exception as exc:
        await update.message.reply_text(
            f"⚠️ *Supabase: connected but query failed*\n\n`{_escape(str(exc))}`",
            parse_mode="MarkdownV2",
        )


async def cmd_engineering_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _get_supabase()
    if not db:
        reason = _escape(_supabase_err or "unknown error")
        await update.message.reply_text(
            f"⚠️ Supabase unavailable — `{reason}`", parse_mode="MarkdownV2"
        )
        return
    try:
        result = db.table("missions").select(
            "mission_id,title,status,priority"
        ).not_.in_("status", ["Closed", "Archived"]).order("priority").limit(10).execute()

        missions = result.data or []
        if not missions:
            await update.message.reply_text(
                "*Engineering Status*\n\nNo active engineering missions\\.", parse_mode="MarkdownV2"
            )
            return

        lines = ["*Engineering — Active Missions*\n"]
        for m in missions:
            icon = "🔴" if m.get("status") == "Blocked" else "🟢"
            lines.append(f"{icon} `{_escape(m.get('mission_id','?'))}` — {_escape(m.get('title','?'))}")
        await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")
    except Exception as exc:
        log.error("engineering_status query failed: %s", exc)
        await update.message.reply_text("⚠️ Failed to fetch engineering missions\\.", parse_mode="MarkdownV2")


# ── Free-text conversation ────────────────────────────────────────────────────

async def cmd_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if not text:
        return
    await update.message.chat.send_action("typing")
    reply = await generate_async(text, _CE_SYSTEM_PROMPT)
    if reply:
        await update.message.reply_text(_escape(reply), parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(
            "CE here\\. LLM unreachable — use /engineering\\_status for current state\\.",
            parse_mode="MarkdownV2",
        )


# ── Restart ──────────────────────────────────────────────────────────────────

_RESTARTABLE = {
    "slack":    ["starfleet-slack-bot.service"],
    "eng-dept": ["tg-engineering-dept.service"],
    "engineer": [],  # self-restart only, handled separately
    "all":      ["starfleet-slack-bot.service", "tg-engineering-dept.service"],
}


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/restart [slack|eng-dept|all] — restart engineering services. Gates on Captain's chat."""
    if update.effective_chat.id != TELEGRAM_CHAT_ID:
        await update.message.reply_text("🚫 Restricted to the Captain's chat.")
        return

    arg = (context.args[0].lower() if context.args else "all")
    services = _RESTARTABLE.get(arg, _RESTARTABLE["all"])
    names = _escape(", ".join(s.replace(".service", "") for s in services))

    await update.message.reply_text(
        f"🔄 Restarting: {names}\\.\\.\\.",
        parse_mode="MarkdownV2",
    )

    lines = []
    for svc in services:
        try:
            r = subprocess.run(["systemctl", "restart", svc], capture_output=True, text=True, timeout=15)
            icon = "✅" if r.returncode == 0 else f"⚠️ rc={r.returncode}"
            lines.append(f"{icon} {svc.replace('.service', '')}")
        except Exception as exc:
            lines.append(f"❌ {svc.replace('.service', '')}: {_escape(str(exc))}")

    restart_self = arg in ("engineer", "all")
    suffix = "\n\n_CE rebooting in 3s\\.\\.\\._" if restart_self else ""

    await update.message.reply_text(
        f"*Restart results*\n\n{_escape(chr(10).join(lines))}{suffix}",
        parse_mode="MarkdownV2",
    )

    if restart_self:
        await asyncio.sleep(3)
        subprocess.Popen(["systemctl", "restart", "tg-engineer.service"])


# ── Main ──────────────────────────────────────────────────────────────────────

_BOT_COMMANDS = [
    ("engineering_status", "Active engineering missions"),
    ("recovery_status",    "Captain's recovery confidence (read-only)"),
    ("restart",            "Restart engineering services  e.g. /restart all"),
    ("db_status",          "Supabase connectivity test"),
    ("help",               "Command reference"),
]


async def _post_init(app) -> None:
    from telegram import BotCommand
    await app.bot.set_my_commands([BotCommand(cmd, desc) for cmd, desc in _BOT_COMMANDS])
    log.info("[startup] Telegram command menu registered (%d commands)", len(_BOT_COMMANDS))


def main() -> None:
    log.info("Chief Engineer Bot starting")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start",              cmd_start))
    app.add_handler(CommandHandler("help",               cmd_help))
    app.add_handler(CommandHandler("recovery_status",    cmd_recovery_status))
    app.add_handler(CommandHandler("engineering_status", cmd_engineering_status))
    app.add_handler(CommandHandler("db_status",          cmd_db_status))
    app.add_handler(CommandHandler("restart",            cmd_restart))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_message))

    log.info("Chief Engineer Bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
