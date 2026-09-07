"""
Tests for the HQ Evolution V2 outcome-learning loop: outcome_contract.py,
evidence_sources.py, outcome_schema.py, outcome_evaluation.py,
evolution_memory.py, and their wiring into evolution_orchestrator.py /
dashboard.py.

Core principle under test throughout: IMPLEMENTATION SUCCESS != IMPROVEMENT
SUCCESS, and missing evidence never becomes a success verdict. Same bare-
sibling-import convention as the other test_hq_evolution*.py files — see
test_hq_evolution.py's own module docstring for why.
"""

import json
import shutil
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))

import outcome_contract  # noqa: E402
import outcome_evaluation  # noqa: E402
import outcome_schema  # noqa: E402
import evolution_memory  # noqa: E402
import evidence_sources  # noqa: E402
from opportunity_store import OpportunityStore, OUTCOME_RESULTS, MISSION_ONLY_CLASSES  # noqa: E402
from policy import PolicyEngine  # noqa: E402
import evolution_orchestrator  # noqa: E402


def make_candidate(**overrides):
    base = {
        "title": "Rotate an unrotated log",
        "source": "s",
        "discovery_source": "internal",
        "change_class": "maintenance",
        "summary": "grows unbounded",
        "why_relevant": "disk growth",
        "investigation": {},
        "provenance": [{"source": "internal_evidence_collector", "location": "x", "detail": "call_log_size_mb=50.0"}],
    }
    base.update(overrides)
    return base


class TempStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.store = OpportunityStore(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)


# ── Outcome Contract (section 43 checklist) ─────────────────────────────

class TestOutcomeContract(unittest.TestCase):
    def test_contract_persists_expected_benefit(self):
        c = outcome_contract.build_outcome_contract(make_candidate(why_relevant="disk growth risk"), REPO_ROOT)
        self.assertEqual(c["expected_benefit"], "disk growth risk")

    def test_baseline_retains_provenance_via_measurement_hint(self):
        candidate = make_candidate(measurement_hint={"type": "file_size_mb", "path": "config/self_improvement_policy.json"})
        c = outcome_contract.build_outcome_contract(candidate, REPO_ROOT)
        self.assertTrue(c["baseline"]["available"])
        self.assertIn("provenance", c["baseline"])
        self.assertIn("captured_at", c["baseline"])
        self.assertIsInstance(c["baseline"]["value"], float)

    def test_deterministic_baseline_from_discovery_provenance(self):
        c = outcome_contract.build_outcome_contract(make_candidate(change_class="maintenance"), REPO_ROOT)
        self.assertEqual(c["measurement_type"], "deterministic")
        self.assertTrue(c["baseline"]["available"])
        self.assertIn("call_log_size_mb=50.0", c["baseline"]["value"])

    def test_missing_baseline_remains_explicitly_unknown_not_fabricated(self):
        """A quantitative change_class with no measurement_hint and no
        provenance must say so explicitly, never guess a number."""
        candidate = make_candidate(change_class="cost_optimisation", provenance=[])
        c = outcome_contract.build_outcome_contract(candidate, REPO_ROOT)
        self.assertEqual(c["measurement_type"], "quantitative")
        self.assertFalse(c["baseline"]["available"])
        self.assertIn("reason", c["baseline"])

    def test_qualitative_measurement_explicitly_not_a_single_baseline(self):
        candidate = make_candidate(change_class="capability", provenance=[])
        c = outcome_contract.build_outcome_contract(candidate, REPO_ROOT)
        self.assertEqual(c["measurement_type"], "mixed")
        self.assertFalse(c["baseline"]["available"])

    def test_observation_window_is_event_cycle_based_not_only_elapsed_days(self):
        for change_class, expected_type in [
            ("maintenance", "immediate"), ("configuration", "immediate"),
            ("reliability", "cycles"), ("cost_optimisation", "cycles"),
            ("capability", "cycles"), ("architecture", "cycles"),
        ]:
            c = outcome_contract.build_outcome_contract(make_candidate(change_class=change_class), REPO_ROOT)
            self.assertEqual(c["observation_window"]["type"], expected_type, change_class)
            self.assertGreaterEqual(c["observation_window"]["count"], 1)

    def test_every_change_class_has_a_regression_guardrail(self):
        """Section 30: no-self-reward-loop — every contract must define
        what regression would look like, not just what success looks like."""
        for change_class in ("maintenance", "configuration", "reliability", "cost_optimisation",
                              "capability", "product_improvement", "architecture"):
            c = outcome_contract.build_outcome_contract(make_candidate(change_class=change_class), REPO_ROOT)
            self.assertTrue(c["regression_signal"])

    def test_contract_starts_pending_implementation_never_pre_started(self):
        c = outcome_contract.build_outcome_contract(make_candidate(), REPO_ROOT)
        self.assertEqual(c["evaluation_status"], "pending_implementation")
        self.assertIsNone(c["observation_started_at"])


# ── Implementation vs outcome success (section 43) ──────────────────────

