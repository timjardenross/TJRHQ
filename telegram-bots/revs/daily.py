"""Part 2 — Daily. §2.1 Morning Capacity Check-in, §2.2 Evening Load
Reflection, §2.3 optional What Held add-on. Plus the two safety triggers
that fire directly off a check-in write: §5.1 downward trend and §5.4b
non-text crisis trigger (event-driven here rather than polled by the
scheduler, since both are naturally "check right after this insert").
"""

from __future__ import annotations

import datetime as dt

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import commands
import db
from copy_bank import crisis_nontext
from safety import crisis_line_short, pem_copy


def _kb(rows):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=data) for label, data in row] for row in rows]
    )


def _today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


# ------------------------------------------------------------------ AM ---

async def send_am_checkin(bot, client, user: dict) -> None:
    text = "Morning. Where's your system today?"
    kb = _kb(
        [
            [("Steady", "am:root:steady"), ("A bit low", "am:root:low")],
            [("Depleted", "am:root:depleted"), ("Wound up", "am:root:wound")],
            [("Skip", "am:root:skip")],
        ]
    )
    await bot.send_message(chat_id=user["id"], text=text, reply_markup=kb)


async def handle_am_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    query = update.callback_query
    await query.answer()
    user_id = row["id"]
    parts = query.data.split(":")  # am:<section>:<value>
    section, value = parts[1], parts[2]
    today = _today()

    if section == "root":
        if value == "skip":
            db.upsert_checkin(client, user_id, today, "am", state="skip")
            return  # §2.1 skip: no reply sent
        db.upsert_checkin(client, user_id, today, "am", state=value)
        await _check_downward_trend(update, client, row)
        await _check_nontext_crisis(update, client, row)

        if value == "steady":
            await query.edit_message_text(
                "Good. What's the shape of today?",
                reply_markup=_kb([[("Light", "am:shape:light"), ("Normal", "am:shape:normal")], [("Heavy", "am:shape:heavy"), ("Unknown", "am:shape:unknown")]]),
            )
        elif value == "low":
            await query.edit_message_text(
                "Okay. Anything you can take off today?",
                reply_markup=_kb(
                    [
                        [("Already have", "am:low:already"), ("I'll look", "am:low:look")],
                        [("Nothing to take off", "am:low:nothing"), ("Not today", "am:low:nottoday")],
                    ]
                ),
            )
        elif value == "depleted":
            await query.edit_message_text(
                "Then today is a recovery day, not a catch-up day.\n\nNothing needed from you here.",
                reply_markup=_kb([[("Regulation tools", "am:depleted:tools"), ("Just leave it", "am:depleted:leave")]]),
            )
        elif value == "wound":
            await query.edit_message_text(
                "Wound up, not flat. Settling first tends to work better.",
                reply_markup=_kb([[("My tools", "am:wound:tools"), ("Not now", "am:wound:notnow")]]),
            )
        return

    if section == "shape":
        db.upsert_checkin(client, user_id, today, "am", shape=value)
        if value in ("light", "normal"):
            await query.edit_message_text("Noted.")
        elif value == "unknown":
            await query.edit_message_text("Fair enough. I'll check in tonight.")
        elif value == "heavy":
            heavy_label = pem_copy("Noted. Where's your recovery going to sit in that?",
                                    "Noted. Where's your recovery going to sit in that?", row.get("pem_flag") or False)
            await query.edit_message_text(
                heavy_label,
                reply_markup=_kb(
                    [
                        [("It's already scheduled", "am:heavy:sched")],
                        [("I'll find it", "am:heavy:find")],
                        [("There isn't any", "am:heavy:none")],
                    ]
                ),
            )
        return

    if section == "heavy":
        if value == "sched":
            await query.edit_message_text("Good.")
        elif value == "find":
            await query.edit_message_text("Noted.")
        elif value == "none":
            recovery_cost_line = pem_copy(
                "For a lot of people that combination turns up a couple of days later — worth knowing, not a forecast.",
                "With this pattern the cost usually lands a day or two later.",
                row.get("pem_flag") or False,
            )
            text = (
                f"Worth flagging. {recovery_cost_line}\n\n"
                "If any recovery turns out to be findable it'll pay for itself. If not, that's the day."
            )
            await query.edit_message_text(
                text, reply_markup=_kb([[("Noted", "am:heavynote:ok"), ("Not possible today", "am:heavynote:ok")]])
            )
        return

    if section == "heavynote":
        # ⚠ Do not push twice — one flag, then let it go.
        await query.edit_message_text("Fair enough. I'll check in tonight.")
        return

    if section == "low":
        if value == "already":
            await query.edit_message_text("Good.")
        elif value == "look":
            await query.edit_message_text("Noted.")
        elif value == "nottoday":
            await query.edit_message_text("Fair enough.")
        elif value == "nothing":
            text = (
                "Understood — sometimes there isn't anything. Then the useful "
                "thing is just knowing today is expensive.\n\n/tools is there if you want it."
            )
            await query.edit_message_text(text, reply_markup=_kb([[("Ok", "am:lownote:ok")]]))
        return

    if section == "lownote":
        await query.edit_message_text("Ok.")
        return

    if section == "depleted":
        # ⚠ No follow-up questions on a depleted morning — check-in ends here.
        if value == "tools":
            await commands.send_tools(update, context, client, row)
        else:
            await query.edit_message_text("Nothing needed from you here.")
        return

    if section == "wound":
        if value == "tools":
            await commands.send_tools(update, context, client, row)
        else:
            await query.edit_message_text("Fair enough. I'm here if that changes.")
        return


