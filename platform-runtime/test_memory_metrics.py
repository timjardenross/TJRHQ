from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.coordination.mission_registry_memory_adapter import MissionRegistryMemoryAdapter
from core.coordination.decision_registry_memory_adapter import DecisionRegistryMemoryAdapter


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


class MemoryMetricsTests(unittest.TestCase):
    def test_mission_registry_logs_stale_context_and_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            active_dir = repo_root / "Missions" / "Active"
            active_dir.mkdir(parents=True)
            stale_file = active_dir / "MSN-OLD.md"
            stale_file.write_text("stale mission content", encoding="utf-8")

            adapter = MissionRegistryMemoryAdapter(registry=None)
            adapter.repo_root = repo_root
            with patch("core.coordination.mission_registry_memory_adapter.log_memory_metric") as mock_metric:
                with patch.object(adapter, "_load_from_files", return_value=[{
                    "mission_id": "MSN-OLD",
                    "title": "Old Mission",
                    "status": "ACTIVE",
                    "updated_at": "2020-01-01T00:00:00Z",
                    "description": "stale mission",
                }]):
                    context = adapter.retrieve_related_missions(title="Old Mission", text="stale mission", limit=3)

            self.assertTrue(context.stale_context)
            self.assertTrue(any("stale context flagged" in context.summary for _ in [0]))
            self.assertTrue(any(call.kwargs.get("action") == "stale_context_flagged" for call in mock_metric.call_args_list))

    def test_decision_registry_logs_metrics_and_flags_stale_context(self):
        supabase = _FakeSupabase({
            "decision_records": [
                {
                    "id": "DEC-OLD",
                    "status": "approved",
                    "decision": "Approve old architecture",
                    "decision_reason": "historic",
                    "decision_timestamp": "2020-01-01T00:00:00Z",
                }
            ]
        })
        adapter = DecisionRegistryMemoryAdapter(supabase=supabase)
        with patch("core.coordination.decision_registry_memory_adapter.log_memory_metric") as mock_metric:
            context = adapter.retrieve_related_decisions(title="old architecture", text="historic", limit=3)

        self.assertTrue(context.stale_context)
        self.assertTrue(any("stale context flagged" in context.summary for _ in [0]))
        self.assertTrue(any(call.kwargs.get("action") == "stale_context_flagged" for call in mock_metric.call_args_list))
        self.assertTrue(any(call.kwargs.get("action") == "related_decisions_retrieved" for call in mock_metric.call_args_list))


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)

