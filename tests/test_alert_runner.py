"""Scheduled caller, controlled delivery test, replay and the default-OFF proofs."""
from __future__ import annotations

import socket
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from intelligence import alert_dispatcher as ad
from intelligence import alert_runner as ar
from intelligence import alert_telegram as at
from intelligence import incident_clustering as ic
from intelligence import scheduler as sch
from intelligence.alert_store import PostgrestAlertStore
from tests.test_alert_store import FakePostgrest
from tools.intelligence.alert_replay import _ts, load_events

FIXTURE = _REPO / "tests/fixtures/incident_clustering/events_30d_sample.tsv"


@pytest.fixture(autouse=True)
def _isolation(monkeypatch):
    for f in (ad.FLAG, ad.SEND_FLAG, ad.DESTINATION_ENV, ar.BUDGET_ENV):
        monkeypatch.delenv(f, raising=False)

    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)


@pytest.fixture(scope="module")
def ms():
    evs = [e for e in load_events(FIXTURE) if any(k in e["title"].lower() for k in ("microsoft", "outlook", "m365"))]
    evs.sort(key=lambda e: (_ts(e["collected_at"]), str(e["id"])))
    s = ad.InMemoryAlertStore()
    for now in sorted({_ts(e["collected_at"]) for e in evs}):
        seen = [e for e in evs if _ts(e["collected_at"]) <= now]
        if any(p["kind"] == "alert" for p in ad.process(ic.cluster_incidents(seen, now=now, force=True), now=now, store=s, force=True)):
            return seen, now
    raise AssertionError("fixture produces no alert")


# ── default OFF ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_flag_off_runner_returns_immediately_and_touches_nothing(monkeypatch):
    called = []
    monkeypatch.setattr(ar, "load_events", lambda *a, **k: called.append("load") or [])
    monkeypatch.setattr("intelligence.alert_store.http_transport", lambda *a, **k: called.append("http"))
    assert ar.run_after_collection("daily") is None and called == []


def test_scheduler_hook_does_not_even_import_the_runner_when_off(monkeypatch):
    monkeypatch.delitem(sys.modules, "intelligence.alert_runner", raising=False)
    sch._run_incident_alerts("daily_collection")
    assert "intelligence.alert_runner" not in sys.modules


