"""Mission 3 — the REMEMBER capability (context_service.py's /remember).

Answers "what have I told you that matters again now?" from existing
canonical domain data only (personal_tasks via the Personal Task
Attention Adapter, captured_items still pending) — no new Remember
table, no second resurfacing/capacity policy.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CA_DIR = _REPO_ROOT / "core" / "context-assembly"
_COORD_DIR = _REPO_ROOT / "core" / "coordination"
_HEALTH_DIR = _REPO_ROOT / "core" / "health"

for p in (_CA_DIR, _COORD_DIR, _HEALTH_DIR, _REPO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import context_service
import supabase_client  # noqa: F401 - imported so patch("supabase_client...") below has a resolvable module


def _personal_task(**overrides) -> dict:
    base = {
        "id": "pt-1", "title": "Buy dog food", "work_state": "captured",
        "urgency": 3, "importance": 3, "due_date": None,
        "deferral_count": 0, "follow_through_paused": False,
    }
    base.update(overrides)
    return base


def _captured_item(**overrides) -> dict:
    base = {
        "id": "ci-1", "title": "Something unresolved", "raw_text": "Something unresolved",
        "captured_at": "2026-09-01T00:00:00+00:00", "classification": "unclassified",
        "actionable": "ambiguous", "review_status": "unreviewed",
    }
    base.update(overrides)
    return base


class TestRemember:
    def test_only_can_wait_tasks_are_excluded(self):
        """A task that never crosses the attention adapter's bar (pure
        CAN_WAIT) doesn't belong in Remember -- it's not "coming back into
        view", it just hasn't left."""
        low_priority = _personal_task(id="low", urgency=1, importance=1)
        with patch("context_service._capacity_status_for_today", return_value="Green"), \
             patch("supabase_client.supabase_get", return_value=[low_priority]):
            result = context_service._http_remember()
        assert result["resurfacing_tasks"] == []

    def test_urgent_task_appears_in_resurfacing(self):
        urgent = _personal_task(id="urgent", urgency=5, importance=4)
        with patch("context_service._capacity_status_for_today", return_value="Green"), \
             patch("supabase_client.supabase_get", return_value=[urgent]):
            result = context_service._http_remember()
        refs = [i["ref"] for i in result["resurfacing_tasks"]]
        assert "urgent" in refs

    def test_red_capacity_suppresses_non_critical_task_via_shared_adapter(self):
        """No second capacity rule here -- Red demotes non-critical items
        to CAN_WAIT inside attention_items_from_personal_tasks() itself,
        which this endpoint's filter then naturally excludes."""
        important_not_critical = _personal_task(id="t1", importance=4, urgency=2)
        with patch("context_service._capacity_status_for_today", return_value="Red"), \
             patch("supabase_client.supabase_get", return_value=[important_not_critical]):
            result = context_service._http_remember()
        assert result["resurfacing_tasks"] == []

    def test_unresolved_captures_included(self):
        item = _captured_item(id="ci-9")
        with patch("context_service._capacity_status_for_today", return_value="Green"), \
             patch("supabase_client.supabase_get") as mock_get:
            mock_get.side_effect = lambda q: [item] if "captured_items" in q else []
            result = context_service._http_remember()
        ids = [c["id"] for c in result["unresolved_captures"]]
        assert "ci-9" in ids

    def test_unresolved_captures_capped_tighter_under_red(self):
        with patch("context_service._capacity_status_for_today", return_value="Red"), \
             patch("supabase_client.supabase_get") as mock_get:
            captured_calls = []

            def fake_get(q):
                if "captured_items" in q:
                    captured_calls.append(q)
                    return []
                return []
            mock_get.side_effect = fake_get
            context_service._http_remember()
        assert any("limit=3" in q for q in captured_calls)

    def test_personal_task_read_failure_degrades_gracefully(self):
        with patch("context_service._capacity_status_for_today", return_value="Green"), \
             patch("supabase_client.supabase_get", side_effect=RuntimeError("boom")):
            result = context_service._http_remember()
        assert result["resurfacing_tasks"] == []
        assert result["unresolved_captures"] == []
        assert result["capacity_status"] == "Green"

    def test_response_is_json_serializable(self):
        import json
        urgent = _personal_task(id="urgent", urgency=5, importance=4)
        with patch("context_service._capacity_status_for_today", return_value="Green"), \
             patch("supabase_client.supabase_get") as mock_get:
            mock_get.side_effect = lambda q: [urgent] if "personal_tasks" in q else [_captured_item()]
            result = context_service._http_remember()
        json.dumps(result)
