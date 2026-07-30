"""
Tests for the self-improvement system.

Tests:
- Evidence collection (deterministic, reproducible)
- Schema validation (findings match contract)
- Policy engine (correct classification)
- Router client (error handling)
- Safety constraints (fail-closed)

Uses stdlib unittest (no external dependencies).
"""

import json
import unittest
from pathlib import Path
import sys

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.self_improvement.collector import EvidenceCollector
from scripts.self_improvement.policy import PolicyEngine, classify_findings
from scripts.self_improvement.router_client import ModelRouterClient


class TestEvidenceCollector(unittest.TestCase):
    """Test evidence collection (deterministic)."""

    def test_collect_returns_dict(self):
        """Evidence collection should return a dict."""
        collector = EvidenceCollector()
        evidence = collector.collect_all()
        self.assertIsInstance(evidence, dict)

    def test_evidence_has_required_fields(self):
        """Evidence should have all required top-level fields."""
        collector = EvidenceCollector()
        evidence = collector.collect_all()
        required = ["collection_timestamp", "repository_state", "filesystem_audit"]
        for field in required:
            self.assertIn(field, evidence)

    def test_repository_state_has_required_fields(self):
        """Repository state should have git info."""
        collector = EvidenceCollector()
        evidence = collector.collect_all()
        repo_state = evidence["repository_state"]
        required = ["branch", "commit", "dirty", "repo_root"]
        for field in required:
            self.assertIn(field, repo_state)

    def test_repository_state_branch_not_empty(self):
        """Branch name should be populated."""
        collector = EvidenceCollector()
        evidence = collector.collect_all()
        self.assertTrue(evidence["repository_state"]["branch"])

    def test_repository_state_commit_looks_like_sha(self):
        """Commit hash should look like a git SHA."""
        collector = EvidenceCollector()
        evidence = collector.collect_all()
        commit = evidence["repository_state"]["commit"]
        self.assertIsNotNone(commit)
        self.assertGreaterEqual(len(commit), 7)

    def test_filesystem_audit_has_python_files(self):
        """Should detect Python files."""
        collector = EvidenceCollector()
        evidence = collector.collect_all()
        python_count = evidence["filesystem_audit"]["python_files"]
        self.assertGreater(python_count, 100)

    def test_filesystem_audit_has_test_files(self):
        """Should detect test files."""
        collector = EvidenceCollector()
        evidence = collector.collect_all()
        test_files = evidence["filesystem_audit"]["test_files"]
        self.assertGreater(len(test_files), 0)

    def test_model_router_audit_sections_exist(self):
        """Model Router audit should have expected sections."""
        collector = EvidenceCollector()
        evidence = collector.collect_all()
        router_audit = evidence["model_router_audit"]
        expected = ["configured_routes", "router_reachable", "router_status"]
        for field in expected:
            self.assertIn(field, router_audit)

    def test_collection_is_deterministic(self):
        """Two consecutive collections should produce same structure."""
        collector = EvidenceCollector()
        e1 = collector.collect_all()
        e2 = collector.collect_all()

        # Should have same top-level keys
        self.assertEqual(set(e1.keys()), set(e2.keys()))

        # Repo state should be identical (same commit, branch)
        self.assertEqual(e1["repository_state"]["commit"], e2["repository_state"]["commit"])
        self.assertEqual(e1["repository_state"]["branch"], e2["repository_state"]["branch"])


class TestPolicyEngine(unittest.TestCase):
    """Test policy classification (deterministic rules)."""

    @classmethod
    def setUpClass(cls):
        """Load policy file once."""
        cls.policy_file = Path("config/self_improvement_policy.json")
        if cls.policy_file.exists():
            cls.engine = PolicyEngine(cls.policy_file)
        else:
            cls.engine = None

    def test_policy_engine_loads_config(self):
        """Policy engine should load config file."""
        if self.engine:
            self.assertIsNotNone(self.engine.config)
            self.assertIn("categories", self.engine.config)

    def test_classify_finding_adds_required_fields(self):
        """Classification should add automation_eligibility and risk_level."""
        if not self.engine:
            self.skipTest("Policy file not found")

        finding = {
            "finding_id": "f_test_001",
            "category": "doc_drift",
            "title": "Test finding",
            "evidence_strength": "conclusive",
            "confidence": 0.99,
            "severity": "low",
        }

        classified = self.engine.classify_finding(finding)
        self.assertIn("automation_eligibility", classified)
        self.assertIn("risk_level", classified)
        self.assertIn("policy_decision_rationale", classified)

    def test_low_confidence_requires_more_evidence(self):
        """Finding with low confidence should request more evidence."""
        if not self.engine:
            self.skipTest("Policy file not found")

        finding = {
            "finding_id": "f_test_low_conf",
            "category": "dead_code",
            "title": "Potential dead code",
            "evidence_strength": "weak",
            "confidence": 0.5,
            "severity": "low",
        }

        classified = self.engine.classify_finding(finding)
        self.assertIn(classified["automation_eligibility"], ["needs_more_evidence", "needs_signoff"])

    def test_placeholder_code_needs_signoff(self):
        """placeholder_code should always need signoff."""
        if not self.engine:
            self.skipTest("Policy file not found")

        finding = {
            "finding_id": "f_test_placeholder",
            "category": "placeholder_code",
            "title": "TODO in production code",
            "evidence_strength": "conclusive",
            "confidence": 0.99,
            "severity": "medium",
        }

        classified = self.engine.classify_finding(finding)
        self.assertEqual(classified["automation_eligibility"], "needs_signoff")


