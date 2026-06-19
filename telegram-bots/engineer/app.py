"""Chief Engineer Bot — @Starship_ChiefEngineer_bot

Technical authority. Conversational via Ollama Cloud with CE persona.
No recovery dispatch — that belongs to XO only.
Surfaces engineering decisions and blockers to the Captain.

Run:  python -m telegram_bots.engineer.app
Env:  telegram-bots/engineer/.env
"""

from __future__ import annotations

import logging
import os
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
        "/recovery\\_status — today's recovery confidence \\(read\\-only\\)\n\n"
        "_Or just talk to me about engineering matters\\._",
        parse_mode="MarkdownV2",
    )


async def cmd_recovery_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = get_recovery_status(_get_supabase())
    await update.message.reply_text(_escape(build_daily_summary(status)), parse_mode="MarkdownV2")


async def cmd_engineering_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _get_supabase()
    if not db:
        await update.message.reply_text("⚠️ Supabase unavailable\\.", parse_mode="MarkdownV2")
        return
    try:
        result = db.table("missions").select(
            "mission_id,title,status,priority"
        ).in_("status", ["ACTIVE", "IN_PROGRESS", "ASSIGNED", "BLOCKED"]).eq(
            "department", "engineering"
        ).order("priority").limit(10).execute()

        missions = result.data or []
        if not missions:
            await update.message.reply_text(
                "*Engineering Status*\n\nNo active engineering missions\\.", parse_mode="MarkdownV2"
            )
            return

        lines = ["*Engineering — Active Missions*\n"]
        for m in missions:
            icon = "🔴" if m.get("status") == "BLOCKED" else "🟢"
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("Chief Engineer Bot starting")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",              cmd_start))
    app.add_handler(CommandHandler("help",               cmd_help))
    app.add_handler(CommandHandler("recovery_status",    cmd_recovery_status))
    app.add_handler(CommandHandler("engineering_status", cmd_engineering_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_message))

    log.info("Chief Engineer Bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
