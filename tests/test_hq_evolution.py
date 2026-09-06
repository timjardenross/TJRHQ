"""
Tests for HQ Evolution (scripts/self_improvement/{opportunity_store,
relevance, internal_discovery, external_discovery, evolution_orchestrator,
migration}.py).

These modules follow the same bare-sibling-import convention as the
pre-existing orchestrator.py/auto_remediation.py/decision_processor.py
(designed to run with their own directory as cwd/sys.path[0], not as a
`scripts.self_improvement.X` package import) — so, unlike
test_self_improvement_system.py, this file puts scripts/self_improvement
itself on sys.path rather than importing through the package.

Uses stdlib unittest plus unittest.mock (already stdlib) — no new
dependencies. Every test that touches a store points OpportunityStore at a
temp directory; none of these tests may write into the committed
data/self-improvement tree.
"""

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

from opportunity_store import OpportunityStore, new_fingerprint, MISSION_ONLY_CLASSES  # noqa: E402
from relevance import RelevanceGate  # noqa: E402
import internal_discovery  # noqa: E402
import external_discovery  # noqa: E402
import migration  # noqa: E402
from policy import PolicyEngine  # noqa: E402

DEFAULT_EVOLUTION_CONFIG = {
    "min_relevance_score_to_investigate": 0.5,
    "min_relevance_score_to_surface": 0.65,
    "dedup_reconsideration_days": 21,
    "max_external_searches_per_cycle": 6,
    "max_external_candidates_per_search": 5,
    "max_external_candidates_per_cycle": 20,
    "external_request_timeout_seconds": 8,
}


def make_candidate(**overrides):
    base = {
        "title": "Adopt widget X",
        "source": "https://example.com/widget-x",
        "discovery_source": "external",
        "change_class": "capability",
        "summary": "Widget X does a thing HQ needs.",
        "why_relevant": "Closes a known gap in HQ's Y subsystem.",
        "evidence_strength": "strong",
        "confidence": 0.8,
        "fit": "strong",
        "value": "high",
        "cost_impact": "lower",
        "complexity": "low",
    }
    base.update(overrides)
    return base


class TempStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.store = OpportunityStore(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestOpportunityStore(TempStoreTestCase):
    def test_create_and_get_roundtrip(self):
        opp = self.store.create_new(title="T", change_class="maintenance", discovery_source="internal")
        fetched = self.store.get(opp.opportunity_id)
        self.assertEqual(fetched["title"], "T")
        self.assertEqual(fetched["lifecycle_state"], "discovered")

    def test_update_appends_new_record_and_folds_to_latest(self):
        opp = self.store.create_new(title="T", change_class="maintenance", discovery_source="internal")
        self.store.update(opp.opportunity_id, lifecycle_state="watching", watch_reason="too new")
        current = self.store.get(opp.opportunity_id)
        self.assertEqual(current["lifecycle_state"], "watching")
        # audit trail preserved — both records exist in the raw log
        self.assertEqual(len(self.store.all_records()), 2)

    def test_ids_are_sequential_and_unique(self):
        ids = [self.store.create_new(title=f"T{i}", change_class="maintenance", discovery_source="internal").opportunity_id
               for i in range(3)]
        self.assertEqual(len(set(ids)), 3)

    def test_fingerprint_is_stable_for_same_inputs(self):
        fp1 = new_fingerprint("Same Title", "src", "internal")
        fp2 = new_fingerprint("  same   title  ", "src", "internal")
        self.assertEqual(fp1, fp2)

    def test_mission_only_classes_match_policy_manual_only(self):
        """The code-level MISSION_ONLY_CLASSES set must agree with which
        change classes config/self_improvement_policy.json actually marks
        manual_only — otherwise the API's Mission-only guard and the
        PolicyEngine's own classification could silently disagree."""
        policy = PolicyEngine(REPO_ROOT / "config" / "self_improvement_policy.json")
        for change_class in MISSION_ONLY_CLASSES:
            rules = policy.category_policy.get(change_class, {})
            self.assertEqual(
                rules.get("automation_eligibility"), "manual_only",
                f"{change_class} is in MISSION_ONLY_CLASSES but policy config doesn't mark it manual_only",
            )


class TestRelevanceGate(TempStoreTestCase):
    def setUp(self):
        super().setUp()
        self.gate = RelevanceGate(DEFAULT_EVOLUTION_CONFIG, self.store)

    def test_high_fit_high_value_strong_evidence_passes_both_thresholds(self):
        verdict = self.gate.evaluate(make_candidate())
        self.assertTrue(verdict.passes_investigate)
        self.assertTrue(verdict.passes_surface)
        self.assertFalse(verdict.is_duplicate)

    def test_weak_candidate_fails_investigate(self):
        verdict = self.gate.evaluate(make_candidate(fit="weak", value="low", evidence_strength="weak", complexity="high"))
        self.assertFalse(verdict.passes_investigate)

    def test_no_why_relevant_never_passes_even_with_high_score_inputs(self):
        """Section 8: never surface on popularity/novelty alone."""
        verdict = self.gate.evaluate(make_candidate(why_relevant=""))
        self.assertFalse(verdict.passes_investigate)
        self.assertFalse(verdict.passes_surface)

    def test_duplicate_of_proposed_opportunity_is_suppressed(self):
        c = make_candidate()
        fp = new_fingerprint(c["title"], c["source"], c["discovery_source"])
        self.store.create_new(title=c["title"], change_class=c["change_class"], discovery_source=c["discovery_source"],
                               lifecycle_state="proposed", fingerprint=fp, relevance_score=0.9)
        verdict = self.gate.evaluate({**c, "fingerprint": fp})
        self.assertTrue(verdict.is_duplicate)
        self.assertFalse(verdict.passes_investigate)

    def test_rejected_opportunity_not_resurfaced_without_better_evidence(self):
        c = make_candidate()
        fp = new_fingerprint(c["title"], c["source"], c["discovery_source"])
        self.store.create_new(title=c["title"], change_class=c["change_class"], discovery_source=c["discovery_source"],
                               lifecycle_state="rejected", fingerprint=fp, relevance_score=0.9)
        verdict = self.gate.evaluate({**c, "fingerprint": fp})
        self.assertTrue(verdict.is_duplicate)

    def test_rejected_opportunity_resurfaced_with_meaningfully_better_evidence(self):
        c = make_candidate()
        fp = new_fingerprint(c["title"], c["source"], c["discovery_source"])
        self.store.create_new(title=c["title"], change_class=c["change_class"], discovery_source=c["discovery_source"],
                               lifecycle_state="rejected", fingerprint=fp, relevance_score=0.2)
        verdict = self.gate.evaluate({**c, "fingerprint": fp})  # scores ~0.8+, well above 0.2 + 0.1
        self.assertFalse(verdict.is_duplicate)

    def test_learned_opportunity_never_resurfaced(self):
        c = make_candidate()
        fp = new_fingerprint(c["title"], c["source"], c["discovery_source"])
        self.store.create_new(title=c["title"], change_class=c["change_class"], discovery_source=c["discovery_source"],
                               lifecycle_state="learned", fingerprint=fp, relevance_score=0.1)
        verdict = self.gate.evaluate({**c, "fingerprint": fp})
        self.assertTrue(verdict.is_duplicate)


class TestPolicyOnEvolutionCategories(unittest.TestCase):
    def setUp(self):
        self.policy = PolicyEngine(REPO_ROOT / "config" / "self_improvement_policy.json")

    def test_capability_never_auto_apply_even_at_high_confidence(self):
        result = self.policy.classify_finding({
            "category": "capability", "confidence": 0.99, "evidence_strength": "conclusive", "severity": "low",
        })
        self.assertEqual(result["automation_eligibility"], "manual_only")

    def test_architecture_never_auto_apply(self):
        result = self.policy.classify_finding({
            "category": "architecture", "confidence": 0.99, "evidence_strength": "conclusive", "severity": "low",
        })
        self.assertEqual(result["automation_eligibility"], "manual_only")

    def test_cost_optimisation_defaults_to_needs_signoff_not_auto(self):
        result = self.policy.classify_finding({
            "category": "cost_optimisation", "confidence": 0.9, "evidence_strength": "strong", "severity": "low",
        })
        self.assertIn(result["automation_eligibility"], ("needs_signoff", "needs_more_evidence"))
        self.assertNotIn(result["automation_eligibility"], ("auto_apply", "auto_with_verification"))

    def test_policy_confidence_cannot_raise_eligibility(self):
        """HQ V1 Integration QA §14/§28 authority-firewall regression: the
        LLM's own self-reported confidence/evidence_strength may only ever
        DOWNGRADE automation_eligibility below a category's deterministic
        default, never raise it above that ceiling. A category whose
        default is needs_signoff (config the model has no influence over)
        must stay needs_signoff-or-more-restrictive even at maximum
        self-reported confidence and conclusive evidence_strength."""
        result = self.policy.classify_finding({
            "category": "duplicate_implementation", "confidence": 1.0,
            "evidence_strength": "conclusive", "severity": "low",
        })
        self.assertNotIn(result["automation_eligibility"], ("auto_apply", "auto_with_verification"))

    def test_policy_low_confidence_downgrades_an_auto_eligible_category(self):
        """The other half of the same invariant: confidence CAN downgrade
        (dead_code defaults to auto_with_verification), confirming the
        ratchet is real and not simply inert."""
        result = self.policy.classify_finding({
            "category": "dead_code", "confidence": 0.1,
            "evidence_strength": "conclusive", "severity": "low",
        })
        self.assertEqual(result["automation_eligibility"], "needs_more_evidence")


class TestInternalDiscovery(unittest.TestCase):
    def test_finding_to_candidate_preserves_evidence_and_category(self):
        finding = {
            "finding_id": "FND-001", "category": "dead_code", "title": "Unused module",
            "description": "no callers", "severity": "low", "confidence": 0.9,
            "evidence": [{"type": "unreferenced_code", "observation": "no callers", "location": "a.py:1"}],
            "proposed_action": {"type": "delete", "description": "remove it"},
            "expected_benefit": "less code to maintain",
            "risk_level": "low", "automation_eligibility": "auto_with_verification",
        }
        candidate = internal_discovery.finding_to_candidate(finding)
        self.assertEqual(candidate["category"], "dead_code")
        self.assertEqual(candidate["change_class"], "maintenance")
        self.assertEqual(candidate["source_finding_id"], "FND-001")
        self.assertEqual(candidate["why_relevant"], "less code to maintain")

    def test_discover_bounded_by_max_candidates(self):
        findings = [
            {"finding_id": f"FND-{i:03d}", "category": "dead_code", "title": f"T{i}", "confidence": 0.9, "severity": "low"}
            for i in range(10)
        ]
        candidates = internal_discovery.discover(findings, evidence={}, max_candidates=3)
        self.assertEqual(len(candidates), 3)

    def test_evidence_derived_candidate_for_unrotated_call_log(self):
        evidence = {"model_router_audit": {"call_log_size_mb": 50.0}, "filesystem_audit": {}}
        candidates = internal_discovery.evidence_derived_candidates(evidence, max_candidates=5)
        self.assertTrue(any("call log" in c["title"].lower() for c in candidates))

    def test_no_candidates_when_evidence_is_unremarkable(self):
        evidence = {"model_router_audit": {"call_log_size_mb": 1.0}, "filesystem_audit": {"config_files": []}}
        candidates = internal_discovery.evidence_derived_candidates(evidence, max_candidates=5)
        self.assertEqual(candidates, [])


class TestExternalDiscovery(unittest.TestCase):
    def test_network_failure_degrades_to_empty_list_not_exception(self):
        topics = [{"id": "t1", "class": "capability", "github_query": "q", "why_relevant": "because"}]
        with patch("external_discovery.urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
            candidates = external_discovery.discover(topics, DEFAULT_EVOLUTION_CONFIG)
        self.assertEqual(candidates, [])

    def test_topic_without_why_relevant_is_skipped_without_a_request(self):
        topics = [{"id": "t1", "class": "capability", "github_query": "q"}]  # no why_relevant
        with patch("external_discovery.urllib.request.urlopen") as mocked:
            candidates = external_discovery.discover(topics, DEFAULT_EVOLUTION_CONFIG)
        mocked.assert_not_called()
        self.assertEqual(candidates, [])

    def test_results_bounded_by_config(self):
        topic = {"id": "t1", "class": "capability", "github_query": "q", "why_relevant": "because", "gap_hypothesis": "g"}

        class FakeResponse:
            def __init__(self, payload):
                self._payload = json.dumps(payload).encode()

            def read(self):
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        many_items = [
            {"full_name": f"org/repo{i}", "html_url": f"https://github.com/org/repo{i}",
             "description": "d", "license": {"spdx_id": "MIT"}, "stargazers_count": 10,
             "open_issues_count": 0, "forks_count": 0, "pushed_at": "2026-01-01T00:00:00Z", "archived": False}
            for i in range(50)
        ]
        config = {**DEFAULT_EVOLUTION_CONFIG, "max_external_candidates_per_search": 5, "max_external_candidates_per_cycle": 5}
        with patch("external_discovery.urllib.request.urlopen", return_value=FakeResponse({"items": many_items})):
            candidates = external_discovery.discover([topic], config)
        self.assertEqual(len(candidates), 5)

    def test_archived_or_unlicensed_repo_flagged_higher_complexity(self):
        topic = {"id": "t1", "class": "capability", "why_relevant": "because"}
        repo = {"full_name": "org/repo", "html_url": "https://github.com/org/repo", "description": "d",
                "license": None, "stargazers_count": 5, "archived": True}
        candidate = external_discovery._repo_to_candidate(repo, topic, "2026-09-06T00:00:00Z")
        self.assertEqual(candidate["complexity"], "high")
        self.assertEqual(candidate["cost_impact"], "unknown")  # section 11: never fabricate cost data


class TestMigration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.data_root = self.tmpdir
        run_dir = self.data_root / "runs" / "2026-09-01-000000"
        run_dir.mkdir(parents=True)
        (run_dir / "findings_classified.json").write_text(json.dumps({"findings": [
            {"finding_id": "FND-001", "category": "dead_code", "title": "Unused helper", "description": "x",
             "severity": "low", "confidence": 0.9,
             "evidence": [{"type": "unreferenced_code", "observation": "no callers", "location": "a.py:1"}],
             "proposed_action": {"type": "delete", "description": "remove"}, "expected_benefit": "less code",
             "risk_level": "low", "automation_eligibility": "auto_with_verification"},
            {"finding_id": "FND-002", "category": "placeholder_code", "title": "TODO in prod path",
             "description": "y", "severity": "medium", "confidence": 0.85, "evidence": [],
             "proposed_action": {"type": "refactor", "description": "z"}, "expected_benefit": "cleaner code",
             "risk_level": "medium", "automation_eligibility": "needs_signoff"},
        ]}))
        review_dir = self.data_root / "review"
        review_dir.mkdir(parents=True)
        (review_dir / "decisions.jsonl").write_text(
            json.dumps({"finding_id": "FND-001", "decision": "approved", "reasoning": "fine"}) + "\n" +
            json.dumps({"finding_id": "FND-002", "decision": "rejected", "reasoning": "not needed"}) + "\n"
        )
        (review_dir / "remediation_results.jsonl").write_text(
            json.dumps({"timestamp": "t", "finding_id": "FND-001", "success": True, "message": "deleted"}) + "\n"
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_migrates_findings_with_correct_states(self):
        result = migration.migrate_legacy_findings_to_opportunities(self.data_root)
        self.assertEqual(result["migrated_count"], 2)
        store = OpportunityStore(self.data_root)
        by_title = {o["title"]: o for o in store.all_current()}
        self.assertEqual(by_title["Unused helper"]["lifecycle_state"], "learned")
        self.assertTrue(by_title["Unused helper"]["outcome"]["implementation_success"])
        self.assertIsNone(by_title["Unused helper"]["outcome"]["improvement_success"])
        self.assertEqual(by_title["TODO in prod path"]["lifecycle_state"], "rejected")

    def test_migration_is_idempotent(self):
        migration.migrate_legacy_findings_to_opportunities(self.data_root)
        second = migration.migrate_legacy_findings_to_opportunities(self.data_root)
        self.assertEqual(second["migrated_count"], 0)
        self.assertEqual(second["skipped_already_migrated_count"], 2)
        store = OpportunityStore(self.data_root)
        self.assertEqual(len(store.all_current()), 2)  # never duplicated

    def test_no_runs_directory_returns_empty_summary_not_error(self):
        empty_root = Path(tempfile.mkdtemp())
        try:
            result = migration.migrate_legacy_findings_to_opportunities(empty_root)
            self.assertEqual(result["migrated_count"], 0)
        finally:
            shutil.rmtree(empty_root, ignore_errors=True)


class TestEvolutionOrchestrator(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_orchestrator(self):
        import evolution_orchestrator
        orch = evolution_orchestrator.EvolutionOrchestrator(REPO_ROOT, self.tmpdir)
        orch._load_watchlist = lambda: []  # never hit the real network in this test
        return orch

    def test_dry_run_never_writes_anything(self):
        orch = self._make_orchestrator()
        result = orch.run_cycle(dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse((self.tmpdir / "review" / "opportunities.jsonl").exists())
        self.assertFalse((self.tmpdir / "review" / "evolution_summary.json").exists())

    def test_nothing_worth_changing_is_a_valid_successful_result(self):
        orch = self._make_orchestrator()
        result = orch.run_cycle(dry_run=False)
        self.assertTrue(result["nothing_worth_changing"])
        self.assertEqual(result["worth_considering_count"], 0)

    def test_injected_candidate_surfaces_and_dedups_on_second_run(self):
        orch = self._make_orchestrator()
        candidate = make_candidate(discovery_source="internal", category="performance_gap", change_class="cost_optimisation")
        with patch("internal_discovery.discover", return_value=[candidate]):
            first = orch.run_cycle(dry_run=False)
            second = orch.run_cycle(dry_run=False)

        self.assertEqual(first["worth_considering_count"], 1)
        self.assertEqual(second["duplicate_count"], 1)
        self.assertEqual(second["worth_considering_count"], 0)

        store = OpportunityStore(self.tmpdir)
        current = store.all_current()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["lifecycle_state"], "proposed")
        self.assertIn("method", current[0]["investigation"])  # template fallback recorded, not silently empty

    def test_capability_opportunity_is_never_auto_eligible(self):
        orch = self._make_orchestrator()
        candidate = make_candidate(discovery_source="external", change_class="capability")
        with patch("internal_discovery.discover", return_value=[candidate]):
            orch.run_cycle(dry_run=False)
        store = OpportunityStore(self.tmpdir)
        current = store.all_current()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["automation_eligibility"], "manual_only")

    def test_surfaced_count_never_exceeds_configured_cap(self):
        orch = self._make_orchestrator()
        orch.evolution_config = {**orch.evolution_config, "max_opportunities_surfaced_per_cycle": 1}
        candidates = [make_candidate(title=f"Candidate {i}", discovery_source="internal") for i in range(4)]
        with patch("internal_discovery.discover", return_value=candidates):
            result = orch.run_cycle(dry_run=False)
        self.assertLessEqual(result["worth_considering_count"], 1)


if __name__ == "__main__":
    unittest.main()
