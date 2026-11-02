"""Tests for intelligence/emergency_alerts.py's alert_silences wiring
(migration 0205) — _send_emergency_warning_emails() must skip a silenced
alert without sending an email or setting emergency_email_sent_at, and
must behave exactly as before when nothing is silenced."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import intelligence.emergency_alerts as ea


def _row(**overrides) -> dict:
    base = {
        "id": "alert-1",
        "headline": "Emergency Warning issued",
        "jurisdiction": "NSW",
        "alert_type": "bushfire",
        "location": "Somewhere, NSW",
        "description": "Details here.",
        "canonical_url": None,
        "issued_at": "2026-09-13T00:00:00Z",
    }
    base.update(overrides)
    return base


class TestSendEmergencyWarningEmails:
    def test_no_rows_returns_zero_without_checking_silences(self):
        with patch.object(ea, "supabase_get", return_value=[]), \
             patch.object(ea.alert_silences, "list_active_silences") as mock_silences:
            sent = ea._send_emergency_warning_emails("nsw_rfs")
        assert sent == 0
        mock_silences.assert_not_called()

    def test_silence_never_suppresses_an_emergency_warning(self):
        rows = [_row()]
        silence = {"id": "sil-1", "reason": "planned burn", "match_jurisdiction": "NSW"}
        with patch.object(ea, "supabase_get", return_value=rows), \
             patch.object(ea.alert_silences, "list_active_silences", return_value=[silence]), \
             patch.object(ea, "send_email", return_value=True) as mock_send, \
             patch.object(ea, "_supabase_request") as mock_patch:
            sent = ea._send_emergency_warning_emails("nsw_rfs")
        assert sent == 1
        mock_send.assert_called_once()
        assert mock_patch.call_count == 2  # sent flag + tier/wording metadata

    def test_everything_silence_does_not_mute_emergency_warnings(self):
        rows = [_row()]
        silence = {"id": "sil-all", "reason": "maintenance window"}
        with patch.object(ea, "supabase_get", return_value=rows), \
             patch.object(ea.alert_silences, "list_active_silences", return_value=[silence]), \
             patch.object(ea, "send_email", return_value=True) as mock_send, \
             patch.object(ea, "_supabase_request"):
            assert ea._send_emergency_warning_emails("nsw_rfs") == 1
        mock_send.assert_called_once()

    def test_unsilenced_alert_sends_email_as_before(self):
        rows = [_row()]
        with patch.object(ea, "supabase_get", return_value=rows), \
             patch.object(ea.alert_silences, "list_active_silences", return_value=[]), \
             patch.object(ea, "send_email", return_value=True) as mock_send, \
             patch.object(ea, "_supabase_request") as mock_patch:
            sent = ea._send_emergency_warning_emails("nsw_rfs")
        assert sent == 1
        mock_send.assert_called_once()
        assert mock_patch.call_count == 2  # sent flag + tier/wording metadata

    def test_silence_lookup_failure_degrades_to_no_silences(self):
        rows = [_row()]
        with patch.object(ea, "supabase_get", return_value=rows), \
             patch.object(ea.alert_silences, "list_active_silences", side_effect=RuntimeError("db down")), \
             patch.object(ea, "send_email", return_value=True) as mock_send, \
             patch.object(ea, "_supabase_request"):
            sent = ea._send_emergency_warning_emails("nsw_rfs")
        assert sent == 1
        mock_send.assert_called_once()

    def test_unnotified_read_failure_returns_zero(self):
        with patch.object(ea, "supabase_get", side_effect=Exception("timeout")), \
             patch.object(ea.alert_silences, "list_active_silences") as mock_silences:
            sent = ea._send_emergency_warning_emails("nsw_rfs")
        assert sent == 0
        mock_silences.assert_not_called()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