class TestImplementationStatus(TempStoreTestCase):
    def test_manual_signal_reports_implemented(self):
        opp = {"outcome": {"implementation_source": "manual", "implementation_verified_at": "2026-01-01T00:00:00+00:00"}}
        result = outcome_evaluation.check_implementation_status(opp, REPO_ROOT, self.tmpdir)
        self.assertTrue(result["implemented"])
        self.assertEqual(result["source"], "manual")

    def test_no_signal_reports_not_implemented(self):
        opp = {"outcome": {}}
        result = outcome_evaluation.check_implementation_status(opp, REPO_ROOT, self.tmpdir)
        self.assertFalse(result["implemented"])
        self.assertIsNone(result["source"])

    def test_remediation_success_via_results_jsonl(self):
        review_dir = self.tmpdir / "review"
        review_dir.mkdir(parents=True)
        (review_dir / "remediation_results.jsonl").write_text(
            json.dumps({"timestamp": "2026-01-01T00:00:00+00:00", "finding_id": "FND-001", "success": True, "message": "done"}) + "\n"
        )
        opp = {"source_finding_id": "FND-001", "outcome": {}}
        result = outcome_evaluation.check_implementation_status(opp, REPO_ROOT, self.tmpdir)
        self.assertTrue(result["implemented"])
        self.assertEqual(result["source"], "remediation")

    def test_remediation_failure_reports_not_implemented(self):
        review_dir = self.tmpdir / "review"
        review_dir.mkdir(parents=True)
        (review_dir / "remediation_results.jsonl").write_text(
            json.dumps({"timestamp": "t", "finding_id": "FND-002", "success": False, "message": "failed"}) + "\n"
        )
        opp = {"source_finding_id": "FND-002", "outcome": {}}
        result = outcome_evaluation.check_implementation_status(opp, REPO_ROOT, self.tmpdir)
        self.assertFalse(result["implemented"])

    def test_mission_status_via_supabase_read(self):
        opp = {"mission_id": "MSN-0001", "outcome": {}}
        with patch("evidence_sources.mission_status", return_value={"available": True, "status": "Implemented", "updated_at": "t"}):
            result = outcome_evaluation.check_implementation_status(opp, REPO_ROOT, self.tmpdir)
        self.assertTrue(result["implemented"])
        self.assertEqual(result["source"], "mission")

    def test_mission_not_yet_implemented(self):
        opp = {"mission_id": "MSN-0002", "outcome": {}}
        with patch("evidence_sources.mission_status", return_value={"available": True, "status": "Idea", "updated_at": "t"}):
            result = outcome_evaluation.check_implementation_status(opp, REPO_ROOT, self.tmpdir)
        self.assertFalse(result["implemented"])

    def test_never_raises_on_garbage_input(self):
        result = outcome_evaluation.check_implementation_status({}, REPO_ROOT, self.tmpdir)
        self.assertFalse(result["implemented"])


class TestObservationWindow(unittest.TestCase):
    def test_not_started_is_not_satisfied(self):
        opp = {"outcome_contract": {"observation_window": {"type": "immediate", "count": 1}, "observation_started_at": None}}
        ready, _ = outcome_evaluation.is_observation_window_satisfied(opp)
        self.assertFalse(ready)

    def test_immediate_is_satisfied_once_started(self):
        opp = {"outcome_contract": {"observation_window": {"type": "immediate", "count": 1},
                                     "observation_started_at": datetime.now(timezone.utc).isoformat()}}
        ready, _ = outcome_evaluation.is_observation_window_satisfied(opp)
        self.assertTrue(ready)

    def test_cycles_not_satisfied_until_count_reached(self):
        opp = {"outcome_contract": {"observation_window": {"type": "cycles", "count": 5},
                                     "observation_started_at": datetime.now(timezone.utc).isoformat()}}
        ready, reason = outcome_evaluation.is_observation_window_satisfied(opp, cycles_elapsed=2)
        self.assertFalse(ready)
        self.assertIn("2", reason)
        ready2, _ = outcome_evaluation.is_observation_window_satisfied(opp, cycles_elapsed=5)
        self.assertTrue(ready2)

    def test_cycles_without_a_count_is_not_ready(self):
        opp = {"outcome_contract": {"observation_window": {"type": "cycles", "count": 5},
                                     "observation_started_at": datetime.now(timezone.utc).isoformat()}}
        ready, _ = outcome_evaluation.is_observation_window_satisfied(opp, cycles_elapsed=None)
        self.assertFalse(ready)

    def test_days_window(self):
        started = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        opp = {"outcome_contract": {"observation_window": {"type": "days", "count": 7}, "observation_started_at": started}}
        ready, _ = outcome_evaluation.is_observation_window_satisfied(opp)
        self.assertTrue(ready)


class TestEvaluateOutcomeSkipBehavior(TempStoreTestCase):
    def test_skips_when_not_implemented_never_sets_a_verdict(self):
        opp = {"outcome": {}, "outcome_contract": {"observation_window": {"type": "immediate", "count": 1}, "observation_started_at": None}}
        result = outcome_evaluation.evaluate_outcome(opp, REPO_ROOT, self.tmpdir, self.store)
        self.assertTrue(result.get("skip"))
        self.assertNotIn("outcome_result", result)

    def test_successful_implementation_alone_does_not_imply_improved(self):
        """The core V2 principle: implementation success != outcome success.
        A confirmed implementation with a baseline==current (no change)
        must classify as no_material_change, never 'improved'."""
        contract = outcome_contract.build_outcome_contract(
            make_candidate(measurement_hint={"type": "file_size_mb", "path": "__nonexistent_test_file__.jsonl"}), REPO_ROOT)
        # baseline unavailable (file doesn't exist -> value 0.0, available True actually)
        opp = {
            "outcome": {"implementation_source": "manual", "implementation_verified_at": datetime.now(timezone.utc).isoformat()},
            "outcome_contract": {**contract, "observation_started_at": datetime.now(timezone.utc).isoformat()},
            "measurement_hint": {"type": "file_size_mb", "path": "__nonexistent_test_file__.jsonl"},
        }
        result = outcome_evaluation.evaluate_outcome(opp, REPO_ROOT, self.tmpdir, self.store)
        self.assertNotEqual(result.get("outcome_result"), "improved")
        self.assertIn(result.get("outcome_result"), ("no_material_change", "inconclusive"))


# ── Evaluation vocabulary (section 44) ──────────────────────────────────

class TestDeterministicEvaluation(unittest.TestCase):
    def test_improved_when_metric_drops_materially(self):
        contract = {"measurement_type": "quantitative", "baseline": {"available": True, "value": 100.0}}
        evidence = {"current_measurement": {"available": True, "value": 50.0}}
        result = outcome_evaluation.evaluate_deterministic(contract, evidence)
        self.assertEqual(result["outcome_result"], "improved")
        self.assertEqual(result["method"], "deterministic")

    def test_no_material_change_within_threshold(self):
        contract = {"measurement_type": "quantitative", "baseline": {"available": True, "value": 100.0}}
        evidence = {"current_measurement": {"available": True, "value": 95.0}}
        result = outcome_evaluation.evaluate_deterministic(contract, evidence)
        self.assertEqual(result["outcome_result"], "no_material_change")

    def test_regressed_when_metric_grows_materially(self):
        contract = {"measurement_type": "quantitative", "baseline": {"available": True, "value": 100.0}}
        evidence = {"current_measurement": {"available": True, "value": 200.0}}
        result = outcome_evaluation.evaluate_deterministic(contract, evidence)
        self.assertEqual(result["outcome_result"], "regressed")

    def test_none_when_not_applicable(self):
        contract = {"measurement_type": "qualitative", "baseline": {"available": False}}
        evidence = {"current_measurement": {"available": False}}
        result = outcome_evaluation.evaluate_deterministic(contract, evidence)
        self.assertIsNone(result)

    def test_none_when_baseline_unavailable(self):
        contract = {"measurement_type": "quantitative", "baseline": {"available": False, "reason": "x"}}
        evidence = {"current_measurement": {"available": True, "value": 10.0}}
        self.assertIsNone(outcome_evaluation.evaluate_deterministic(contract, evidence))


