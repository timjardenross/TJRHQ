"""
Regression tests for the 2026-09-06 evidence_strength backfill in
scripts/self_improvement/orchestrator.py's Phase 3 classification loop.

Root cause: the Model Router's analysis schema never returns an
evidence_strength field on a finding, so policy.py's
_determine_automation_eligibility() always read finding.get(
"evidence_strength", "weak") and got the "weak" default — silently
downgrading every finding whose category requires more than "weak"
evidence to needs_more_evidence, regardless of how high the model's own
confidence was. Found live in production: two findings at confidence
0.95/0.92 (config_drift/governance_violation, both requiring
moderate/strong evidence) were both downgraded, meaning neither the
original strict auto_remediation gate nor the newer PR-drafting gate
(scripts/self_improvement/auto_remediation.py's should_remediate_via_pr())
could ever admit anything this pipeline classifies.

Fix backfills evidence_strength from confidence using the same mapping
internal_discovery.py already relies on for this exact finding shape
(promoted from that module's private helper to
confidence_to_evidence_strength() so orchestrator.py can reuse it too,
rather than duplicating the thresholds).

Never touches real data/self-improvement/ — every test uses a scratch
tmpdir as data_root. Uses the real, current config/self_improvement_policy.json
(repo_root's own PolicyEngine construction) rather than a fabricated
policy file, so this test fails if the real category rules for
config_drift ever change in a way that would break this fix's assumptions.

Bare-sibling-import convention matches the other scripts/self_improvement
test files — see test_hq_evolution.py's own module docstring for why.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))

from orchestrator import SelfImprovementOrchestrator  # noqa: E402
from internal_discovery import confidence_to_evidence_strength  # noqa: E402


def make_raw_finding(**overrides):
    base = {
        "category": "config_drift",
        "title": "Duplicate self-improvement policy configuration formats",
        "evidence": [{"type": "config_value", "observation": "test", "location": "config/x.json"}],
        "confidence": 0.95,
        "severity": "medium",
        "proposed_action": {"type": "consolidate", "description": "test"},
        "expected_benefit": "test",
    }
    base.update(overrides)
    return base


class TestConfidenceToEvidenceStrengthMapping(unittest.TestCase):
    def test_conclusive_at_point_nine_and_above(self):
        self.assertEqual(confidence_to_evidence_strength(0.95), "conclusive")
        self.assertEqual(confidence_to_evidence_strength(0.9), "conclusive")

    def test_weak_below_point_six(self):
        self.assertEqual(confidence_to_evidence_strength(0.3), "weak")


class TestOrchestratorEvidenceStrengthBackfill(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.data_root = self.tmpdir / "data"
        self.orch = SelfImprovementOrchestrator(REPO_ROOT, self.data_root)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, findings):
        with patch.object(self.orch.collector, "collect_all", return_value=[{"section": "test", "data": {}}]), \
             patch.object(self.orch.router, "health_check", return_value=True), \
             patch.object(self.orch.router, "analyse_evidence", return_value={"success": True, "findings": findings}), \
             patch.object(self.orch.executor, "git_commit", return_value=None):
            return self.orch.run_full_cycle(dry_run=True, remediate=False)

    def _classified_findings(self, summary):
        run_dir = self.data_root / "runs" / summary["run_id"]
        return json.loads((run_dir / "findings_classified.json").read_text())["findings"]

    def test_high_confidence_finding_reaches_needs_signoff_not_needs_more_evidence(self):
        """The exact live bug: confidence 0.95 on a config_drift finding
        (evidence_required=moderate, default eligibility=needs_signoff)
        must no longer be silently downgraded to needs_more_evidence."""
        summary = self._run([make_raw_finding(confidence=0.95, category="config_drift")])
        classified = self._classified_findings(summary)
        self.assertEqual(len(classified), 1)
        self.assertEqual(classified[0]["evidence_strength"], "conclusive")
        self.assertEqual(classified[0]["automation_eligibility"], "needs_signoff")

    def test_governance_violation_at_high_confidence_also_reaches_needs_signoff(self):
        """governance_violation requires 'strong' evidence — the other
        live-observed case, confidence 0.92."""
        summary = self._run([make_raw_finding(confidence=0.92, category="governance_violation")])
        classified = self._classified_findings(summary)
        self.assertEqual(classified[0]["evidence_strength"], "conclusive")
        self.assertEqual(classified[0]["automation_eligibility"], "needs_signoff")

    def test_genuinely_low_confidence_finding_still_correctly_needs_more_evidence(self):
        """The backfill must not make PolicyEngine's evidence check a
        no-op — a real low-confidence finding must still be downgraded."""
        summary = self._run([make_raw_finding(confidence=0.3, category="config_drift")])
        classified = self._classified_findings(summary)
        self.assertEqual(classified[0]["evidence_strength"], "weak")
        self.assertEqual(classified[0]["automation_eligibility"], "needs_more_evidence")

    def test_evidence_strength_explicitly_provided_by_the_model_is_not_overridden(self):
        """setdefault() must never clobber a value the model actually did
        provide — the backfill is a fallback, not a forced recompute."""
        summary = self._run([make_raw_finding(confidence=0.1, evidence_strength="conclusive")])
        classified = self._classified_findings(summary)
        self.assertEqual(classified[0]["evidence_strength"], "conclusive")
        self.assertEqual(classified[0]["automation_eligibility"], "needs_signoff")


if __name__ == "__main__":
    unittest.main()
