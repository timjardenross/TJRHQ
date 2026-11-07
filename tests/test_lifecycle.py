"""
Tests for the simplified opportunity lifecycle (scripts/self_improvement/lifecycle.py)
and how the store and dashboard use it.

Four stages the Captain sees (To decide / In progress / Done / Closed) plus a
hidden "researching"; the original ten states survive as `stage_detail` because
dedup/reconsideration, the observation window and outcome memory depend on them.
Nothing already on disk is rewritten: old log lines are read as (stage, detail).
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tests.si_dashboard_helpers import (
    si_test_client,  # SEC-01 G3: authenticated test client
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))

import lifecycle
from opportunity_store import OpportunityStore

FINE_TO_STAGE = {
    "discovered": "researching", "investigating": "researching",
    "proposed": "to_decide",
    "approved": "in_progress", "implementing": "in_progress", "verifying": "in_progress",
    "learned": "done",
    "watching": "closed", "rejected": "closed", "resolved_before_research": "closed",
}


class TestVocabulary(unittest.TestCase):
    def test_every_fine_state_maps_to_exactly_one_stage(self):
        self.assertEqual(lifecycle.STAGE_OF, FINE_TO_STAGE)
        self.assertEqual(set(lifecycle.STAGE_OF), set(lifecycle.FINE_STATES))

    def test_four_visible_stages_plus_hidden_researching(self):
        self.assertEqual(lifecycle.VISIBLE_STAGES, ("to_decide", "in_progress", "done", "closed"))
        self.assertEqual(set(lifecycle.STAGES), {"researching", *lifecycle.VISIBLE_STAGES})

    def test_split_fine_state(self):
        for fine, stage in FINE_TO_STAGE.items():
            self.assertEqual(lifecycle.split(fine), (stage, fine))

    def test_split_stage_with_matching_detail(self):
        self.assertEqual(lifecycle.split("in_progress", "verifying"), ("in_progress", "verifying"))

    def test_split_stage_alone_uses_a_default_detail(self):
        for stage, detail in lifecycle.DEFAULT_DETAIL.items():
            self.assertEqual(lifecycle.split(stage), (stage, detail))

    def test_split_stage_with_mismatched_detail_ignores_the_detail(self):
        self.assertEqual(lifecycle.split("closed", "proposed"), ("closed", "rejected"))

    def test_fine_value_beats_a_stale_detail(self):
        # an update to "verifying" must not keep the previous record's "proposed"
        self.assertEqual(lifecycle.split("verifying", "proposed"), ("in_progress", "verifying"))

    def test_unknown_or_missing_is_treated_as_not_yet_surfaced(self):
        for bad in (None, "", "bogus", 7):
            self.assertEqual(lifecycle.split(bad), ("researching", "discovered"))

    def test_detail_and_stage_of_record_work_on_raw_and_normalised(self):
        raw = {"lifecycle_state": "watching"}
        norm = lifecycle.normalise_record(raw)
        for rec in (raw, norm):
            self.assertEqual(lifecycle.detail_of(rec), "watching")
            self.assertEqual(lifecycle.stage_of(rec), "closed")
        self.assertEqual(raw, {"lifecycle_state": "watching"})  # input untouched
        self.assertEqual(lifecycle.normalise_record(norm), norm)  # idempotent

    def test_matches_accepts_either_vocabulary(self):
        rec = {"lifecycle_state": "in_progress", "stage_detail": "verifying"}
        self.assertTrue(lifecycle.matches(rec, {"in_progress"}))
        self.assertTrue(lifecycle.matches(rec, {"verifying", "x"}))
        self.assertFalse(lifecycle.matches(rec, {"proposed", "to_decide"}))


class TestStoreCompatibility(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = OpportunityStore(self.tmp)
        self.log = self.tmp / "review" / "opportunities.jsonl"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _lines(self):
        return [json.loads(line) for line in self.log.read_text().splitlines() if line.strip()]

    def test_new_opportunity_starts_researching(self):
        opp = self.store.create_new(title="t", change_class="reliability", discovery_source="internal")
        self.assertEqual((opp.lifecycle_state, opp.stage_detail), ("researching", "discovered"))
        self.assertEqual(self._lines()[0]["stage_detail"], "discovered")

    def test_caller_can_still_pass_a_fine_state(self):
        opp = self.store.create_new(title="t", change_class="reliability", discovery_source="internal",
                                    lifecycle_state="resolved_before_research")
        self.assertEqual((opp.lifecycle_state, opp.stage_detail), ("closed", "resolved_before_research"))

    def test_old_log_lines_are_read_as_stage_and_detail_without_rewriting_them(self):
        self.log.parent.mkdir(parents=True, exist_ok=True)
        old = [
            {"opportunity_id": "EVO-0001", "title": "a", "lifecycle_state": "proposed"},
            {"opportunity_id": "EVO-0002", "title": "b", "lifecycle_state": "verifying"},
            {"opportunity_id": "EVO-0003", "title": "c", "lifecycle_state": "watching"},
        ]
        original = "".join(json.dumps(r) + "\n" for r in old)
        self.log.write_text(original)

        current = {r["opportunity_id"]: r for r in self.store.all_current()}
        self.assertEqual((current["EVO-0001"]["lifecycle_state"], current["EVO-0001"]["stage_detail"]), ("to_decide", "proposed"))
        self.assertEqual((current["EVO-0002"]["lifecycle_state"], current["EVO-0002"]["stage_detail"]), ("in_progress", "verifying"))
        self.assertEqual((current["EVO-0003"]["lifecycle_state"], current["EVO-0003"]["stage_detail"]), ("closed", "watching"))
        # the raw audit trail is untouched, and reading never writes
        self.assertEqual(self.log.read_text(), original)
        self.assertEqual(self.store.all_records()[1]["lifecycle_state"], "verifying")

    def test_update_with_a_fine_state_stores_stage_and_detail_and_keeps_history(self):
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text(json.dumps({"opportunity_id": "EVO-0001", "title": "a",
                                        "change_class": "reliability", "discovery_source": "internal",
                                        "lifecycle_state": "proposed"}) + "\n")
        updated = self.store.update("EVO-0001", lifecycle_state="verifying")
        self.assertEqual((updated.lifecycle_state, updated.stage_detail), ("in_progress", "verifying"))

        lines = self._lines()
        self.assertEqual(len(lines), 2)  # appended, not rewritten
        self.assertEqual(lines[0]["lifecycle_state"], "proposed")  # old line still old-format
        self.assertEqual((lines[1]["lifecycle_state"], lines[1]["stage_detail"]), ("in_progress", "verifying"))

    def test_update_does_not_inherit_the_previous_states_detail(self):
        opp = self.store.create_new(title="t", change_class="reliability", discovery_source="internal",
                                    lifecycle_state="proposed")
        self.assertEqual(opp.stage_detail, "proposed")
        after = self.store.update(opp.opportunity_id, lifecycle_state="rejected", rejection_reason="no")
        self.assertEqual((after.lifecycle_state, after.stage_detail), ("closed", "rejected"))

    def test_update_that_is_not_a_state_change_keeps_the_detail(self):
        opp = self.store.create_new(title="t", change_class="reliability", discovery_source="internal",
                                    lifecycle_state="verifying")
        after = self.store.update(opp.opportunity_id, summary="more words")
        self.assertEqual((after.lifecycle_state, after.stage_detail), ("in_progress", "verifying"))

    def test_near_duplicate_exclusion_still_uses_the_fine_state(self):
        a = self.store.create_new(title="Rotate the call log weekly", change_class="reliability",
                                  discovery_source="internal", lifecycle_state="learned")
        found = self.store.find_near_duplicate("Rotate the call log weekly", "internal", "reliability")
        self.assertIsNone(found, "learned is excluded by default")
        found = self.store.find_near_duplicate("Rotate the call log weekly", "internal", "reliability",
                                               exclude_states=())
        self.assertEqual(found["opportunity_id"], a.opportunity_id)


class TestDashboardUsesStages(unittest.TestCase):
    def setUp(self):
        try:
            import flask  # noqa: F401
        except ImportError:
            self.skipTest("Flask not installed in this environment")
        import dashboard
        self.dashboard = dashboard
        self.tmp = Path(tempfile.mkdtemp())
        self._original = dashboard.opportunity_store
        dashboard.opportunity_store = OpportunityStore(self.tmp)
        self.client = si_test_client(dashboard)
        self.store = dashboard.opportunity_store

    def tearDown(self):
        self.dashboard.opportunity_store = self._original
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self, title, state):
        return self.store.create_new(title=title, change_class="capability", discovery_source="external",
                                     lifecycle_state=state)

    def test_state_filter_accepts_fine_names_and_stage_names(self):
        a = self._make("proposed one", "proposed")
        self._make("closed one", "rejected")
        for query in ("proposed", "to_decide"):
            body = self.client.get(f"/api/opportunities?state={query}").get_json()
            self.assertEqual([o["opportunity_id"] for o in body["opportunities"]], [a.opportunity_id], query)

    def test_api_returns_stage_in_lifecycle_state_and_fine_state_in_stage_detail(self):
        a = self._make("x", "verifying")
        body = self.client.get(f"/api/opportunity/{a.opportunity_id}").get_json()
        self.assertEqual((body["lifecycle_state"], body["stage_detail"]), ("in_progress", "verifying"))

    def test_reject_closes_the_opportunity(self):
        a = self._make("x", "proposed")
        res = self.client.post("/api/opportunity/decide", json={
            "opportunity_id": a.opportunity_id, "decision_type": "reject", "reasoning": "no fit"})
        self.assertEqual(res.status_code, 200)
        now = self.store.get(a.opportunity_id)
        self.assertEqual((now["lifecycle_state"], now["stage_detail"]), ("closed", "rejected"))
        self.assertEqual(now["rejection_reason"], "no fit")

    def test_keep_watching_parks_it_in_closed_with_a_watch_reason(self):
        a = self._make("x", "investigating")
        self.client.post("/api/opportunity/decide", json={
            "opportunity_id": a.opportunity_id, "decision_type": "keep_watching", "reasoning": "premature"})
        now = self.store.get(a.opportunity_id)
        self.assertEqual((now["lifecycle_state"], now["stage_detail"]), ("closed", "watching"))
        self.assertEqual(now["watch_reason"], "premature")

    def test_parked_item_can_be_moved_back_to_to_decide(self):
        a = self._make("x", "watching")
        self.client.post("/api/opportunity/decide", json={
            "opportunity_id": a.opportunity_id, "decision_type": "turn_into_improvement"})
        now = self.store.get(a.opportunity_id)
        self.assertEqual((now["lifecycle_state"], now["stage_detail"]), ("to_decide", "proposed"))

    def test_mark_implemented_is_judged_on_the_fine_state(self):
        # approved/implementing may be marked implemented (when a contract exists)...
        ok = self._make("ok", "implementing")
        self.store.update(ok.opportunity_id, outcome_contract={"expected_benefit": "x"})
        res = self.client.post("/api/opportunity/decide", json={
            "opportunity_id": ok.opportunity_id, "decision_type": "mark_implemented"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.store.get(ok.opportunity_id)["stage_detail"], "verifying")
        # ...a merely proposed one may not, even though both are "not closed"
        no = self._make("no", "proposed")
        res = self.client.post("/api/opportunity/decide", json={
            "opportunity_id": no.opportunity_id, "decision_type": "mark_implemented"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("currently 'proposed'", res.get_json()["error"])

    def test_pending_decisions_counts_to_decide_only(self):
        self._make("a", "proposed")
        self._make("b", "proposed")
        self._make("c", "investigating")
        self._make("d", "rejected")
        body = self.client.get("/api/evolution-summary").get_json()
        self.assertEqual(body["pending_decisions_count"], 2)


if __name__ == "__main__":
    unittest.main()
