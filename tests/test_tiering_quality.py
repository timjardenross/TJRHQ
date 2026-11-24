"""Tiering quality (preview defects D2, D4-D6, D10): shared freshness, additive tiered view, stale/non-incident handling, exposures and
warnings kept, one incident id everywhere, and the frozen reference-set scorecard (material detection must not fall below Morning V1).
Offline: no network, nothing sent. The frozen V0/V1 reference sets are only read."""
from __future__ import annotations

import json
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from intelligence import alert_dispatcher as ad
from intelligence import brief_evidence as be
from intelligence import delivery_tiers as dt
from intelligence import event_detection as ed
from intelligence import freshness as fr
from intelligence import incident_clustering as ic
from intelligence import tiered_brief as tb
from tools.intelligence import conversion_measure as cm
from tools.intelligence.alert_replay import load_events

NOW = datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _isolation(monkeypatch):
    for f in ("DELIVERY_TIERS_V1", "INCIDENT_CLUSTERING_V2", fr.ALERT_FRESH_ENV, "PORTAL_BASE_URL"):
        monkeypatch.delenv(f, raising=False)

    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)


def ev(eid, title, source="ABC News", hours_ago=2.0, summary="", geography="AU"):
    pub = NOW - timedelta(hours=hours_ago)
    return {"id": eid, "title": title, "source": source, "geography": geography, "summary": summary,
            "published_at": pub.isoformat(), "collected_at": pub.isoformat()}


def tier_of(events, needle, now=NOW):
    for inc in ic.cluster_incidents(events, now=now, force=True):
        if any(needle in r.candidate.title for r in inc.reports):
            return dt.tier_for_incident(inc, now=now), inc
    raise AssertionError(needle)


# D2: one freshness definition --------------------------------------------------------------------------------------------

def test_one_freshness_constant_for_tiers_dispatcher_and_brief(monkeypatch):
    assert dt.ALERT_FRESH_HOURS == fr.ALERT_FRESH_HOURS == ad.DEFAULT_FRESH_HOURS == 6.0
    assert be.URGENT_MAX_AGE_HOURS == fr.BRIEF_FRESH_HOURS
    assert ad.fresh_window() == fr.alert_window() == timedelta(hours=6)
    monkeypatch.setenv(fr.ALERT_FRESH_ENV, "2")
    assert ad.fresh_window() == fr.alert_window() == timedelta(hours=2)


def test_tier_alert_and_dispatcher_agree_on_a_7h_old_incident():
    events = [ev("a1", "Optus customers hit by nationwide mobile outage", "ABC News", 7), ev("a2", "Optus outage: thousands unable to make calls", "SMH", 7.1)]
    td, inc = tier_of(events, "Optus customers")
    assert td.tier != dt.IMMEDIATE_ALERT                      # 7 h > the shared 6 h window
    assert ad.alertable_reports(inc, NOW) == []               # and the dispatcher agrees
    fresh = [ev("a1", "Optus customers hit by nationwide mobile outage", "ABC News", 1), ev("a2", "Optus outage: thousands unable to make calls", "SMH", 1.1)]
    td2, inc2 = tier_of(fresh, "Optus customers")
    assert td2.tier == dt.IMMEDIATE_ALERT and ad.alertable_reports(inc2, NOW)


# D6: stale or non-incident material is never a current scheduled incident --------------------------------------------------

def test_stale_quake_is_context_not_scheduled():
    td, _ = tier_of([ev("q1", "Top End shaken as major quake hits East Timor", hours_ago=66)], "quake")
    assert td.tier not in (dt.SCHEDULED_BRIEF, dt.IMMEDIATE_ALERT)


def test_tsunami_staffing_policy_story_is_not_an_incident():
    for hours in (1, 65):
        td, _ = tier_of([ev("t1", "Tsunami response window shorter after staff pulled from remote island", hours_ago=hours)], "Tsunami")
        assert td.tier == dt.REFERENCE_RETAIN, hours


