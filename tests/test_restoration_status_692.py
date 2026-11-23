"""PR #692 follow-up: restoration status is explicit and exhaustive (ongoing | partially_restored | restored | unknown).

Written FIRST, to fail on origin/main and on the first #692 commit:
- a stale continuation cue was dropped while the word 'restored' survived, so 'Power partly restored after Sydney outage, thousands
  still without' at 50h read as RESTORED;
- 'Power partly restored after Sydney outage' read as RESTORED even when fresh (partial restoration over-read as recovery);
- a report with no published time (Google News and other feeds) was timed by its COLLECTION time, so a 9-day-old republished
  'outage continues' story looked live.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from intelligence import brief_evidence as be
from intelligence import event_detection as ed

NOW = datetime(2026, 11, 23, 20, 0, tzinfo=timezone.utc)


def _ts(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ev(i, title, hours_ago, *, src="ABC News", published_hours_ago="same", collected_hours_ago=None):
    """A report published ``hours_ago`` (verified time). ``published_hours_ago=None`` drops the published time (unverified)."""
    collected = hours_ago if collected_hours_ago is None else collected_hours_ago
    row = {"id": i, "title": title, "summary": "", "source": src, "geography": "AU", "collected_at": _ts(collected), "url": f"https://x/{i}"}
    pub = hours_ago if published_hours_ago == "same" else published_hours_ago
    if pub is not None:
        row["published_at"] = _ts(pub)
    return row


def status(events, member="a"):
    d = next(d for d in ed.run(events, now=NOW) if member in {m.event_id for m in d.group.members})
    return ed.escalation_record(d, now=NOW)["restoration_status"]


def status_of(cands):
    return ed._restoration_status(cands, NOW)


def chron(rows):
    """The multi-report chronology path, on the reports themselves (grouping is decided elsewhere)."""
    return status_of([ed.detect_candidate(r) for r in rows])


STILL = "Optus outage continues across Sydney"
PARTLY_STILL = "Power partly restored after Sydney outage, thousands still without"
PARTLY = "Power partly restored after Sydney outage"
RESTORED = "Power restored across Sydney after outage"
MIXED = "Power restored but thousands still without after Sydney outage"
STATED = "Telstra mobile outage leaves customers unable to make calls across Australia"


# ── the four statuses, single-report path ─────────────────────────────────────────────────────────────────
def test_single_report_ongoing():
    assert status([ev("a", STILL, 3)]) == "ongoing"


def test_single_report_partially_restored():
    assert status([ev("a", PARTLY, 3)]) == "partially_restored"          # main: "restored"


def test_single_report_restored():
    assert status([ev("a", RESTORED, 3)]) == "restored"


def test_single_report_unknown_when_cue_is_stale():
    assert status([ev("a", STILL, 50)]) == "unknown"


@pytest.mark.parametrize("title", [
    "Power partially restored after Sydney outage",
    "Power mostly restored after Sydney outage",
    "Power restored for most customers after Sydney outage",
    "Power back for most after Sydney outage",
    "Optus services returning after nationwide outage",
    "Services being restored after Optus outage",
])
def test_partial_restoration_wording(title):
    assert status([ev("a", title, 3)]) == "partially_restored"


# ── the exact probe cases ─────────────────────────────────────────────────────────────────────────────────
def test_probe_partly_restored_with_stale_still_is_never_restored():
    assert status([ev("a", PARTLY_STILL, 50)]) == "unknown"             # #692 first commit: "restored"


def test_probe_partly_restored_with_live_still_is_ongoing():
    assert status([ev("a", PARTLY_STILL, 3)]) == "ongoing"


def test_probe_stale_partial_is_unknown():
    assert status([ev("a", PARTLY, 50)]) == "unknown"                   # main: "restored"


def test_probe_stale_back_for_most_but_continues_is_unknown():
    assert status([ev("a", "Power back for most but outage continues for thousands in Sydney", 50)]) == "unknown"


@pytest.mark.parametrize("age, expected", [(3, "ongoing"), (50, "unknown"), (100, "unknown")])
def test_mixed_restored_but_still_without_is_never_restored(age, expected):
    """Live: the 'still without' clause makes it ongoing. Stale: the cue cannot establish current state, and it must never fall back
    to the surviving word 'restored'."""
    assert status([ev("a", MIXED, age)]) == expected


# ── the four statuses, multi-report chronology path ───────────────────────────────────────────────────────
def test_chronology_ongoing():
    assert chron([ev("a", RESTORED, 30), ev("b", "Sydney power outage still affecting thousands", 2)]) == "ongoing"


def test_chronology_partially_restored_after_restored():
    assert chron([ev("a", RESTORED, 10), ev("b", PARTLY, 3)]) == "partially_restored"


def test_chronology_restored_after_partial():
    assert chron([ev("a", PARTLY, 10), ev("b", RESTORED, 3)]) == "restored"


def test_chronology_unknown_when_latest_is_a_stale_still():
    assert chron([ev("a", RESTORED, 90), ev("b", "Sydney power outage still affecting thousands", 60)]) == "unknown"


def test_chronology_stale_still_then_fresh_restored():
    assert chron([ev("a", "Sydney power outage still affecting thousands", 60), ev("b", RESTORED, 3)]) == "restored"


def test_chronology_restored_then_stated_reopen_that_aged_out_is_unknown():
    assert chron([ev("a", RESTORED, 30), ev("b", "Sydney power outage leaves thousands without power again", 20)]) == "unknown"


def test_chronology_restored_then_fresh_reopen_is_ongoing():
    assert chron([ev("a", RESTORED, 30), ev("b", "Sydney power outage leaves thousands without power again", 2)]) == "ongoing"


def test_chronology_restored_then_fresh_partial_reopen_is_partial():
    assert chron([ev("a", RESTORED, 30), ev("b", "Power partially restored after second Sydney outage", 2)]) == "partially_restored"


def test_same_instant_tie_less_resolved_wins():
    a = ed.detect_candidate(ev("a", RESTORED, 3))
    b = ed.detect_candidate(ev("b", "Sydney power outage still affecting thousands", 3))
    c = ed.detect_candidate(ev("c", PARTLY, 3))
    assert status_of([a, b]) == "ongoing"
    assert status_of([a, c]) == "partially_restored"
    assert status_of([a, b, c]) == "ongoing"


def _long_running(latest_hours_ago):
    ages = [144, 120, 96, 72, latest_hours_ago] if latest_hours_ago < 72 else [144, 120, 96, latest_hours_ago]
    return [ed.detect_candidate(ev(f"r{n}", "Sydney power outage still affecting thousands of homes", h)) for n, h in enumerate(ages)]


def test_long_running_incident_latest_fresh_update_is_ongoing():
    assert status_of(_long_running(2)) == "ongoing"


def test_long_running_incident_latest_update_three_days_old_is_unknown():
    assert status_of(_long_running(72)) == "unknown"


def test_long_running_incident_restored_then_reopened():
    cands = _long_running(40) + [ed.detect_candidate(ev("x", RESTORED, 30)),
                                 ed.detect_candidate(ev("y", "Sydney power outage leaves thousands without power again", 2))]
    assert status_of(cands) == "ongoing"


# ── time verification ─────────────────────────────────────────────────────────────────────────────────────
def test_time_verified_flag():
    assert ed.detect_candidate(ev("a", STILL, 3)).time_verified is True
    assert ed.detect_candidate(ev("a", STILL, 3, published_hours_ago=None)).time_verified is False
    # a published time later than collection (+1h skew) is not a verified publication time
    assert ed.detect_candidate(ev("a", STILL, 3, published_hours_ago=0, collected_hours_ago=3)).time_verified is False
    assert ed.detect_candidate(ev("a", STILL, 3, published_hours_ago=2.5, collected_hours_ago=3)).time_verified is True


def test_no_published_time_continuation_is_unknown():
    assert status([ev("a", STILL, 2, published_hours_ago=None)]) == "unknown"     # main: "ongoing"


def test_nine_day_old_republished_continues_is_never_ongoing():
    # Google News row: no published time; collected an hour ago, story is nine days old
    gn = "Google News - Critical Infrastructure/Energy Cyberattack AU"
    assert status([ev("a", STILL, 1, src=gn, published_hours_ago=None)]) == "unknown"
    # and with its real (old) published time it is a stale cue
    assert status([ev("a", STILL, 9 * 24, src=gn, collected_hours_ago=1)]) == "unknown"


def test_fresh_unverified_stated_report_is_unknown():
    assert status([ev("a", STATED, 2, published_hours_ago=None)]) == "unknown"    # main: "ongoing"
    assert status([ev("a", STATED, 2)]) == "ongoing"


def test_unverified_partial_is_unknown():
    assert status([ev("a", PARTLY, 2, published_hours_ago=None)]) == "unknown"


def test_report_time_fallback_unchanged():
    row = ev("a", STILL, 2, published_hours_ago=None)
    assert ed._report_time(row) == NOW - timedelta(hours=2)


# ── consumers ─────────────────────────────────────────────────────────────────────────────────────────────
def _view(n, restoration, priority="WATCH", evidence="corroborated"):
    return be.IncidentView(
        incident_id=f"inc-{n}", headline=f"Sydney power outage {n}", priority=priority, materiality="high", sector_tier=1,
        event_type="outage", impact_status="stated", evidence_status=evidence, evidence_basis=["ABC News"], evidence_confidence=0.8,
        independent_publishers=2, provisional=False, grouping_confidence=0.9,
        reports=[{"report_id": f"r{n}", "publisher": "ABC News", "source_name": "ABC News", "source_kind": "mainstream", "title": "t",
                  "url": None, "collected_at": None, "published_at": None, "role": "original", "geography": "AU", "summary": ""}],
        first_seen=NOW - timedelta(hours=2), last_seen=NOW - timedelta(hours=2),
        record={"impact": "stated in headline", "affected_customers": None, "duration": None, "restoration_status": restoration,
                "critical_service_dependencies": ["energy"], "next_verification_action": "check"})


def _evset(*views):
    return be.EvidenceSet("test", NOW, 24, len(views), list(views))


def test_partial_counts_as_current_disruption_and_is_labelled():
    text = "\n".join(be.morning_view(_evset(_view(1, "partially_restored"), _view(2, "unknown"))))
    assert "Operational situation: 1 confirmed or corroborated" in text
    assert "1 more reported with current status unknown" in text
    assert "partially restored" in text
    assert "partially_restored" not in text


def test_forward_watch_lists_partial_but_not_restored_or_unknown():
    text = "\n".join(be.morning_view(_evset(_view(1, "partially_restored"), _view(2, "restored"), _view(3, "unknown"), _view(4, "ongoing"))))
    fw = text.split("Forward watch", 1)[1]
    assert "Sydney power outage 1" in fw and "Sydney power outage 4" in fw
    assert "Sydney power outage 2" not in fw and "Sydney power outage 3" not in fw
    assert "(restoration partially restored)" in fw


def _prev(restoration):
    return {"date": "2026-11-16", "incidents": [{"incident_id": "inc-old", "report_ids": ["r1"], "headline": "h", "priority": "WATCH",
                                                 "materiality": "high", "evidence_status": "corroborated",
                                                 "restoration_status": restoration}], "patterns": []}


@pytest.mark.parametrize("prev, cur, resolved", [
    ("ongoing", "partially_restored", False), ("ongoing", "unknown", False), ("partially_restored", "partially_restored", False),
    ("ongoing", "restored", True), ("partially_restored", "restored", True), ("restored", "restored", False),
])
def test_compare_snapshots_resolved_only_for_restored(prev, cur, resolved):
    out = be.compare_snapshots(_prev(prev), _evset(_view(1, cur)))
    assert bool(out["resolved"]) is resolved


def test_snapshot_payload_keeps_the_explicit_status():
    assert be.snapshot_payload(_evset(_view(1, "partially_restored")))["incidents"][0]["restoration_status"] == "partially_restored"


def test_partial_outage_keeps_the_live_restoration_action():
    assert "restoration estimate" in ed._next_action("outage", "stated", "partially_restored")
    assert "no live restoration action" in ed._next_action("outage", "stated", "restored")
    assert "confirm the disruption is current" in ed._next_action("outage", "stated", "unknown")


def test_statuses_are_exhaustive():
    assert set(ed.RESTORATION_STATUSES) == {"ongoing", "partially_restored", "restored", "unknown"}
