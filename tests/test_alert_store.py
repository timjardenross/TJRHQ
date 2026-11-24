"""Persistent AlertStore against a fake PostgREST layer: restart, concurrent claim, send failure stays retryable, rate limit, dry rows separate."""
from __future__ import annotations

import socket
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from intelligence import alert_dispatcher as ad
from intelligence import incident_clustering as ic
from intelligence.alert_store import PostgrestAlertStore, StoreUnavailable
from tools.intelligence.alert_replay import _ts, load_events

FIXTURE = _REPO / "tests/fixtures/incident_clustering/events_30d_sample.tsv"


def _iso(v):
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


class FakePostgrest:
    """Just enough PostgREST: select/eq/is.null/lt/gt/gte/or/and filters, POST upsert (merge/ignore), PATCH with return=representation.
    One lock = each request is atomic, like one SQL statement."""

    def __init__(self):
        self.tables = {"incident_alert_state": {}, "incident_alert_sends": []}
        self.lock = threading.Lock()
        self.fail = False
        self.log = []

    @staticmethod
    def _cmp(val, op, arg):
        if op == "is":
            return val is None if arg == "null" else val is not None
        if val is None:
            return False
        if op == "eq":
            return str(val) == arg
        a, b = _iso(val), _iso(arg)
        return {"lt": a < b, "gt": a > b, "gte": a >= b}[op]

    def _term(self, row, term):
        if term.startswith("or(") and term.endswith(")"):
            return any(self._term(row, t) for t in self._split(term[3:-1]))
        col, op, arg = term.split(".", 2)
        return self._cmp(row.get(col), op, arg)

    @staticmethod
    def _split(s):
        out, depth, cur = [], 0, ""
        for ch in s:
            depth += ch == "("
            depth -= ch == ")"
            if ch == "," and depth == 0:
                out.append(cur)
                cur = ""
            else:
                cur += ch
        return out + [cur]

    def _match(self, row, params):
        for k, v in params:
            if k in ("select", "limit", "order", "on_conflict"):
                continue
            if k == "and":
                if not all(self._term(row, t) for t in self._split(v[1:-1])):
                    return False
            elif k == "or":
                if not any(self._term(row, t) for t in self._split(v[1:-1])):
                    return False
            else:
                op, arg = v.split(".", 1)
                if not self._cmp(row.get(k), op, arg):
                    return False
        return True

    def __call__(self, method, table, params, body=None, prefer=None):
        with self.lock:
            self.log.append((method, table))
            if self.fail:
                raise StoreUnavailable("fake outage")
            if table == "incident_alert_state":
                rows = self.tables[table]
                if method == "GET":
                    return [dict(r) for r in rows.values() if self._match(r, params)]
                if method == "POST":
                    cur = rows.get(body["incident_key"])
                    if cur is None:
                        rows[body["incident_key"]] = {"event_ids": [], "alerted_at": None, "restoration_sent_at": None, "dry_alerted_at": None,
                                                      "dry_restoration_at": None, **{c: None for c in ("alert_claimed_at", "alert_claim_token", "restoration_claimed_at",
                                                      "restoration_claim_token", "test_sent_at", "test_claimed_at", "test_claim_token")}, **body}
                    elif "merge" in (prefer or ""):
                        cur.update(body)
                    return []
                if method == "PATCH":
                    hit = [r for r in rows.values() if self._match(r, params)]
                    for r in hit:
                        r.update(body)
                    return [dict(r) for r in hit]
            else:
                if method == "POST":
                    self.tables[table].append({"id": len(self.tables[table]) + 1, **body})
                    return []
                return [dict(r) for r in self.tables[table] if self._match(r, params)]
        raise AssertionError((method, table))


@pytest.fixture(autouse=True)
def _isolation(monkeypatch):
    for f in (ad.FLAG, ad.SEND_FLAG, ad.DESTINATION_ENV):
        monkeypatch.delenv(f, raising=False)

    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)


@pytest.fixture(scope="module")
def scenario():
    """(incidents, now) at the first collection batch where the MS365 incident alerts, plus the full later restoration batches."""
    evs = [e for e in load_events(FIXTURE) if any(k in e["title"].lower() for k in ("microsoft", "outlook", "m365"))]
    evs.sort(key=lambda e: (_ts(e["collected_at"]), str(e["id"])))
    store = ad.InMemoryAlertStore()
    batches = []
    for now in sorted({_ts(e["collected_at"]) for e in evs}):
        incs = ic.cluster_incidents([e for e in evs if _ts(e["collected_at"]) <= now], now=now, force=True)
        out = ad.process(incs, now=now, store=store, force=True)
        batches.append((now, incs, [p["kind"] for p in out]))
    alert_at = next(b for b in batches if "alert" in b[2])
    return batches, alert_at


def _real(monkeypatch):
    monkeypatch.setenv(ad.SEND_FLAG, "1")
    monkeypatch.setenv(ad.DESTINATION_ENV, "xo")


