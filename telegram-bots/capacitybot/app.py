"""MY CAPACITY TODAY Bot — @tjrmindbody_capacitybot

Standalone capacity-tracking companion. Split out of telegram-bots/xo/app.py
(2026-08-22) — MY CAPACITY TODAY had no coupling to XO's LLM/mission/debrief
code, so it now runs as its own bot/process/token rather than a feature
bolted onto the Executive Officer.

V02 WP01 (2026-08-22): every question's full text and every option's full
wording now always renders in the message body (never only on a button);
buttons carry compact "N · short label" only, and long multi-select lists
paginate. See MY_CAPACITY_TODAY_V02_Mission_and_Scope.md §3. Question text
+ keyboards are both owned by capacity_today.py (q_*/kb_* pairs) so this
file never hardcodes option wording.

Run:  python -m telegram_bots.capacitybot.app
Env:  telegram-bots/capacitybot/.env
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

_TZ = ZoneInfo("Australia/Brisbane")

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
log = logging.getLogger("capacitybot")

# httpx logs every request at INFO, including the full URL — for
# python-telegram-bot's polling/send calls that means the bot token in
# plaintext on every log line. WARNING still surfaces real failures.
logging.getLogger("httpx").setLevel(logging.WARNING)

# ── Shared modules ────────────────────────────────────────────────────────────

sys.path.insert(0, str(_REPO_ROOT))

from core.platform.telegram_access import is_allowed as _chat_is_allowed

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

from telegram_bots.capacitybot import capacity_today as ct

# ── Supabase ──────────────────────────────────────────────────────────────────

_supabase = None


def _get_supabase():
    """Returns the bot's single Supabase client (memoised)."""
    global _supabase
    if _supabase is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            log.warning("SUPABASE_URL/SUPABASE_KEY not set — Supabase disabled")
            return _supabase
        try:
            from supabase import create_client
            _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            log.info("Supabase client initialised")
        except Exception as exc:
            log.warning("Supabase client failed: %s", exc)
    return _supabase


def _page(f: dict) -> int:
    """Extract the `pg` callback field as an int, defaulting to 0. A
    malformed/non-numeric value must never crash the handler (spec §25)."""
    try:
        return int(f.get("pg", 0) or 0)
    except (TypeError, ValueError):
        return 0


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "MY CAPACITY TODAY\n\n"
        "Track what your system needs today — not what diagnosis explains it.\n\n"
        "/capacity — quick check-in (30-60s)\n"
        "/deepcheck — deeper reflection\n"
        "/evening — evening reflection\n"
        "/today — today's check-ins\n"
        "/week, /month — trend reviews\n"
        "/capacity_patterns — common patterns (30d)\n"
        "/actions — which strategies helped most\n"
        "/therapy — therapist-friendly summary\n\n"
        "/help for this list again."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick capacity check-in. See capacity_today.py for the full flow."""
    await update.message.reply_text(ct.q_capacity(), reply_markup=ct.kb_capacity())


async def cmd_deepcheck(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deeper reflection, standalone (not following a quick check-in)."""
    db = _get_supabase()
    saved, row, err = await ct.write_quick_checkin(db, {})
    if not saved or not row:
        await update.message.reply_text(f"⚠️ Could not start deep check-in: {err}")
        return
    row_id = str(row["id"])
    await update.message.reply_text(
        f"Going deeper.\n\n{ct.q_deep_load_category()}",
        reply_markup=ct.kb_deep_load_category(row_id),
    )


async def cmd_evening(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"Evening reflection\n\n{ct.q_evening_trajectory()}",
        reply_markup=ct.kb_evening_trajectory(),
    )


async def cmd_capacity_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/today — show today's check-ins."""
    db = _get_supabase()
    rows = await ct.fetch_recent(db, days=0)
    today = datetime.now(_TZ).date().isoformat()
    rows = [r for r in rows if r.get("log_date") == today]
    if not rows:
        await update.message.reply_text("No check-ins logged today yet. /capacity to start one.")
        return
    parts = [ct.render_summary(r) for r in rows if r.get("checkin_type") == "capacity"]
    await update.message.reply_text("\n\n---\n\n".join(parts) if parts else "No capacity check-ins today yet.")


async def cmd_capacity_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _get_supabase()
    rows = await ct.fetch_recent(db, days=7)
    await update.message.reply_text(ct.render_trend_summary(rows, "WEEKLY CAPACITY REVIEW"))


async def cmd_capacity_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _get_supabase()
    rows = await ct.fetch_recent(db, days=30)
    await update.message.reply_text(ct.render_trend_summary(rows, "MONTHLY CAPACITY REVIEW"))


