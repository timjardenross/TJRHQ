"""
Telstra PoC — Phase A end-to-end GO/NO-GO gate.

Runs 6 Telstra-outage signals through the full enhanced pipeline OFFLINE against
the in-memory repository (no network, deterministic):

  collect -> classify (real classifier) -> source-tier (real) -> fuzzy dedup (real)
  -> 10-dim score (Analyst heuristic) -> HUMAN GATE verify -> HUMAN GATE select
  -> QA pass -> curate watchlist -> publish (Executive) -> next-cycle watchlist
  materialisation.

Also asserts the governance gates actually block: analyst can't publish, publish
before QA_PASSED fails, selecting <3 fails.
"""

import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.analysis.intelligence_analyst import IntelligenceAnalyst
from intelligence.classification.classifier import classify
from intelligence.classification.deduplicator import SignalDeduplicator
from intelligence.classification.source_tier import classify_source_tier
from intelligence.governance.workflow_gate import (
    ANALYST,
    EXECUTIVE_APPROVER,
    INTELLIGENCE_LEAD,
    GovernanceError,
)
from intelligence.models import IntelligenceItem
from intelligence.watchlist.tracker import WatchlistTracker
from intelligence.workflow import service
from intelligence.workflow.repository import InMemoryRepository


class _NoLLM:
    """Force the Analyst onto its deterministic heuristic path (offline)."""

    def generate(self, prompt):
        return None, None


# A realistic briefing week: the Telstra incident is DUPLICATED across two outlets
# (fuzzy dedup must merge them -> proves dedup), alongside four genuinely distinct
# OR incidents that must stay separate. 6 raw -> 5 canonical incidents.
TELSTRA_WEEK = [
    # 0 + 1: the same Telstra outage, two outlets -> should merge into one incident.
    ("Telstra network outage hits millions of customers nationwide",
     "A major Telstra mobile and internet outage disrupted essential services across Australia for hours.",
     "https://www.abc.net.au/news/telstra-outage"),
    ("Millions of Telstra customers hit by nationwide network outage",
     "A widespread Telstra mobile network outage left millions of customers across Australia without service.",
     "https://www.afr.com/companies/telstra-outage"),
    # 2: distinct — energy.
    ("AEMO warns of electricity grid load shedding across Victoria",
     "AEMO cautioned that electricity supply constraints could force load shedding in Victoria.",
     "https://www.reuters.com/world/aemo-grid"),
    # 3: distinct — regulatory / payments.
    ("ASIC opens enforcement action against a major payments provider",
     "ASIC has commenced enforcement action against a payments provider over operational failures.",
     "https://asic.gov.au/enforcement-payments"),
    # 4: distinct — cloud dependency.
    ("AWS outage disrupts cloud services for Australian banks",
     "An AWS outage degraded cloud-hosted services relied on by several Australian banks.",
     "https://www.itnews.com.au/aws-outage"),
    # 5: distinct — telco.
    ("Optus reports mobile network degradation across Sydney",
     "Optus reported degraded mobile network performance affecting customers across Sydney.",
     "https://www.theguardian.com/australia-news/optus-degradation"),
]


def _now():
    return datetime(2026, 7, 11, tzinfo=timezone.utc)


