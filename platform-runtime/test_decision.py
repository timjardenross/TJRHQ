from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from core.coordination.decision_registry_memory_adapter import DecisionRegistryMemoryAdapter
from core.coordination.number_one_memory_adapter import NumberOneMemoryAdapter


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return _FakeResponse(self.rows)


class _FakeSupabase:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return _FakeQuery(self.tables.get(name, []))


class DecisionRegistryMemoryAdapterTests(unittest.TestCase):
    def test_related_decisions_and_conflict_warning_from_supabase(self):
        supabase = _FakeSupabase({
            "decision_records": [
                {
                    "id": "DEC-011",
                    "status": "approved",
                    "decision": "Approve mission registry consolidation",
                    "decision_reason": "Aligned with governance",
                    "mission_id": "MSN-100",
                    "adr_reference": "ADR-011",
                },
                {
                    "id": "DEC-004",
                    "status": "rejected",
                    "decision": "Reject duplicate embedding pipeline",
                    "decision_reason": "Duplicate of existing capability",
                    "mission_id": "MSN-101",
                },
            ]
        })
        adapter = DecisionRegistryMemoryAdapter(supabase=supabase)

        context = adapter.retrieve_related_decisions(
            title="mission registry consolidation",
            objective="improve related decision recall",
            adr_reference="ADR-011",
            text="decision registry consolidation",
            limit=5,
        )

        self.assertTrue(context.found)
        self.assertGreaterEqual(context.confidence, 0.3)
        self.assertGreaterEqual(len(context.related_decisions), 1)
        self.assertTrue(any(item.decision_id == "DEC-011" for item in context.related_decisions))
        self.assertTrue(any("DEC-011" in warning for warning in context.conflict_warnings))

    def test_file_fallback_returns_related_decision(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            decisions_dir = repo_root / "knowledge" / "decisions"
            decisions_dir.mkdir(parents=True)
            (decisions_dir / "DEC-20260612-TEST.md").write_text(
                "\n".join([
                    "Decision ID: DEC-20260612-TEST",
                    "Status: Approved",
                    "",
                    "Decision:",
                    "Use the canonical mission registry as source of truth.",
                    "",
                    "Rationale:",
                    "Keeps governance aligned.",
                    "",
                    "Related:",
                    "Superseded by DEC-20260613-TEST.",
                ]),
                encoding="utf-8",
            )

            adapter = DecisionRegistryMemoryAdapter(supabase=None, repo_root=repo_root)
            context = adapter.retrieve_related_decisions(
                title="canonical mission registry source of truth",
                objective="governance recall",
                text="mission registry source of truth",
                limit=3,
            )

            self.assertTrue(context.found)
            self.assertTrue(any(item.decision_id == "DEC-20260612-TEST" for item in context.related_decisions))
            self.assertTrue(any(item.lineage for item in context.related_decisions))


class NumberOneDecisionMemoryTests(unittest.TestCase):
    def test_number_one_memory_includes_related_decisions(self):
        adapter = NumberOneMemoryAdapter()

        class _StubDecisionContext:
            found = True
            confidence = 0.88
            related_decisions = [
                type("Decision", (), {
                    "decision_id": "DEC-011",
                    "status": "approved",
                    "summary": "Approve mission registry consolidation",
                    "reason": "title overlap",
                    "source": "decision-registry",
                    "confidence": 0.88,
                    "lineage": "",
                    "conflict": True,
                })()
            ]

        adapter.decision_registry_memory = type(
            "_StubDecisionAdapter",
            (),
            {"retrieve_related_decisions": lambda self, **kwargs: _StubDecisionContext()},
        )()

        context = adapter.retrieve_context(
            missions=[{"mission_id": "MSN-100", "title": "Mission registry consolidation", "status": "ACTIVE"}],
            routing_results={},
        )

        self.assertTrue(context.found)
        self.assertTrue(any(item.get("source_type") == "decision_registry" for item in context.sources))
        self.assertTrue(any("Review related decisions" in recommendation for recommendation in context.recommendations))

    def test_number_one_memory_summary_is_compact(self):
        adapter = NumberOneMemoryAdapter()
        summary = adapter._format_summary(
            [
                "Missions: MSN-100 overlap",
                "DEC-011: approve mission registry consolidation",
                "ADR-004: knowledge architecture",
            ],
            [
                {"source_type": "mission_registry"},
                {"source_type": "decision_registry"},
                {"source_type": "adr"},
            ],
        )

        self.assertIn("Sources: mission registry, decision registry, adr", summary)
        self.assertLessEqual(len(summary), 500)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
