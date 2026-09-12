"""
Tests for scripts/self_improvement/staleness_check.py — the deterministic
re-check that answers "why is this finding still open if it was already
fixed outside the pipeline" without ever guessing or auto-closing anything.

Same bare-sibling-import convention as test_hq_evolution.py.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))

import staleness_check


def make_finding(**overrides):
    base = {
        "finding_id": "FND-001",
        "title": "Deprecated directory persists",
        "evidence": [{"type": "file_exists", "observation": "still there", "location": "some/dir"}],
    }
    base.update(overrides)
    return base


class TestCheckEvidenceItem(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_file_exists_claim_confirmed_when_path_present(self):
        (self.tmpdir / "still-here.txt").write_text("x")
        item = {"type": "file_exists", "location": "still-here.txt"}
        result = staleness_check.check_evidence_item(item, self.tmpdir, set())
        self.assertEqual(result["status"], "confirmed")

    def test_file_exists_claim_resolved_when_path_gone(self):
        item = {"type": "file_exists", "location": "never-existed.txt"}
        result = staleness_check.check_evidence_item(item, self.tmpdir, set())
        self.assertEqual(result["status"], "resolved")

    def test_dead_code_treated_same_as_file_exists(self):
        item = {"type": "unreferenced_code", "location": "gone-already.py"}
        result = staleness_check.check_evidence_item(item, self.tmpdir, set())
        self.assertEqual(result["status"], "resolved")

    def test_file_missing_claim_confirmed_while_still_absent(self):
        item = {"type": "file_missing", "location": "docs/still-missing.md"}
        result = staleness_check.check_evidence_item(item, self.tmpdir, set())
        self.assertEqual(result["status"], "confirmed")

    def test_file_missing_claim_resolved_once_it_exists(self):
        (self.tmpdir / "docs").mkdir()
        (self.tmpdir / "docs" / "now-exists.md").write_text("x")
        item = {"type": "file_missing", "location": "docs/now-exists.md"}
        result = staleness_check.check_evidence_item(item, self.tmpdir, set())
        self.assertEqual(result["status"], "resolved")

    def test_git_history_claim_confirmed_while_path_still_dirty(self):
        item = {"type": "git_history", "location": "data/self-improvement/review/.evolution_cycle.lock"}
        dirty = {"data/self-improvement/review/.evolution_cycle.lock"}
        result = staleness_check.check_evidence_item(item, self.tmpdir, dirty)
        self.assertEqual(result["status"], "confirmed")

    def test_git_history_claim_resolved_once_no_longer_dirty(self):
        item = {"type": "git_history", "location": "data/self-improvement/review/.evolution_cycle.lock"}
        result = staleness_check.check_evidence_item(item, self.tmpdir, set())
        self.assertEqual(result["status"], "resolved")

    def test_config_value_never_guessed(self):
        """config_value/service_status/etc. require re-running the original
        detection logic (a live probe) — this module must never guess
        either direction from a bare location string."""
        item = {"type": "config_value", "location": "core/model-router"}
        result = staleness_check.check_evidence_item(item, self.tmpdir, set())
        self.assertEqual(result["status"], "unclear")

    def test_location_escaping_repo_root_is_unclear_not_an_error(self):
        item = {"type": "file_exists", "location": "../../etc/passwd"}
        result = staleness_check.check_evidence_item(item, self.tmpdir, set())
        self.assertEqual(result["status"], "unclear")


class TestCheckFindingStaleness(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q"], cwd=self.tmpdir, check=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_evidence_is_unclear(self):
        finding = make_finding(evidence=[])
        result = staleness_check.check_finding_staleness(finding, self.tmpdir)
        self.assertEqual(result["status"], "unclear")

    def test_all_resolved_evidence_yields_resolved_overall(self):
        finding = make_finding(evidence=[
            {"type": "file_exists", "location": "gone-a.txt"},
            {"type": "unreferenced_code", "location": "gone-b.py"},
        ])
        result = staleness_check.check_finding_staleness(finding, self.tmpdir)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(len(result["items"]), 2)

    def test_any_confirmed_evidence_keeps_overall_confirmed(self):
        (self.tmpdir / "still-here.txt").write_text("x")
        finding = make_finding(evidence=[
            {"type": "file_exists", "location": "still-here.txt"},
            {"type": "file_exists", "location": "gone-b.txt"},
        ])
        result = staleness_check.check_finding_staleness(finding, self.tmpdir)
        self.assertEqual(result["status"], "confirmed")

    def test_mixed_resolved_and_unclear_is_unclear_not_resolved(self):
        """A finding must never read as 'resolved' unless EVERY evidence
        item independently confirms it — one unclear item (something this
        module can't verify) is enough to withhold that signal, matching
        the never-guess contract."""
        finding = make_finding(evidence=[
            {"type": "file_exists", "location": "gone-a.txt"},
            {"type": "config_value", "location": "core/model-router"},
        ])
        result = staleness_check.check_finding_staleness(finding, self.tmpdir)
        self.assertEqual(result["status"], "unclear")


if __name__ == "__main__":
    unittest.main()
