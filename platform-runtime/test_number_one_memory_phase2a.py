"""Tests for ADR-006 Phase 2A: Number One memory-aware oversight."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.coordination.number_one import NumberOne, MissionStatus, Priority, Mission
from core.coordination.number_one_memory_adapter import NumberOneMemoryAdapter, MemoryContext


class TestNumberOneMemoryAdapter(unittest.TestCase):
    def test_retrieve_context_returns_advisory_context(self):
        adapter = NumberOneMemoryAdapter(repo_root=ROOT)
        fake_row = {
            "id": "MSN-001",
            "mission_id": "MSN-001",
            "title": "Duplicate Search Pipeline",
            "summary": "Existing mission for duplicate search",
            "confidence": 0.85,
        }

        with patch.object(adapter, "supabase", None), \
             patch.object(adapter, "_retrieve_from_files", return_value=[{"source_type": "adr", "summary": "ADR", "confidence": 0.9, "duplicate": True}, fake_row]):
            context = adapter.retrieve_context([{"mission_id": "MSN-001", "title": "Duplicate Search Pipeline"}], {})

        self.assertTrue(context.found)
        self.assertGreaterEqual(context.confidence, 0.85)
        self.assertTrue(context.duplicates)
        self.assertTrue(context.recommendations)

    def test_persist_brief_is_non_blocking_without_supabase(self):
        adapter = NumberOneMemoryAdapter(repo_root=ROOT)
        with patch.object(adapter, "supabase", None):
            ok = adapter.persist_brief({"brief_id": "BRIEF-1", "mission_id": "MSN-001", "summary": "Summary", "recommendations": []})
        self.assertFalse(ok)


class TestNumberOneMemoryAwareBrief(unittest.TestCase):
    def test_brief_includes_memory_in_recommendations_when_available(self):
        num1 = NumberOne()
        memory = MemoryContext(
            found=True,
            confidence=0.91,
            summary="Existing ADR and mission overlap",
            sources=[{"source_type": "adr", "summary": "Existing ADR"}],
            duplicates=[{"source_type": "mission", "summary": "Duplicate mission"}],
            recommendations=["Reference existing ADR before proposing a new approach"],
        )

        missions = [
            {
                "mission_id": "MSN-001",
                "title": "Duplicate Search Pipeline",
                "status": "PROPOSED",
                "priority": "P1",
                "domain": "research",
            }
        ]

        with patch.object(num1, "_get_memory_context", return_value=memory), \
             patch.object(num1, "_persist_memory_context") as mock_persist:
            brief = num1.get_daily_brief(missions)

        self.assertTrue(any(item.startswith("Memory context:") for item in brief.recommended_actions))
        mock_persist.assert_called_once()

    def test_memory_failure_keeps_existing_behavior(self):
        num1 = NumberOne()
        missions = [
            {
                "mission_id": "MSN-002",
                "title": "Baseline Mission",
                "status": "PROPOSED",
                "priority": "P2",
                "domain": "ops",
            }
        ]

        with patch.object(num1, "_get_memory_context", return_value=None), \
             patch.object(num1, "_persist_memory_context") as mock_persist:
            brief = num1.get_daily_brief(missions)

        self.assertIsNotNone(brief)
        self.assertFalse(any(item.startswith("Memory context:") for item in brief.recommended_actions))
        mock_persist.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
