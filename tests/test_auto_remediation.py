"""
Tests for scripts/self_improvement/auto_remediation.py's remediation-
eligibility gates, focused on the 2026-09-06 widening that lets
`needs_signoff` findings reach a draft-PR review path.

Core safety property under test: widening WHICH findings may be
remediated must never widen HOW a needs_signoff finding can be
remediated. It may only ever reach HandoffPRStrategy (opens a draft PR,
a human must merge it) — never DeleteFileStrategy/DocumentStrategy/
ObservabilityStrategy, which mutate the working tree directly and get
committed to main by execute() itself with no human review before the
commit lands. automation_eligibility remains PolicyEngine's sole
authority over the direct-commit path; this change only ever adds a
second, strictly narrower, PR-only path alongside it.

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

from auto_remediation import (  # noqa: E402
    AutoRemediationExecutor, DeleteFileStrategy, DocumentStrategy, ObservabilityStrategy, HandoffPRStrategy,
)


def make_finding(**overrides):
    base = {
        "finding_id": "FND-TEST-001",
        "title": "Test finding",
        "category": "observability_gap",
        "risk_level": "medium",
        "automation_eligibility": "needs_signoff",
        "evidence": [],
        "proposed_action": {"type": "monitor", "description": "test"},
    }
    base.update(overrides)
    return base


class TestShouldRemediateStrictGateUnchanged(unittest.TestCase):
    """The original, direct-commit-eligible gate must behave exactly as
    before this change — needs_signoff still never qualifies here."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.executor = AutoRemediationExecutor(REPO_ROOT, self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_needs_signoff_never_qualifies_for_direct_commit(self):
        finding = make_finding(risk_level="low", automation_eligibility="needs_signoff")
        self.assertFalse(self.executor.should_remediate(0.9, finding))

    def test_medium_risk_never_qualifies_for_direct_commit(self):
        finding = make_finding(risk_level="medium", automation_eligibility="auto_apply")
        self.assertFalse(self.executor.should_remediate(0.9, finding))

    def test_auto_apply_low_risk_high_confidence_still_qualifies(self):
        finding = make_finding(risk_level="low", automation_eligibility="auto_apply")
        self.assertTrue(self.executor.should_remediate(0.9, finding))


