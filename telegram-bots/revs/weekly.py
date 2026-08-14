"""Part 3.1 — Weekly Pattern Review. Monthly Review (§3.2) is deferred to
v2 per §8.1 pilot scope, along with everything that depends on /expand
(§4.4, also deferred) — so the REBUILD variant of Q5 degrades gracefully
here rather than referencing an expansion that can't exist yet in this
build.

Q4 (Systems) rotation: the source docs name only some of the twelve REVS
capacity systems by number (2, 3, 6, 7, 8, 9, 10, 11, 12 appear scattered
across REVS_Telegram_Worksheet_Mapping.md; the full canonical 1-12 list
lives in a framework doc — REG-001 or similar — that wasn't provided with
these two files). SYSTEM_NAMES below has only the confirmed ones;
unconfirmed numbers render as "System N" rather than an invented name.
Needs the real registry wired in before this ships to a real user — noted
in README.md's launch blockers.
"""

from __future__ import annotations

import datetime as dt

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import db

SYSTEM_NAMES = {
    3: "Recovery Cycles",
    6: "Emotional Regulation",
    8: "Work & Productivity",
    9: "Cognition & Executive Function",
    11: "Masking & Authenticity",
    12: "Purpose & Meaning",
}
_ALL_SYSTEM_NUMBERS = list(range(1, 13))

RECOGNISE_OBSERVATIONS = [
    "Notice what time of day you're most settled.",
    "Notice what tends to come just before a crash.",
    "Notice which people leave you with more energy than you started with.",
    "Notice what your body does first when it's had enough.",
]


def _kb(rows):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=data) for label, data in row] for row in rows]
    )


def _week_start(today: dt.date) -> dt.date:
    return today - dt.timedelta(days=today.weekday())  # Monday


def _system_label(n: int) -> str:
    return SYSTEM_NAMES.get(n, f"System {n}")


def _rotation_for(review_count: int) -> tuple[int, int]:
    a = _ALL_SYSTEM_NUMBERS[(review_count * 2) % 12]
    b = _ALL_SYSTEM_NUMBERS[(review_count * 2 + 1) % 12]
    return a, b


def _pattern_line(checkins: list[dict], prev_matched: int | None, prev_logged: int | None) -> str:
    am = [c for c in checkins if c["period"] == "am" and c.get("state") != "skip"]
    pm = [c for c in checkins if c["period"] == "pm" and c.get("state") != "skip"]
    logged = len(am)
    steady = sum(1 for c in am if c["state"] == "steady")
    low = sum(1 for c in am if c["state"] == "low")
    depleted = sum(1 for c in am if c["state"] == "depleted")
    wound = sum(1 for c in am if c["state"] == "wound")
    under_count = sum(1 for c in pm if c["state"] == "under")
    over_count = sum(1 for c in pm if c["state"] == "over")
    matched = sum(1 for c in pm if c["state"] == "about")

    if steady == 7 and under_count >= 5:
        line = (
            "Seven steady days with load well under — worth a look at "
            "whether that's real ease or the check-in smoothing things out."
        )
    elif over_count >= 3:
        line = "Load ran past the envelope more often than not this week."
    elif logged < 3:
        line = "Not much logged this week — no problem. Here's what there is."
    elif steady >= 5 and matched >= 4:
        line = "That's a rhythm holding."
    elif prev_matched is not None and matched > prev_matched:
        line = "Steadier than last week."
    elif prev_matched is not None and matched < prev_matched:
        line = "Less steady than last week. Worth a look at what changed."
    else:
        line = "Mixed week. Nothing standing out either way."

    return line, steady, low, depleted, wound, matched, logged


async def send_weekly_review(bot, client, user: dict) -> None:
    today = dt.datetime.now(dt.timezone.utc).date()
    week_start = _week_start(today)
    week_end = week_start + dt.timedelta(days=6)
    checkins = db.checkins_between(client, user["id"], week_start, week_end)

    prev_reviews = db.recent_weekly_reviews(client, user["id"], limit=1)
    # prev matched/logged not persisted on the review row in this schema;
    # trend rows 5/6 fall back to "else" (row 7) until a future migration
    # adds a snapshot column — acceptable degradation, not a safety gap.
    line, steady, low, depleted, wound, matched, logged = _pattern_line(checkins, None, None)

    text = (
        "Week in review.\n\n"
        f"Your seven days: {steady} steady · {low} low · {depleted} depleted · {wound} wound up\n\n"
        f"Load sat right on {matched} of {logged} days.\n\n"
        f"{line}"
    )
    kb = _kb([[("Keep going", "wk:open:keep"), ("Just the numbers, thanks", "wk:open:numbers")]])
    await bot.send_message(chat_id=user["id"], text=text, reply_markup=kb)


