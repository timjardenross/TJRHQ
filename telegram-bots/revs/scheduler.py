"""Scheduled + periodic-scan jobs. Everything here is either a proactive
send (daily AM/PM, weekly review) or a time-based safety scan (§5.4c
re-contact, §5.5 silence, §4.3 delayed setback reflection, §5.6 periodic
PEM re-screen) — anything event-driven off a single check-in write (§5.1,
part of §5.4b) lives in daily.py instead, fired inline right after the
insert.

Uses apscheduler's AsyncIOScheduler, same dependency already pinned in
requirements.txt (mirrors telegram-bots/xo/requirements.txt). Unlike XO,
this bot DOES self-schedule — there is no separate always-on
intelligence-scheduler.service equivalent for REVS, and a per-user cron
of "send at each user's own chosen time" doesn't fit that shared-daemon
model anyway.
"""

from __future__ import annotations

import datetime as dt
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import commands
import daily
import db
import onboarding
import weekly
from copy_bank import crisis_recontact
from safety import locale_resources

log = logging.getLogger("revs-bot.scheduler")

_TICK_SECONDS = 60
_SAFETY_SCAN_SECONDS = 120
_WEEKDAY_INDEX = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}


def _now_hhmm() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%H:%M")


def _norm(t) -> str:
    return (t or "")[:5]


def _weekday_name(d: dt.date) -> str:
    return d.strftime("%A")


async def _tick(bot, client) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    hhmm = now.strftime("%H:%M")
    today = now.date()
    weekday = _weekday_name(today)

    users = db.list_active_users(client)
    for user in users:
        if user.get("quiet_until") and user["quiet_until"] > now.isoformat():
            continue

        if _norm(user.get("am_time")) == hhmm:
            existing = db.get_checkin(client, user["id"], today, "am")
            if not existing:
                try:
                    await daily.send_am_checkin(bot, client, user)
                except Exception:
                    log.exception("[scheduler] AM send failed for %s", user["id"])

        if user.get("pm_enabled", True) and _norm(user.get("pm_time")) == hhmm:
            existing = db.get_checkin(client, user["id"], today, "pm")
            if not existing:
                try:
                    await daily.send_pm_checkin(bot, client, user)
                except Exception:
                    log.exception("[scheduler] PM send failed for %s", user["id"])

        if user.get("weekly_day") == weekday and _norm(user.get("weekly_time")) == hhmm:
            week_start = today - dt.timedelta(days=today.weekday())
            reviews = db.recent_weekly_reviews(client, user["id"], limit=1)
            already = reviews and reviews[0]["week_start"] == week_start.isoformat()
            if not already:
                try:
                    await weekly.send_weekly_review(bot, client, user)
                except Exception:
                    log.exception("[scheduler] weekly send failed for %s", user["id"])


async def _safety_scan(bot, client) -> None:
    now = dt.datetime.now(dt.timezone.utc)

    # §5.4c — 24h crisis re-contact, one message, no demand.
    for event in db.due_recontacts(client):
        try:
            user = db.get_user(client, event["user_id"])
            if not user:
                continue
            text = crisis_recontact(locale_resources(user.get("locale")))
            await bot.send_message(chat_id=user["id"], text=text)
            db.mark_recontact_sent(client, event["id"])
        except Exception:
            log.exception("[scheduler] recontact failed for event %s", event.get("id"))

    # §4.3 — delayed setback reflection, gated on the last two check-ins.
    for setback in db.due_setback_reflections(client):
        try:
            user = db.get_user(client, setback["user_id"])
            if not user:
                continue
            recent = db.recent_checkins(client, user["id"], "am", limit=2)
            ok = len(recent) >= 2 and all(c.get("state") in ("steady", "low") for c in recent)
            age_days = (now - dt.datetime.fromisoformat(setback["occurred_at"].replace("Z", "+00:00"))).days
            if ok:
                await commands.send_setback_reflection_prompt(bot, client, setback)
            elif age_days >= 7:
                db.update_setback(client, setback["id"], reflection_status="declined")
            else:
                due = now + dt.timedelta(hours=48)
                db.update_setback(client, setback["id"], reflection_due_at=due.isoformat())
        except Exception:
            log.exception("[scheduler] setback reflection failed for %s", setback.get("id"))