class TestTelstraPoC(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryRepository()
        self.analyst = IntelligenceAnalyst(llm_provider=_NoLLM())

    def _ingest_and_classify(self):
        """Stages 2–6: collect, fuzzy dedup, classify, source-tier, persist.

        Fuzzy dedup must collapse the two Telstra articles (same incident, two
        outlets) into one canonical, leaving 5 distinct incidents. Only the
        canonical of each cluster is persisted and flows into the brief."""
        raw = [{"id": f"raw-{i}", "title": t, "summary": s, "url": u}
               for i, (t, s, u) in enumerate(TELSTRA_WEEK)]

        clusters = SignalDeduplicator().cluster_signals(raw)
        self.assertEqual(len(clusters), 5, "Telstra duplicate should merge -> 5 incidents")
        self.assertTrue(any(c.size == 2 for c in clusters), "the Telstra pair must merge")

        by_id = {r["id"]: r for r in raw}
        event_ids = []
        for i, cluster in enumerate(clusters):
            canon = by_id[cluster.canonical_id]
            title, summary, url = canon["title"], canon["summary"], canon["url"]
            item = IntelligenceItem(
                source_id=f"src-{i}", source_name="poc", source_priority=2,
                source_confidence_weight=0.8, source_category="telecom",
                raw_title=title, raw_summary=summary, canonical_url=url,
                collected_at=_now(),
            )
            ce = classify(item)
            row = self.repo.insert_event({
                "event_id": f"evt-{i}",
                "raw_title": title, "raw_summary": summary, "canonical_url": url,
                "event_type": ce.event_type, "sector": ce.sector, "geography": ce.geography,
                "customer_impact": ce.customer_impact, "banking_relevance": ce.banking_relevance,
                "cps230_relevance": ce.cps230_relevance, "dependency_risk": ce.dependency_risk,
                "operational_relevance": ce.operational_relevance,
                "source_tier": classify_source_tier(url),
                "cluster_similarity": (max(cluster.similarities.values())
                                       if cluster.similarities else None),
                "signal_status": "TO_COLLECT",
            })
            event_ids.append(row["event_id"])
        return event_ids

    def test_end_to_end_go_no_go(self):
        event_ids = self._ingest_and_classify()

        # Stage 8–9: score all six.
        for eid in event_ids:
            scored = service.score_event(self.repo, self.analyst, eid)
            self.assertEqual(scored["signal_status"], "SCORED")
            self.assertIn("score_breakdown", scored)
            self.assertIn(scored["risk_rating"], ("HIGH", "MEDIUM", "LOW"))

        # At least the primary telecom outages should score HIGH.
        highs = [e for e in self.repo.list_events() if e.get("risk_rating") == "HIGH"]
        self.assertGreaterEqual(len(highs), 1)

        # Stage 7 human gate: Intelligence Lead verifies five signals.
        to_select = event_ids[:5]
        for eid in to_select:
            v = service.verify_event(self.repo, INTELLIGENCE_LEAD, eid,
                                     confidence_level="Confirmed",
                                     verified_against={"tier_1_source": "https://telstra.com/status"})
            self.assertEqual(v["signal_status"], "VERIFIED")
            self.assertEqual(v["confidence_level"], "Confirmed")

        # Create the brief and Stage 11 human gate: select the five verified events.
        brief = self.repo.insert_brief({
            "period_start": "2026-07-05", "period_end": "2026-07-11",
            # In production BriefGenerator + LLMProvider (Mistral 4-stage) fills this.
            "executive_snapshot": "Telstra's nationwide outage cascaded into payments, "
                                  "government, health and emergency communications.",
        })
        brief_id = brief["brief_id"]
        service.select_events(self.repo, INTELLIGENCE_LEAD, brief_id, to_select)
        self.assertEqual(len(self.repo.get_brief(brief_id)["signal_ids"]), 5)
        for eid in to_select:
            self.assertEqual(self.repo.get_event(eid)["signal_status"], "IN_BRIEF")

        # QA pass (consolidated 2026-07-18 from the original 3-gate + mark_qa_ready sequence).
        service.qa_pass(self.repo, "system", brief_id)
        self.assertEqual(self.repo.get_brief(brief_id)["approval_status"], "QA_PASSED")

        # Stage 14 human gate: curate the forward watchlist.
        watch = service.curate_watchlist(self.repo, INTELLIGENCE_LEAD, brief_id, [
            {"text": "Monitor secondary payment-system cascades",
             "query": {"keyword": "payment", "lookfor": "queue", "timeframe": "7d"}},
            {"text": "Track ACMA investigation findings",
             "query": {"keyword": "acma", "lookfor": "investigation"}},
            {"text": "Watch backup connectivity uptake",
             "query": {"keyword": "backup", "lookfor": "redundancy"}},
        ])
        self.assertEqual(len(watch), 3)

        # Executive publishes.
        published = service.publish_brief(self.repo, EXECUTIVE_APPROVER, brief_id,
                                         published_at="2026-07-11T08:00:00Z")
        self.assertEqual(published["approval_status"], "PUBLISHED")

        final = self.repo.get_brief(brief_id)
        self.assertEqual(final["approval_status"], "PUBLISHED")
        self.assertEqual(len(final["signal_ids"]), 5)
        self.assertEqual(len(final["forward_watch"]), 3)
        self.assertTrue(final["executive_snapshot"])
        self.assertGreater(len(final["executive_snapshot"]), 50)

        # Post-brief automation: a next-cycle ACMA-investigation signal materialises
        # the second watchlist item.
        next_evt = self.repo.insert_event({
            "event_id": "evt-next",
            "raw_title": "ACMA opens formal investigation into Telstra outage",
            "raw_summary": "ACMA launches an investigation into the Telstra outage response.",
            "signal_status": "TO_COLLECT",
        })
        summary = WatchlistTracker(self.repo).track_brief(brief_id, [next_evt])
        self.assertEqual(summary["items"], 3)
        self.assertEqual(summary["materialized"], 1)   # ACMA item materialised
        self.assertEqual(summary["pending"], 2)

        print("✅ Telstra PoC PASSED — Phase B GO")

    def test_governance_blocks(self):
        event_ids = self._ingest_and_classify()
        for eid in event_ids:
            service.score_event(self.repo, self.analyst, eid)
        brief = self.repo.insert_brief({"period_start": "2026-07-05", "period_end": "2026-07-11"})
        bid = brief["brief_id"]

        # Analyst cannot verify or publish.
        with self.assertRaises(GovernanceError):
            service.verify_event(self.repo, ANALYST, event_ids[0], "Confirmed")
        with self.assertRaises(GovernanceError):
            service.publish_brief(self.repo, ANALYST, bid)

        # Selecting fewer than 3 events is rejected.
        for eid in event_ids[:2]:
            service.verify_event(self.repo, INTELLIGENCE_LEAD, eid, "Probable")
        with self.assertRaises(GovernanceError):
            service.select_events(self.repo, INTELLIGENCE_LEAD, bid, event_ids[:2])

        # Cannot publish before QA_PASSED.
        with self.assertRaises(GovernanceError):
            service.publish_brief(self.repo, EXECUTIVE_APPROVER, bid)


if __name__ == "__main__":
    unittest.main()
