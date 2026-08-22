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
from telegram_bots.capacitybot import guide
from telegram_bots.capacitybot import helpme
from telegram_bots.capacitybot import intervention_engine as ie

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
    """V02 WP07 — "which strategies were used most" -> "which strategies
    actually helped", sourced from capacity_intervention_events (both
    /capacity Q9 and /helpme accepts), not just capacity_checkins'
    selected_action text."""
    db = _get_supabase()
    summary = await ie.personal_effectiveness_summary(db)
    await update.message.reply_text(ie.render_effectiveness_summary(summary))


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
                # V02 WP06 — Q9 acceptance now also feeds the same
                # outcome-learning table /helpme writes to (spec §19), not
                # just the free-text selected_action column on the
                # check-in row (kept for dashboard/history compatibility).
                if f["act"] != "skip":
                    intervention = await ie.get_intervention(db, f["act"])
                    if intervention:
                        ok, event_row, _err = await ie.create_event(
                            db,
                            source="capacity_q9",
                            intervention_id=f["act"],
                            checkin_id=row_id,
                            capacity_before=row.get("capacity_state"),
                            stimulation_before=row.get("stimulation_state"),
                            pain_before=row.get("pain_state"),
                            pain_score_before=row.get("pain_score"),
                            regulation_before=row.get("regulation_state"),
                            executive_before=row.get("executive_function"),
                            compensation_before=row.get("compensation_load"),
                            context_loads=row.get("active_loads"),
                        )
                        if ok and event_row and intervention.get("requires_followup"):
                            minutes = intervention.get("estimated_minutes") or 15
                            chat_id = update.effective_chat.id
                            event_id = event_row["id"]

                            async def _fire(ctx: ContextTypes.DEFAULT_TYPE, _eid=event_id) -> None:
                                await ctx.bot.send_message(
                                    chat_id=chat_id,
                                    text=helpme.q_reassess_outcome(),
                                    reply_markup=helpme.kb_reassess_outcome(_eid),
                                )

                            context.job_queue.run_once(_fire, when=minutes * 60, name=f"capacity-q9-reassess-{event_id}")
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
                ranked = await ie.rank_interventions(
                    db,
                    capacity_state=(row or {}).get("capacity_state"),
                    stimulation_state=(row or {}).get("stimulation_state"),
                    pain_state=(row or {}).get("pain_state"),
                    executive_function=(row or {}).get("executive_function"),
                    limit=5,
                )
                await query.edit_message_text(
                    ct.q_actions(ranked),
                    reply_markup=ct.kb_actions(id_base, ranked),
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


# ── /helpme (V02 WP04 + WP05) ────────────────────────────────────────────────
# "Something is difficult right now. Help me do something about it." See
# helpme.py's module docstring for the full design. context.user_data holds
# the flow's browsing state (help_state, optional triage context, which
# intervention ids have already been declined) — ephemeral, cleared on
# accept/stop, lost on a bot restart mid-browse (acceptable, matches this
# bot's existing tolerance for in-flight non-persistent state).

async def cmd_helpme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("helpme_ctx", None)
    context.user_data.pop("helpme_seen", None)
    context.user_data.pop("helpme_current", None)
    await update.message.reply_text(helpme.q_helpme_entry(), reply_markup=helpme.kb_helpme_entry())


async def _helpme_offer_next(query, context: ContextTypes.DEFAULT_TYPE, state: str) -> None:
    """Ranks candidates for the current flow context and shows the
    highest-scored one not already declined this session (spec §7: offer
    ONE intervention, not a list)."""
    flow_ctx = context.user_data.get("helpme_ctx", {})
    seen = context.user_data.get("helpme_seen", [])
    db = _get_supabase()
    ranked = await ie.rank_interventions(
        db,
        help_state=state,
        capacity_state=flow_ctx.get("capacity_state"),
        stimulation_state=flow_ctx.get("stimulation_state"),
        pain_state=flow_ctx.get("pain_state"),
        limit=10,
    )
    candidates = [r for r in ranked if r["intervention_id"] not in seen]
    if not candidates:
        await query.edit_message_text(helpme.render_no_more_options())
        return
    top = candidates[0]
    context.user_data["helpme_current"] = top["intervention_id"]
    await query.edit_message_text(
        helpme.render_offer(top),
        reply_markup=helpme.kb_offer(state, top["intervention_id"]),
    )


async def handle_helpme_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """State selection + the 3 states with an optional one-tap clarifying
    question (overwhelmed/sensory_overload/unknown — spec §8.1/§8.5/§8.9)."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("ch|"):
        return
    f = helpme.parse_cb(data)
    state = f.get("s")
    if not state:
        return

    if state == "overwhelmed" and "c" not in f:
        await query.edit_message_text(helpme.q_reduce_first(), reply_markup=helpme.kb_reduce_first(state))
        return

    if state == "sensory_overload" and "c" not in f:
        await query.edit_message_text(helpme.q_sensory_dominant(), reply_markup=helpme.kb_sensory_dominant(state))
        return

    if state == "unknown":
        if "cap" not in f:
            await query.edit_message_text(ct.q_capacity(), reply_markup=helpme.kb_triage_capacity())
            return
        if "stim" not in f:
            await query.edit_message_text(ct.q_stimulation(), reply_markup=helpme.kb_triage_stimulation(f["cap"]))
            return
        if "pain" not in f:
            await query.edit_message_text(ct.q_pain(), reply_markup=helpme.kb_triage_pain(f["cap"], f["stim"]))
            return

    context.user_data["helpme_ctx"] = {
        "capacity_state": ct.CAPACITY_CODE_TO_STATE.get(f.get("cap")) if f.get("cap") else None,
        "stimulation_state": ct.STIM_CODE_TO_STATE.get(f.get("stim")) if f.get("stim") else None,
        "pain_state": ct.PAIN_CODE_TO_STATE.get(f.get("pain")) if f.get("pain") else None,
        "context_note": f.get("c"),
    }
    context.user_data["helpme_seen"] = []
    await _helpme_offer_next(query, context, state)


async def handle_helpme_offer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Accept / Something else / Can't do that / Stop on the offered
    intervention (spec §8.1's button pattern, generalised to every state)."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("chi|"):
        return
    f = helpme.parse_cb(data)
    state = f.get("s")
    iid = f.get("iid")
    action = f.get("act")
    if not state or not iid:
        return

    if action == "stop":
        await query.edit_message_text(helpme.render_stopped())
        context.user_data.pop("helpme_ctx", None)
        context.user_data.pop("helpme_seen", None)
        context.user_data.pop("helpme_current", None)
        return

    if action == "skip":
        context.user_data.setdefault("helpme_seen", []).append(iid)
        await _helpme_offer_next(query, context, state)
        return

    if action == "accept":
        db = _get_supabase()
        intervention = await ie.get_intervention(db, iid)
        if not intervention:
            await query.edit_message_text("⚠️ Could not load that intervention.")
            return
        flow_ctx = context.user_data.get("helpme_ctx", {})
        ok, row, err = await ie.create_event(
            db,
            source="helpme",
            intervention_id=iid,
            help_state=state,
            capacity_before=flow_ctx.get("capacity_state"),
            stimulation_before=flow_ctx.get("stimulation_state"),
            pain_before=flow_ctx.get("pain_state"),
            context_loads=[flow_ctx["context_note"]] if flow_ctx.get("context_note") else None,
        )
        if not ok or not row:
            await query.edit_message_text(f"⚠️ Could not log this: {err}")
            return

        reminder_minutes = None
        if intervention.get("requires_followup"):
            reminder_minutes = intervention.get("estimated_minutes") or 15
            chat_id = update.effective_chat.id
            event_id = row["id"]

            async def _fire(ctx: ContextTypes.DEFAULT_TYPE) -> None:
                await ctx.bot.send_message(
                    chat_id=chat_id,
                    text=helpme.q_reassess_outcome(),
                    reply_markup=helpme.kb_reassess_outcome(event_id),
                )

            context.job_queue.run_once(_fire, when=reminder_minutes * 60, name=f"helpme-reassess-{event_id}")

        await query.edit_message_text(helpme.render_accepted(intervention, reminder_minutes))
        context.user_data.pop("helpme_ctx", None)
        context.user_data.pop("helpme_seen", None)
        context.user_data.pop("helpme_current", None)


async def handle_helpme_reassessment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Better/Same/Worse -> optional capacity-after -> optional
    would-use-again (spec §12). Reachable either from the reminder DM or by
    tapping into a still-open reassessment prompt."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("chr|"):
        return
    f = helpme.parse_cb(data)
    event_id = f.get("ev")
    if not event_id:
        return
    db = _get_supabase()

    if f.get("ua") is not None:
        ok, err = await ie.complete_reassessment(
            db, event_id,
            outcome=f.get("o", "unknown"),
            capacity_after=None if f.get("ca") in (None, "skip") else f["ca"],
            would_use_again=None if f["ua"] == "skip" else f["ua"],
        )
        await query.edit_message_text(helpme.render_reassess_done() if ok else f"⚠️ Could not save: {err}")
        return

    if f.get("ca") is not None:
        await query.edit_message_text(
            helpme.q_reassess_use_again(),
            reply_markup=helpme.kb_reassess_use_again(event_id, f["o"], f["ca"]),
        )
        return

    if f.get("o") is not None:
        await query.edit_message_text(
            helpme.q_reassess_capacity_after(),
            reply_markup=helpme.kb_reassess_capacity_after(event_id, f["o"]),
        )
        return


# ── /guide (V02 WP08) ─────────────────────────────────────────────────────────
# "I am not necessarily in distress, but I do not know what would be
# sensible to do next" (spec §16). Reuses a recent /capacity check-in when
# one exists rather than re-asking; always asks "available time", the one
# dimension capacity_checkins has no equivalent for.

async def _find_recent_checkin(db) -> dict | None:
    rows = await ct.fetch_recent(db, days=1)
    now = datetime.now(_TZ)
    recent = None
    for r in rows:
        if r.get("checkin_type") != "capacity" or not r.get("capacity_state") or not r.get("captured_at"):
            continue
        try:
            captured = datetime.fromisoformat(r["captured_at"])
        except ValueError:
            continue
        age_minutes = (now - captured).total_seconds() / 60
        if age_minutes <= guide.RECENT_CHECKIN_WINDOW_MINUTES:
            recent = r  # rows are ascending by captured_at — last match wins
    return recent


async def cmd_guide(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _get_supabase()
    recent = await _find_recent_checkin(db)
    if recent:
        parts = ["cg", f"cap={guide.STATE_TO_CAPACITY_CODE.get(recent['capacity_state'])}"]
        if recent.get("stimulation_state"):
            parts.append(f"stim={guide.STATE_TO_STIM_CODE.get(recent['stimulation_state'])}")
        if recent.get("pain_state"):
            parts.append(f"pain={guide.STATE_TO_PAIN_CODE.get(recent['pain_state'])}")
        prefix = "|".join(parts)
        await update.message.reply_text(guide.q_time_available(), reply_markup=guide.kb_time_available(prefix))
    else:
        await update.message.reply_text(ct.q_capacity(), reply_markup=guide.kb_guide_capacity())


async def handle_guide_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("cg|"):
        return
    f = guide.parse_cb(data)

    if "cap" not in f:
        return
    if "stim" not in f and "t" not in f:
        await query.edit_message_text(ct.q_stimulation(), reply_markup=guide.kb_guide_stimulation(f["cap"]))
        return
    if "pain" not in f and "t" not in f:
        await query.edit_message_text(ct.q_pain(), reply_markup=guide.kb_guide_pain(f["cap"], f["stim"]))
        return
    if "t" not in f:
        prefix = f"cg|cap={f['cap']}" + (f"|stim={f['stim']}" if f.get("stim") else "") + \
                 (f"|pain={f['pain']}" if f.get("pain") else "")
        await query.edit_message_text(guide.q_time_available(), reply_markup=guide.kb_time_available(prefix))
        return

    capacity_state = ct.CAPACITY_CODE_TO_STATE.get(f.get("cap"))
    stimulation_state = ct.STIM_CODE_TO_STATE.get(f.get("stim")) if f.get("stim") else None
    pain_state = ct.PAIN_CODE_TO_STATE.get(f.get("pain")) if f.get("pain") else None
    max_minutes = guide.TIME_TO_MAX_MINUTES.get(f["t"])

    context.user_data["guide_ctx"] = {
        "capacity_state": capacity_state,
        "stimulation_state": stimulation_state,
        "pain_state": pain_state,
        "max_minutes": max_minutes,
    }
    context.user_data["guide_seen"] = []

    db = _get_supabase()
    ranked = await ie.rank_interventions(
        db, capacity_state=capacity_state, stimulation_state=stimulation_state,
        pain_state=pain_state, max_minutes=max_minutes, limit=10,
    )
    if not ranked:
        await query.edit_message_text(guide.render_no_options())
        return
    top = ranked[0]
    context.user_data["guide_current"] = top["intervention_id"]
    await query.edit_message_text(guide.render_offer(top), reply_markup=guide.kb_offer(top["intervention_id"]))


async def handle_guide_offer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("cgi|"):
        return
    f = guide.parse_cb(data)
    iid = f.get("iid")
    action = f.get("act")
    if not iid or not action:
        return

    db = _get_supabase()
    flow_ctx = context.user_data.get("guide_ctx", {})

    if action == "why":
        intervention = await ie.get_intervention(db, iid)
        if not intervention:
            return
        why_text = guide.render_why(
            intervention, flow_ctx.get("capacity_state"),
            flow_ctx.get("stimulation_state"), flow_ctx.get("pain_state"),
        )
        await query.edit_message_text(
            f"{guide.render_offer(intervention)}\n\n{why_text}",
            reply_markup=guide.kb_offer(iid, showing_why=True),
        )
        return

    if action == "another":
        context.user_data.setdefault("guide_seen", []).append(iid)
        seen = context.user_data["guide_seen"]
        ranked = await ie.rank_interventions(
            db, capacity_state=flow_ctx.get("capacity_state"), stimulation_state=flow_ctx.get("stimulation_state"),
            pain_state=flow_ctx.get("pain_state"), max_minutes=flow_ctx.get("max_minutes"), limit=10,
        )
        candidates = [r for r in ranked if r["intervention_id"] not in seen]
        if not candidates:
            await query.edit_message_text(guide.render_no_options())
            return
        top = candidates[0]
        context.user_data["guide_current"] = top["intervention_id"]
        await query.edit_message_text(guide.render_offer(top), reply_markup=guide.kb_offer(top["intervention_id"]))
        return

    if action == "accept":
        intervention = await ie.get_intervention(db, iid)
        if not intervention:
            await query.edit_message_text("⚠️ Could not load that intervention.")
            return
        ok, row, err = await ie.create_event(
            db, source="guide", intervention_id=iid,
            capacity_before=flow_ctx.get("capacity_state"),
            stimulation_before=flow_ctx.get("stimulation_state"),
            pain_before=flow_ctx.get("pain_state"),
        )
        if not ok or not row:
            await query.edit_message_text(f"⚠️ Could not log this: {err}")
            return

        reminder_minutes = None
        if intervention.get("requires_followup"):
            reminder_minutes = intervention.get("estimated_minutes") or 15
            chat_id = update.effective_chat.id
            event_id = row["id"]

            async def _fire(ctx: ContextTypes.DEFAULT_TYPE) -> None:
                await ctx.bot.send_message(
                    chat_id=chat_id,
                    text=helpme.q_reassess_outcome(),
                    reply_markup=helpme.kb_reassess_outcome(event_id),
                )

            context.job_queue.run_once(_fire, when=reminder_minutes * 60, name=f"guide-reassess-{event_id}")

        await query.edit_message_text(guide.render_accepted(intervention, reminder_minutes))
        context.user_data.pop("guide_ctx", None)
        context.user_data.pop("guide_seen", None)
        context.user_data.pop("guide_current", None)


# ── Main ──────────────────────────────────────────────────────────────────────

_BOT_COMMANDS = [
    ("helpme",            "Something's hard right now — get one thing to try"),
    ("guide",             "Not sure what to do next — get a sensible suggestion"),
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
    app.add_handler(CommandHandler("helpme",             cmd_helpme))
    app.add_handler(CommandHandler("guide",              cmd_guide))
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
    app.add_handler(CallbackQueryHandler(handle_helpme_callback,              pattern=r"^ch\|"))
    app.add_handler(CallbackQueryHandler(handle_helpme_offer_callback,        pattern=r"^chi\|"))
    app.add_handler(CallbackQueryHandler(handle_helpme_reassessment_callback, pattern=r"^chr\|"))
    app.add_handler(CallbackQueryHandler(handle_guide_callback,               pattern=r"^cg\|"))
    app.add_handler(CallbackQueryHandler(handle_guide_offer_callback,         pattern=r"^cgi\|"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_message))

    log.info("Capacity Bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