def test_real_hazard_event_is_not_swallowed_by_the_policy_guard():
    td, _ = tier_of([ev("t2", "Tsunami warning issued for Queensland coast, residents told to evacuate", hours_ago=1)], "Tsunami warning")
    assert td.tier != dt.REFERENCE_RETAIN


# D4/5: exposures and warnings are preserved without a stated consequence ---------------------------------------------------

def test_exploited_critical_advisory_is_scheduled_as_exposure_not_reference():
    e = ev("v1", "CRITICAL ALERT: Critical vulnerabilities in Citrix NetScaler ADC and Gateway", "ACSC Alerts & Advisories", 3, geography="AU")
    td, _ = tier_of([e], "Citrix")
    assert td.tier == dt.SCHEDULED_BRIEF and td.evidence.get("exposure") is True


def test_critical_rce_advisory_with_no_stated_consequence_is_kept_at_monitor():
    e = ev("v2", "Vulnerabilities in nginx Affecting Cisco Products: November 2026", "Cisco Security Advisories", 40, geography="GLOBAL",
           summary="nginx announced a fix for multiple critical vulnerabilities that could lead to remote code execution.")
    td, _ = tier_of([e], "nginx")
    assert td.tier == dt.MONITOR and td.evidence.get("exposure") is True


def test_old_advisory_is_not_kept_forever():
    e = ev("v3", "Vulnerabilities in nginx Affecting Cisco Products", "Cisco Security Advisories", 100, geography="GLOBAL",
           summary="critical vulnerabilities that could lead to remote code execution")
    td, _ = tier_of([e], "nginx")
    assert td.tier == dt.REFERENCE_RETAIN


def test_credible_fire_warning_is_monitored_not_reference():
    td, _ = tier_of([ev("f1", "Breaking: Emergency fire warning issued for Victoria's north-west", hours_ago=20, geography="AU")], "fire warning")
    assert td.tier == dt.MONITOR


def test_stale_warning_ages_out():
    td, _ = tier_of([ev("f2", "Breaking: Emergency fire warning issued for Victoria's north-west", hours_ago=90, geography="AU")], "fire warning")
    assert td.tier == dt.REFERENCE_RETAIN


# NT is Australian ---------------------------------------------------------------------------------------------------------

def test_nt_government_is_an_australian_marker():
    assert ed._au_marker("NT government departments hit by massive network outage")


# Additive tiered view and one incident id --------------------------------------------------------------------------------

def _evidence(events):
    return be.build_evidence(events, now=NOW, window_hours=72)


def test_tiered_view_is_additive_over_morning_v1_sections():
    events = [ev("c1", "Coles Group investigating a cyber incident", "iTnews", 3), ev("c2", "Coles investigates cyber attack but provides little detail", "ABC News", 2),
              ev("w1", "Vulnerabilities in nginx Affecting Cisco Products: November 2026", "Cisco Security Advisories", 30, geography="GLOBAL",
                 summary="critical vulnerabilities that could lead to remote code execution")]
    evidence = _evidence(events)
    lines, shown = tb.render(events, now=NOW, window_hours=72, evidence=evidence, be=be)
    text = "\n".join(lines)
    v1 = "\n".join(be.morning_view(evidence))
    assert "TIERED INCIDENT PICTURE" in text and tb.V1_DETAIL_HEADING in text
    for marker in ("Operational implications", "Forward watch", "WORTH KNOWING", "Nothing to report in"):
        assert (marker in v1) == (marker in text), marker      # nothing V1 prints is lost
    assert shown


def test_historical_only_v1_incident_is_not_carried_as_current():
    events = [ev("h1", "Telstra outage in July retold: what does the share buyback after the July outage mean", "Google News - Telstra", 3)]
    incidents = ic.cluster_incidents(events, now=NOW, force=True)
    view = tb.v1_additive_view(_evidence(events), incidents)
    rels = {r.relation for inc in incidents for r in inc.reports}
    assert (ic.HISTORICAL_REFERENCE in rels) == (len(view.incidents) == 0)


