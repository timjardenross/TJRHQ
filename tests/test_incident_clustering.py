"""Incident clustering v2, delivery tiers and the offline alert replay. Offline, fixture-driven, no network.

The fixture (tests/fixtures/incident_clustering/events_30d_sample.tsv) holds real titles/dates/sources read with a SELECT-only query on
intelligence_events (Microsoft 365 outage 12-16 Nov 2026, Telstra and other telecommunications items, Coles cyber attack)."""
from __future__ import annotations

import json
import re
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tools" / "intelligence"))

import alert_replay as ar

from intelligence import delivery_tiers as dt
from intelligence import incident_clustering as ic

FIXTURE = _REPO / "tests" / "fixtures" / "incident_clustering" / "events_30d_sample.tsv"
REF_V1 = _REPO / "knowledge" / "intelligence-reference-set" / "reference_set_v1.json"
EXPORT = _REPO / "knowledge" / "intelligence-reference-set" / "events_export_2026-11-24.json"
NOW = datetime(2026, 11, 24, 6, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)


@pytest.fixture(scope="module")
def events():
    return ar.load_events(FIXTURE)


@pytest.fixture(scope="module")
def v2(events):
    return ic.cluster_incidents(events, now=NOW, force=True)


@pytest.fixture(scope="module")
def v1(events):
    return ic.cluster_incidents(events, now=NOW, force=False)


def _incident_with(incidents, event_id):
    return next(i for i in incidents if any(r.event_id == event_id for r in i.reports))


def _rel(incident, event_id):
    return next(r.relation for r in incident.reports if r.event_id == event_id)


# ── flags ────────────────────────────────────────────────────────────────────────────────────────────────
def test_flags_default_off_and_read_at_call_time(monkeypatch):
    monkeypatch.delenv(ic.FLAG, raising=False)
    monkeypatch.delenv(dt.FLAG, raising=False)
    assert not ic.enabled() and not dt.enabled()
    monkeypatch.setenv(ic.FLAG, "1")
    monkeypatch.setenv(dt.FLAG, "true")
    assert ic.enabled() and dt.enabled()
    monkeypatch.setenv(ic.FLAG, "0")
    assert not ic.enabled()


def test_flag_off_means_no_consolidation(events, monkeypatch):
    monkeypatch.delenv(ic.FLAG, raising=False)
    off = ic.cluster_incidents(events, now=NOW)
    assert all(len(i.merged_from) == 1 for i in off)
    monkeypatch.setenv(ic.FLAG, "1")
    on = ic.cluster_incidents(events, now=NOW)
    assert len(on) < len(off)


# ── Microsoft 365 outage regression ───────────────────────────────────────────────────────────────────────
STRAGGLERS = {"a160eef1": "restoration-only headline", "d05821f7": "Outlook cost story with no 'Microsoft' in the headline",
              "f802acac": "phishing follow-up"}


def test_m365_stragglers_are_separate_incidents_in_baseline(v1):
    main = _incident_with(v1, "a6d72e00")
    for eid in STRAGGLERS:
        assert _incident_with(v1, eid) is not main, f"baseline already merged {eid}: the regression no longer shows a gap"


def test_m365_consolidated_into_one_incident(v2):
    main = _incident_with(v2, "a6d72e00")
    for eid in STRAGGLERS:
        assert _incident_with(v2, eid) is main
    assert main.subject == "microsoft" and main.n_reports >= 40


def test_duplicate_representation_before_after(events):
    d = ar.duplicate_representation(events, NOW)["microsoft_365_outage"]
    assert d["baseline"]["total"]["incidents"] >= 4
    assert d["consolidated"]["total"]["incidents"] <= 2
    assert d["consolidated"]["total"]["reports"] == d["baseline"]["total"]["reports"]      # nothing dropped, only consolidated


