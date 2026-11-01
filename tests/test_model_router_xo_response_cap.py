"""xo-response must not keep generating long after its client has given up."""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "model-router"))
sys.path.insert(0, str(REPO_ROOT))

import app

CLIENT_TIMEOUT_SECONDS = 20  # telegram-bots/llm.py _ROUTER_TIMEOUT


class XoResponseCapTest(unittest.TestCase):
    def test_server_timeout_is_just_above_the_client_timeout(self):
        t = app.TASK_POLICY["xo-response"]["timeout"]
        self.assertGreaterEqual(t, CLIENT_TIMEOUT_SECONDS)
        self.assertLessEqual(t, 30)

    def test_generation_is_bounded(self):
        self.assertLessEqual(app.TASK_POLICY["xo-response"].get("num_predict", 10**6), 600)

    def test_other_tasks_keep_their_long_timeouts(self):
        self.assertEqual(app.TASK_POLICY["classify-document"]["timeout"], 300)


if __name__ == "__main__":
    unittest.main()
