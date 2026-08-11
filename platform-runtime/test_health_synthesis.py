"""Tests for health_synthesis.py — /health-brief command.

Rewritten 2026-08-11 (Fleet Engineering Review backlog item) — the
previous version tested a much richer module: DailyLogStats/EventStats
dataclasses, run_weekly_synthesis() with Supabase persistence
(_supabase_upsert), health_events integration, a Health-Summary.md
write step, and an LLM-with-rule-based-fallback split modeled as two
named functions. None of that exists in commands/health_synthesis.py
anymore — it was deliberately simplified (see the module's own
docstring: "Public API: handle_health_brief(user_id, client)") to a
read-only fetch -> _summarise() -> optional _llm_synthesis() -> DM
flow, reading from analytics_health_daily instead of health_daily_logs
+ health_events, with no persistence step at all. This is not a
regression to undo — it's tested here as today's actual behavior.

The old privacy-boundary tests checked that a written supporting_data
payload excluded clinical fields; there is no write path anymore, so
the equivalent guarantee tested here is that _summarise() only ever
reads named fields from each row (nervous_system_state/energy/
sleep_hours/mood/posture) — an arbitrary/clinical key on a row can
never reach the outbound DM text, verified directly below.

Run: platform-runtime/.venv/bin/python -m pytest platform-runtime/test_health_synthesis.py -v
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from commands.health_synthesis import (
    _fetch_recent_logs,
    _summarise,
    _llm_synthesis,
    handle_health_brief,
)


# ── _summarise(): no data ───────────────────────────────────────────────────────

class TestSummariseNoData(unittest.TestCase):
    def test_no_rows_message(self):
        text = _summarise([])
        self.assertIn("No check-in data", text)
        self.assertIn("/health-check", text)


# ── _summarise(): aggregation ───────────────────────────────────────────────────

class TestSummariseAggregation(unittest.TestCase):
    def _rows(self):
        return [
            {"nervous_system_state": "calm", "energy": "high", "mood": "positive", "sleep_hours": 8.0},
            {"nervous_system_state": "calm", "energy": "moderate", "mood": "stable", "sleep_hours": 7.0},
            {"nervous_system_state": "dysregulated", "energy": "low", "mood": "low", "sleep_hours": 5.0},
        ]

    def test_nervous_system_counts_shown(self):
        text = _summarise(self._rows())
        self.assertIn("Calm: 2/3 days", text)
        self.assertIn("Dysregulated: 1/3 days", text)

    def test_dominant_state_called_out(self):
        text = _summarise(self._rows())
        self.assertIn("Dominant state this week: *Calm*", text)

    def test_avg_sleep_shown(self):
        text = _summarise(self._rows())
        expected_avg = round((8.0 + 7.0 + 5.0) / 3, 1)
        self.assertIn(f"avg {expected_avg}h", text)

    def test_dysregulated_warning_at_3_or_more(self):
        rows = [{"nervous_system_state": "dysregulated"} for _ in range(3)]
        text = _summarise(rows)
        self.assertIn("dysregulated day(s) this week", text)

    def test_no_warning_below_3_dysregulated(self):
        rows = [{"nervous_system_state": "dysregulated"}, {"nervous_system_state": "calm"}]
        text = _summarise(rows)
        self.assertNotIn("conditions need attention", text)

    def test_energy_distribution_shown(self):
        text = _summarise(self._rows())
        self.assertIn("Low: 1/3", text)
        self.assertIn("High: 1/3", text)

    def test_recovery_posture_shown_when_present(self):
        rows = [{"posture_band": "green"}, {"posture_band": "green"}, {"posture_band": "amber"}]
        text = _summarise(rows)
        self.assertIn("green: 2 day(s)", text)

    def test_safety_footer_present(self):
        text = _summarise(self._rows())
        self.assertIn("The Captain is not broken", text)


class TestSummarisePrivacyBoundary(unittest.TestCase):
    """_summarise() only ever reads nervous_system_state/energy/sleep_hours/
    mood/posture_band(/posture) from each row — an arbitrary or clinical
    key can never reach the outbound text, because nothing extracts it."""

    def test_unread_clinical_field_never_appears_in_output(self):
        rows = [{
            "nervous_system_state": "calm",
            "notes": "SECRET_CLINICAL_NOTE_DO_NOT_EXPOSE",
            "diagnosis": "should never surface",
            "blood_pressure": "120/80",
        }]
        text = _summarise(rows)
        self.assertNotIn("SECRET_CLINICAL_NOTE_DO_NOT_EXPOSE", text)
        self.assertNotIn("should never surface", text)
        self.assertNotIn("120/80", text)

    def test_malformed_sleep_hours_does_not_crash(self):
        rows = [{"nervous_system_state": "calm", "sleep_hours": "not-a-number"}]
        # Should not raise — malformed values are skipped, not propagated.
        text = _summarise(rows)
        self.assertIn("Calm", text)


# ── _fetch_recent_logs(): Supabase unavailable handling ────────────────────────

class TestFetchRecentLogs(unittest.TestCase):
    def test_none_db_returns_empty(self):
        self.assertEqual(_fetch_recent_logs(None), [])

    def test_disabled_db_returns_empty(self):
        mock_db = MagicMock()
        mock_db.is_enabled.return_value = False
        self.assertEqual(_fetch_recent_logs(mock_db), [])

    def test_fetch_exception_returns_empty_not_raises(self):
        mock_db = MagicMock()
        mock_db.is_enabled.return_value = True
        mock_db.raw_client.table.side_effect = RuntimeError("db down")
        self.assertEqual(_fetch_recent_logs(mock_db), [])


# ── handle_health_brief(): end to end ───────────────────────────────────────────

class TestHandleHealthBrief(unittest.TestCase):
    def test_no_supabase_sends_no_data_brief_not_crash(self):
        mock_client = MagicMock()
        with patch("commands.health_synthesis._make_supabase", return_value=None), \
             patch("commands.health_synthesis._llm_synthesis", return_value=None):
            handle_health_brief("U1", mock_client)

        mock_client.chat_postMessage.assert_called_once()
        call_text = str(mock_client.chat_postMessage.call_args)
        self.assertIn("No check-in data", call_text)

    def test_llm_unavailable_falls_back_to_raw_summary(self):
        mock_db = MagicMock()
        mock_db.is_enabled.return_value = True
        mock_client = MagicMock()

        rows = [{"nervous_system_state": "calm", "energy": "high"}]
        with patch("commands.health_synthesis._make_supabase", return_value=mock_db), \
             patch("commands.health_synthesis._fetch_recent_logs", return_value=rows), \
             patch("commands.health_synthesis._llm_synthesis", return_value=None):
            handle_health_brief("U2", mock_client)

        call_text = str(mock_client.chat_postMessage.call_args)
        self.assertIn("Weekly Health Brief", call_text)
        self.assertNotIn("Medical Officer Interpretation", call_text)

    def test_llm_available_appends_interpretation(self):
        mock_db = MagicMock()
        mock_db.is_enabled.return_value = True
        mock_client = MagicMock()

        rows = [{"nervous_system_state": "calm"}]
        with patch("commands.health_synthesis._make_supabase", return_value=mock_db), \
             patch("commands.health_synthesis._fetch_recent_logs", return_value=rows), \
             patch("commands.health_synthesis._llm_synthesis", return_value="Looking steady this week."):
            handle_health_brief("U3", mock_client)

        call_text = str(mock_client.chat_postMessage.call_args)
        self.assertIn("Medical Officer Interpretation", call_text)
        self.assertIn("Looking steady this week.", call_text)

    def test_dm_failure_does_not_raise(self):
        mock_db = MagicMock()
        mock_db.is_enabled.return_value = True
        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = RuntimeError("slack down")

        with patch("commands.health_synthesis._make_supabase", return_value=mock_db), \
             patch("commands.health_synthesis._fetch_recent_logs", return_value=[]), \
             patch("commands.health_synthesis._llm_synthesis", return_value=None):
            handle_health_brief("U4", mock_client)  # must not raise


if __name__ == "__main__":
    unittest.main()
