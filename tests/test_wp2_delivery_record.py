"""WP2: durable attempt-level delivery records, ambiguity, restart recovery, duplicate policy (all transports mocked)."""
import threading

import pytest

from intelligence import delivery_record as dr
from intelligence.delivery_record import AttemptKind as K
from intelligence.delivery_record import ChunkResult, InMemoryAttemptStore
from intelligence.delivery_record import DeliveryOutcome as O

TEXT = "A" * 100
BIG = "\n".join(f"para {i} " + "x" * 30 for i in range(9))


def split3(t):  # deterministic splitter: 3 pieces
    n = max(1, len(t) // 3)
    return [t[i:i + n] for i in range(0, len(t), n)][:3] if len(t) > 3 else [t]


class Crash(BaseException):
    """Simulates the process dying mid-send (not an Exception, so nothing swallows it)."""


class Script:
    """Scripted per-call transport behaviour; records every piece it was asked to send (the 'wire')."""
    def __init__(self, *states):
        self.states, self.wire = list(states), []

    def __call__(self, piece):
        self.wire.append(piece)
        st = self.states.pop(0) if self.states else "OK"
        if st == "CRASH":
            raise Crash()
        if st == "RAISE":
            raise TimeoutError("read timed out")
        mid = 100 + len(self.wire)
        return {"OK": ChunkResult(0, "CONFIRMED", message_id=mid, attempts=1),
                "FAIL": ChunkResult(0, "FAILED", error="HTTP 400: bad", attempts=1),
                "UNK": ChunkResult(0, "UNKNOWN", error="TimeoutError", attempts=1)}[st]


def go(store, sender, text=BIG, **kw):
    return dr.deliver("ref", "b1", text, channel="telegram", store=store, split=split3, send_chunk=sender, **kw)


def test_all_chunks_confirmed():
    st, s = InMemoryAttemptStore(), Script()
    r = go(st, s)
    assert r.outcome is O.CONFIRMED and r.rollup.confirmed_chunks == [0, 1, 2] and len(s.wire) == 3
    assert dr.duplicate_report(st.load("ref", "b1", "telegram"))["preventable_duplicates"] == 0


def test_ambiguous_send_timeout_after_request_is_unknown_and_stops():
    st, s = InMemoryAttemptStore(), Script("OK", "RAISE")
    r = go(st, s)
    assert r.outcome is O.PARTIAL and r.rollup.ambiguous_chunks == [1]
    assert len(s.wire) == 2                                    # chunk 3 not blindly sent after an ambiguous chunk
    a = st.load("ref", "b1", "telegram")[0]
    assert [c.state for c in a.chunks] == ["CONFIRMED", "UNKNOWN", "NOT_ATTEMPTED"]


def test_first_chunk_ambiguous_is_unknown_not_failed():
    st = InMemoryAttemptStore()
    assert go(st, Script("UNK")).outcome is O.UNKNOWN


def test_definite_failure_of_every_chunk_is_failed():
    st = InMemoryAttemptStore()
    r = go(st, Script("FAIL", "FAIL", "FAIL"))
    assert r.outcome is O.FAILED


def test_definite_first_chunk_failure_continues_with_the_remaining_chunks():
    """Round 3 (N9): a definite non-delivery does not drop the rest of the brief (legacy behaviour); the gap is recorded as PARTIAL."""
    st, s = InMemoryAttemptStore(), Script("FAIL")
    r = go(st, s)
    assert r.outcome is O.PARTIAL and len(s.wire) == 3 and r.rollup.confirmed_chunks == [1, 2]


def test_partial_chunks_definite_failure():
    st = InMemoryAttemptStore()
    r = go(st, Script("OK", "OK", "FAIL"))
    assert r.outcome is O.PARTIAL and r.rollup.ambiguous_chunks == []


def test_primary_never_sent_twice_after_confirmed():
    st = InMemoryAttemptStore(); s = Script()
    go(st, s)
    r2 = go(st, s)
    assert not r2.sent and r2.preventable_duplicate_prevented and len(s.wire) == 3


@pytest.mark.parametrize("first", [["UNK"], ["OK", "UNK"]])
def test_primary_not_resent_as_primary_after_ambiguity(first):
    st = InMemoryAttemptStore(); s = Script(*first)
    go(st, s); n = len(s.wire)
    r2 = go(st, s)
    assert not r2.sent and len(s.wire) == n


def test_definite_failure_may_be_retried_as_primary_without_marker():
    st, s = InMemoryAttemptStore(), Script("FAIL")
    go(st, s)
    r2 = go(st, s)
    assert r2.sent and r2.outcome is O.CONFIRMED and dr.RECOVERY_MARKER not in s.wire
    assert dr.duplicate_report(st.load("ref", "b1", "telegram"))["preventable_duplicates"] == 0


def test_partial_with_definite_failure_continues_only_missing_chunks():
    st, s = InMemoryAttemptStore(), Script("OK", "FAIL")
    go(st, s)
    plan = dr.plan_recovery(st.load("ref", "b1", "telegram"))
    assert plan.allowed and plan.chunk_indexes == [1]            # chunk 2 already went out after the definite failure of chunk 1
    r2 = go(st, s)
    assert r2.outcome is O.CONFIRMED and r2.rollup.confirmed_chunks == [0, 1, 2]
    assert len(s.wire) == 3 + 1                                 # chunks 0 and 2 were NOT sent again


def test_authorised_recovery_resend_is_marked_recorded_and_disclosed():
    st, s = InMemoryAttemptStore(), Script("OK", "UNK")
    go(st, s)
    plan = dr.plan_recovery(st.load("ref", "b1", "telegram"))
    assert plan.allowed and plan.chunk_indexes == [1, 2]
    r2 = go(st, s, kind=K.AUTHORISED_RECOVERY_RESEND, authorised_by=dr.POLICY_AUTHORISER)
    assert r2.sent and s.wire[2].startswith(dr.RECOVERY_MARKER + "\n\n") and len(s.wire) == 4   # marker merged into the first resent chunk
    attempts = st.load("ref", "b1", "telegram")
    assert [a.kind for a in attempts] == [K.PRIMARY, K.AUTHORISED_RECOVERY_RESEND]   # both attempts recorded
    roll = dr.rollup(attempts)
    assert roll.outcome is O.CONFIRMED and roll.possible_duplicate_chunks == [1]
    assert "may have been delivered twice" in roll.disclosure and roll.recovery_resends == 1
    rep = dr.duplicate_report(attempts)
    assert rep["preventable_duplicates"] == 0 and rep["authorised_recovery_resends"] == 1 and rep["exactly_once_claimed"] is False


def test_resend_requires_authorisation():
    st = InMemoryAttemptStore(); s = Script("UNK")
    go(st, s)
    r = go(st, s, kind=K.AUTHORISED_RECOVERY_RESEND)
    assert not r.sent and r.refused_reason == "resend_not_authorised"


def test_resend_without_prior_ambiguity_refused():
    st = InMemoryAttemptStore(); s = Script("FAIL")
    go(st, s)
    r = go(st, s, kind=K.AUTHORISED_RECOVERY_RESEND, authorised_by=dr.POLICY_AUTHORISER)
    assert not r.sent and r.preventable_duplicate_prevented
    r0 = go(InMemoryAttemptStore(), s, kind=K.AUTHORISED_RECOVERY_RESEND, authorised_by=dr.POLICY_AUTHORISER)
    assert r0.refused_reason == "resend_without_prior_attempt"


def test_resend_of_confirmed_refused():
    st = InMemoryAttemptStore(); s = Script()
    go(st, s)
    r = go(st, s, kind=K.AUTHORISED_RECOVERY_RESEND, authorised_by=dr.POLICY_AUTHORISER)
    assert not r.sent and r.refused_reason == "resend_of_confirmed"


def test_only_one_resend_per_ambiguity():
    st = InMemoryAttemptStore(); s = Script("UNK", "OK", "UNK")
    go(st, s)
    go(st, s, kind=K.AUTHORISED_RECOVERY_RESEND, authorised_by=dr.POLICY_AUTHORISER)     # marker ok, chunk0 ambiguous again
    r3 = go(st, s, kind=K.AUTHORISED_RECOVERY_RESEND, authorised_by=dr.POLICY_AUTHORISER)
    assert not r3.sent


def test_failed_first_resent_chunk_keeps_the_marker_for_the_next_one_and_never_sends_it_alone():
    st = InMemoryAttemptStore(); s = Script("UNK", "FAIL", "FAIL", "FAIL")
    go(st, s)
    r = go(st, s, kind=K.AUTHORISED_RECOVERY_RESEND, authorised_by=dr.POLICY_AUTHORISER)
    assert r.outcome is O.FAILED and len(s.wire) == 1 + 3
    assert all(w.startswith(dr.RECOVERY_MARKER) and "\n\n" in w for w in s.wire[1:])


def test_restart_mid_send_persisted_state_and_recovery():
    st, s = InMemoryAttemptStore(), Script("OK", "CRASH")
    with pytest.raises(Crash):
        go(st, s)
    reborn = InMemoryAttemptStore(st.snapshot())                       # new process, durable state only
    a = reborn.load("ref", "b1", "telegram")[0]
    assert a.state == "sending" and [c.state for c in a.chunks] == ["CONFIRMED"]
    s2 = Script()
    blocked = go(reborn, s2)                                           # a restarted sender must not just send again
    assert not blocked.sent and blocked.refused_reason == "attempt_in_flight_or_interrupted" and s2.wire == []
    fixed = dr.recover_interrupted("ref", "b1", "telegram", reborn)
    assert fixed and fixed[0].outcome is O.PARTIAL
    assert [c.state for c in fixed[0].chunks] == ["CONFIRMED", "UNKNOWN", "NOT_ATTEMPTED"]
    plan = dr.plan_recovery(reborn.load("ref", "b1", "telegram"))
    assert plan.allowed and plan.chunk_indexes == [1, 2]
    r = go(reborn, s2, kind=K.AUTHORISED_RECOVERY_RESEND, authorised_by=dr.POLICY_AUTHORISER)
    assert r.rollup.outcome is O.CONFIRMED and len(s2.wire) == 2 and s2.wire[0].startswith(dr.RECOVERY_MARKER)   # 2 chunks (marker merged), chunk 0 untouched


def test_crash_before_any_chunk_is_unknown_after_recovery():
    st, s = InMemoryAttemptStore(), Script("CRASH")
    with pytest.raises(Crash):
        go(st, s)
    reborn = InMemoryAttemptStore(st.snapshot())
    fixed = dr.recover_interrupted("ref", "b1", "telegram", reborn)
    assert fixed[0].outcome is O.UNKNOWN


def test_reconcile_without_provider_lookup_is_unconfirmed_never_confirmed():
    st = InMemoryAttemptStore()
    go(st, Script("UNK"))
    dr.reconcile(st.load("ref", "b1", "telegram"), st)
    roll = dr.rollup(st.load("ref", "b1", "telegram"))
    assert roll.outcome is O.UNCONFIRMED
    # an UNCONFIRMED brief is still eligible for the one marked resend
    assert dr.plan_recovery(st.load("ref", "b1", "telegram")).allowed


def test_reconcile_with_provider_proof_can_confirm():
    st = InMemoryAttemptStore()
    go(st, Script("UNK"), text="B" * 3)         # single piece
    dr.reconcile(st.load("ref", "b1", "telegram"), st, lookup=lambda a, c: 4242)
    assert dr.rollup(st.load("ref", "b1", "telegram")).outcome is O.CONFIRMED


def test_concurrent_senders_only_one_claims():
    st = InMemoryAttemptStore(); wire = []
    gate = threading.Barrier(8)

    def sender(piece):
        wire.append(piece)
        return ChunkResult(0, "CONFIRMED", message_id=1, attempts=1)

    def worker():
        gate.wait()
        go(st, sender)

    ts = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(wire) == 3                                           # exactly one sender transmitted the brief
    assert dr.duplicate_report(st.load("ref", "b1", "telegram"))["preventable_duplicates"] == 0


def test_new_content_is_a_new_version_not_a_duplicate():
    st, s = InMemoryAttemptStore(), Script()
    go(st, s)
    r = go(st, s, text=BIG + " corrected")
    assert r.sent


def test_chunking_change_blocks_resend():
    st = InMemoryAttemptStore(); s = Script("UNK")
    go(st, s)
    r = dr.deliver("ref", "b1", BIG, channel="telegram", store=st, split=lambda t: [t], send_chunk=s,
                   kind=K.AUTHORISED_RECOVERY_RESEND, authorised_by=dr.POLICY_AUTHORISER)
    assert r.refused_reason == "chunking_changed_since_primary"


def test_duplicate_report_flags_a_forged_preventable_duplicate():
    st, s = InMemoryAttemptStore(), Script()
    go(st, s)
    rows = st.snapshot()
    import copy
    forged = copy.deepcopy(rows[0]); forged.update(attempt_id="zz", attempt_no=2, started_at="9999")
    rep = dr.duplicate_report([dr.AttemptRecord.from_row(r) for r in rows + [forged]])
    assert rep["preventable_duplicates"] >= 1 and "primary_sent_more_than_once" in rep["preventable_detail"]


def test_row_roundtrip_is_lossless():
    st, s = InMemoryAttemptStore(), Script("OK", "UNK")
    go(st, s)
    a = st.load("ref", "b1", "telegram")[0]
    assert dr.AttemptRecord.from_row(a.to_row()).to_row() == a.to_row()


def test_flags_default_off(monkeypatch):
    for f in (dr.FLAG, dr.AUTO_RESEND_FLAG):
        monkeypatch.delenv(f, raising=False)
    assert not dr.enabled() and not dr.auto_resend_enabled()
    monkeypatch.setenv(dr.AUTO_RESEND_FLAG, "1")
    assert not dr.auto_resend_enabled()          # auto resend never active without the record flag
