"""
Unit tests for intelligence/ranking/ranker.py

Covers:
- rank() returns list[RankedEvent] sorted descending by rank_score
- top_events() never exceeds TOP_EVENTS_LIMIT
- Recency decay (recent events rank higher than stale)
- Source priority weight (priority 1 > priority 5)
- Geography weight (AU > APAC > GLOBAL)
- Suppressed events excluded from top_events
"""

import sys
import os
import unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.ranking.ranker import rank, top_events
from intelligence.models import ClassifiedEvent, RankedEvent
from intelligence.config import TOP_EVENTS_LIMIT


def _make_event(
    title: str = "Test event",
    source_id: str = "src-1",
    source_priority: int = 2,
    banking_relevance: str = "medium",
    cps230_relevance: bool = False,
    operational_relevance: float = 0.55,
    customer_impact: str = "low",
    geography: str = "AU",
    event_type: str = "regulatory",
    suppressed: bool = False,
    days_old: int = 0,
) -> ClassifiedEvent:
    collected = datetime.now(tz=timezone.utc) - timedelta(days=days_old)
    return ClassifiedEvent(
        event_id=f"uuid-{title[:8]}",
        source_id=source_id,
        source_name=f"Source {source_id}",
        source_priority=source_priority,
        source_confidence_weight=0.8,
        source_category="media",
        raw_title=title,
        raw_summary="",
        canonical_url="https://example.com/item",
        published_at=collected,
        collected_at=collected,
        dedup_hash="aabbcc",
        event_type=event_type,
        geography=geography,
        sector="financial_services",
        operational_relevance=operational_relevance,
        customer_impact=customer_impact,
        banking_relevance=banking_relevance,
        cps230_relevance=cps230_relevance,
        dependency_risk=False,
        confidence=0.8,
        suppressed=suppressed,
    )


class TestRankReturnType(unittest.TestCase):

    def test_returns_list(self):
        events = [_make_event(title=f"Event {i}") for i in range(3)]
        self.assertIsInstance(rank(events), list)

    def test_each_element_is_ranked_event(self):
        events = [_make_event(title=f"Event {i}") for i in range(3)]
        for r in rank(events):
            self.assertIsInstance(r, RankedEvent)

    def test_empty_input(self):
        self.assertEqual(rank([]), [])


class TestTopEventsCap(unittest.TestCase):

    def test_never_exceeds_top_limit(self):
        events = [_make_event(title=f"Event {i}") for i in range(20)]
        result = top_events(rank(events))
        self.assertLessEqual(len(result), TOP_EVENTS_LIMIT)

    def test_fewer_than_limit_returns_all(self):
        n = max(1, TOP_EVENTS_LIMIT - 2)
        events = [_make_event(title=f"Event {i}") for i in range(n)]
        result = top_events(rank(events))
        self.assertEqual(len(result), n)

    def test_suppressed_excluded_from_top(self):
        events = [_make_event(title=f"Suppressed {i}", suppressed=True) for i in range(3)]
        result = top_events(rank(events))
        self.assertEqual(len(result), 0)


class TestRecencyDecay(unittest.TestCase):

    def test_recent_ranks_above_stale(self):
        fresh = _make_event(title="Fresh event A", days_old=0)
        stale = _make_event(title="Stale event A", days_old=13)
        ranked = {r.raw_title: r.rank_score for r in rank([fresh, stale])}
        self.assertGreater(ranked["Fresh event A"], ranked["Stale event A"])

    def test_14_day_old_event_lower_than_fresh(self):
        fresh = _make_event(title="Fresh B", days_old=0)
        very_old = _make_event(title="Very Old B", days_old=14)
        ranked = {r.raw_title: r.rank_score for r in rank([fresh, very_old])}
        self.assertGreater(ranked["Fresh B"], ranked["Very Old B"])


class TestSourcePriorityWeight(unittest.TestCase):

    def test_priority_1_outranks_priority_5(self):
        high = _make_event(title="High Pri", source_priority=1,
                            operational_relevance=0.6)
        low = _make_event(title="Low Pri", source_priority=5,
                           operational_relevance=0.6)
        ranked = {r.raw_title: r.rank_score for r in rank([high, low])}
        self.assertGreater(ranked["High Pri"], ranked["Low Pri"])


class TestGeographyWeight(unittest.TestCase):

    def test_au_outranks_global(self):
        au = _make_event(title="AU Event", geography="AU")
        gl = _make_event(title="GLOBAL Event", geography="GLOBAL")
        ranked = {r.raw_title: r.rank_score for r in rank([au, gl])}
        self.assertGreater(ranked["AU Event"], ranked["GLOBAL Event"])

    def test_apac_between_au_and_global(self):
        au = _make_event(title="AU", geography="AU")
        ap = _make_event(title="APAC", geography="APAC")
        gl = _make_event(title="GLOBAL", geography="GLOBAL")
        scored = {r.raw_title: r.rank_score for r in rank([au, ap, gl])}
        self.assertGreater(scored["AU"], scored["APAC"])
        self.assertGreater(scored["APAC"], scored["GLOBAL"])


class TestRankOrdering(unittest.TestCase):

    def test_output_descending_by_score(self):
        events = [_make_event(title=f"Ev {i}", days_old=i) for i in range(5)]
        result = rank(events)
        scores = [r.rank_score for r in result]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