def _rows(fake):
    return fake.tables["incident_alert_state"]


def test_real_send_persists_and_restart_never_resends(monkeypatch, scenario):
    _real(monkeypatch)
    _, (now, incs, _k) = scenario[0], scenario[1]
    fake, sent = FakePostgrest(), []
    s1 = PostgrestAlertStore(fake)
    out = ad.process(incs, now=now, store=s1, sender=lambda p, d: sent.append(p) or True, force=True)
    assert [p["kind"] for p in out] == ["alert"] and out[0]["sent"] and len(sent) == 1
    row = _rows(fake)[out[0]["incident_key"]]
    assert row["alerted_at"] is not None and row["alert_claim_token"] is None and row["alert_claimed_at"] is None
    assert [r["mode"] for r in fake.tables["incident_alert_sends"]] == ["real"]
    # "restart": a brand-new store object (empty cache) over the same database, same and later instants
    for later in (now, now + timedelta(minutes=5), now + timedelta(hours=1)):
        out2 = ad.process(incs, now=later, store=PostgrestAlertStore(fake), sender=lambda p, d: sent.append(p) or True, force=True, window=timedelta(seconds=1))
        assert not [p for p in out2 if p["kind"] == "alert"]
    assert len(sent) == 1


def test_claim_backstops_even_with_a_stale_cache(monkeypatch, scenario):
    """Two processes whose caches both say 'not alerted': the server-side claim lets exactly one send."""
    _real(monkeypatch)
    _, (now, incs, _k) = scenario[0], scenario[1]
    fake, sent = FakePostgrest(), []
    a, b = PostgrestAlertStore(fake), PostgrestAlertStore(fake)
    a.load()
    b.load()                                               # both caches are empty and stale from here on
    ad.process(incs, now=now, store=a, sender=lambda p, d: sent.append(("a", p)) or True, force=True)
    out = ad.process(incs, now=now, store=b, sender=lambda p, d: sent.append(("b", p)) or True, force=True)
    assert [s[0] for s in sent] == ["a"]
    assert out and out[0].get("claimed_elsewhere") and not out[0]["sent"]


