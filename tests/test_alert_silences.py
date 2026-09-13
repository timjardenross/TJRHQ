"""Tests for core/platform/alert_silences.py — Alertmanager-style temporary
suppression (migration 0205)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))

import alert_silences


def _silence(**overrides) -> dict:
    base = {
        "id": "sil-1",
        "reason": "planned hazard-reduction burn",
        "starts_at": "2026-09-01T00:00:00+00:00",
        "ends_at": "2026-09-02T00:00:00+00:00",
        "match_jurisdiction": None,
        "match_alert_type": None,
        "match_severity": None,
        "match_source_key": None,
    }
    base.update(overrides)
    return base


def _alert(**overrides) -> dict:
    base = {
        "jurisdiction": "NSW",
        "alert_type": "hazard_reduction",
        "severity": "emergency_warning",
        "source_key": "nsw_rfs",
    }
    base.update(overrides)
    return base


# ── _matches ─────────────────────────────────────────────────────────────────

class TestMatches:
    def test_all_null_matches_everything(self):
        assert alert_silences._matches(_silence(), _alert()) is True

    def test_single_field_match(self):
        s = _silence(match_jurisdiction="NSW")
        assert alert_silences._matches(s, _alert(jurisdiction="NSW")) is True
        assert alert_silences._matches(s, _alert(jurisdiction="QLD")) is False

    def test_all_fields_must_match(self):
        s = _silence(match_jurisdiction="NSW", match_alert_type="hazard_reduction")
        assert alert_silences._matches(s, _alert(jurisdiction="NSW", alert_type="hazard_reduction")) is True
        assert alert_silences._matches(s, _alert(jurisdiction="NSW", alert_type="bushfire")) is False

    def test_severity_and_source_key_fields(self):
        s = _silence(match_severity="emergency_warning", match_source_key="nsw_rfs")
        assert alert_silences._matches(s, _alert()) is True
        assert alert_silences._matches(s, _alert(source_key="qld_fire")) is False


# ── check_silence ────────────────────────────────────────────────────────────

class TestCheckSilence:
    def test_returns_none_when_no_silences(self):
        assert alert_silences.check_silence(_alert(), []) is None

    def test_returns_first_match(self):
        silences = [
            _silence(id="a", match_jurisdiction="QLD"),
            _silence(id="b", match_jurisdiction="NSW"),
        ]
        match = alert_silences.check_silence(_alert(jurisdiction="NSW"), silences)
        assert match is not None
        assert match["id"] == "b"

    def test_fetches_active_silences_when_none_passed(self):
        with patch.object(alert_silences, "list_active_silences", return_value=[_silence()]) as mock_list:
            match = alert_silences.check_silence(_alert())
        mock_list.assert_called_once()
        assert match is not None


# ── create_silence ───────────────────────────────────────────────────────────

class TestCreateSilence:
    def test_empty_reason_raises(self):
        with pytest.raises(ValueError, match="reason"):
            alert_silences.create_silence(reason="   ", ends_at="2026-09-02T00:00:00+00:00")

    def test_ends_before_starts_raises(self):
        with pytest.raises(ValueError, match="ends_at"):
            alert_silences.create_silence(
                reason="test",
                starts_at="2026-09-02T00:00:00+00:00",
                ends_at="2026-09-01T00:00:00+00:00",
            )

    def test_missing_credentials_raises_runtime_error(self):
        far_future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        with patch.object(alert_silences, "_URL", ""), patch.object(alert_silences, "_KEY", ""), \
             pytest.raises(RuntimeError, match="credentials"):
            alert_silences.create_silence(reason="test", ends_at=far_future)

    def test_posts_expected_body(self):
        class _FakeResp:
            def read(self): return b'[{"id": "new-sil"}]'
            def __enter__(self): return self
            def __exit__(self, *a): pass

        far_future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        with patch.object(alert_silences, "_URL", "https://example.supabase.co"), \
             patch.object(alert_silences, "_KEY", "test-key"), \
             patch("urllib.request.urlopen", return_value=_FakeResp()) as mock_urlopen:
            result = alert_silences.create_silence(
                reason="hazard reduction burn",
                ends_at=far_future,
                jurisdiction="NSW",
                alert_type="hazard_reduction",
            )
        assert result == {"id": "new-sil"}
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://example.supabase.co/rest/v1/alert_silences"


# ── list_active_silences ─────────────────────────────────────────────────────

class TestListActiveSilences:
    def test_queries_active_window(self):
        with patch.object(alert_silences, "supabase_get", return_value=[]) as mock_get:
            at = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
            alert_silences.list_active_silences(at=at)
        (path,), _ = mock_get.call_args
        assert "starts_at=lte." in path
        assert "ends_at=gte." in path
        assert "2026-09-01T12:00:00" in path

    def test_defaults_to_now(self):
        with patch.object(alert_silences, "supabase_get", return_value=[]) as mock_get:
            alert_silences.list_active_silences()
        assert mock_get.call_count == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
