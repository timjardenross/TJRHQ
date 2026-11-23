"""#669 (morning-quality concern 1): retrospective reporting must not be labelled as an ongoing live disruption without
current evidence.

Written to FAIL on the pre-fix behaviour: every report with no restored/retrospective cue defaulted to ongoing=True, and
_restoration_status() returned "ongoing" for any stated report, however old; 'APRA calls Microsoft outage a "near miss"'
(commentary on a past outage, three days old) was shown as ESCALATE and "ongoing".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from intelligence import brief_evidence as be
from intelligence import event_detection as ed

NOW = datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc)


def e(i, title, source, age_hours, geo="AU"):
    return {"id": i, "title": title, "source": source, "geography": geo, "summary": "",
            "collected_at": (NOW - timedelta(hours=age_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def decision(events, member="a"):
    return next(d for d in ed.run(events, now=NOW) if member in {m.event_id for m in d.group.members})


def restoration(events, now=NOW):
    return ed.escalation_record(decision(events), now=now)["restoration_status"]


NEAR_MISS = 'APRA calls Microsoft outage a "near miss" for financial system'
OLD_STATED = "Telstra mobile outage leaves customers unable to make calls across Australia"


def test_near_miss_commentary_is_retrospective_not_live():
    d = decision([e("a", NEAR_MISS, "Insurance Business", 53)])
    assert d.impact_status == "retrospective"                              # pre-fix: "stated"
    assert d.priority != "ESCALATE"                                        # a past event is never an escalation on its own
    assert ed.escalation_record(d, now=NOW)["restoration_status"] != "ongoing"


def test_a_well_corroborated_near_miss_is_not_escalated_either():
    """The real case: five publishers carried the APRA commentary, which made it ESCALATE and ongoing."""
    evs = [e(f"r{n}", NEAR_MISS + f" - Publisher {n}", src, 53 + n)
           for n, src in enumerate(["Insurance Business", "ABC News", "The Guardian", "Financial Review", "ITnews"])]
    for d in ed.run(evs, now=NOW):
        assert d.priority != "ESCALATE"
        assert ed.escalation_record(d, now=NOW)["restoration_status"] != "ongoing"


def test_other_retrospective_cues_are_recognised():
    for t in ("Post-mortem of the Optus outage released", "Root cause of the Telstra outage identified",
              "Lessons from the Qantas systems failure"):
        c = ed.detect_candidate(e("a", t, "ABC News", 5))
        assert c is None or c.status != "stated", t


def test_an_old_stated_report_with_no_continuation_cue_is_not_called_ongoing():
    assert restoration([e("a", OLD_STATED, "ABC News", 48)]) == "unknown"   # pre-fix: "ongoing"


def test_a_fresh_stated_report_is_still_ongoing():
    assert restoration([e("a", OLD_STATED, "ABC News", 2)]) == "ongoing"


def test_an_explicit_continuation_cue_is_current_evidence_even_when_the_report_is_older():
    assert restoration([e("a", "Telstra outage continues for thousands across Australia", "ABC News", 30)]) == "ongoing"


def test_the_freshness_boundary():
    assert restoration([e("a", OLD_STATED, "ABC News", ed.FRESH_REPORT_HOURS - 1)]) == "ongoing"
    assert restoration([e("a", OLD_STATED, "ABC News", ed.FRESH_REPORT_HOURS + 1)]) == "unknown"


def test_callers_that_do_not_pass_now_keep_the_previous_rule():
    d = decision([e("a", OLD_STATED, "ABC News", 48)])
    assert ed.escalation_record(d)["restoration_status"] == "ongoing"      # compatibility for callers without a clock


def test_chronology_still_wins_over_freshness():
    assert restoration([e("a", "Telstra outage still affecting customers across Australia", "ABC News", 6),
                        e("b", "Telstra outage restored for customers across Australia", "The Guardian", 3)]) == "restored"


def test_the_morning_view_labels_a_retrospective_item_as_such_and_never_as_ongoing():
    ev = be.build_evidence([e("a", NEAR_MISS, "Insurance Business", 3)], now=NOW, window_hours=72)
    text = "\n".join(be.morning_view(ev))
    assert "Ongoing:" not in text                                           # not in the forward watch as a live disruption
    assert ", ongoing" not in text and "restoration ongoing" not in text   # nor in the facts line
    assert "retrospective report" in text                                   # and it says what it is