async def _check_downward_trend(update: Update, client, row: dict) -> None:
    """§5.1 — three consecutive depleted/wound_up, fires once per episode."""
    user_id = row["id"]
    now = dt.datetime.now(dt.timezone.utc)
    suppressed_until = row.get("downward_trend_suppressed_until")
    if suppressed_until and suppressed_until > now.isoformat():
        return

    recent = db.recent_checkins(client, user_id, "am", limit=3)
    if len(recent) < 3:
        return
    if not all(c.get("state") in ("depleted", "wound") for c in recent):
        return

    # "No repeat until two steady days" — if the alert already fired and no
    # two-steady-day reset has happened since, skip.
    alert_at = row.get("downward_trend_alert_at")
    if alert_at:
        since = db.recent_checkins(client, user_id, "am", limit=10)
        after_alert = [c for c in since if c["created_at"] > alert_at]
        steady_run = 0
        for c in sorted(after_alert, key=lambda c: c["checkin_date"]):
            if c.get("state") == "steady":
                steady_run += 1
            else:
                steady_run = 0
        if steady_run < 2:
            return

    text = "Three days running now.\n\nAnything that can come off in the next couple of days?"
    kb = _kb(
        [
            [("Already reducing", "trend:already"), ("I'll look", "trend:look")],
            [("Nothing can come off", "trend:nothing"), ("Leave me be", "trend:leaveme")],
        ]
    )
    db.update_user(client, user_id, downward_trend_alert_at=now.isoformat())
    await update.effective_chat.send_message(text, reply_markup=kb)


async def handle_trend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    user_id = row["id"]
    now = dt.datetime.now(dt.timezone.utc)

    if value == "already":
        await query.edit_message_text("Good.")
    elif value == "look":
        await query.edit_message_text("Noted.")
    elif value == "leaveme":
        db.update_user(client, user_id, downward_trend_suppressed_until=(now + dt.timedelta(hours=72)).isoformat())
        await query.edit_message_text("Ok.")
        return
    elif value == "nothing":
        await query.edit_message_text("Understood — sometimes there genuinely isn't.\n\n/tools is there if you need it.")

    db.update_user(client, user_id, paused_until=None)  # auto-pause expansion — no /expand in pilot, no-op placeholder


async def _check_nontext_crisis(update: Update, client, row: dict) -> None:
    """§5.4b — five consecutive depleted, or /setback twice in 14 days
    (the /setback half of this check lives in commands.py, called from
    there directly). This half covers the five-consecutive-depleted path."""
    user_id = row["id"]
    if db.is_nontext_crisis_suppressed(client, user_id):
        return
    recent = db.recent_checkins(client, user_id, "am", limit=5)
    if len(recent) < 5 or not all(c.get("state") == "depleted" for c in recent):
        return
    await fire_nontext_crisis(update, client, row)