def test_scheduler_hook_never_raises(monkeypatch):
    monkeypatch.setenv(ad.FLAG, "1")
    monkeypatch.setattr(ar, "run_after_collection", lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
    sch._run_incident_alerts("daily_collection")           # must not raise


def test_hook_is_wired_into_every_collection_job():
    src = (_REPO / "intelligence/scheduler.py").read_text()
    for name in ("daily_collection", "priority_tiered_collection", "intraday_status_collection", "intraday_media_collection"):
        assert f'_run_incident_alerts("{name}")' in src
    assert "alert_runner" in src and "add_job(\n        _run_incident_alerts" not in src


def test_flag_on_without_send_flag_is_dry_run_and_never_calls_sender(monkeypatch, ms):
    monkeypatch.setenv(ad.FLAG, "1")
    events, now = ms
    fake, sent = FakePostgrest(), []
    res = ar.run_after_collection("t", store=PostgrestAlertStore(fake), sender=lambda p, d: sent.append(p) or True, events=events, now=now)
    assert res["dry"] == 1 and res["sent"] == 0 and sent == []
    row = next(iter(fake.tables["incident_alert_state"].values()))
    assert row["alerted_at"] is None and row["dry_alerted_at"] is not None


def test_send_flag_without_destination_is_still_dry(monkeypatch, ms):
    monkeypatch.setenv(ad.FLAG, "1")
    monkeypatch.setenv(ad.SEND_FLAG, "1")
    events, now = ms
    sent = []
    res = ar.run_after_collection("t", store=PostgrestAlertStore(FakePostgrest()), sender=lambda p, d: sent.append(p) or True, events=events, now=now)
    assert res["sent"] == 0 and sent == []


def test_full_enable_sends_once_through_the_runner(monkeypatch, ms):
    monkeypatch.setenv(ad.FLAG, "1")
    monkeypatch.setenv(ad.SEND_FLAG, "1")
    monkeypatch.setenv(ad.DESTINATION_ENV, "xo")
    events, now = ms
    fake, sent = FakePostgrest(), []
    for _ in range(3):
        ar.run_after_collection("t", store=PostgrestAlertStore(fake), sender=lambda p, d: sent.append((p, d)) or True, events=events, now=now)
    assert len(sent) == 1 and sent[0][1] == "xo"


def test_runner_never_raises_and_sends_nothing_when_store_down(monkeypatch, ms):
    monkeypatch.setenv(ad.FLAG, "1")
    monkeypatch.setenv(ad.SEND_FLAG, "1")
    monkeypatch.setenv(ad.DESTINATION_ENV, "xo")
    events, now = ms
    fake, sent = FakePostgrest(), []
    fake.fail = True
    res = ar.run_after_collection("t", store=PostgrestAlertStore(fake), sender=lambda p, d: sent.append(p) or True, events=events, now=now)
    assert "error" in res and sent == []


def test_runner_never_raises_when_event_load_fails(monkeypatch):
    monkeypatch.setenv(ad.FLAG, "1")
    monkeypatch.setattr(ar, "load_events", lambda *a, **k: (_ for _ in ()).throw(OSError("db")))
    assert "error" in ar.run_after_collection("t")


def test_budget_stops_dispatch(monkeypatch, ms):
    monkeypatch.setenv(ad.FLAG, "1")
    events, now = ms
    incs = ic.cluster_incidents(events, now=now, force=True)
    out = ad.process(incs, now=now, store=ad.InMemoryAlertStore(), force=True, deadline=time.monotonic() - 1)
    assert out == []


def test_overlapping_pass_is_skipped(monkeypatch):
    monkeypatch.setenv(ad.FLAG, "1")
    assert ar._lock.acquire(blocking=False)
    try:
        assert ar.run_after_collection("t") == {"skipped": "busy"}
    finally:
        ar._lock.release()


# ── controlled test ──────────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_controlled_test_refuses_without_yes():
    out, sent = [], []
    assert ar.controlled_test(yes=False, destination="xo", store=PostgrestAlertStore(FakePostgrest()), sender=lambda p, d: sent.append(p) or True, out=out.append) == 2
    assert sent == [] and "REFUSED" in out[0]


def test_controlled_test_refuses_without_destination():
    sent = []
    assert ar.controlled_test(yes=True, destination="", store=PostgrestAlertStore(FakePostgrest()), sender=lambda p, d: sent.append(p) or True, out=lambda s: None) == 2
    assert sent == []


def test_controlled_test_sends_once_records_test_mode_and_suppresses_second_run():
    fake, sent, out = FakePostgrest(), [], []
    for _ in range(2):                                   # two invocations = two processes (fresh store objects)
        code = ar.controlled_test(yes=True, destination="xo", store=PostgrestAlertStore(fake), sender=lambda p, d: sent.append((p, d)) or True, out=out.append)
        assert code == 0
    assert len(sent) == 1 and sent[0][0]["kind"] == "test" and sent[0][1] == "xo"
    assert sent[0][0]["incident_key"] == ar.TEST_KEY and not sent[0][0]["incident_key"].startswith("inc-")
    assert [r["mode"] for r in fake.tables["incident_alert_sends"]] == ["test"]
    assert any("SENT one test alert" in o for o in out) and any("SUPPRESSED" in o for o in out)
    assert list(fake.tables["incident_alert_state"]) == [ar.TEST_KEY]            # touched no incident row


def test_controlled_test_resends_after_window_and_failure_is_retryable():
    fake, sent = FakePostgrest(), []
    t0 = _ts("2026-11-24T00:00:00Z")
    ok = lambda p, d: sent.append(p) or True
    ar.controlled_test(yes=True, destination="xo", store=PostgrestAlertStore(fake), sender=lambda p, d: False, now=t0, out=lambda s: None)
    assert fake.tables["incident_alert_sends"] == []
    ar.controlled_test(yes=True, destination="xo", store=PostgrestAlertStore(fake), sender=ok, now=t0 + timedelta(minutes=1), out=lambda s: None)
    ar.controlled_test(yes=True, destination="xo", store=PostgrestAlertStore(fake), sender=ok, now=t0 + timedelta(hours=1), out=lambda s: None)
    ar.controlled_test(yes=True, destination="xo", store=PostgrestAlertStore(fake), sender=ok, now=t0 + timedelta(hours=7), out=lambda s: None)
    assert len(sent) == 2


def test_controlled_test_ignores_incident_flags_but_main_requires_yes(monkeypatch, capsys):
    monkeypatch.setattr("intelligence.alert_store.http_transport", lambda *a, **k: FakePostgrest())
    assert ad.main(["--controlled-test", "--destination", "xo"]) == 2
    assert "REFUSED" in capsys.readouterr().out


# ── replay + telegram format ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_replay_is_dry_only_even_with_send_env(monkeypatch):
    monkeypatch.setenv(ad.SEND_FLAG, "1")
    monkeypatch.setenv(ad.DESTINATION_ENV, "xo")
    evs = [e for e in load_events(FIXTURE) if any(k in e["title"].lower() for k in ("microsoft", "outlook", "m365"))]
    out = []
    alerts = ar.replay(evs, out=out.append)
    assert [a["kind"] for a in alerts].count("alert") == 1 and all(a["dry_run"] and not a["sent"] for a in alerts)
    assert "would-have-alerted" in out[0]


def test_telegram_format_is_distinct_and_escaped():
    msg = at.format_message({"kind": "alert", "text": "ALERT: A <b> & B\nStatus: x\nView: /y"})
    assert msg.startswith("🚨 <b>INCIDENT ALERT</b>\n<b>A &lt;b&gt; &amp; B</b>")
    assert at.format_message({"kind": "restoration", "text": "RESTORED: t"}).startswith("✅ <b>INCIDENT RESTORED</b>")
    t = at.format_message({"kind": "test"})
    assert "[TEST] Alert path check — no incident" in t and "No incident exists" in t


def test_telegram_sender_uses_default_xo_chat_and_no_retry(monkeypatch):
    seen = {}

    class R:
        ok, error = True, None
    import core.platform.notification_service as ns
    monkeypatch.setattr(ns, "notify", lambda body, **k: seen.update(k, body=body) or R())
    assert at.send({"kind": "alert", "text": "ALERT: t"}, "xo") is True
    assert seen["chat_id"] is None and seen["max_retries"] == 0 and seen["template"] == "raw"
    at.send({"kind": "alert", "text": "ALERT: t"}, "12345")
    assert seen["chat_id"] == "12345"


def test_dispatcher_module_still_imports_no_transport():
    src = (_REPO / "intelligence/alert_dispatcher.py").read_text().split("def main(")[0]
    assert "notification_service" not in src and "urllib" not in src and "requests" not in src
