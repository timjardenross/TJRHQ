"""list_active_users() is cached between scheduler ticks and dropped on any
revs_users write from this process (was one Supabase read every 60s)."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

import db


def _client(rows):
    client = MagicMock()
    query = client.table.return_value.select.return_value.eq.return_value
    query.execute.return_value = MagicMock(data=rows)
    return client, query


def setup_function():
    db._invalidate_active_users()


def test_second_tick_is_served_from_cache():
    client, query = _client([{"id": 1, "am_time": "08:00"}])
    assert db.list_active_users(client) == [{"id": 1, "am_time": "08:00"}]
    assert db.list_active_users(client) == [{"id": 1, "am_time": "08:00"}]
    assert query.execute.call_count == 1


def test_update_user_invalidates_so_new_times_apply_next_tick():
    client, query = _client([{"id": 1, "am_time": "08:00"}])
    db.list_active_users(client)
    db.update_user(client, 1, am_time="09:30")
    db.list_active_users(client)
    assert query.execute.call_count == 2


def test_create_and_delete_invalidate():
    client, query = _client([])
    client.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": 2}])
    db.list_active_users(client)
    db.create_user(client, 2, "Sam")
    db.list_active_users(client)
    db.delete_user_cascade(client, 2)
    db.list_active_users(client)
    assert query.execute.call_count == 3


def test_ttl_expiry_refetches():
    client, query = _client([])
    db.list_active_users(client)
    with patch.object(db.time, "monotonic", return_value=db.time.monotonic() + db._ACTIVE_USERS_TTL_SECONDS + 1):
        db.list_active_users(client)
    assert query.execute.call_count == 2


def test_lapsed_pause_is_honoured_from_cache_and_callers_get_copies():
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).isoformat()
    future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat()
    client, _ = _client([{"id": 1, "paused_until": past}, {"id": 2, "paused_until": future}])
    users = db.list_active_users(client)
    assert [u["id"] for u in users] == [1]
    users[0]["am_time"] = "mutated"
    assert "am_time" not in db.list_active_users(client)[0]
