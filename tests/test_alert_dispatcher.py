"""Immediate-alert dispatcher: dry-run default, once per incident, restoration once, rate limiting, never a real send without flag + destination."""
from __future__ import annotations

import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from intelligence import alert_dispatcher as ad
from intelligence import incident_clustering as ic
from tools.intelligence.alert_replay import _ts, load_events

FIXTURE = _REPO / "tests/fixtures/incident_clustering/events_30d_sample.tsv"


@pytest.fixture(autouse=True)
def _isolation(monkeypatch):
    for f in (ad.FLAG, ad.SEND_FLAG, ad.DESTINATION_ENV):
        monkeypatch.delenv(f, raising=False)

    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)


@pytest.fixture(scope="module")
def ms_events():
    return [e for e in load_events(FIXTURE) if "microsoft" in e["title"].lower() or "outlook" in e["title"].lower() or "m365" in e["title"].lower()]


def _run(events, store, **kw):
    """Replay batches in collection order through the dispatcher."""
    out = []
    evs = sorted(events, key=lambda e: (_ts(e["collected_at"]), str(e["id"])))
    for now in sorted({_ts(e["collected_at"]) for e in evs}):
        seen = [e for e in evs if _ts(e["collected_at"]) <= now]
        out += ad.process(ic.cluster_incidents(seen, now=now, force=True), now=now, store=store, **kw)
    return out


def test_master_flag_off_returns_nothing_and_touches_nothing(ms_events):
    store = ad.InMemoryAlertStore()
    out = ad.process(ic.cluster_incidents(ms_events, now=_ts(ms_events[-1]["collected_at"]), force=True), store=store)
    assert out == [] and store.states == {} and store.sends == []


def test_default_is_dry_run_and_sends_once_per_incident(ms_events):
    store = ad.InMemoryAlertStore()
    sent = []
    out = _run(ms_events, store, force=True, sender=lambda p, d: sent.append(p) or True)     # sender given, but no send flag/destination
    alerts = [p for p in out if p["kind"] == "alert"]
    assert len(alerts) == 1                                          # 42 reports, one incident, one alert
    assert all(p["dry_run"] and not p["sent"] for p in out)
    assert sent == []                                                # the sender was never called
    assert "ALERT:" in alerts[0]["text"] and alerts[0]["incident_key"].startswith("inc-")


def test_flag_only_enabled_via_env(monkeypatch, ms_events):
    monkeypatch.setenv(ad.FLAG, "1")
    store = ad.InMemoryAlertStore()
    evs = sorted(ms_events, key=lambda e: _ts(e["collected_at"]))
    n = 0
    for now in sorted({_ts(e["collected_at"]) for e in evs}):
        seen = [e for e in evs if _ts(e["collected_at"]) <= now]
        n += len(ad.process(ic.cluster_incidents(seen, now=now, force=True), now=now, store=store))
    assert n >= 1


def test_real_send_needs_flag_destination_and_sender(monkeypatch, ms_events):
    sent = []
    sender = lambda p, d: sent.append((p["kind"], d)) or True
    monkeypatch.setenv(ad.SEND_FLAG, "1")
    _run(ms_events, ad.InMemoryAlertStore(), force=True, sender=sender)
    assert sent == []                                                # flag without destination: still dry-run
    monkeypatch.setenv(ad.DESTINATION_ENV, "chat-123")
    _run(ms_events, ad.InMemoryAlertStore(), force=True)
    assert sent == []                                                # flag + destination without a sender: still dry-run
    store = ad.InMemoryAlertStore()
    out = _run(ms_events, store, force=True, sender=sender)
    assert [k for k, _ in sent][:1] == ["alert"] and sent[0][1] == "chat-123"
    assert any(p["sent"] and not p["dry_run"] for p in out)


def test_never_repeats_an_alert_across_passes(monkeypatch, ms_events):
    monkeypatch.setenv(ad.SEND_FLAG, "1")
    monkeypatch.setenv(ad.DESTINATION_ENV, "chat-123")
    sent = []
    store = ad.InMemoryAlertStore()
    sender = lambda p, d: sent.append(p["kind"]) or True
    _run(ms_events, store, force=True, sender=sender)
    first = list(sent)
    _run(ms_events, store, force=True, sender=sender)                # same events again, same store
    assert sent == first and first.count("alert") == 1 and first.count("restoration") <= 1


def test_dry_run_does_not_consume_the_real_once(monkeypatch, ms_events):
    store = ad.InMemoryAlertStore()
    _run(ms_events, store, force=True)                                # rehearsal
    st = next(iter(store.states.values()))
    assert st.dry_alerted_at is not None and st.alerted_at is None
    monkeypatch.setenv(ad.SEND_FLAG, "1")
    monkeypatch.setenv(ad.DESTINATION_ENV, "chat-123")
    sent = []
    _run(ms_events, store, force=True, sender=lambda p, d: sent.append(p["kind"]) or True)
    assert sent.count("alert") == 1                                   # the real send still happens once


def test_failed_send_is_not_recorded_and_is_retried(monkeypatch, ms_events):
    monkeypatch.setenv(ad.SEND_FLAG, "1")
    monkeypatch.setenv(ad.DESTINATION_ENV, "chat-123")
    store = ad.InMemoryAlertStore()
    out = _run(ms_events, store, force=True, sender=lambda p, d: (_ for _ in ()).throw(RuntimeError("transport down")))
    assert out and all(not p["sent"] and "error" in p for p in out)
    assert all(st.alerted_at is None for st in store.states.values())
    ok = []
    _run(ms_events, store, force=True, sender=lambda p, d: ok.append(p["kind"]) or True)
    assert ok.count("alert") == 1


