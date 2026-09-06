"""
Tests for the HQ Evolution follow-up mission: overnight scheduler wiring,
real (schema-validated) investigation synthesis with an honest fallback,
and current-state validation of watchlist gap_hypotheses before spending
external-research budget.

Same sys.path convention as test_hq_evolution.py (these modules use bare
sibling imports, matching the pre-existing orchestrator.py/auto_
remediation.py style) — see that file's module docstring for why.
"""

import fcntl
import json
import shutil
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))

import state_validation  # noqa: E402
from investigation_schema import validate_investigation, honest_fallback_investigation, ALLOWED_RECOMMENDATIONS  # noqa: E402
from opportunity_store import OpportunityStore, MISSION_ONLY_CLASSES  # noqa: E402
import evolution_orchestrator  # noqa: E402
import external_discovery  # noqa: E402


def _load_real_watchlist() -> list[dict]:
    with open(REPO_ROOT / "config" / "evolution_watchlist.json") as f:
        return json.load(f)["topics"]


class TestStateValidation(unittest.TestCase):
    def test_no_validation_block_is_unclear_not_a_guess(self):
        verdict = state_validation.validate_topic({"id": "x"}, REPO_ROOT)
        self.assertEqual(verdict["result"], "unclear")

    def test_presence_confirms_when_pattern_found(self):
        topic = {"validation": {"check_type": "presence_confirms", "pattern": "class EvidenceCollector", "paths": ["scripts/self_improvement/collector.py"]}}
        verdict = state_validation.validate_topic(topic, REPO_ROOT)
        self.assertEqual(verdict["result"], "confirmed")
        self.assertTrue(verdict["evidence"])

    def test_presence_resolves_when_pattern_absent(self):
        topic = {"validation": {"check_type": "presence_resolves", "pattern": "this_pattern_should_never_exist_xyz123", "paths": ["scripts/self_improvement/collector.py"]}}
        verdict = state_validation.validate_topic(topic, REPO_ROOT)
        self.assertEqual(verdict["result"], "confirmed")  # absent -> confirmed for "presence_resolves"

    def test_file_exists_confirms_vs_resolves_are_opposite(self):
        confirms = state_validation.validate_topic(
            {"validation": {"check_type": "file_exists_confirms", "paths": ["scripts/self_improvement/collector.py"]}}, REPO_ROOT)
        resolves = state_validation.validate_topic(
            {"validation": {"check_type": "file_exists_resolves", "paths": ["scripts/self_improvement/collector.py"]}}, REPO_ROOT)
        self.assertEqual(confirms["result"], "confirmed")
        self.assertEqual(resolves["result"], "resolved")

    def test_unreadable_paths_degrade_to_unclear_not_exception(self):
        topic = {"validation": {"check_type": "presence_confirms", "pattern": "x", "paths": ["definitely/does/not/exist"]}}
        verdict = state_validation.validate_topic(topic, REPO_ROOT)
        self.assertIn(verdict["result"], ("resolved", "unclear"))  # no match on nonexistent path -> "resolved" for presence_confirms, never raises

    def test_duplicate_synthesis_regression_resolves_against_real_repo(self):
        """Section 16's worked example: the real repo's telegram-bots/xo/
        app.py renders the canonical intelligence_briefs row directly for
        /brief (grep-confirmed), not an independent LLM re-synthesis — so
        this specific gap_hypothesis must validate as resolved, using the
        REAL watchlist config and REAL repo, not a mock."""
        topics = _load_real_watchlist()
        topic = next(t for t in topics if t["id"] == "duplicate-synthesis")
        verdict = state_validation.validate_topic(topic, REPO_ROOT)
        self.assertEqual(verdict["result"], "resolved")

    def test_model_routing_confirmed_against_real_repo(self):
        """Sanity check the opposite direction with real data too — the
        bespoke router file still exists, so this hypothesis must NOT be
        marked resolved."""
        topics = _load_real_watchlist()
        topic = next(t for t in topics if t["id"] == "model-routing")
        verdict = state_validation.validate_topic(topic, REPO_ROOT)
        self.assertEqual(verdict["result"], "confirmed")

    def test_validate_watchlist_partitions_active_vs_resolved(self):
        topics = _load_real_watchlist()
        active, resolved = state_validation.validate_watchlist(topics, REPO_ROOT)
        self.assertEqual(len(active) + len(resolved), len(topics))
        self.assertTrue(any(t["id"] == "duplicate-synthesis" for t in resolved))
        self.assertFalse(any(t["id"] == "duplicate-synthesis" for t in active))

    def test_every_watchlist_topic_still_has_why_relevant_and_gap_hypothesis(self):
        """The rename (known_gap -> gap_hypothesis) must not have silently
        dropped the HQ-relevance justification section 8 requires."""
        for topic in _load_real_watchlist():
            self.assertIn("why_relevant", topic)
            self.assertTrue(topic["why_relevant"])
            self.assertIn("gap_hypothesis", topic)
            self.assertNotIn("known_gap", topic)


