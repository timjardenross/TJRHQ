"""
Unit tests for fuzzy near-duplicate clustering (Phase A Stage 6) in
intelligence/classification/deduplicator.py.

Covers:
- Same incident across different outlets/wordings clusters together
- Distinct incidents stay separate (no over-clustering)
- Canonical = first (lowest-index) signal in a cluster
- Similarity scores recorded on members
- Empty / single-signal edge cases
- Performance budget (<100ms/signal)
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.classification.deduplicator import (
    SignalDeduplicator,
    text_similarity,
)


def _sig(sid, title, summary=""):
    return {"id": sid, "title": title, "summary": summary}


class TestFuzzyDedup(unittest.TestCase):
    def test_same_incident_clusters(self):
        signals = [
            _sig("a", "Telstra network outage hits millions of customers nationwide",
                 "A major Telstra mobile and internet outage disrupted services across Australia."),
            _sig("b", "Millions of Telstra customers hit by nationwide network outage",
                 "Telstra's mobile network suffered a widespread outage affecting millions."),
            _sig("c", "Telstra outage: millions of customers across Australia lose service",
                 "Widespread Telstra network disruption left millions without connectivity."),
        ]
        clusters = SignalDeduplicator().cluster_signals(signals)  # calibrated default
        self.assertEqual(len(clusters), 1, "all three should be one incident")
        self.assertEqual(clusters[0].canonical_id, "a")
        self.assertEqual(sorted(clusters[0].member_ids), ["b", "c"])

    def test_distinct_incidents_separate(self):
        signals = [
            _sig("a", "Telstra network outage hits millions nationwide"),
            _sig("b", "AEMO warns of electricity grid load shedding in Victoria"),
            _sig("c", "ASIC opens enforcement action against a payments provider"),
        ]
        clusters = SignalDeduplicator(0.85).cluster_signals(signals)
        self.assertEqual(len(clusters), 3, "unrelated events must not over-cluster")
        for c in clusters:
            self.assertEqual(c.size, 1)

    def test_canonical_is_first(self):
        signals = [
            _sig("first", "Optus data breach exposes customer records"),
            _sig("second", "Optus breach: customer records exposed in data incident"),
        ]
        clusters = SignalDeduplicator(0.5).cluster_signals(signals)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].canonical_id, "first")
        self.assertIn("second", clusters[0].similarities)
        self.assertGreaterEqual(clusters[0].similarities["second"], 0.5)

    def test_empty_and_single(self):
        self.assertEqual(SignalDeduplicator().cluster_signals([]), [])
        one = SignalDeduplicator().cluster_signals([_sig("solo", "A lone signal")])
        self.assertEqual(len(one), 1)
        self.assertEqual(one[0].canonical_id, "solo")
        self.assertEqual(one[0].member_ids, [])

    def test_text_similarity_bounds(self):
        self.assertEqual(text_similarity("", "anything"), 0.0)
        self.assertAlmostEqual(text_similarity("same text", "same text"), 1.0, places=3)
        self.assertLess(text_similarity("telstra outage", "asic enforcement action"), 0.85)

    def test_performance(self):
        # 200 signals across ~20 incident templates.
        templates = [
            f"Incident {k} disrupts service for customers in region {k}" for k in range(20)
        ]
        signals = [_sig(f"s{i}", templates[i % 20], "detail text about the incident")
                   for i in range(200)]
        start = time.perf_counter()
        SignalDeduplicator().cluster_signals(signals)
        avg_ms = (time.perf_counter() - start) / len(signals) * 1000
        self.assertLess(avg_ms, 100.0, f"too slow: {avg_ms:.2f} ms/signal")


if __name__ == "__main__":
    unittest.main()
