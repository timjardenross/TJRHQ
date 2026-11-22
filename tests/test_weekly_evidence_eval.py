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
    def prio(self, evs):
        return we.correlate_incidents(evs, now=NOW)[0].headline.priority

    def test_primary_material_fresh_escalates(self):
        assert self.prio([e("a", "CISA adds actively exploited vulnerability", "CISA Alerts")]) == "ESCALATE"

    def test_stale_primary_is_watch_not_escalate(self):
        assert self.prio([e("a", "CISA adds actively exploited vulnerability", "CISA Alerts", hours_ago=100)]) == "WATCH"

    def test_single_mainstream_report_does_not_escalate(self):
        assert self.prio([e("a", "South Australia transmission line failure leaves thousands without power", "ABC News")]) == "WATCH"

    def test_known_limitation_differently_worded_reports_are_not_grouped(self):
        """Documented limitation (D12): title-token grouping splits paraphrased reports of one
        incident, so two outlets reporting it in different words do NOT corroborate each other."""
        evs = [e("a", "Major blackout hits South Australia as transmission line fails", "ABC News"),
               e("b", "South Australia blackout after transmission line failure leaves thousands without power", "Guardian Australia")]
        assert len(we.correlate_incidents(evs, now=NOW)) == 2

    def test_two_independent_mainstream_reports_escalate(self):
        evs = [e("a", "South Australia transmission line failure leaves thousands without power", "ABC News"),
               e("b", "Power still out after South Australia transmission line failure", "Guardian Australia")]
        assert self.prio(evs) == "ESCALATE"

    def test_syndicated_copy_does_not_count_as_a_second_source(self):
        t = "South Australia transmission line failure leaves thousands without power"
        assert self.prio([e("a", t, "ABC News"), e("b", t, "Bloomberg")]) == "WATCH"

    def test_aggregator_only_material_incident_is_verify_first(self):
        assert self.prio([e("a", "Ransomware attack causes widespread outage - Some Site", "Google News - Cyber")]) == "VERIFY"

    def test_low_materiality_is_reference_whatever_the_source(self):
        assert self.prio([e("a", "Quarterly results announced", "Bloomberg")]) == "REFERENCE"


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
