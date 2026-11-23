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


# ── Codex review of #674: same-class incidents at different places, and partial restoration ──────────────────────
def test_same_class_reports_naming_different_places_are_different_incidents():
    """Codex P2: two AU boil-water notices six hours apart for Sydney and Melbourne merged (shared sector + generic terms)."""
    g = groups([e("a", "Boil water notice for Sydney suburbs after contamination in drinking water", "ABC News", 0),
                e("b", "Boil water notice for Melbourne suburbs after contamination in drinking water", "The Guardian", 6)])
    assert g == [["a"], ["b"]]


def test_same_class_reports_naming_the_same_place_still_merge():
    g = groups([e("a", "Boil water notice issued for Sydney suburbs after contamination detected", "ABC News"),
                e("b", "Boil water notice for Sydney suburbs as contamination detected in water supply", "The Guardian", 1)])
    assert g == [["a", "b"]]


def test_a_report_naming_no_place_is_not_blocked_from_merging():
    a = ed.detect_candidate(e("a", "Boil water notice for Sydney suburbs after contamination in drinking water", "ABC News"))
    b = ed.detect_candidate(e("b", "Boil water notice for suburbs after contamination in drinking water", "The Guardian", 1))
    assert not ed._location_conflict(a, b)


def test_place_aliases_are_normalised():
    assert ed._places("Victorian floods and flooding in victoria and NSW and New South Wales") == frozenset({"victoria", "nsw"})


def test_the_location_guard_does_not_apply_to_outage_or_cyber_links():
    """Outage / cyber links keep their existing guards; a national outage is not split by the cities it names."""
    g = groups([e("a", "Telstra mobile outage leaves customers in Sydney unable to make calls", "ABC News", 0),
                e("b", "Telstra mobile outage leaves customers in Melbourne unable to make calls", "The Guardian", 1)])
    assert g == [["a", "b"]]


def test_a_partly_restored_report_after_a_still_report_stays_ongoing():
    """Codex P2: 'restored to some ... but thousands without power' has no 'still' word but is not a restoration."""
    rec = record_for([e("a", "Power outage still affecting 20,000 Telstra customers in Adelaide", "ABC News", 0),
                      e("b", "Power restored to some Telstra customers in Adelaide but thousands without power", "The Guardian", 6)])
    assert rec["restoration_status"] == "ongoing"          # pre-fix: "restored"


def test_partial_restoration_phrases_are_not_restoration():
    for t in ("Telstra outage partially restored in Adelaide", "Power yet to be restored for 3,000 Adelaide customers",
              "Not all Adelaide customers restored after Telstra outage", "Power restored in Adelaide but 4,000 homes remain offline"):
        assert ed._report_state(ed.detect_candidate(e("a", t, "ABC News"))) in ("ongoing", None), t


def test_a_clean_restoration_is_still_restored():
    assert ed._report_state(ed.detect_candidate(e("a", "Telstra power outage restored for 20,000 customers in Adelaide", "ABC News"))) == "restored"
    assert record_for([e("a", OUTAGE_STILL, "ABC News", 3), e("b", OUTAGE_RESTORED, "The Guardian", 6)])["restoration_status"] == "restored"


def test_the_undated_fallback_uses_the_same_per_report_state():
    cands = [ed.detect_candidate(e("a", "Power restored to some customers in Adelaide but thousands without power", "ABC News"))]
    assert ed._restoration_status([dataclass_replace_unpublished(c) for c in cands]) == "ongoing"


def dataclass_replace_unpublished(c):
    import dataclasses
    return dataclasses.replace(c, published=None)


def test_a_reopened_incident_with_no_still_marker_is_ongoing_again():
    """Codex P2: 'still' -> 'restored' -> 'without power again': the latest stated report has no 'still' word but is active."""
    events = [e("a", "Power outage still affecting 20,000 Telstra customers in Adelaide", "ABC News", 0),
              e("b", "Telstra power outage restored for 20,000 customers in Adelaide", "ABC News", 3),
              e("c", "Telstra power outage leaves 20,000 customers in Adelaide without power again", "ABC News", 6)]
    assert len(groups(events)) == 1
    assert record_for(events)["restoration_status"] == "ongoing"


def test_a_later_clean_restoration_still_closes_an_earlier_active_report():
    events = [e("a", "Telstra power outage leaves 20,000 customers in Adelaide without power", "ABC News", 0),
              e("b", "Telstra power outage restored for 20,000 customers in Adelaide", "ABC News", 4)]
    assert record_for(events)["restoration_status"] == "restored"


