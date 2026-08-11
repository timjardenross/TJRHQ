"""
Unit tests for intelligence/scheduler.py's Downdetector tiered-cadence
priority job (Captain decision 1: Big 4 banks + Telstra/Optus checked more
often during 07:00-19:00 AEST business hours, everything else unchanged).

Covers:
- _within_priority_tiered_window() time-gating at representative hours
  (before window, window start, mid-window, window end boundary, after window)
- _PRIORITY_TIERED_SOURCE_NAMES is scoped to exactly the 6 named sources
  (Big 4 banks, NOT Bendigo/UBank; Telstra/Optus, NOT TPG/Vodafone/NBN)
- _priority_tiered_collection_job() calls collect_all() only with sources
  matching those 6 names when inside the window, and never collects at all
  outside the window
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence import scheduler


class TestWithinPriorityTieredWindow(unittest.TestCase):
    def test_before_window(self):
        self.assertFalse(scheduler._within_priority_tiered_window(6))

    def test_window_start_inclusive(self):
        self.assertTrue(scheduler._within_priority_tiered_window(7))

    def test_mid_window(self):
        self.assertTrue(scheduler._within_priority_tiered_window(13))

    def test_last_hour_inside_window(self):
        self.assertTrue(scheduler._within_priority_tiered_window(18))

    def test_window_end_exclusive(self):
        self.assertFalse(scheduler._within_priority_tiered_window(19))

    def test_after_window(self):
        self.assertFalse(scheduler._within_priority_tiered_window(22))

    def test_midnight(self):
        self.assertFalse(scheduler._within_priority_tiered_window(0))


class TestPrioritySourceScoping(unittest.TestCase):
    def test_exactly_six_sources(self):
        self.assertEqual(len(scheduler._PRIORITY_TIERED_SOURCE_NAMES), 6)

    def test_big_four_banks_included(self):
        for name in (
            "Downdetector AU — NAB",
            "Downdetector AU — ANZ Bank",
            "Downdetector AU — Commonwealth Bank",
            "Downdetector AU — Westpac",
        ):
            self.assertIn(name, scheduler._PRIORITY_TIERED_SOURCE_NAMES)

    def test_bendigo_and_ubank_excluded(self):
        self.assertNotIn("Downdetector AU — Bendigo Bank", scheduler._PRIORITY_TIERED_SOURCE_NAMES)
        self.assertNotIn("Downdetector AU — UBank", scheduler._PRIORITY_TIERED_SOURCE_NAMES)

    def test_top_two_telcos_included(self):
        self.assertIn("Downdetector AU — Telstra", scheduler._PRIORITY_TIERED_SOURCE_NAMES)
        self.assertIn("Downdetector AU — Optus", scheduler._PRIORITY_TIERED_SOURCE_NAMES)

    def test_other_telcos_excluded(self):
        for name in (
            "Downdetector AU — TPG Telecom",
            "Downdetector AU — Vodafone",
            "Downdetector AU — NBN Co",
        ):
            self.assertNotIn(name, scheduler._PRIORITY_TIERED_SOURCE_NAMES)


class _FakeSource:
    def __init__(self, source_name):
        self.source_name = source_name


class TestPriorityTieredCollectionJob(unittest.TestCase):
    """Gates the job on _within_priority_tiered_window directly rather than
    fighting the function's internal (locally-imported) datetime/zoneinfo
    call — that time-gating logic itself is covered directly and
    exhaustively by TestWithinPriorityTieredWindow above; these tests cover
    the job's WIRING (does it actually call collect_all only with the right
    sources, does it actually skip collection entirely when gated off)."""

    def test_noop_outside_window(self):
        with mock.patch.object(scheduler, "_within_priority_tiered_window", return_value=False), \
             mock.patch("intelligence.ingestion.collection_engine.collect_all") as mock_collect:
            scheduler._priority_tiered_collection_job()
            mock_collect.assert_not_called()

    def test_collects_only_scoped_sources_inside_window(self):
        registry = [
            _FakeSource("Downdetector AU — NAB"),
            _FakeSource("Downdetector AU — Telstra"),
            _FakeSource("Downdetector AU — Bendigo Bank"),   # must be excluded
            _FakeSource("AEMO Market Notices"),               # must be excluded
        ]
        with mock.patch.object(scheduler, "_within_priority_tiered_window", return_value=True), \
             mock.patch("intelligence.persistence.intelligence_store.load_source_registry",
                         return_value=registry), \
             mock.patch("intelligence.ingestion.collection_engine.collect_all",
                         return_value=([], [])) as mock_collect:
            scheduler._priority_tiered_collection_job()

        mock_collect.assert_called_once()
        called_sources = mock_collect.call_args.kwargs.get("sources")
        if called_sources is None and mock_collect.call_args.args:
            called_sources = mock_collect.call_args.args[0]
        called_names = {s.source_name for s in called_sources}
        self.assertEqual(
            called_names,
            {"Downdetector AU — NAB", "Downdetector AU — Telstra"},
        )

    def test_empty_scoped_source_list_skips_collection(self):
        # Registry has none of the 6 priority sources active right now.
        registry = [_FakeSource("Downdetector AU — Bendigo Bank")]
        with mock.patch.object(scheduler, "_within_priority_tiered_window", return_value=True), \
             mock.patch("intelligence.persistence.intelligence_store.load_source_registry",
                         return_value=registry), \
             mock.patch("intelligence.ingestion.collection_engine.collect_all") as mock_collect:
            scheduler._priority_tiered_collection_job()
        mock_collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
