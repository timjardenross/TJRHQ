"""Unit tests for scripts/memory/nightly_consolidation.py (USS-TJR-MSN-0378
Stream 5). All LLM and Supabase calls are mocked so these run fully offline,
same convention as tests/test_episodic_memory.py and test_unified_memory.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

pytestmark = pytest.mark.asyncio

from scripts.memory.nightly_consolidation import (
    _distill,
    consolidate_command_memory,
    consolidate_conversation_turns,
)


class TestDistill:
    async def test_parses_json_array_reply(self):
        with patch("telegram_bots.llm.generate_async", new=AsyncMock(return_value='["fact one", "fact two"]')):
            result = await _distill("captain: hello\nxo: hi")
        assert result == ["fact one", "fact two"]

    async def test_returns_empty_list_on_empty_json_array(self):
        with patch("telegram_bots.llm.generate_async", new=AsyncMock(return_value="[]")):
            result = await _distill("captain: hi\nxo: hi")
        assert result == []

    async def test_returns_empty_list_on_invalid_json(self):
        with patch("telegram_bots.llm.generate_async", new=AsyncMock(return_value="not json")):
            result = await _distill("captain: hi")
        assert result == []

    async def test_returns_empty_list_on_llm_failure(self):
        with patch("telegram_bots.llm.generate_async", new=AsyncMock(side_effect=RuntimeError("boom"))):
            result = await _distill("captain: hi")
        assert result == []

    async def test_returns_empty_list_on_none_reply(self):
        with patch("telegram_bots.llm.generate_async", new=AsyncMock(return_value=None)):
            result = await _distill("captain: hi")
        assert result == []

    async def test_returns_empty_list_for_empty_transcript(self):
        result = await _distill("")
        assert result == []

    async def test_strips_and_filters_blank_facts(self):
        with patch("telegram_bots.llm.generate_async", new=AsyncMock(return_value='[" a fact ", "", "  "]')):
            result = await _distill("captain: hi")
        assert result == ["a fact"]


def _fake_db_for_turns(turns: list[dict]) -> MagicMock:
    db = MagicMock()
    select_chain = (
        db.table.return_value.select.return_value
        .is_.return_value
        .order.return_value
        .order.return_value
        .limit.return_value
    )
    select_chain.execute.return_value.data = turns
    return db


class TestConsolidateConversationTurns:
    async def test_no_rows_is_a_noop(self):
        db = _fake_db_for_turns([])
        with patch("core.platform.unified_memory.remember") as mock_remember:
            result = await consolidate_conversation_turns(db)
        assert result == {"turns_read": 0, "facts_written": 0}
        mock_remember.assert_not_called()

    async def test_distills_per_chat_and_writes_facts(self):
        turns = [
            {"id": "t1", "chat_id": 111, "role": "captain", "text": "what's my capacity today?", "created_at": "2026-09-14T08:00:00Z"},
            {"id": "t2", "chat_id": 111, "role": "xo", "text": "confidence is 70%", "created_at": "2026-09-14T08:00:05Z"},
        ]
        db = _fake_db_for_turns(turns)
        with (
            patch("scripts.memory.nightly_consolidation._distill", new=AsyncMock(return_value=["Captain's capacity was 70% on 2026-09-14"])),
            patch("core.platform.unified_memory.remember", return_value={"added": True}) as mock_remember,
        ):
            result = await consolidate_conversation_turns(db)
        assert result == {"turns_read": 2, "facts_written": 1}
        mock_remember.assert_called_once()
        _, kwargs = mock_remember.call_args
        assert kwargs["metadata"] == {"workbench": "xo"}
        # consolidated_at update was issued for both turn ids
        db.table.return_value.update.assert_called_once()
        update_args = db.table.return_value.update.call_args[0][0]
        assert "consolidated_at" in update_args

    async def test_marking_consolidated_failure_does_not_raise(self):
        turns = [{"id": "t1", "chat_id": 1, "role": "captain", "text": "hi", "created_at": "2026-09-14T08:00:00Z"}]
        db = _fake_db_for_turns(turns)
        db.table.return_value.update.return_value.in_.return_value.execute.side_effect = RuntimeError("db down")
        with (
            patch("scripts.memory.nightly_consolidation._distill", new=AsyncMock(return_value=[])),
        ):
            result = await consolidate_conversation_turns(db)
        assert result["turns_read"] == 1


def _fake_db_for_decisions(rows: list[dict]) -> MagicMock:
    db = MagicMock()
    select_chain = db.table.return_value.select.return_value.gte.return_value.order.return_value
    select_chain.execute.return_value.data = rows
    return db


class TestConsolidateCommandMemory:
    async def test_no_rows_is_a_noop(self):
        db = _fake_db_for_decisions([])
        with patch("core.platform.unified_memory.remember") as mock_remember:
            result = await consolidate_command_memory(db)
        assert result == {"decisions_read": 0, "facts_written": 0}
        mock_remember.assert_not_called()

    async def test_distills_and_tags_command_memory_workbench(self):
        rows = [{"mission_id": "USS-TJR-MSN-0378", "decision_type": "scope", "reasoning": "chose additive migration", "outcome": "applied", "timestamp": "2026-09-14T09:00:00"}]
        db = _fake_db_for_decisions(rows)
        with (
            patch("scripts.memory.nightly_consolidation._distill", new=AsyncMock(return_value=["Chose additive migration for research_memory"])),
            patch("core.platform.unified_memory.remember", return_value={"added": True}) as mock_remember,
        ):
            result = await consolidate_command_memory(db)
        assert result == {"decisions_read": 1, "facts_written": 1}
        _, kwargs = mock_remember.call_args
        assert kwargs["metadata"] == {"workbench": "command-memory"}
