"""
Tests for the diff-scoped defect checklists appended to the XO engineering
review prompt (core/engineering/xo_review.py): the silent-failure list always
applies, Python/TypeScript lists only when the diff touches those files, and
the verbatim gatekeeper rubric is left intact.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.engineering import xo_review

PY_DIFF = (
    "diff --git a/core/x.py b/core/x.py\n--- a/core/x.py\n+++ b/core/x.py\n"
    "@@ -1 +1 @@\n-a = 1\n+a = 2\n"
)
TS_NEW_FILE_DIFF = (
    "diff --git a/lcars-portal/src/a.tsx b/lcars-portal/src/a.tsx\n--- /dev/null\n"
    "+++ b/lcars-portal/src/a.tsx\n@@ -0,0 +1 @@\n+export const A = 1;\n"
)
REQ_DIFF = (
    "--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1 @@\n-openai==1.0\n+openai==1.1\n"
)


class TestDiffPaths(unittest.TestCase):
    def test_strips_prefixes_and_dev_null(self):
        self.assertEqual(xo_review._diff_paths(PY_DIFF), ["core/x.py"])
        self.assertEqual(xo_review._diff_paths(TS_NEW_FILE_DIFF), ["lcars-portal/src/a.tsx"])


class TestChecklistSelection(unittest.TestCase):
    def test_python_diff_gets_python_and_silent_failure(self):
        text = xo_review._checklists_for_diff(PY_DIFF)
        self.assertIn("SILENT FAILURES", text)
        self.assertIn("PYTHON:", text)
        self.assertNotIn("TYPESCRIPT", text)

    def test_typescript_diff_gets_typescript(self):
        text = xo_review._checklists_for_diff(TS_NEW_FILE_DIFF)
        self.assertIn("TYPESCRIPT", text)
        self.assertNotIn("PYTHON:", text)

    def test_version_bump_diff_gets_silent_failure_only(self):
        text = xo_review._checklists_for_diff(REQ_DIFF)
        self.assertIn("SILENT FAILURES", text)
        self.assertNotIn("PYTHON:", text)
        self.assertNotIn("TYPESCRIPT", text)


class TestPromptShape(unittest.TestCase):
    def test_rubric_intact_and_checklists_before_diff(self):
        prompt = xo_review._build_review_prompt(diff=PY_DIFF, mission_title="t", mission_summary="s")
        self.assertTrue(prompt.startswith(xo_review._XO_GATEKEEPER_RUBRIC))
        self.assertLess(prompt.index("DEFECT CHECKLISTS"), prompt.index("DIFF UNDER REVIEW"))
        # Output contract unchanged: same four JSON keys requested.
        self.assertIn('{"verdict": "approve|approve_with_changes|hold"', prompt)


if __name__ == "__main__":
    unittest.main()
