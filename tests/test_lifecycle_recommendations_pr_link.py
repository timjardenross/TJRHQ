"""
Tests for the 2026-09-06 "one-click PR link" fix to the Gate-2 XO-to-Captain
lifecycle-recommendations Telegram notification (MSN-0066):
intelligence/proactive_cadences.py's job_lifecycle_recommendations().

Previously each review-item line only ever showed a bare handoff ID and the
literal string "Captain — review/merge the PR" — no link at all, even
though core/coordination/pending_actions.py's payload now carries pr_url
(threaded through delivery_reconciler.py -> lifecycle_reconciler.py). The
Captain had to leave the notification and manually find the right PR on
GitHub every time.

Slack (platform-runtime/proactive_scheduler.py) is deliberately out of
scope — this platform doesn't use it for this notification, so only the
Telegram path was fixed.

Never touches real Telegram — build_pending_actions and the actual notify
call are mocked in every test. The job is double-gated behind
LIFECYCLE_RECS_ENABLED (default off); tests set it explicitly.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import intelligence.proactive_cadences as tg_cadences  # noqa: E402


def make_payload(pr_url: str | None):
    review_item = {"id": "ENG-HANDOFF-SD-FND-001-20260906124944", "next_actor": "Captain — review/merge the PR"}
    if pr_url is not None:
        review_item["pr_url"] = pr_url
    return {"totals": {"awaiting_approval": 0, "review": 1}, "awaiting_approval": [], "review": [review_item]}


class TestTelegramLifecycleRecommendationsPrLink(unittest.TestCase):
    def _run(self, pr_url):
        payload = make_payload(pr_url)
        with patch.dict(os.environ, {"LIFECYCLE_RECS_ENABLED": "true"}), \
             patch("core.coordination.pending_actions.build_pending_actions", return_value=payload), \
             patch.object(tg_cadences, "_tg_notify", return_value=True) as mock_notify, \
             patch.object(tg_cadences, "_shakedown_log"):
            tg_cadences.job_lifecycle_recommendations()
        return mock_notify.call_args[0][0]

    def test_pr_url_present_appears_on_its_own_line(self):
        text = self._run("https://github.com/timjardenross/TJRHQ/pull/56")
        self.assertIn("https://github.com/timjardenross/TJRHQ/pull/56", text)
        self.assertIn("ENG-HANDOFF-SD-FND-001-20260906124944", text)

    def test_no_pr_url_omits_link_line_without_crashing(self):
        text = self._run(None)
        self.assertNotIn("http", text)
        self.assertIn("Captain — review/merge the PR", text)


if __name__ == "__main__":
    unittest.main()
