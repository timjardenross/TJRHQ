"""A new Idea mission must be marked seen only AFTER its alert was sent. It used to be marked first and
the send result ignored, so a failed send (for example a Telegram 401) lost the one-time alert for good."""
import sqlite3
from unittest.mock import patch

import pytest

from core.coordination import command_bus as cb


class _Client:
    def __init__(self, rows):
        self.rows = rows

    def select(self, table, columns=None, limit=None):
        return self.rows


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    cb._init_db(c)
    yield c
    c.close()


def _ideas(*ids):
    return [{"mission_id": i, "title": f"Title {i}", "status": "Idea"} for i in ids]


def _seen(conn):
    return {r[0] for r in conn.execute("SELECT mission_id FROM seen_missions")}


def test_successful_send_marks_the_mission_seen(conn):
    with patch.object(cb, "_route", return_value=True) as route:
        cb._rule_new_missions(conn, _Client(_ideas("M1")))
    assert route.call_count == 1 and _seen(conn) == {"M1"}


def test_failed_send_does_not_mark_the_mission_seen(conn):
    with patch.object(cb, "_route", return_value=False):
        cb._rule_new_missions(conn, _Client(_ideas("M1")))
    assert _seen(conn) == set()


def test_failed_send_is_retried_on_the_next_cycle_and_then_marked(conn):
    client = _Client(_ideas("M1"))
    with patch.object(cb, "_route", return_value=False):
        cb._rule_new_missions(conn, client)
    assert _seen(conn) == set()
    with patch.object(cb, "_route", return_value=True) as route:
        cb._rule_new_missions(conn, client)
        cb._rule_new_missions(conn, client)  # already seen: not sent again
    assert route.call_count == 1 and _seen(conn) == {"M1"}


def test_a_failing_transport_stops_the_cycle_after_one_call(conn):
    with patch.object(cb, "_route", return_value=False) as route:
        cb._rule_new_missions(conn, _Client(_ideas("M1", "M2", "M3")))
    assert route.call_count == 1 and _seen(conn) == set()


def test_already_seen_missions_are_not_sent_again(conn):
    conn.execute("INSERT INTO seen_missions (mission_id, first_seen) VALUES ('M1', 'x')")
    conn.commit()
    with patch.object(cb, "_route", return_value=True) as route:
        cb._rule_new_missions(conn, _Client(_ideas("M1", "M2")))
    assert route.call_count == 1 and _seen(conn) == {"M1", "M2"}
