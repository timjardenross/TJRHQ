"""Unit tests for core/platform/unified_memory.py's RELATIONSHIPS recall path.

Covers memory_graph.py's first real caller (2026-09-12): recall(RELATIONSHIPS,
query=...) routes to memory_graph.search() (Graphiti); recall(RELATIONSHIPS)
with no query, or any Graphiti failure, falls through to the existing
`knowledge_edges` table. All Graphiti/Supabase calls are mocked so these run
fully offline, same convention as tests/test_episodic_memory.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.platform.unified_memory import MemoryType, recall, remember


def _fake_table_result(rows: list[dict]) -> MagicMock:
    raw = MagicMock()
    query = raw.table.return_value.select.return_value
    query.eq.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.execute.return_value = MagicMock(data=rows)
    return raw


class TestRecallRelationships:
    def test_query_routes_to_memory_graph_search(self):
        fake_facts = [{"fact": "Telstra outage escalated", "valid_at": "2026-09-01T00:00:00Z", "invalid_at": None}]
        with patch("core.platform.memory_graph.search", new=AsyncMock(return_value=fake_facts)) as mock_search:
            result = recall(MemoryType.RELATIONSHIPS, query="Telstra outage", limit=5)
        mock_search.assert_awaited_once_with("Telstra outage", num_results=5, group_ids=None)
        assert result == fake_facts

    def test_no_query_falls_through_to_knowledge_edges_table(self):
        rows = [{"id": "1", "source": "a", "target": "b"}]
        with patch("core.platform.unified_memory._supabase_raw", return_value=_fake_table_result(rows)), patch("core.platform.memory_graph.search", new=AsyncMock()) as mock_search:
            result = recall(MemoryType.RELATIONSHIPS)
        mock_search.assert_not_awaited()
        assert result == rows

    def test_graphiti_failure_falls_back_to_knowledge_edges_table(self):
        """memory_graph._build_graphiti() raises RuntimeError when
        GEMINI_API_KEY isn't set — recall() must degrade to the table, not
        raise, matching every other non-blocking recall path in this module."""
        rows = [{"id": "2", "source": "c", "target": "d"}]
        with patch("core.platform.unified_memory._supabase_raw", return_value=_fake_table_result(rows)), patch("core.platform.memory_graph.search", new=AsyncMock(side_effect=RuntimeError("GEMINI_API_KEY not set"))):
            result = recall(MemoryType.RELATIONSHIPS, query="anything")
        assert result == rows

    def test_group_ids_filter_is_passed_through(self):
        with patch("core.platform.memory_graph.search", new=AsyncMock(return_value=[])) as mock_search:
            recall(MemoryType.RELATIONSHIPS, query="q", group_ids=["health-intelligence"])
        mock_search.assert_awaited_once_with("q", num_results=10, group_ids=["health-intelligence"])


class TestRememberRelationships:
    """USS-TJR-MSN-0378 Stream 5: remember(RELATIONSHIPS, ...) previously had
    no write path at all — this covers the new memory_graph.add_fact() route."""

    def test_writes_via_memory_graph_add_fact(self):
        with patch("core.platform.memory_graph.add_fact", new=AsyncMock(return_value=True)) as mock_add:
            result = remember(MemoryType.RELATIONSHIPS, "Captain deferred MSN-0388", user_id="captain")
        mock_add.assert_awaited_once_with(
            "Captain deferred MSN-0388", group_id="captain", workbench=None,
        )
        assert result == {"added": True}

    def test_passes_workbench_from_metadata(self):
        with patch("core.platform.memory_graph.add_fact", new=AsyncMock(return_value=True)) as mock_add:
            remember(
                MemoryType.RELATIONSHIPS, "fact text", user_id="captain",
                metadata={"workbench": "xo"},
            )
        mock_add.assert_awaited_once_with("fact text", group_id="captain", workbench="xo")

    def test_returns_empty_dict_on_failure(self):
        with patch("core.platform.memory_graph.add_fact", new=AsyncMock(return_value=False)):
            result = remember(MemoryType.RELATIONSHIPS, "fact text", user_id="captain")
        assert result == {}

    def test_returns_empty_dict_on_exception(self):
        with patch("core.platform.memory_graph.add_fact", new=AsyncMock(side_effect=RuntimeError("boom"))):
            result = remember(MemoryType.RELATIONSHIPS, "fact text", user_id="captain")
        assert result == {}
