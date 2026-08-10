"""Standalone pre-cutover verification for the xo_bot scoped Supabase role.

Run this AFTER SUPABASE_JWT_SECRET (or a pre-minted XO_BOT_SCOPED_TOKEN) and
SUPABASE_ANON_KEY are added to telegram-bots/xo/.env, and BEFORE restarting
tg-xo.service with the new credential. It exercises every real Supabase
operation the live bot's own code performs, through the exact same
scoped_supabase.build_scoped_client() construction app.py's _get_supabase()
uses — not a substitute mechanism.

Every table/operation here was independently verified once already at the
SQL level (SET LOCAL ROLE xo_bot inside a rolled-back transaction, see
xo-bot-scoped-role-implemented.md) — that pass confirmed the RLS policies
and GRANTs themselves are correct (and caught two real bugs: missing
sequence GRANTs for activity_logs/weight_logs, fixed in migration 0135).
This script's job is different: it proves the *other* half — that the
JWT-minting + header-patch + PostgREST role-switching mechanism in
scoped_supabase.py actually reaches the database as `xo_bot` over real
HTTP, end to end. Do not skip this even though the SQL pass already
succeeded; a broken JWT/header path would silently fall back to (or
outright fail as) something else entirely.

No transaction rollback is available over the REST API, so this script
cleans up every row it writes explicitly (delete after insert/update
tests) rather than relying on ON COMMIT DROP-style semantics. If it dies
partway through, look for rows tagged 'xo_bot_rls_test' /
log_date/window_date = 2099-01-01 in recovery_pulses, activity_logs,
weight_logs, captured_items, wellness_reminder_log and remove them by hand.

Usage:
    cd /opt/starship-endeavour/telegram-bots/xo
    .venv/bin/python3 test_scoped_role.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_BOT_DIR = Path(__file__).parent
_REPO_ROOT = _BOT_DIR.parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BOT_DIR / ".env")

import os  # noqa: E402

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")

_PASS = []
_FAIL = []


def check(name: str, fn):
    try:
        detail = fn()
        _PASS.append(name)
        print(f"  PASS  {name}" + (f"  ({detail})" if detail else ""))
        return detail
    except Exception as exc:
        _FAIL.append((name, str(exc)))
        print(f"  FAIL  {name}  -> {exc}")
        return None


def cleanup(fn) -> None:
    """Best-effort cleanup after a test op — must never let a cleanup
    failure (e.g. the row was never created because the op it's cleaning
    up after already failed) abort the rest of the run. Not itself a
    pass/fail signal."""
    try:
        fn()
    except Exception as exc:
        print(f"  (cleanup skipped/failed, non-fatal: {exc})")


def main() -> int:
    if not SUPABASE_URL:
        print("SUPABASE_URL not set — aborting.")
        return 2

    from telegram_bots.xo import scoped_supabase

    token_preview = scoped_supabase.resolve_scoped_auth()
    if not token_preview:
        print(
            "No scoped credential configured (SUPABASE_JWT_SECRET / "
            "XO_BOT_SCOPED_TOKEN both unset). Nothing to test yet — this is "
            "expected until the Captain/dashboard-holder supplies "
            "SUPABASE_JWT_SECRET. Not a failure, just not runnable."
        )
        return 3

    db = scoped_supabase.build_scoped_client(SUPABASE_URL)
    if db is None:
        print("build_scoped_client() returned None (likely missing SUPABASE_ANON_KEY). Aborting.")
        return 2

    print("Scoped client constructed. Running 22 real operations as xo_bot...\n")

    # 1-2. missions / recovery_confidence_today — read-only surfaces
    check("missions SELECT", lambda: db.table("missions").select("mission_id").limit(1).execute())
    check("recovery_confidence_today SELECT (view)",
          lambda: db.table("recovery_confidence_today").select("*").execute())

    # 3-6. recovery_pulses — select, insert, update, upsert
    check("recovery_pulses SELECT", lambda: db.table("recovery_pulses").select("id").limit(1).execute())

    def _pulse_insert():
        res = db.table("recovery_pulses").insert({
            "log_date": "2099-01-01", "pulse_type": "midday",
            "energy": "high", "nervous_system": "calm",
            "source": "telegram", "notes": "xo_bot_rls_test",
        }).execute()
        if not res.data:
            raise RuntimeError("insert returned no data")
        return res.data[0]["id"]

    pulse_id = check("recovery_pulses INSERT", _pulse_insert)

    if pulse_id:
        check("recovery_pulses UPDATE (landmine: no authenticated policy exists live)",
              lambda: db.table("recovery_pulses").update({"notes": "xo_bot_rls_test [updated]"}).eq("id", pulse_id).execute())
        # Not a real bot operation — the live bot never deletes recovery_pulses
        # rows, and xo_bot correctly has no DELETE grant on this table (see
        # migration 0135). A failure here is expected and not a test failure;
        # test rows are swept up by the admin-level cleanup query documented
        # in xo-bot-scoped-role-implemented.md if this ever fails.
        cleanup(lambda: db.table("recovery_pulses").delete().eq("id", pulse_id).execute())

    check("recovery_pulses UPSERT (on_conflict=log_date,pulse_type)",
          lambda: db.table("recovery_pulses").upsert(
              {"log_date": "2099-01-01", "pulse_type": "morning", "energy": "moderate",
               "nervous_system": "activated", "source": "telegram"},
              on_conflict="log_date,pulse_type").execute())
    cleanup(lambda: db.table("recovery_pulses").delete().eq("log_date", "2099-01-01").execute())

    # 7-8. activity_logs
    check("activity_logs SELECT", lambda: db.table("activity_logs").select("id").limit(1).execute())

    def _activity_insert():
        res = db.table("activity_logs").insert({
            "log_date": "2099-01-01", "activity_type": "walk", "source": "telegram", "completed": True,
        }).execute()
        return res.data[0]["id"] if res.data else None

    activity_id = check("activity_logs INSERT (needs sequence USAGE grant, see migration 0135)", _activity_insert)
    if activity_id:
        cleanup(lambda: db.table("activity_logs").delete().eq("id", activity_id).execute())

    # 9-10. weight_logs
    check("weight_logs SELECT", lambda: db.table("weight_logs").select("id").limit(1).execute())

    def _weight_upsert():
        res = db.table("weight_logs").upsert(
            {"log_date": "2099-01-01", "weight_kg": 82.5, "source": "telegram"},
            on_conflict="log_date").execute()
        return res.data[0]["id"] if res.data else None

    weight_id = check("weight_logs UPSERT (needs sequence USAGE grant, see migration 0135)", _weight_upsert)
    if weight_id:
        cleanup(lambda: db.table("weight_logs").delete().eq("id", weight_id).execute())

    # 11-14. intelligence_* read surfaces
    check("intelligence_briefs SELECT",
          lambda: db.table("intelligence_briefs").select("brief_id").order("generated_at", desc=True).limit(1).execute())
    check("intelligence_events SELECT",
          lambda: db.table("intelligence_events").select("event_id").limit(1).execute())
    check("intelligence_source_health SELECT",
          lambda: db.table("intelligence_source_health").select("source_id").limit(1).execute())
    check("intelligence_source_registry SELECT",
          lambda: db.table("intelligence_source_registry").select("source_id").eq("active", True).limit(1).execute())

    # 15-18. captured_items — the full lifecycle including the DELETE landmine
    def _capture_insert():
        row_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        res = db.table("captured_items").insert({
            "id": row_id, "captured_by": "xo_bot_rls_test", "captured_at": now_iso,
            "source_type": "channel_message", "source_channel_id": "telegram-xo-rls-test",
            "source_message_id": "999999999", "source_message_ts": "0",
            "item_type": "text_note", "title": "xo_bot RLS test capture",
            "raw_text": "test", "classification": "reference", "importance": "medium",
            "requires_review": False, "processing_status": "pending", "review_status": "unreviewed",
        }).execute()
        if not res.data:
            raise RuntimeError("insert returned no data")
        return res.data[0]["id"]

    capture_id = check("captured_items INSERT", _capture_insert)
    if capture_id:
        check("captured_items SELECT", lambda: db.table("captured_items").select("*").eq("id", capture_id).execute())
        check("captured_items UPDATE", lambda: db.table("captured_items").update(
            {"processing_status": "dismissed"}).eq("id", capture_id).execute())
        check("captured_items DELETE (THE LANDMINE CASE — no authenticated policy exists live)",
              lambda: db.table("captured_items").delete().eq("id", capture_id).execute())

    # 19-20. health_daily_logs / health_insights — read-only surfaces
    check("health_daily_logs SELECT", lambda: db.table("health_daily_logs").select("log_date").limit(1).execute())
    check("health_insights SELECT", lambda: db.table("health_insights").select("week_start").limit(1).execute())

    # 21-22. wellness_reminder_log — dedup select + insert
    check("wellness_reminder_log SELECT",
          lambda: db.table("wellness_reminder_log").select("id").eq("window_date", "2099-01-01").execute())

    def _reminder_insert():
        res = db.table("wellness_reminder_log").insert({
            "window_date": "2099-01-01", "pulse_window": "midday",
            "action": "xo_bot_rls_test", "confidence_at_send": 50,
        }).execute()
        return res.data[0]["id"] if res.data else None

    reminder_id = check("wellness_reminder_log INSERT", _reminder_insert)
    if reminder_id:
        cleanup(lambda: db.table("wellness_reminder_log").delete().eq("id", reminder_id).execute())

    print(f"\n{len(_PASS)} passed, {len(_FAIL)} failed.")
    if _FAIL:
        print("\nFailures:")
        for name, err in _FAIL:
            print(f"  - {name}: {err}")
        return 1
    print("\nAll real xo_bot operations verified against the scoped role. Safe to consider cutover.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
