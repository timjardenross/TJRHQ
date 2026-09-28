"""Mission writers must send rows the live `missions` table accepts.

The live table (created outside the migration system) requires `mission_id`
(unique; `id` is a generated uuid) and `repo`, limits `status` with a CHECK and
`priority` to P0-P3, and has no `owner` / `updated_by` column. Every writer
below used to send `id`/`owner`/`updated_by`/`domain` and no `repo`, so each
insert was rejected with a 400 — silently, because all of them are best-effort.

The corrected payloads were also checked against the real table in a rolled-back
transaction (Supabase, 2026-09-28).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
for sub in ("", "platform-runtime"):
    if str(ROOT / sub) not in sys.path:
        sys.path.insert(0, str(ROOT / sub))

import command_memory_integration as cmi
import mission_logger
from lib.notebook import notebook_route_executor

# Columns that exist on the live missions table.
LIVE_COLUMNS = {
    "id", "mission_id", "title", "description", "task_type", "status", "repo", "branch_name",
    "pr_url", "created_by", "created_at", "updated_at", "mission_type", "closed_at",
    "outcome_rating", "priority", "rework_of", "strategic_objective_id",
}


def _assert_insertable(record: dict) -> None:
    assert set(record) <= LIVE_COLUMNS, f"unknown columns: {set(record) - LIVE_COLUMNS}"
    assert record["mission_id"] and record["title"] and record["repo"]
    assert "id" not in record  # a generated uuid; a mission id string would fail the cast
    assert record["status"] in cmi.LIVE_MISSION_STATUSES
    if "priority" in record:
        assert record["priority"] in cmi.LIVE_MISSION_PRIORITIES


# ── CommandMemoryClient ─────────────────────────────────────────────────────

def _client():
    client = cmi.CommandMemoryClient.__new__(cmi.CommandMemoryClient)
    client._initialized = True
    client.url, client.key = "https://example.supabase.co", "key"
    return client


def test_insert_with_on_conflict_ignores_duplicates():
    client = _client()
    with patch.object(client, "request", return_value=[]) as req:  # PostgREST: ignored duplicate -> []
        assert client.insert("missions", {"mission_id": "M-1"}, on_conflict="mission_id") is True
    method, path, _payload = req.call_args.args
    assert (method, path) == ("POST", "/rest/v1/missions?on_conflict=mission_id")
    assert req.call_args.kwargs["extra_headers"]["Prefer"] == "resolution=ignore-duplicates,return=representation"


def test_insert_with_on_conflict_still_reports_a_real_failure():
    client = _client()
    with patch.object(client, "request", return_value=None):  # HTTP error
        assert client.insert("missions", {"mission_id": "M-1"}, on_conflict="mission_id") is False


def test_plain_insert_is_unchanged():
    client = _client()
    with patch.object(client, "request", return_value=[{"id": "x"}]) as req:
        assert client.insert("command_memory_records", {"id": "x"}) is True
    assert req.call_args.args[1] == "/rest/v1/command_memory_records"
    assert req.call_args.kwargs["extra_headers"] == {"Prefer": "return=representation"}
    with patch.object(client, "request", return_value=[]):
        assert client.insert("command_memory_records", {"id": "x"}) is False  # empty = nothing written


def test_update_can_match_on_another_key():
    client = _client()
    with patch.object(client, "request", return_value=[{"mission_id": "M-1"}]) as req:
        assert client.update("missions", "M-1", {"status": "Closed"}, key="mission_id") is True
    assert req.call_args.args[1] == "/rest/v1/missions?mission_id=eq.M-1"
    with patch.object(client, "request", return_value=[{"id": "d"}]) as req:
        client.update("command_memory_records", "DEC-1", {"status": "x"})
    assert req.call_args.args[1] == "/rest/v1/command_memory_records?id=eq.DEC-1"


# ── Writers ─────────────────────────────────────────────────────────────────

def test_officer_created_mission_is_insertable():
    fake = MagicMock()
    fake.insert.return_value = True
    with patch.object(cmi, "get_client", return_value=fake), \
         patch.object(cmi.id_registry, "next_id", side_effect=lambda prefix: f"{prefix}-0001"), \
         patch("core.governance.authority_validator.can_officer", return_value=(True, "ok")), \
         patch("core.governance.authority_validator.audit_authority_action"):
        mission_id = cmi.create_mission_from_officer(
            officer="chief_engineer", title="T", summary="S", priority="P1",
            recommended_owner="number_one", captain_override=True,
        )
    assert mission_id == "MSN-0001"
    mission_call = next(c for c in fake.insert.call_args_list if c.args[0] == "missions")
    record = mission_call.args[1]
    _assert_insertable(record)
    assert record["priority"] == "P1"
    assert "Recommended Owner:** number_one" in record["description"]  # owner lives in the description
    assert mission_call.kwargs == {"on_conflict": "mission_id"}


def test_officer_priority_outside_p0_p3_is_omitted_not_rejected():
    fake = MagicMock()
    fake.insert.return_value = True
    with patch.object(cmi, "get_client", return_value=fake), \
         patch.object(cmi.id_registry, "next_id", side_effect=lambda prefix: f"{prefix}-0002"), \
         patch("core.governance.authority_validator.can_officer", return_value=(True, "ok")), \
         patch("core.governance.authority_validator.audit_authority_action"):
        cmi.create_mission_from_officer(officer="x", title="T", summary="S", priority="P5", captain_override=True)
    record = next(c for c in fake.insert.call_args_list if c.args[0] == "missions").args[1]
    _assert_insertable(record)
    assert "priority" not in record


def test_mission_logger_delegates_to_the_schema_correct_writer():
    with patch.object(cmi, "save_mission_to_command_memory") as save:
        mission_logger._supabase_insert_mission(
            mission_id="M-20260928-000000", title="T", domain="operations", status="Idea",
        )
    save.assert_called_once_with(mission_id="M-20260928-000000", title="T", created_by="commander", status="Idea")


def test_notebook_mission_is_insertable():
    sb = MagicMock()
    note = {"id": "note-1", "title": "Capture", "raw_content": "body", "triage_summary": "summary"}
    mission_id, table = notebook_route_executor._create_mission(note, sb)
    assert table == "missions" and mission_id
    record = sb.table.return_value.insert.call_args.args[0]
    _assert_insertable(record)
    assert record["mission_id"] == mission_id
    assert record["created_by"] == "notebook" and record["status"] == "Idea"
    json.dumps(record)  # serialisable as sent
