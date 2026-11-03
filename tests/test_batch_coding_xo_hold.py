"""
When XO reviews a proposed edit to an existing file and says Hold (and no PR
opened), run_sync_one stamps the handoff HELD so it leaves the active queue
instead of asking the Captain to "sign off" on something XO already rejected.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.coordination import engineering_handoff_reader as reader
from core.engineering import batch_coding
from tests.test_batch_coding_pr_error import (
    _FILE_RESPONSE,
    write_pending_handoff,
)


class TestXoHoldStamping(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.dir = self.tmpdir / "Missions" / "Engineering-Handoffs"
        self.path = write_pending_handoff(self.dir, "ENG-HANDOFF-TEST-HOLD")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, pr_result):
        with patch.object(batch_coding, "_ensure_env"), \
             patch.object(batch_coding.batch_api, "complete", return_value=_FILE_RESPONSE), \
             patch.object(batch_coding, "_open_files_pr", return_value=pr_result):
            return batch_coding.run_sync_one(self.path, client=MagicMock())

    def _batch_status(self):
        return reader._parse_handoff_file(self.path)["batch_status"]

    def test_hold_with_no_pr_is_stamped_held_and_leaves_the_queue(self):
        result = self._run({"opened": False, "reason": "all_existing_deferred",
                            "deferred_review": {"verdict": "hold", "reasoning": "truncates .gitignore"}})
        self.assertEqual(result["status"], "held")
        self.assertEqual(self._batch_status(), "HELD")
        self.assertIsNone(reader.derive_engineering_status(self._batch_status()))

    def test_approve_verdict_stays_delivered(self):
        result = self._run({"opened": False, "reason": "x",
                            "deferred_review": {"verdict": "approve", "reasoning": "fine"}})
        self.assertEqual(result["status"], "delivered")
        self.assertEqual(self._batch_status(), "DELIVERED")

    def test_hold_but_a_pr_opened_stays_delivered(self):
        # The PR has its own /merge_pr gate and verdict comment.
        result = self._run({"opened": True, "url": "https://github.com/o/r/pull/1", "branch": "b",
                            "deferred_review": {"verdict": "hold", "reasoning": "r"}})
        self.assertEqual(result["status"], "delivered")
        self.assertEqual(self._batch_status(), "DELIVERED")

    def test_no_deferred_review_stays_delivered(self):
        result = self._run({"opened": False, "reason": "github_not_configured"})
        self.assertEqual(result["status"], "delivered")


if __name__ == "__main__":
    unittest.main()