async def cmd_capacity_patterns(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _get_supabase()
    rows = await ct.fetch_recent(db, days=30)
    await update.message.reply_text(ct.render_trend_summary(rows, "CAPACITY PATTERNS — LAST 30 DAYS"))


async def cmd_capacity_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _get_supabase()
    rows = await ct.fetch_recent(db, days=30)
    await update.message.reply_text(ct.render_actions_summary(rows))


async def cmd_therapy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(ct.q_therapy_window(), reply_markup=ct.kb_therapy_window())


async def cmd_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Only free-text input this bot expects: the deep check-in's closing
    note (trigger + notes). Anything else gets pointed back at /capacity —
    this bot has no LLM/general-chat path, unlike XO."""
    text = (update.message.text or "").strip()
    if not text:
        return

    row_id = context.user_data.pop("capacity_deep_note_id", None) if context.user_data else None
    if row_id:
        db = _get_supabase()
        saved, err = await ct.write_deep_checkin(db, row_id, {"tn": text, "nt": text})
        await update.message.reply_text(
            "🔎 Deep check-in saved." if saved else f"⚠️ Could not save note: {err}"
        )
        return

    await update.message.reply_text("Not sure what to do with that — try /capacity or /help.")


# ── Inline MY CAPACITY TODAY callbacks ───────────────────────────────────────
# Same convention as the source in telegram-bots/xo/app.py: state lives
# entirely in the pipe-delimited callback data, checked from most-complete
# field backward to least-complete (capacity_today.base_from() rebuilds the
# next screen's prefix from parsed fields rather than string-slicing). A
# `pg` field (current button page) rides alongside a multi-select's other
# fields — see capacity_today.kb_multiselect / _page() above.

async def handle_capacity_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Two phases. Phase 1 (no `id` yet, Q1-Q5): state lives entirely in the
    callback string — cheap, these fields are all single-char codes, never
    close to Telegram's 64-byte callback_data limit. Phase 2 (Q6 onward,
    `id` present): the multi-select steps (active_loads, identified_needs)
    can select up to 16 items each — carrying that plus every prior field in
    the callback data blew past 64 bytes in testing (measured 103 bytes
    worst-case). So from Q6 on, the row is created in the DB and every tap
    writes through immediately; callback data only ever carries the row id
    (a short bigint) plus the field being set *this* tap."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("ct|"):
        return
    f = ct.parse_cb(data)
    if "noop" in f:
        return

    db = _get_supabase()
    row_id = f.get("id")

    # ── Phase 2: id present — every step reads/writes the DB row directly ──
    if row_id is not None:
        id_base = f"ct|id={row_id}"

        if f.get("done") == "1":
            row = await ct.fetch_checkin(db, row_id)
            await query.edit_message_text(ct.render_summary(row or {}))
            return

        if f.get("act") is not None:
            saved, row, err = await ct.write_quick_checkin(db, {"id": row_id, "act": f["act"]})
            if saved and row:
                await query.edit_message_text(
                    ct.render_summary(row),
                    reply_markup=ct.kb_go_deeper(str(row["id"])),
                )
            else:
                await query.edit_message_text(f"⚠️ Could not save check-in: {err}")
            return

        if f.get("nd") is not None:
            saved, row, err = await ct.write_quick_checkin(db, {"id": row_id, "nd": f["nd"]})
            if f.get("next") == "1":
                codes = ct.suggest_actions(row or {})
                await query.edit_message_text(
                    ct.q_actions(codes),
                    reply_markup=ct.kb_actions(id_base, codes),
                )
            else:
                await query.edit_message_text(
                    ct.q_identified_needs(f["nd"]),
                    reply_markup=ct.kb_multiselect(
                        id_base, "nd", ct.IDENTIFIED_NEEDS, ct.IDENTIFIED_NEEDS_SHORT, f["nd"], page=_page(f)),
                )
            return

        if f.get("cp") is not None:
            await ct.write_quick_checkin(db, {"id": row_id, "cp": f["cp"]})
            await query.edit_message_text(
                ct.q_identified_needs(""),
                reply_markup=ct.kb_multiselect(
                    id_base, "nd", ct.IDENTIFIED_NEEDS, ct.IDENTIFIED_NEEDS_SHORT, "", page=0),
            )
            return

        if f.get("ld") is not None:
            saved, row, err = await ct.write_quick_checkin(db, {"id": row_id, "ld": f["ld"]})
            if f.get("next") == "1":
                await query.edit_message_text(
                    ct.q_compensation(),
                    reply_markup=ct.kb_compensation(id_base),
                )
            else:
                await query.edit_message_text(
                    ct.q_active_loads(f["ld"]),
                    reply_markup=ct.kb_multiselect(
                        id_base, "ld", ct.ACTIVE_LOADS, ct.ACTIVE_LOADS_SHORT, f["ld"], page=_page(f)),
                )
            return

        # just transitioned into Phase 2 with nothing selected yet
        await query.edit_message_text(
            ct.q_active_loads(""),
            reply_markup=ct.kb_multiselect(
                id_base, "ld", ct.ACTIVE_LOADS, ct.ACTIVE_LOADS_SHORT, "", page=0),
        )
        return

    # ── Phase 1: Q1-Q5, pure callback-data state ────────────────────────────

    if f.get("done") == "1":
        saved, row, err = await ct.write_quick_checkin(db, f)
        text = ct.render_summary(row or f)
        text += "\n\n(Saved — partial check-in.)" if saved else f"\n\n⚠️ {err}"
        await query.edit_message_text(text)
        return

    if f.get("e") is not None:
        # Q5 answered — create the row now, hand off to Phase 2 (id-based).
        saved, row, err = await ct.write_quick_checkin(db, f)
        if not saved or not row:
            await query.edit_message_text(f"⚠️ Could not start check-in: {err}")
            return
        await query.edit_message_text(
            ct.q_active_loads(""),
            reply_markup=ct.kb_multiselect(
                f"ct|id={row['id']}", "ld", ct.ACTIVE_LOADS, ct.ACTIVE_LOADS_SHORT, "", page=0),
        )
        return

    if f.get("r") is not None:
        await query.edit_message_text(
            ct.q_executive_function(),
            reply_markup=ct.kb_executive_function(f["c"], f["t"], f["p"], f["ps"], f["r"]),
        )
        return

    if f.get("ps") is not None:
        await query.edit_message_text(
            ct.q_regulation(),
            reply_markup=ct.kb_regulation(f["c"], f["t"], f["p"], f["ps"]),
        )
        return

    if f.get("p") is not None:
        await query.edit_message_text(
            ct.q_pain_score(),
            reply_markup=ct.kb_pain_score(f["c"], f["t"], f["p"]),
        )
        return

    if f.get("t") is not None:
        await query.edit_message_text(
            ct.q_pain(),
            reply_markup=ct.kb_pain(f["c"], f["t"]),
        )
        return

    # only capacity_state chosen so far
    await query.edit_message_text(
        ct.q_stimulation(),
        reply_markup=ct.kb_stimulation(f["c"]),
    )


async def handle_capacity_deep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deep check-in. Two phases like the main quick check-in: lc/uc/mp/rd
    accumulate in the callback string itself; once `rd` is answered the
    draft is written to the row and every step after that (rf/ha/ua) is
    write-through, id-only in the callback."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("ctd|"):
        return
    f = ct.parse_cb(data)
    row_id = f.get("id")
    if not row_id:
        return
    db = _get_supabase()
    base = f"ctd|id={row_id}"

    # ── Phase 2: rf/ha/ua/final — write-through, id-only callback base ──────
    if f.get("final") == "1":
        row = await ct.fetch_checkin(db, row_id)
        context.user_data.pop("capacity_deep_note_id", None)
        await query.edit_message_text(
            "🔎 Deep check-in saved." if row else "🔎 Deep check-in saved (summary unavailable)."
        )
        return

    if f.get("ua") is not None:
        saved, err = await ct.write_deep_checkin(db, row_id, {"ua": f["ua"]})
        if f.get("next") == "1" or f.get("done") == "1":
            context.user_data["capacity_deep_note_id"] = row_id
            await query.edit_message_text(
                "One more (optional): what happened before this, or anything else worth noting?\n\n"
                "Reply with text, or tap Skip.",
                reply_markup=ct.kb_deep_note_prompt(row_id),
            )
        else:
            await query.edit_message_text(
                ct.q_deep_multiselect("What made things worse?", ct.UNHELPFUL_ACTIONS_OPTIONS, f["ua"]),
                reply_markup=ct.kb_deep_multiselect(
                    row_id, "ua", ct.UNHELPFUL_ACTIONS_OPTIONS, ct.UNHELPFUL_ACTIONS_SHORT, f["ua"], page=_page(f)),
            )
        return

    if f.get("ha") is not None:
        saved, err = await ct.write_deep_checkin(db, row_id, {"ha": f["ha"]})
        if f.get("next") == "1":
            await query.edit_message_text(
                ct.q_deep_multiselect("What made things worse?", ct.UNHELPFUL_ACTIONS_OPTIONS, ""),
                reply_markup=ct.kb_deep_multiselect(
                    row_id, "ua", ct.UNHELPFUL_ACTIONS_OPTIONS, ct.UNHELPFUL_ACTIONS_SHORT, "", page=0),
            )
        elif f.get("done") == "1":
            context.user_data["capacity_deep_note_id"] = row_id
            await query.edit_message_text(
                "One more (optional): what happened before this, or anything else worth noting?\n\n"
                "Reply with text, or tap Skip.",
                reply_markup=ct.kb_deep_note_prompt(row_id),
            )
        else:
            await query.edit_message_text(
                ct.q_deep_multiselect("What helped?", ct.HELPFUL_ACTIONS_OPTIONS, f["ha"]),
                reply_markup=ct.kb_deep_multiselect(
                    row_id, "ha", ct.HELPFUL_ACTIONS_OPTIONS, ct.HELPFUL_ACTIONS_SHORT, f["ha"], page=_page(f)),
            )
        return

    if f.get("rf") is not None:
        saved, err = await ct.write_deep_checkin(db, row_id, {"rf": f["rf"]})
        if f.get("next") == "1":
            await query.edit_message_text(
                ct.q_deep_multiselect("What helped?", ct.HELPFUL_ACTIONS_OPTIONS, ""),
                reply_markup=ct.kb_deep_multiselect(
                    row_id, "ha", ct.HELPFUL_ACTIONS_OPTIONS, ct.HELPFUL_ACTIONS_SHORT, "", page=0),
            )
        elif f.get("done") == "1":
            context.user_data["capacity_deep_note_id"] = row_id
            await query.edit_message_text(
                "One more (optional): what happened before this, or anything else worth noting?\n\n"
                "Reply with text, or tap Skip.",
                reply_markup=ct.kb_deep_note_prompt(row_id),
            )
        else:
            await query.edit_message_text(
                ct.q_deep_multiselect(
                    "Did you skip food, movement, rest, medication, sleep, or recovery?",
                    ct.RECOVERY_FACTORS, f["rf"]),
                reply_markup=ct.kb_deep_multiselect(
                    row_id, "rf", ct.RECOVERY_FACTORS, ct.RECOVERY_FACTORS_SHORT, f["rf"], page=_page(f)),
            )
        return

    # ── Phase 1: lc/uc/mp/rd — accumulate in the callback string ────────────

    if f.get("rd") is not None:
        saved, err = await ct.write_deep_checkin(db, row_id, f)
        if not saved:
            await query.edit_message_text(f"⚠️ Could not save: {err}")
            return
        await query.edit_message_text(
            ct.q_deep_multiselect(
                "Did you skip food, movement, rest, medication, sleep, or recovery?",
                ct.RECOVERY_FACTORS, ""),
            reply_markup=ct.kb_deep_multiselect(
                row_id, "rf", ct.RECOVERY_FACTORS, ct.RECOVERY_FACTORS_SHORT, "", page=0),
        )
        return

    if f.get("mp") is not None:
        base2 = f"{base}|lc={f.get('lc')}|uc={f.get('uc')}|mp={f['mp']}"
        await query.edit_message_text(
            ct.q_deep_recovery_duration(),
            reply_markup=ct.kb_deep_recovery_duration(base2),
        )
        return

    if f.get("uc") is not None:
        base2 = f"{base}|lc={f.get('lc')}|uc={f['uc']}"
        await query.edit_message_text(
            "Were you masking or forcing yourself to function?",
            reply_markup=ct.kb_deep_yesno(base2, "mp"),
        )
        return

    if f.get("lc") is not None:
        base2 = f"{base}|lc={f['lc']}"
        await query.edit_message_text(
            "Did something unexpected change?",
            reply_markup=ct.kb_deep_yesno(base2, "uc"),
        )
        return


async def handle_capacity_reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """'Remind me later' — schedules a one-off JobQueue nudge. In-memory
    only: lost on bot restart, acceptable for a same-day nudge."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("ctr|"):
        return
    f = ct.parse_cb(data)
    row_id = f.get("id")
    minutes = f.get("m")
    if not row_id:
        return

    if minutes is None:
        await query.edit_message_text(
            ct.q_remind_duration(),
            reply_markup=ct.kb_remind_duration(row_id),
        )
        return

    chat_id = update.effective_chat.id
    mins = int(minutes)

    async def _fire(ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await ctx.bot.send_message(
            chat_id=chat_id,
            text=f"⏰ Reminder!\n\n{ct.q_capacity()}",
            reply_markup=ct.kb_capacity(),
        )

    context.job_queue.run_once(_fire, when=mins * 60, name=f"capacity-remind-{row_id}")
    await query.edit_message_text(f"⏰ Reminder set for {mins} minutes.")


async def handle_capacity_evening_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("cte|"):
        return
    f = ct.parse_cb(data)
    db = _get_supabase()

    if f.get("cd") is not None:
        saved, err = await ct.write_evening(db, f)
        text = "🌙 Evening reflection saved." if saved else f"⚠️ Could not save: {err}"
        await query.edit_message_text(text)
        return

    if f.get("hf") is not None:
        await query.edit_message_text(
            ct.q_evening_debt(),
            reply_markup=ct.kb_evening_debt(f["dt"], f["hf"]),
        )
        return

    if f.get("dt") is not None:
        await query.edit_message_text(
            ct.q_evening_helpful(),
            reply_markup=ct.kb_evening_helpful(f["dt"]),
        )
        return


async def handle_capacity_therapy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("cty|"):
        return
    f = ct.parse_cb(data)
    weeks = int(f.get("w", "2"))
    db = _get_supabase()
    rows = await ct.fetch_recent(db, days=weeks * 7)
    await query.edit_message_text(ct.render_therapy_summary(rows, weeks))


# ── Main ──────────────────────────────────────────────────────────────────────

_BOT_COMMANDS = [
    ("capacity",          "Quick capacity check-in (30-60s, tap buttons)"),
    ("deepcheck",         "Deeper reflection — what happened, what helped"),
    ("evening",           "Evening capacity reflection (3 questions)"),
    ("today",             "Show today's capacity check-ins"),
    ("week",              "Weekly capacity review"),
    ("month",             "Monthly capacity pattern review"),
    ("capacity_patterns", "Most common capacity patterns (30d)"),
    ("actions",           "Which strategies have helped most"),
    ("therapy",           "Generate a therapist-friendly summary"),
    ("start",             "Introduction and quick-start"),
    ("help",              "Commands"),
]


async def _post_init(app) -> None:
    from telegram import BotCommand
    await app.bot.set_my_commands([BotCommand(cmd, desc) for cmd, desc in _BOT_COMMANDS])
    log.info(
        "CapacityBot started version=V02 telegram=connected supabase=%s commands=%d",
        "connected" if _get_supabase() else "unavailable", len(_BOT_COMMANDS),
    )


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """One malformed callback or Supabase failure must not crash the
    process (spec §25) — the python-telegram-bot dispatcher already isolates
    handler exceptions per-update, this is just the log backstop."""
    log.exception("[unhandled] %s", context.error)


async def _global_auth_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs before every other handler (group -1). Silent drop (no reply)
    on an unauthorized chat."""
    chat = update.effective_chat
    if chat is None or not _chat_is_allowed(chat.id, TELEGRAM_CHAT_ID):
        raise ApplicationHandlerStop


def main() -> None:
    log.info("Capacity Bot starting")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_post_init).build()
    app.add_error_handler(_on_error)

    app.add_handler(TypeHandler(Update, _global_auth_gate), group=-1)

    app.add_handler(CommandHandler("start",              cmd_start))
    app.add_handler(CommandHandler("help",               cmd_help))
    app.add_handler(CommandHandler("capacity",           cmd_capacity))
    app.add_handler(CommandHandler("deepcheck",          cmd_deepcheck))
    app.add_handler(CommandHandler("evening",            cmd_evening))
    app.add_handler(CommandHandler("today",              cmd_capacity_today))
    app.add_handler(CommandHandler("week",               cmd_capacity_week))
    app.add_handler(CommandHandler("month",              cmd_capacity_month))
    app.add_handler(CommandHandler("capacity_patterns",  cmd_capacity_patterns))
    app.add_handler(CommandHandler("actions",            cmd_capacity_actions))
    app.add_handler(CommandHandler("therapy",            cmd_therapy))

    app.add_handler(CallbackQueryHandler(handle_capacity_callback,         pattern=r"^ct\|"))
    app.add_handler(CallbackQueryHandler(handle_capacity_deep_callback,    pattern=r"^ctd\|"))
    app.add_handler(CallbackQueryHandler(handle_capacity_evening_callback, pattern=r"^cte\|"))
    app.add_handler(CallbackQueryHandler(handle_capacity_therapy_callback, pattern=r"^cty\|"))
    app.add_handler(CallbackQueryHandler(handle_capacity_reminder_callback, pattern=r"^ctr\|"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_message))

    log.info("Capacity Bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
