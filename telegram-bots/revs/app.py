"""REVS Telegram bot — entrypoint. Standalone service, own token, own
Supabase role (migration 0147_revs_bot_scoped_role.sql) — deliberately NOT
merged into telegram-bots/xo/app.py. See README.md for why.

Pilot scope only (§8.1 of REVS_Telegram_Prompt_Library.md): full
onboarding, daily AM/PM, weekly review, /tools /pace /setback /pem /stage
/mydata /deleteme /quiet /pause /resume /whatheld, and safety triggers
§5.1/§5.4(a/b/c)/§5.5/§5.6/§5.7. Deferred to v2: RECOGNISE loop generation,
/expand, monthly review, early-warning matching (§5.2/§5.3).

⚠ NOT started/enabled as a systemd service by this build — see
deploy/revs-bot.service and README.md's launch blockers. Do not run this
against real users until that checklist is signed off.
"""

from __future__ import annotations

import logging
import os
import sys

# Every sibling module in this package (commands.py, db.py, daily.py, …)
# uses flat `import db` / `from copy_bank import …` style, not
# `from telegram_bots.revs import db`. That only resolves if this
# directory is on sys.path — true when running scripts directly, but NOT
# true under `python -m telegram_bots.revs.app` (start.sh / the systemd
# unit), which puts only the repo root on sys.path. Insert this directory
# before any sibling import below runs, so both invocation styles work.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import Update
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

import commands
import config
import daily
import db
import onboarding
import safety
import scheduler
import weekly
from scoped_supabase import build_scoped_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("revs-bot")

_CLIENT = None  # set in main(); module-level so handler closures can reach it


def _get_client():
    if _CLIENT is None:
        raise RuntimeError("Supabase client not initialised — main() must run first")
    return _CLIENT


# ---------------------------------------------------------- crisis gate ---

async def _crisis_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """§5.4a — runs on ALL free text, before any other classification,
    before storage, before any scheduled send. Registered at group=-1 so
    it runs before every other text handler; raises ApplicationHandlerStop
    to prevent onboarding/tools/weekly/etc. from also processing the same
    message once a crisis is flagged — 'do not counsel, do not ask
    follow-up questions, do not attempt assessment. One message,
    resources, silence.'"""
    if not update.message or not update.message.text or update.message.text.startswith("/"):
        return
    if not safety.classify_free_text(update.message.text):
        return

    client = _get_client()
    user_id = update.effective_user.id
    row = db.get_user(client, user_id)
    if row is None:
        row = db.create_user(client, user_id, update.effective_user.first_name or "there")

    import datetime as dt
    from copy_bank import crisis_language_response
    from escalate import notify_captain

    now = dt.datetime.now(dt.timezone.utc)
    recontact_due = now + dt.timedelta(hours=24)
    db.insert_crisis_event(client, user_id, "language", recontact_due)
    db.update_user(client, user_id, quiet_until=(now + dt.timedelta(hours=48)).isoformat())

    text = crisis_language_response(safety.locale_resources(row.get("locale")))
    await update.message.reply_text(text)

    # Escalation runs after the user's own resources message is already
    # sent — never delays it — and a failure here (bad XO credentials,
    # network hiccup) is logged, not raised, so it can't break the user
    # -facing crisis path itself.
    await notify_captain(
        user_id=user_id,
        first_name=row.get("first_name"),
        trigger_type="language",
        locale=row.get("locale"),
        triggered_text=update.message.text,
    )
    raise ApplicationHandlerStop


# ---------------------------------------------------------- text router ---

async def _text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    client = _get_client()
    user_id = update.effective_user.id
    row = db.get_user(client, user_id)
    if row is None:
        row = db.create_user(client, user_id, update.effective_user.first_name or "there")
    db.touch_last_seen(client, user_id)

    if not row.get("onboarding_complete"):
        if await onboarding.handle_onboarding_text(update, context, client, row):
            return

    if await commands.handle_tool_instruction_text(update, context, client, row):
        return
    if await commands.handle_recovery_window_text(update, context, client, row):
        return
    if await commands.handle_setback_signal_text(update, context, client, row):
        return
    if await daily.handle_pm_note_text(update, context, client, row):
        return
    if await weekly.handle_weekly_text(update, context, client, row):
        return
    # No active flow was waiting on free text — matches global rule 8
    # ("every branch has a defined response") without inventing a reply
    # to unsolicited chatter; a short pointer is enough.
    await update.message.reply_text("Not sure what to do with that — /help for commands.")


# ------------------------------------------------------- callback router ---

