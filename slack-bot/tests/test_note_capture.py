"""Tests for commands/note_capture.py (EXEC-010C WP4)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BOT_DIR = REPO_ROOT / "slack-bot"
for p in (str(REPO_ROOT), str(BOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from commands.note_capture import handle_note_capture


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_supabase(note_id: str = "uuid-1234") -> MagicMock:
    sb = MagicMock()
    chain = MagicMock()
    chain.execute.return_value.data = [{"id": note_id}]
    sb.table.return_value.insert.return_value = chain
    return sb


# ── Empty / missing content ────────────────────────────────────────────────────

def test_empty_text_returns_usage():
    out = handle_note_capture("", "U123", "C456", _make_supabase())
    assert "/note" in out
    assert "Usage" in out


def test_whitespace_only_returns_usage():
    out = handle_note_capture("   ", "U123", "C456", _make_supabase())
    assert "Usage" in out


# ── No supabase client ─────────────────────────────────────────────────────────

def test_no_supabase_returns_warning():
    out = handle_note_capture("some content", "U123", "C456", None)
    assert "not configured" in out.lower() or "unavailable" in out.lower()


# ── Successful capture ─────────────────────────────────────────────────────────

def test_successful_capture_returns_confirmation():
    sb = _make_supabase("uuid-1234")
    out = handle_note_capture("Explore API-first auth", "U123", "C456", sb)
    assert "captured" in out.lower()
    assert "uuid-123" in out  # short ID prefix


def test_successful_capture_inserts_correct_record():
    sb = _make_supabase()
    handle_note_capture("Test note content", "U123", "C456", sb)
    insert_call_args = sb.table.return_value.insert.call_args[0][0]
    assert insert_call_args["raw_content"] == "Test note content"
    assert insert_call_args["source"] == "slack"
    assert insert_call_args["status"] == "CAPTURED"


def test_successful_capture_includes_navigation_hint():
    sb = _make_supabase()
    out = handle_note_capture("Some idea", "U123", "C456", sb)
    assert "captains-notebook" in out or "notebook" in out.lower()


# ── Supabase failure ───────────────────────────────────────────────────────────

def test_supabase_exception_returns_error_message():
    sb = MagicMock()
    sb.table.return_value.insert.return_value.execute.side_effect = Exception("DB error")
    out = handle_note_capture("Content", "U123", "C456", sb)
    assert ":x:" in out or "failed" in out.lower()


def test_supabase_empty_data_returns_warning():
    sb = MagicMock()
    sb.table.return_value.insert.return_value.execute.return_value.data = []
    out = handle_note_capture("Content", "U123", "C456", sb)
    assert "warning" in out.lower() or "no data" in out.lower()


# ── Content trimming ───────────────────────────────────────────────────────────

def test_content_is_stripped_before_insert():
    sb = _make_supabase()
    handle_note_capture("  spaces around  ", "U123", "C456", sb)
    insert_args = sb.table.return_value.insert.call_args[0][0]
    assert insert_args["raw_content"] == "spaces around"