class TestRouterClient(unittest.TestCase):
    """Test Model Router client (error handling)."""

    def test_router_client_init(self):
        """Client should initialize."""
        client = ModelRouterClient()
        self.assertEqual(client.base_url, "http://127.0.0.1:8891")

    def test_router_client_health_check_returns_bool(self):
        """Health check should return boolean."""
        client = ModelRouterClient()
        result = client.health_check()
        self.assertIsInstance(result, bool)

    def test_router_client_has_call_log(self):
        """Client should maintain a call log."""
        client = ModelRouterClient()
        self.assertTrue(hasattr(client, "call_log"))
        self.assertIsInstance(client.call_log, list)


class TestFindingSchema(unittest.TestCase):
    """Test finding schema validation."""

    def test_finding_schema_exists(self):
        """Finding schema file should exist."""
        schema_file = Path("schemas/self_improvement_finding.schema.json")
        self.assertTrue(schema_file.exists())

    def test_finding_schema_is_valid_json(self):
        """Schema should be valid JSON."""
        schema_file = Path("schemas/self_improvement_finding.schema.json")
        with open(schema_file) as f:
            schema = json.load(f)
        self.assertIsInstance(schema, dict)
        self.assertIn("$schema", schema)

    def test_policy_schema_exists(self):
        """Policy schema/config file should exist."""
        policy_file = Path("config/self_improvement_policy.json")
        self.assertTrue(policy_file.exists())

    def test_policy_is_valid_json(self):
        """Policy config should be valid JSON."""
        policy_file = Path("config/self_improvement_policy.json")
        with open(policy_file) as f:
            config = json.load(f)
        self.assertIsInstance(config, dict)
        self.assertIn("categories", config)


class TestSafetyConstraints(unittest.TestCase):
    """Test fail-closed safety constraints."""

    def test_policy_has_fail_closed_conditions(self):
        """Policy should define fail-closed conditions."""
        policy_file = Path("config/self_improvement_policy.json")
        if not policy_file.exists():
            self.skipTest("Policy file not found")

        with open(policy_file) as f:
            config = json.load(f)

        self.assertIn("safety", config)
        self.assertIn("fail_closed_conditions", config["safety"])
        conditions = config["safety"]["fail_closed_conditions"]
        self.assertGreater(len(conditions), 0)
        self.assertIn("repository_dirty", conditions)

    def test_policy_forbids_dangerous_actions(self):
        """Policy should forbid dangerous auto-remediation actions."""
        policy_file = Path("config/self_improvement_policy.json")
        if not policy_file.exists():
            self.skipTest("Policy file not found")

        with open(policy_file) as f:
            config = json.load(f)

        forbidden = config["auto_remediation"]["forbidden_actions"]
        dangerous = ["delete_code", "modify_implementation", "commit_to_repo", "push_to_remote"]
        for action in dangerous:
            self.assertIn(action, forbidden)


class TestIntegration(unittest.TestCase):
    """Integration tests (full workflow)."""

    @classmethod
    def setUpClass(cls):
        """Load policy file once."""
        cls.policy_file = Path("config/self_improvement_policy.json")
        cls.engine = None
        if cls.policy_file.exists():
            cls.engine = PolicyEngine(cls.policy_file)

    def test_collect_then_classify_workflow(self):
        """Can collect evidence and classify findings."""
        if not self.engine:
            self.skipTest("Policy file not found")

        # Collect
        collector = EvidenceCollector()
        evidence = collector.collect_all()
        self.assertIsNotNone(evidence["repository_state"]["commit"])

        # Synthesize a test finding (simulating what Model Router would produce)
        test_finding = {
            "finding_id": "f_integration_001",
            "category": "doc_drift",
            "title": "Test integration finding",
            "evidence_strength": "conclusive",
            "confidence": 0.95,
            "severity": "low",
        }

        # Classify
        classified = classify_findings([test_finding], self.policy_file)
        self.assertEqual(len(classified), 1)
        self.assertIn("automation_eligibility", classified[0])


if __name__ == "__main__":
    unittest.main()