def test_concurrent_claim_has_exactly_one_winner():
    fake = FakePostgrest()
    PostgrestAlertStore(fake).put(ad.AlertState("inc-x", {"e1"}, "h"))
    winners, barrier = [], threading.Barrier(12)

    def worker():
        st = PostgrestAlertStore(fake)
        barrier.wait()
        tok = st.claim("alert", "inc-x")
        if tok:
            winners.append(tok)
    ts = [threading.Thread(target=worker) for _ in range(12)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(winners) == 1


def test_send_failure_leaves_state_retryable(monkeypatch, scenario):
    _real(monkeypatch)
    _, (now, incs, _k) = scenario[0], scenario[1]
    fake, calls = FakePostgrest(), []
    store = PostgrestAlertStore(fake)
    out = ad.process(incs, now=now, store=store, sender=lambda p, d: calls.append(1) or False, force=True)
    assert out[0]["sent"] is False
    key = out[0]["incident_key"]
    row = _rows(fake)[key]
    assert row["alerted_at"] is None and row["alert_claim_token"] is None            # released, not sent
    assert fake.tables["incident_alert_sends"] == []                                # nothing counted against the rate limit
    out2 = ad.process(incs, now=now + timedelta(minutes=5), store=PostgrestAlertStore(fake), sender=lambda p, d: calls.append(1) or True, force=True)
    assert out2[0]["sent"] and len(calls) == 2 and _rows(fake)[key]["alerted_at"] is not None


def test_sender_exception_is_also_retryable(monkeypatch, scenario):
    _real(monkeypatch)
    _, (now, incs, _k) = scenario[0], scenario[1]
    fake = FakePostgrest()

    def boom(p, d):
        raise RuntimeError("telegram down")
    out = ad.process(incs, now=now, store=PostgrestAlertStore(fake), sender=boom, force=True)
    assert out[0]["sent"] is False and "telegram down" in out[0]["error"]
    assert all(r["alerted_at"] is None and r["alert_claim_token"] is None for r in _rows(fake).values())


def test_store_outage_before_send_sends_nothing(monkeypatch, scenario):
    _real(monkeypatch)
    _, (now, incs, _k) = scenario[0], scenario[1]
    fake, sent = FakePostgrest(), []
    fake.fail = True
    with pytest.raises(StoreUnavailable):
        ad.process(incs, now=now, store=PostgrestAlertStore(fake), sender=lambda p, d: sent.append(p) or True, force=True)
    assert sent == []


def test_record_failure_after_send_keeps_claim_so_no_resend(monkeypatch, scenario):
    _real(monkeypatch)
    _, (now, incs, _k) = scenario[0], scenario[1]
    fake, sent = FakePostgrest(), []

    class Flaky(PostgrestAlertStore):
        def complete(self, *a, **k):
            raise StoreUnavailable("blip")
    out = ad.process(incs, now=now, store=Flaky(fake), sender=lambda p, d: sent.append(p) or True, force=True)
    assert out[0]["sent"] is True
    out2 = ad.process(incs, now=now + timedelta(minutes=5), store=PostgrestAlertStore(fake), sender=lambda p, d: sent.append(p) or True, force=True)
    assert len(sent) == 1 and out2[0].get("claimed_elsewhere")


def test_dry_run_uses_dry_columns_and_never_consumes_the_real_once(monkeypatch, scenario):
    _, (now, incs, _k) = scenario[0], scenario[1]
    fake = FakePostgrest()
    out = ad.process(incs, now=now, store=PostgrestAlertStore(fake), force=True)
    key = out[0]["incident_key"]
    row = _rows(fake)[key]
    assert row["dry_alerted_at"] is not None and row["alerted_at"] is None
    assert [r["mode"] for r in fake.tables["incident_alert_sends"]] == ["dry"]
    again = ad.process(incs, now=now + timedelta(minutes=1), store=PostgrestAlertStore(fake), force=True)
    assert not [p for p in again if p["kind"] == "alert"]                           # dry is once too (across restarts)
    _real(monkeypatch)
    sent = []
    real = ad.process(incs, now=now + timedelta(minutes=2), store=PostgrestAlertStore(fake), sender=lambda p, d: sent.append(p) or True, force=True)
    assert [p["kind"] for p in real] == ["alert"] and len(sent) == 1                # rehearsal did not consume the real send
    assert [r["mode"] for r in fake.tables["incident_alert_sends"]] == ["dry", "real"]


def test_rate_limit_is_persisted_across_restarts(monkeypatch, scenario):
    _real(monkeypatch)
    _, (now, incs, _k) = scenario[0], scenario[1]
    fake = FakePostgrest()
    PostgrestAlertStore(fake).put(ad.AlertState("inc-other", {"zz"}, "other"))
    for i in range(3):
        PostgrestAlertStore(fake).log_send(now - timedelta(minutes=i), "real", "inc-other", "alert")
    out = ad.process(incs, now=now, store=PostgrestAlertStore(fake), sender=lambda p, d: True, force=True, max_per_window=3)
    assert out and out[0]["deferred"] and not out[0]["sent"]
    assert all(r["alerted_at"] is None for r in _rows(fake).values())              # deferral keeps state untouched
    later = ad.process(incs, now=now + timedelta(hours=2), store=PostgrestAlertStore(fake), sender=lambda p, d: True, force=True, max_per_window=3)
    assert later[0]["sent"]


def test_restoration_sent_once_and_persisted(monkeypatch, scenario):
    _real(monkeypatch)
    batches, _alert = scenario
    fake, sent = FakePostgrest(), []
    for now, incs, _k in batches:                                                    # every batch, a fresh store each time (restart per pass)
        ad.process(incs, now=now, store=PostgrestAlertStore(fake), sender=lambda p, d: sent.append(p) or True, force=True, max_per_window=99)
    kinds = [p["kind"] for p in sent]
    assert kinds.count("alert") == 1 and kinds.count("restoration") <= 1
    if "restoration" in kinds:
        assert sent[-1]["headline"] == sent[0]["headline"]                           # restoration pins the original headline


def test_put_cannot_unsend(monkeypatch, scenario):
    """A stale cache writing back its state must not clear a real-send marker set by someone else."""
    fake = FakePostgrest()
    s = PostgrestAlertStore(fake)
    s.put(ad.AlertState("inc-y", {"a"}, "h"))
    _rows(fake)["inc-y"]["alerted_at"] = "2026-11-24T00:00:00+00:00"
    st = ad.AlertState("inc-y", {"a", "b"}, "h")                                     # stale view: alerted_at None
    PostgrestAlertStore(fake).put(st)
    assert _rows(fake)["inc-y"]["alerted_at"] == "2026-11-24T00:00:00+00:00" and set(_rows(fake)["inc-y"]["event_ids"]) == {"a", "b"}


def test_test_claim_window_and_lease():
    fake = FakePostgrest()
    s = PostgrestAlertStore(fake)
    s.ensure_row("test-alert-path", "t")
    now = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
    tok = s.claim("test", "test-alert-path", now=now, resend_after=timedelta(hours=6))
    assert tok and s.claim("test", "test-alert-path", now=now, resend_after=timedelta(hours=6)) is None     # in progress
    assert s.complete("test", "test-alert-path", tok, now)
    assert s.claim("test", "test-alert-path", now=now + timedelta(hours=1), resend_after=timedelta(hours=6)) is None
    assert s.claim("test", "test-alert-path", now=now + timedelta(hours=7), resend_after=timedelta(hours=6))