async def _daily_scan(bot, client) -> None:
    """Once-a-day checks: §5.5 silence, §5.6 periodic PEM re-screen,
    §3.1 three-skipped-reviews offer."""
    now = dt.datetime.now(dt.timezone.utc)
    users = db.list_active_users(client)

    for user in users:
        last_seen = user.get("last_seen_at")
        if not last_seen:
            continue
        last_seen_dt = dt.datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
        silent_days = (now - last_seen_dt).days

        if silent_days >= 14:
            db.update_user(client, user["id"], paused_until="9999-12-31T00:00:00+00:00")
            continue

        if silent_days >= 7 and not user.get("silence_notice_sent_at"):
            try:
                await bot.send_message(
                    chat_id=user["id"],
                    text=(
                        "Been quiet for a week. Completely fine — no catching "
                        "up needed.\n\n/tools is still there."
                    ),
                    reply_markup=_silence_kb(),
                )
                db.update_user(client, user["id"], silence_notice_sent_at=now.isoformat())
            except Exception:
                log.exception("[scheduler] silence notice failed for %s", user["id"])

        # §5.6 — 90-day periodic re-screen for pem_flag=false with ≥2 setbacks logged.
        if user.get("pem_flag") is False and not user.get("pending_pem_trigger"):
            pem_set_at = user.get("pem_set_at")
            if pem_set_at:
                age = (now - dt.datetime.fromisoformat(pem_set_at.replace("Z", "+00:00"))).days
                if age >= 90 and db.recent_setback_count(client, user["id"], 9999) >= 2:
                    try:
                        await onboarding.send_pem_rescreen(bot, client, user["id"], trigger="periodic_90d")
                    except Exception:
                        log.exception("[scheduler] PEM re-screen failed for %s", user["id"])

        # §3.1 — three skipped weekly reviews -> offer to pause them, once.
        # Counts a week as "skipped" the day after its scheduled slot if no
        # revs_weekly_reviews row exists for that week_start yet.
        # weekly_skip_last_counted guards against re-counting the same
        # missed week on every 6-hourly scan.
        weekly_day = user.get("weekly_day")
        if weekly_day and weekly_day in _WEEKDAY_INDEX and not user.get("weekly_pause_offer_sent"):
            today = now.date()
            this_week_start = today - dt.timedelta(days=today.weekday())
            scheduled_this_week = this_week_start + dt.timedelta(days=_WEEKDAY_INDEX[weekly_day])
            slot_passed = today > scheduled_this_week
            already_counted = user.get("weekly_skip_last_counted") == scheduled_this_week.isoformat()
            if slot_passed and not already_counted:
                reviews = db.recent_weekly_reviews(client, user["id"], limit=1)
                completed = reviews and reviews[0]["week_start"] == this_week_start.isoformat()
                if not completed:
                    new_count = (user.get("weekly_skip_count") or 0) + 1
                    db.update_user(
                        client, user["id"],
                        weekly_skip_count=new_count,
                        weekly_skip_last_counted=scheduled_this_week.isoformat(),
                    )
                    if new_count >= 3:
                        try:
                            await bot.send_message(
                                chat_id=user["id"],
                                text=(
                                    "The weekly reviews have been going unanswered "
                                    "— no problem at all. Want them paused for a bit?"
                                ),
                                reply_markup=_weekly_pause_kb(),
                            )
                            db.update_user(client, user["id"], weekly_pause_offer_sent=True)
                        except Exception:
                            log.exception("[scheduler] weekly-skip offer failed for %s", user["id"])


def _weekly_pause_kb():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Pause them", callback_data="wkpause:pause"), InlineKeyboardButton("Leave them running", callback_data="wkpause:leave")]]
    )


def _silence_kb():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Still here", callback_data="silence:still"), InlineKeyboardButton("Pause it", callback_data="silence:pause"), InlineKeyboardButton("Stop it", callback_data="silence:stop")]]
    )


def start(application, client) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    bot = application.bot

    scheduler.add_job(_tick, "interval", seconds=_TICK_SECONDS, args=[bot, client], id="revs_tick", max_instances=1, coalesce=True)
    scheduler.add_job(_safety_scan, "interval", seconds=_SAFETY_SCAN_SECONDS, args=[bot, client], id="revs_safety_scan", max_instances=1, coalesce=True)
    scheduler.add_job(_daily_scan, "interval", hours=6, args=[bot, client], id="revs_daily_scan", max_instances=1, coalesce=True)
    scheduler.start()
    log.info("[scheduler] started — tick=%ss safety=%ss daily=6h", _TICK_SECONDS, _SAFETY_SCAN_SECONDS)
    return scheduler