async def handle_weekly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    section, value = parts[1], parts[2] if len(parts) > 2 else None
    user_id = row["id"]

    if section == "open":
        if value == "numbers":
            _finalize(context)
            db.update_user(client, user_id, weekly_skip_count=0)
            await query.edit_message_text("That's the week. Next check-in tomorrow.")
            return
        context.user_data["weekly_answers"] = {}
        await query.edit_message_text(
            "What worked this week? Anything that held, or went better than expected.",
            reply_markup=_kb([[("Skip", "wk:q1skip:")]]),
        )
        context.user_data["awaiting_weekly_text"] = "what_held"
        return

    if section == "q1skip":
        await _ask_q2(update, context)
        return

    if section == "q2skip":
        context.user_data["awaiting_weekly_text"] = None
        await _ask_q3(update)
        return

    if section == "q3":
        context.user_data.setdefault("weekly_answers", {})["why_cause"] = value
        await _ask_q4(update, context, client, row)
        return

    if section == "sys1":
        context.user_data.setdefault("weekly_answers", {})["system_1_rating"] = value
        sys2 = context.user_data.get("weekly_sys2_label", "the other system")
        await query.edit_message_text(
            f"And {sys2}?",
            reply_markup=_kb([[("Better", "wk:sys2:better"), ("Same", "wk:sys2:same")], [("Worse", "wk:sys2:worse"), ("Skip", "wk:sys2:skip")]]),
        )
        return

    if section == "sys2":
        context.user_data.setdefault("weekly_answers", {})["system_2_rating"] = value
        await _ask_q5(update, context, row)
        return

    if section == "q5":
        await _finish_q5(update, context, client, row, value)
        return


async def _ask_q2(update: Update, context=None):
    await update.callback_query.edit_message_text(
        "And what didn't go the way you planned?", reply_markup=_kb([[("Skip", "wk:q2skip:")]])
    )
    if context is not None:
        context.user_data["awaiting_weekly_text"] = "what_didnt"


async def _ask_q3(update: Update):
    text = "Take the thing that didn't go to plan — do you know what was underneath it?"
    kb = _kb(
        [
            [("Not enough recovery", "wk:q3:not_enough_recovery"), ("Pushed past a limit", "wk:q3:pushed_limit")],
            [("Something outside my control", "wk:q3:outside_control"), ("Sensory / environment", "wk:q3:sensory")],
            [("Emotional or social load", "wk:q3:emotional"), ("Poor sleep", "wk:q3:sleep")],
            [("No idea", "wk:q3:no_idea")],
        ]
    )
    await update.callback_query.edit_message_text(text, reply_markup=kb)


async def _ask_q4(update: Update, context, client, row: dict):
    reviews = db.recent_weekly_reviews(client, row["id"], limit=100)
    sys1, sys2 = _rotation_for(len(reviews))
    label1, label2 = _system_label(sys1), _system_label(sys2)
    context.user_data["weekly_sys2_label"] = label2
    context.user_data.setdefault("weekly_answers", {})["system_1"] = label1
    context.user_data["weekly_answers"]["system_2"] = label2
    await update.callback_query.edit_message_text(
        f"Quick one on two of your systems this week.\n{label1} — how did that sit?",
        reply_markup=_kb([[("Better", "wk:sys1:better"), ("Same", "wk:sys1:same")], [("Worse", "wk:sys1:worse"), ("Skip", "wk:sys1:skip")]]),
    )


