"""Delivery attempts are append-only: conditional store updates, forward-only transitions, stale writers refused (mocked transport)."""
import copy
import json
import sys
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_wp2_delivery_record import Script, go

from intelligence import delivery_record as dr
from intelligence.delivery_record import DeliveryOutcome as O
from intelligence.delivery_record import InMemoryAttemptStore


def test_confirmed_attempt_cannot_be_rewritten_by_a_stale_copy():
    st, s = InMemoryAttemptStore(), Script()
    go(st, s)
    stored = st.load("ref", "b1", "telegram")[0]
    assert stored.outcome is O.CONFIRMED
    stale = copy.deepcopy(stored)
    stale.outcome, stale.chunks = O.FAILED, []
    with pytest.raises(dr.AttemptConflict):
        st.update(stale)
    assert st.load("ref", "b1", "telegram")[0].outcome is O.CONFIRMED
    assert len(st.load("ref", "b1", "telegram")[0].chunks) == 3


def test_stale_in_memory_copy_is_refused_even_for_a_permitted_transition():
    st, s = InMemoryAttemptStore(), Script("UNK")
    go(st, s)
    a, b = st.load("ref", "b1", "telegram")[0], st.load("ref", "b1", "telegram")[0]
    a.outcome = O.UNCONFIRMED
    st.update(a)                    # first reconciler wins
    b.outcome = O.UNCONFIRMED
    with pytest.raises(dr.AttemptConflict, match="stale_update"):
        st.update(b)                # second still holds the pre-image: refused, not a lost update


def test_update_requires_a_claimed_attempt_no_upsert():
    st = InMemoryAttemptStore()
    rec = dr.AttemptRecord("ref", "b1", "telegram", "h")
    with pytest.raises(dr.AttemptConflict, match="unknown_attempt"):
        st.update(rec)


@pytest.mark.parametrize("old,new,ok", [
    ("UNKNOWN", "UNCONFIRMED", True), ("UNKNOWN", "PARTIAL", True), ("UNKNOWN", "CONFIRMED", True),
    ("UNCONFIRMED", "CONFIRMED", True), ("PARTIAL", "CONFIRMED", True),
    ("CONFIRMED", "FAILED", False), ("CONFIRMED", "UNKNOWN", False), ("FAILED", "CONFIRMED", False),
    ("PARTIAL", "UNKNOWN", False), ("UNCONFIRMED", "UNKNOWN", False), ("UNKNOWN", "FAILED", False),
])
def test_outcome_transition_table(old, new, ok):
    row = {"attempt_id": "a", "state": "finished", "outcome": old, "finished_at": "t", "chunks": []}
    nrow = dict(row, outcome=new)
    assert (dr.check_transition(row, nrow) is None) is ok


def test_confirmed_chunk_and_identity_and_reopen_rules():
    base = {"attempt_id": "a", "state": "sending", "outcome": None, "finished_at": None, "attempt_no": 1,
            "chunks": [{"index": 0, "state": "CONFIRMED", "message_id": 5}]}
    assert dr.check_transition(base, dict(base, chunks=base["chunks"] + [{"index": 1, "state": "FAILED"}])) is None
    assert dr.check_transition(base, dict(base, chunks=[])) == "chunk_history_cannot_shrink"
    assert dr.check_transition(base, dict(base, chunks=[{"index": 0, "state": "CONFIRMED", "message_id": 6}])) == "confirmed_chunk_cannot_change"
    assert dr.check_transition(base, dict(base, attempt_no=2)) == "identity_columns_immutable"
    done = dict(base, state="finished", outcome="PARTIAL", finished_at="t")
    assert dr.check_transition(done, dict(done, state="sending")) == "finished_attempt_cannot_reopen"


def test_deliver_stops_and_leaves_stored_record_when_a_concurrent_actor_moved_the_attempt():
    st, s = InMemoryAttemptStore(), Script()
    real_update = st.update
    calls = {"n": 0}

    def racing_update(rec):
        calls["n"] += 1
        if calls["n"] == 2:          # after the first chunk another actor (restart recovery) finished the attempt
            st.load(rec.brief_table, rec.brief_id, rec.channel)[0]
            dr.recover_interrupted(rec.brief_table, rec.brief_id, rec.channel, st)
        return real_update(rec)

    st.update = racing_update
    r = go(st, s)
    assert r.refused_reason == "update_refused_stale_attempt"
    assert len(s.wire) < 3                                    # nothing more was sent after the refusal
    stored = st.load("ref", "b1", "telegram")[0]
    assert stored.state == "finished" and stored.outcome in (O.UNKNOWN, O.PARTIAL)