_CALLBACK_ROUTES = {
    # "onb" is handled as a special case in _callback_router below — its
    # handler signature (update, context, client) has no `row` arg, unlike
    # every other entry here, so it doesn't fit this dict's calling
    # convention.
    "am": daily.handle_am_callback,
    "trend": daily.handle_trend_callback,
    "crisis": daily.handle_crisis_nt_callback,
    "pm": daily.handle_pm_callback,
    "tools": commands.handle_tools_callback,
    "pace": commands.handle_pace_callback,
    "setback": commands.handle_setback_callback,
    "sbref": commands.handle_setback_reflection_callback,
    "sbcause": commands.handle_setback_cause_callback,
    "sbwarn": commands.handle_setback_warning_callback,
    "sbsig": None,  # handled inline below (mark reflection done, no signal)
    "sbdone": None,  # trivial ack, handled inline
    "setstage": commands.handle_setstage_callback,
    "deleteme": commands.handle_deleteme_callback,
    "silence": commands.handle_silence_callback,
    "wkpause": commands.handle_weekly_pause_callback,
    "wk": weekly.handle_weekly_callback,
}


async def _callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    client = _get_client()
    query = update.callback_query
    prefix = query.data.split(":", 1)[0]
    user_id = update.effective_user.id
    row = db.get_user(client, user_id)
    if row is None:
        row = db.create_user(client, user_id, update.effective_user.first_name or "there")
    db.touch_last_seen(client, user_id)

    if prefix == "sbsig":
        await query.answer()
        setback_id = int(query.data.split(":")[1])
        db.update_setback(client, setback_id, reflection_status="done")
        await query.edit_message_text("Noted.")
        return
    if prefix == "sbdone":
        await query.answer()
        await query.edit_message_text("Ok.")
        return
    if prefix == "onb":
        await onboarding.handle_onboarding_callback(update, context, client)
        return

    handler = _CALLBACK_ROUTES.get(prefix)
    if handler is None:
        await query.answer()
        log.warning("[callback] no route for prefix=%s data=%s", prefix, query.data)
        return
    await handler(update, context, client, row)


# --------------------------------------------------------------- start ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    client = _get_client()
    await onboarding.start_onboarding(update, context, client)


def _wrap(fn):
    """Adapts a commands.py handler (update, context, client, row) into a
    plain CommandHandler callback that resolves the client/row itself."""

    async def _inner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        client = _get_client()
        user_id = update.effective_user.id
        row = db.get_user(client, user_id)
        if row is None:
            await update.message.reply_text("Send /start first to set up.")
            return
        db.touch_last_seen(client, user_id)
        await fn(update, context, client, row)

    return _inner


def main() -> None:
    global _CLIENT

    token = config.require(config.TELEGRAM_BOT_TOKEN, "TELEGRAM_BOT_TOKEN")
    supabase_url = config.require(config.SUPABASE_URL, "SUPABASE_URL")

    client = build_scoped_client(supabase_url)
    if client is None:
        log.error(
            "[startup] could not build a scoped revs_bot Supabase client — "
            "refusing to start unscoped. Check SUPABASE_ANON_KEY, "
            "SUPABASE_JWT_SECRET, and that migration 0147 has been applied."
        )
        sys.exit(1)
    _CLIENT = client

    app = Application.builder().token(token).build()

    # §5.4a crisis gate first, before anything else can touch free text.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _crisis_gate), group=-1)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", _wrap(commands.cmd_help)))
    app.add_handler(CommandHandler("tools", _wrap(commands.cmd_tools)))
    app.add_handler(CommandHandler("pace", _wrap(commands.cmd_pace)))
    app.add_handler(CommandHandler("setback", _wrap(commands.cmd_setback)))
    app.add_handler(CommandHandler("pem", _wrap(commands.cmd_pem)))
    app.add_handler(CommandHandler("stage", _wrap(commands.cmd_stage)))
    app.add_handler(CommandHandler("mydata", _wrap(commands.cmd_mydata)))
    app.add_handler(CommandHandler("deleteme", _wrap(commands.cmd_deleteme)))
    app.add_handler(CommandHandler("quiet", _wrap(commands.cmd_quiet)))
    app.add_handler(CommandHandler("pause", _wrap(commands.cmd_pause)))
    app.add_handler(CommandHandler("resume", _wrap(commands.cmd_resume)))
    app.add_handler(CommandHandler("whatheld", _wrap(commands.cmd_whatheld)))

    app.add_handler(CallbackQueryHandler(_callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _text_router))

    scheduler.start(app, client)

    log.info("[startup] REVS bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
