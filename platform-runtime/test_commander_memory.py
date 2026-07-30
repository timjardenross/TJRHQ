from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import commander_bridge
import app


class CommanderMemoryPresentationTests(unittest.TestCase):
    def test_commander_response_appends_memory_note(self):
        fake_context = MagicMock(found=True, note="*Historical Insight:*\nMemory Confidence: HIGH")
        with patch.object(commander_bridge._commander_memory_adapter, "build_memory_note", return_value=fake_context), \
             patch.object(commander_bridge, "run_supabase_commander", return_value="Commander output"), \
             patch.object(commander_bridge, "format_commander_response", side_effect=lambda parsed: "Commander output"):
            result = commander_bridge.handle_slack_message("commander review prior decisions", user_id="U1", channel_id="C1")

        self.assertIn("Historical Insight", result["response_text"])
        self.assertEqual(result["intent"], "general")

    def test_mission_capture_receives_memory_note(self):
        with patch.object(app._commander_memory_adapter, "build_memory_note", return_value=MagicMock(found=True, note="*Historical Insight:*\nMemory Confidence: LOW")), \
             patch.object(app, "handle_mission_capture", return_value="Mission captured"):
            rendered = app._append_commander_memory_note("Mission captured", text="new mission", intent="mission")

        self.assertIn("Historical Insight", rendered)

    def test_decision_log_receives_memory_note(self):
        with patch.object(app._commander_memory_adapter, "build_memory_note", return_value=MagicMock(found=True, note="*Historical Insight:*\nMemory Confidence: HIGH")):
            rendered = app._append_commander_memory_note("Decision logged", text="new decision", intent="decision")

        self.assertIn("Historical Insight", rendered)

    def test_low_confidence_memory_omits_confidence_line(self):
        fake_context = MagicMock(found=True, note="*Historical Insight:*\nReason: 1 related reference")
        with patch.object(commander_bridge._commander_memory_adapter, "build_memory_note", return_value=fake_context), \
             patch.object(commander_bridge, "run_supabase_commander", return_value="Commander output"), \
             patch.object(commander_bridge, "format_commander_response", side_effect=lambda parsed: "Commander output"):
            result = commander_bridge.handle_slack_message("general update", user_id="U1", channel_id="C1")

        self.assertIn("Historical Insight", result["response_text"])
        self.assertNotIn("Memory Confidence:", result["response_text"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
