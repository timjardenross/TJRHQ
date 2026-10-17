"""governance-cache-sweep re-queues completed captured_items every 24h; that
re-processing must not relaunch a full research mission for an item whose
research already completed (it drained the Gemini spend cap)."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

sys.modules.setdefault("supabase", types.SimpleNamespace(create_client=lambda *a, **k: MagicMock()))

from core.inbox import orchestrator


def _process(item: dict) -> tuple[dict, MagicMock]:
    """Run process_captured_item on `item`; return (final update, thread mock)."""
    db = MagicMock()
    db.enabled.return_value = True
    db.get.return_value = item
    db.exists_url.return_value = None
    with patch.object(orchestrator, "_db", db), \
         patch.object(orchestrator, "_classify", return_value="research"), \
         patch.object(orchestrator, "_rate_importance", return_value="medium"), \
         patch.object(orchestrator, "_summarize", return_value=("s", "rule")), \
         patch("core.inbox.governance_integration.apply_governance_assessment", return_value={}), \
         patch.object(orchestrator.threading, "Thread") as thread:
        orchestrator.process_captured_item(item["id"])
    final = db.update.call_args_list[-1].args[2]
    return final, thread


def test_completed_research_is_not_relaunched():
    final, thread = _process({"id": "i1", "title": "t", "raw_text": "r", "research_status": "completed"})
    thread.assert_not_called()
    assert "research_status" not in final


def test_running_research_is_not_relaunched():
    _, thread = _process({"id": "i2", "title": "t", "raw_text": "r", "research_status": "running"})
    thread.assert_not_called()


def test_new_item_still_gets_research():
    final, thread = _process({"id": "i3", "title": "t", "raw_text": "r", "research_status": None})
    thread.assert_called_once()
    assert final["research_status"] == "pending"


def test_failed_research_can_still_retry():
    final, thread = _process({"id": "i4", "title": "t", "raw_text": "r", "research_status": "failed"})
    thread.assert_called_once()
    assert final["research_status"] == "pending"