class TestInconclusiveHandling(TempStoreTestCase):
    def test_inconclusive_from_missing_evidence_not_success(self):
        contract = outcome_contract.build_outcome_contract(make_candidate(change_class="cost_optimisation", provenance=[]), REPO_ROOT)
        # Force an immediate window so this test isolates "evidence missing"
        # from "window not yet elapsed" (a separate, already-covered case).
        contract["observation_window"] = {"type": "immediate", "count": 1}
        opp = {
            "outcome": {"implementation_source": "manual", "implementation_verified_at": datetime.now(timezone.utc).isoformat()},
            "outcome_contract": {**contract, "observation_started_at": datetime.now(timezone.utc).isoformat()},
        }
        result = outcome_evaluation.evaluate_outcome(opp, REPO_ROOT, self.tmpdir, self.store)
        self.assertEqual(result["outcome_result"], "inconclusive")

    def test_inconclusive_forced_by_concurrent_change(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        # A second, concurrent 'reliability' opportunity landing during the window.
        self.store.create_new(title="Other reliability change", change_class="reliability",
                               discovery_source="internal", lifecycle_state="implementing")
        contract = outcome_contract.build_outcome_contract(make_candidate(change_class="reliability", measurement_hint={"type": "file_size_mb", "path": "__nope__.jsonl"}), REPO_ROOT)
        opp = {
            "opportunity_id": "EVO-TEST", "change_class": "reliability",
            "outcome": {"implementation_source": "manual", "implementation_verified_at": now_iso},
            "outcome_contract": {**contract, "observation_started_at": now_iso, "observation_window": {"type": "immediate", "count": 1}},
            "measurement_hint": {"type": "file_size_mb", "path": "__nope__.jsonl"},
        }
        result = outcome_evaluation.evaluate_outcome(opp, REPO_ROOT, self.tmpdir, self.store)
        self.assertEqual(result["outcome_result"], "inconclusive")
        self.assertIsNotNone(result.get("attribution_risk"))

    def test_not_yet_ready_before_window_elapses(self):
        contract = outcome_contract.build_outcome_contract(make_candidate(change_class="architecture"), REPO_ROOT)
        opp = {
            "outcome": {"implementation_source": "manual", "implementation_verified_at": datetime.now(timezone.utc).isoformat()},
            "outcome_contract": {**contract, "observation_started_at": datetime.now(timezone.utc).isoformat()},
        }
        result = outcome_evaluation.evaluate_outcome(opp, REPO_ROOT, self.tmpdir, self.store, cycles_elapsed=1)
        self.assertEqual(result["outcome_result"], "not_yet_ready")

    def test_qualitative_class_never_reaches_improved_without_new_evidence(self):
        """A capability/architecture/product_improvement opportunity has no
        measurement_hint and no post-implementation evidence source wired —
        only its own PRE-implementation investigation notes. Even if a
        mocked model would happily assert "improved" from those notes
        alone, evaluate_outcome must never call the model (there is no new
        evidence for it to interpret) and must return inconclusive. This
        guards the exact failure mode section 10 forbids: the model
        confirming its own earlier optimism instead of genuine evidence."""
        contract = outcome_contract.build_outcome_contract(
            make_candidate(change_class="capability", investigation={"why_hq_is_looking_at_this": "seems promising"}),
            REPO_ROOT,
        )
        contract["observation_window"] = {"type": "immediate", "count": 1}
        opp = {
            "opportunity_id": "EVO-QUAL-TEST",
            "change_class": "capability",
            "investigation": {"why_hq_is_looking_at_this": "seems promising"},
            "outcome": {"implementation_source": "manual", "implementation_verified_at": datetime.now(timezone.utc).isoformat()},
            "outcome_contract": {**contract, "observation_started_at": datetime.now(timezone.utc).isoformat()},
        }

        class ImproperlyOptimisticRouter:
            def health_check(self):
                return True

            def evaluate_outcome(self, evidence_bundle):
                return {"success": True, "evaluation": {"outcome_result": "improved", "confidence": "high",
                                                          "evidence_summary": "it feels great", "what_worked": "",
                                                          "what_did_not": "", "unexpected_effects": [], "future_implication": ""}}

        router = ImproperlyOptimisticRouter()
        result = outcome_evaluation.evaluate_outcome(opp, REPO_ROOT, self.tmpdir, self.store, router=router)
        self.assertEqual(result["outcome_result"], "inconclusive")
        self.assertNotEqual(result.get("method"), "model_synthesis")


class TestOutcomeSchema(unittest.TestCase):
    def test_valid_input_passes_through(self):
        raw = {"outcome_result": "improved", "evidence_summary": "x", "confidence": "high",
               "what_worked": "a", "what_did_not": "b", "unexpected_effects": ["c"], "future_implication": "d"}
        result = outcome_schema.validate_outcome_evaluation(raw)
        self.assertEqual(result["outcome_result"], "improved")
        self.assertEqual(result["confidence"], "high")

    def test_invalid_result_falls_back_to_inconclusive_never_success(self):
        result = outcome_schema.validate_outcome_evaluation({"outcome_result": "definitely great"})
        self.assertEqual(result["outcome_result"], "inconclusive")

    def test_model_cannot_assert_not_yet_ready_itself(self):
        """not_yet_ready is a pre-evaluation state decided before the model
        is ever called — the model's own output must never assert it."""
        result = outcome_schema.validate_outcome_evaluation({"outcome_result": "not_yet_ready"})
        self.assertEqual(result["outcome_result"], "inconclusive")

    def test_invalid_confidence_falls_back_to_low(self):
        result = outcome_schema.validate_outcome_evaluation({"confidence": "extremely sure"})
        self.assertEqual(result["confidence"], "low")

    def test_garbage_input_never_raises(self):
        for garbage in (None, {}, {"unexpected_effects": "not a list"}):
            try:
                outcome_schema.validate_outcome_evaluation(garbage if isinstance(garbage, dict) else {})
            except Exception as exc:
                self.fail(f"validate_outcome_evaluation raised on {garbage!r}: {exc}")

    def test_honest_fallback_never_fabricates_success(self):
        fallback = outcome_schema.honest_fallback_outcome_evaluation("model unreachable")
        self.assertEqual(fallback["outcome_result"], "inconclusive")
        self.assertEqual(fallback["confidence"], "low")
        self.assertEqual(fallback["method"], "template_fallback")


class TestEvidenceRetentionAfterModelSynthesis(TempStoreTestCase):
    def test_evidence_detail_present_regardless_of_evaluation_method(self):
        """Section 14/31: model interpretation must not erase underlying
        evidence — evidence_detail must survive in the returned dict."""
        contract = outcome_contract.build_outcome_contract(make_candidate(), REPO_ROOT)
        opp = {
            "outcome": {"implementation_source": "manual", "implementation_verified_at": datetime.now(timezone.utc).isoformat()},
            "outcome_contract": {**contract, "observation_started_at": datetime.now(timezone.utc).isoformat()},
            "measurement_hint": {"type": "file_size_mb", "path": "config/self_improvement_policy.json"},
        }
        result = outcome_evaluation.evaluate_outcome(opp, REPO_ROOT, self.tmpdir, self.store)
        self.assertIn("evidence_detail", result)
        self.assertIn("implementation_status", result)


# ── Authority firewall (section 45) ──────────────────────────────────────

class TestAuthorityFirewall(unittest.TestCase):
    def setUp(self):
        self.policy = PolicyEngine(REPO_ROOT / "config" / "self_improvement_policy.json")

    def test_outcome_evaluation_module_never_imports_policy_engine(self):
        """Structural guarantee: the evaluation engine has no code path
        that could reach PolicyEngine at all. Checks actual import/call
        statements, not the module's own docstring (which legitimately
        names PolicyEngine while explaining that this module never touches
        it)."""
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(outcome_evaluation))
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_names.add(node.module or "")
                imported_names.update(alias.name for alias in node.names)
        self.assertNotIn("policy", imported_names)
        self.assertNotIn("PolicyEngine", imported_names)
        # No call anywhere in the module constructs a PolicyEngine.
        calls = [ast.dump(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)]
        self.assertFalse(any("PolicyEngine" in c for c in calls))

    def test_automation_eligibility_identical_regardless_of_outcome_result(self):
        """No outcome_result value can be present anywhere in the dict
        classify_finding() reads without changing its verdict — because it
        never reads the outcome dict at all. Prove this across every value."""
        base_finding = {"category": "capability", "confidence": 0.9, "evidence_strength": "conclusive", "severity": "low"}
        eligibilities = set()
        for result in OUTCOME_RESULTS:
            finding_with_outcome_result = {**base_finding, "outcome": {"outcome_result": result}}
            classified = self.policy.classify_finding(finding_with_outcome_result)
            eligibilities.add(classified["automation_eligibility"])
        self.assertEqual(len(eligibilities), 1)
        self.assertEqual(next(iter(eligibilities)), "manual_only")

    def test_prior_improved_outcome_does_not_auto_approve_new_candidate(self):
        """A new discovery candidate always starts at 'discovered' — a
        prior learned+improved record in memory must never fast-track a
        NEW opportunity's lifecycle_state."""
        tmpdir = Path(tempfile.mkdtemp())
        try:
            store = OpportunityStore(tmpdir)
            store.create_new(title="Prior success", change_class="cost_optimisation", discovery_source="internal",
                              lifecycle_state="learned", outcome={"outcome_result": "improved", "confidence": "high"})
            new_opp = store.create_new(title="A new but similar idea", change_class="cost_optimisation",
                                        discovery_source="internal", lifecycle_state="discovered")
            self.assertEqual(new_opp.lifecycle_state, "discovered")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_mission_only_classes_still_match_policy_manual_only(self):
        for change_class in MISSION_ONLY_CLASSES:
            rules = self.policy.category_policy.get(change_class, {})
            self.assertEqual(rules.get("automation_eligibility"), "manual_only")