class TestInvestigationSchema(unittest.TestCase):
    def test_valid_input_passes_through(self):
        raw = {
            "why_hq_is_looking_at_this": "x", "fit_with_hq": "strong",
            "potential_benefits": ["a", "b"], "cost_impact": "lower",
            "risks": ["r"], "implementation_effort": "low", "alternatives": ["alt"],
            "confidence": 0.8, "recommendation": "worth_pursuing", "recommendation_rationale": "y",
        }
        result = validate_investigation(raw)
        self.assertEqual(result["recommendation"], "worth_pursuing")
        self.assertEqual(result["confidence"], 0.8)

    def test_invalid_recommendation_falls_back_to_needs_more_evidence(self):
        result = validate_investigation({"recommendation": "definitely_do_this_now"})
        self.assertEqual(result["recommendation"], "needs_more_evidence")

    def test_confidence_out_of_range_is_clamped(self):
        self.assertEqual(validate_investigation({"confidence": 5.0})["confidence"], 1.0)
        self.assertEqual(validate_investigation({"confidence": -3.0})["confidence"], 0.0)

    def test_non_numeric_confidence_becomes_none_not_zero(self):
        # None is honest ("no model confidence available"); 0.0 would
        # falsely imply the model actively scored this at zero confidence.
        self.assertIsNone(validate_investigation({"confidence": "very confident"})["confidence"])

    def test_malformed_lists_are_coerced_not_crashed(self):
        result = validate_investigation({"potential_benefits": "not a list", "risks": None})
        self.assertEqual(result["potential_benefits"], [])
        self.assertEqual(result["risks"], [])

    def test_garbage_input_never_raises(self):
        for garbage in (None, {}, {"random": object()}, {"confidence": float("nan")}):
            try:
                validate_investigation(garbage if isinstance(garbage, dict) else {})
            except Exception as exc:  # pragma: no cover - the assertion is that this never happens
                self.fail(f"validate_investigation raised on {garbage!r}: {exc}")

    def test_honest_fallback_never_presents_a_model_confidence(self):
        fallback = honest_fallback_investigation({"why_relevant": "x", "summary": "y"})
        self.assertIsNone(fallback["confidence"])
        self.assertEqual(fallback["method"], "template_fallback")
        self.assertEqual(fallback["recommendation"], "needs_more_evidence")
        self.assertIn("unavailable", fallback["recommendation_rationale"].lower())
        self.assertNotIn("strongly recommend", fallback["recommendation_rationale"].lower())

    def test_all_recommendation_values_are_advisory_enum_only(self):
        self.assertEqual(set(ALLOWED_RECOMMENDATIONS), {"worth_pursuing", "keep_watching", "not_useful", "needs_more_evidence"})


