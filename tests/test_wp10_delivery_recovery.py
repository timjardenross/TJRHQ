"""WP10: durable delivery recovery job. Report-only by default; apply behind default-OFF flags; idempotent,
restart-safe, HOLD-window and kill-switch aware; one marked resend per brief version. Every transport is a script:
nothing is sent."""
from __future__ import annotations

import json
import pathlib
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from intelligence import delivery_record as dr
from intelligence import delivery_recovery as rec
from intelligence.delivery_record import ChunkResult
from intelligence.delivery_recovery import InMemoryRecoveryStore

MEL = ZoneInfo("Australia/Melbourne")
NOW = datetime(2026, 11, 26, 10, 0, tzinfo=MEL).astimezone(timezone.utc)      # AEDT, outside every HOLD window
TEXT = "\n".join(f"para {i} " + "x" * 30 for i in range(9))
HASH = dr.content_hash(TEXT)
TABLE, BID, CH = "captains_daily_briefs", "b-1", "telegram"


def split3(t):
    n = max(1, len(t) // 3)
    return [t[i:i + n] for i in range(0, len(t), n)][:3]


class Crash(BaseException):
    pass


class Script:
    def __init__(self, *states):
        self.states, self.wire = list(states), []

    def __call__(self, piece):
        self.wire.append(piece)
        st = self.states.pop(0) if self.states else "OK"
        if st == "CRASH":
            raise Crash()
        n = len(self.wire)
        return {"OK": ChunkResult(0, "CONFIRMED", message_id=100 + n, attempts=1),
                "FAIL": ChunkResult(0, "FAILED", error="HTTP 400: bad", attempts=1),
                "UNK": ChunkResult(0, "UNKNOWN", error="TimeoutError", attempts=1)}[st]


class CountingStore(InMemoryRecoveryStore):
    """Counts writes so report-only can be proved write-free."""
    def __init__(self, rows=None):
        super().__init__(rows)
        self.writes = 0
        self.list_calls = 0

    def claim(self, r):
        self.writes += 1
        super().claim(r)

    def update(self, r):
        self.writes += 1
        super().update(r)

    def list_recent(self, since):
        self.list_calls += 1
        return super().list_recent(since)


class _VClock:
    """Virtual wall clock for delivery_record's timestamps (dr.utcnow reads dr.datetime), so seeded and job-created
    records live on the same timeline as the job's injected clock. Strictly increasing by 1 ms per read."""
    t = NOW

    @classmethod
    def now(cls, tz=None):
        cls.t = cls.t + timedelta(milliseconds=1)
        return cls.t.astimezone(tz) if tz else cls.t.replace(tzinfo=None)


class _FakeDT(datetime):
    @classmethod
    def now(cls, tz=None):
        return _VClock.now(tz)


@pytest.fixture(autouse=True)
def vclock(monkeypatch):
    monkeypatch.setattr(dr, "datetime", _FakeDT)
    _VClock.t = NOW
    return _VClock


def seed(*states, age_minutes=60, text=TEXT, bid=BID, store_cls=CountingStore, kind=dr.AttemptKind.PRIMARY, prior=None):
    """Run a real (scripted) primary delivery and freeze its records ``age_minutes`` before NOW."""
    base = store_cls()
    sender = Script(*states)
    _VClock.t = NOW - timedelta(minutes=age_minutes)
    dr.deliver(TABLE, bid, text, channel=CH, store=base, split=split3, send_chunk=sender)
    _VClock.t = NOW
    return base, sender


def flags(monkeypatch, apply=True):
    monkeypatch.delenv(rec.KILL_SWITCH, raising=False)
    if apply:
        monkeypatch.setenv(dr.FLAG, "1")
        monkeypatch.setenv(dr.AUTO_RESEND_FLAG, "1")
        monkeypatch.setenv(rec.APPLY_FLAG, "1")
    else:
        for k in (dr.FLAG, dr.AUTO_RESEND_FLAG, rec.APPLY_FLAG):
            monkeypatch.delenv(k, raising=False)


def run(store, *, send=None, loader=lambda t, b: TEXT, apply=None, now=NOW):
    send = send or Script()
    _VClock.t = now
    return rec.run_recovery(store=store, clock=lambda: now, apply=apply, text_loader=loader, send_chunk=send, split=split3), send


def item(report, i=0):
    return report["items"][i]


# ------------------------------------------------------------------------------------------------ report only

def test_report_only_is_default_and_writes_nothing(monkeypatch):
    flags(monkeypatch, apply=False)
    store, _ = seed("OK", "UNK")
    before = store.snapshot()
    store.writes = 0
    loads = []
    r, send = run(store, loader=lambda t, b: loads.append(1) or TEXT)
    assert r["mode"] == "report_only" and r["status"] == "ok"
    assert item(r)["action"] == "authorised_resend_due" and item(r)["outcome"] == "PARTIAL"
    assert send.wire == [] and loads == [] and store.writes == 0 and store.snapshot() == before
    assert r["needs_attention"] is True and r["counts"]["due_authorised_resend"] == 1 and r["counts"]["sent"] == 0


def test_explicit_apply_true_cannot_override_missing_flags(monkeypatch):
    flags(monkeypatch, apply=False)
    store, _ = seed("OK", "UNK")
    r, send = run(store, apply=True)
    assert r["mode"] == "report_only" and send.wire == []


@pytest.mark.parametrize("missing", [rec.APPLY_FLAG, dr.AUTO_RESEND_FLAG, dr.FLAG])
def test_apply_needs_all_three_flags(monkeypatch, missing):
    flags(monkeypatch)
    monkeypatch.delenv(missing)
    store, _ = seed("OK", "UNK")
    r, send = run(store)
    assert r["mode"] == "report_only" and send.wire == []


def test_apply_false_param_forces_report_only(monkeypatch):
    flags(monkeypatch)
    store, _ = seed("OK", "UNK")
    r, send = run(store, apply=False)
    assert r["mode"] == "report_only" and send.wire == []


def test_report_only_twice_gives_same_report(monkeypatch):
    flags(monkeypatch, apply=False)
    store, _ = seed("OK", "UNK")
    a, _ = run(store)
    b, _ = run(store)
    a.pop("generated_at"), b.pop("generated_at")
    assert a == b


def test_report_only_projects_interrupted_without_writing(monkeypatch):
    flags(monkeypatch, apply=False)
    base = CountingStore()
    s = Script("OK", "CRASH")
    _VClock.t = NOW - timedelta(minutes=60)
    with pytest.raises(Crash):
        dr.deliver(TABLE, BID, TEXT, channel=CH, store=base, split=split3, send_chunk=s)
    store = base
    before = store.snapshot()
    store.writes = 0
    r, _ = run(store)
    assert item(r)["action"] == "authorised_resend_due" and item(r)["would_recover_interrupted"] == 1
    assert store.writes == 0 and store.snapshot() == before


def test_confirmed_delivery_needs_no_action(monkeypatch):
    flags(monkeypatch)
    store, _ = seed("OK", "OK", "OK")
    r, send = run(store)
    assert item(r)["action"] == "confirmed" and not r["needs_attention"] and send.wire == []


# ------------------------------------------------------------------------------------------------ apply

def test_apply_makes_exactly_one_marked_resend_and_second_run_refuses(monkeypatch):
    flags(monkeypatch)
    store, _ = seed("OK", "UNK")
    r, send = run(store)
    assert r["mode"] == "apply" and item(r)["apply_result"] == "sent:CONFIRMED" and r["counts"]["sent"] == 1
    pieces = split3(TEXT)
    assert send.wire == [dr.RECOVERY_MARKER + "\n\n" + pieces[1], pieces[2]]   # marker merged into the first resent chunk; ONLY the unconfirmed chunks
    roll = dr.rollup(store.load(TABLE, BID, CH))
    assert roll.outcome is dr.DeliveryOutcome.CONFIRMED and roll.recovery_resends == 1
    assert "may have been delivered twice" in roll.disclosure
    r2, send2 = run(store)
    assert send2.wire == [] and item(r2)["action"] == "confirmed" and r["preventable_duplicates"] == 0 == r2["preventable_duplicates"]


def test_resend_that_is_itself_ambiguous_is_not_retried_again(monkeypatch):
    flags(monkeypatch)
    store, _ = seed("UNK")
    r, _send = run(store, send=Script("OK", "UNK"))          # marker ok, chunk ambiguous again
    assert item(r)["apply_result"].startswith("sent:")
    for _ in range(3):
        r2, send2 = run(store)
        assert send2.wire == [] and item(r2)["action"] == "refused" and item(r2)["plan_reason"] == "resend_already_made"
        assert r2["needs_attention"] is True and item(r2)["preventable_duplicate_prevented"] is True
    assert sum(1 for a in store.load(TABLE, BID, CH) if a.kind is dr.AttemptKind.AUTHORISED_RECOVERY_RESEND) == 1


def test_apply_skips_when_stored_text_changed_or_missing(monkeypatch):
    flags(monkeypatch)
    store, _ = seed("OK", "UNK")
    r, send = run(store, loader=lambda t, b: TEXT + " edited")
    assert item(r)["apply_result"] == "skipped_content_unavailable_or_changed" and send.wire == []
    r, send = run(store, loader=lambda t, b: None)
    assert item(r)["apply_result"] == "skipped_content_unavailable_or_changed" and send.wire == []
    r = rec.run_recovery(store=store, clock=lambda: NOW, send_chunk=Script(), split=split3)       # no loader at all
    assert item(r)["apply_result"] == "skipped_no_text_loader"
    r, send = run(store, loader=lambda t, b: (_ for _ in ()).throw(OSError("db down")))
    assert item(r)["apply_result"].startswith("skipped_text_load_failed") and send.wire == []


def test_definite_failure_continues_as_plain_primary_without_marker(monkeypatch):
    flags(monkeypatch)
    store, _ = seed("OK", "FAIL")
    r, send = run(store)
    assert item(r)["action"] == "continue_due" and item(r)["apply_result"] == "sent:CONFIRMED"
    assert send.wire == split3(TEXT)[1:2]          # round 3: chunk 2 went out after the definite failure of chunk 1; only chunk 1 is missing
    assert all(dr.RECOVERY_MARKER not in w for w in send.wire)
    r2, send2 = run(store)
    assert send2.wire == [] and item(r2)["action"] == "confirmed"


def test_brief_older_than_max_age_is_reported_not_resent(monkeypatch):
    flags(monkeypatch)
    store, _ = seed("OK", "UNK", age_minutes=rec.MAX_RECOVERY_AGE_HOURS * 60 + 5)
    r, send = run(store)
    assert item(r)["action"] == "expired" and "apply_result" not in item(r) and send.wire == [] and r["needs_attention"]


def test_fresh_ambiguity_waits_before_resend(monkeypatch):
    flags(monkeypatch)
    store, _ = seed("OK", "UNK", age_minutes=rec.MIN_AMBIGUITY_AGE_MINUTES - 5)
    r, send = run(store)
    assert item(r)["action"] == "authorised_resend_due" and item(r)["apply_result"] == "waiting_ambiguity_age" and send.wire == []
    later = NOW + timedelta(minutes=10)
    r, send = run(store, now=later)
    assert item(r)["apply_result"] == "sent:CONFIRMED"


def test_max_sends_per_run(monkeypatch):
    flags(monkeypatch)
    rows = []
    for i in range(rec.MAX_SENDS_PER_RUN + 1):
        s, _ = seed("UNK", bid=f"b-{i}")
        rows += s.snapshot()
    store = CountingStore(rows)
    r, _send = run(store)
    assert r["counts"]["sent"] == rec.MAX_SENDS_PER_RUN
    assert sum(1 for it in r["items"] if it.get("apply_result") == "deferred_run_limit") == 1


def test_concurrent_runs_cannot_both_resend(monkeypatch):
    flags(monkeypatch)
    store, _ = seed("OK", "UNK")
    sends = [Script() for _ in range(6)]
    out = []

    def go(s):
        out.append(run(store, send=s)[0])

    ts = [threading.Thread(target=go, args=(s,)) for s in sends]
    [t.start() for t in ts]
    [t.join() for t in ts]
    markers = sum(w.startswith(dr.RECOVERY_MARKER) for s in sends for w in s.wire)
    assert markers == 1
    assert dr.duplicate_report(store.load(TABLE, BID, CH))["preventable_duplicates"] == 0


# ------------------------------------------------------------------------------------------------ HOLD / kill switch

@pytest.mark.parametrize("h,m,expect", [(6, 54, None), (6, 55, "06:55-07:10"), (7, 0, "06:55-07:10"), (7, 10, "06:55-07:10"), (7, 11, None),
                                         (12, 24, None), (12, 25, "12:25-12:40"), (12, 40, "12:25-12:40"), (12, 41, None),
                                         (17, 54, None), (17, 55, "17:55-18:10"), (18, 10, "17:55-18:10"), (18, 11, None)])
@pytest.mark.parametrize("month", [(2026, 11, 26), (2026, 7, 15)])      # AEDT and AEST: the wall clock is what counts
def test_hold_window_boundaries_melbourne_wall_clock(month, h, m, expect):
    now = datetime(*month, h, m, tzinfo=MEL).astimezone(timezone.utc)
    assert rec.hold_window(now) == expect


def test_hold_window_run_reads_and_sends_nothing(monkeypatch):
    flags(monkeypatch)
    store, _ = seed("OK", "UNK")
    held_now = datetime(2026, 11, 26, 7, 0, tzinfo=MEL).astimezone(timezone.utc)
    store.list_calls = store.writes = 0
    r, send = run(store, now=held_now)
    assert r["status"] == "held" and r["hold_window"] == "06:55-07:10" and send.wire == [] and store.list_calls == 0 and store.writes == 0


def test_run_that_drifts_into_hold_window_stops_before_sending(monkeypatch):
    flags(monkeypatch)
    store, _ = seed("OK", "UNK")
    times = iter([NOW, datetime(2026, 11, 26, 12, 30, tzinfo=MEL).astimezone(timezone.utc)] + [NOW] * 10)
    r = rec.run_recovery(store=store, clock=lambda: next(times), text_loader=lambda t, b: TEXT, send_chunk=(s := Script()), split=split3)
    assert item(r)["apply_result"] == "skipped_hold_window" and s.wire == []


def test_kill_switch_disables_everything(monkeypatch):
    flags(monkeypatch)
    monkeypatch.setenv(rec.KILL_SWITCH, "1")
    store, _ = seed("OK", "UNK")
    store.list_calls = 0
    r, send = run(store)
    assert r["status"] == "disabled" and r["kill_switch"] is True and send.wire == [] and store.list_calls == 0


def test_kill_switch_flipped_mid_run_stops_sending(monkeypatch):
    flags(monkeypatch)
    rows = []
    for i in range(2):
        s, _ = seed("UNK", bid=f"b-{i}")
        rows += s.snapshot()
    store = CountingStore(rows)

    def loader(t, b):
        monkeypatch.setenv(rec.KILL_SWITCH, "1")       # operator flips the switch while the run is in progress
        return TEXT
    r, send = run(store, loader=loader)
    assert [it["apply_result"] for it in r["items"]] == ["skipped_kill_switch", "deferred_run_limit"]
    assert send.wire == []


# ------------------------------------------------------------------------------------------------ restart safety / interruption matrix

def _interrupted(states, crash_on_update=None, age=60):
    """Run a delivery that dies (BaseException) mid-send and return the durable rows frozen ``age`` minutes before NOW."""
    base = CountingStore()
    if crash_on_update is not None:
        n = {"i": 0}
        orig = base.update

        def upd(r):
            n["i"] += 1
            if n["i"] == crash_on_update:
                base.update = orig                      # the process died once; the restarted job writes normally
                raise Crash()
            orig(r)
        base.update = upd
    _VClock.t = NOW - timedelta(minutes=age)
    with pytest.raises(Crash):
        dr.deliver(TABLE, BID, TEXT, channel=CH, store=base, split=split3, send_chunk=Script(*states))
    return base


def test_restart_new_process_same_decisions_from_durable_state_only(monkeypatch):
    flags(monkeypatch, apply=False)
    store, _ = seed("OK", "UNK")
    a, _ = run(store)
    reborn = CountingStore(store.snapshot())            # new process: nothing but the rows
    b, _ = run(reborn)
    a.pop("generated_at"), b.pop("generated_at")
    assert a == b


def test_restart_between_apply_runs_does_not_resend(monkeypatch):
    flags(monkeypatch)
    store, _ = seed("OK", "UNK")
    run(store)
    reborn = CountingStore(store.snapshot())
    r, send = run(reborn)
    assert send.wire == [] and item(r)["action"] == "confirmed"


def test_matrix_before_acceptance_claim_only(monkeypatch):
    """Crash after the attempt was claimed but before any request was written: indistinguishable from 'during', so it is
    treated as ambiguous and gets the one marked resend of ALL chunks."""
    flags(monkeypatch)
    store = _interrupted(["CRASH"])
    r, send = run(store)
    pc = split3(TEXT)
    assert send.wire == [dr.RECOVERY_MARKER + "\n\n" + pc[0], pc[1], pc[2]] and item(r)["apply_result"] == "sent:CONFIRMED"
    assert run(store)[1].wire == []


def test_matrix_during_acceptance_confirmed_prefix_not_resent(monkeypatch):
    flags(monkeypatch)
    store = _interrupted(["OK", "CRASH"])
    _r, send = run(store)
    pc = split3(TEXT)
    assert send.wire == [dr.RECOVERY_MARKER + "\n\n" + pc[1], pc[2]]
    assert dr.rollup(store.load(TABLE, BID, CH)).outcome is dr.DeliveryOutcome.CONFIRMED


def test_matrix_after_acceptance_before_record_is_disclosed_as_possible_duplicate(monkeypatch):
    """Provider accepted chunk 1 but the process died before recording it (store.update #2 never lands)."""
    flags(monkeypatch)
    store = _interrupted(["OK", "OK", "OK"], crash_on_update=3)
    pre = {c.index: c.state for a in store.load(TABLE, BID, CH) for c in a.chunks}
    assert 2 not in pre                                  # chunk 2 was accepted by the provider but never recorded
    _r, send = run(store)
    roll = dr.rollup(store.load(TABLE, BID, CH))
    assert send.wire[0].startswith(dr.RECOVERY_MARKER) and roll.recovery_resends == 1
    assert "chunk(s) [2] may have been delivered twice" in roll.disclosure
    assert dr.duplicate_report(store.load(TABLE, BID, CH))["preventable_duplicates"] == 0


def test_matrix_after_everything_confirmed_but_not_finished_needs_no_resend(monkeypatch):
    flags(monkeypatch)
    base = CountingStore()
    orig = base.update
    state = {"n": 0}
    _VClock.t = NOW - timedelta(minutes=60)

    def upd(r):
        state["n"] += 1
        if r.state == "finished":
            base.update = orig                           # all chunks recorded, dies before the finish write (once)
            raise Crash()
        orig(r)
    base.update = upd
    with pytest.raises(Crash):
        dr.deliver(TABLE, BID, TEXT, channel=CH, store=base, split=split3, send_chunk=Script())
    store = base
    r, send = run(store)
    assert send.wire == [] and item(r)["action"] == "confirmed" and item(r)["outcome"] == "CONFIRMED"


def test_live_send_inside_grace_period_is_left_alone(monkeypatch):
    flags(monkeypatch)
    store = _interrupted(["OK", "CRASH"], age=rec.STALE_INTERRUPTED_MINUTES - 5)
    before = store.snapshot()
    store.writes = 0
    r, send = run(store)
    assert item(r)["action"] == "in_flight_wait" and send.wire == [] and store.writes == 0 and store.snapshot() == before


def test_interrupted_attempt_is_recovered_in_apply_mode_and_persisted(monkeypatch):
    flags(monkeypatch)
    store = _interrupted(["OK", "CRASH"])
    run(store, send=Script("UNK"))          # marker itself ambiguous
    attempts = store.load(TABLE, BID, CH)
    assert all(a.state == "finished" for a in attempts)
    assert [c.state for c in attempts[0].chunks] == ["CONFIRMED", "UNKNOWN", "NOT_ATTEMPTED"]
    assert attempts[0].chunks[1].error == "interrupted_in_flight"


# ------------------------------------------------------------------------------------------------ fail safe and report contract

def test_unreadable_store_reports_error_and_sends_nothing(monkeypatch):
    flags(monkeypatch)

    class Broken(InMemoryRecoveryStore):
        def list_recent(self, since):
            raise OSError("404 table missing")
    s = Script()
    r = rec.run_recovery(store=Broken(), clock=lambda: NOW, text_loader=lambda t, b: TEXT, send_chunk=s, split=split3)
    assert r["status"] == "error" and r["errors"] == ["list_recent:OSError"] and r["needs_attention"] and s.wire == []


def test_mid_apply_store_failure_halts_the_run(monkeypatch):
    flags(monkeypatch)
    rows = []
    for i in range(2):
        s, _ = seed("UNK", bid=f"b-{i}")
        rows += s.snapshot()
    store = CountingStore(rows)

    def bad_claim(r):
        raise OSError("db gone")
    store.claim = bad_claim
    r, send = run(store)
    assert send.wire == [] and item(r)["apply_result"] == "error:OSError" and item(r, 1)["apply_result"] == "deferred_run_limit"


def test_job_wrapper_never_raises_and_reports_missing_config(monkeypatch):
    for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", rec.REPORT_PATH_ENV):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    r = rec.job_recovery()
    assert r["status"] == "error" and r["errors"] == ["supabase_not_configured"]


def test_report_contract_and_no_message_text(monkeypatch, tmp_path):
    flags(monkeypatch, apply=False)
    store, _ = seed("OK", "UNK")
    r, _ = run(store)
    assert {"schema", "kind", "generated_at", "mode", "status", "hold_window", "kill_switch", "counts", "preventable_duplicates",
            "needs_attention", "items", "errors", "exactly_once_claimed"} <= set(r)
    assert r["schema"] == 1 and r["kind"] == "brief_delivery_recovery_report" and r["exactly_once_claimed"] is False
    path = tmp_path / "rep.json"
    rec.emit_report(r, str(path))
    on_disk = json.loads(path.read_text())
    assert on_disk == json.loads(json.dumps(r, default=str))
    assert "para 3" not in path.read_text() and "_kind" not in path.read_text()
    assert not list(tmp_path.glob(".recovery-report-*"))


def test_forged_preventable_duplicate_is_counted(monkeypatch):
    flags(monkeypatch, apply=False)
    store, _ = seed("OK", "OK", "OK")
    rows = store.snapshot()
    forged = json.loads(json.dumps(rows[0]))
    forged["attempt_id"], forged["attempt_no"] = "forged", 2
    store2 = CountingStore(rows + [forged])
    r, _ = run(store2)
    assert r["preventable_duplicates"] >= 1


def test_postgrest_list_recent_is_a_select_only_query(monkeypatch):
    seen = {}

    class R:
        def read(self):
            return b"[]"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        seen["url"], seen["method"], seen["data"] = req.full_url, req.get_method(), req.data
        return R()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert rec.PostgrestRecoveryStore("https://x.test", "k").list_recent("2026-01-01T00:00:00+00:00") == []
    assert seen["method"] == "GET" and seen["data"] is None and "started_at=gte." in seen["url"] and seen["url"].startswith("https://x.test/rest/v1/intelligence_delivery_attempts")


def test_not_registered_in_scheduler_or_units():
    root = pathlib.Path(__file__).resolve().parents[1]
    assert "delivery_recovery" not in (root / "intelligence" / "scheduler.py").read_text()
    assert not [p for p in (root / "deploy").glob("**/*") if p.is_file() and "delivery_recovery" in p.read_text(errors="ignore")] if (root / "deploy").exists() else True


def test_postgrest_list_recent_returns_newest_rows_within_limit_oldest_first(monkeypatch):
    """N8: on overflow of LIMIT the newest rows must be kept: ask for started_at.desc, return ascending."""
    seen = {}
    rows = [{"attempt_id": f"a{i}", "brief_table": "ref", "brief_id": "b", "channel": "telegram", "content_hash": "h", "kind": "PRIMARY",
                 "attempt_no": 1, "chunks_total": 1, "planned_chunks": [], "chunks": [], "state": "finished", "outcome": "CONFIRMED",
                 "started_at": f"2026-11-25T0{i}:00:00+00:00"} for i in (5, 4, 3)]          # server returns newest first

    class R:
        def read(self):
            return json.dumps(rows).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        seen["url"] = req.full_url
        return R()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    out = rec.PostgrestRecoveryStore("https://x.test", "k").list_recent("2026-01-01T00:00:00+00:00")
    assert "order=started_at.desc" in seen["url"] and "limit=500" in seen["url"]
    assert [a.attempt_id for a in out] == ["a3", "a4", "a5"]