# ── Evolution memory retrieval (section 46) ─────────────────────────────

class TestEvolutionMemoryRetrieval(TempStoreTestCase):
    def test_similar_prior_learned_outcome_is_retrievable(self):
        self.store.create_new(
            title="Switch model router to cheaper embedding provider", change_class="cost_optimisation",
            discovery_source="internal", lifecycle_state="learned",
            outcome={"outcome_result": "improved", "confidence": "high", "evidence_summary": "cost dropped"},
        )
        candidate = {"title": "Switch model router to cheaper completion provider", "change_class": "cost_optimisation",
                     "discovery_source": "internal", "summary": "", "why_relevant": ""}
        related = evolution_memory.find_related_outcomes(candidate, self.store)
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]["relationship"], "learned")
        self.assertEqual(related[0]["outcome_result"], "improved")

    def test_unrelated_change_class_never_injected(self):
        self.store.create_new(title="Switch model router to cheaper embedding provider", change_class="architecture",
                               discovery_source="internal", lifecycle_state="learned",
                               outcome={"outcome_result": "improved"})
        candidate = {"title": "Switch model router to cheaper embedding provider", "change_class": "cost_optimisation",
                     "discovery_source": "internal", "summary": "", "why_relevant": ""}
        related = evolution_memory.find_related_outcomes(candidate, self.store)
        self.assertEqual(related, [])

    def test_rejected_and_regressed_never_conflated(self):
        self.store.create_new(title="Local model for synthesis task alpha", change_class="cost_optimisation",
                               discovery_source="internal", lifecycle_state="rejected",
                               rejection_reason="cost not justified")
        self.store.create_new(title="Local model for synthesis task beta", change_class="cost_optimisation",
                               discovery_source="internal", lifecycle_state="learned",
                               outcome={"outcome_result": "regressed", "confidence": "high", "evidence_summary": "latency rose"})
        candidate = {"title": "Local model for synthesis task gamma", "change_class": "cost_optimisation",
                     "discovery_source": "internal", "summary": "", "why_relevant": ""}
        related = evolution_memory.find_related_outcomes(candidate, self.store)
        rejected = [r for r in related if r["relationship"] == "rejected"]
        learned = [r for r in related if r["relationship"] == "learned"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(len(learned), 1)
        self.assertIsNone(rejected[0]["outcome_result"])
        self.assertIsNone(learned[0]["rejection_reason"])
        self.assertEqual(learned[0]["outcome_result"], "regressed")

    def test_user_preference_not_rewritten_as_technical_evidence(self):
        self.store.create_new(title="Local model for synthesis task alpha", change_class="cost_optimisation",
                               discovery_source="internal", lifecycle_state="rejected",
                               rejection_reason="team simply did not want this direction")
        candidate = {"title": "Local model for synthesis task alpha redo", "change_class": "cost_optimisation",
                     "discovery_source": "internal", "summary": "", "why_relevant": ""}
        related = evolution_memory.find_related_outcomes(candidate, self.store)
        formatted = evolution_memory.format_related_experience(related)
        self.assertIn("rejected", formatted.lower())
        self.assertNotIn("regressed", formatted.lower())
        self.assertNotIn("improved", formatted.lower())

    def test_resolved_before_research_history_is_usable(self):
        self.store.create_new(title="Duplicate synthesis gap hypothesis", change_class="cost_optimisation",
                               discovery_source="external", lifecycle_state="resolved_before_research",
                               why_relevant="Telegram already renders canonical brief")
        candidate = {"title": "Duplicate synthesis gap hypothesis revisited", "change_class": "cost_optimisation",
                     "discovery_source": "external", "summary": "", "why_relevant": ""}
        related = evolution_memory.find_related_outcomes(candidate, self.store)
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]["relationship"], "resolved_before_research")

    def test_historical_reevaluation_does_not_erase_prior_verdict(self):
        opp = self.store.create_new(title="X", change_class="reliability", discovery_source="internal",
                                     lifecycle_state="verifying", outcome={"evaluation_history": []})
        first = {"outcome_result": "inconclusive", "confidence": "low", "evidence_summary": "day 7", "evaluated_at": "2026-01-07T00:00:00+00:00", "method": "deterministic"}
        self.store.update(opp.opportunity_id, outcome={"evaluation_history": [first]}, lifecycle_state="verifying")
        second = {"outcome_result": "improved", "confidence": "high", "evidence_summary": "day 21", "evaluated_at": "2026-01-21T00:00:00+00:00", "method": "deterministic"}
        current = self.store.get(opp.opportunity_id)
        history = list(current["outcome"]["evaluation_history"]) + [second]
        self.store.update(opp.opportunity_id, outcome={**current["outcome"], "outcome_result": "improved", "evaluation_history": history}, lifecycle_state="learned")

        final = self.store.get(opp.opportunity_id)
        self.assertEqual(len(final["outcome"]["evaluation_history"]), 2)
        self.assertEqual(final["outcome"]["evaluation_history"][0]["outcome_result"], "inconclusive")
        self.assertEqual(final["outcome"]["evaluation_history"][1]["outcome_result"], "improved")