def test_m365_relations(v2):
    inc = _incident_with(v2, "a6d72e00")
    assert len(inc.by_relation(ic.NEW)) == 1 and _rel(inc, "a6d72e00") == ic.NEW         # earliest factual report
    for eid in ("a160eef1", "5faa0a3f", "bbb1fb24", "cd458e26"):                           # recovers / restores / broad recovery / being restored
        assert _rel(inc, eid) == ic.RESTORATION_UPDATE
    assert next(r for r in inc.reports if r.event_id == "cd458e26").restoration == "partial"
    assert next(r for r in inc.reports if r.event_id == "a160eef1").restoration == "full"
    # a race / attempt to restore and a negated recovery are NOT restorations
    for eid in ("af2fdab8", "583fc2bf", "fb013077", "eb4b05dd", "5e5a75b9"):
        assert _rel(inc, eid) != ic.RESTORATION_UPDATE, eid
    for eid in ("f802acac", "d05821f7", "d6d555f3", "4bdac5e3", "e692952a"):               # phishing, cost, hidden-risk, backup plans, review
        assert _rel(inc, eid) == ic.RELATED, eid
    assert _rel(inc, "d1f78bc2") == ic.SUBSEQUENT                                          # cause statement is a factual update


def test_apra_near_miss_after_the_chain_window_is_not_the_alerting_incident(v2):
    apra = _incident_with(v2, "1d9cd2a4")
    assert apra is not _incident_with(v2, "a6d72e00")
    assert dt.tier_for_incident(apra, now=NOW).tier in (dt.CONTEXT, dt.REFERENCE_RETAIN)


# ── Telstra / telecommunications regression ───────────────────────────────────────────────────────────────
def test_distinct_telstra_incidents_are_not_merged(v2):
    ids = ("a075c25f", "6f8cbc2a", "005e774d", "130ca8a1", "d7cd797e")                    # Kingswood, mystery calls, Yornup upgrade, Stockton, AWS
    assert len({id(_incident_with(v2, e)) for e in ids}) == len(ids)
    assert _incident_with(v2, "d7cd797e").subject == "aws"


def test_telstra_complaints_aftermath_has_no_new_report(v2):
    inc = _incident_with(v2, "42e7c791")
    assert not inc.by_relation(ic.NEW)
    assert {r.relation for r in inc.reports} <= {ic.RELATED, ic.HISTORICAL_REFERENCE}
    assert _rel(_incident_with(v2, "4df0bd3c"), "4df0bd3c") == ic.HISTORICAL_REFERENCE      # "... After the July Outage"


def test_telstra_tiers_no_false_urgency(v2, v1):
    # baseline rates the single aggregator headline "warned of Telstra mobile disruptions" VERIFY / immediate
    base = _incident_with(v1, "a075c25f").decision
    assert (base.priority, base.urgency) == ("VERIFY", "immediate")
    for eid in ("a075c25f", "005e774d", "130ca8a1", "6f8cbc2a"):
        # MONITOR while fresh; once older than the shared brief window it is CONTEXT. Never urgent, never a scheduled item.
        assert dt.tier_for_incident(_incident_with(v2, eid), now=NOW).tier in (dt.MONITOR, dt.CONTEXT), eid


def test_coles_cyber_attack_is_one_incident(v2):
    inc = _incident_with(v2, "249d258d")
    assert {r.event_id for r in inc.reports} == {"249d258d", "997b22a6", "2e345266", "4e356803"}
    assert _rel(inc, "249d258d") == ic.NEW and _rel(inc, "2e345266") == ic.RELATED


# ── delivery tiers ────────────────────────────────────────────────────────────────────────────────────────
def _ev(i, title, source, pub="2026-11-24T05:00:00+00:00", col="2026-11-24T05:10:00+00:00"):
    return {"id": i, "title": title, "source": source, "published_at": pub, "collected_at": col}


def _tier(events, now=None):
    now = now or datetime(2026, 11, 24, 5, 30, tzinfo=timezone.utc)
    incs = ic.cluster_incidents(events, now=now, force=True)
    assert len(incs) == 1
    return dt.tier_for_incident(incs[0], now=now)


def test_tier_immediate_alert_single_mainstream_report():
    t = _tier([_ev("n1", "Breaking: NAB customers experiencing phone and internet banking outages", "ABC News")])
    assert t.tier == dt.IMMEDIATE_ALERT and any("provisional" in r for r in t.reasons)


def test_tier_same_report_is_not_an_alert_when_stale():
    t = _tier([_ev("n1", "Breaking: NAB customers experiencing phone and internet banking outages", "ABC News")],
              now=datetime(2026, 11, 25, 5, 30, tzinfo=timezone.utc))
    assert t.tier != dt.IMMEDIATE_ALERT


