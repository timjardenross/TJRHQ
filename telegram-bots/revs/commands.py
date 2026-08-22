"""Part 4 — On-demand commands. Pilot scope only (§8.1): /tools /pace
/setback /pem /stage /mydata /deleteme /help /quiet /pause /resume
/whatheld. /expand (§4.4) and its gates are deferred to v2 per the doc —
there is no `/expand` handler here at all, not even a stub, so it falls
through to Telegram's "unknown command" default rather than silently
half-working.
"""

from __future__ import annotations

import datetime as dt
import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import db
import onboarding
from copy_bank import APPROACH_LABELS, DEFAULT_REGULATION, STAGE_LABELS
from safety import screen_for_storage


def _kb(rows):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=data) for label, data in row] for row in rows]
    )


async def _reply(update: Update, text: str, markup=None):
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)


# --------------------------------------------------------------- /tools ---

async def cmd_tools(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    await send_tools(update, context, client, row)


async def send_tools(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    """⚠ Zero questions on the happy path — a dysregulated user can tap,
    not compose. This is the entry point; setup (if no tools stored yet
    and the user is REGULATE+) is offered but never forced."""
    tools = db.get_tools(client, row["id"])
    if not tools:
        stage = row.get("stage")
        if stage in ("REGULATE", "REBUILD", "REDESIGN"):
            await _reply(
                update,
                "Let's set your three.\n\n"
                "There are seven ways to regulate a nervous system. Most "
                "people find three or four that work for them — and which "
                "three is very individual.",
                _kb([[("Walk me through them", "tools:setup:walk"), ("I already know mine", "tools:setup:know")]]),
            )
            return
        # Pre-REGULATE — always the seven defaults, never a bare category button.
        await _reply(update, "Pick one:", _kb(_approach_rows("tools:approach")))
        return

    rows = [[(t["approach"] and _short(t) or "…", f"tools:pick:{t['slot']}")] for t in tools]
    rows.append([("Something else", "tools:other")])
    lines = [_short(t) for t in tools]
    await _reply(update, "\n".join(lines), _kb(rows))


def _short(tool: dict) -> str:
    return APPROACH_LABELS.get(tool["approach"], tool["approach"])


def _approach_rows(prefix: str):
    items = list(APPROACH_LABELS.items())
    return [[(items[i][1], f"{prefix}:{items[i][0]}")] for i in range(len(items))]


async def handle_tools_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    section = parts[1]
    value = parts[2] if len(parts) > 2 else None
    user_id = row["id"]

    if section == "setup":
        context.user_data["tools_setup"] = {"mode": value, "slot": 1, "picked": []}
        await _tools_setup_pick_approach(update, context)
        return

    if section == "setup_pick":
        setup = context.user_data.get("tools_setup") or {}
        setup["current_approach"] = value
        context.user_data["tools_setup"] = setup
        await query.edit_message_text(f"Write your own instruction for {APPROACH_LABELS[value]}, in your own words.")
        context.user_data["awaiting_tool_instruction"] = True
        return

    if section == "pick":
        slot = int(value)
        tools = {t["slot"]: t for t in db.get_tools(client, user_id)}
        tool = tools.get(slot)
        if not tool:
            await query.edit_message_text("That one isn't set yet — try /tools again.")
            return
        await query.edit_message_text(
            tool["instruction"], reply_markup=_kb([[("Done", f"tools:done:{slot}"), ("Didn't work", f"tools:retry:{slot}")]])
        )
        return

    if section == "done":
        await query.edit_message_text("Good.")
        return

    if section == "retry":
        slot = int(value)
        tools = {t["slot"]: t for t in db.get_tools(client, user_id)}
        others = [t for s, t in tools.items() if s != slot]
        rows = [[(_short(t), f"tools:pick:{t['slot']}")] for t in others]
        rows.append([("Leave it", "tools:leave:")])
        await query.edit_message_text("Try another, or leave it — both fine.", reply_markup=_kb(rows))
        return

    if section == "leave":
        await query.edit_message_text("Ok.")
        return

    if section == "other":
        await query.edit_message_text("Pick one:", reply_markup=_kb(_approach_rows("tools:approach")))
        return

    if section == "approach":
        instruction = DEFAULT_REGULATION.get(value, "Take a slow breath and let your shoulders drop.")
        await query.edit_message_text(instruction, reply_markup=_kb([[("Done", "tools:done:0")]]))
        return


async def _tools_setup_pick_approach(update: Update, context):
    setup = context.user_data["tools_setup"]
    picked = setup.get("picked", [])
    remaining = [a for a in APPROACH_LABELS if a not in picked]
    rows = [[(APPROACH_LABELS[a], f"tools:setup_pick:{a}")] for a in remaining]
    slot = setup.get("slot", 1)
    await update.callback_query.edit_message_text(f"Pick approach {slot} of 3:", reply_markup=_kb(rows))


async def handle_tool_instruction_text(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> bool:
    if not context.user_data.get("awaiting_tool_instruction"):
        return False
    context.user_data.pop("awaiting_tool_instruction", None)
    setup = context.user_data.get("tools_setup") or {}
    approach = setup.get("current_approach")
    text = (update.message.text or "").strip()
    non_replayable = screen_for_storage(text)  # §5.7 storage-time screening
    slot = setup.get("slot", 1)
    db.upsert_tool(client, row["id"], slot, approach, text, non_replayable)
    setup["picked"] = setup.get("picked", []) + [approach]
    setup["slot"] = slot + 1
    context.user_data["tools_setup"] = setup

    if slot >= 3:
        context.user_data.pop("tools_setup", None)
        await update.message.reply_text("Your three are set. /tools any time you need them.")
        return True

    remaining = [a for a in APPROACH_LABELS if a not in setup["picked"]]
    kb = _kb([[(APPROACH_LABELS[a], f"tools:setup_pick:{a}")] for a in remaining])
    await update.message.reply_text(f"Set. Pick approach {slot + 1} of 3:", reply_markup=kb)
    return True


# ---------------------------------------------------------------- /pace ---

async def cmd_pace(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    context.user_data["pace_setup"] = True
    await update.message.reply_text(
        "Two questions to find your pacing window.\n\n"
        "When you're doing something — work, a task, a conversation — "
        "roughly how long before you start to feel it?",
        reply_markup=_kb(
            [
                [("15 min", "pace:w:15 min"), ("30 min", "pace:w:30 min"), ("45 min", "pace:w:45 min")],
                [("An hour", "pace:w:an hour"), ("Longer", "pace:w:longer"), ("Varies a lot", "pace:w:varies a lot")],
            ]
        ),
    )


async def handle_pace_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    query = update.callback_query
    await query.answer()
    value = query.data.split(":", 2)[2]
    context.user_data["pace_window"] = value
    context.user_data["awaiting_recovery_window"] = True
    await query.edit_message_text("And what resets you, and for how long?")


async def handle_recovery_window_text(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> bool:
    if not context.user_data.get("awaiting_recovery_window"):
        return False
    context.user_data.pop("awaiting_recovery_window", None)
    recovery = (update.message.text or "").strip()
    activity = context.user_data.pop("pace_window", "your usual window")
    db.update_user(client, row["id"], activity_window=activity, recovery_window=recovery)
    await update.message.reply_text(
        f"Set: about {activity} on, {recovery} to reset.\n\n"
        "The ratio matters more than the numbers. Adjust any time with /pace."
    )
    return True


# ------------------------------------------------------------- /setback ---

async def cmd_setback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    due = now + dt.timedelta(hours=72)
    db.insert_setback(client, row["id"], due)

    # §5.4b half: /setback twice within 14 days.
    if db.recent_setback_count(client, row["id"], 14) >= 2:
        import daily  # lazy: daily.py imports commands.py at module load
        await daily.fire_nontext_crisis(update, client, row)

    text = (
        "Okay. Recovery first — the working out can wait.\n\n"
        "For now: nothing on, no catching up, no analysing what went "
        "wrong. A setback is information about your limits, not a "
        "failure of effort."
    )
    await update.message.reply_text(
        text,
        reply_markup=_kb(
            [[("Regulation tools", "setback:tools"), ("Pause the check-ins", "setback:pause"), ("Just noted", "setback:noted")]]
        ),
    )


async def handle_setback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    if value == "tools":
        await send_tools(update, context, client, row)
    elif value == "pause":
        await cmd_pause(update, context, client, row)
    else:
        await query.edit_message_text("Noted.")


# --------------------------------------------------------- setback recall

async def send_setback_reflection_prompt(bot, client, setback: dict) -> None:
    text = "A few days on from that setback. Up for looking at it?"
    kb = _kb([[("Yes", f"sbref:{setback['id']}:yes"), ("Not yet", f"sbref:{setback['id']}:notyet"), ("Leave it", f"sbref:{setback['id']}:leave")]])
    await bot.send_message(chat_id=setback["user_id"], text=text, reply_markup=kb)


async def handle_setback_reflection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    query = update.callback_query
    await query.answer()
    _, setback_id, value = query.data.split(":")
    setback_id = int(setback_id)

    if value == "leave":
        db.update_setback(client, setback_id, reflection_status="declined")
        await query.edit_message_text("Ok.")
        return
    if value == "notyet":
        due = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=48)
        db.update_setback(client, setback_id, reflection_due_at=due.isoformat())
        await query.edit_message_text("No problem — I'll check again in a couple of days.")
        return

    await query.edit_message_text(
        "What was happening in the days before it?",
        reply_markup=_kb(
            [
                [("More on than usual", f"sbcause:{setback_id}:more_on"), ("Something unexpected", f"sbcause:{setback_id}:unexpected")],
                [("Slipped out of pacing", f"sbcause:{setback_id}:pacing")],
                [("Sensory or environment", f"sbcause:{setback_id}:sensory"), ("Emotional or social load", f"sbcause:{setback_id}:emotional")],
                [("Nothing obvious", f"sbcause:{setback_id}:nothing")],
            ]
        ),
    )


async def handle_setback_cause_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    query = update.callback_query
    await query.answer()
    _, setback_id, value = query.data.split(":")
    setback_id = int(setback_id)
    db.update_setback(client, setback_id, precursor=value)

    if value == "nothing" and row.get("pem_flag") is False:
        # §5.6 re-screen trigger: setback reflection returned "nothing
        # obvious" with a stored pem_flag=false — the dangerous direction
        # for a stale flag, so re-ask rather than trust it.
        db.update_user(client, row["id"], pending_pem_trigger="setback_followup")
        await onboarding.show_pem(update)
        return

    await query.edit_message_text(
        "Looking back — was there a point where you could see it coming?",
        reply_markup=_kb(
            [
                [("Yes, and I kept going", f"sbwarn:{setback_id}:kept_going")],
                [("Yes, too late", f"sbwarn:{setback_id}:too_late")],
                [("No warning at all", f"sbwarn:{setback_id}:none")],
                [("Not sure", f"sbwarn:{setback_id}:notsure")],
            ]
        ),
    )


async def handle_setback_warning_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    query = update.callback_query
    await query.answer()
    _, setback_id, value = query.data.split(":")
    setback_id = int(setback_id)
    db.update_setback(client, setback_id, saw_it_coming=value)

    if value == "kept_going":
        context.user_data["awaiting_setback_signal"] = setback_id
        await query.edit_message_text(
            "That's worth having. Seeing it is the hard part, and acting on "
            "it isn't always available.\n\nWhat was the signal?",
            reply_markup=_kb([[("Skip", f"sbsig:{setback_id}:skip")]]),
        )
        return
    if value == "none" and row.get("pem_flag"):
        await query.edit_message_text(
            "That's common with this pattern — the delay means there's "
            "often no usable warning at all. Not a cue you missed.",
            reply_markup=_kb([[("Ok", "sbdone:")]]),
        )
        db.update_setback(client, setback_id, reflection_status="done")
        return
    if value == "too_late":
        await query.edit_message_text("Noted. Late is still information.")
    else:
        await query.edit_message_text("Fair enough.")
    db.update_setback(client, setback_id, reflection_status="done")


async def handle_setback_signal_text(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> bool:
    setback_id = context.user_data.get("awaiting_setback_signal")
    if not setback_id:
        return False
    context.user_data.pop("awaiting_setback_signal", None)
    text = (update.message.text or "").strip()
    non_replayable = screen_for_storage(text)  # §5.7
    db.update_setback(client, setback_id, warning_signal=text, warning_non_replayable=non_replayable, reflection_status="done")
    await update.message.reply_text("Noted.")
    return True


# --------------------------------------------------------------- admin ---

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    await update.message.reply_text(
        "/tools — regulation shortlist, right now\n"
        "/pace — set your activity/recovery windows\n"
        "/setback — after a crash, recovery first\n"
        "/pem — re-check the PEM screen\n"
        "/stage — see or change your stage\n"
        "/mydata — export everything, sent as a file\n"
        "/deleteme — delete everything, immediate and total\n"
        "/quiet — mute 24h, no questions asked\n"
        "/pause — stop check-ins until you /resume\n"
        "/resume — turn check-ins back on\n"
        "/whatheld — toggle the optional evening add-on"
    )


async def cmd_pem(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    db.update_user(client, row["id"], pending_pem_trigger="user_command")
    await onboarding.show_pem(update)


async def cmd_stage(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    current = row.get("stage")
    label = STAGE_LABELS.get(current, "not set")
    await update.message.reply_text(
        f"Current stage: {label}. Change it?",
        reply_markup=_kb(
            [
                [(STAGE_LABELS["RECOGNISE"], "setstage:RECOGNISE"), (STAGE_LABELS["REGULATE"], "setstage:REGULATE")],
                [(STAGE_LABELS["REBUILD"], "setstage:REBUILD"), (STAGE_LABELS["REDESIGN"], "setstage:REDESIGN")],
                [("Leave as is", "setstage:keep")],
            ]
        ),
    )


async def handle_setstage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    if value == "keep":
        await query.edit_message_text("Left as is.")
        return
    db.update_user(client, row["id"], stage=value, stage_set_at=dt.datetime.now(dt.timezone.utc).isoformat())
    await query.edit_message_text(f"Stage set to {STAGE_LABELS[value]}.")


async def cmd_mydata(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    user_id = row["id"]
    payload = {
        "user": row,
        "checkins": client.table("revs_checkins").select("*").eq("user_id", user_id).execute().data,
        "weekly_reviews": client.table("revs_weekly_reviews").select("*").eq("user_id", user_id).execute().data,
        "tools": db.get_tools(client, user_id),
        "setbacks": client.table("revs_setbacks").select("*").eq("user_id", user_id).execute().data,
        "pem_screen_log": client.table("revs_pem_screen_log").select("*").eq("user_id", user_id).execute().data,
    }
    from io import BytesIO
    buf = BytesIO(json.dumps(payload, indent=2, default=str).encode("utf-8"))
    buf.name = f"revs_data_{user_id}.json"
    await update.message.reply_document(document=buf, filename=buf.name, caption="Everything stored about you.")


async def cmd_deleteme(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    await update.message.reply_text(
        "This deletes everything — check-ins, tools, everything — "
        "immediately and totally. Sure?",
        reply_markup=_kb([[("Yes, delete everything", "deleteme:confirm"), ("No, cancel", "deleteme:cancel")]]),
    )


async def handle_deleteme_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    if value == "cancel":
        await query.edit_message_text("Cancelled — nothing deleted.")
        return
    db.delete_user_cascade(client, row["id"])
    await query.edit_message_text("Done. Everything's deleted. Send /start any time to begin again.")


async def cmd_quiet(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=24)
    db.update_user(client, row["id"], quiet_until=until.isoformat())
    await update.message.reply_text("Quiet for 24 hours.")


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    db.update_user(client, row["id"], paused_until="9999-12-31T00:00:00+00:00")
    await _reply(update, "Paused. /resume any time you want it back.")


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    db.update_user(client, row["id"], paused_until=None)
    await update.message.reply_text("Back on. Next check-in at your usual time.")


async def handle_weekly_pause_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    """§3.1 — response to the three-skipped-reviews offer. Pauses only the
    weekly review slot, not daily check-ins (that's /pause's job)."""
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    if value == "pause":
        db.update_user(client, row["id"], weekly_day=None, weekly_time=None)
        await query.edit_message_text("Weekly reviews paused. Set a new time any time you're ready.")
    else:
        db.update_user(client, row["id"], weekly_skip_count=0, weekly_pause_offer_sent=False)
        await query.edit_message_text("Left running.")


async def handle_silence_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    """§5.5 — response to the seven-day silence notice."""
    query = update.callback_query
    await query.answer()
    value = query.data.split(":")[1]
    if value == "still":
        await query.edit_message_text("Good to know. Carrying on as usual.")
    elif value == "pause":
        await cmd_pause(update, context, client, row)
    elif value == "stop":
        db.update_user(client, row["id"], paused_until="9999-12-31T00:00:00+00:00")
        await query.edit_message_text("Stopped. Send /start any time to pick it back up.")


async def cmd_whatheld(update: Update, context: ContextTypes.DEFAULT_TYPE, client, row: dict) -> None:
    if row.get("stage") == "RECOGNISE":
        await update.message.reply_text("Not available in Recognise — this one's off until Regulate.")
        return
    new_val = not row.get("whatheld_enabled")
    db.update_user(client, row["id"], whatheld_enabled=new_val)
    await update.message.reply_text("What Held add-on: " + ("on" if new_val else "off") + ".")
