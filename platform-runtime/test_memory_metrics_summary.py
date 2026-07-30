from __future__ import annotations

import sys
import unittest
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.coordination.memory_metrics import summarize_memory_metrics, fetch_memory_metrics_summary
from commands.memory_queries import handle_memory_metrics_summary


class MemoryMetricsSummaryTests(unittest.TestCase):
    def test_empty_metrics_returns_not_enough_data(self):
        summary = summarize_memory_metrics([])
        self.assertFalse(summary["found"])
        self.assertEqual(summary["reason"], "no_data")

    def test_partial_metrics_returns_compact_summary(self):
        events = [
            {"event_type": "memory_metric", "action": "memory_lookup", "outcome": "hit"},
            {"event_type": "memory_metric", "action": "fallback", "outcome": "load_failed"},
            {"event_type": "memory_metric", "action": "reuse_accepted", "outcome": "accepted"},
        ]
        summary = summarize_memory_metrics(events, window_days=7)
        self.assertTrue(summary["found"])
        self.assertEqual(summary["hit_rate"], 33.3)
        self.assertEqual(summary["fallback_rate"], 33.3)
        self.assertEqual(summary["research_reuse_rate"], 33.3)
        self.assertIn("Memory hit rate", "\n".join(summary["lines"]))

    def test_populated_metrics_summary_command(self):
        fake_client = MagicMock()
        fake_client.select_recent.return_value = [
            {"event_type": "memory_metric", "action": "memory_lookup", "outcome": "hit", "created_at": datetime.now(timezone.utc).isoformat()},
            {"event_type": "memory_metric", "action": "memory_lookup", "outcome": "miss", "created_at": datetime.now(timezone.utc).isoformat()},
            {"event_type": "memory_metric", "action": "fallback", "outcome": "load_failed", "created_at": datetime.now(timezone.utc).isoformat()},
            {"event_type": "memory_metric", "action": "reuse_accepted", "outcome": "accepted", "created_at": datetime.now(timezone.utc).isoformat()},
            {"event_type": "memory_metric", "action": "stale_context_flagged", "outcome": "stale_context_flagged", "details": {"artifact_type": "mission"}, "created_at": datetime.now(timezone.utc).isoformat()},
            {"event_type": "memory_metric", "action": "mission_overlap_warning", "outcome": "warning", "created_at": datetime.now(timezone.utc).isoformat()},
            {"event_type": "memory_metric", "action": "decision_conflict_warning", "outcome": "warning", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        summary = fetch_memory_metrics_summary(fake_client, window_days=7)
        self.assertTrue(summary["found"])
        self.assertEqual(summary["conflict_warning_count"], 1)
        self.assertEqual(summary["overlap_warning_count"], 1)
        self.assertEqual(summary["stale_context_count"], 1)
        self.assertEqual(summary["research_reuse_rate"], 14.3)
        self.assertIn("Low hit rate", " ".join(summary.get("alerts", [])))
        self.assertEqual(summary["stale_context_sources"]["missions"], 1)

    def test_alert_thresholds_can_be_overridden_with_environment(self):
        from core.coordination.memory_metrics import build_memory_metrics_alerts, get_memory_metric_thresholds

        with patch.dict(os.environ, {
            "MEMORY_METRICS_LOW_HIT_RATE_THRESHOLD": "25",
            "MEMORY_METRICS_HIGH_FALLBACK_RATE_THRESHOLD": "5",
        }, clear=False):
            thresholds = get_memory_metric_thresholds()
            alerts = build_memory_metrics_alerts({
                "found": True,
                "hit_rate": 30.0,
                "fallback_rate": 6.0,
                "conflict_warning_count": 0,
                "overlap_warning_count": 0,
                "stale_context_count": 0,
            })

        self.assertEqual(thresholds["low_hit_rate"], 25.0)
        self.assertEqual(thresholds["high_fallback_rate"], 5.0)
        self.assertIn("High fallback rate", " ".join(alerts))

    def test_handler_empty_metrics_is_graceful(self):
        with patch("commands.memory_queries.fetch_memory_metrics_summary") as mock_fetch:
            mock_fetch.return_value = {"found": False, "window_days": 7, "reason": "no_data"}
            respond = MagicMock()
            handle_memory_metrics_summary(lambda: None, respond, {"text": ""})

        respond.assert_called_once()
        self.assertIn("Not enough data yet", respond.call_args.args[0])

    def test_handler_populated_metrics_renders_summary(self):
        with patch("commands.memory_queries.fetch_memory_metrics_summary") as mock_fetch:
            mock_fetch.return_value = {
                "found": True,
                "lines": [
                    "Window: last 7 days",
                    "Memory hit rate: 50.0% (5/10)",
                    "Miss rate: 20.0% (2/10)",
                    "Fallback rate: 10.0% (1/10)",
                    "Research reuse rate: 20.0% (2/10)",
                    "Stale-context count: 1",
                    "Overlap-warning count: 1",
                    "Conflict-warning count: 1",
                ],
            }
            respond = MagicMock()
            handle_memory_metrics_summary(lambda: None, respond, {"text": "7"})

        respond.assert_called_once()
        rendered = respond.call_args.args[0]
        self.assertIn("Memory Metrics", rendered)
        self.assertIn("Memory hit rate", rendered)

    def test_handler_accepts_7d_flag(self):
        with patch("commands.memory_queries.fetch_memory_metrics_summary") as mock_fetch:
            mock_fetch.return_value = {
                "found": False,
                "window_days": 7,
                "reason": "no_data",
            }
            respond = MagicMock()
            handle_memory_metrics_summary(lambda: None, respond, {"text": "--7d"})

        mock_fetch.assert_called_once()
        self.assertEqual(mock_fetch.call_args.kwargs["window_days"], 7)
        respond.assert_called_once()
        self.assertIn("Window: last 7 days", respond.call_args.args[0])
        self.assertIn("/memory-metrics --7d", respond.call_args.args[0])

    def test_handler_accepts_30d_flag(self):
        with patch("commands.memory_queries.fetch_memory_metrics_summary") as mock_fetch:
            mock_fetch.return_value = {
                "found": False,
                "window_days": 30,
                "reason": "no_data",
            }
            respond = MagicMock()
            handle_memory_metrics_summary(lambda: None, respond, {"text": "--30d"})

        mock_fetch.assert_called_once()
        self.assertEqual(mock_fetch.call_args.kwargs["window_days"], 30)
        respond.assert_called_once()
        self.assertIn("Window: last 30 days", respond.call_args.args[0])

    def test_handler_invalid_flag_falls_back_to_default_window(self):
        with patch("commands.memory_queries.fetch_memory_metrics_summary") as mock_fetch:
            mock_fetch.return_value = {
                "found": False,
                "window_days": 7,
                "reason": "no_data",
            }
            respond = MagicMock()
            handle_memory_metrics_summary(lambda: None, respond, {"text": "--latest"})

        mock_fetch.assert_called_once()
        self.assertEqual(mock_fetch.call_args.kwargs["window_days"], 7)
        respond.assert_called_once()
        self.assertIn("Window: last 7 days", respond.call_args.args[0])

    def test_handler_30d_summary_includes_comparison(self):
        now = datetime.now(timezone.utc)
        recent = now.isoformat()
        older = (now - timedelta(days=15)).isoformat()
        oldest = (now - timedelta(days=45)).isoformat()
        summary = summarize_memory_metrics([
            {"event_type": "memory_metric", "action": "memory_lookup", "outcome": "hit", "created_at": recent},
            {"event_type": "memory_metric", "action": "memory_lookup", "outcome": "miss", "created_at": recent},
            {"event_type": "memory_metric", "action": "fallback", "outcome": "load_failed", "created_at": recent},
            {"event_type": "memory_metric", "action": "reuse_accepted", "outcome": "accepted", "created_at": recent},
            {"event_type": "memory_metric", "action": "memory_lookup", "outcome": "hit", "created_at": older},
            {"event_type": "memory_metric", "action": "reuse_accepted", "outcome": "accepted", "created_at": older},
            {"event_type": "memory_metric", "action": "memory_lookup", "outcome": "miss", "created_at": oldest},
        ], window_days=30)
        self.assertTrue(summary["comparison"]["found"])
        self.assertIn("30-day comparison", "\n".join(summary["comparison"]["lines"]))

    def test_handler_30d_renders_comparison_lines(self):
        with patch("commands.memory_queries.fetch_memory_metrics_summary") as mock_fetch:
            mock_fetch.return_value = {
                "found": True,
                "lines": [
                    "Window: last 30 days",
                    "Memory hit rate: 50.0% (10/20)",
                    "Miss rate: 20.0% (4/20)",
                    "Fallback rate: 10.0% (2/20)",
                    "Research reuse rate: 20.0% (4/20)",
                    "Stale-context count: 1",
                    "Overlap-warning count: 1",
                    "Conflict-warning count: 1",
                ],
                "alerts": ["Low hit rate: consider adding more retrievable memory coverage."],
                "comparison": {
                    "found": True,
                    "lines": [
                        "30-day comparison vs prior 30-day window:",
                        "  Hit rate: 50.0% vs 40.0%",
                        "  Fallback rate: 10.0% vs 12.0%",
                        "  Research reuse rate: 20.0% vs 15.0%",
                    ],
                },
            }
            respond = MagicMock()
            handle_memory_metrics_summary(lambda: None, respond, {"text": "--30d"})

        rendered = respond.call_args.args[0]
        self.assertIn("Operational notes", rendered)
        self.assertIn("30-day comparison vs prior 30-day window", rendered)

    def test_default_thresholds_still_apply_without_env_overrides(self):
        from core.coordination.memory_metrics import build_memory_metrics_alerts, get_memory_metric_thresholds

        with patch.dict(os.environ, {}, clear=True):
            thresholds = get_memory_metric_thresholds()
            alerts = build_memory_metrics_alerts({
                "found": True,
                "hit_rate": 39.9,
                "fallback_rate": 20.1,
                "conflict_warning_count": 0,
                "overlap_warning_count": 0,
                "stale_context_count": 0,
            })

        self.assertEqual(thresholds["low_hit_rate"], 40.0)
        self.assertEqual(thresholds["high_fallback_rate"], 20.0)
        self.assertIn("Low hit rate", " ".join(alerts))


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