# ── End-to-end orchestrator integration ─────────────────────────────────

class TestOrchestratorOutcomeLoop(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_orchestrator(self):
        orch = evolution_orchestrator.EvolutionOrchestrator(REPO_ROOT, self.tmpdir)
        orch._load_watchlist = lambda: []
        return orch

    def test_fresh_cycle_reports_calm_zero_state(self):
        orch = self._make_orchestrator()
        result = orch.run_cycle(dry_run=False)
        self.assertEqual(result["outcomes_completed_count"], 0)
        self.assertEqual(result["regressions_count"], 0)
        self.assertIsNone(result["latest_material_learning"])
        self.assertEqual(result["cycle_status"], "ok")
        self.assertIsNotNone(result["freshness"])

    def test_dry_run_never_evaluates_outcomes(self):
        orch = self._make_orchestrator()
        store = OpportunityStore(self.tmpdir)
        contract = outcome_contract.build_outcome_contract(make_candidate(), REPO_ROOT)
        opp = store.create_new(title="X", change_class="maintenance", discovery_source="internal",
                                lifecycle_state="approved", outcome_contract=contract)
        result = orch.run_cycle(dry_run=True)
        self.assertEqual(result["outcomes_completed_count"], 0)
        # dry-run must never write — record must be unchanged
        current = store.get(opp.opportunity_id)
        self.assertEqual(current["lifecycle_state"], "approved")

    def test_end_to_end_manual_implementation_to_learned(self):
        orch = self._make_orchestrator()
        store = OpportunityStore(self.tmpdir)
        candidate = make_candidate(change_class="maintenance")
        contract = outcome_contract.build_outcome_contract(candidate, REPO_ROOT)
        opp = store.create_new(title=candidate["title"], change_class="maintenance", discovery_source="internal",
                                lifecycle_state="approved", outcome_contract=contract, provenance=candidate["provenance"])
        now_iso = datetime.now(timezone.utc).isoformat()
        store.update(opp.opportunity_id,
                      outcome={"implementation_success": True, "implementation_source": "manual", "implementation_verified_at": now_iso},
                      outcome_contract={**contract, "observation_started_at": now_iso, "evaluation_status": "observing"},
                      lifecycle_state="verifying")

        result = orch.run_cycle(dry_run=False)
        final = store.get(opp.opportunity_id)
        self.assertEqual(final["lifecycle_state"], "learned")
        self.assertIn(final["outcome"]["outcome_result"], OUTCOME_RESULTS)
        self.assertEqual(result["outcomes_completed_count"], 1)

    def test_measurement_hint_survives_persistence_and_drives_real_comparison(self):
        """Regression test for a real bug found during manual integration
        testing: measurement_hint must survive from a discovery candidate
        onto the persisted Opportunity, or the one concrete quantitative
        example (call-log rotation) silently degrades to 'no baseline'."""
        orch = self._make_orchestrator()
        store = OpportunityStore(self.tmpdir)
        scratch = self.tmpdir / "fake_call_log.jsonl"
        scratch.write_text("x" * (2 * 1024 * 1024))  # 2MB "before"

        with patch("evidence_sources.file_size_mb", side_effect=lambda path: evidence_sources.file_size_mb.__wrapped__(scratch) if hasattr(evidence_sources.file_size_mb, "__wrapped__") else {"available": True, "value": scratch.stat().st_size / (1024 * 1024), "description": "scratch"}):
            candidate = make_candidate(change_class="maintenance", measurement_hint={"type": "file_size_mb", "path": "__scratch__"})
            contract = outcome_contract.build_outcome_contract(candidate, REPO_ROOT)

        opp = store.create_new(title=candidate["title"], change_class="maintenance", discovery_source="internal",
                                lifecycle_state="approved", outcome_contract=contract,
                                measurement_hint=candidate["measurement_hint"])
        self.assertEqual(store.get(opp.opportunity_id)["measurement_hint"], candidate["measurement_hint"])

        now_iso = datetime.now(timezone.utc).isoformat()
        store.update(opp.opportunity_id,
                      outcome={"implementation_source": "manual", "implementation_verified_at": now_iso},
                      outcome_contract={**contract, "observation_started_at": now_iso, "evaluation_status": "observing"},
                      lifecycle_state="verifying")

        scratch.write_text("x" * 1024)  # shrink -> "after"
        with patch("evidence_sources.file_size_mb", return_value={"available": True, "value": scratch.stat().st_size / (1024 * 1024), "description": "scratch after"}):
            result = orch.run_cycle(dry_run=False)

        final = store.get(opp.opportunity_id)
        self.assertEqual(final["lifecycle_state"], "learned")
        self.assertEqual(final["outcome"]["outcome_result"], "improved")
        self.assertEqual(final["outcome"]["method"], "deterministic")

    def test_evaluation_phase_failure_never_blocks_discovery(self):
        """Section 8 of the audit checklist: a total, unanticipated failure
        of the (newer, less battle-tested) outcome-evaluation phase must
        never take the rest of the overnight cycle down with it —
        discovery/investigation is the pre-existing, load-bearing pipeline
        and has to keep running regardless."""
        orch = self._make_orchestrator()
        with patch.object(orch, "_evaluate_due_outcomes", side_effect=RuntimeError("boom")):
            result = orch.run_cycle(dry_run=False)
        self.assertEqual(result["outcomes_completed_count"], 0)
        self.assertIn("run_id", result)
        self.assertIsNotNone(result["run_id"])


# ── Morning compression (section 48) ────────────────────────────────────

class TestMorningCompression(unittest.TestCase):
    def setUp(self):
        try:
            import flask  # noqa: F401
        except ImportError:
            self.skipTest("Flask not installed in this environment")
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_regressions_count_surfaces_via_evolution_summary(self):
        import dashboard
        original_store = dashboard.opportunity_store
        store = OpportunityStore(self.tmpdir)
        dashboard.opportunity_store = store
        try:
            store.create_new(title="A regression", change_class="reliability", discovery_source="internal",
                              lifecycle_state="learned", outcome={"outcome_result": "regressed"})
            client = dashboard.app.test_client()
            res = client.get("/api/evolution-summary")
            body = res.get_json()
            self.assertEqual(body["regressions_count"], 1)
        finally:
            dashboard.opportunity_store = original_store

    def test_observing_opportunity_is_not_counted_as_pending_decision(self):
        """An in-progress observation window must never present as human
        urgency — only 'proposed' counts toward pending_decisions_count."""
        import dashboard
        original_store = dashboard.opportunity_store
        store = OpportunityStore(self.tmpdir)
        dashboard.opportunity_store = store
        try:
            store.create_new(title="Still observing", change_class="reliability", discovery_source="internal",
                              lifecycle_state="verifying")
            client = dashboard.app.test_client()
            res = client.get("/api/evolution-summary")
            body = res.get_json()
            self.assertEqual(body["pending_decisions_count"], 0)
        finally:
            dashboard.opportunity_store = original_store

    def test_zero_state_is_calm_not_manufactured(self):
        import dashboard
        original_store = dashboard.opportunity_store
        dashboard.opportunity_store = OpportunityStore(self.tmpdir)
        try:
            client = dashboard.app.test_client()
            res = client.get("/api/evolution-summary")
            body = res.get_json()
            self.assertEqual(body["outcomes_completed_count"], 0)
            self.assertEqual(body["regressions_count"], 0)
            self.assertIsNone(body["latest_material_learning"])
        finally:
            dashboard.opportunity_store = original_store

    def test_mark_implemented_requires_prior_approval_and_contract(self):
        import dashboard
        original_store = dashboard.opportunity_store
        store = OpportunityStore(self.tmpdir)
        dashboard.opportunity_store = store
        try:
            client = dashboard.app.test_client()
            opp = store.create_new(title="Not approved yet", change_class="maintenance",
                                    discovery_source="internal", lifecycle_state="proposed")
            res = client.post("/api/opportunity/decide", json={"opportunity_id": opp.opportunity_id, "decision_type": "mark_implemented"})
            self.assertEqual(res.status_code, 400)

            opp2 = store.create_new(title="Approved but no contract", change_class="maintenance",
                                     discovery_source="internal", lifecycle_state="approved")
            res2 = client.post("/api/opportunity/decide", json={"opportunity_id": opp2.opportunity_id, "decision_type": "mark_implemented"})
            self.assertEqual(res2.status_code, 400)
        finally:
            dashboard.opportunity_store = original_store

    def test_approve_improvement_attaches_a_real_outcome_contract(self):
        import dashboard
        original_store = dashboard.opportunity_store
        store = OpportunityStore(self.tmpdir)
        dashboard.opportunity_store = store
        try:
            client = dashboard.app.test_client()
            opp = store.create_new(title="Reduce config sprawl", change_class="configuration",
                                    discovery_source="internal", lifecycle_state="proposed",
                                    provenance=[{"source": "internal_evidence_collector", "location": "config/", "detail": "config_files_count=47"}])
            res = client.post("/api/opportunity/decide", json={"opportunity_id": opp.opportunity_id, "decision_type": "approve_improvement"})
            self.assertEqual(res.status_code, 200)
            body = res.get_json()
            self.assertTrue(body["opportunity"]["outcome_contract"]["expected_benefit"])
            self.assertEqual(body["opportunity"]["outcome_contract"]["evaluation_status"], "pending_implementation")
        finally:
            dashboard.opportunity_store = original_store

    def test_duplicate_approve_call_never_rebuilds_an_existing_contract(self):
        """Section 6: the Outcome Contract is built once, at approval,
        before implementation, and never rebuilt afterward — even if the
        approve/create_mission decision is (re-)posted again later (a
        double-submit, a retried request, or a re-approval after further
        review). A rebuild would recompute baseline/created_at from
        whatever the repo looks like NOW, retrospectively rewriting the
        original pre-implementation baseline to fit later reality."""
        import dashboard
        original_store = dashboard.opportunity_store
        store = OpportunityStore(self.tmpdir)
        dashboard.opportunity_store = store
        try:
            client = dashboard.app.test_client()
            opp = store.create_new(title="Reduce config sprawl", change_class="configuration",
                                    discovery_source="internal", lifecycle_state="proposed",
                                    provenance=[{"source": "internal_evidence_collector", "location": "config/", "detail": "config_files_count=47"}])
            res1 = client.post("/api/opportunity/decide", json={"opportunity_id": opp.opportunity_id, "decision_type": "approve_improvement"})
            first_contract = res1.get_json()["opportunity"]["outcome_contract"]

            # Simulate a second approve call landing later, after the
            # underlying evidence has moved on (state mutated in between,
            # as if the repo/opportunity changed between the two calls).
            store.update(opp.opportunity_id, provenance=[{"source": "internal_evidence_collector", "location": "config/", "detail": "config_files_count=3"}])
            res2 = client.post("/api/opportunity/decide", json={"opportunity_id": opp.opportunity_id, "decision_type": "approve_improvement"})
            second_contract = res2.get_json()["opportunity"]["outcome_contract"]

            self.assertEqual(first_contract["created_at"], second_contract["created_at"])
            self.assertEqual(first_contract["baseline"], second_contract["baseline"])
        finally:
            dashboard.opportunity_store = original_store

    def test_approve_improvement_bridges_to_bounded_remediation_engine(self):
        """Regression test for a real bug found live: approve_improvement
        recorded the decision on the Opportunity but never wrote to
        decisions.jsonl — the ONLY file AutoRemediationExecutor (the actual
        code-changing engine, run by the separate self-improving-system.
        service) reads to decide what to remediate. Two real approvals sat
        with nothing ever triggered. Opportunities that came from a legacy
        classified finding (source_finding_id set) must get an "approved"
        decision written for that exact finding_id so the existing,
        unmodified engine picks it up on its own next run."""
        import dashboard
        original_store = dashboard.opportunity_store
        original_decisions_file = dashboard.DECISIONS_FILE
        store = OpportunityStore(self.tmpdir)
        dashboard.opportunity_store = store
        dashboard.DECISIONS_FILE = self.tmpdir / "decisions.jsonl"
        try:
            client = dashboard.app.test_client()
            opp = store.create_new(title="Dual config files", change_class="configuration",
                                    discovery_source="internal", lifecycle_state="proposed",
                                    source_finding_id="FND-001")
            res = client.post("/api/opportunity/decide", json={"opportunity_id": opp.opportunity_id, "decision_type": "approve_improvement"})
            self.assertEqual(res.status_code, 200)

            self.assertTrue(dashboard.DECISIONS_FILE.exists())
            decisions = [json.loads(line) for line in dashboard.DECISIONS_FILE.read_text().splitlines() if line.strip()]
            matching = [d for d in decisions if d.get("finding_id") == "FND-001"]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0]["decision"], "approved")
        finally:
            dashboard.opportunity_store = original_store
            dashboard.DECISIONS_FILE = original_decisions_file

    def test_approve_improvement_without_source_finding_id_writes_no_decision(self):
        """An opportunity with no source_finding_id (pure internal/external
        discovery, not mirroring a legacy classified finding) has nothing
        for the bounded-remediation engine to act on — must not write a
        decisions.jsonl entry with a None/missing finding_id."""
        import dashboard
        original_store = dashboard.opportunity_store
        original_decisions_file = dashboard.DECISIONS_FILE
        store = OpportunityStore(self.tmpdir)
        dashboard.opportunity_store = store
        dashboard.DECISIONS_FILE = self.tmpdir / "decisions2.jsonl"
        try:
            client = dashboard.app.test_client()
            opp = store.create_new(title="External-only opportunity", change_class="configuration",
                                    discovery_source="external", lifecycle_state="proposed")
            res = client.post("/api/opportunity/decide", json={"opportunity_id": opp.opportunity_id, "decision_type": "approve_improvement"})
            self.assertEqual(res.status_code, 200)
            self.assertFalse(dashboard.DECISIONS_FILE.exists())
        finally:
            dashboard.opportunity_store = original_store
            dashboard.DECISIONS_FILE = original_decisions_file