def test_restoration_update_sent_once_after_alert():
    t0 = datetime(2026, 11, 20, 1, 0, tzinfo=timezone.utc)
    ev = [{"id": "aaaa0001", "source": "ABC News", "title": "Breaking: Optus network outage leaves customers across Australia without mobile service",
           "published_at": t0.isoformat(), "collected_at": t0.isoformat()},
          {"id": "aaaa0002", "source": "ABC News", "title": "Optus network outage: services restored after hours-long disruption",
           "published_at": (t0 + timedelta(hours=3)).isoformat(), "collected_at": (t0 + timedelta(hours=3)).isoformat()}]
    store = ad.InMemoryAlertStore()
    out = _run(ev, store, force=True)
    kinds = [p["kind"] for p in out]
    assert kinds == ["alert", "restoration"]                          # alert once when live, one restoration update when restored
    assert "RESTORED:" in out[1]["text"] and out[0]["incident_key"] == out[1]["incident_key"]
    again = _run(ev, store, force=True)
    assert again == []                                                # nothing repeats on a second pass


def test_rate_limit_defers_without_consuming_state(monkeypatch):
    def fam(i):
        t = datetime(2026, 11, 20, 1, i, tzinfo=timezone.utc)
        return {"id": f"bb{i:06d}", "source": "ABC News", "title": f"Breaking: Optus network outage {i} leaves customers across Australia without service",
                "published_at": t.isoformat(), "collected_at": t.isoformat()}
    now = datetime(2026, 11, 20, 1, 30, tzinfo=timezone.utc)
    store = ad.InMemoryAlertStore()
    for _ in range(3):
        store.log_send(now - timedelta(minutes=5), "dry")
    out = ad.process(ic.cluster_incidents([fam(1)], now=now, force=True), now=now, store=store, force=True)
    assert len(out) == 1 and out[0]["deferred"]                       # alert-level incident, rate limit reached: deferred, not recorded
    assert all(st.dry_alerted_at is None for st in store.states.values())
    later = now + timedelta(hours=2)
    out2 = ad.process(ic.cluster_incidents([fam(1)], now=later, force=True), now=later, store=store, force=True)
    assert len(out2) == 1 and not out2[0]["deferred"]                 # window passed: the deferred alert goes out


def test_incident_identity_survives_growth(ms_events):
    store = ad.InMemoryAlertStore()
    _run(ms_events, store, force=True)
    assert len(store.states) == 1
    assert len(next(iter(store.states.values())).event_ids) >= 4


def _live_outage_events(t0):
    return [{"id": "bbbb0001", "source": "ABC News", "title": "Telstra mobile network outage leaves customers across Australia unable to make calls",
             "published_at": (t0 - timedelta(minutes=10)).isoformat(), "collected_at": (t0 - timedelta(minutes=5)).isoformat()},
            {"id": "bbbb0002", "source": "ABC News", "title": "Telstra crews race to restore mobile network after outage",
             "published_at": (t0 + timedelta(hours=1)).isoformat(), "collected_at": (t0 + timedelta(hours=1, minutes=5)).isoformat()},
            {"id": "bbbb0003", "source": "ABC News", "title": "Telstra mobile network restored after outage, services back online",
             "published_at": (t0 + timedelta(hours=3)).isoformat(), "collected_at": (t0 + timedelta(hours=3, minutes=5)).isoformat()}]


def test_restoration_message_keeps_the_headline_of_the_original_alert():
    """Rehearsal finding (2026-11-24): the incident headline is re-chosen each pass and became a hedged 'crews race to restore'
    report, so a RESTORED message carried a title that contradicted it. The restoration pins the alert-time headline."""
    t0 = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)
    out = _run(_live_outage_events(t0), ad.InMemoryAlertStore(), force=True)
    assert [p["kind"] for p in out] == ["alert", "restoration"]
    assert out[1]["headline"] == out[0]["headline"] and "race to restore" not in out[1]["text"].split("\n")[0].lower()
    assert out[1]["text"].startswith("RESTORED: Telstra mobile network outage")
    assert "services back online" in out[1]["text"]                  # the restoration report itself is still cited


def test_payload_reports_line_separates_factual_from_grouped_commentary():
    """Rehearsal finding: a lone commentary report attached at low confidence inflated 'Reports: 4' when only 2 were factual."""
    t0 = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)
    inc = ic.cluster_incidents(_live_outage_events(t0)[:1], now=t0, force=True)[0]
    from intelligence import delivery_tiers as dt
    td = dt.tier_for_incident(inc, now=t0)
    assert "Reports: 1 (" in ad.build_payload("alert", inc, td, t0)["text"]               # nothing to separate: unchanged text
    td.evidence["n_factual"] = 1
    inc2 = ic.cluster_incidents(_live_outage_events(t0), now=t0 + timedelta(hours=4), force=True)[0]
    td2 = dt.tier_for_incident(inc2, now=t0 + timedelta(hours=4))
    td2.evidence["n_factual"] = 2
    assert "Reports: 3 grouped, 2 factual (" in ad.build_payload("alert", inc2, td2, t0)["text"]
