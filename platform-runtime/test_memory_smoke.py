from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.coordination.advisory_memory_formatter import format_memory_block
from core.coordination.decision_registry_memory_adapter import DecisionRegistryMemoryAdapter
from core.coordination.number_one_memory_adapter import NumberOneMemoryAdapter
import commands.research_command as research_command


class MemorySmokeTest(unittest.TestCase):
    def test_research_number_one_and_decision_memory_are_all_advisory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            decisions_dir = repo_root / "knowledge" / "decisions"
            decisions_dir.mkdir(parents=True)
            (decisions_dir / "DEC-SMOKE.md").write_text(
                "\n".join([
                    "Decision ID: DEC-SMOKE",
                    "Status: Approved",
                    "",
                    "Decision:",
                    "Use the canonical mission registry as source of truth.",
                    "",
                    "Rationale:",
                    "Avoid duplicate work and improve governance recall.",
                    "",
                    "Related:",
                    "Superseded by DEC-SMOKE-2.",
                ]),
                encoding="utf-8",
            )

            decision_adapter = DecisionRegistryMemoryAdapter(supabase=None, repo_root=repo_root)
            decision_context = decision_adapter.retrieve_related_decisions(
                title="canonical mission registry source of truth",
                objective="avoid duplicate work",
                text="governance recall and duplicate work",
                limit=3,
            )

            num1 = NumberOneMemoryAdapter(repo_root=repo_root)
            num1.decision_registry_memory = decision_adapter
            num1.mission_registry_memory = MagicMock()
            num1.mission_registry_memory.retrieve_related_missions.return_value = MagicMock(
                found=True,
                confidence=0.6,
                summary="MSN-SMOKE: title overlap",
                related_missions=[MagicMock(mission_id="MSN-SMOKE", title="Smoke", status="ACTIVE", reason="title overlap", confidence=0.6)],
            )
            num1.supabase = None
            with patch.object(num1, "_retrieve_from_supabase", return_value=[]):
                num_context = num1.retrieve_context(
                    missions=[{"mission_id": "MSN-SMOKE", "title": "Smoke", "status": "ACTIVE"}],
                    routing_results={},
                )

            with patch.object(research_command, "_build_mission_registry_memory_adapter") as mission_builder, \
                 patch.object(research_command, "_build_decision_registry_memory_adapter") as decision_builder, \
                 patch.object(research_command, "_build_research_supabase_client", return_value=object()), \
                 patch("lib.research_memory_retrieval.ResearchMemoryRetriever.search_prior_research", return_value=MagicMock(found=False, recommendation="NEW_RESEARCH", match_confidence=0.0, reason="", entry=None)), \
                 patch("core.coordination.research_orchestration.ResearchOrchestrator") as mock_orchestrator:
                mission_builder.return_value = MagicMock(
                    retrieve_related_missions=lambda **kwargs: MagicMock(
                        found=True,
                        confidence=0.7,
                        summary="MSN-SMOKE: overlap",
                        related_missions=[MagicMock(mission_id="MSN-SMOKE", status="ACTIVE", title="Smoke", reason="title overlap")],
                    )
                )
                decision_builder.return_value = MagicMock(
                    retrieve_related_decisions=lambda **kwargs: decision_context
                )
                mock_orchestrator.return_value.run_research_mission.return_value = MagicMock(
                    mission_id="MSN-RESEARCH",
                    research_topic="memory smoke",
                    consolidated_findings="Findings",
                    recommendation="Proceed",
                    confidence=0.8,
                    timestamp="2026-06-12T00:00:00Z",
                    provider_paths=[],
                    tasks_completed=1,
                    task_count=1,
                    status="success",
                )

                research_output = research_command._execute_research_mission("memory smoke", "U123", "C123")

        self.assertTrue(decision_context.found)
        self.assertTrue(num_context.found)
        self.assertIn("Sources:", num_context.summary)
        self.assertIn("Related missions", research_output)
        self.assertIn("Related decisions", research_output)
        self.assertTrue(any(item.get("source_type") == "decision_registry" for item in num_context.sources))
        self.assertIn("Sources: mission registry, decision registry", format_memory_block(
            label="Memory context",
            items=[{"mission_id": "MSN-SMOKE", "status": "ACTIVE", "reason": "title overlap"}],
            source_types=["mission registry", "decision registry"],
            summary="Smoke",
            confidence=0.8,
        ))


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)

