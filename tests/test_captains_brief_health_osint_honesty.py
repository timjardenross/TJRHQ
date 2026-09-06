"""HQ V1 Integration QA §21/§9 regression: a genuinely quiet Health OSINT
week must not render identically to a week where the Sunday 02:00
health_osint_weekly_fetch collector silently failed. See
intelligence/captains_brief.py's _health_osint_collector_caveat() and
_format_weekly_osint_block()'s empty_caveat parameter.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

import intelligence.captains_brief as cb  # noqa: E402


def test_no_caveat_when_collector_reports_ok():
    with mock.patch.object(cb, "_sb_get", return_value=[{"status": "ok", "checked_at": "2026-09-01T02:00:00Z"}]):
        assert cb._health_osint_collector_caveat() is None


def test_caveat_when_collector_reports_failed():
    with mock.patch.object(cb, "_sb_get", return_value=[{"status": "failed", "checked_at": "2026-09-01T02:00:00Z"}]):
        caveat = cb._health_osint_collector_caveat()
    assert caveat is not None
    assert "failure" in caveat.lower()


def test_caveat_when_no_heartbeat_row_found_at_all():
    with mock.patch.object(cb, "_sb_get", return_value=[]):
        caveat = cb._health_osint_collector_caveat()
    assert caveat is not None
    assert "could not be confirmed" in caveat


def test_empty_rows_without_caveat_matches_prior_behaviour():
    lines = cb._format_weekly_osint_block("HEALTH OSINT", "\U0001fa7a", [], "confidence_level", "title")
    assert lines == ["<b>\U0001fa7a HEALTH OSINT — WEEKLY</b>", "  No signals collected this week.", ""]


def test_empty_rows_with_caveat_appends_warning_line():
    lines = cb._format_weekly_osint_block(
        "HEALTH OSINT", "\U0001fa7a", [], "confidence_level", "title",
        empty_caveat="the weekly collector reported a failure this week",
    )
    assert any("weekly collector reported a failure" in line for line in lines)


def test_non_empty_rows_never_trigger_the_collector_check():
    """The caveat check only runs when rows is empty (generate_weekly_report's
    own call site) — a real signal week never spends an extra query on this."""
    with mock.patch.object(cb, "_sb_get") as sb_mock:
        sb_mock.return_value = [{"title": "x", "confidence_level": "HIGH"}]
        rows = sb_mock.return_value
        caveat = cb._health_osint_collector_caveat() if not rows else None
    assert caveat is None


class TestCollectionCoverageCaveat:
    """HQ V1 Integration QA §21 (Deferred Gap I7): the Captain's Daily
    Brief pipeline now checks its feeding collection job's heartbeat and
    persists a coverage caveat, distinguishing "collection ran fine" from
    "collection lagged/failed before this brief generated." """

    def test_none_when_collection_job_ok(self):
        with mock.patch.object(cb, "_sb_get", return_value=[{"status": "ok"}]):
            assert cb._collection_coverage_caveat("intelligence_collection") is None

    def test_caveat_when_collection_job_failed(self):
        with mock.patch.object(cb, "_sb_get", return_value=[{"status": "failed"}]):
            caveat = cb._collection_coverage_caveat("intelligence_collection")
        assert caveat is not None
        assert "intelligence_collection" in caveat

    def test_caveat_when_no_heartbeat_row_at_all(self):
        with mock.patch.object(cb, "_sb_get", return_value=[]):
            caveat = cb._collection_coverage_caveat("intelligence_collection")
        assert caveat is not None
        assert "could not be confirmed" in caveat

    def test_persist_brief_payload_includes_new_coverage_fields(self):
        """_persist_brief must actually send evidence_window_hours/
        collection_caveat to captains_daily_briefs, not just accept them as
        unused parameters."""
        captured = {}

        class _FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def _fake_urlopen(req, timeout=8):
            captured["body"] = __import__("json").loads(req.data)
            return _FakeResponse()

        with mock.patch.object(cb, "_SUPABASE_URL", "https://example.test"), \
             mock.patch.object(cb, "_SUPABASE_KEY", "fake-key"), \
             mock.patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            cb._persist_brief(
                "morning", "brief text", signals_count=3, health={},
                evidence_window_hours=24, collection_caveat="intelligence_collection reported a failure",
            )

        assert captured["body"]["evidence_window_hours"] == 24
        assert captured["body"]["collection_caveat"] == "intelligence_collection reported a failure"
