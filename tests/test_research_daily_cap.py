"""Hard daily ceiling on research missions (each is ~8-10 Gemini calls)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.modules.setdefault("supabase", types.SimpleNamespace(create_client=lambda *a, **k: MagicMock()))
sys.path.insert(0, str(ROOT / "core" / "coordination"))

import research_orchestration as ro


def _client_with_count(count):
    client = MagicMock()
    client.table.return_value.select.return_value.gte.return_value.limit.return_value.execute.return_value = (
        MagicMock(count=count)
    )
    return client


def _env(monkeypatch, cap="30"):
    monkeypatch.setenv("SUPABASE_URL", "http://x")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    monkeypatch.setenv("RESEARCH_MAX_MISSIONS_PER_DAY", cap)


def test_under_cap_allows(monkeypatch):
    _env(monkeypatch)
    with patch("supabase.create_client", return_value=_client_with_count(29)):
        assert ro._daily_mission_cap_reached() == (False, 29, 30)


def test_at_cap_blocks(monkeypatch):
    _env(monkeypatch)
    with patch("supabase.create_client", return_value=_client_with_count(30)):
        assert ro._daily_mission_cap_reached() == (True, 30, 30)


def test_zero_disables(monkeypatch):
    _env(monkeypatch, cap="0")
    assert ro._daily_mission_cap_reached() == (False, 0, 0)


def test_db_error_fails_open(monkeypatch):
    _env(monkeypatch)
    with patch("supabase.create_client", side_effect=RuntimeError("db down")):
        assert ro._daily_mission_cap_reached()[0] is False


def test_mission_refused_when_capped(monkeypatch):
    with patch.object(ro, "_daily_mission_cap_reached", return_value=(True, 30, 30)), \
         patch.object(ro.ResearchOrchestrator, "_decompose_research_topic") as decompose:
        result = ro.ResearchOrchestrator().run_research_mission("a long enough topic to research")
    decompose.assert_not_called()
    assert result.status == "error"
    assert "cap reached" in result.errors[0]
