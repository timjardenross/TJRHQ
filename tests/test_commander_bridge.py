import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "platform-runtime"))

import commander_bridge  # noqa: E402


def write_result(table: str, ok: bool = True, enabled: bool = True):
    return commander_bridge.SupabaseWriteResult(ok=ok, enabled=enabled, table=table)


class CommanderBridgeTest(unittest.TestCase):
    def test_decision_intent_writes_decision_payload(self):
        with patch.object(commander_bridge, "log_commander_event", return_value=write_result("commander_events")), \
                patch.object(commander_bridge, "log_decision", return_value=write_result("commander_decisions")) as decision, \
                patch.object(commander_bridge, "fetch_recent_context", return_value={"events": [], "decisions": [], "missions": [], "memory": []}):
            result = commander_bridge.handle_slack_message(
                "Decision: Defer BFG cleanup until token rotation is confirmed.",
                user_id="U1",
                channel_id="C1",
                message_ts="123.45",
            )

        self.assertEqual(result["intent"], "decision")
        self.assertTrue(result["logged"]["decision"])
        payload = decision.call_args.args[0]
        self.assertEqual(payload["decision_title"], "Defer BFG cleanup until token rotation is confirmed.")
        self.assertEqual(payload["source"], "slack")
        self.assertEqual(payload["user_id"], "U1")

    def test_mission_candidate_intent_writes_mission_payload(self):
        # Fleet Engineering Review 2026-08-11: this test's INTENT_MISSION_
        # CANDIDATE path calls commander_bridge.create_mission() for real
        # (commander_bridge.py:212) — unmocked, this minted a genuine
        # USS-TJR-MSN-* record and incremented the live .id-counters.json
        # every time the test suite ran. Mocked here since the test only
        # asserts on the mission_candidate LOG payload, never the mission
        # object itself.
        with patch.object(commander_bridge, "log_commander_event", return_value=write_result("commander_events")), \
                patch.object(commander_bridge, "log_mission_candidate", return_value=write_result("commander_mission_candidates")) as mission, \
                patch.object(commander_bridge, "create_mission", return_value={
                    "mission_id": "USS-TJR-MSN-TEST", "title": "Test Mission",
                    "domain": "Test", "status": "candidate",
                }), \
                patch.object(commander_bridge, "fetch_recent_context", return_value={"events": [], "decisions": [], "missions": [], "memory": []}):
            result = commander_bridge.handle_slack_message(
                "Create mission: Build Slack to Supabase Commander integration.",
                user_id="U1",
                channel_id="C1",
            )

        self.assertEqual(result["intent"], "mission_candidate")
        self.assertTrue(result["logged"]["mission_candidate"])
        payload = mission.call_args.args[0]
        self.assertIn("Slack to Supabase", payload["mission_title"])

    def test_memory_intent_writes_memory_payload(self):
        with patch.object(commander_bridge, "log_commander_event", return_value=write_result("commander_events")), \
                patch.object(commander_bridge, "log_memory_event", return_value=write_result("commander_memory_events")) as memory, \
                patch.object(commander_bridge, "fetch_recent_context", return_value={"events": [], "decisions": [], "missions": [], "memory": []}):
            result = commander_bridge.handle_slack_message(
                "Remember: Supabase is persistence, not the source of truth.",
                user_id="U1",
                channel_id="C1",
            )

        self.assertEqual(result["intent"], "memory")
        self.assertTrue(result["logged"]["memory"])
        payload = memory.call_args.args[0]
        self.assertIn("Supabase is persistence", payload["memory_text"])

    def test_general_message_uses_router_and_runtime(self):
        with patch.object(commander_bridge, "log_commander_event", return_value=write_result("commander_events")), \
                patch.object(commander_bridge, "fetch_recent_context", return_value={"events": [], "decisions": [], "missions": [], "memory": []}), \
                patch.object(commander_bridge, "execute_commander_runtime", return_value="Commander response") as runtime:
            result = commander_bridge.handle_slack_message("Who should own the governance source of truth?")

        self.assertEqual(result["intent"], "general")
        self.assertEqual(result["route"], "Knowledge Officer")
        self.assertEqual(result["response_text"], "Commander response")
        runtime.assert_called_once()

    def test_supabase_unavailable_does_not_crash_bridge(self):
        disabled = write_result("commander_events", ok=False, enabled=False)
        with patch.object(commander_bridge, "log_commander_event", return_value=disabled), \
                patch.object(commander_bridge, "log_decision", return_value=disabled), \
                patch.object(commander_bridge, "fetch_recent_context", return_value={"events": [], "decisions": [], "missions": [], "memory": []}):
            result = commander_bridge.handle_slack_message("Decision: Keep GitHub as source of truth.")

        self.assertTrue(result["ok"])
        self.assertFalse(result["logged"]["decision"])
        self.assertIn("captured", result["response_text"])


if __name__ == "__main__":
    unittest.main()
