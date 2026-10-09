"""USS-TJR-MSN-0412 Stream 4: the Supabase database-size line and 450 MB guard.

intelligence/db_size.py must (a) always render a line for the weekly report,
including when the size check fails, and (b) warn at most once per day at or
above the threshold, never raising into a brief.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

import intelligence.captains_brief as cb
from intelligence import db_size


class _Result:
    def __init__(self, ok=True, error=None):
        self.ok, self.error = ok, error


# --- format_line ------------------------------------------------------------

def test_line_shows_size_limit_and_percent():
    assert db_size.format_line(350.0) == "🗄 Supabase DB: 350 MB of 500 MB (70%)"


def test_line_flags_at_the_warning_threshold():
    assert "⚠️" in db_size.format_line(450.0)
    assert "⚠️" not in db_size.format_line(449.9)


def test_line_says_unavailable_instead_of_vanishing():
    line = db_size.format_line(None)
    assert "unavailable" in line and "Supabase DB" in line


# --- check_and_warn ---------------------------------------------------------

def _warn(tmp_path, size, now, notify):
    return db_size.check_and_warn(size, now=now, notify_fn=notify, state_path=tmp_path / "state.json")


def test_no_warning_below_threshold(tmp_path):
    notify = mock.Mock(return_value=_Result())
    assert _warn(tmp_path, 449.9, 1000.0, notify) is False
    notify.assert_not_called()


def test_warns_at_threshold_and_records_state(tmp_path):
    notify = mock.Mock(return_value=_Result())
    assert _warn(tmp_path, 450.0, 1000.0, notify) is True
    notify.assert_called_once()
    body = notify.call_args.args[0]
    assert "450 MB" in body and "500 MB" in body
    assert json.loads((tmp_path / "state.json").read_text())["last_warned"] == 1000.0


def test_cooldown_blocks_a_second_warning_within_24h(tmp_path):
    notify = mock.Mock(return_value=_Result())
    assert _warn(tmp_path, 470.0, 1000.0, notify) is True
    assert _warn(tmp_path, 470.0, 1000.0 + 23 * 3600, notify) is False
    assert notify.call_count == 1


def test_warns_again_after_the_cooldown(tmp_path):
    notify = mock.Mock(return_value=_Result())
    assert _warn(tmp_path, 470.0, 1000.0, notify) is True
    assert _warn(tmp_path, 470.0, 1000.0 + 24 * 3600 + 1, notify) is True
    assert notify.call_count == 2


def test_failed_send_is_not_recorded_so_it_retries(tmp_path):
    notify = mock.Mock(return_value=_Result(ok=False, error="boom"))
    assert _warn(tmp_path, 470.0, 1000.0, notify) is False
    assert not (tmp_path / "state.json").exists()


def test_corrupt_state_means_warn(tmp_path):
    (tmp_path / "state.json").write_text("not json")
    notify = mock.Mock(return_value=_Result())
    assert _warn(tmp_path, 470.0, 1000.0, notify) is True


def test_unknown_size_never_warns_and_never_raises(tmp_path):
    notify = mock.Mock(return_value=_Result())
    with mock.patch.object(db_size, "fetch_size_mb", return_value=None):
        assert db_size.check_and_warn(notify_fn=notify, state_path=tmp_path / "s.json") is False
    notify.assert_not_called()


def test_a_crashing_sender_never_breaks_the_brief(tmp_path):
    notify = mock.Mock(side_effect=RuntimeError("telegram down"))
    assert _warn(tmp_path, 470.0, 1000.0, notify) is False


# --- fetch_size_mb ----------------------------------------------------------

def test_fetch_converts_bytes_to_mb(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    resp = mock.MagicMock()
    resp.__enter__.return_value.read.return_value = str(350 * 1048576).encode()
    with mock.patch("urllib.request.urlopen", return_value=resp) as uo:
        assert db_size.fetch_size_mb() == 350.0
    req = uo.call_args.args[0]
    assert req.full_url.endswith("/rest/v1/rpc/get_db_size_bytes") and req.get_method() == "POST"


def test_fetch_returns_none_on_failure_or_missing_config(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert db_size.fetch_size_mb() is None
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
        assert db_size.fetch_size_mb() is None


# --- wiring into the existing briefs ---------------------------------------

def _stub_weekly(monkeypatch):
    for name, value in {
        "_get_weekly_tech_signals": [], "_get_weekly_health_signals": [],
        "_generate_tech_osint_summary": None, "_generate_health_osint_summary": None,
        "_get_weekly_content_activity": [], "_get_weekly_capacity": {}, "_get_weekly_outage_alerts": [],
        "_health_osint_collector_caveat": None,
    }.items():
        monkeypatch.setattr(cb, name, lambda *a, _v=value, **k: _v)


def test_weekly_report_contains_the_size_line(monkeypatch):
    _stub_weekly(monkeypatch)
    monkeypatch.setattr(db_size, "fetch_size_mb", lambda: 350.0)
    assert "Supabase DB: 350 MB of 500 MB (70%)" in cb.generate_weekly_report()


def test_weekly_report_still_renders_when_the_size_check_fails(monkeypatch):
    _stub_weekly(monkeypatch)
    monkeypatch.setattr(db_size, "fetch_size_mb", lambda: None)
    assert "size unavailable" in cb.generate_weekly_report()


def _stub_send(monkeypatch):
    monkeypatch.setattr(cb, "generate_morning_brief", lambda: "morning text")
    monkeypatch.setattr(cb, "generate_weekly_report", lambda: "weekly text")
    monkeypatch.setattr(cb, "_get_recent_signals", lambda hours=24: [])
    monkeypatch.setattr(cb, "_collection_coverage_caveat", lambda *_a, **_k: None)
    monkeypatch.setattr(cb, "_persist_brief", lambda *a, **k: None)
    monkeypatch.setattr(cb, "_get_capacity_today", dict)
    monkeypatch.setattr(cb, "_email_morning_brief", lambda text: None)
    monkeypatch.setattr(cb, "_send_telegram", lambda text: True)


def test_morning_brief_runs_the_daily_guard_once(monkeypatch):
    _stub_send(monkeypatch)
    guard = mock.Mock(return_value=False)
    monkeypatch.setattr(db_size, "check_and_warn", guard)
    assert cb.send_brief("morning") is True
    guard.assert_called_once_with()


def test_other_briefs_do_not_run_the_guard(monkeypatch):
    _stub_send(monkeypatch)
    guard = mock.Mock(return_value=False)
    monkeypatch.setattr(db_size, "check_and_warn", guard)
    assert cb.send_brief("weekly") is True
    guard.assert_not_called()
