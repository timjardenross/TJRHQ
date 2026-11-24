"""Alert dispatcher freshness/register guards and the canonical incident id. Retrospective sources and back-fills are never live."""
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
from intelligence import tiered_brief as tb
from tools.intelligence.alert_replay import load_events

NOW = datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc)
OPTUS = "Breaking: Optus network outage leaves customers across Australia without mobile service"
FIXTURE = _REPO / "tests/fixtures/incident_clustering/events_30d_sample.tsv"


@pytest.fixture(autouse=True)
def _isolation(monkeypatch):
    for f in (ad.FLAG, ad.SEND_FLAG, ad.DESTINATION_ENV, ad.FRESH_ENV, tb.PORTAL_BASE_ENV):
        monkeypatch.delenv(f, raising=False)

    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)


def _ev(i, title, source, published):
    return {"id": i, "source": source, "title": title, "published_at": published.isoformat(), "collected_at": NOW.isoformat()}


def _alerts(events, now=NOW):
    return ad.process(ic.cluster_incidents(events, now=now, force=True), now=now, store=ad.InMemoryAlertStore(), force=True)


def test_baseline_fresh_outage_alerts():
    assert [p["kind"] for p in _alerts([_ev("c0000001", OPTUS, "ABC News", NOW - timedelta(hours=1))])] == ["alert"]


def test_asic_release_dated_two_weeks_ago_never_alerts():
    ev = [_ev("c0000002", "ASIC statement: Australian bank outage left customers without service", "ASIC Media Releases", NOW - timedelta(days=14))]
    assert _alerts(ev) == []
    assert ad.alertable_reports(ic.cluster_incidents(ev, now=NOW, force=True)[0], NOW) == []


def test_old_published_report_never_alerts_even_if_the_tier_alone_would():
    ev = [_ev("c0000003", OPTUS, "ABC News", NOW - timedelta(hours=10))]      # inside the 12 h tier window, outside the 6 h dispatcher window
    inc = ic.cluster_incidents(ev, now=NOW, force=True)[0]
    assert ad.dt.tier_for_incident(inc, now=NOW).tier == ad.dt.IMMEDIATE_ALERT
    assert _alerts(ev) == []


def test_freshness_window_is_configurable(monkeypatch):
    monkeypatch.setenv(ad.FRESH_ENV, "11")
    assert [p["kind"] for p in _alerts([_ev("c0000004", OPTUS, "ABC News", NOW - timedelta(hours=10))])] == ["alert"]


def test_optus_national_outage_register_entry_never_alerts():
    assert ad.is_register_source("Optus National Outage Register")
    assert _alerts([_ev("c0000005", OPTUS, "Optus National Outage Register", NOW - timedelta(minutes=30))]) == []


def test_unverified_publication_time_cannot_alert():
    e = {"id": "c0000006", "source": "ABC News", "title": OPTUS, "published_at": None, "collected_at": NOW.isoformat()}
    assert _alerts([e]) == []


def test_payload_carries_the_canonical_id_and_portal_link(monkeypatch):
    monkeypatch.setenv(tb.PORTAL_BASE_ENV, "https://hq.example.test/")
    p = _alerts([_ev("c0000007", OPTUS, "ABC News", NOW - timedelta(hours=1))])[0]
    assert p["incident_id"] == p["incident_key"] and p["incident_id"].startswith("inc-") and len(p["incident_id"]) == 14
    assert p["link"] == f"https://hq.example.test/intelligence#{p['incident_id']}" and p["link"] in p["text"]


def test_incident_id_is_deterministic_and_linked_in_the_brief():
    events = load_events(FIXTURE)
    now = datetime(2026, 11, 13, 21, 0, tzinfo=timezone.utc)
    ms = [e for e in events if e["collected_at"] <= "2026-11-13T21:00:00+00:00" and ("icrosoft" in e["title"] or "utlook" in e["title"])]
    inc = max(ic.cluster_incidents(ms, now=now, force=True), key=lambda i: i.n_reports)
    again = max(ic.cluster_incidents(list(reversed(ms)), now=now, force=True), key=lambda i: i.n_reports)
    assert tb.incident_id(inc) == tb.incident_id(again)                         # input order does not matter
    lines, _ = tb.render(ms, now=now)
    assert any(tb.incident_link(tb.incident_id(inc)) in ln for ln in lines)


def test_dispatcher_pins_the_id_it_first_alerted_with_even_if_a_back_dated_report_joins():
    """Known limit: a late-collected report PUBLISHED earlier than the first one changes the computed id. The dispatcher keeps the id it
    alerted with, so the restoration update carries the same incident_id as the alert."""
    store = ad.InMemoryAlertStore()
    t = NOW - timedelta(hours=1)
    a = _ev("d0000001", OPTUS, "ABC News", t)
    first = ad.process(ic.cluster_incidents([a], now=NOW, force=True), now=NOW, store=store, force=True)[0]
    back = _ev("d0000002", "Optus outage: services restored after hours-long disruption", "ABC News", t - timedelta(days=0, minutes=-30))
    back["published_at"] = (NOW - timedelta(minutes=10)).isoformat()
    out = ad.process(ic.cluster_incidents([a, back], now=NOW, force=True), now=NOW, store=store, force=True)
    assert [p["kind"] for p in out] == ["restoration"] and out[0]["incident_id"] == first["incident_id"]
