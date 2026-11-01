"""
Unit tests for context_service.py's _http_health_adjusted_queue() — the
/queue/health-adjusted HTTP endpoint's implementation.

2026-09-08 (USS-TJR-MSN-0054 follow-on): NumberOne.get_health_adjusted_queue()
existed, tested (core/coordination/test_number_one.py), and had zero live
callers — same situation the daily brief was in before it was wired up.
This endpoint is its first caller. Mocks _load_missions() and
_capacity_status_for_today() so these run without a real Missions/ corpus,
Supabase, or Captain's Log check-in data.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CA_DIR = _REPO_ROOT / "core" / "context-assembly"
_COORD_DIR = _REPO_ROOT / "core" / "coordination"

for p in (_CA_DIR, _COORD_DIR, _REPO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import context_service

_SYNTHETIC_MISSIONS = [
    {
        "mission_id": "USS-TJR-MSN-9101",
        "title": "P0 test mission",
        "status": "Active",
        "priority": "P0",
        "domain": "engineering",
        "blockers": [],
        "dependencies": [],
        "next_action": "continue",
        "assigned_role": None,
    },
    {
        "mission_id": "USS-TJR-MSN-9102",
        "title": "P2 test mission",
        "status": "Active",
        "priority": "P2",
        "domain": "engineering",
        "blockers": [],
        "dependencies": [],
        "next_action": "continue",
        "assigned_role": None,
    },
]


class TestHttpHealthAdjustedQueue(unittest.TestCase):
    def _run(self, capacity_status="Green", missions=None):
        with patch.object(context_service, "_load_live_missions_for_number_one",
                           return_value=missions if missions is not None else _SYNTHETIC_MISSIONS), \
             patch.object(context_service, "_capacity_status_for_today", return_value=capacity_status), \
             patch("engineering_handoff_reader.load_engineering_handoffs", return_value=[]):
            return context_service._http_health_adjusted_queue()

    def test_contract_keys_present(self):
        result = self._run()
        for key in ("assembled_at", "source", "engine", "capacity_status",
                    "queue", "recommended_focus", "advisory"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_uses_todays_capacity_status(self):
        result = self._run(capacity_status="Amber")
        self.assertEqual(result["capacity_status"], "Amber")

    def test_capacity_status_resolution_failure_degrades_to_unknown(self):
        """A Supabase failure resolving today's capacity must never break the
        queue endpoint — it must fall back to an honest Unknown, not 500."""
        with patch.object(context_service, "_load_live_missions_for_number_one",
                           return_value=_SYNTHETIC_MISSIONS), \
             patch("health_context_adapter.build_health_context_live", side_effect=RuntimeError("boom")), \
             patch("engineering_handoff_reader.load_engineering_handoffs", return_value=[]):
            result = context_service._http_health_adjusted_queue()
        self.assertEqual(result["capacity_status"], "Unknown")

    def test_queue_items_are_json_serializable_dicts(self):
        result = self._run()
        self.assertEqual(len(result["queue"]), len(_SYNTHETIC_MISSIONS))
        for item in result["queue"]:
            self.assertIsInstance(item, dict)
            for key in ("mission_id", "priority", "status", "title", "capacity_note"):
                self.assertIn(key, item)
            self.assertIsInstance(item["priority"], str)

    def test_red_capacity_marks_non_p0_deferred(self):
        result = self._run(capacity_status="Red")
        notes = {m["mission_id"]: m["capacity_note"] for m in result["queue"]}
        self.assertIn("CRITICAL", notes["USS-TJR-MSN-9101"])
        self.assertIn("DEFERRED", notes["USS-TJR-MSN-9102"])

    def test_response_is_actually_json_serializable(self):
        import json
        result = self._run()
        json.dumps(result)

    def test_empty_mission_list_does_not_raise(self):
        result = self._run(missions=[])
        self.assertEqual(result["queue"], [])


if __name__ == "__main__":
    unittest.main()