class TestShouldRemediateViaPr(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.executor = AutoRemediationExecutor(REPO_ROOT, self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_needs_signoff_at_medium_risk_qualifies_for_pr(self):
        finding = make_finding(risk_level="medium", automation_eligibility="needs_signoff")
        self.assertTrue(self.executor.should_remediate_via_pr(finding))

    def test_needs_signoff_at_low_risk_qualifies_for_pr(self):
        finding = make_finding(risk_level="low", automation_eligibility="needs_signoff")
        self.assertTrue(self.executor.should_remediate_via_pr(finding))

    def test_high_risk_never_qualifies_for_pr_even_with_needs_signoff(self):
        finding = make_finding(risk_level="high", automation_eligibility="needs_signoff")
        self.assertFalse(self.executor.should_remediate_via_pr(finding))

    def test_critical_risk_never_qualifies_for_pr(self):
        finding = make_finding(risk_level="critical", automation_eligibility="needs_signoff")
        self.assertFalse(self.executor.should_remediate_via_pr(finding))

    def test_needs_more_evidence_never_qualifies_for_pr(self):
        """needs_signoff is admitted by name — a distinct, weaker
        classification like needs_more_evidence must not slip in via the
        same widened gate."""
        finding = make_finding(risk_level="low", automation_eligibility="needs_more_evidence")
        self.assertFalse(self.executor.should_remediate_via_pr(finding))

    def test_manual_only_never_qualifies_for_pr(self):
        finding = make_finding(risk_level="low", automation_eligibility="manual_only")
        self.assertFalse(self.executor.should_remediate_via_pr(finding))

    def test_auto_apply_also_qualifies_for_pr_path(self):
        """The PR path is a superset for eligible-for-direct findings too
        (harmless — should_remediate() is checked first in execute() and
        wins whenever it applies)."""
        finding = make_finding(risk_level="low", automation_eligibility="auto_apply")
        self.assertTrue(self.executor.should_remediate_via_pr(finding))


class TestExecuteRoutingSafety(unittest.TestCase):
    """The critical end-to-end safety property: a needs_signoff finding
    whose category matches a narrow, direct-commit strategy must still be
    forced through HandoffPRStrategy — never the narrower one — because
    execute() bypasses get_remediation_strategy()'s normal narrowest-first
    search for anything not should_remediate()-eligible."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.run_dir = self.tmpdir / "runs" / "2026-09-06-000000"
        self.run_dir.mkdir(parents=True)
        (self.tmpdir / "review").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _seed(self, finding, decision="approved"):
        (self.run_dir / "findings_classified.json").write_text(json.dumps({"findings": [finding]}))
        (self.tmpdir / "review" / "decisions.jsonl").write_text(
            json.dumps({"finding_id": finding["finding_id"], "decision": decision}) + "\n"
        )

    def test_needs_signoff_observability_finding_never_reaches_observability_strategy(self):
        """category=observability_gap would normally match
        ObservabilityStrategy.can_remediate() first in the strategies list
        — confirm a needs_signoff finding is routed to pr_strategy instead,
        and ObservabilityStrategy.remediate() (a direct working-tree
        mutation) is never called at all."""
        finding = make_finding(category="observability_gap", risk_level="medium", automation_eligibility="needs_signoff")
        self._seed(finding)
        executor = AutoRemediationExecutor(REPO_ROOT, self.tmpdir)

        with patch.object(ObservabilityStrategy, "remediate") as mock_observability, \
             patch.object(executor.pr_strategy, "remediate", return_value={"success": True, "mode": "pr", "message": "Draft PR opened"}) as mock_pr:
            result = executor.execute(model_confidence=0.9, dry_run=False)

        mock_observability.assert_not_called()
        mock_pr.assert_called_once()
        self.assertEqual(result["remediated_count"], 1)
        self.assertEqual(result["failed_count"], 0)

    def test_needs_signoff_finding_never_produces_a_direct_mode_result(self):
        finding = make_finding(category="observability_gap", risk_level="medium", automation_eligibility="needs_signoff")
        self._seed(finding)
        executor = AutoRemediationExecutor(REPO_ROOT, self.tmpdir)

        with patch.object(executor.pr_strategy, "remediate", return_value={"success": True, "mode": "pr", "message": "Draft PR opened"}), \
             patch.object(executor, "git_commit") as mock_git_commit:
            executor.execute(model_confidence=0.9, dry_run=False)

        mock_git_commit.assert_not_called()

    def test_high_risk_needs_signoff_finding_is_skipped_entirely(self):
        finding = make_finding(category="observability_gap", risk_level="high", automation_eligibility="needs_signoff")
        self._seed(finding)
        executor = AutoRemediationExecutor(REPO_ROOT, self.tmpdir)

        with patch.object(ObservabilityStrategy, "remediate") as mock_observability, \
             patch.object(executor.pr_strategy, "remediate") as mock_pr:
            result = executor.execute(model_confidence=0.9, dry_run=False)

        mock_observability.assert_not_called()
        mock_pr.assert_not_called()
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(result["remediated_count"], 0)

    def test_auto_apply_dead_code_finding_still_uses_direct_strategy_unchanged(self):
        """Regression guard: the pre-existing, strict direct-commit path
        must still resolve to the narrow strategy first when a finding
        genuinely qualifies for it — the new PR path must never intercept
        an already-eligible finding."""
        finding = make_finding(category="dead_code", risk_level="low", automation_eligibility="auto_apply",
                                proposed_action={"type": "delete"}, evidence=[{"location": "x/y/__pycache__"}])
        self._seed(finding)
        executor = AutoRemediationExecutor(REPO_ROOT, self.tmpdir)

        with patch.object(DeleteFileStrategy, "remediate", return_value={"success": True, "mode": "direct", "message": "deleted"}) as mock_delete, \
             patch.object(executor.pr_strategy, "remediate") as mock_pr, \
             patch.object(executor, "git_commit", return_value="abc1234") as mock_git_commit, \
             patch.object(executor, "run_tests", return_value=True):
            result = executor.execute(model_confidence=0.9, dry_run=False)

        mock_delete.assert_called_once()
        mock_pr.assert_not_called()
        mock_git_commit.assert_called_once()
        self.assertEqual(result["remediated_count"], 1)

    def test_unapproved_needs_signoff_finding_is_never_touched(self):
        """No decision at all — never remediated via either path."""
        finding = make_finding(category="observability_gap", risk_level="medium", automation_eligibility="needs_signoff")
        (self.run_dir / "findings_classified.json").write_text(json.dumps({"findings": [finding]}))
        # No decisions.jsonl entry written at all.
        executor = AutoRemediationExecutor(REPO_ROOT, self.tmpdir)

        with patch.object(ObservabilityStrategy, "remediate") as mock_observability, \
             patch.object(executor.pr_strategy, "remediate") as mock_pr:
            result = executor.execute(model_confidence=0.9, dry_run=False)

        mock_observability.assert_not_called()
        mock_pr.assert_not_called()
        self.assertEqual(result["approved_count"], 0)


class TestHandoffPRStrategyMessageSurfacesRealReason(unittest.TestCase):
    """2026-09-06: sync-one's pr_error field (batch_coding.py's
    run_sync_one) now carries the real reason a PR wasn't opened, instead
    of the strategy always guessing "GitHub not configured or no new
    files to add" regardless of the actual cause — confirmed live: a
    fully-configured GITHUB_TOKEN/GITHUB_REPO and a genuinely new file
    still produced that exact guess, because the true cause (a git-level
    failure) was never surfaced anywhere."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.strategy = HandoffPRStrategy()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _remediate(self, sync_one_stdout: dict):
        fake_result = type("R", (), {
            "returncode": 0, "stdout": json.dumps(sync_one_stdout), "stderr": "",
        })()
        with patch("auto_remediation.subprocess.run", return_value=fake_result):
            return self.strategy.remediate(self.tmpdir, make_finding(finding_id="FND-999"))

    def test_real_pr_error_reason_replaces_the_old_generic_guess(self):
        result = self._remediate({
            "status": "delivered", "artifact": "artifacts/x.patch.md",
            "pr_url": "", "pr_error": "git_failed: push rejected",
        })
        self.assertIn("git_failed: push rejected", result["message"])
        self.assertNotIn("GitHub not configured or no new files to add", result["message"])

    def test_missing_pr_error_falls_back_to_old_generic_wording(self):
        """Backward compatible with an older sync-one or the diff-mode
        fallback path, neither of which sets pr_error."""
        result = self._remediate({
            "status": "delivered", "artifact": "artifacts/x.patch.md", "pr_url": "",
        })
        self.assertIn("GitHub not configured or no new files to add", result["message"])

    def test_successful_pr_open_still_reports_the_url_not_pr_error(self):
        result = self._remediate({
            "status": "delivered", "artifact": "artifacts/x.patch.md",
            "pr_url": "https://github.com/x/y/pull/1", "pr_error": "",
        })
        self.assertIn("https://github.com/x/y/pull/1", result["message"])
        self.assertNotIn("no PR opened", result["message"])


if __name__ == "__main__":
    unittest.main()
