"""Tests for intelligence/emergency_alert_summary.py's alert_silences
wiring (migration 0205) — _exclude_silenced() must drop any alert matching
an active silence before the hourly digest fingerprints, prompts, or
narrates the active set, and must degrade to "nothing silenced" on a
silence-lookup failure rather than blocking a real summary."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import intelligence.emergency_alert_summary as eas


def _alert(**overrides) -> dict:
    base = {
        "id": "a1",
        "jurisdiction": "NSW",
        "alert_type": "hazard_reduction",
        "severity": "advice",
        "status": "active",
        "headline": "Advice — planned hazard reduction",
        "location": None,
        "description": None,
        "issued_at": None,
        "source_key": "nsw_rfs",
    }
    base.update(overrides)
    return base


def _silence(**overrides) -> dict:
    base = {
        "id": "sil-1",
        "reason": "planned burn",
        "match_jurisdiction": None,
        "match_alert_type": None,
        "match_severity": None,
        "match_source_key": None,
    }
    base.update(overrides)
    return base


class TestExcludeSilenced:
    def test_no_silences_returns_alerts_unchanged(self):
        alerts = [_alert(id="a1"), _alert(id="a2")]
        with patch.object(eas.alert_silences, "list_active_silences", return_value=[]):
            result = eas._exclude_silenced(alerts)
        assert result == alerts

    def test_matching_silence_excludes_alert(self):
        alerts = [_alert(id="a1", jurisdiction="NSW"), _alert(id="a2", jurisdiction="QLD")]
        silence = _silence(match_jurisdiction="NSW")
        with patch.object(eas.alert_silences, "list_active_silences", return_value=[silence]):
            result = eas._exclude_silenced(alerts)
        assert [a["id"] for a in result] == ["a2"]

    def test_silence_lookup_failure_returns_alerts_unchanged(self):
        alerts = [_alert(id="a1")]
        with patch.object(eas.alert_silences, "list_active_silences", side_effect=RuntimeError("db down")):
            result = eas._exclude_silenced(alerts)
        assert result == alerts


class TestRunSilencing:
    def test_silenced_alert_excluded_from_count_and_prompt(self):
        """A run where the only active alert is silenced must count it as
        0 active alerts and never pass it to the LLM prompt/verbatim
        section — whether that run then holds for the daily digest or
        proceeds to generate a "nothing urgent" summary depends on the
        real wall-clock digest-hour logic (untouched by this change,
        see _DIGEST_HOUR_UTC), so both outcomes are mocked to succeed and
        only the alert-exclusion behavior is asserted."""
        alerts = [_alert(id="a1", severity="watch_and_act")]
        silence = _silence()  # all-null: silences everything

        with patch.object(eas, "supabase_get", return_value=alerts), \
             patch.object(eas.alert_silences, "list_active_silences", return_value=[silence]), \
             patch.object(eas, "_get_state", return_value={"last_fingerprint": None, "last_sent_at": None}), \
             patch.object(eas, "_generate_summary", return_value=("nothing urgent", "gemini")) as mock_generate, \
             patch.object(eas, "send_email", return_value=True), \
             patch.object(eas, "_set_state"), \
             patch.object(eas, "record_heartbeat"):
            result = eas.run()

        assert result["count"] == 0
        if mock_generate.called:
            prompt_arg = mock_generate.call_args[0][0]
            assert prompt_arg == []

    def test_unsilenced_alert_reaches_summary_generation(self):
        alerts = [_alert(id="a1", severity="watch_and_act")]

        with patch.object(eas, "supabase_get", return_value=alerts), \
             patch.object(eas.alert_silences, "list_active_silences", return_value=[]), \
             patch.object(eas, "_get_state", return_value={"last_fingerprint": None, "last_sent_at": None}), \
             patch.object(eas, "_generate_summary", return_value=("summary text", "gemini")), \
             patch.object(eas, "send_email", return_value=True), \
             patch.object(eas, "_set_state"), \
             patch.object(eas, "record_heartbeat"):
            result = eas.run()

        assert result["count"] == 1
        assert result["emailed"] is True
