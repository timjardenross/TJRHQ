"""
Tests for mission_lifecycle WP2 (status transitions) and WP3 (idea filter).

Coverage:
  - /mission-list idea with no Supabase data
  - _format_idea_list empty
  - _format_idea_list with missions
  - handle_mission_status read mode (no transition arg)
  - handle_mission_status invalid status rejected
  - handle_mission_status transition — Supabase success
  - handle_mission_status transition — Supabase failure (audit written)
  - _handle_status_transition audit file written
  - _VALID_TRANSITIONS_LOWER covers all statuses
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from commands.mission_lifecycle import (
    _VALID_TRANSITIONS,
    _VALID_TRANSITIONS_LOWER,
    _format_idea_list,
    handle_mission_list,
    handle_mission_status,
)


class TestValidTransitions(unittest.TestCase):
    def test_all_statuses_covered(self):
        expected = {"Idea", "Planned", "Active", "Blocked", "Review", "Completed", "Closed"}
        self.assertEqual(_VALID_TRANSITIONS, expected)

    def test_lower_lookup(self):
        self.assertEqual(_VALID_TRANSITIONS_LOWER["idea"], "Idea")
        self.assertEqual(_VALID_TRANSITIONS_LOWER["planned"], "Planned")
        self.assertEqual(_VALID_TRANSITIONS_LOWER["active"], "Active")


class TestFormatIdeaList(unittest.TestCase):
    def test_empty(self):
        result = _format_idea_list([])
        self.assertIn("empty", result.lower())
        self.assertIn("/mission-capture", result)

    def test_single_mission(self):
        missions = [{"id": "M-001", "title": "Test Idea", "created_at": "2026-06-01T00:00:00Z"}]
        result = _format_idea_list(missions)
        self.assertIn("M-001", result)
        self.assertIn("Test Idea", result)
        self.assertIn("/mission-status", result)

    def test_age_display(self):
        missions = [{"id": "M-001", "title": "Old Idea", "created_at": "2020-01-01T00:00:00Z"}]
        result = _format_idea_list(missions)
        self.assertIn("d old", result)

    def test_caps_at_25(self):
        missions = [{"id": f"M-{i:03d}", "title": f"Idea {i}", "created_at": ""} for i in range(30)]
        result = _format_idea_list(missions)
        self.assertIn("and 5 more", result)


class TestHandleMissionListIdea(unittest.TestCase):
    @patch("commands.mission_lifecycle._supabase_missions", return_value=[])
    def test_no_supabase_returns_guidance(self, _mock):
        result = handle_mission_list("idea")
        self.assertIn("/mission-capture", result)

    @patch("commands.mission_lifecycle._supabase_missions")
    def test_with_ideas(self, mock_sb):
        mock_sb.return_value = [
            {"id": "M-001", "title": "Idea One", "created_at": "2026-06-01T00:00:00Z"},
        ]
        result = handle_mission_list("idea")
        self.assertIn("M-001", result)
        self.assertIn("Idea Registry", result)


class TestHandleMissionStatus(unittest.TestCase):
    def test_empty_shows_usage(self):
        result = handle_mission_status("")
        self.assertIn("Usage", result)

    def test_invalid_status_rejected(self):
        result = handle_mission_status("MSN-0001 limbo")
        self.assertIn("Unknown status", result)
        self.assertIn("limbo", result)

    @patch("commands.mission_lifecycle._supabase_update_mission_status", return_value=True)
    @patch("commands.mission_lifecycle._supabase_missions", return_value=[
        {"id": "MSN-0001", "title": "Test", "status": "Idea"}
    ])
    @patch("commands.mission_lifecycle._write_transition_audit")
    def test_transition_success(self, mock_audit, _mock_sb, _mock_update):
        result = handle_mission_status("MSN-0001 planned", "U001")
        self.assertIn("Idea", result)
        self.assertIn("Planned", result)
        self.assertIn("MSN-0001", result)
        mock_audit.assert_called_once()

    @patch("commands.mission_lifecycle._supabase_update_mission_status", return_value=False)
    @patch("commands.mission_lifecycle._supabase_missions", return_value=[])
    @patch("commands.mission_lifecycle._write_transition_audit")
    def test_transition_supabase_unavailable(self, mock_audit, _mock_sb, _mock_update):
        result = handle_mission_status("MSN-0001 active", "U001")
        self.assertIn("recorded locally", result)
        mock_audit.assert_called_once()

    def test_case_insensitive_status(self):
        with (
            patch("commands.mission_lifecycle._supabase_update_mission_status", return_value=True),
            patch("commands.mission_lifecycle._supabase_missions", return_value=[
                {"id": "MSN-0001", "title": "T", "status": "Idea"}
            ]),
            patch("commands.mission_lifecycle._write_transition_audit"),
        ):
            result = handle_mission_status("MSN-0001 ACTIVE")
            self.assertIn("Active", result)


class TestTransitionAudit(unittest.TestCase):
    def test_audit_file_written(self):
        from commands.mission_lifecycle import _write_transition_audit, _TRANSITION_LOG_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("commands.mission_lifecycle._TRANSITION_LOG_DIR", Path(tmpdir)):
                _write_transition_audit("MSN-0001", "Idea", "Planned", "U001", "test note")
                files = list(Path(tmpdir).glob("TRANSITION-MSN-0001-*.json"))
                self.assertEqual(len(files), 1)
                data = json.loads(files[0].read_text())
                self.assertEqual(data["from_status"], "Idea")
                self.assertEqual(data["to_status"], "Planned")
                self.assertEqual(data["note"], "test note")


if __name__ == "__main__":
    unittest.main()
