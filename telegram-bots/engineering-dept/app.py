"""Engineering Dept Bot — @starship_endeavour_bot

Descoped noticeboard. Read-only status queries only.
No recovery dispatch (XO only). No pulse logging. No conversational layer.
Use XO for recovery and conversation; use this for quick ops status lookups.

Run:  python -m telegram_bots.engineering-dept.app
Env:  telegram-bots/engineering-dept/.env
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
log = logging.getLogger("engineering-dept-bot")

# ── Shared modules ────────────────────────────────────────────────────────────

sys.path.insert(0, str(_REPO_ROOT))

from telegram_bots.recovery_officer.engagement_dispatcher import (
    build_daily_summary,
    get_recovery_status,
)

# ── Telegram ──────────────────────────────────────────────────────────────────

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ── Supabase ──────────────────────────────────────────────────────────────────

_supabase      = None
_supabase_err  = None

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


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"*Engineering Dept — @starship\\_endeavour\\_bot*\n\n"
        f"Chat ID: `{update.effective_chat.id}`\n\n"
        "/operations\\_status · /recovery\\_status · /help\n\n"
        "_Read\\-only noticeboard\\. Use XO for recovery and conversation\\._",
        parse_mode="MarkdownV2",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*Engineering Dept — Commands*\n\n"
        "/operations\\_status — all active missions\n"
        "/recovery\\_status — today's recovery confidence \\(read\\-only\\)\n\n"
        "_For recovery logging and conversation, use XO\\._",
        parse_mode="MarkdownV2",
    )


async def cmd_recovery_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = get_recovery_status(_get_supabase())
    await update.message.reply_text(_escape(build_daily_summary(status)), parse_mode="MarkdownV2")


async def cmd_operations_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _get_supabase()
    if not db:
        reason = _escape(_supabase_err or "unknown error")
        await update.message.reply_text(f"⚠️ Supabase unavailable — `{reason}`\\.", parse_mode="MarkdownV2")
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

        lines = ["*Operations — All Active Missions*\n"]
        for m in missions:
            icon  = "🔴" if m.get("status") == "BLOCKED" else "🟢"
            dept  = _escape(m.get("department") or "?")
            mid   = _escape(m.get("mission_id") or "?")
            title = _escape(m.get("title") or "?")
            lines.append(f"{icon} `{mid}` \\[{dept}\\] {title}")

        await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")
    except Exception as exc:
        log.error("operations_status query failed: %s", exc)
        await update.message.reply_text("⚠️ Failed to fetch operations status\\.", parse_mode="MarkdownV2")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("Engineering Dept Bot starting")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",             cmd_start))
    app.add_handler(CommandHandler("help",              cmd_help))
    app.add_handler(CommandHandler("recovery_status",   cmd_recovery_status))
    app.add_handler(CommandHandler("operations_status", cmd_operations_status))

    log.info("Engineering Dept Bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
