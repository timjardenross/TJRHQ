"""
Regression tests for the 2026-09-06 pr_error surfacing fix in
core/engineering/batch_coding.py's run_sync_one().

Root cause: when open_files_pr() (whole-file mode) returned opened=False,
its rich `reason`/`detail` (git_failed, pr_api_403, no_files_written, ...)
was only logged, never put anywhere the caller could see it —
auto_remediation.py's HandoffPRStrategy only inspects run_sync_one's JSON
stdout, so every real PR-open failure was indistinguishable from "GitHub
not configured", the one case its old generic message actually named.
Confirmed live: GITHUB_TOKEN/GITHUB_REPO were both configured and the
proposed file was genuinely new, yet the same generic message appeared —
the true cause (a git-level failure before the push ever reached GitHub)
was invisible anywhere.

Never touches real Mistral/GitHub — batch_api.complete and _open_files_pr
are both mocked. Dotted-path import convention matches the rest of
core/engineering/*.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.engineering import batch_coding  # noqa: E402

_FILE_RESPONSE = (
    "I'll add the exclusion patterns.\n\n"
    "FILE: tools/intelligence/filesystem_audit_config.py\n"
    "```python\n"
    "EXCLUDE_PATTERNS = [r'.*\\.venv($|/)']\n"
    "```\n"
)


def write_pending_handoff(handoffs_dir: Path, handoff_id: str) -> Path:
    handoffs_dir.mkdir(parents=True, exist_ok=True)
    path = handoffs_dir / f"{handoff_id}.md"
    path.write_text(
        "- Status: APPROVED_FOR_ENGINEERING\n"
        "- Batch Status: PENDING\n"
        f"- Mission ID: {handoff_id}\n"
        "\n## Mission Title\nTest handoff\n"
        "\n## Summary\nTest summary\n",
        encoding="utf-8",
    )
    return path


class TestRunSyncOnePrErrorSurfacing(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.handoffs_dir = self.tmpdir / "Missions" / "Engineering-Handoffs"
        self.handoff_path = write_pending_handoff(self.handoffs_dir, "ENG-HANDOFF-TEST-001")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, open_files_pr_result):
        with patch.object(batch_coding, "_ensure_env"), \
             patch.object(batch_coding.batch_api, "complete", return_value=_FILE_RESPONSE), \
             patch.object(batch_coding, "_open_files_pr", return_value=open_files_pr_result):
            return batch_coding.run_sync_one(self.handoff_path, client=MagicMock())

    def test_git_failure_reason_and_detail_surface_in_pr_error(self):
        result = self._run({"opened": False, "reason": "git_failed", "detail": "push rejected"})
        self.assertEqual(result["status"], "delivered")
        self.assertEqual(result["pr_url"], "")
        self.assertEqual(result["pr_error"], "git_failed: push rejected")

    def test_reason_without_detail_is_not_padded_with_none(self):
        result = self._run({"opened": False, "reason": "no_files_written", "skipped": []})
        self.assertEqual(result["pr_error"], "no_files_written")
        self.assertNotIn("None", result["pr_error"])

    def test_pr_api_failure_reason_surfaces(self):
        result = self._run({"opened": False, "reason": "pr_api_403", "detail": "Resource not accessible"})
        self.assertEqual(result["pr_error"], "pr_api_403: Resource not accessible")

    def test_successful_pr_open_leaves_pr_error_empty(self):
        result = self._run({
            "opened": True, "url": "https://github.com/x/y/pull/1", "branch": "mistral/test",
        })
        self.assertEqual(result["pr_url"], "https://github.com/x/y/pull/1")
        self.assertEqual(result["pr_error"], "")

    def test_missing_reason_key_never_raises(self):
        """Defence in depth: even a malformed open_files_pr() result must
        never crash run_sync_one — it should still report status=delivered
        with some pr_error string, not throw."""
        result = self._run({"opened": False})
        self.assertEqual(result["status"], "delivered")
        self.assertEqual(result["pr_error"], "unknown")


if __name__ == "__main__":
    unittest.main()