# ── Remediation/dispatch status surfacing (2026-09-06 UI-visibility fix) ──
#
# Both auto_remediation.py and mission_dispatch.py act on an opportunity/
# Mission a human already approved without writing anything back to the
# record the human is looking at — a needs_signoff opportunity could get a
# draft PR opened for it, or a Mission could get dispatched, with zero
# visible change on HQ Evolution's own page. These two endpoints are a
# read-only join of each engine's own outcome log onto the record it
# concerns, keyed by the source_finding_id/mission_id link that already
# exists — never a second source of truth, never a write.

class TestRemediationStatusSurfacing(unittest.TestCase):
    def setUp(self):
        try:
            import flask  # noqa: F401
        except ImportError:
            self.skipTest("Flask not installed in this environment")
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_remediation_result(self, path, finding_id, success, message):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps({
                "timestamp": "2026-09-06T12:00:00+00:00",
                "finding_id": finding_id,
                "success": success,
                "message": message,
            }) + "\n")

    def test_opportunity_list_surfaces_a_successful_pr_remediation(self):
        import dashboard
        original_store = dashboard.opportunity_store
        original_results_file = dashboard.REMEDIATION_RESULTS_FILE
        store = OpportunityStore(self.tmpdir)
        dashboard.opportunity_store = store
        dashboard.REMEDIATION_RESULTS_FILE = self.tmpdir / "remediation_results.jsonl"
        try:
            store.create_new(title="Dual config files", change_class="configuration",
                              discovery_source="internal", lifecycle_state="approved",
                              source_finding_id="FND-001")
            self._write_remediation_result(dashboard.REMEDIATION_RESULTS_FILE, "FND-001", True,
                                            "Draft PR opened for review: https://github.com/x/y/pull/9")
            client = dashboard.app.test_client()
            res = client.get("/api/opportunities")
            opp = res.get_json()["opportunities"][0]
            self.assertEqual(opp["remediation_status"], "succeeded")
            self.assertEqual(opp["remediation_pr_url"], "https://github.com/x/y/pull/9")
        finally:
            dashboard.opportunity_store = original_store
            dashboard.REMEDIATION_RESULTS_FILE = original_results_file

    def test_opportunity_detail_surfaces_a_failed_remediation_with_no_url(self):
        import dashboard
        original_store = dashboard.opportunity_store
        original_results_file = dashboard.REMEDIATION_RESULTS_FILE
        store = OpportunityStore(self.tmpdir)
        dashboard.opportunity_store = store
        dashboard.REMEDIATION_RESULTS_FILE = self.tmpdir / "remediation_results.jsonl"
        try:
            opp = store.create_new(title="Flaky finding", change_class="configuration",
                                    discovery_source="internal", lifecycle_state="approved",
                                    source_finding_id="FND-002")
            self._write_remediation_result(dashboard.REMEDIATION_RESULTS_FILE, "FND-002", False,
                                            "sync-one exited 1: some error")
            client = dashboard.app.test_client()
            res = client.get(f"/api/opportunity/{opp.opportunity_id}")
            body = res.get_json()
            self.assertEqual(body["remediation_status"], "failed")
            self.assertIsNone(body["remediation_pr_url"])
        finally:
            dashboard.opportunity_store = original_store
            dashboard.REMEDIATION_RESULTS_FILE = original_results_file

    def test_opportunity_with_no_source_finding_id_gets_no_remediation_fields(self):
        import dashboard
        original_store = dashboard.opportunity_store
        original_results_file = dashboard.REMEDIATION_RESULTS_FILE
        store = OpportunityStore(self.tmpdir)
        dashboard.opportunity_store = store
        dashboard.REMEDIATION_RESULTS_FILE = self.tmpdir / "remediation_results.jsonl"
        try:
            store.create_new(title="External-only opportunity", change_class="configuration",
                              discovery_source="external", lifecycle_state="approved")
            client = dashboard.app.test_client()
            res = client.get("/api/opportunities")
            opp = res.get_json()["opportunities"][0]
            self.assertNotIn("remediation_status", opp)
        finally:
            dashboard.opportunity_store = original_store
            dashboard.REMEDIATION_RESULTS_FILE = original_results_file

    def test_opportunity_approved_but_not_yet_remediated_gets_no_remediation_fields(self):
        """No entry in remediation_results.jsonl yet (e.g. approved, but the
        next self-improving-system.timer run hasn't happened) must read as
        'nothing to show', never a false 'failed'."""
        import dashboard
        original_store = dashboard.opportunity_store
        original_results_file = dashboard.REMEDIATION_RESULTS_FILE
        store = OpportunityStore(self.tmpdir)
        dashboard.opportunity_store = store
        dashboard.REMEDIATION_RESULTS_FILE = self.tmpdir / "remediation_results.jsonl"
        try:
            store.create_new(title="Awaiting next cycle", change_class="configuration",
                              discovery_source="internal", lifecycle_state="approved",
                              source_finding_id="FND-003")
            client = dashboard.app.test_client()
            res = client.get("/api/opportunities")
            opp = res.get_json()["opportunities"][0]
            self.assertNotIn("remediation_status", opp)
        finally:
            dashboard.opportunity_store = original_store
            dashboard.REMEDIATION_RESULTS_FILE = original_results_file

    def test_mission_dispatch_status_endpoint_surfaces_pr_url(self):
        import dashboard
        original_log_file = dashboard.MISSION_DISPATCH_LOG_FILE
        dashboard.MISSION_DISPATCH_LOG_FILE = self.tmpdir / "mission_dispatch_log.jsonl"
        try:
            dashboard.MISSION_DISPATCH_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(dashboard.MISSION_DISPATCH_LOG_FILE, "a") as f:
                f.write(json.dumps({
                    "timestamp": "2026-09-06T12:00:00+00:00",
                    "mission_id": "MSN-9001",
                    "success": True,
                    "message": "Draft PR opened for review: https://github.com/x/y/pull/3",
                }) + "\n")
            client = dashboard.app.test_client()
            res = client.get("/api/mission-dispatch-status")
            body = res.get_json()
            self.assertEqual(body["dispatches"]["MSN-9001"]["pr_url"], "https://github.com/x/y/pull/3")
            self.assertTrue(body["dispatches"]["MSN-9001"]["success"])
        finally:
            dashboard.MISSION_DISPATCH_LOG_FILE = original_log_file

    def test_mission_dispatch_status_endpoint_empty_when_no_log_yet(self):
        import dashboard
        original_log_file = dashboard.MISSION_DISPATCH_LOG_FILE
        dashboard.MISSION_DISPATCH_LOG_FILE = self.tmpdir / "no_such_log.jsonl"
        try:
            client = dashboard.app.test_client()
            res = client.get("/api/mission-dispatch-status")
            self.assertEqual(res.get_json(), {"dispatches": {}})
        finally:
            dashboard.MISSION_DISPATCH_LOG_FILE = original_log_file


if __name__ == "__main__":
    unittest.main()
