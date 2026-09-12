"""
Regression test for USS-TJR-MSN-0047 (lightweight code review process).

batch_coding.py's auto-generated handoff PRs (_open_files_pr, _maybe_open_pr)
pass an explicit `body=` to the GitHub API — GitHub never applies
.github/pull_request_template.md to a PR opened this way, so the review
checklist has to be folded into the generated body directly or an
auto-handoff PR never sees it. Confirms both body templates actually include
the reminder, and that the checklist file it points at exists and is real
(not the old 3-line stub).

Never touches real GitHub — github_pr.open_files_pr / open_draft_pr are both
mocked so only the constructed body is inspected.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.engineering import batch_coding

_CHECKLIST_PATH = REPO_ROOT / "specialists" / "knowledge-packs" / "Code-Review-Checklist.md"
_PR_TEMPLATE_PATH = REPO_ROOT / ".github" / "pull_request_template.md"


class TestReviewChecklistWiredIntoHandoffPRs(unittest.TestCase):
    def _env(self):
        return patch.object(batch_coding, "_env_value", side_effect=lambda k: {
            "GITHUB_TOKEN": "test-token", "GITHUB_REPO": "example/repo",
        }.get(k, ""))

    def test_open_files_pr_body_references_checklist(self):
        with self._env(), patch.object(
            batch_coding.github_pr, "open_files_pr", return_value={"opened": True, "url": "x", "branch": "y"},
        ) as mock_open:
            batch_coding._open_files_pr("ENG-HANDOFF-TEST", {"a.py": "x = 1\n"}, {})
        body = mock_open.call_args.kwargs["body"]
        self.assertIn("Code-Review-Checklist.md", body)

    def test_maybe_open_pr_body_references_checklist(self):
        diff = (
            "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
            "@@ -0,0 +1 @@\n+x = 1\n"
        )
        with self._env(), patch.object(
            batch_coding.github_pr, "open_draft_pr", return_value={"opened": True, "url": "x", "branch": "y"},
        ) as mock_open:
            batch_coding._maybe_open_pr("ENG-HANDOFF-TEST", diff, {})
        body = mock_open.call_args.kwargs["body"]
        self.assertIn("Code-Review-Checklist.md", body)

    def test_checklist_file_exists_and_is_not_the_old_stub(self):
        self.assertTrue(_CHECKLIST_PATH.exists())
        content = _CHECKLIST_PATH.read_text(encoding="utf-8")
        self.assertGreater(len(content.splitlines()), 3)
        self.assertIn("USS-TJR-MSN-0047", content)

    def test_pr_template_exists_and_references_checklist(self):
        self.assertTrue(_PR_TEMPLATE_PATH.exists())
        content = _PR_TEMPLATE_PATH.read_text(encoding="utf-8")
        self.assertIn("Code-Review-Checklist.md", content)


if __name__ == "__main__":
    unittest.main()
