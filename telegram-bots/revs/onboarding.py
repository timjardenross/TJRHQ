"""Part 1 — Onboarding. §1.1 through §1.6 of
REVS_Telegram_Prompt_Library.md.

State is persisted to revs_users.onboarding_step after every message, not
kept in python-telegram-bot's in-memory ConversationHandler — the flow is
"pausable and resumable at any point" per the doc, including across a bot
restart, which in-memory conversation state doesn't survive.

Deferred to v2 (§8.1 pilot scope): nothing in Part 1 itself is deferred —
onboarding ships in full for the pilot. §1.4a triage is the *documented
interim* (NOTE in the source doc) until the live assessment
(tjrmindbody_public's discover-your-capacity) has a result-import path;
that integration is tracked separately, not blocking this bot.
"""

from __future__ import annotations

import datetime as dt
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import db
import safety
from copy_bank import STAGE_LABELS

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=data) for label, data in row] for row in rows]
    )


async def _send(update: Update, text: str, markup=None):
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)


# ---------------------------------------------------------------- entry ---

async def start_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE, client) -> None:
    user = update.effective_user
    row = db.get_user(client, user.id)
    if row is None:
        row = db.create_user(client, user.id, user.first_name or "there")
    if row.get("onboarding_complete"):
        await update.message.reply_text(
            "You're already set up. /help for commands, /pause to stop the check-ins for a while."
        )
        return
    await _welcome(update, context, first_name=row.get("first_name") or "there")


async def _welcome(update: Update, context, first_name: str):
    text = (
        f"Hi {first_name}. This is the REVS check-in.\n\n"
        "Two short messages a day, one review each week.\n"
        "Most days it's two taps. That's the whole thing.\n\n"
        "You can pause it, slow it down or stop it any time."
    )
    kb = _kb([[("Start setup", "onb:start"), ("Tell me more first", "onb:more")]])
    await _send(update, text, kb)


# ----------------------------------------------------------- dispatcher ---

