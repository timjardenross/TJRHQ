"""Incident snapshot publisher: dry-run default, shared incident_key with the alert payload (one incident, one entry across channels)."""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from intelligence import alert_dispatcher as ad
from intelligence import incident_clustering as ic
from tools.intelligence import publish_incident_snapshot as pub
from tools.intelligence.alert_replay import _ts, load_events

FIXTURE = _REPO / "tests/fixtures/incident_clustering/events_30d_sample.tsv"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.delenv(pub.WRITE_FLAG, raising=False)

    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)


@pytest.fixture(scope="module")
def events():
    return [e for e in load_events(FIXTURE) if e["collected_at"] <= "2026-11-12T23:30:00+00:00" and ("icrosoft" in e["title"] or "utlook" in e["title"])]


def test_rows_have_the_portal_contract(events):
    now = max(_ts(e["collected_at"]) for e in events)
    rows = pub.build_rows(events, now=now)
    assert rows
    keys = {"incident_key", "headline", "tier", "restoration_status", "n_reports", "why", "reports", "material_exception", "snapshot_at", "last_report_at"}
    assert all(set(r) == keys for r in rows)
    assert len({r["incident_key"] for r in rows}) == len(rows)           # one row per incident
    assert all({"relation", "event_id", "title", "published_at", "restoration"} <= set(x) for r in rows for x in r["reports"])


def test_snapshot_key_equals_the_telegram_alert_key(events):
    now = max(_ts(e["collected_at"]) for e in events)
    alert = ad.process(ic.cluster_incidents(events, now=now, force=True), now=now, force=True)
    alert_keys = {p["incident_key"] for p in alert if p["kind"] == "alert"}
    snap = {r["incident_key"] for r in pub.build_rows(events, now=now) if r["tier"] == "IMMEDIATE_ALERT"}
    assert alert_keys and alert_keys == snap


def test_write_is_off_without_flag_and_never_touches_the_network(events, monkeypatch):
    rows = pub.build_rows(events, now=max(_ts(e["collected_at"]) for e in events))
    assert pub.write_rows(rows) is False
    monkeypatch.setenv(pub.WRITE_FLAG, "1")                               # flag alone is not enough: no URL/key configured
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert pub.write_rows(rows) is False


def test_material_exception_is_live_scheduled_brief_only(events):
    now = max(_ts(e["collected_at"]) for e in events)
    for r in pub.build_rows(events, now=now):
        if r["material_exception"]:
            assert r["tier"] == "SCHEDULED_BRIEF" and r["restoration_status"] in ("ongoing", "partially_restored")
