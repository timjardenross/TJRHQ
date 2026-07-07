"""Tests for notebook_route_executor.py (EXEC-010C WP1)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BOT_DIR = REPO_ROOT / "slack-bot"
for p in (str(REPO_ROOT), str(BOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.notebook.notebook_route_executor import (
    ExecutionResult,
    ROUTE_MAP,
    SUPPORTED_ROUTES,
    execute_all_routed,
    execute_route,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_supabase(note_data: dict, insert_id: str = "artefact-123") -> MagicMock:
    """Build a minimal Supabase mock returning the given note and a successful insert."""
    sb = MagicMock()

    # intelligence_notes select chain
    select_chain = MagicMock()
    select_chain.execute.return_value.data = note_data
    sb.table.return_value.select.return_value.eq.return_value.single.return_value = select_chain

    # insert chain
    insert_chain = MagicMock()
    insert_chain.execute.return_value.data = [{"id": insert_id}]
    sb.table.return_value.insert.return_value = insert_chain

    # update chain
    update_chain = MagicMock()
    update_chain.execute.return_value.data = []
    sb.table.return_value.update.return_value.eq.return_value = update_chain

    return sb


def _routed_note(**overrides) -> dict:
    base = {
        "id": "note-001",
        "title": "Test note",
        "raw_content": "Some raw content",
        "status": "ROUTED",
        "recommended_route": "captain",
        "routed_to_type": None,
        "routed_to_id": None,
        "triage_summary": "Summary text",
        "classification": "strategic",
        "value_score": 0.7,
    }
    base.update(overrides)
    return base


# ── ROUTE_MAP / SUPPORTED_ROUTES ──────────────────────────────────────────────

def test_route_map_keys_are_valid_triage_routes():
    valid_triage = {"captain", "xo", "number_one", "officer", "knowledge"}
    assert set(ROUTE_MAP.keys()) == valid_triage


def test_supported_routes_are_non_empty():
    assert len(SUPPORTED_ROUTES) >= 5


# ── execute_route — happy paths ────────────────────────────────────────────────

def test_execute_route_captain_creates_mission():
    note = _routed_note(recommended_route="captain")
    sb = _make_supabase(note)

    result = execute_route("note-001", sb)

    assert result.success
    assert result.route_type == "MISSION"
    assert result.artefact_table == "missions"
    assert result.error is None
    assert not result.skipped


def test_execute_route_xo_creates_mission():
    note = _routed_note(recommended_route="xo")
    sb = _make_supabase(note)
    result = execute_route("note-001", sb)
    assert result.route_type == "MISSION"


def test_execute_route_number_one_creates_improvement():
    note = _routed_note(recommended_route="number_one")
    sb = _make_supabase(note)
    result = execute_route("note-001", sb)
    assert result.route_type == "IMPROVEMENT"
    assert result.artefact_table == "decisions"


def test_execute_route_knowledge_creates_knowledge_article():
    note = _routed_note(recommended_route="knowledge")
    sb = _make_supabase(note)
    result = execute_route("note-001", sb)
    assert result.route_type == "KNOWLEDGE_ARTICLE"
    assert result.artefact_table == "lessons_learned"


def test_execute_route_with_explicit_route_type_overrides_recommended():
    note = _routed_note(recommended_route="captain")
    sb = _make_supabase(note)
    result = execute_route("note-001", sb, route_type="RESEARCH_REQUEST")
    assert result.route_type == "RESEARCH_REQUEST"
    assert result.artefact_table == "research_memory"


# ── execute_route — idempotency ────────────────────────────────────────────────

def test_execute_route_skips_if_routed_to_id_present():
    note = _routed_note(routed_to_id="M-existing", recommended_route="captain")
    sb = _make_supabase(note)
    result = execute_route("note-001", sb)
    assert result.skipped
    assert result.artefact_id == "M-existing"
    assert "Already executed" in (result.skip_reason or "")


def test_execute_route_skips_non_routed_note():
    note = _routed_note(status="READY_FOR_ROUTING", routed_to_id=None)
    sb = _make_supabase(note)
    result = execute_route("note-001", sb)
    assert result.skipped
    assert "READY_FOR_ROUTING" in (result.skip_reason or "")


def test_execute_route_errors_on_missing_note():
    sb = _make_supabase(None)
    result = execute_route("ghost-id", sb)
    assert result.error is not None
    assert "not found" in result.error.lower()


# ── execute_route — traceability write-back ────────────────────────────────────

def test_execute_route_writes_traceability_fields():
    note = _routed_note(recommended_route="captain")
    sb = _make_supabase(note)
    execute_route("note-001", sb, routed_by="captain")
    # update should have been called on intelligence_notes
    update_calls = [str(c) for c in sb.table.call_args_list]
    assert any("intelligence_notes" in c for c in update_calls)


# ── ExecutionResult ────────────────────────────────────────────────────────────

def test_execution_result_success_property():
    r = ExecutionResult(note_id="n1", route_type="MISSION", artefact_id="M-123")
    assert r.success is True


def test_execution_result_no_artefact_is_not_success():
    r = ExecutionResult(note_id="n1", route_type="MISSION")
    assert r.success is False


# ── execute_all_routed ─────────────────────────────────────────────────────────

def test_execute_all_routed_processes_pending_notes():
    sb = MagicMock()

    # Query for ROUTED notes with no routed_to_id
    sb.table.return_value.select.return_value.eq.return_value.is_.return_value.execute.return_value.data = [
        {"id": "note-A"}, {"id": "note-B"},
    ]

    # Each individual note fetch + insert/update
    note_a = _routed_note(id="note-A", recommended_route="captain")
    note_b = _routed_note(id="note-B", recommended_route="knowledge")

    fetch_chain = MagicMock()
    fetch_chain.execute.side_effect = [
        MagicMock(data=note_a),
        MagicMock(data=note_b),
    ]
    sb.table.return_value.select.return_value.eq.return_value.single.return_value = fetch_chain

    insert_chain = MagicMock()
    insert_chain.execute.return_value.data = [{"id": "artefact-x"}]
    sb.table.return_value.insert.return_value = insert_chain

    update_chain = MagicMock()
    update_chain.execute.return_value.data = []
    sb.table.return_value.update.return_value.eq.return_value = update_chain

    results = execute_all_routed(sb, routed_by="test")
    assert len(results) == 2