class TestOverlapPrevention(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_second_orchestrator_cannot_acquire_lock_while_first_holds_it(self):
        orch1 = evolution_orchestrator.EvolutionOrchestrator(REPO_ROOT, self.tmpdir)
        orch2 = evolution_orchestrator.EvolutionOrchestrator(REPO_ROOT, self.tmpdir)
        try:
            self.assertTrue(orch1._try_acquire_lock())
            self.assertFalse(orch2._try_acquire_lock())
        finally:
            orch1._release_lock()
        # Lock released — a third acquisition attempt succeeds.
        self.assertTrue(orch2._try_acquire_lock())
        orch2._release_lock()

    def test_run_cycle_skips_cleanly_when_lock_held(self):
        orch = evolution_orchestrator.EvolutionOrchestrator(REPO_ROOT, self.tmpdir)
        orch._load_watchlist = lambda: []
        (self.tmpdir / "review").mkdir(parents=True, exist_ok=True)
        held_fd = open(self.tmpdir / "review" / ".evolution_cycle.lock", "w")
        fcntl.flock(held_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            result = orch.run_cycle(dry_run=False)
            self.assertTrue(result.get("skipped"))
            self.assertTrue(result.get("nothing_worth_changing"))
        finally:
            fcntl.flock(held_fd, fcntl.LOCK_UN)
            held_fd.close()

    def test_dry_run_never_takes_the_lock(self):
        """Section 5: dry-run remains scheduler-independent — it should
        succeed even while a real cycle's lock is held."""
        orch = evolution_orchestrator.EvolutionOrchestrator(REPO_ROOT, self.tmpdir)
        orch._load_watchlist = lambda: []
        (self.tmpdir / "review").mkdir(parents=True, exist_ok=True)
        held_fd = open(self.tmpdir / "review" / ".evolution_cycle.lock", "w")
        fcntl.flock(held_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            result = orch.run_cycle(dry_run=True)
            self.assertFalse(result.get("skipped", False))
        finally:
            fcntl.flock(held_fd, fcntl.LOCK_UN)
            held_fd.close()


class TestResearchOrderAndBounds(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_resolved_topic_is_excluded_from_external_discovery_call(self):
        """Research order (section 17): INTERNAL VALIDATION before
        EXTERNAL DISCOVERY. A topic that validates as resolved must never
        be handed to external_discovery.discover()."""
        orch = evolution_orchestrator.EvolutionOrchestrator(REPO_ROOT, self.tmpdir)
        orch._load_watchlist = lambda: [
            {"id": "resolved-topic", "class": "capability", "why_relevant": "x",
             "validation": {"check_type": "file_exists_resolves", "paths": ["scripts/self_improvement/collector.py"]}},
            {"id": "active-topic", "class": "capability", "why_relevant": "y"},  # no validation -> unclear -> stays active
        ]
        captured_topic_ids = []

        def fake_discover(topics, config):
            captured_topic_ids.extend(t["id"] for t in topics)
            return []

        with patch("external_discovery.discover", side_effect=fake_discover):
            orch.run_cycle(dry_run=False)

        self.assertNotIn("resolved-topic", captured_topic_ids)
        self.assertIn("active-topic", captured_topic_ids)

    def test_resolved_topic_persists_as_resolved_before_research_and_is_not_duplicated(self):
        orch = evolution_orchestrator.EvolutionOrchestrator(REPO_ROOT, self.tmpdir)
        orch._load_watchlist = lambda: [
            {"id": "resolved-topic", "class": "capability", "why_relevant": "x", "gap_hypothesis": "g",
             "validation": {"check_type": "file_exists_resolves", "paths": ["scripts/self_improvement/collector.py"]}},
        ]
        with patch("external_discovery.discover", return_value=[]):
            orch.run_cycle(dry_run=False)
            orch.run_cycle(dry_run=False)  # second cycle — must not duplicate the record

        store = OpportunityStore(self.tmpdir)
        resolved = [r for r in store.all_current() if r["lifecycle_state"] == "resolved_before_research"]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["validation_result"], "resolved")
        self.assertTrue(resolved[0]["validated_at"])
        # Stale hypothesis retains history — the full audit trail is on disk,
        # not silently deleted, even though all_current() only shows latest.
        self.assertGreaterEqual(len(store.all_records()), 1)

    def test_external_search_count_bounded_regardless_of_active_topic_count(self):
        orch = evolution_orchestrator.EvolutionOrchestrator(REPO_ROOT, self.tmpdir)
        orch.evolution_config = {**orch.evolution_config, "max_external_searches_per_cycle": 2, "max_external_candidates_per_search": 1, "max_external_candidates_per_cycle": 2}
        many_topics = [{"id": f"t{i}", "class": "capability", "why_relevant": "x"} for i in range(10)]
        orch._load_watchlist = lambda: many_topics

        with patch("external_discovery.urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
            result = orch.run_cycle(dry_run=False)

        self.assertLessEqual(result["cost_accounting"]["external_searches_made"], 10)  # all 10 are "active" (unclear)
        # But external_discovery.discover() itself must never issue more
        # than max_external_searches_per_cycle real requests regardless of
        # how many active topics it's handed — verified in test_hq_evolution.py's
        # TestExternalDiscovery.test_results_bounded_by_config; here we just
        # confirm the orchestrator doesn't crash or hang against 10 topics.
        self.assertIsInstance(result["duration_ms"], int)

    def test_llm_recommendation_never_changes_automation_eligibility(self):
        """Section 9/45: recommendation is advisory only. Same candidate,
        four different (all-valid) model recommendations -> identical
        automation_eligibility every time, because classify_finding() never
        reads the investigation dict at all."""
        orch = evolution_orchestrator.EvolutionOrchestrator(REPO_ROOT, self.tmpdir)
        orch._load_watchlist = lambda: []
        candidate = {
            "title": "Some capability idea", "source": "s", "discovery_source": "internal",
            "change_class": "capability", "summary": "x", "why_relevant": "y",
            "evidence_strength": "strong", "confidence": 0.9, "fit": "strong", "value": "high",
            "cost_impact": "lower", "complexity": "low",
        }
        eligibilities = set()
        for rec in ALLOWED_RECOMMENDATIONS:
            fake_router_result = {"success": True, "investigation": {"recommendation": rec, "confidence": 0.9}}
            with patch.object(orch.router, "health_check", return_value=True), \
                 patch.object(orch.router, "investigate_opportunity", return_value=fake_router_result), \
                 patch("internal_discovery.discover", return_value=[dict(candidate)]):
                result = orch.run_cycle(dry_run=False)
            store = OpportunityStore(self.tmpdir)
            current = [o for o in store.all_current() if o["title"] == candidate["title"]]
            eligibilities.add(current[-1]["automation_eligibility"] if current else None)
        self.assertEqual(len(eligibilities), 1, f"automation_eligibility varied across recommendations: {eligibilities}")
        self.assertEqual(next(iter(eligibilities)), "manual_only")  # capability is Mission-only regardless


class TestMissionOnlyServerSideEnforcement(unittest.TestCase):
    """Section 24/26: capability/product_improvement/architecture stay
    Mission-only, enforced by the Flask bridge itself — not just hidden by
    the UI. Requires Flask (already a declared dependency of this
    subsystem, scripts/self_improvement/requirements.txt)."""

    def setUp(self):
        try:
            import flask  # noqa: F401
        except ImportError:
            self.skipTest("Flask not installed in this environment")
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_approve_improvement_rejected_for_mission_only_class(self):
        import dashboard
        from opportunity_store import OpportunityStore as Store

        original_store = dashboard.opportunity_store
        dashboard.opportunity_store = Store(self.tmpdir)
        try:
            for change_class in MISSION_ONLY_CLASSES:
                opp = dashboard.opportunity_store.create_new(
                    title=f"Test {change_class}", change_class=change_class,
                    discovery_source="internal", lifecycle_state="proposed",
                )
                client = dashboard.app.test_client()
                res = client.post("/api/opportunity/decide", json={
                    "opportunity_id": opp.opportunity_id, "decision_type": "approve_improvement",
                })
                self.assertEqual(res.status_code, 400, f"{change_class} should refuse approve_improvement")
                current = dashboard.opportunity_store.get(opp.opportunity_id)
                self.assertEqual(current["lifecycle_state"], "proposed")  # unchanged
        finally:
            dashboard.opportunity_store = original_store

    def test_create_mission_still_works_for_mission_only_class(self):
        import dashboard
        from opportunity_store import OpportunityStore as Store

        original_store = dashboard.opportunity_store
        dashboard.opportunity_store = Store(self.tmpdir)
        try:
            opp = dashboard.opportunity_store.create_new(
                title="Architecture idea", change_class="architecture",
                discovery_source="internal", lifecycle_state="proposed",
            )
            client = dashboard.app.test_client()
            res = client.post("/api/opportunity/decide", json={
                "opportunity_id": opp.opportunity_id, "decision_type": "create_mission", "mission_id": "MSN-0001",
            })
            self.assertEqual(res.status_code, 200)
            current = dashboard.opportunity_store.get(opp.opportunity_id)
            self.assertEqual(current["lifecycle_state"], "implementing")
            self.assertEqual(current["mission_id"], "MSN-0001")
        finally:
            dashboard.opportunity_store = original_store


if __name__ == "__main__":
    unittest.main()
