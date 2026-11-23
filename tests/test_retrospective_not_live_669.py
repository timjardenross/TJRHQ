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


# ── Codex review of #676 ───────────────────────────────────────────────────────────────────────────────────────────
LIVE_ROOT_CAUSE = "Telstra mobile outage leaves 50000 customers unable to make calls as engineers investigate root cause"


def test_a_live_headline_that_mentions_root_cause_work_stays_live():
    """Codex P2: 'engineers investigate root cause' during a live outage must not become a retrospective report."""
    d = decision([e("a", LIVE_ROOT_CAUSE, "ABC News", 2)])
    assert d.impact_status == "stated"                                      # pre-fix: retrospective
    assert d.priority == "ESCALATE"                                         # pre-fix: WATCH
    assert ed.escalation_record(d, now=NOW)["restoration_status"] == "ongoing"
    assert "retrospective report" not in be._tag(be.build_evidence([e("a", LIVE_ROOT_CAUSE, "ABC News", 2)], now=NOW, window_hours=72).incidents[0])


def test_a_root_cause_that_has_been_found_is_retrospective():
    for t in ("Root cause of the Telstra outage identified", "Telstra confirms root cause of last week's outage",
              "Root cause analysis released for the Optus network failure", "Report reveals root cause of the Qantas systems failure"):
        c = ed.detect_candidate(e("a", t, "ABC News", 5))
        assert c is None or c.status != "stated", t


# ── A re-surfaced headline about a much older dated event (Microsoft "Friday 13th outage continues", seen on the 22nd) ──────────

MS13 = "Microsoft's Friday 13th outage continues with fraud and employee risk warnings - Insurance Business"


def test_a_continues_headline_naming_an_old_date_does_not_establish_ongoing():
    evs = [e("a", MS13, "Google News - Critical Infrastructure/Energy Cyberattack AU", 5.4)]      # collected 22 Nov; names Friday 13 Nov
    assert restoration(evs) == "unknown"                                  # pre-fix: "ongoing"
    assert restoration(evs, now=None) == "unknown"


def test_named_date_resolution_is_read_not_inferred():
    ref = datetime(2026, 11, 22, 19, 4, tzinfo=timezone.utc)
    assert ed.named_date(MS13, ref) == datetime(2026, 11, 13, tzinfo=timezone.utc)
    assert ed.named_date("Outage on 13 November continues", ref) == datetime(2026, 11, 13, tzinfo=timezone.utc)
    assert ed.named_date("Power out 14/11/2026 still", ref) == datetime(2026, 11, 14, tzinfo=timezone.utc)
    assert ed.named_date("Telstra outage continues", ref) is None


def test_a_continues_headline_with_no_old_date_is_still_ongoing():
    evs = [e("a", "Telstra mobile outage continues across Australia", "ABC News", 30)]
    assert restoration(evs) == "ongoing"


def test_a_recent_date_in_the_headline_does_not_make_a_continuation_historic():
    ref_title = "Outage on 22 November continues across Australia"                   # same day as the report
    assert restoration([e("a", ref_title, "ABC News", 5)]) == "ongoing"


def test_recent_independent_evidence_still_establishes_ongoing_alongside_a_historic_headline():
    evs = [e("a", MS13, "Google News - Critical Infrastructure/Energy Cyberattack AU", 5.4),
           e("b", "Microsoft outage still affecting Australian businesses, services remain down", "ABC News", 2)]
    assert restoration(evs, now=NOW) == "ongoing"


def test_the_morning_view_does_not_call_the_historic_item_ongoing():
    es = be.build_evidence([e("a", MS13, "Google News - Critical Infrastructure/Energy Cyberattack AU", 5.4)], now=NOW, window_hours=72)
    view = "\n".join(be.morning_view(es)).lower()
    assert "restoration ongoing" not in view and "- ongoing:" not in view and ", ongoing" not in view


# ── Context-specific verification actions ───────────────────────────────────────────────────────────────────

LIVE_RX = ("restoration estimate", "customer count")


def action(events, member="a"):
    return ed.escalation_record(decision(events, member), now=NOW)["next_verification_action"]


def test_a_retrospective_investigation_gets_no_live_restoration_task():
    a = action([e("a", "'One-in-2,000-year weather' to be investigated post-blackout", "ABC News", 20)])
    assert "restoration estimate" not in a and "customer count" not in a
    assert "no live restoration action" in a


def test_a_disruption_reported_restored_gets_a_post_incident_action():
    a = action([e("a", "Power restored after Eyre Peninsula blackout leaves 11,000 without electricity", "ABC News", 6)])
    assert "restoration estimate" not in a and "restoration time" in a


def test_a_live_outage_keeps_the_restoration_estimate_action():
    a = action([e("a", "Telstra mobile outage continues across Australia, thousands still without service", "ABC News", 3)])
    assert "restoration estimate" in a and "network operator" not in a


def test_an_outage_of_unknown_currency_is_first_checked_for_currency():
    a = action([e("a", MS13, "Google News - Critical Infrastructure/Energy Cyberattack AU", 5.4)])
    assert "restoration estimate" not in a and "no live restoration action" in a


