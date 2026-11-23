"""#669 (evidence integrity): a hedged or anonymously sourced report must not count towards corroboration.

Written to FAIL on the pre-fix behaviour: evidence_status() required a non-hedged report but then used
group.independent_publishers, which also counts hedged publishers, so one solid report plus one 'reportedly' report
from a second publisher was labelled 'corroborated'.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from intelligence import event_detection as ed

T0 = datetime(2026, 11, 20, 3, 0, tzinfo=timezone.utc)
NOW = T0 + timedelta(hours=48)


def e(i, title, source, hours=0, summary=""):
    return {"id": i, "title": title, "source": source, "geography": "AU", "summary": summary,
            "collected_at": (T0 + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")}


import dataclasses

from intelligence import weekly_evidence as we


def cand(i, title, source, hours=0, **over):
    c = ed.detect_candidate(e(i, title, source, hours))
    assert c is not None, "fixture must be a candidate"
    return dataclasses.replace(c, **over) if over else c


def group_of(members, independent_publishers):
    """Group as correlate() builds it for two reports from different publishers that are not syndicated copies."""
    return ed.Group("inc-test", members, [], 0.9, independent_publishers, [], [])


A = lambda: cand("a", "Power outage hits 20,000 customers in SA", "ABC News", family="abc news", kind=we.MAINSTREAM, hedged=False)
B_HEDGED = lambda: cand("b", "Power cut leaves thousands in the dark in SA, utility reportedly says", "The Guardian", 1,
                        family="the guardian", kind=we.MAINSTREAM, hedged=True)
B_SOLID = lambda: cand("b", "Power cut leaves thousands in the dark in SA", "The Guardian", 1,
                       family="the guardian", kind=we.MAINSTREAM, hedged=False)


def test_second_publisher_that_is_hedged_does_not_corroborate():
    status, _ = ed.evidence_status(group_of([A(), B_HEDGED()], independent_publishers=2))
    assert status == "reported"      # pre-fix: "corroborated" (counted the hedged publisher)


def test_two_hedged_publishers_are_unverified():
    a = dataclasses.replace(A(), hedged=True)
    status, _ = ed.evidence_status(group_of([a, B_HEDGED()], independent_publishers=2))
    assert status == "unverified"


def test_two_solid_independent_publishers_still_corroborate():
    status, _ = ed.evidence_status(group_of([A(), B_SOLID()], independent_publishers=2))
    assert status == "corroborated"


def test_primary_unhedged_report_is_still_officially_confirmed():
    primary = dataclasses.replace(A(), kind=we.PRIMARY)
    status, _ = ed.evidence_status(group_of([primary, B_HEDGED()], independent_publishers=2))
    assert status == "officially_confirmed"


def test_end_to_end_run_never_reports_corroborated_for_a_hedged_second_report():
    decs = ed.run([e("a", "Power outage hits 20,000 customers in SA", "ABC News"),
                   e("b", "Network fault reportedly leaves South Australian homes without power", "The Guardian", 1)], now=NOW)
    assert all(d.evidence_status != "corroborated" for d in decs)
