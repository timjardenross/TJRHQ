"""
Daily medication reminder — XO nags until the Captain confirms.

Captain request 2026-09-24: "daily alert via the XO bot at 7am to tell me to
take my medicines — message every 15 mins till I say I've taken them."

Cadence (all Australia/Brisbane, same fixed TZ as every other XO/capacitybot
schedule):
  - 07:00 first reminder (python-telegram-bot JobQueue.run_daily — the same
    in-process mechanism capacitybot already uses for its 08:00/13:00/20:00
    pushes, so no new APScheduler instance is introduced).
  - Then every 15 min (JobQueue.run_repeating) until confirmed.
  - Hard stop at 22:00 so an unanswered day never turns into overnight
    pings; the next day starts fresh at 07:00.

Confirmation — any of:
  - the "✅ Taken" inline button on any reminder (callback_data "md|taken"),
  - /meds_taken,
  - a plain-text reply like "taken", "done", "I've taken them", "took my
    meds" — only matched while today's reminder is still outstanding, so
    ordinary conversation with XO is never swallowed on other days/times.

State: the confirmed date is persisted to a small local JSON file next to
this module (gitignored), so a bot restart neither re-nags after the Captain
already confirmed nor silently drops an in-progress nag — _post_init calls
resume_if_due() to pick an outstanding day back up.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

log = logging.getLogger("xo-bot.meds")

TZ = ZoneInfo("Australia/Brisbane")

START_TIME       = dtime(7, 0)
INTERVAL_MINUTES = 15
CUTOFF_TIME      = dtime(22, 0)

DAILY_JOB_NAME = "meds-daily-0700"
NAG_JOB_NAME   = "meds-nag"
CALLBACK_TAKEN = "md|taken"

STATE_PATH = Path(__file__).parent / ".medication_state.json"


# ── State ─────────────────────────────────────────────────────────────────────

def _load_state(path: Path = STATE_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001 - corrupt state must not crash the bot; worst case is one extra reminder
        log.warning("[meds] could not read %s: %s", path, exc)
        return {}


def _save_state(state: dict, path: Path = STATE_PATH) -> None:
    try:
        path.write_text(json.dumps(state), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - a failed write only risks one extra reminder after restart
        log.warning("[meds] could not write %s: %s", path, exc)


def today(now: datetime | None = None) -> date:
    return (now or datetime.now(TZ)).astimezone(TZ).date()


def is_confirmed(on: date, path: Path = STATE_PATH) -> bool:
    return _load_state(path).get("confirmed_date") == on.isoformat()


def mark_confirmed(on: date, path: Path = STATE_PATH) -> None:
    state = _load_state(path)
    state["confirmed_date"] = on.isoformat()
    _save_state(state, path)


def is_outstanding(now: datetime | None = None, path: Path = STATE_PATH) -> bool:
    """True between 07:00 and 22:00 on a day not yet confirmed."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    in_window = START_TIME <= now.time() < CUTOFF_TIME
    return in_window and not is_confirmed(now.date(), path)


# ── Natural-language confirmation ─────────────────────────────────────────────

_MEDS_WORDS = r"(?:med|meds|medicine|medicines|medication|medications|tablets|pills)"
_CONFIRM_PATTERNS = [
    re.compile(r"^\s*(?:taken|done|took (?:them|it)|all done|yep,? taken)\s*[.!✅👍]*\s*$", re.IGNORECASE),
    re.compile(r"\b(?:i'?ve|i have|i|just|already)\s+(?:taken|took|had)\s+(?:them|it|my|the)\b", re.IGNORECASE),
    re.compile(rf"\b(?:taken|took|had)\s+(?:my\s+|the\s+|all\s+)?{_MEDS_WORDS}\b", re.IGNORECASE),
    re.compile(rf"\b{_MEDS_WORDS}\s+(?:taken|done)\b", re.IGNORECASE),
]


def is_confirmation_text(text: str) -> bool:
    return any(p.search(text or "") for p in _CONFIRM_PATTERNS)


# ── Messages ──────────────────────────────────────────────────────────────────

def keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Taken", callback_data=CALLBACK_TAKEN)]])


def reminder_text(count: int) -> str:
    if count <= 1:
        return "💊 Morning, Captain — time to take your medicines.\n\nTap ✅ Taken or reply \"taken\" when done."
    return f"💊 Reminder #{count} — medicines still not confirmed. Take them now, then tap ✅ Taken."


CONFIRMED_TEXT = "✅ Logged — medicines taken. Reminders stopped for today."


# ── Jobs ──────────────────────────────────────────────────────────────────────

def _cancel_nag(job_queue) -> None:
    for job in job_queue.get_jobs_by_name(NAG_JOB_NAME):
        job.schedule_removal()


def _start_nag(job_queue, chat_id: int) -> None:
    _cancel_nag(job_queue)
    job_queue.run_repeating(
        _job_nag,
        interval=timedelta(minutes=INTERVAL_MINUTES),
        first=timedelta(minutes=INTERVAL_MINUTES),
        chat_id=chat_id,
        name=NAG_JOB_NAME,
        data={"count": 1},
    )


async def _send(bot, chat_id: int, count: int) -> None:
    await bot.send_message(chat_id, reminder_text(count), reply_markup=keyboard())


async def _job_daily(context) -> None:
    """07:00 — first reminder, then arm the 15-minute repeat."""
    chat_id = context.job.chat_id
    if is_confirmed(today()):
        return
    await _send(context.bot, chat_id, 1)
    _start_nag(context.job_queue, chat_id)


async def _job_nag(context) -> None:
    """Every 15 min — stops itself once confirmed or at the 22:00 cutoff."""
    job = context.job
    if not is_outstanding():
        job.schedule_removal()
        return
    job.data["count"] += 1
    await _send(context.bot, job.chat_id, job.data["count"])


def schedule(job_queue, chat_id: int) -> None:
    """Register the daily 07:00 job. Called once from app._post_init."""
    job_queue.run_daily(
        _job_daily, time=START_TIME.replace(tzinfo=TZ), chat_id=chat_id, name=DAILY_JOB_NAME,
    )


async def resume_if_due(bot, job_queue, chat_id: int) -> None:
    """After a restart inside today's window with no confirmation yet,
    send a reminder now and resume the 15-minute cadence."""
    if is_outstanding():
        log.info("[meds] restart inside reminder window, unconfirmed — resuming nag")
        await _send(bot, chat_id, 1)
        _start_nag(job_queue, chat_id)


def confirm(job_queue) -> None:
    """Mark today confirmed and stop any running nag."""
    mark_confirmed(today())
    _cancel_nag(job_queue)
    log.info("[meds] confirmed for %s", today().isoformat())
