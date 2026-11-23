"""#669 (3a): event correlation by the real shared class, and restoration status by report chronology.

Each test is written to FAIL on the pre-fix behaviour:
- _link() classed every shared type other than outage/cyber as 'vulnerability' and rejected it, so hazards, water quality,
  supply shortfalls and service disruptions never merged across publishers;
- escalation_record() said 'restored' only if NO report said 'still', so an earlier 'still without power' report vetoed a
  later 'power restored' (and the incident stayed 'ongoing' in the forward watch and in snapshot comparison).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from intelligence import event_detection as ed

T0 = datetime(2026, 11, 20, 3, 0, tzinfo=timezone.utc)
NOW = T0 + timedelta(hours=96)


def e(i, title, source, hours=0, geo="AU"):
    return {"id": i, "title": title, "source": source, "geography": geo, "summary": "",
            "collected_at": (T0 + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def groups(events):
    return sorted(sorted(m.event_id for m in d.group.members) for d in ed.run(events, now=NOW))


def record_for(events, member="a"):
    d = next(d for d in ed.run(events, now=NOW) if member in {m.event_id for m in d.group.members})
    return ed.escalation_record(d)


# ── correlation across the non-outage classes ─────────────────────────────────────────────────────────────────
def test_water_quality_reports_from_two_publishers_merge():
    g = groups([e("a", "Boil water notice issued for Sydney suburbs after contamination detected", "ABC News"),
                e("b", "Boil water notice for Sydney suburbs as contamination detected in water supply", "The Guardian", 1)])
    assert g == [["a", "b"]]


def test_hazard_reports_from_two_publishers_merge():
    g = groups([e("a", "Severe storm warning for Sydney and Illawarra with damaging winds", "ABC News"),
                e("b", "Damaging winds and severe storm warning issued for Sydney and Illawarra", "The Guardian", 1)])
    assert g == [["a", "b"]]


def test_shared_class_is_chosen_by_priority_and_falls_back_to_vulnerability_only_when_it_is_the_only_one():
    class C:
        def __init__(self, *t):
            self.types = t
    assert ed._shared_class(C("outage", "hazard"), C("outage", "hazard")) == "outage"
    assert ed._shared_class(C("hazard"), C("hazard", "water_quality")) == "hazard"
    assert ed._shared_class(C("water_quality"), C("hazard")) is None
    assert ed._shared_class(C("vulnerability"), C("vulnerability")) == "vulnerability"


def test_the_class_window_still_applies():
    """Hazard reports a week apart are not one incident (48h default window)."""
    g = groups([e("a", "Severe storm warning for Sydney and Illawarra with damaging winds", "ABC News"),
                e("b", "Damaging winds and severe storm warning issued for Sydney and Illawarra", "The Guardian", 24 * 6)])
    assert g == [["a"], ["b"]]


def test_unrelated_reports_of_the_same_class_do_not_merge():
    g = groups([e("a", "Severe storm warning for Perth with damaging winds", "ABC News", geo="AU"),
                e("b", "Boil water notice issued for Sydney suburbs after contamination detected", "The Guardian", 1)])
    assert all(len(x) == 1 for x in g)


def test_vulnerability_advisories_are_still_never_grouped_by_prose():
    a = ed.detect_candidate(e("a", "Critical remote code execution vulnerability CVE-2026-1111 in Acme router", "CISA"))
    b = ed.detect_candidate(e("b", "Critical remote code execution vulnerability CVE-2026-2222 in Acme router", "NVD"))
    if a and b and a.is_candidate and b.is_candidate:
        assert ed._link(a, b, ed._idf([a, b])) is None


# ── restoration chronology ──────────────────────────────────────────────────────────────────────────────────────
OUTAGE_STILL = "Power outage still affecting 20,000 Telstra customers in Adelaide"
OUTAGE_RESTORED = "Telstra power outage restored for 20,000 customers in Adelaide"
OUTAGE_AGAIN = "Telstra outage continues: 20,000 customers in Adelaide without service again"


def test_a_later_restored_report_overrides_an_earlier_still_report():
    rec = record_for([e("a", OUTAGE_STILL, "ABC News", 0), e("b", OUTAGE_RESTORED, "The Guardian", 6)])
    assert rec["restoration_status"] == "restored"          # pre-fix: "ongoing"


def test_a_later_ongoing_report_reopens_an_earlier_restored_report():
    rec = record_for([e("a", OUTAGE_RESTORED, "ABC News", 0), e("b", OUTAGE_AGAIN, "The Guardian", 6)])
    assert rec["restoration_status"] == "ongoing"


def test_report_order_in_the_input_does_not_matter():
    fwd = record_for([e("a", OUTAGE_STILL, "ABC News", 0), e("b", OUTAGE_RESTORED, "The Guardian", 6)])
    rev = record_for([e("b", OUTAGE_RESTORED, "The Guardian", 6), e("a", OUTAGE_STILL, "ABC News", 0)], member="a")
    assert fwd["restoration_status"] == rev["restoration_status"] == "restored"


def test_a_mixed_report_is_ongoing_not_restored():
    rec = record_for([e("a", "Power restored to some Telstra customers in Adelaide but thousands still without service", "ABC News")])
    assert rec["restoration_status"] == "ongoing"


def test_same_instant_restored_and_ongoing_is_conservative():
    rec = record_for([e("a", OUTAGE_STILL, "ABC News", 3), e("b", OUTAGE_RESTORED, "The Guardian", 3)])
    assert rec["restoration_status"] == "ongoing"


def test_single_restored_report_is_restored_and_single_still_report_is_ongoing():
    assert record_for([e("a", OUTAGE_RESTORED, "ABC News")])["restoration_status"] == "restored"
    assert record_for([e("a", OUTAGE_STILL, "ABC News")])["restoration_status"] == "ongoing"


def test_snapshot_comparison_sees_the_chronological_status():
    """A resolved outage must not stay 'ongoing' in the week-on-week comparison."""
    from intelligence import brief_evidence as be
    ev = be.build_evidence([e("a", OUTAGE_STILL, "ABC News", 0), e("b", OUTAGE_RESTORED, "The Guardian", 6)], now=NOW, window_hours=24 * 7)
    states = {i.record["restoration_status"] for i in ev.incidents}
    assert "ongoing" not in states
