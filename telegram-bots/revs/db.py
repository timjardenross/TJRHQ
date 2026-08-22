"""Supabase access for the REVS bot. All queries go through the single
scoped `revs_bot` client built at startup (see scoped_supabase.py) — no
service_role fallback. Every function here takes the client explicitly
rather than reaching for a module-level global, so tests can pass a fake.

Table/column names match core/infrastructure/supabase/migrations/
0147_revs_bot_scoped_role.sql.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Optional


# ---------------------------------------------------------------- users ---

def get_user(client, user_id: int) -> Optional[dict]:
    res = client.table("revs_users").select("*").eq("id", user_id).limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None


def create_user(client, user_id: int, first_name: str) -> dict:
    res = (
        client.table("revs_users")
        .insert({"id": user_id, "first_name": first_name, "onboarding_step": "welcome"})
        .execute()
    )
    return res.data[0]


def update_user(client, user_id: int, **fields: Any) -> None:
    if not fields:
        return
    client.table("revs_users").update(fields).eq("id", user_id).execute()


def touch_last_seen(client, user_id: int) -> None:
    update_user(client, user_id, last_seen_at=dt.datetime.now(dt.timezone.utc).isoformat())


def delete_user_cascade(client, user_id: int) -> None:
    """'Deletion is immediate and total' (§1.2). FKs are ON DELETE CASCADE
    for the child tables, but delete explicitly rather than relying only on
    the cascade, so this stays correct even if a future migration changes
    the FK behaviour."""
    for table in (
        "revs_pem_screen_log",
        "revs_crisis_events",
        "revs_setbacks",
        "revs_tools",
        "revs_weekly_reviews",
        "revs_checkins",
    ):
        client.table(table).delete().eq("user_id", user_id).execute()
    client.table("revs_users").delete().eq("id", user_id).execute()


def list_active_users(client) -> list[dict]:
    """Users with onboarding complete, not currently paused. Used by the
    scheduler to decide who's due for a scheduled send."""
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    res = (
        client.table("revs_users")
        .select("*")
        .eq("onboarding_complete", True)
        .execute()
    )
    users = res.data or []
    return [u for u in users if not (u.get("paused_until") and u["paused_until"] > now)]


# ------------------------------------------------------------ checkins ---

def upsert_checkin(client, user_id: int, checkin_date: dt.date, period: str, **fields: Any) -> dict:
    row = {"user_id": user_id, "checkin_date": checkin_date.isoformat(), "period": period, **fields}
    res = (
        client.table("revs_checkins")
        .upsert(row, on_conflict="user_id,checkin_date,period")
        .execute()
    )
    return res.data[0]


def get_checkin(client, user_id: int, checkin_date: dt.date, period: str) -> Optional[dict]:
    res = (
        client.table("revs_checkins")
        .select("*")
        .eq("user_id", user_id)
        .eq("checkin_date", checkin_date.isoformat())
        .eq("period", period)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def recent_checkins(client, user_id: int, period: str, limit: int = 14) -> list[dict]:
    res = (
        client.table("revs_checkins")
        .select("*")
        .eq("user_id", user_id)
        .eq("period", period)
        .order("checkin_date", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def checkins_between(client, user_id: int, start: dt.date, end: dt.date) -> list[dict]:
    res = (
        client.table("revs_checkins")
        .select("*")
        .eq("user_id", user_id)
        .gte("checkin_date", start.isoformat())
        .lte("checkin_date", end.isoformat())
        .execute()
    )
    return res.data or []


# ------------------------------------------------------------- weekly ---

def upsert_weekly_review(client, user_id: int, week_start: dt.date, **fields: Any) -> dict:
    row = {"user_id": user_id, "week_start": week_start.isoformat(), **fields}
    res = (
        client.table("revs_weekly_reviews")
        .upsert(row, on_conflict="user_id,week_start")
        .execute()
    )
    return res.data[0]


def recent_weekly_reviews(client, user_id: int, limit: int = 6) -> list[dict]:
    res = (
        client.table("revs_weekly_reviews")
        .select("*")
        .eq("user_id", user_id)
        .order("week_start", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# --------------------------------------------------------------- tools ---

def get_tools(client, user_id: int) -> list[dict]:
    res = (
        client.table("revs_tools")
        .select("*")
        .eq("user_id", user_id)
        .order("slot")
        .execute()
    )
    return res.data or []


def upsert_tool(client, user_id: int, slot: int, approach: str, instruction: str, non_replayable: bool) -> dict:
    row = {
        "user_id": user_id,
        "slot": slot,
        "approach": approach,
        "instruction": instruction,
        "non_replayable": non_replayable,
    }
    res = client.table("revs_tools").upsert(row, on_conflict="user_id,slot").execute()
    return res.data[0]


# ----------------------------------------------------------- setbacks ---

def insert_setback(client, user_id: int, reflection_due_at: dt.datetime) -> dict:
    res = (
        client.table("revs_setbacks")
        .insert(
            {
                "user_id": user_id,
                "reflection_status": "pending",
                "reflection_due_at": reflection_due_at.isoformat(),
            }
        )
        .execute()
    )
    return res.data[0]


def update_setback(client, setback_id: int, **fields: Any) -> None:
    client.table("revs_setbacks").update(fields).eq("id", setback_id).execute()


def due_setback_reflections(client) -> list[dict]:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    res = (
        client.table("revs_setbacks")
        .select("*")
        .eq("reflection_status", "pending")
        .lte("reflection_due_at", now)
        .execute()
    )
    return res.data or []


def recent_setback_count(client, user_id: int, days: int) -> int:
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    res = (
        client.table("revs_setbacks")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("occurred_at", since)
        .execute()
    )
    return res.count or 0


# ------------------------------------------------------------- crisis ---

def insert_crisis_event(client, user_id: int, trigger_type: str, recontact_due_at: Optional[dt.datetime]) -> dict:
    row: dict[str, Any] = {"user_id": user_id, "trigger_type": trigger_type}
    if recontact_due_at is not None:
        row["recontact_due_at"] = recontact_due_at.isoformat()
    res = client.table("revs_crisis_events").insert(row).execute()
    return res.data[0]


def due_recontacts(client) -> list[dict]:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    res = (
        client.table("revs_crisis_events")
        .select("*")
        .lte("recontact_due_at", now)
        .is_("recontact_sent_at", "null")
        .execute()
    )
    return res.data or []


def mark_recontact_sent(client, event_id: int) -> None:
    client.table("revs_crisis_events").update(
        {"recontact_sent_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    ).eq("id", event_id).execute()


def set_dont_show_again(client, user_id: int, until: dt.datetime) -> None:
    client.table("revs_crisis_events").insert(
        {
            "user_id": user_id,
            "trigger_type": "nontext",
            "dont_show_again": True,
            "suppressed_until": until.isoformat(),
        }
    ).execute()


def is_nontext_crisis_suppressed(client, user_id: int) -> bool:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    res = (
        client.table("revs_crisis_events")
        .select("id")
        .eq("user_id", user_id)
        .eq("dont_show_again", True)
        .gte("suppressed_until", now)
        .limit(1)
        .execute()
    )
    return bool(res.data)


# --------------------------------------------------------- pem screens ---

def insert_pem_screen_log(client, user_id: int, result: str, trigger: str) -> dict:
    res = (
        client.table("revs_pem_screen_log")
        .insert({"user_id": user_id, "result": result, "trigger": trigger})
        .execute()
    )
    return res.data[0]