async def fire_nontext_crisis(update: Update, client, row: dict) -> None:
    user_id = row["id"]
    recontact_due = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=24)
    db.insert_crisis_event(client, user_id, "nontext", recontact_due)
    text = crisis_nontext(crisis_line_short(row.get("locale")))
    kb = _kb([[("Ok", "crisis:nt_ok"), ("Don't show me this again", "crisis:nt_suppress")]])
    await update.effective_chat.send_message(text, reply_markup=kb)

    from escalate import notify_captain

    await notify_captain(
        user_id=user_id,
        first_name=row.get("first_name"),
        trigger_type="nontext",
        locale=row.get("locale"),
        detail="5 consecutive depleted check-ins, or 2 setbacks logged within 14 days",
        triggered_text=None,  # no free text involved in this trigger path
    )


async def handle_crisis_nt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    if value == "nt_suppress":
        db.set_dont_show_again(client, row["id"], dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=90))
        await query.edit_message_text("Ok — won't show that again for a while.")
    else:
        await query.edit_message_text("Ok.")


# ------------------------------------------------------------------ PM ---

async def send_pm_checkin(bot, client, user: dict) -> None:
    today = _today()
    am = db.get_checkin(client, user["id"], today, "am")
    if am and am.get("state") == "depleted":
        return  # §2.2: skipped entirely if the morning returned depleted
    text = "Evening. How did today's load sit against what you had?"
    kb = _kb(
        [
            [("Under it", "pm:root:under"), ("About right", "pm:root:about")],
            [("Over it", "pm:root:over"), ("No idea", "pm:root:noidea")],
        ]
    )
    await bot.send_message(chat_id=user["id"], text=text, reply_markup=kb)


async def handle_pm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    query = update.callback_query
    await query.answer()
    user_id = row["id"]
    parts = query.data.split(":")
    section, value = parts[1], parts[2] if len(parts) > 2 else None
    today = _today()

    if section == "root":
        db.upsert_checkin(client, user_id, today, "pm", state=value)
        if value == "about":
            context.user_data["awaiting_pm_note"] = True
            await query.edit_message_text(
                "That's the one that matters. Anything that made it work?",
                reply_markup=_kb([[("Skip", "pm:noteskip:")]]),
            )
        elif value == "over":
            await query.edit_message_text(
                "What tipped it?",
                reply_markup=_kb(
                    [
                        [("Too much on", "pm:cause:too_much"), ("Something unexpected", "pm:cause:unexpected")],
                        [("Didn't stop when I meant to", "pm:cause:didnt_stop")],
                        [("Sensory / environment", "pm:cause:sensory"), ("Emotional load", "pm:cause:emotional")],
                        [("Not sure", "pm:cause:notsure")],
                    ]
                ),
            )
        elif value == "under":
            under_text = pem_copy(
                "Noted. Under isn't a problem — it's often what makes the rest of the week possible.",
                "Noted. Staying under is the work, not a shortfall.",
                row.get("pem_flag") or False,
            )
            await query.edit_message_text(under_text, reply_markup=_kb([[("Ok", "pm:underack:")]]))
        elif value == "noidea":
            await query.edit_message_text("That's fine. Fog is data too.")
        return

    if section == "cause":
        db.upsert_checkin(client, user_id, today, "pm", cause=value)
        await query.edit_message_text(
            "Logged. Tomorrow's worth treating as lighter than usual.",
            reply_markup=_kb([[("Noted", "pm:causeack:")]]),
        )
        return

    if section in ("noteskip", "underack", "causeack"):
        context.user_data.pop("awaiting_pm_note", None)
        if section == "noteskip":
            await query.edit_message_text("Noted.")
        elif section == "underack":
            await query.edit_message_text("Ok.")
        else:
            await query.edit_message_text("Noted.")
        return


async def handle_pm_note_text(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> bool:
    """§2.2 'About right' free-text follow-up, and §2.3 What Held add-on."""
    if not context.user_data.get("awaiting_pm_note"):
        return False
    context.user_data.pop("awaiting_pm_note", None)
    text = (update.message.text or "").strip()
    from safety import screen_for_storage

    non_replayable = screen_for_storage(text)
    db.upsert_checkin(client, row["id"], _today(), "pm", note=text, note_non_replayable=non_replayable)
    await update.message.reply_text("Noted.")
    return True