async def handle_onboarding_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data  # "onb:<action>[:<value>]"
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    value = parts[2] if len(parts) > 2 else None

    row = db.get_user(client, user_id) or db.create_user(client, user_id, update.effective_user.first_name or "there")

    if action == "more":
        text = (
            "REVS works on the idea that capacity is real and finite, and "
            "that recovery happens by working with your system rather than "
            "overriding it.\n\n"
            "This bot isn't here to set you targets or get you doing more. "
            "It's here to help you notice your own pattern."
        )
        await _send(update, text, _kb([[("Start setup", "onb:start")]]))
        return

    if action == "start":
        await _show_consent(update)
        return

    if action == "consent_policy":
        await update.callback_query.edit_message_text(
            "Full policy: tjrmindbody.com/privacy-policy",
            reply_markup=_kb([[("Back", "onb:start")]]),
        )
        return

    if action == "consent_ok":
        db.update_user(client, user_id, consent_at=dt.datetime.now(dt.timezone.utc).isoformat(), onboarding_step="locale")
        await _show_locale(update)
        return

    if action == "locale":
        db.update_user(client, user_id, locale=value, onboarding_step="pem")
        if value == "OTHER":
            await update.callback_query.edit_message_text(
                "I'll show international options. Findahelpline.com covers "
                "most countries.",
                reply_markup=_kb([[("Ok", "onb:pem_intro")]]),
            )
            return
        await show_pem(update)
        return

    if action == "pem_intro":
        await show_pem(update)
        return

    if action == "pem":
        # Durable, not context.user_data: this answer can arrive long after
        # the question was sent (periodic re-screens, delayed replies), so
        # the label must survive a bot restart. onboarding_complete=False
        # means this is the once-only initial screen; otherwise it's a
        # re-screen and pending_pem_trigger (set by whichever re-screen
        # path fired) carries the audit label.
        if not row.get("onboarding_complete"):
            trigger = "onboarding"
        else:
            trigger = row.get("pending_pem_trigger") or "user_command"
            db.update_user(client, user_id, pending_pem_trigger=None)
        await _handle_pem_answer(update, client, user_id, value, trigger=trigger)
        return

    if action == "pem_ack":
        if not row.get("onboarding_complete"):
            await _show_stage(update)
        else:
            await update.callback_query.edit_message_text("Updated.")
        return

    if action == "stage":
        if value == "unsure":
            db.update_user(client, user_id, onboarding_step="triage_q1")
            await _show_triage_q1(update)
            return
        db.update_user(client, user_id, stage=value, stage_set_at=dt.datetime.now(dt.timezone.utc).isoformat(), onboarding_step="timing_am")
        await _show_timing_am(update)
        return

    if action == "triage1":
        context.user_data["triage_q1"] = value
        await _show_triage_q2(update)
        return

    if action == "triage2":
        context.user_data["triage_q2"] = value
        await _show_triage_q3(update)
        return

    if action == "triage3":
        stage = _score_triage(context.user_data.get("triage_q1"), context.user_data.get("triage_q2"), value)
        db.update_user(client, user_id, stage=stage, stage_set_at=dt.datetime.now(dt.timezone.utc).isoformat(), onboarding_step="timing_am")
        await update.callback_query.edit_message_text(
            f"Based on that, {STAGE_LABELS[stage]} is where you're starting. Adjustable any time with /stage."
        )
        await _show_timing_am(update, send_new=True, context=context)
        return

    if action == "am":
        if value == "pick":
            db.update_user(client, user_id, onboarding_step="timing_am_custom")
            await update.callback_query.edit_message_text("Type the time as HH:MM, 24h (e.g. 07:30).")
            return
        db.update_user(client, user_id, am_time=value, onboarding_step="timing_pm")
        await _show_timing_pm(update)
        return

    if action == "pm":
        if value == "pick":
            db.update_user(client, user_id, onboarding_step="timing_pm_custom")
            await update.callback_query.edit_message_text("Type the time as HH:MM, 24h (e.g. 20:00).")
            return
        if value == "skip":
            db.update_user(client, user_id, pm_enabled=False, onboarding_step="timing_weekly")
        else:
            db.update_user(client, user_id, pm_time=value, pm_enabled=True, onboarding_step="timing_weekly")
        await _show_timing_weekly(update)
        return

    if action == "weekly":
        if value == "pick":
            db.update_user(client, user_id, onboarding_step="timing_weekly_custom")
            await update.callback_query.edit_message_text(
                "Type a day and time as 'Day HH:MM', e.g. 'Sunday 18:00'."
            )
            return
        day, time_ = value.split("-", 1)
        db.update_user(client, user_id, weekly_day=day, weekly_time=time_, onboarding_step="baseline")
        await _show_baseline(update)
        return

    if action == "baseline":
        db.update_user(
            client,
            user_id,
            baseline=value,
            onboarding_step="done",
            onboarding_complete=True,
        )
        row = db.get_user(client, user_id)
        am_time = row.get("am_time") or "your set time"
        text = (
            "That's setup done.\n\n"
            f"First check-in tomorrow at {am_time}.\n\n"
            "Two worth knowing now:\n"
            "/tools — when you need to settle, right now\n"
            "/pause — when you need this to stop for a while\n\n"
            "Missing days isn't failure. It's usually information."
        )
        await update.callback_query.edit_message_text(text)
        return


