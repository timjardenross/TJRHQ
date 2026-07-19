"""
Unit tests for Phase B crisis-mode governance actions (escalate / notify_telegram /
stand_down), their dispatcher wiring, and the governance dispatch CLI bridge.
Nothing sends live or hits the network (injected fakes / unknown-action paths).
"""

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.governance.workflow_gate import (
    ANALYST,
    EXECUTIVE_APPROVER,
    INTELLIGENCE_LEAD,
    AuthorizationError,
    NotFoundError,
)
from intelligence.workflow import api, cli, service
from intelligence.workflow.repository import InMemoryRepository


def _brief(repo, risk="AMBER", **extra):
    return repo.insert_brief({"period_start": "2026-07-05", "period_end": "2026-07-11",
                              "overall_risk": risk,
                              "executive_snapshot": "Telstra nationwide outage cascade.",
                              "signal_ids": ["e1", "e2", "e3"], **extra})["brief_id"]


class TestEscalate(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryRepository()

    def test_escalate_sets_red(self):
        bid = _brief(self.repo, risk="AMBER")
        out = service.escalate_brief(self.repo, INTELLIGENCE_LEAD, bid, reason="triple-zero impact")
        self.assertEqual(out["overall_risk"], "RED")

    def test_escalate_rbac(self):
        bid = _brief(self.repo)
        with self.assertRaises(AuthorizationError):
            service.escalate_brief(self.repo, ANALYST, bid)

    def test_escalate_missing(self):
        with self.assertRaises(NotFoundError):
            service.escalate_brief(self.repo, INTELLIGENCE_LEAD, "ghost")


class TestNotifyTelegram(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryRepository()
        os.environ["LCARS_PORTAL_URL"] = "https://portal.example"

    def test_payload_has_deeplink_button(self):
        bid = _brief(self.repo, risk="RED")
        payload = service.build_telegram_alert(self.repo.get_brief(bid))
        self.assertIn("VERIFY NOW", payload["button_label"])
        self.assertIn(f"/escalation/{bid}", payload["deep_link"])
        self.assertIn("alert_source=telegram", payload["deep_link"])
        self.assertIn("🔴", payload["text"])

    def test_notify_with_injected_sender(self):
        bid = _brief(self.repo, risk="RED")
        seen = {}
        def sender(p):
            seen.update(p)
            return True
        out = service.notify_telegram(self.repo, INTELLIGENCE_LEAD, bid, sender=sender)
        self.assertTrue(out["sent"])
        self.assertIn("deep_link", seen)

    def test_notify_sender_failure_never_raises(self):
        bid = _brief(self.repo, risk="RED")
        def boom(p):
            raise RuntimeError("telegram down")
        out = service.notify_telegram(self.repo, INTELLIGENCE_LEAD, bid, sender=boom)
        self.assertFalse(out["sent"])  # graceful

    def test_notify_rbac(self):
        bid = _brief(self.repo, risk="RED")
        with self.assertRaises(AuthorizationError):
            service.notify_telegram(self.repo, EXECUTIVE_APPROVER, bid, sender=lambda p: True)


class TestStandDown(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryRepository()

    def test_stand_down_with_lesson(self):
        bid = _brief(self.repo, risk="RED")
        out = service.stand_down(self.repo, INTELLIGENCE_LEAD, bid,
                                 lesson_text="add carrier-dependency watch", category="surprise")
        self.assertTrue(out["stood_down"])
        self.assertIsNotNone(out["lesson"])
        self.assertEqual(out["lesson"]["category"], "surprise")

    def test_stand_down_no_lesson(self):
        bid = _brief(self.repo, risk="RED")
        out = service.stand_down(self.repo, INTELLIGENCE_LEAD, bid)
        self.assertTrue(out["stood_down"])
        self.assertIsNone(out["lesson"])

    def test_stand_down_rbac(self):
        bid = _brief(self.repo, risk="RED")
        with self.assertRaises(AuthorizationError):
            service.stand_down(self.repo, ANALYST, bid)


class TestDispatcherNewActions(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryRepository()

    def test_escalate_dispatch(self):
        bid = _brief(self.repo)
        s, body = api.dispatch(self.repo, "brief.escalate", INTELLIGENCE_LEAD, {"brief_id": bid})
        self.assertEqual(s, 200)
        self.assertEqual(body["result"]["overall_risk"], "RED")

    def test_stand_down_dispatch(self):
        bid = _brief(self.repo, risk="RED")
        s, body = api.dispatch(self.repo, "brief.stand_down", INTELLIGENCE_LEAD,
                               {"brief_id": bid, "lesson_text": "x", "category": "other"})
        self.assertEqual(s, 200)
        self.assertTrue(body["result"]["stood_down"])

    def test_new_actions_rbac_403(self):
        bid = _brief(self.repo)
        for action in ("brief.escalate", "brief.notify_telegram", "brief.stand_down"):
            s, _ = api.dispatch(self.repo, action, ANALYST, {"brief_id": bid})
            self.assertEqual(s, 403, action)

    def test_missing_field_400(self):
        s, _ = api.dispatch(self.repo, "brief.escalate", INTELLIGENCE_LEAD, {})
        self.assertEqual(s, 400)


class TestDispatchCLI(unittest.TestCase):
    def _run(self, req):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--json", json.dumps(req)])
        return code, json.loads(buf.getvalue())

    def test_unknown_action_404(self):
        # Unknown action returns 404 before the repo is touched (no network).
        code, out = self._run({"action": "signal.nuke", "role": "intelligence_lead", "payload": {}})
        self.assertEqual(out["status"], 404)
        self.assertEqual(code, 1)

    def test_missing_role_403(self):
        code, out = self._run({"action": "brief.escalate", "role": "", "payload": {"brief_id": "b"}})
        self.assertEqual(out["status"], 403)

    def test_bad_json_400(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--json", "{not json"])
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], 400)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
