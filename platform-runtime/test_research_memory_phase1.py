"""Phase 1 tests for ADR-006 research memory activation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

import commands.research_command as research_command


class TestResearchMemoryPhase1(unittest.TestCase):
    def test_research_uses_memory_before_new_execution(self):
        retriever_result = MagicMock()
        retriever_result.found = True
        retriever_result.recommendation = "REUSE"
        retriever_result.match_confidence = 0.93
        retriever_result.reason = "Fresh research"
        retriever_result.entry = {
            "findings": "Existing findings",
            "recommendation": "Reuse prior research",
            "mission_id": "MSN-OLD-001",
        }

        with patch.object(research_command, "_build_research_supabase_client", return_value=object()) as mock_client, \
             patch("lib.research_memory_retrieval.ResearchMemoryRetriever.search_prior_research", return_value=retriever_result) as mock_search, \
             patch("core.coordination.research_orchestration.ResearchOrchestrator") as mock_orchestrator:
            response = research_command.handle_research_request("evaluate search strategy", "U123", "C123")

        self.assertIn("Prior Research Reused", response)
        mock_client.assert_called()
        mock_search.assert_called_once()
        mock_orchestrator.assert_not_called()

    def test_research_persists_results_after_completion(self):
        fake_result = MagicMock()
        fake_result.mission_id = "MSN-20260612-0001"
        fake_result.research_topic = "memory aware research"
        fake_result.consolidated_findings = "Findings"
        fake_result.recommendation = "Proceed"
        fake_result.confidence = 0.81
        fake_result.timestamp = "2026-06-12T00:00:00Z"
        fake_result.provider_paths = ["gemini"]
        fake_result.tasks_completed = 2
        fake_result.task_count = 2
        fake_result.status = "success"

        with patch.object(research_command, "_build_research_supabase_client") as mock_client_builder, \
             patch.object(research_command, "_queue_mission_logging") as mock_queue_logging, \
             patch.object(research_command, "_persist_research_memory") as mock_persist, \
             patch("lib.research_memory_retrieval.ResearchMemoryRetriever.search_prior_research", return_value=MagicMock(found=False, recommendation="NEW_RESEARCH", match_confidence=0.0, reason="", entry=None)), \
             patch("core.coordination.research_orchestration.ResearchOrchestrator") as mock_orchestrator:
            mock_client_builder.return_value = object()
            mock_orchestrator.return_value.run_research_mission.return_value = fake_result
            response = research_command._execute_research_mission("memory aware research", "U123", "C123")

        self.assertTrue(response)
        mock_queue_logging.assert_called_once()
        mock_persist.assert_called_once_with(fake_result, "U123")

    def test_persistence_failure_is_non_blocking(self):
        fake_result = MagicMock()
        fake_result.mission_id = "MSN-20260612-0002"
        fake_result.research_topic = "fault tolerant retrieval"
        fake_result.consolidated_findings = "Findings"
        fake_result.recommendation = "Proceed"
        fake_result.confidence = 0.5
        fake_result.timestamp = "2026-06-12T00:00:00Z"
        fake_result.provider_paths = []
        fake_result.tasks_completed = 1
        fake_result.task_count = 1
        fake_result.status = "success"

        fake_write_result = MagicMock(ok=False, table="research_memory", error="disabled")
        fake_client = MagicMock()
        fake_client.insert.return_value = fake_write_result

        with patch.object(research_command, "_build_research_supabase_client", return_value=fake_client):
            research_command._persist_research_memory(fake_result, "U123")

        fake_client.insert.assert_called_once()

    def test_duplicate_research_opportunity_surfaces_reuse(self):
        retriever_result = MagicMock()
        retriever_result.found = True
        retriever_result.recommendation = "REUSE_WITH_NOTE"
        retriever_result.match_confidence = 0.67
        retriever_result.reason = "Recent research"
        retriever_result.entry = {
            "findings": "Earlier findings",
            "recommendation": "Refresh with note",
            "mission_id": "MSN-OLD-002",
        }

        with patch.object(research_command, "_build_research_supabase_client", return_value=object()), \
             patch("lib.research_memory_retrieval.ResearchMemoryRetriever.search_prior_research", return_value=retriever_result), \
             patch("core.coordination.research_orchestration.ResearchOrchestrator") as mock_orchestrator:
            response = research_command._execute_research_mission("duplicate opportunity", "U123", "C123")

        self.assertIn("Prior Research + Fresh Data", response)
        self.assertIn("Note", response)
        mock_orchestrator.assert_not_called()

    def test_research_supabase_builder_returns_raw_client(self):
        fake_raw_client = object()
        with patch("tools.supabase.client.CommanderSupabaseClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.raw_client = fake_raw_client
            mock_client_cls.return_value = mock_client

            raw_client = research_command._build_research_supabase_client()

        self.assertIs(raw_client, fake_raw_client)


if __name__ == "__main__":
    unittest.main(verbosity=2)