async def handle_onboarding_text(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> bool:
    """Free-text input during onboarding (custom time entries). Returns True
    if the message was consumed as an onboarding step."""
    step = row.get("onboarding_step")
    text = (update.message.text or "").strip()

    if step == "timing_am_custom":
        m = _TIME_RE.match(text)
        if not m:
            await update.message.reply_text("Didn't catch that — HH:MM, 24h, e.g. 07:30.")
            return True
        db.update_user(client, row["id"], am_time=text, onboarding_step="timing_pm")
        await _show_timing_pm(update)
        return True

    if step == "timing_pm_custom":
        m = _TIME_RE.match(text)
        if not m:
            await update.message.reply_text("Didn't catch that — HH:MM, 24h, e.g. 20:00.")
            return True
        db.update_user(client, row["id"], pm_time=text, pm_enabled=True, onboarding_step="timing_weekly")
        await _show_timing_weekly(update)
        return True

    if step == "timing_weekly_custom":
        bits = text.rsplit(" ", 1)
        day_ok = len(bits) == 2 and bits[0].strip().capitalize() in _WEEKDAY_NAMES
        if not day_ok or not _TIME_RE.match(bits[1]):
            await update.message.reply_text("Format: 'Day HH:MM', e.g. 'Sunday 18:00'.")
            return True
        day, time_ = bits
        db.update_user(client, row["id"], weekly_day=day.strip().capitalize(), weekly_time=time_, onboarding_step="baseline")
        await _show_baseline(update)
        return True

    return False


# --------------------------------------------------------------- steps ---

async def _show_consent(update: Update):
    text = (
        "Before we start.\n\n"
        "Your answers are stored so the bot can show you patterns over "
        "time. That's the only reason they're kept.\n\n"
        "Export everything with /mydata, delete everything with "
        "/deleteme. Deletion is immediate and total.\n\n"
        "This isn't medical care and it doesn't replace it."
    )
    kb = _kb([[("I understand", "onb:consent_ok")], [("Read the full policy", "onb:consent_policy")]])
    await _send(update, text, kb)


async def _show_locale(update: Update):
    text = "Where are you based? This only affects which support numbers I show if they're ever needed."
    kb = _kb([[("Australia", "onb:locale:AU"), ("UK", "onb:locale:UK")], [("US", "onb:locale:US"), ("Somewhere else", "onb:locale:OTHER")]])
    await update.callback_query.edit_message_text(text, reply_markup=kb)


async def show_pem(update: Update):
    """Public entry point — reused by /pem and by the §5.6/§4.3 re-screen
    triggers, not just the onboarding flow, so it must work whether the
    update is a command message or a callback query."""
    text = (
        "One question that changes how this works for you.\n\n"
        "After activity — even ordinary activity like a shower, a "
        "conversation, a short walk — do you get worse in a way that "
        "shows up hours or a day later, and lasts more than a day?"
    )
    kb = _kb(
        [
            [("Yes, that's my pattern", "onb:pem:yes")],
            [("Sometimes / not sure", "onb:pem:uncertain")],
            [("No — I get tired, but I recover with rest", "onb:pem:no")],
        ]
    )
    await _send(update, text, kb)


# Backwards-compatible alias for the internal onboarding call sites below.
_show_pem = show_pem


async def send_pem_rescreen(bot, client, user_id: int, trigger: str = "periodic_90d") -> None:
    """§5.6 re-screen, fired by scheduler.py (which has no inbound Update
    to attach to — just a bot and a user id). Sends a new message rather
    than editing one. `trigger` is persisted to revs_users.pending_pem_trigger
    so the eventual "onb:pem:<value>" callback tap — which may land long
    after this send, across a possible bot restart — logs the correct
    §5.6 audit label instead of defaulting to the wrong one."""
    db.update_user(client, user_id, pending_pem_trigger=trigger)
    text = (
        "One to re-check, since it's been a while and it changes how "
        "this works.\n\n"
        "After activity — even ordinary activity like a shower, a "
        "conversation, a short walk — do you get worse in a way that "
        "shows up hours or a day later, and lasts more than a day?"
    )
    kb = _kb(
        [
            [("Yes, that's my pattern", "onb:pem:yes")],
            [("Sometimes / not sure", "onb:pem:uncertain")],
            [("No — I get tired, but I recover with rest", "onb:pem:no")],
        ]
    )
    await bot.send_message(chat_id=user_id, text=text, reply_markup=kb)


async def _handle_pem_answer(update: Update, client, user_id: int, value: str, trigger: str):
    if value == "yes":
        db.update_user(client, user_id, pem_flag=True, pem_certainty="stated", pem_set_at=dt.datetime.now(dt.timezone.utc).isoformat())
        db.insert_pem_screen_log(client, user_id, "yes", trigger)
        text = (
            "Thanks — that matters, and it changes what this bot does.\n\n"
            "For this pattern, gradually pushing harder is documented to "
            "worsen the crash rather than build tolerance. So this bot "
            "won't suggest you do more, and it works from your baseline "
            "rather than toward a target.\n\n"
            "If you haven't already, it's worth a conversation with a "
            "clinician who knows this pattern specifically."
        )
        await update.callback_query.edit_message_text(text, reply_markup=_kb([[("Got it", "onb:pem_ack")]]))
        return
    if value == "uncertain":
        db.update_user(client, user_id, pem_flag=True, pem_certainty="precautionary", pem_set_at=dt.datetime.now(dt.timezone.utc).isoformat())
        db.insert_pem_screen_log(client, user_id, "uncertain", trigger)
        text = (
            "You're not certain, and most people aren't — there's no "
            "clean self-test for this.\n\n"
            "Because being wrong in one direction has real costs and "
            "being wrong in the other only costs time, I'll use the "
            "cautious setting. You can change it any time with /pem.\n\n"
            "If it's worth pinning down, tracking your crashes for a "
            "fortnight is the usual way, and a clinician who knows this "
            "pattern can help."
        )
        await update.callback_query.edit_message_text(text, reply_markup=_kb([[("Got it", "onb:pem_ack")]]))
        return
    # no
    db.update_user(client, user_id, pem_flag=False, pem_certainty="cleared", pem_set_at=dt.datetime.now(dt.timezone.utc).isoformat())
    db.insert_pem_screen_log(client, user_id, "no", trigger)
    if trigger == "onboarding":
        await _show_stage(update)
    else:
        await update.callback_query.edit_message_text("Updated — cleared.")


async def _show_stage(update: Update):
    text = (
        "Where are you starting?\n\n"
        "If you've done the REVS assessment, use that result. If not, "
        "pick what sounds closest — adjustable any time with /stage."
    )
    kb = _kb(
        [
            [("Recognise — still working out what's going on", "onb:stage:RECOGNISE")],
            [("Regulate — I know the pattern, I need tools", "onb:stage:REGULATE")],
            [("Rebuild — I'm stable and want to grow capacity", "onb:stage:REBUILD")],
            [("Redesign — I'm reshaping my life around what I know", "onb:stage:REDESIGN")],
            [("Not sure", "onb:stage:unsure")],
        ]
    )
    await update.callback_query.edit_message_text(text, reply_markup=kb)


async def _show_triage_q1(update: Update):
    text = (
        "Three quick ones.\n\n"
        "In a normal week, how often does your system get overwhelmed — "
        "crashed, shut down, or wound up and unable to settle?"
    )
    kb = _kb(
        [
            [("Most days", "onb:triage1:most_days"), ("A few times a week", "onb:triage1:few_times")],
            [("Now and then", "onb:triage1:now_then"), ("Rarely", "onb:triage1:rarely")],
        ]
    )
    await update.callback_query.edit_message_text(text, reply_markup=kb)


async def _show_triage_q2(update: Update):
    text = "When that happens, do you have things you can do that reliably help you settle?"
    kb = _kb(
        [
            [("No, nothing reliable", "onb:triage2:none")],
            [("One or two things", "onb:triage2:some")],
            [("Yes, a few that work", "onb:triage2:several")],
        ]
    )
    await update.callback_query.edit_message_text(text, reply_markup=kb)


async def _show_triage_q3(update: Update):
    text = "And right now — are you trying to hold steady, or trying to grow?"
    kb = _kb(
        [
            [("Hold steady", "onb:triage3:REGULATE")],
            [("Grow, carefully", "onb:triage3:REBUILD")],
            [("Neither — I'm reshaping things", "onb:triage3:REDESIGN")],
        ]
    )
    await update.callback_query.edit_message_text(text, reply_markup=kb)


def _score_triage(q1: str, q2: str, ceiling: str) -> str:
    """§1.4a scoring — floor from Q1/Q2 overrides ceiling from Q3.
    RESULT = the more conservative of floor and ceiling."""
    order = ["RECOGNISE", "REGULATE", "REBUILD", "REDESIGN"]

    floor = None
    if q1 == "most_days" or q2 == "none":
        floor = "RECOGNISE"
    elif q1 == "few_times" or q2 == "some":
        floor = "REGULATE"

    if floor is None:
        return ceiling
    if order.index(floor) < order.index(ceiling):
        return floor
    return ceiling


async def _show_timing_am(update: Update, send_new: bool = False, context=None):
    text = "When suits for the morning check-in?"
    kb = _kb(
        [
            [("Early — 7am", "onb:am:07:00"), ("Mid — 9am", "onb:am:09:00")],
            [("Late — 11am", "onb:am:11:00"), ("Pick a time", "onb:am:pick")],
        ]
    )
    if send_new:
        await update.effective_chat.send_message(text, reply_markup=kb)
    else:
        await update.callback_query.edit_message_text(text, reply_markup=kb)


async def _show_timing_pm(update: Update):
    text = "And the evening one?"
    kb = _kb(
        [
            [("6pm", "onb:pm:18:00"), ("8pm", "onb:pm:20:00"), ("9pm", "onb:pm:21:00")],
            [("Pick a time", "onb:pm:pick"), ("Skip evenings entirely", "onb:pm:skip")],
        ]
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.effective_chat.send_message(text, reply_markup=kb)


async def _show_timing_weekly(update: Update):
    text = "Weekly review — one longer one, about five minutes."
    kb = _kb(
        [
            [("Sunday evening", "onb:weekly:Sunday-18:00"), ("Monday morning", "onb:weekly:Monday-09:00")],
            [("Friday afternoon", "onb:weekly:Friday-16:00"), ("Pick", "onb:weekly:pick")],
        ]
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.effective_chat.send_message(text, reply_markup=kb)


async def _show_baseline(update: Update):
    text = (
        "Last thing. On an ordinary day — not a good one, not a bad "
        "one — roughly what fits?"
    )
    kb = _kb(
        [
            [("Rather not say", "onb:baseline:not_say")],
            [("A little", "onb:baseline:little"), ("Some", "onb:baseline:some")],
            [("A fair bit", "onb:baseline:fair_bit"), ("Most of what I need to", "onb:baseline:most")],
        ]
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.effective_chat.send_message(text, reply_markup=kb)
