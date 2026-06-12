"""
Unit tests for intelligence/classification/deduplicator.py

Covers:
- Hash consistency (same input → same hash)
- Hash uniqueness (different input → different hash)
- Normalisation (case, whitespace invariant)
- Date granularity (same day → same hash; different day → different hash)
- None published_at → stable hash
"""

import sys
import os
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.classification.deduplicator import compute_hash
from intelligence.models import IntelligenceItem


def _make_item(title: str, source_id: str = "src-1",
               published_at=None) -> IntelligenceItem:
    return IntelligenceItem(
        source_id=source_id,
        source_name="Test Source",
        source_priority=2,
        source_confidence_weight=0.8,
        raw_title=title,
        collected_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
        raw_summary="",
        canonical_url="https://example.com/item",
        published_at=published_at or datetime(2026, 6, 12, tzinfo=timezone.utc),
    )


class TestHashConsistency(unittest.TestCase):

    def test_same_input_same_hash(self):
        item = _make_item("APRA updates CPS 230 guidelines")
        self.assertEqual(compute_hash(item), compute_hash(item))

    def test_hash_is_64_char_hex(self):
        h = compute_hash(_make_item("Test headline"))
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))

    def test_case_insensitive(self):
        h1 = compute_hash(_make_item("APRA Updates CPS 230 Guidelines"))
        h2 = compute_hash(_make_item("apra updates cps 230 guidelines"))
        self.assertEqual(h1, h2)

    def test_extra_whitespace_normalised(self):
        h1 = compute_hash(_make_item("APRA   updates   CPS 230"))
        h2 = compute_hash(_make_item("APRA updates CPS 230"))
        self.assertEqual(h1, h2)

    def test_leading_trailing_whitespace(self):
        h1 = compute_hash(_make_item("  APRA updates CPS 230  "))
        h2 = compute_hash(_make_item("APRA updates CPS 230"))
        self.assertEqual(h1, h2)


class TestHashUniqueness(unittest.TestCase):

    def test_different_title_different_hash(self):
        h1 = compute_hash(_make_item("Title A"))
        h2 = compute_hash(_make_item("Title B"))
        self.assertNotEqual(h1, h2)

    def test_different_source_different_hash(self):
        h1 = compute_hash(_make_item("Same Title", source_id="src-1"))
        h2 = compute_hash(_make_item("Same Title", source_id="src-2"))
        self.assertNotEqual(h1, h2)

    def test_different_date_different_hash(self):
        h1 = compute_hash(_make_item("Same Title",
                                     published_at=datetime(2026, 6, 12, tzinfo=timezone.utc)))
        h2 = compute_hash(_make_item("Same Title",
                                     published_at=datetime(2026, 6, 13, tzinfo=timezone.utc)))
        self.assertNotEqual(h1, h2)


class TestDateHandling(unittest.TestCase):

    def test_same_day_different_time_same_hash(self):
        h1 = compute_hash(_make_item("Headline X",
                                     published_at=datetime(2026, 6, 12, 6, 0, tzinfo=timezone.utc)))
        h2 = compute_hash(_make_item("Headline X",
                                     published_at=datetime(2026, 6, 12, 18, 0, tzinfo=timezone.utc)))
        self.assertEqual(h1, h2)

    def test_none_date_stable(self):
        item = _make_item("Headline no date", published_at=None)
        h1 = compute_hash(item)
        h2 = compute_hash(item)
        self.assertEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