def test_tier_aggregator_only_is_monitor_not_alert():
    t = _tier([_ev("n1", "Breaking: NAB customers experiencing phone and internet banking outages - Google News", "Google News - NAB")])
    assert t.tier == dt.MONITOR


def test_tier_scheduled_brief_when_restored():
    evs = [_ev("n1", "Breaking: NAB customers experiencing phone and internet banking outages", "ABC News", "2026-11-24T01:00:00+00:00", "2026-11-24T01:10:00+00:00"),
           _ev("n2", "NAB restores systems following online banking outage", "Cyber Daily", "2026-11-24T05:00:00+00:00", "2026-11-24T05:10:00+00:00")]
    t = _tier(evs)
    assert t.tier == dt.SCHEDULED_BRIEF, t.reasons


def test_tier_context_for_commentary_only():
    t = _tier([_ev("n1", "Microsoft outage exposes global reliance on core tech providers - Australia", "Financial Times")])
    assert t.tier in (dt.CONTEXT, dt.REFERENCE_RETAIN)


def test_tier_reference_retain_for_foreign_status_noise():
    t = _tier([_ev("n1", "Cloudflare Status: Network Performance Issues in Chicago (ORD) (resolved)", "Cloudflare Status")])
    assert t.tier == dt.REFERENCE_RETAIN


def test_tiers_are_the_documented_five():
    assert dt.TIERS == (dt.IMMEDIATE_ALERT, dt.SCHEDULED_BRIEF, dt.MONITOR, dt.CONTEXT, dt.REFERENCE_RETAIN)


# ── replay harness ────────────────────────────────────────────────────────────────────────────────────────
def test_replay_alerts_on_fixture(events):
    res = ar.replay(events, consolidated=True)
    heads = [a["headline"] for a in res["alerts"]]
    assert any("Microsoft" in h for h in heads) and any("flights" in h.lower() for h in heads)
    assert not any("Telstra" in h for h in heads)                              # no false urgency on the Telstra items
    ms = next(a for a in res["alerts"] if "Microsoft" in a["headline"])
    assert 0 <= ms["latency_hours_from_first_collection"] <= 4
    assert len([a for a in res["alerts"] if "Microsoft" in a["headline"]]) == 1   # one alert for the whole 50-report incident


def test_replay_is_deterministic_and_sends_nothing(events):
    a = ar.replay(events, consolidated=True)["alerts"]
    b = ar.replay(list(reversed(events)), consolidated=True)["alerts"]
    assert [(x["alerted_at"], x["headline"]) for x in a] == [(x["alerted_at"], x["headline"]) for x in b]
    src = Path(ar.__file__).read_text()
    assert not re.search(r"^\s*(?:import|from)\s+(?:requests|httpx|urllib\.request|telegram|supabase)", src, re.MULTILINE)


def test_surfacing_audit_counts_and_reasons(events):
    res = ar.replay(events, consolidated=True)
    audit = ar.surfacing_audit(res, events)
    assert audit["material_incidents"] == audit["surfaced_in_a_brief"] + audit["never_surfaced"]
    assert audit["never_surfaced"] >= 1 and sum(audit["why"].values()) >= audit["never_surfaced"]
    # the Microsoft 365 incident reached a brief only through an Insurance Business commentary report
    assert "surfaced_only_via_a_commentary_or_aftermath_report" in audit["why"]


@pytest.mark.skipif(not (REF_V1.exists() and EXPORT.exists()), reason="frozen reference set not present")
def test_replay_against_frozen_reference_set_v1():
    ref = json.loads(REF_V1.read_text())
    assert len(ref["incidents"]) == 53                                         # frozen: this PR never edits it
    events = ar.load_events(EXPORT)
    res = ar.replay(events, consolidated=True)
    sc = ar.score_against_reference(res, events, ref)
    assert sc["false_urgency_records"] == [] and sc["negatives_reaching_scheduled_brief_or_alert"] == []
    assert {"RS-001", "RS-003", "RS-008"} <= set(sc["material_alerted"])
    assert sc["duplicate_alert_records"] == []
    # partial restorations ("being restored") are never counted as false restoration; a full 'recovers' claim 12.6 h early is
    assert [f["event_id"] for f in sc["false_restoration"]] == ["itnrec01"]
