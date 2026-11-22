"""Tests for the offline evaluation harness and the priority/escalation rules."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "scripts"))

import eval_weekly_evidence as ev

import intelligence.weekly_evidence as we

NOW = datetime(2026, 11, 23, tzinfo=timezone.utc)


class TestFixtureIntegrity:
    def test_shape_and_vocabulary(self):
        rows = ev.load()
        assert len(rows) == 150 and len({r["id"] for r in rows}) == 150
        assert {r["label_materiality"] for r in rows} <= {"H", "M", "L"}
        assert {r["label_priority"] for r in rows} <= {"E", "W", "V", "R"}
        assert {r["stratum"] for r in rows} == {"A_known", "B_primary", "C_legacyhigh", "D_belowcutoff", "E_rest"}

    def test_set_is_stratified_not_only_legacy_flagged(self):
        rows = ev.load()
        below = [r for r in rows if r["legacy_rank"] < ev.LEGACY_RANK_FLOOR]
        assert len(below) >= 40                      # includes events the legacy sample could not see
        assert sum(1 for r in rows if r["label_materiality"] == "H") >= 15

    def test_fixture_declares_labels_unreviewed(self):
        import json
        meta = json.loads(ev.DEFAULT_FIXTURE.read_text())["_meta"]
        assert "NOT yet reviewed" in meta["status"]


class TestMetrics:
    def test_prf_basic(self):
        m = ev.prf([True, True, False, False], [True, False, True, False])
        assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 1, 1)
        assert m["precision"] == 0.5 and m["recall"] == 0.5

    def test_prf_no_positives_is_none_not_a_crash(self):
        assert ev.prf([False, False], [False, False])["precision"] is None

    def test_grouping_recall_pairwise(self):
        inc = {"a": "i1", "b": "i1", "c": "i2"}
        r = ev.grouping_recall(inc, {"g": ["a", "b", "c"]})
        assert r["g"]["pairs"] == 3 and r["g"]["grouped_pairs"] == 1 and r["g"]["incident_groups_used"] == 2

    def test_evaluation_is_deterministic(self):
        a, b = ev.evaluate(ev.load()), ev.evaluate(ev.load())
        a.pop("_inc_of"), b.pop("_inc_of")
        assert a == b

    def test_proposed_method_beats_every_legacy_predictor_on_f1(self):
        res = ev.evaluate(ev.load())["materiality_high"]
        new = res["proposed method"]["f1"]
        assert all(new > v["f1"] for k, v in res.items() if k != "proposed method")


def e(i, title, source, hours_ago=6):
    return {"id": i, "title": title, "source": source,
            "collected_at": (NOW - timedelta(hours=hours_ago)).isoformat()}


class TestPriorityRules:
    """Escalation policy (Captain's direction, 2026-11-23): a KEV advisory is not automatically critical;
    a single credible report of a severe outage may escalate PROVISIONALLY (marked uncorroborated, with
    follow-up); multiple publishers are not a universal prerequisite."""

    def inc(self, evs):
        return we.correlate_incidents(evs, now=NOW)[0].headline

    # --- advisories: exposure, exploitation, urgency decide -------------------------------------
    def test_kev_without_known_exposure_is_watch_with_an_exposure_note(self):
        a = self.inc([e("a", "CISA adds actively exploited vulnerability in obscure FooBar appliance to catalog", "CISA Alerts")])
        assert a.priority == "WATCH" and a.escalation and "exposure unknown" in a.escalation["note"]

    def test_kev_with_exploitation_and_known_exposure_escalates(self):
        a = self.inc([e("a", "CISA adds actively exploited nginx vulnerability to catalog", "CISA Alerts")])
        assert a.priority == "ESCALATE" and a.escalation["provisional"] is False

    def test_stale_exploited_exposed_advisory_is_not_escalated(self):
        a = self.inc([e("a", "CISA adds actively exploited nginx vulnerability to catalog", "CISA Alerts", hours_ago=100)])
        assert a.priority == "WATCH"

    def test_exposure_without_exploitation_is_not_escalated(self):
        a = self.inc([e("a", "Critical vulnerability in nginx requires patching, no exploitation reported", "CISA Alerts")])
        assert a.priority != "ESCALATE"

    # --- incidents: one credible report can escalate provisionally -------------------------------
    def test_single_mainstream_report_of_severe_outage_escalates_provisionally(self):
        a = self.inc([e("a", "11,000 still without power after storm topples transmission towers", "ABC News")])
        assert a.priority == "ESCALATE"
        assert a.escalation["provisional"] and a.escalation["uncorroborated"]
        assert "verify" in a.escalation["follow_up"]

    def test_corroborated_escalation_is_not_marked_provisional(self):
        evs = [e("a", "South Australia transmission line failure leaves thousands without power", "ABC News"),
               e("b", "Power still out after South Australia transmission line failure", "Guardian Australia")]
        a = self.inc(evs)
        assert a.priority == "ESCALATE" and a.escalation["provisional"] is False

    def test_syndicated_copy_still_counts_as_one_publisher_so_stays_provisional(self):
        t = "South Australia transmission line failure leaves thousands without power"
        a = self.inc([e("a", t, "ABC News"), e("b", t, "Bloomberg")])
        assert a.priority == "ESCALATE" and a.escalation["uncorroborated"]

    def test_stale_severe_incident_is_watch_not_escalate(self):
        a = self.inc([e("a", "11,000 still without power after storm topples transmission towers", "ABC News", hours_ago=100)])
        assert a.priority == "WATCH"

    def test_aggregator_only_severe_incident_is_verify_first(self):
        a = self.inc([e("a", "Ransomware attack causes widespread outage - Some Site", "Google News - Cyber")])
        assert a.priority == "VERIFY"

    def test_high_materiality_but_no_severe_consequence_is_watch_not_escalate(self):
        a = self.inc([e("a", "Major global outage hits a SaaS design tool for hours", "BBC News")])
        assert a.materiality_level == "high" and a.priority == "WATCH" and a.escalation is None

    def test_low_materiality_is_reference_whatever_the_source(self):
        assert self.inc([e("a", "Quarterly results announced", "Bloomberg")]).priority == "REFERENCE"

    # --- grouping v2 ------------------------------------------------------------------------------
    def test_differently_worded_reports_of_one_incident_now_group(self):
        evs = [e("a", "Major blackout hits South Australia as transmission line fails", "ABC News"),
               e("b", "South Australia blackout after transmission line failure leaves thousands without power", "Guardian Australia")]
        assert len(we.correlate_incidents(evs, now=NOW)) == 1

    def test_v1_grouping_still_available_for_comparison(self):
        evs = [e("a", "Major blackout hits South Australia as transmission line fails", "ABC News"),
               e("b", "South Australia blackout after transmission line failure leaves thousands without power", "Guardian Australia")]
        assert len(we.correlate_incidents(evs, now=NOW, grouping="v1")) == 2

    def test_same_entity_same_class_groups_but_different_class_does_not(self):
        same = [e("a", "Coles Group investigating a cyber incident", "iTnews"),
                e("b", "Coles supermarket cyber attack: retailer investigates security breach", "ABC News")]
        diff = [e("c", "Coles Group investigating a cyber incident", "iTnews"),
                e("d", "Coles appeals ACCC decision blocking supermarket", "ABC News")]
        assert len(we.correlate_incidents(same, now=NOW)) == 1
        assert len(we.correlate_incidents(diff, now=NOW)) == 2

    def test_unrelated_outages_do_not_merge(self):
        evs = [e("a", "Microsoft outage hits Outlook and Teams users", "ABC News"),
               e("b", "Triple Zero outage in Canberra under investigation", "ABC News")]
        assert len(we.correlate_incidents(evs, now=NOW)) == 2


class TestAdversarial:
    """Cases designed to fool the vocabulary, the grouping and the escalation rule."""

    def mat(self, t):
        return we.materiality(t, "")

    def test_negation_and_denial_do_not_create_a_critical_incident_from_nothing(self):
        # vocabulary matches 'outage' even in a denial: the headline stays at most medium without scale cues
        assert self.mat("Company says there was no outage") < 0.5

    def test_metaphor_and_sport_headlines_do_not_trigger(self):
        for t in ("Bloomberg's new daily trivia game", "Think Twice", "GTA VI takes over Thanksgiving week",
                  "Black out your calendar: NRL draw released", "Power couple buys a vineyard"):
            assert self.mat(t) == 0.0, t

    def test_keyword_stuffing_is_capped(self):
        assert self.mat("blackout blackout blackout outage outage ransomware ransomware cyberattack") <= 1.0

    def test_ordinary_politics_with_au_words_stays_zero(self):
        assert self.mat("Victorian election debate: Labor and Liberals clash over housing in Melbourne") == 0.0

    def test_au_org_names_alone_do_not_create_materiality(self):
        assert self.mat("Coles appeals ACCC decision blocking Kalgoorlie supermarket") == 0.0

    def test_unsupported_causal_headline_is_flagged_not_trusted(self):
        flags = we.headline_flags("Outage caused by rogue insider", "Officials said an outage occurred")
        assert "headline_causal_claim_not_in_body" in flags

    def test_conflicting_sources_cap_confidence_even_for_a_severe_event(self):
        evs = [e("a", "Company confirms breach affecting 200,000 customers", "Bloomberg"),
               e("b", "Company denies breach says 80,000 customers", "ABC News")]
        inc = we.correlate_incidents(evs, now=NOW)[0]
        assert all(a.confidence <= 0.5 for a in inc.members)

    def test_future_dated_event_cannot_escalate(self):
        future = {**e("a", "11,000 still without power after storm topples transmission towers", "ABC News"),
                  "collected_at": "2099-01-01T00:00:00Z"}
        out = we.build_weekly_evidence(events=[future], universe={"usable": 1}, health_records=[],
                                       capacity={"entries": []}, db_snapshots=[], now=NOW)
        assert out["excluded_future_events"] == 1 and out["incidents"] == []

    def test_source_outage_is_not_an_all_clear(self):
        assert we.observation_state(0, baseline_per_week=300) == we.SOURCE_OUTAGE


class TestShadowRunner:
    def test_renders_from_an_export_and_is_labelled_shadow(self, tmp_path):
        import render_shadow_report as rs
        rows = ev.load()[:30]
        export = {"events": ev.to_events(rows), "universe": {"usable": 2330, "au_events": 560},
                  "health": {"total": 392, "registrations": 320, "other": 72}, "now": "2026-11-23T13:00:00Z"}
        out = rs.render(export, "17-23 Nov 2026")
        assert out.startswith("SHADOW OUTPUT") and "1. EXECUTIVE SUMMARY" in out

    def test_has_no_delivery_network_or_database_path(self):
        src = (Path(__file__).resolve().parents[1] / "scripts" / "render_shadow_report.py").read_text().lower()
        for banned in ("urllib", "requests", "http", "telegram", "smtp", "supabase", "socket", "subprocess"):
            assert banned not in src.replace("shadow output", "").replace("export format", "")

    def test_cli_writes_a_local_file(self, tmp_path):
        import json as j

        import render_shadow_report as rs
        exp = tmp_path / "e.json"
        exp.write_text(j.dumps({"events": [], "universe": {"usable": 0}, "now": "2026-11-23T13:00:00Z"}))
        out = tmp_path / "out.txt"
        assert rs.main([str(exp), "--out", str(out), "--week", "w"]) == 0
        assert out.read_text().startswith("SHADOW OUTPUT")
