"""Offline Gate 2 tests for intelligence/weekly_evidence.py (Captain's review matrix)."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

import intelligence.weekly_evidence as we

NOW = datetime(2026, 11, 23, tzinfo=timezone.utc)


def ev(i, title, source, hours_ago=6, summary="", geo=None, legacy=None):
    return {"id": i, "title": title, "source": source, "summary": summary, "geography": geo,
            "collected_at": (NOW - timedelta(hours=hours_ago)).isoformat(), "legacy": legacy or {}}


# ── 1. High-impact single events ──────────────────────────────────────────────
class TestSingleEventsSurvive:
    def test_lone_primary_advisory_is_incident_watch_and_not_dropped(self):
        incs = we.correlate_incidents(
            [ev("a", "CISA Adds Four Known Exploited Vulnerabilities to Catalog", "CISA Alerts")], now=NOW)
        assert len(incs) == 1
        watch = we.incident_watch(incs)
        assert [w.headline.event_id for w in watch] == ["a"]
        assert watch[0].headline.priority == "ESCALATE"

    def test_single_event_does_not_form_a_theme(self):
        incs = we.correlate_incidents([ev("a", "Known exploited vulnerability added", "CISA Alerts")], now=NOW)
        assert we.cluster_themes(incs)["statement"] == "no thematic cluster identified"
        assert we.incident_watch(incs)             # ...but it is still surfaced

    def test_low_materiality_event_is_not_incident_watch(self):
        incs = we.correlate_incidents(
            [ev("e", "How the Victorian election will shape the suburbs", "ABC News",
                legacy={"relevance": 1.0, "risk": "HIGH"})], now=NOW)
        assert we.incident_watch(incs) == []
        assert incs[0].headline.materiality_level == "low"


# ── 2. Axes are independent of the legacy fields ──────────────────────────────
class TestSourceKinds:
    def test_aggregator_about_a_regulator_is_not_primary(self):
        assert we.source_kind("Google News - APRA/ASIC Operational Resilience") == we.AGGREGATOR
        assert we.source_kind("APRA Media Releases") == we.PRIMARY

    def test_registry_and_aggregator_never_graded_as_primary(self):
        assert we.source_kind("ClinicalTrials.gov") == we.REGISTRY
        a = we.correlate_incidents([ev("x", "APRA calls outage a near miss", "Google News - APRA/ASIC Operational Resilience")], now=NOW)[0].headline
        assert a.confidence_level == "low" and a.priority != "ESCALATE"


class TestMaterialityRecall:
    def test_generic_cyber_incident_wording_is_material(self):
        for t in ("Coles Group investigating a cyber incident", "Bell Financial says some client data likely accessed",
                  "Hijacked website tool plants card skimmer on Australian brands"):
            assert we.materiality(t, "") > 0, t

    def test_ordinary_politics_stays_low(self):
        assert we.materiality("Labor announces backflip on backpackers", "") == 0.0


class TestAxesIndependence:
    def test_legacy_fields_do_not_change_any_axis(self):
        base = ev("a", "Power out after transmission line failure in South Australia", "ABC News")
        hi = {**base, "legacy": {"rank": 99, "relevance": 1.0, "risk": "HIGH", "disposition": "ESCALATE"}}
        lo = {**base, "legacy": {"rank": 1, "relevance": 0.0, "risk": "LOW", "disposition": "REFERENCE"}}
        a = we.correlate_incidents([hi], now=NOW)[0].headline
        b = we.correlate_incidents([lo], now=NOW)[0].headline
        assert (a.confidence, a.materiality, a.priority) == (b.confidence, b.materiality, b.priority)
        assert a.legacy["risk"] == "HIGH" and b.legacy["risk"] == "LOW"      # kept for comparison only

    def test_mainstream_source_is_not_automatically_high_confidence(self):
        a = we.correlate_incidents([ev("a", "Giants clash over gas reservation policy", "Bloomberg")], now=NOW)[0].headline
        assert a.confidence_level != "high"

    def test_primary_source_outranks_mainstream_on_confidence(self):
        p = we.correlate_incidents([ev("p", "Critical vulnerability patch advisory", "Cisco Security Advisories")], now=NOW)[0].headline
        m = we.correlate_incidents([ev("m", "Critical vulnerability patch advisory", "Bloomberg")], now=NOW)[0].headline
        assert p.confidence > m.confidence

    def test_priority_is_verify_when_material_but_poorly_evidenced(self):
        a = we.correlate_incidents([ev("x", "Ransomware attack causes widespread outage", "Google News - Cyber")], now=NOW)[0].headline
        assert a.materiality_level == "high" and a.priority == "VERIFY"


# ── 3. Syndicated reporting ───────────────────────────────────────────────────
class TestSyndication:
    def test_identical_copies_count_as_one_independent_report(self):
        t = "Power still out after South Australia transmission line failure"
        incs = we.correlate_incidents([ev("a", t, "ABC News"), ev("b", t, "Bloomberg")], now=NOW)
        assert len(incs) == 1 and incs[0].independent_publishers == 1

    def test_separately_worded_reports_are_independent(self):
        incs = we.correlate_incidents([
            ev("a", "South Australia transmission line failure leaves thousands without power", "ABC News"),
            ev("b", "Power still out after South Australia transmission line failure", "Guardian Australia"),
        ], now=NOW)
        assert len(incs) == 1 and incs[0].independent_publishers == 2

    def test_aggregator_is_attributed_to_the_underlying_publisher(self):
        fam = we.publisher_family("Google News - Critical Infrastructure", "GAO warns of gaps - Industrial Cyber")
        assert fam == "industrial cyber"


# ── 4. Misleading headlines ───────────────────────────────────────────────────
class TestMisleadingHeadlines:
    def test_causal_headline_not_in_body_is_flagged_and_penalised(self):
        bad = we.headline_flags("Hospital outage caused by rogue insider", "Officials said the hospital is investigating an outage")
        assert "headline_causal_claim_not_in_body" in bad
        good = we.headline_flags("Hospital outage under investigation", "Officials said the hospital is investigating an outage")
        assert good == []
        assert we.confidence(we.MAINSTREAM, 1, bad) < we.confidence(we.MAINSTREAM, 1, good)

    def test_no_body_is_unverifiable_not_supported(self):
        assert we.headline_flags("Anything", "") == ["headline_unverifiable_no_body"]

    def test_headline_with_unrelated_body_is_flagged(self):
        assert "headline_not_supported_by_body" in we.headline_flags(
            "Regulator fines bank over reporting failures", "Rainfall totals were above average across the region")


# ── 5. Conflicting sources ────────────────────────────────────────────────────
class TestConflicts:
    def test_conflicting_assertions_and_figures_cap_confidence(self):
        incs = we.correlate_incidents([
            ev("a", "Company confirms breach affecting 200,000 customers", "Bloomberg"),
            ev("b", "Company denies breach says 80,000 customers", "ABC News"),
        ], now=NOW)
        assert len(incs) == 1
        assert "conflicting_assertions" in incs[0].flags
        assert any(f.startswith("conflicting_figures") for f in incs[0].flags)
        assert all(a.confidence <= 0.5 for a in incs[0].members)

    def test_agreeing_sources_raise_confidence(self):
        t1 = "South Australia transmission line failure leaves thousands without power"
        t2 = "Power still out after South Australia transmission line failure"
        one = we.correlate_incidents([ev("a", t1, "ABC News")], now=NOW)[0].headline.confidence
        two = we.correlate_incidents([ev("a", t1, "ABC News"), ev("b", t2, "Guardian Australia")], now=NOW)[0].headline.confidence
        assert two > one


# ── 6. Themes need distinct incidents ─────────────────────────────────────────
class TestThemes:
    def test_one_incident_reported_many_times_is_not_a_theme(self):
        t = "Blackout after transmission line fails in South Australia"
        evs = [ev(f"e{i}", t + (" " * i), s) for i, s in enumerate(["ABC News", "Bloomberg", "Guardian Australia", "BBC News"])]
        incs = we.correlate_incidents(evs, now=NOW)
        assert len(incs) == 1
        out = we.cluster_themes(incs)
        assert out["themes"] == [] and out["statement"] == "no thematic cluster identified"
        assert out["below_threshold"][0]["incidents"] == 1

    def test_three_distinct_incidents_three_publishers_two_days_is_a_theme(self):
        evs = [
            ev("a", "Blackout after transmission line fails in South Australia", "ABC News", hours_ago=60),
            ev("b", "Victoria electricity supply at risk of power shortage", "Guardian Australia", hours_ago=30),
            ev("c", "Gas reservation policy dispute raises grid reliability fears", "Bloomberg", hours_ago=6),
        ]
        out = we.cluster_themes(we.correlate_incidents(evs, now=NOW))
        assert [t["theme"] for t in out["themes"]] == ["energy_grid"]
        assert out["themes"][0]["incidents"] == 3

    def test_technology_outage_theme_across_distinct_incidents(self):
        evs = [
            ev("a", "Microsoft says three-month-old bug behind global M365 outage", "iTnews", hours_ago=70),
            ev("b", "Cloudflare dashboard and API service issues outage in EU region", "BBC News", hours_ago=40),
            ev("c", "Authorities investigating four-minute Triple Zero outage in Canberra", "ABC News", hours_ago=8),
        ]
        out = we.cluster_themes(we.correlate_incidents(evs, now=NOW))
        assert [t["theme"] for t in out["themes"]] == ["technology_outages"]

    def test_commentary_sites_do_not_make_a_theme(self):
        evs = [ev(str(i), f"Why outage number {i} should worry leaders", s) for i, s in
               enumerate(["Psychology Today — Work", "Inc. Magazine — Leadership", "Fast Company — Work Life"])]
        out = we.cluster_themes(we.correlate_incidents(evs, now=NOW))
        assert out["themes"] == []

    def test_unrelated_text_never_creates_a_theme(self):
        evs = [ev(str(i), f"Quarterly earnings update number {i}", s) for i, s in enumerate(["ABC News", "Bloomberg", "BBC News"])]
        assert we.cluster_themes(we.correlate_incidents(evs, now=NOW))["statement"] == "no thematic cluster identified"


# ── 7. Health evidence typing ─────────────────────────────────────────────────
class TestHealthEvidence:
    def test_registration_labelled_study_result_is_not_a_result(self):
        r = we.classify_health_record("A Trial of X in Chronic Pain (NCT01234567)", "ClinicalTrials.gov", "study_result")
        assert r["kind"] == we.REGISTRATION and r["demonstrated_result"] is False

    def test_non_evidence_journal_items(self):
        for t in ("[World Report] Coal industry draws criticism", "[Obituary] A Person", "[Editorial] Something"):
            assert we.classify_health_record(t, "The Lancet")["kind"] == we.NON_EVIDENCE

    def test_review_guideline_safety_finding(self):
        assert we.classify_health_record("A systematic review and meta-analysis of sleep", "Medicine")["kind"] == we.REVIEW
        assert we.classify_health_record("Clinical practice guideline for low back pain", "Journal")["kind"] == we.GUIDELINE
        assert we.classify_health_record("FDA Drug Safety Communication on X", "FDA")["kind"] == we.SAFETY
        f = we.classify_health_record("A randomized placebo-controlled trial of X", "Journal")
        assert f["kind"] == we.FINDING and f["demonstrated_result"] and f["design"] == "randomized"

    def test_terminated_trial_is_a_safety_signal_not_a_result(self):
        r = we.classify_health_record("Trial of Y (NCT07654321)", "ClinicalTrials.gov", "safety_alert")
        assert r["kind"] == we.SAFETY and r["demonstrated_result"] is False

    def test_summary_never_counts_registrations_as_results(self):
        recs = [{"title": f"Trial {i} (NCT0000000{i})", "source": "ClinicalTrials.gov", "signal_type": "study_result"} for i in range(5)]
        recs.append({"title": "A randomized trial of Z", "source": "Journal"})
        s = we.summarise_health(recs)
        assert s["by_kind"][we.REGISTRATION] == 5 and s["demonstrated_results"] == 1
        assert s["registrations_counted_as_results"] == 0


# ── 8. Absence typing / source outages ────────────────────────────────────────
class TestAbsence:
    def test_silent_source_against_baseline_is_an_outage(self):
        assert we.observation_state(0, baseline_per_week=20) == we.SOURCE_OUTAGE

    def test_collector_failure_is_an_outage_even_with_rows(self):
        assert we.observation_state(3, collector_failed=True) == we.SOURCE_OUTAGE

    def test_zero_without_baseline_is_not_observed_never_clear(self):
        assert we.observation_state(0) == we.NOT_OBSERVED

    def test_below_minimum_is_insufficient_and_enough_is_observed(self):
        assert we.observation_state(2, minimum=4) == we.INSUFFICIENT
        assert we.observation_state(5, minimum=4) == we.OBSERVED


# ── 9. Narrative assurance ────────────────────────────────────────────────────
EVID = {
    "e1": {"title": "Live: Power still out after SA transmission line downed", "summary": "", "source": "ABC News"},
    "e2": {"title": "Company confirms breach affecting 80,000 customers", "summary": "", "source": "Bloomberg"},
}


class TestNarrativeAssurance:
    def test_supported_claim_passes(self):
        r = we.validate_claims([we.Claim("Power is still out after a South Australia transmission line was downed", ["e1"])], EVID)
        assert r.ok, r.failures

    def test_missing_or_unknown_ids_fail(self):
        assert not we.validate_claims([we.Claim("Power is out", [])], EVID).ok
        assert "unknown evidence id" in we.validate_claims([we.Claim("Power is out", ["zz"])], EVID).failures[0]

    def test_existing_id_does_not_make_an_unrelated_claim_supported(self):
        r = we.validate_claims([we.Claim("Ransomware crippled three hospitals nationwide", ["e1"])], EVID)
        assert not r.ok and "does not support" in r.failures[0]

    def test_wrong_figure_fails(self):
        r = we.validate_claims([we.Claim("Company confirms breach affecting 200,000 customers", ["e2"])], EVID)
        assert any("figure 200,000" in f for f in r.failures)

    def test_unsupported_causal_claim_fails(self):
        r = we.validate_claims([we.Claim("The power out was caused by data centre demand", ["e1"])], EVID)
        assert any("causal claim" in f for f in r.failures)

    def test_causal_claim_with_two_independent_sources_stating_cause_passes(self):
        evid = {"a": {"title": "Outage caused by failed transmission line", "summary": "", "source": "ABC News"},
                "b": {"title": "Failed transmission line blamed for outage", "summary": "", "source": "Guardian Australia"}}
        r = we.validate_claims([we.Claim("Outage caused by failed transmission line", ["a", "b"])], evid)
        assert r.ok, r.failures

    def test_failure_falls_back_to_deterministic_text(self):
        out = we.render_narrative([we.Claim("Ransomware crippled hospitals", ["e1"])], EVID, "FALLBACK COUNTS")
        assert out["mode"] == "deterministic_fallback" and out["text"] == "FALLBACK COUNTS" and out["failures"]

    def test_valid_narrative_is_used(self):
        out = we.render_narrative([we.Claim("Power is still out after a South Australia transmission line was downed", ["e1"])], EVID, "FALLBACK")
        assert out["mode"] == "narrative"

    def test_empty_claims_use_fallback(self):
        assert we.render_narrative([], EVID, "FALLBACK")["mode"] == "deterministic_fallback"


# ── 10. Methodology versioning ────────────────────────────────────────────────
class TestVersioning:
    def test_same_version_comparable(self):
        assert we.comparable(we.METHOD_VERSION, we.METHOD_VERSION)[0]

    def test_documented_break_is_refused_with_reason(self):
        ok, why = we.comparable("legacy/confidence-count", we.METHOD_VERSION)
        assert not ok and "discontinuity" in why

    def test_unknown_version_fails_closed(self):
        assert not we.comparable("mystery", we.METHOD_VERSION)[0]

    def test_outputs_are_stamped_and_legacy_values_preserved(self):
        a = we.correlate_incidents([ev("a", "x ransomware outage", "Bloomberg", legacy={"risk": "HIGH"})], now=NOW)[0].headline
        assert a.method_version == we.METHOD_VERSION and a.legacy == {"risk": "HIGH"}

    def test_classifier_epochs_exist_for_future_discontinuities(self):
        assert we.CLASSIFIER_EPOCHS and we.CLASSIFIER_EPOCHS[0]["epoch"].startswith("classifier-")


# ── 11. Snapshots, retention and forecasts ────────────────────────────────────
def snap(days_ago, mb):
    return {"date": (NOW - timedelta(days=days_ago)).date().isoformat(), "size_mb": mb}


class TestSnapshotsAndForecast:
    def test_roundtrip_stamps_version_and_survives_a_corrupt_line(self):
        with tempfile.TemporaryDirectory() as d:
            st = we.SnapshotStore(os.path.join(d, "s.jsonl"))
            st.append(snap(7, 250)); st.append(snap(0, 256))
            with open(st.path, "a") as f:
                f.write("{not json\n")
            rows = st.load()
            assert [r["size_mb"] for r in rows] == [250, 256]
            assert all(r["method_version"] == we.METHOD_VERSION for r in rows)

    def test_retention_prunes_only_old_rows_atomically(self):
        with tempfile.TemporaryDirectory() as d:
            st = we.SnapshotStore(os.path.join(d, "s.jsonl"), retention_weeks=4)
            for days, mb in ((100, 200), (20, 240), (0, 250)):
                st.append(snap(days, mb))
            assert st.prune(now=NOW) == 1
            assert [r["size_mb"] for r in st.load()] == [240, 250]
            assert not os.path.exists(st.path + ".tmp")

    def test_missing_file_is_empty(self):
        assert we.SnapshotStore("/nonexistent/dir/x.jsonl").load() == []

    def test_forecast_refused_on_thin_history(self):
        out = we.forecast_growth([snap(14, 250), snap(7, 256), snap(0, 262)])
        assert out["available"] is False and "insufficient history" in out["reason"]

    def test_forecast_refused_when_span_too_short(self):
        out = we.forecast_growth([snap(6, 250), snap(4, 251), snap(2, 252), snap(0, 253)])
        assert out["available"] is False

    def test_forecast_available_with_range(self):
        out = we.forecast_growth([snap(21, 250), snap(14, 256), snap(7, 262), snap(0, 268)])
        assert out["available"] and out["mb_per_week"] == 6.0
        assert out["weeks_to_limit"] == round((500 - 268) / 6, 1)
        lo, hi = out["weeks_to_limit_range"]
        assert lo <= out["weeks_to_limit"] <= hi

    def test_cleanup_drop_starts_a_new_segment_and_is_noted(self):
        snaps = [snap(35, 300), snap(28, 200), snap(21, 204), snap(14, 208), snap(7, 212), snap(0, 216)]
        out = we.forecast_growth(snaps)
        assert out["available"] and any("cleanup" in n for n in out["notes"])
        assert out["current_mb"] == 216 and 3.5 < out["mb_per_week"] < 4.5

    def test_flat_or_shrinking_has_no_weeks_to_limit(self):
        out = we.forecast_growth([snap(21, 250), snap(14, 250), snap(7, 250), snap(0, 250)])
        assert out["available"] and out["weeks_to_limit"] is None


# ── 12. Assembly: future-dated data, sampling, capacity ───────────────────────
class TestAssembly:
    def _build(self, events, capacity, universe=None):
        return we.build_weekly_evidence(events=events, universe=universe or {"usable": len(events)},
                                        health_records=[], capacity=capacity, db_snapshots=[], now=NOW)

    def test_future_dated_events_are_excluded_and_counted(self):
        future = {**ev("f", "Ransomware attack", "CISA Alerts"), "collected_at": "2099-01-01T00:00:00Z"}
        out = self._build([ev("a", "Known exploited vulnerability", "CISA Alerts"), future], {"entries": []})
        assert out["excluded_future_events"] == 1 and len(out["incidents"]) == 1

    def test_future_dated_capacity_rows_are_excluded(self):
        cap = {"source": "pulse", "entries": [{"log_date": "2099-01-01"}, {"log_date": "2099-01-01"}]}
        out = self._build([], cap)["capacity"]
        assert out["observations"] == 0 and out["excluded_future"] == 2 and out["state"] == we.NOT_OBSERVED

    def test_small_capacity_sample_is_insufficient(self):
        cap = {"source": "checkin", "entries": [{"log_date": "2026-11-20"}, {"log_date": "2026-11-21"}]}
        assert self._build([], cap)["capacity"]["state"] == we.INSUFFICIENT

    def test_pool_smaller_than_universe_is_declared_a_sample(self):
        out = self._build([ev("a", "x", "Bloomberg")], {"entries": []}, universe={"usable": 2376})
        assert out["universe"]["pool_is_sample"] is True and out["universe"]["usable"] == 2376

    def test_forecast_state_is_carried_and_gated(self):
        assert self._build([], {"entries": []})["database"]["available"] is False

    def test_assembly_carries_method_version(self):
        assert self._build([], {"entries": []})["method_version"] == we.METHOD_VERSION


class TestBriefRenderer:
    def _ev(self, events, cap=None):
        return we.build_weekly_evidence(events=events, universe={"usable": 2330, "au_events": 560},
                                        health_records=[], capacity=cap or {"entries": []}, db_snapshots=[], now=NOW)

    def test_all_ten_required_sections_present(self):
        out = we.render_intelligence_brief(self._ev([ev("a", "CISA adds actively exploited vulnerability", "CISA Alerts")]),
                                           week_label="17-23 Nov 2026")
        for n, name in enumerate(("EXECUTIVE SUMMARY", "PRIORITY DEVELOPMENTS", "OPERATIONAL RESILIENCE", "AI AND GOVERNANCE",
                                  "HEALTH AND NEUROSCIENCE", "CROSS-DOMAIN", "AUSTRALIAN RELEVANCE", "EMERGING RISKS",
                                  "RECOMMENDED ACTIONS", "EVIDENCE CONFIDENCE"), 1):
            assert f"{n}. {name}" in out

    def test_states_pool_is_not_the_full_week_and_nothing_is_sent(self):
        out = we.render_intelligence_brief(self._ev([ev("a", "x", "Bloomberg")]), week_label="w")
        assert "a candidate pool, not the full week" in out and "not sent" in out

    def test_empty_week_does_not_claim_no_issue(self):
        out = we.render_intelligence_brief(self._ev([]), week_label="w")
        assert "not evidence of no issue" in out

    def test_registrations_never_presented_as_results(self):
        out = we.render_intelligence_brief(self._ev([]), week_label="w",
                                           health={"total": 392, "registrations": 320, "other": 72})
        assert "a registration shows a study exists, not what it found" in out
        assert "Demonstrated results counted from registrations: 0" in out

    def test_capacity_not_observed_wording_and_future_rows_disclosed(self):
        out = we.render_intelligence_brief(
            self._ev([], cap={"source": "pulse", "entries": [{"log_date": "2099-01-01"}]}), week_label="w")
        assert "not observed" in out and "1 future-dated record(s) excluded" in out

    def test_no_forecast_stated_without_history(self):
        assert "no forecast — insufficient history" in we.render_intelligence_brief(self._ev([]), week_label="w")

    def test_themes_absent_says_none_not_silence(self):
        assert "none (no thematic cluster identified)" in we.render_intelligence_brief(self._ev([]), week_label="w")

    def test_every_item_attributed_to_a_source(self):
        out = we.render_intelligence_brief(self._ev([ev("a", "Ransomware attack causes outage", "Bloomberg")]), week_label="w")
        assert "as reported by Bloomberg" in out