def test_reconcile_never_overwrites_a_newer_stored_outcome():
    st, s = InMemoryAttemptStore(), Script("UNK")
    go(st, s)
    mine = st.load("ref", "b1", "telegram")
    theirs = st.load("ref", "b1", "telegram")
    changed = dr.reconcile(theirs, st)
    assert [a.outcome for a in changed] == [O.UNCONFIRMED]
    assert dr.reconcile(mine, st) == []          # stale pre-image: refused quietly, stored UNCONFIRMED kept
    assert st.load("ref", "b1", "telegram")[0].outcome is O.UNCONFIRMED


# -- the PostgREST store never upserts -----------------------------------------------------------------------------------

class FakeResp:
    def __init__(self, body):
        self._b = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._b


def _rec(outcome=None, state="sending"):
    r = dr.AttemptRecord("ref", "b1", "telegram", "h")
    r.state, r.outcome = state, outcome
    r._persisted = ("sending", None)
    return r


def test_postgrest_update_is_a_conditional_patch_of_mutable_columns_only():
    seen = {}

    def fake(req, timeout=0):
        seen["url"], seen["method"], seen["body"] = req.full_url, req.get_method(), json.loads(req.data)
        return FakeResp(b'[{"attempt_id":"x"}]')

    store = dr.PostgrestAttemptStore("https://example.invalid", "k")
    with mock.patch("urllib.request.urlopen", fake):
        store.update(_rec())
    assert seen["method"] == "PATCH"
    assert "on_conflict" not in seen["url"] and "merge-duplicates" not in str(seen)
    assert "state=eq.sending" in seen["url"] and "outcome=is.null" in seen["url"] and "attempt_id=eq." in seen["url"]
    assert set(seen["body"]) == {"chunks", "state", "outcome", "reason", "finished_at"}      # identity columns never sent


def test_postgrest_update_no_match_is_a_stale_conflict():
    store = dr.PostgrestAttemptStore("https://example.invalid", "k")
    with mock.patch("urllib.request.urlopen", lambda req, timeout=0: FakeResp(b"[]")):  # noqa: SIM117 - nested contexts kept for readability
        with pytest.raises(dr.AttemptConflict, match="stale_update"):
            store.update(_rec())


@pytest.mark.parametrize("code", [400, 409])
def test_postgrest_update_trigger_refusal_is_a_conflict_other_errors_propagate(code):
    store = dr.PostgrestAttemptStore("https://example.invalid", "k")

    def refuse(req, timeout=0):
        raise urllib.error.HTTPError("u", code, "x", {}, BytesIO(b"{}"))

    with mock.patch("urllib.request.urlopen", refuse):  # noqa: SIM117 - nested contexts kept for readability
        with pytest.raises(dr.AttemptConflict):
            store.update(_rec())

    def boom(req, timeout=0):
        raise urllib.error.HTTPError("u", 500, "x", {}, BytesIO(b"{}"))

    with mock.patch("urllib.request.urlopen", boom):  # noqa: SIM117 - nested contexts kept for readability
        with pytest.raises(urllib.error.HTTPError):
            store.update(_rec())


def test_postgrest_update_filter_follows_the_loaded_state_for_forward_transitions():
    seen = {}

    def fake(req, timeout=0):
        seen["url"] = req.full_url
        return FakeResp(b'[{"attempt_id":"x"}]')

    r = dr.AttemptRecord("ref", "b1", "telegram", "h")
    r._persisted = ("finished", "UNKNOWN")
    r.state, r.outcome = "finished", O.UNCONFIRMED
    with mock.patch("urllib.request.urlopen", fake):
        dr.PostgrestAttemptStore("https://example.invalid", "k").update(r)
    assert "state=eq.finished" in seen["url"] and "outcome=eq.UNKNOWN" in seen["url"]
    assert r._persisted == ("finished", "UNCONFIRMED")