async def _ask_q5(update: Update, context, row: dict):
    stage = row.get("stage")
    if stage == "RECOGNISE":
        prompt = RECOGNISE_OBSERVATIONS[hash(row["id"]) % len(RECOGNISE_OBSERVATIONS)]
        await update.callback_query.edit_message_text(
            "Nothing to set for next week. Recognise is about seeing the "
            f"pattern, not changing it yet.\n\nOne thing to watch, if you "
            f"want one:\n{prompt}",
            reply_markup=_kb([[("Ok", "wk:q5:ack")]]),
        )
    elif stage == "REGULATE":
        await update.callback_query.edit_message_text(
            "One thing for next week — not a goal, a rhythm.\nWhat's the "
            "one recovery point you'll protect?",
            reply_markup=_kb([[("Skip", "wk:q5:skip")]]),
        )
        context.user_data["awaiting_weekly_text"] = "next_week"
    elif stage == "REBUILD":
        # /expand is deferred to v2 — no active expansion can exist yet.
        await update.callback_query.edit_message_text(
            "No micro-expansion running yet — that's a Rebuild feature "
            "landing in a later update. For now: what's the one recovery "
            "point you'll protect next week?",
            reply_markup=_kb([[("Skip", "wk:q5:skip")]]),
        )
        context.user_data["awaiting_weekly_text"] = "next_week"
    else:  # REDESIGN
        await update.callback_query.edit_message_text(
            "Anything structural coming up next week — a decision, a "
            "boundary, a conversation you've been holding off?",
            reply_markup=_kb([[("Skip", "wk:q5:skip")]]),
        )
        context.user_data["awaiting_weekly_text"] = "next_week"


async def _finish_q5(update: Update, context, client, row: dict, value: str):
    if value != "skip":
        pass  # "ack" for RECOGNISE — nothing to store
    await _save_and_close(update, context, client, row)


async def _save_and_close(update: Update, context, client, row: dict):
    context.user_data["awaiting_weekly_text"] = None
    answers = context.user_data.pop("weekly_answers", {})
    today = dt.datetime.now(dt.timezone.utc).date()
    db.upsert_weekly_review(client, row["id"], _week_start(today), **answers)
    db.update_user(client, row["id"], weekly_skip_count=0)
    am_time = row.get("am_time") or "your usual time"
    await update.callback_query.edit_message_text(f"That's the week. Next check-in {am_time} tomorrow.")


def _finalize(context):
    context.user_data.pop("weekly_answers", None)
    context.user_data["awaiting_weekly_text"] = None


async def handle_weekly_text(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> bool:
    field = context.user_data.get("awaiting_weekly_text")
    if not field:
        return False
    text = (update.message.text or "").strip()
    answers = context.user_data.setdefault("weekly_answers", {})

    if field == "what_held":
        answers["what_held"] = text
        await _ask_q2_from_message(update, context)
        return True
    if field == "what_didnt":
        answers["what_didnt"] = text
        context.user_data["awaiting_weekly_text"] = None
        await _ask_q3_from_message(update)
        return True
    if field == "next_week":
        answers["next_week"] = text
        await update.message.reply_text("Noted.")
        # Persist directly since there's no callback query to drive _save_and_close.
        today = dt.datetime.now(dt.timezone.utc).date()
        db.upsert_weekly_review(client, row["id"], _week_start(today), **context.user_data.pop("weekly_answers", {}))
        db.update_user(client, row["id"], weekly_skip_count=0)
        context.user_data["awaiting_weekly_text"] = None
        am_time = row.get("am_time") or "your usual time"
        await update.message.reply_text(f"That's the week. Next check-in {am_time} tomorrow.")
        return True
    return False


async def _ask_q2_from_message(update: Update, context):
    await update.message.reply_text(
        "And what didn't go the way you planned?", reply_markup=_kb([[("Skip", "wk:q2skip:")]])
    )
    context.user_data["awaiting_weekly_text"] = "what_didnt"


async def _ask_q3_from_message(update: Update):
    text = "Take the thing that didn't go to plan — do you know what was underneath it?"
    kb = _kb(
        [
            [("Not enough recovery", "wk:q3:not_enough_recovery"), ("Pushed past a limit", "wk:q3:pushed_limit")],
            [("Something outside my control", "wk:q3:outside_control"), ("Sensory / environment", "wk:q3:sensory")],
            [("Emotional or social load", "wk:q3:emotional"), ("Poor sleep", "wk:q3:sleep")],
            [("No idea", "wk:q3:no_idea")],
        ]
    )
    await update.message.reply_text(text, reply_markup=kb)
