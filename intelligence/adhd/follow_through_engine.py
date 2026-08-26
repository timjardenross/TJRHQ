"""
Adaptive Follow-Through Engine

Replaces task_nudge_scheduler.py's send-path with mode-aware, durable
follow-through scheduling for `personal_tasks` (migrations 0165/0166).

Where task_nudge_scheduler.py used a SQLite rate-limiter and a fixed
"urgency>=4, stalled >2h" rule with a single random-template nudge,
this engine:
  - Reads/writes next_review_at / last_surfaced_at / nudge_count /
    deferral_count directly on personal_tasks — the columns themselves
    ARE the dedup ledger, no separate cache.
  - Applies per-task `follow_through_mode` scheduling (gentle / normal /
    persistent / deadline / waiting).
  - Gates on today's capacity_checkins state, quiet hours (mirrors
    platform-runtime/captain_notifications.py's NotificationConfig —
    reimplemented locally rather than imported, different venv/process),
    and a daily send cap.
  - Bundles low-urgency items into one message, sends
    deadline-near/repeated-deferral items individually.
  - Sends via Telegram directly (to recover message_id for
    follow_through_sends) rather than through
    core/platform/notification_service.notify(), whose NotificationResult
    does not carry the Telegram message_id back to the caller.

All PostgREST access is stdlib urllib, matching task_nudge_scheduler.py's
_fetch_stalled_tasks pattern (no supabase-py SDK dependency anywhere else
in this codebase).

Entry point: run_follow_through_pass() — plain sync function, called
directly from intelligence/scheduler.py's _adhd_nudge_job() (no asyncio
loop needed; every network call here is a blocking urllib request).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Any, Optional

from intelligence.config import SUPABASE_KEY, SUPABASE_URL

log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

CANDIDATE_WORK_STATES = ("captured", "in_progress", "paused", "blocked")

# Days-before-due checkpoints for follow_through_mode='deadline', in
# calendar-chronological order (14-days-out fires first, 0 = due date).
DEADLINE_LADDER_DAYS = [14, 7, 3, 1, 0]
_DEADLINE_WARN_DAYS = {14, 7}  # remaining ladder values (3, 1, 0, overdue) are 'crit'

CANDIDATE_SELECT_COLUMNS = (
    "id,title,category,urgency,importance,effort_minutes,work_state,due_date,"
    "waiting_on,micro_action,mvp_note,stop_point,restart_cue,follow_through_mode,"
    "next_review_at,snoozed_until,last_surfaced_at,nudge_count,deferral_count,"
    "blocker_category"
)

_TELEGRAM_HTML_SPECIAL = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"))

TONE_RANK = {"crit": 0, "warn": 1, "neutral": 2}


# ── Small helpers ────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today(now: datetime) -> date:
    return now.date()


def _q(value: Any) -> str:
    """Percent-encode a single dynamic value for embedding inside a raw
    PostgREST filter expression (structural chars — (),.= — are left
    literal, matching captains_brief.py's raw-append query style)."""
    return urllib.parse.quote(str(value), safe="")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _date_to_dt(d: date) -> datetime:
    """Midnight UTC of a date column value, for comparison against
    timestamptz next_review_at."""
    return datetime.combine(d, dt_time.min, tzinfo=timezone.utc)


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        v = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _esc_html(text: str) -> str:
    for ch, esc in _TELEGRAM_HTML_SPECIAL:
        text = text.replace(ch, esc)
    return text


# ── PostgREST access ─────────────────────────────────────────────────────────

def _pg_headers(extra: Optional[dict] = None) -> dict:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def _pg_get(path_and_query: str, count_exact: bool = False) -> tuple[list[dict], Optional[int]]:
    """GET {SUPABASE_URL}/rest/v1/{path_and_query}. Returns (rows, total_count).
    total_count is only populated when count_exact=True (via Content-Range)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("[FollowThrough] Supabase not configured; skipping")
        return [], None
    url = f"{SUPABASE_URL}/rest/v1/{path_and_query}"
    headers = _pg_headers({"Prefer": "count=exact"} if count_exact else None)
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read() or b"[]")
            total = None
            if count_exact:
                cr = resp.headers.get("Content-Range", "")
                if "/" in cr:
                    tail = cr.rsplit("/", 1)[-1]
                    if tail.isdigit():
                        total = int(tail)
            return rows, total
    except Exception as exc:
        log.error("[FollowThrough] GET %s failed: %s", path_and_query, exc)
        return [], None


def _pg_patch(table: str, row_id: str, payload: dict) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    url = f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{_q(row_id)}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="PATCH",
        headers=_pg_headers({"Prefer": "return=minimal"}),
    )
    try:
        with urllib.request.urlopen(req, timeout=15):
            return True
    except Exception as exc:
        log.error("[FollowThrough] PATCH %s/%s failed: %s", table, row_id, exc)
        return False


def _pg_post(table: str, payload: dict) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers=_pg_headers({"Prefer": "return=minimal"}),
    )
    try:
        with urllib.request.urlopen(req, timeout=15):
            return True
    except Exception as exc:
        log.error("[FollowThrough] POST %s failed: %s", table, exc)
        return False


def build_candidate_query(now: datetime) -> str:
    """Build the PostgREST query string (path + query) for candidate
    selection. Nested and/or uses PostgREST's composite meta-param syntax:
    `and=(or(...),or(...))` — nested groups drop the leading `=` since
    they're function-call-style arguments inside the parent group."""
    now_iso = _q(_iso(now))
    filt = (
        "personal_tasks"
        f"?select={CANDIDATE_SELECT_COLUMNS}"
        f"&work_state=in.({','.join(CANDIDATE_WORK_STATES)})"
        "&follow_through_paused=eq.false"
        "&and=("
        f"or(next_review_at.is.null,next_review_at.lte.{now_iso}),"
        f"or(snoozed_until.is.null,snoozed_until.lte.{now_iso})"
        ")"
        "&order=due_date.asc.nullslast"
        "&limit=200"
    )
    return filt


def build_daily_cap_query(now: datetime) -> str:
    today_start = _q(_iso(datetime.combine(_today(now), dt_time.min, tzinfo=timezone.utc)))
    return (
        "follow_through_events"
        "?select=id"
        "&event_type=eq.surfaced"
        f"&occurred_at=gte.{today_start}"
    )


def _fetch_candidates(now: datetime) -> list[dict]:
    query = build_candidate_query(now)
    rows, _ = _pg_get(query)
    return rows


def _fetch_todays_capacity_state(now: datetime) -> Optional[str]:
    today_iso = _today(now).isoformat()
    query = (
        "capacity_checkins"
        f"?log_date=eq.{today_iso}&checkin_type=eq.capacity"
        "&order=captured_at.desc&limit=1"
    )
    rows, _ = _pg_get(query)
    if not rows:
        return None
    return rows[0].get("capacity_state")


def _count_todays_surfaced(now: datetime) -> int:
    query = build_daily_cap_query(now)
    rows, total = _pg_get(query, count_exact=True)
    if total is not None:
        return total
    return len(rows)


# ── Quiet hours (mirrors platform-runtime/captain_notifications.py's
# NotificationConfig.should_send — reimplemented locally, not imported:
# different venv/process. Env vars are plain hour integers (0-23), NOT
# HH:MM — that matches the live implementation, not the HH:MM assumption
# in the original mission brief.) ────────────────────────────────────────────

def _in_quiet_hours(now: datetime) -> bool:
    quiet_start = int(os.environ.get("QUIET_HOURS_START", "22"))
    quiet_end = int(os.environ.get("QUIET_HOURS_END", "7"))
    hour = now.astimezone().hour  # local time, matches captain_notifications.py's datetime.now()
    if quiet_start > quiet_end:
        # Wraps midnight: quiet from start until end next morning.
        return hour >= quiet_start or hour < quiet_end
    return quiet_start <= hour < quiet_end


# ── Deadline ladder ──────────────────────────────────────────────────────────

def _next_deadline_checkpoint(due: date, today: date, inclusive: bool) -> tuple[Optional[date], str]:
    """Earliest ladder checkpoint date that is still ahead (or, once
    overdue, the next day in the 1-day overdue drumbeat).

    inclusive=True: a checkpoint landing exactly on `today` counts as due
    now (used for a brand-new item's first-ever pass). inclusive=False:
    only checkpoints strictly after `today` count (used right after a
    send, to schedule the NEXT occurrence rather than re-firing today's).
    """
    if due < today:
        return today + timedelta(days=1), "crit"  # overdue drumbeat
    for d in DEADLINE_LADDER_DAYS:
        cp = due - timedelta(days=d)
        if (cp >= today) if inclusive else (cp > today):
            tone = "warn" if d in _DEADLINE_WARN_DAYS else "crit"
            return cp, tone
    return None, "neutral"


# ── Mode scheduling ──────────────────────────────────────────────────────────

def compute_initial_schedule(task: dict, now: datetime) -> tuple[Optional[datetime], str, bool]:
    """For a candidate with next_review_at IS NULL (first-ever pass).

    Returns (next_review_at_to_persist_if_not_sent_now, tone,
    eligible_now). `eligible_now` decides whether THIS pass should surface
    it; a brand-new gentle/normal/persistent/waiting item is always
    eligible immediately, a brand-new deadline item only if it's already
    within its first ladder checkpoint (or overdue).
    """
    mode = task.get("follow_through_mode") or "normal"
    due = _parse_date(task.get("due_date"))
    today = _today(now)

    if mode == "deadline":
        if due is None:
            # No due_date to build a ladder from — fall back to a
            # persistent-style 3-day check-in rather than never surfacing.
            return now + timedelta(days=3), "neutral", True
        if due < today:
            # Already overdue on its very first pass — surface immediately,
            # don't wait for a checkpoint that's now in the past.
            return _date_to_dt(today), "crit", True
        cp, tone = _next_deadline_checkpoint(due, today, inclusive=True)
        if cp is None:
            return None, "neutral", False
        eligible = cp <= today
        return _date_to_dt(cp), tone, eligible

    if mode == "gentle":
        target = _date_to_dt(due) if due else now + timedelta(days=3)
        return target, "neutral", True

    if mode == "normal":
        if due and _date_to_dt(due) - timedelta(days=2) > now:
            target = _date_to_dt(due) - timedelta(days=2)
        else:
            target = now + timedelta(days=2)
        return target, "neutral", True

    if mode == "persistent":
        return now + timedelta(days=3), "neutral", True

    if mode == "waiting":
        target = _date_to_dt(due) if due else now + timedelta(days=7)
        return target, "neutral", True

    # Unknown mode — treat like normal-once, non-fatal.
    return now + timedelta(days=2), "neutral", True


def compute_next_review_after_send(task: dict, now: datetime, new_nudge_count: int) -> Optional[datetime]:
    """Post-send scheduling for the NEXT occurrence (or None to stop)."""
    mode = task.get("follow_through_mode") or "normal"
    due = _parse_date(task.get("due_date"))

    if mode == "gentle":
        return None  # gentle surfaces once, then stops per migration 0165 comment.

    if mode == "normal":
        if new_nudge_count >= 2:
            return None  # normal stops after its 2nd surface.
        return now + timedelta(days=2)

    if mode == "persistent":
        return now + timedelta(days=3)

    if mode == "waiting":
        return now + timedelta(days=7)

    if mode == "deadline":
        if due is None:
            return now + timedelta(days=3)
        cp, _tone = _next_deadline_checkpoint(due, _today(now), inclusive=False)
        return _date_to_dt(cp) if cp else None

    return None


def _tone_for_candidate(task: dict, mode_tone: str) -> str:
    if (task.get("deferral_count") or 0) >= 3:
        return "crit"
    return mode_tone


# ── Candidate assembly ───────────────────────────────────────────────────────

def _assemble_eligible_candidates(raw_rows: list[dict], now: datetime) -> list[dict]:
    """Applies compute_initial_schedule() to null-next_review_at rows and
    drops candidates whose mode/schedule says "not yet". Rows that already
    had a next_review_at <= now (from the query) are eligible outright —
    the query already did that filtering."""
    eligible: list[dict] = []
    for task in raw_rows:
        nra_raw = task.get("next_review_at")
        if nra_raw:
            # Already has a scheduled review time that's <= now (per query).
            task["_tone"] = _tone_for_candidate(task, "neutral")
            # Recompute tone properly for deadline mode using its ladder
            # position, since the stored next_review_at alone doesn't carry it.
            if task.get("follow_through_mode") == "deadline":
                due = _parse_date(task.get("due_date"))
                if due is not None:
                    _cp, tone = _next_deadline_checkpoint(due, _today(now), inclusive=True)
                    task["_tone"] = _tone_for_candidate(task, tone)
            eligible.append(task)
            continue

        _next_dt, tone, eligible_now = compute_initial_schedule(task, now)
        if not eligible_now:
            continue
        task["_tone"] = _tone_for_candidate(task, tone)
        eligible.append(task)
    return eligible


def _apply_capacity_gate(candidates: list[dict], capacity_state: Optional[str], now: datetime) -> list[dict]:
    if capacity_state != "red":
        return candidates
    today = _today(now)
    kept = []
    for task in candidates:
        mode = task.get("follow_through_mode")
        due = _parse_date(task.get("due_date"))
        if mode in ("gentle", "normal") and (due is None or (due - today).days > 1):
            continue
        kept.append(task)
    return kept


def _is_critical_deadline(task: dict, now: datetime) -> bool:
    if task.get("follow_through_mode") != "deadline":
        return False
    due = _parse_date(task.get("due_date"))
    if due is None:
        return False
    return (due - _today(now)).days <= 1


def _apply_quiet_hours_gate(candidates: list[dict], now: datetime) -> list[dict]:
    if not _in_quiet_hours(now):
        return candidates
    return [t for t in candidates if _is_critical_deadline(t, now)]


def _apply_daily_cap(candidates: list[dict], now: datetime) -> list[dict]:
    max_per_day = int(os.environ.get("FOLLOW_THROUGH_MAX_PER_DAY", "5"))
    already_sent = _count_todays_surfaced(now)
    remaining = max(0, max_per_day - already_sent)
    if remaining >= len(candidates):
        return candidates
    ordered = sorted(
        candidates,
        key=lambda t: (
            TONE_RANK.get(t.get("_tone", "neutral"), 2),
            _parse_date(t.get("due_date")) or date.max,
        ),
    )
    return ordered[:remaining]


# ── Bundling ─────────────────────────────────────────────────────────────────

def _always_individual(task: dict, now: datetime) -> bool:
    if (task.get("deferral_count") or 0) >= 3:
        return True
    if task.get("follow_through_mode") == "deadline":
        due = _parse_date(task.get("due_date"))
        if due is not None and (due - _today(now)).days <= 3:
            return True
    return False


def _split_bundle_vs_individual(candidates: list[dict], now: datetime) -> tuple[list[dict], list[dict]]:
    individual = [t for t in candidates if _always_individual(t, now)]
    rest = [t for t in candidates if not _always_individual(t, now)]
    if len(rest) >= 2:
        return individual, rest  # rest goes into one bundle
    individual.extend(rest)  # 0 or 1 leftover -> send individually (or nothing)
    return individual, []


# ── Message composition ──────────────────────────────────────────────────────

def _btn(text: str, callback_data: str) -> dict:
    return {"text": text, "callback_data": callback_data}


def _kb(rows: list[dict]) -> dict:
    return {"inline_keyboard": [[b] for b in rows]}


def _next_action_phrase(task: dict) -> str:
    micro = task.get("micro_action")
    if micro:
        return f"Next: {micro}"
    return "What's the next tiny step?"


def compose_individual_message(task: dict, now: datetime) -> tuple[str, dict, bool]:
    """Returns (html_text, reply_markup, is_repeated_deferral)."""
    title = _esc_html(task.get("title") or "Untitled")
    mode = task.get("follow_through_mode") or "normal"
    deferral_count = task.get("deferral_count") or 0
    task_id = task["id"]

    if deferral_count >= 3:
        text = (
            f"<b>{title}</b>\n"
            "This has been moved a few times. Want help working out what's in the way?"
        )
        buttons = [
            _btn("Help Me Start", f"tk|start|{task_id}"),
            _btn("It's Blocked", f"tk|blocked|{task_id}"),
            _btn("Move It", f"tk|tomorrow|{task_id}"),
            _btn("Drop It", f"tk|drop|{task_id}"),
        ]
        return text, _kb(buttons), True

    if mode == "waiting":
        who = _esc_html(task.get("waiting_on") or "this")
        text = f"<b>{title}</b>\nStill outstanding? Check whether {who} has come through."
        buttons = [
            _btn("Still waiting", f"tk|snooze|{task_id}"),
            _btn("Resolved", f"tk|done|{task_id}"),
            _btn("Follow up now", f"tk|start|{task_id}"),
        ]
        return text, _kb(buttons), False

    tone = task.get("_tone", "neutral")
    due = _parse_date(task.get("due_date"))
    if mode == "deadline":
        if due is not None and due < _today(now):
            lede = "Overdue"
        elif tone == "crit":
            lede = "Due soon"
        elif due is not None:
            lede = f"Due {due.isoformat()}"
        else:
            lede = "Has a deadline"
    else:
        lede = {
            "gentle": "Still on the list",
            "normal": "Following up",
            "persistent": "Still open",
        }.get(mode, "Following up")

    text = f"<b>{title}</b>\n{lede}. {_esc_html(_next_action_phrase(task))}"
    buttons = [
        _btn("Done", f"tk|done|{task_id}"),
        _btn("Snooze", f"tk|snooze|{task_id}"),
        _btn("Tomorrow", f"tk|tomorrow|{task_id}"),
        _btn("Help Me Start", f"tk|start|{task_id}"),
        _btn("Blocked", f"tk|blocked|{task_id}"),
    ]
    return text, _kb(buttons), False


def compose_bundle_message(tasks: list[dict]) -> tuple[str, dict]:
    n = len(tasks)
    lines = "\n".join(f"- {_esc_html(t.get('title') or 'Untitled')}" for t in tasks[:5])
    text = f"<b>{n} Life Admin items need a decision</b>\n{lines}"
    buttons = [_btn("Review", "tk|review|")]
    return text, _kb(buttons)


# ── Telegram send (direct — need message_id back for follow_through_sends,
# which notify()'s NotificationResult does not carry) ───────────────────────

def _resolve_chat_id() -> str:
    raw_ids = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
    if raw_ids:
        return raw_ids.split(",")[0].strip()
    return os.environ.get("TELEGRAM_CHAT_ID", "")


def _send_telegram(text: str, reply_markup: dict) -> tuple[bool, Optional[str], Optional[int]]:
    """Sends via Telegram HTML parse_mode (matches
    core/platform/notification_service.py's _send_telegram convention).
    Returns (ok, error, message_id)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = _resolve_chat_id()
    if not token or not chat_id:
        return False, "missing TELEGRAM_BOT_TOKEN or chat id", None
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body_obj = {
        "chat_id": chat_id,
        "text": text[:4096],
        "parse_mode": "HTML",
        "reply_markup": reply_markup,
    }
    payload = json.dumps(body_obj).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            parsed = json.loads(resp.read())
            message_id = (parsed.get("result") or {}).get("message_id")
            return True, None, message_id
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}", None


# ── Recording ────────────────────────────────────────────────────────────────

def _record_send(task: dict, now: datetime, tone: str, bundled: bool) -> None:
    new_nudge_count = (task.get("nudge_count") or 0) + 1
    next_review_at = compute_next_review_after_send(task, now, new_nudge_count)
    patch = {
        "last_surfaced_at": _iso(now),
        "nudge_count": new_nudge_count,
        "next_review_at": _iso(next_review_at) if next_review_at else None,
    }
    _pg_patch("personal_tasks", task["id"], patch)
    _pg_post("follow_through_events", {
        "task_id": task["id"],
        "event_type": "surfaced",
        "detail": {
            "mode": task.get("follow_through_mode"),
            "tone": tone,
            "bundled": bundled,
        },
    })


def _record_individual_sent(task_id: str, chat_id: str, message_id: Optional[int]) -> None:
    if message_id is None:
        return
    _pg_post("follow_through_sends", {
        "task_id": task_id,
        "chat_id": chat_id,
        "message_id": message_id,
    })


# ── Entry point ──────────────────────────────────────────────────────────────

def run_follow_through_pass() -> dict:
    """Main scheduler entry point. Sync, matches how _adhd_nudge_job() in
    intelligence/scheduler.py invokes it (plain call, no asyncio needed —
    every network call in this module is blocking urllib).

    Returns {"checked": N, "nudged": N, "errors": [...]}."""
    summary: dict[str, Any] = {"checked": 0, "nudged": 0, "errors": []}
    now = _now()

    try:
        raw_rows = _fetch_candidates(now)
        summary["checked"] = len(raw_rows)
        if not raw_rows:
            return summary

        candidates = _assemble_eligible_candidates(raw_rows, now)
        if not candidates:
            return summary

        capacity_state = _fetch_todays_capacity_state(now)
        candidates = _apply_capacity_gate(candidates, capacity_state, now)
        if not candidates:
            return summary

        candidates = _apply_quiet_hours_gate(candidates, now)
        if not candidates:
            log.info("[FollowThrough] In quiet hours, nothing critical to break through")
            return summary

        candidates = _apply_daily_cap(candidates, now)
        if not candidates:
            log.info("[FollowThrough] Daily cap reached, nothing to send")
            return summary

        individual, bundle = _split_bundle_vs_individual(candidates, now)
        chat_id = _resolve_chat_id()

        for task in individual:
            try:
                text, reply_markup, _is_repeat = compose_individual_message(task, now)
                ok, error, message_id = _send_telegram(text, reply_markup)
                if not ok:
                    summary["errors"].append(f"send failed for {task['id']}: {error}")
                    continue
                _record_individual_sent(task["id"], chat_id, message_id)
                _record_send(task, now, task.get("_tone", "neutral"), bundled=False)
                summary["nudged"] += 1
            except Exception as exc:
                summary["errors"].append(f"task {task.get('id')}: {exc}")
                log.error("[FollowThrough] Individual send failed for %s: %s", task.get("id"), exc)

        if bundle:
            try:
                text, reply_markup = compose_bundle_message(bundle)
                ok, error, _message_id = _send_telegram(text, reply_markup)
                if not ok:
                    summary["errors"].append(f"bundle send failed: {error}")
                else:
                    for task in bundle:
                        try:
                            _record_send(task, now, task.get("_tone", "neutral"), bundled=True)
                        except Exception as exc:
                            summary["errors"].append(f"bundle record failed for {task.get('id')}: {exc}")
                    summary["nudged"] += 1
            except Exception as exc:
                summary["errors"].append(f"bundle: {exc}")
                log.error("[FollowThrough] Bundle send failed: %s", exc)

        return summary

    except Exception as exc:
        error_msg = f"[FollowThrough] Pass error: {exc}"
        log.error(error_msg)
        summary["errors"].append(error_msg)
        return summary