def test_other_incident_classes_keep_their_class_specific_action():
    a = action([e("a", "Hijacked website testing tool plants card skimmer on Australian brands' sites", "iTnews", 3)])
    assert "restoration" not in a


def test_a_reopened_incident_counts_as_ongoing_only_while_the_reopening_report_is_current():
    evs = [e("a", "Telstra power outage restored for 20,000 customers in Adelaide", "ABC News", 30),
           e("b", "Telstra power outage leaves 20,000 customers in Adelaide without power again", "ABC News", 4)]
    assert restoration(evs) == "ongoing"                       # reopening report is 4h old
    old = [e("a", "Telstra power outage restored for 20,000 customers in Adelaide", "ABC News", 60),
           e("b", "Telstra power outage leaves 20,000 customers in Adelaide without power again", "ABC News", 40)]
    assert restoration(old) == "unknown"                       # 40h old with no cue: not live, but it still invalidates the earlier restoration
    assert "reported restored" not in action(old)


# ── Codex P2s on the historic-date guard ────────────────────────────────────────────────────────────────────

def test_a_historic_partial_restoration_is_never_read_as_restored():
    ev0 = [e("a", "Power from 13 November outage yet to be restored for 3,000 Adelaide customers", "ABC News", 5)]      # collected 22 Nov
    assert restoration(ev0) != "restored"
    assert "reported restored" not in action(ev0)


def test_a_historic_clean_restoration_is_still_restored():
    assert restoration([e("a", "Power from 13 November outage restored for 3,000 Adelaide customers", "ABC News", 5)]) == "restored"


def test_a_future_restoration_estimate_is_not_a_historical_date():
    ref = datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc)
    assert ed.named_date("Telstra outage continues across Australia, restoration expected on 24/11/2026", ref) is None
    assert ed.named_date("Telstra outage continues across Australia, restoration expected on 24 November", ref) is None
    evs = [e("a", "Telstra outage continues across Australia, restoration expected on 24/11/2026", "ABC News", 3)]
    assert restoration(evs) == "ongoing"
    assert "restoration estimate" in action(evs)


# ── Currency applies to priority, not only to status; an inquiry continuing is not a service disruption continuing (release review, High) ──

def test_a_recent_headline_about_an_old_dated_outage_is_not_escalated():
    d = decision([e("a", MS13, "Insurance Business", 5.4)])
    assert d.priority != "ESCALATE" and d.impact_status == "retrospective"
    assert ed.escalation_record(d, now=NOW)["restoration_status"] != "ongoing"


def test_an_inquiry_continuing_is_not_a_service_disruption_continuing():
    for t in ("Inquiry continues into Telstra outage that cut triple zero for thousands", "Review ongoing after Optus outage left millions offline",
              "Court case continues over Telstra triple zero outage"):
        d = decision([e("a", t, "ABC News", 3)])
        assert d.priority != "ESCALATE", t
        assert d.impact_status == "retrospective", t
        assert ed.escalation_record(d, now=NOW)["restoration_status"] != "ongoing", t


def test_a_genuinely_continuing_outage_is_still_ongoing_and_escalated():
    d = decision([e("a", "Telstra mobile outage continues across Australia, thousands still without service", "ABC News", 3)])
    assert d.impact_status == "stated"
    assert ed.escalation_record(d, now=NOW)["restoration_status"] == "ongoing"


def test_an_outage_continuing_into_another_day_is_still_a_live_outage():
    """Codex P2: 'continues into a third day' with no process subject is the outage continuing."""
    evs = [e("a", "Telstra outage continues into a third day, some services restored across Australia", "ABC News", 3)]
    d = decision(evs)
    assert d.impact_status == "stated"
    assert ed.escalation_record(d, now=NOW)["restoration_status"] == "ongoing"


def test_live_outage_wording_with_restored_or_resolved_is_not_retrospective():
    """Review MEDIUM: forecast / wait / negated restoration describes a live outage, not a retrospective one."""
    for t in ("Ausgrid outage: power will be restored by 5pm for 8,000 homes",
              "Telstra outage: services remain down until resolved for 20,000 customers",
              "Optus outage: power not restored for 5,000 homes"):
        d = decision([e("a", t, "ABC News", 1)])
        assert d.group.members[0].status != "retrospective", t
        rec = ed.escalation_record(d, now=NOW)
        assert rec["restoration_status"] != "restored", t


def test_completed_restoration_is_still_retrospective():
    d = decision([e("a", "Ausgrid outage: power restored for 8,000 homes", "ABC News", 1)])
    assert d.group.members[0].status == "retrospective"


def test_modal_may_followed_by_a_count_is_not_a_date():
    d = decision([e("a", "Ausgrid outage may 10,000 homes without power", "ABC News", 1)])
    assert d.group.members[0].status != "retrospective"
    assert ed.named_date("Ausgrid outage may 10,000 homes without power", NOW) is None
    assert ed.named_date("Ausgrid outage on May 10 left homes without power", NOW) is not None
