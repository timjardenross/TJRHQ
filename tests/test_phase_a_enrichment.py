"""
Unit tests for intelligence/ingestion/phase_a_enrichment.py — the live-pipeline
seam (source-tier + fuzzy dedup + heuristic scoring) used by the daily job.
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.ingestion.phase_a_enrichment import enrich_and_save, source_tier_for


def _event(title, summary, url, **extra):
    ns = types.SimpleNamespace(
        raw_title=title, raw_summary=summary, canonical_url=url,
        event_type=extra.get("event_type", "telecom_outage"),
        geography=extra.get("geography", "AU"),
        customer_impact=extra.get("customer_impact", "high"),
        banking_relevance=extra.get("banking_relevance", "medium"),
        cps230_relevance=extra.get("cps230_relevance", False),
        dependency_risk=extra.get("dependency_risk", False),
        operational_relevance=extra.get("operational_relevance", 0.7),
        sector=extra.get("sector", "telecom"),
        rank_score=extra.get("rank_score", 42.0),
    )
    return ns


class _FakeStore:
    def __init__(self):
        self.saved = []          # list of (event, phase_a)
        self._n = 0

    def save_event(self, event, ori=None, phase_a=None):
        self._n += 1
        eid = f"uuid-{self._n}"
        self.saved.append((event, phase_a, eid))
        return eid


class TestEnrichment(unittest.TestCase):
    def setUp(self):
        self.store = _FakeStore()
        self.events = [
            _event("Telstra network outage hits millions nationwide",
                   "A major Telstra mobile and internet outage disrupted services across Australia.",
                   "https://www.abc.net.au/news/telstra"),
            _event("Millions of Telstra customers hit by nationwide network outage",
                   "A widespread Telstra mobile network outage left millions without service.",
                   "https://www.afr.com/telstra"),
            _event("AEMO warns of Victorian electricity grid load shedding",
                   "AEMO warned electricity supply constraints could force load shedding.",
                   "https://reuters.com/aemo", event_type="energy_disruption"),
        ]

    def test_source_tier(self):
        self.assertEqual(source_tier_for(self.events[0]), 2)   # abc.net.au
        self.assertEqual(source_tier_for(self.events[2]), 1)   # reuters.com

    def test_enrich_partitions_and_scores(self):
        stats = enrich_and_save(self.events, self.store)
        # Telstra pair merges -> 2 canonicals (e0, e2), 1 duplicate (e1).
        self.assertEqual(stats["canonical"], 2)
        self.assertEqual(stats["duplicate"], 1)
        self.assertEqual(stats["failed"], 0)

        by_status = {}
        canonical_id_for_dup = None
        for _ev, pa, eid in self.store.saved:
            by_status.setdefault(pa["signal_status"], []).append((pa, eid))
            if pa["signal_status"] == "DUPLICATE":
                canonical_id_for_dup = pa["canonical_signal_id"]

        self.assertEqual(len(by_status["SCORED"]), 2)
        self.assertEqual(len(by_status["DUPLICATE"]), 1)

        # canonicals carry score + tier, NOT an overriding rank_score.
        for pa, _eid in by_status["SCORED"]:
            self.assertIn("score_breakdown", pa)
            self.assertIn(pa["risk_rating"], ("HIGH", "MEDIUM", "LOW"))
            self.assertIn("source_tier", pa)
            self.assertNotIn("rank_score", pa)   # ranker stays authoritative

        # duplicate references a real saved canonical event_id + similarity.
        self.assertIsNotNone(canonical_id_for_dup)
        self.assertTrue(canonical_id_for_dup.startswith("uuid-"))
        dup_pa = by_status["DUPLICATE"][0][0]
        self.assertIsNotNone(dup_pa["cluster_similarity"])

    def test_empty(self):
        self.assertEqual(enrich_and_save([], self.store),
                         {"canonical": 0, "duplicate": 0, "failed": 0})


if __name__ == "__main__":
    unittest.main()
