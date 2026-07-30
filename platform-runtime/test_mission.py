"""Tests for ADR-006 Phase 3 mission registry memory integration."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MISSION_REGISTRY_DIR = ROOT / "core" / "missions" / "mission-registry"
if str(MISSION_REGISTRY_DIR) not in sys.path:
    sys.path.insert(0, str(MISSION_REGISTRY_DIR))

from mission_registry import MissionRegistry
from core.coordination.mission_registry_memory_adapter import MissionRegistryMemoryAdapter
from core.coordination.number_one_memory_adapter import NumberOneMemoryAdapter
import commands.research_command as research_command


def _seed_mission(registry: MissionRegistry, *, mission_id: str, title: str, description: str, domain: str, priority: str, source: str, status: str, tags: list[str]):
    conn = sqlite3.connect(registry.db_path)
    cursor = conn.cursor()
    now = "2026-06-12T00:00:00Z"
    columns = [
        "mission_id", "title", "description", "domain", "division", "assigned_role",
        "assigned_specialists", "priority", "status", "source", "created_at", "updated_at",
        "due_date", "next_action", "dependencies", "blockers", "evidence_links",
        "completion_notes", "deferral_reason", "cancellation_reason", "adoption_rating",
        "decision_log", "tags", "expected_behaviour", "actual_behaviour", "validation_method",
        "validation_result", "validation_evidence_link", "blocking_defects",
        "closure_submitted_by", "closure_submitted_at", "number_one_reviewed_by",
        "number_one_reviewed_at", "number_one_approval", "number_one_notes",
        "xo_approved_by", "xo_approved_at", "xo_notes", "closure_audit_trail",
    ]
    values = [
        mission_id, title, description, domain, None, "Unassigned",
        json.dumps([]), priority, status, source, now, now,
        None, None, json.dumps([]), json.dumps([]), json.dumps([]),
        None, None, None, None,
        json.dumps([]), json.dumps(tags), None, None, None,
        None, None, json.dumps([]), json.dumps([]),
        None, None, None,
        None, None, None,
        None, None, '[]',
    ]
    placeholders = ", ".join(["?"] * len(values))
    cursor.execute(
        f"INSERT INTO missions ({', '.join(columns)}) VALUES ({placeholders})",
        values,
    )
    conn.commit()
    conn.close()


class TestMissionRegistryMemoryAdapter(unittest.TestCase):
    def test_related_missions_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "missions.db"
            registry = MissionRegistry(str(db_path))
            _seed_mission(
                registry,
                mission_id="MSN-1001",
                title="Research Memory Integration",
                description="Integrate mission registry memory lookup",
                domain="Governance",
                priority="P2",
                source="Captain",
                status="PROPOSED",
                tags=["memory", "research"],
            )
            _seed_mission(
                registry,
                mission_id="MSN-1002",
                title="Duplicate Work Detection",
                description="Prevent redundant research and planning",
                domain="Governance",
                priority="P1",
                source="Captain",
                status="ACTIVE",
                tags=["duplicate", "research"],
            )

            adapter = MissionRegistryMemoryAdapter(registry=registry)
            context = adapter.retrieve_related_missions(
                title="Research Memory Integration",
                objective="Lookup related missions",
                tags=["memory"],
                status="PROPOSED",
                capability="Knowledge Retrieval",
                text="research memory duplicate work",
                limit=5,
            )

        self.assertTrue(context.found)
        self.assertTrue(context.related_missions)
        self.assertTrue(any(item.mission_id == "MSN-1001" for item in context.related_missions))
        self.assertTrue(any(item.reason for item in context.related_missions))

    def test_fallback_is_non_blocking(self):
        adapter = MissionRegistryMemoryAdapter(registry=None)
        with patch.object(adapter, "_load_missions", side_effect=RuntimeError("boom")):
            context = adapter.retrieve_related_missions(title="anything")
        self.assertFalse(context.found)
        self.assertEqual(context.related_missions, [])

    def test_duplicate_detection_mentions_relevant_reason(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "missions.db"
            registry = MissionRegistry(str(db_path))
            _seed_mission(
                registry,
                mission_id="MSN-2001",
                title="Mission Registry Memory Integration",
                description="Surface similar missions and duplicate work",
                domain="Governance",
                priority="P2",
                source="Captain",
                status="ACTIVE",
                tags=["memory", "duplicate"],
            )

            adapter = MissionRegistryMemoryAdapter(registry=registry)
            context = adapter.retrieve_related_missions(
                title="Mission Registry Memory Integration",
                objective="Surface related missions",
                tags=["memory", "duplicate"],
                text="duplicate work mission registry",
                limit=5,
            )

        self.assertTrue(context.found)
        self.assertTrue(any("title overlap" in item.reason or "text similarity" in item.reason for item in context.related_missions))


class TestNumberOneMissionRegistryMemoryIntegration(unittest.TestCase):
    def test_number_one_includes_mission_registry_references(self):
        num1 = NumberOneMemoryAdapter(repo_root=ROOT)
        memory = MagicMock()
        memory.found = True
        memory.confidence = 0.85
        memory.summary = "Mission registry overlap detected"
        memory.related_missions = [
            MagicMock(mission_id="MSN-3001", title="Related Mission", status="ACTIVE", reason="title overlap", confidence=0.9)
        ]

        with patch.object(num1, "mission_registry_memory") as mock_registry_memory, \
             patch.object(num1, "supabase", None), \
             patch.object(num1, "_retrieve_from_supabase", return_value=[]):
            mock_registry_memory.retrieve_related_missions.return_value = memory
            context = num1.retrieve_context([{"mission_id": "MSN-3001", "title": "Related Mission"}], {})

        self.assertTrue(context.found)
        self.assertTrue(any(item.get("source_type") == "mission_registry" for item in context.sources))
        self.assertTrue(any("Review related missions" in item for item in context.recommendations))

    def test_research_output_surfaces_related_missions(self):
        with patch.object(research_command, "_build_mission_registry_memory_adapter") as mock_adapter_builder, \
             patch.object(research_command, "_build_research_supabase_client", return_value=object()), \
             patch("lib.research_memory_retrieval.ResearchMemoryRetriever.search_prior_research", return_value=MagicMock(found=False, recommendation="NEW_RESEARCH", match_confidence=0.0, reason="", entry=None)), \
             patch("core.coordination.research_orchestration.ResearchOrchestrator") as mock_orchestrator:
            mock_registry = MagicMock()
            mock_registry.retrieve_related_missions.return_value = MagicMock(
                found=True,
                confidence=0.9,
                summary="MSN-4001: title overlap",
                related_missions=[MagicMock(mission_id="MSN-4001", status="ACTIVE", title="Related Mission", reason="title overlap", confidence=0.9)],
            )
            mock_adapter_builder.return_value = mock_registry
            mock_orchestrator.return_value.run_research_mission.return_value = MagicMock(
                mission_id="MSN-4000",
                research_topic="Mission Registry memory",
                consolidated_findings="Findings",
                recommendation="Proceed",
                confidence=0.8,
                timestamp="2026-06-12T00:00:00Z",
                provider_paths=[],
                tasks_completed=1,
                task_count=1,
                status="success",
            )

            response = research_command._execute_research_mission("Mission Registry memory", "U123", "C123")

        self.assertIn("Related missions", response)
        mock_orchestrator.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
