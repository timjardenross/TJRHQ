"""Owner decision 2026-11-03: a Red or Amber capacity reading no longer raises an improvement's
priority and no longer opens an automatic Human Systems investigation. Pure/offline."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from lib.improvement.framework import ImprovementCategory, ImprovementOpportunity
from lib.improvement.scoring import ImprovementScoringEngine
from lib.investigation import officer_investigations as oi


class TestCapacityDoesNotSteer(unittest.TestCase):
    def _opp(self, category=ImprovementCategory.CAPACITY):
        return ImprovementOpportunity(
            source_officer="human_systems", domain="capacity", observation="x", category=category,
            suggested_action="y", estimated_effort="low", expected_benefit="z",
        )

    def test_improvement_priority_is_the_same_whatever_the_capacity_reading(self):
        engine = ImprovementScoringEngine()
        for category in (ImprovementCategory.CAPACITY, ImprovementCategory.WASTE, ImprovementCategory.RISK):
            scores = {
                status: engine._score_captain_capacity_impact(self._opp(category), {"capacity_status": status})
                for status in ("Green", "Amber", "Red", "Unknown")
            }
            self.assertEqual(len(set(scores.values())), 1, (category, scores))

    def test_red_or_amber_capacity_opens_no_human_systems_investigation(self):
        self.assertFalse(hasattr(oi, "investigate_human_systems"))
        self.assertNotIn("investigate_human_systems", oi.__all__)
        with mock.patch.object(oi, "open_investigation", return_value="INV-1") as opened:
            for status in ("Red", "Amber"):
                ctx = SimpleNamespace(
                    capacity_status=status, engineering_blocked=5, resilience_available=False,
                    resilience_risk="Unknown", number_one_items=[],
                )
                oi.run_all_investigation_triggers(ctx)
            for call in opened.call_args_list:
                self.assertNotEqual(call.kwargs.get("officer"), "human_systems", call)


if __name__ == "__main__":
    unittest.main(verbosity=2)
