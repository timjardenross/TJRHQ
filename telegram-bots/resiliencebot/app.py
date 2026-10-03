#!/usr/bin/env python3
"""Resilience Crosswalk Bot — the Operational Resilience Advisor (USS-TJR-OR-001) on Telegram.

A thin front-end over ``platform-runtime/lib/resilience`` (the grounded crosswalk
pipeline): intake via inline buttons, the crosswalk itself delivered as a Markdown
document, and accept / edit / reject review buttons that write to the pipeline's
audit log. No host or shell actions, so XO stays the only action-capable bot.

Commands:
    /crosswalk <request>   start a crosswalk (or send the request as the next message)
    /coverage              what the corpus actually holds, per framework
    /pending               crosswalks still awaiting your review
    /help

Run:  python -m telegram_bots.resiliencebot.app
Env:  telegram-bots/resiliencebot/.env (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
      plus the platform's LLM_PROVIDER / MODEL_ROUTER_URL settings)
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_BOT_DIR = Path(__file__).parent
_REPO_ROOT = _BOT_DIR.parents[1]

load_dotenv(_BOT_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("resiliencebot")
# httpx logs full request URLs at INFO, which include the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)

for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "platform-runtime")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.resilience import audit
from lib.resilience.corpus import load_corpus
from lib.resilience.pipeline import Intake, run_crosswalk
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

from core.platform.telegram_access import is_allowed as _chat_is_allowed
from telegram_bots.resiliencebot import conversation as cv

_SESSION_KEY = "crosswalk_session"
_AWAITING_KEY = "awaiting_request"


def _markup(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=data) for label, data in row]
                                 for row in rows])


async def _global_auth_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or not _chat_is_allowed(chat.id, TELEGRAM_CHAT_ID):
        raise ApplicationHandlerStop


# ── Commands ──────────────────────────────────────────────────────────────────

HELP_TEXT = (
    "RESILIENCE CROSSWALK — Operational Resilience Advisor\n\n"
    "/crosswalk <request> — map a requirement across frameworks\n"
    "   e.g. /crosswalk CPS 230 business continuity testing\n"
    "/coverage — what the corpus holds per framework\n"
    "/pending — crosswalks awaiting your review\n\n"
    "Every output is a draft for your review. No customer data, no confidential "
    "material, no regulator responses or legal advice."
)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def _start_session(update: Update, context: ContextTypes.DEFAULT_TYPE, request: str) -> None:
    frameworks = sorted(load_corpus().frameworks)
    session = cv.new_session(request, frameworks)
    context.chat_data[_SESSION_KEY] = session
    context.chat_data.pop(_AWAITING_KEY, None)
    await update.message.reply_text(cv.intake_text(session), reply_markup=_markup(cv.intake_keyboard(session)))


async def cmd_crosswalk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    request = " ".join(context.args or []).strip()
    if not request:
        context.chat_data[_AWAITING_KEY] = True
        await update.message.reply_text("What requirement should I crosswalk? Send it as your next message.")
        return
    await _start_session(update, context, request)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.chat_data.get(_AWAITING_KEY):
        await _start_session(update, context, update.message.text or "")
    else:
        await update.message.reply_text("Use /crosswalk <request> to start. /help for more.")


async def cmd_coverage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(cv.coverage_text(load_corpus().coverage()))


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending = audit.unreviewed_runs()
    if not pending:
        await update.message.reply_text("No crosswalks awaiting review.")
        return
    await update.message.reply_text("Awaiting review:")
    for run_id in pending[-5:]:
        await update.message.reply_text(run_id, reply_markup=_markup(cv.review_keyboard(run_id)))


# ── Callbacks ─────────────────────────────────────────────────────────────────

async def handle_intake_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    cb = cv.parse_callback(query.data)
    session: cv.Session | None = context.chat_data.get(_SESSION_KEY)
    if session is None:
        await query.edit_message_text("That crosswalk request has expired. Start again with /crosswalk.")
        return

    if cb.kind == "cancel":
        context.chat_data.pop(_SESSION_KEY, None)
        await query.edit_message_text("Crosswalk cancelled.")
        return
    if cb.kind in {"toggle", "source", "use"}:
        if cb.kind == "toggle":
            session.toggle(cb.index)
        elif cb.kind == "source":
            session.cycle_source()
        else:
            session.cycle_use()
        await query.edit_message_text(cv.intake_text(session), reply_markup=_markup(cv.intake_keyboard(session)))
        return
    if cb.kind != "run":
        return

    context.chat_data.pop(_SESSION_KEY, None)
    await query.edit_message_text(cv.intake_text(session) + "\n\n⏳ Running crosswalk…")
    intake = Intake(source_framework=session.source, targets=sorted(session.targets) or None,
                    intended_use=session.use)
    try:
        run = await asyncio.to_thread(run_crosswalk, session.request, intake)
    except Exception as exc:
        # Pipeline / corpus / LLM failure surface is broad: report and log, never crash the bot.
        log.exception("crosswalk run failed")
        await query.message.reply_text(f"Crosswalk failed: {type(exc).__name__}. Details are in the bot log.")
        return

    if run.status == "ok":
        await query.message.reply_document(
            document=io.BytesIO(run.markdown.encode("utf-8")),
            filename=f"{run.run_id}.md",
        )
        await query.message.reply_text(cv.run_summary(run), reply_markup=_markup(cv.review_keyboard(run.run_id)))
    else:
        await query.message.reply_text(cv.run_summary(run))


async def handle_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    cb = cv.parse_callback(query.data)
    if cb.kind != "review":
        return
    audit.record_review(cb.run_id, cb.decision)
    await query.edit_message_text(f"{query.message.text}\n\nReview recorded: {cb.decision}.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(TypeHandler(Update, _global_auth_gate), group=-1)
    app.add_handler(CommandHandler(["start", "help"], cmd_help))
    app.add_handler(CommandHandler("crosswalk", cmd_crosswalk))
    app.add_handler(CommandHandler("coverage", cmd_coverage))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CallbackQueryHandler(handle_intake_callback, pattern=r"^xw\|"))
    app.add_handler(CallbackQueryHandler(handle_review_callback, pattern=r"^rv\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    log.info("Resilience Crosswalk bot online")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