def test_one_incident_id_across_brief_alert_snapshot_and_link(monkeypatch):
    monkeypatch.setenv("PORTAL_BASE_URL", "https://hq.example.test")
    events = [ev("m1", "Optus customers hit by nationwide mobile outage", "ABC News", 1), ev("m2", "Optus outage: thousands unable to make calls", "SMH", 1.1)]
    incidents = ic.cluster_incidents(events, now=NOW, force=True)
    canonical = {tb.incident_id(i) for i in incidents}
    view = tb.v1_additive_view(_evidence(events), incidents)
    assert {v.incident_id for v in view.incidents} <= canonical                       # brief citations use the canonical id
    lines, _ = tb.render(events, now=NOW, window_hours=72, evidence=_evidence(events), be=be)
    text = "\n".join(lines)
    for cid in canonical:
        if cid in text:
            assert f"https://hq.example.test/intelligence-workbench?tab=incidents#{cid}" in text   # the canonical link builder
    alerts = ad.process(incidents, now=NOW, force=True)
    assert alerts and all(a["incident_id"] in canonical and a["link"] == tb.incident_link(a["incident_id"]) for a in alerts)


# Frozen reference scorecard ------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def scorecard():
    reference = json.loads(cm.REF.read_text(encoding="utf-8"))
    return cm.measure(load_events(cm.EXPORT), reference)


def test_material_detection_is_not_below_morning_v1(scorecard):
    s = scorecard["systems"]
    n = lambda k: int(s[k]["material_detected"].split("/")[0])
    assert s["tiered"]["material_detected"].endswith("/13")
    assert n("tiered") >= 8                                   # tiers alone: the pre-fix value was 5 of 13
    assert n("tiered_additive") >= n("morning_v1") >= 8
    assert set(s["morning_v1"]["material_detected_ids"]) - {"RS-005"} <= set(s["tiered"]["material_detected_ids"])


def test_no_false_urgency_and_negatives_do_not_regress(scorecard):
    s = scorecard["systems"]
    assert s["tiered"]["false_urgency_records"] == [] == s["tiered_additive"]["false_urgency_records"]
    assert len(s["tiered_additive"]["negatives_reaching_brief_level"]) <= len(s["morning_v1"]["negatives_reaching_brief_level"])
    assert s["tiered"]["negatives_reaching_brief_level"] == []
    assert s["tiered"]["material_alerted"] == s["morning_v1"]["material_alerted"]


# Codex finding: maintenance/upgrade wording must not demote a stated live outage -------------------------------------------

NAB = "Breaking: NAB customers experiencing phone and internet banking outages after failed upgrade"


def test_nab_failed_upgrade_outage_is_an_alert_not_advance_notice():
    events = [ev("n1", NAB, "ABC News", 1), ev("n2", "NAB outage: customers unable to use internet banking", "SMH", 0.9)]
    td, _ = tier_of(events, "NAB customers")
    assert td.tier == dt.IMMEDIATE_ALERT, td.reasons
    td1, _ = tier_of([ev("n1", NAB, "ABC News", 1)], "NAB customers")
    assert td1.tier in (dt.IMMEDIATE_ALERT, dt.SCHEDULED_BRIEF) and "planned" not in td1.reasons[0]


def test_later_cause_update_does_not_suppress_the_incident():
    events = [ev("n1", "NAB customers experiencing phone and internet banking outages", "ABC News", 2),
              ev("n3", "NAB blames maintenance upgrade for banking outages, customers still unable to log in", "SMH", 1)]
    td, _ = tier_of(events, "NAB")
    assert td.tier == dt.IMMEDIATE_ALERT, td.reasons


def test_genuinely_planned_future_window_is_still_monitor():
    td, _ = tier_of([ev("p1", "NAB internet banking will be offline for scheduled maintenance from 10pm on 28 November", "ABC News", 1)], "NAB internet")
    assert td.tier == dt.MONITOR and "planned" in td.reasons[0]


def test_bare_maintenance_word_is_not_planned():
    assert not dt._is_planned([])
    td, _ = tier_of([ev("p2", "Optus network upgrade leaves thousands of customers without mobile service", "ABC News", 1)], "Optus network")
    assert td.tier != dt.MONITOR or "planned" not in td.reasons[0]