def _pub(i, title, source, collected_h, published_h):
    ev = e(i, title, source, collected_h)
    ev["published_at"] = (T0 + timedelta(hours=published_h)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ev


def test_report_chronology_follows_publication_time_not_collection_time():
    """Codex P2: an older restoration article collected AFTER a newer ongoing report must not make the incident 'restored'."""
    events = [_pub("a", "Telstra power outage still affecting 20,000 customers in Adelaide", "ABC News", collected_h=3.1, published_h=3.0),
              _pub("b", "Telstra power outage restored for 20,000 customers in Adelaide", "ABC News", collected_h=3.2, published_h=0.0)]
    assert len(groups(events)) == 1
    assert record_for(events)["restoration_status"] == "ongoing"


def test_a_missing_or_implausible_published_at_falls_back_to_collection_time():
    ev = e("a", "Telstra power outage still affecting 20,000 customers in Adelaide", "ABC News", 3)
    c = ed.detect_candidate(ev)
    assert c.published == ed.we._parse_ts(ev["collected_at"])
    ev["published_at"] = (T0 + timedelta(hours=40)).strftime("%Y-%m-%dT%H:%M:%SZ")           # later than collection: ignored
    assert ed.detect_candidate(ev).published == c.published
    ev["published_at"] = "not a date"
    assert ed.detect_candidate(ev).published == c.published


def test_load_events_carries_published_at():
    from intelligence import brief_evidence as be
    rows = [{"event_id": "x", "raw_title": "T", "raw_summary": "", "geography": "AU", "collected_at": "2026-11-22T06:10:00Z",
             "published_at": "2026-11-22T03:00:00Z", "canonical_url": "https://x", "intelligence_source_registry": {"source_name": "ABC News"}}]
    out = be.load_events(lambda *a, **k: rows, hours=24)
    assert out[0]["published_at"] == "2026-11-22T03:00:00Z"


# ── Forecast and hedged restoration must not override explicit ongoing evidence (release review, High) ───────────────────────

ONGOING_T = "Telstra power outage still affecting 20,000 customers in Adelaide"


def test_a_forecast_restoration_does_not_override_an_explicit_ongoing_report():
    for later in ("Telstra power outage in Adelaide will be restored by 5pm for 20,000 customers",
                  "Telstra power outage in Adelaide expected to be restored by evening for 20,000 customers",
                  "Adelaide power outage: restoration expected overnight for 20,000 customers"):
        events = [e("a", ONGOING_T, "ABC News", 0), e("b", later, "ABC News", 3)]
        assert len(groups(events)) == 1, later
        assert record_for(events)["restoration_status"] == "ongoing", later


def test_a_hedged_restoration_does_not_override_an_explicit_ongoing_report():
    for later in ("Telstra power outage in Adelaide reportedly restored for 20,000 customers",
                  "Telstra power outage in Adelaide believed to be restored for 20,000 customers, company yet to confirm",
                  "Telstra says power outage restored for 20,000 Adelaide customers, unconfirmed"):
        events = [e("a", ONGOING_T, "ABC News", 0), e("b", later, "ABC News", 3)]
        assert len(groups(events)) == 1, later
        assert record_for(events)["restoration_status"] == "ongoing", later


def test_an_affirmative_restoration_still_closes_the_incident():
    events = [e("a", ONGOING_T, "ABC News", 0), e("b", "Telstra power outage restored for 20,000 customers in Adelaide", "ABC News", 3)]
    assert record_for(events)["restoration_status"] == "restored"


def test_provenance_keeps_both_timestamps_and_says_which_one_informed_chronology():
    from intelligence import brief_evidence as be
    ev = _pub("a", "Telstra power outage still affecting 20,000 customers in Adelaide", "ABC News", collected_h=3.1, published_h=3.0)
    es = be.build_evidence([ev], now=NOW, window_hours=200)
    r = es.incidents[0].reports[0]
    assert r["collected_at"] == ev["collected_at"] and r["published_at"] and r["published_at"] != r["collected_at"]


def test_a_past_restoration_after_before_is_not_a_forecast():
    """Codex P2: 'affected 20,000 customers before power restored' describes completed restoration."""
    events = [e("a", "Telstra power outage affected 20,000 customers in Adelaide before power restored", "ABC News", 3)]
    assert record_for(events)["restoration_status"] != "ongoing"


def test_an_operator_attributed_restoration_is_affirmative():
    """Codex P2: 'according to Telstra' is attribution, not a hedge; it closes an earlier ongoing report."""
    events = [e("a", ONGOING_T, "ABC News", 0),
              e("b", "Telstra power outage restored for 20,000 customers in Adelaide, according to Telstra", "ABC News", 3)]
    assert len(groups(events)) == 1
    assert record_for(events)["restoration_status"] == "restored"


def test_negated_or_in_progress_restoration_is_not_restored():
    """Review HIGH: 'power not restored', 'being restored', 'partially back online' must not read as restored."""
    for t in ("Optus outage: power not restored for 5,000 homes",
              "Telstra outage: services have not been restored for 20,000 customers",
              "Telstra outage: services yet to come back online for 20,000 customers",
              "Ausgrid outage: power is being restored to 8,000 homes",
              "Telstra outage: services partially back online for 20,000 customers",
              "Optus outage: restoration unlikely before tomorrow for 5,000 homes"):
        assert record_for([e("a", t, "ABC News", 3)])["restoration_status"] != "restored", t


def test_affirmative_restoration_phrasings_still_restore():
    for t in ("Ausgrid outage: power has been restored to 8,000 homes", "Telstra outage: services restored for 20,000 customers"):
        assert record_for([e("a", t, "ABC News", 3)])["restoration_status"] == "restored", t
