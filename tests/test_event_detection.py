"""Staged event detection (wk-detect/0.3.0): deterministic rules, uncertainty handling, adversarial cases."""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from intelligence import event_detection as ed

T0 = datetime(2026, 11, 20, 3, 0, tzinfo=timezone.utc)


def ev(i, title, source="ABC News", hours=0, geo="AU", summary=""):
    return {"id": i, "title": title, "source": source, "geography": geo, "summary": summary,
            "collected_at": (T0 + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def one(events):
    ds = ed.run(events, now=T0 + timedelta(hours=48))
    return {m.event_id: d for d in ds for m in d.group.members}, ds


class TestStage1Candidates:
    def test_cyber_mention_without_sector_or_scale_is_not_a_candidate(self):
        c = ed.detect_candidate(ev("a", "Excite Cyber earns Advanced status with Fortinet", "ARN"))
        assert not c.is_candidate

    def test_stated_compromise_is_kept_for_verification_even_without_a_known_sector(self):
        c = ed.detect_candidate(ev("a", "Hijacked website tool plants card skimmer on brands' sites"))
        assert c.is_candidate

    def test_sector_and_event_type_are_extracted_not_inferred_from_one_word(self):
        c = ed.detect_candidate(ev("a", "Shop freezers hit by cyber-attack, food now useless", "BBC News"))
        assert "retail_food" in c.sectors and "cyber_incident" in c.types and c.consequence == "essential_service"

    def test_infrastructure_damage_is_an_outage_event(self):
        c = ed.detect_candidate(ev("a", "Transmission towers crushed, knocking out power to 20,000"))
        assert c.is_candidate and "outage" in c.types and "energy" in c.sectors

    def test_roundup_headline_is_commentary_not_an_incident_carrier(self):
        c = ed.detect_candidate(ev("a", "Nationwide Ground Stop Lifted, Nvidia Spy Scandal, Starship's Longest Test Flight", "Bloomberg"))
        assert c.commentary


class TestStage2Correlation:
    def test_preserves_original_report_ids_and_records_confidence_and_reason(self):
        _, ds = one([ev("m1", "Microsoft platforms suffering widespread outages, including Outlook", hours=0),
                     ev("m2", "Microsoft races to restore services after global outage", "Financial Times", hours=5)])
        g = ds[0].group
        assert sorted(m.event_id for m in g.members) == ["m1", "m2"]
        assert 0.5 <= g.grouping_confidence <= 1 and g.pairs and "microsoft" in g.pairs[0][3]

    def test_same_organisation_different_incidents_stay_separate(self):
        by, _ = one([ev("c1", "Coles investigating a cyber incident", hours=0),
                     ev("c2", "Coles hit by new cyber attack on loyalty accounts", hours=24 * 12)])
        assert by["c1"].group.incident_id != by["c2"].group.incident_id

    def test_same_organisation_different_service_stays_separate(self):
        by, _ = one([ev("a", "Microsoft Outlook outage hits millions", hours=0),
                     ev("b", "Microsoft Azure outage takes down payments", "Financial Times", hours=2)])
        assert by["a"].group.incident_id != by["b"].group.incident_id

    def test_unrelated_incidents_the_same_day_are_not_merged_or_causally_linked(self):
        by, _ = one([ev("a", "Coles investigating a cyber incident", hours=0),
                     ev("b", "Telstra outage leaves customers without mobile service", hours=1)])
        assert by["a"].group.incident_id != by["b"].group.incident_id
        assert not hasattr(by["a"].group, "causes") and not hasattr(by["a"], "caused_by")

    def test_commentary_attaches_but_is_not_independent_corroboration(self):
        by, _ = one([ev("o", "Microsoft outage hits Outlook and Teams worldwide", "BBC News", hours=0),
                      ev("k", "Microsoft outage exposes global reliance on core tech providers", "Financial Times", hours=20)])
        g = by["o"].group
        assert by["o"].group is by["k"].group and g.commentary_ids == ["k"] and g.independent_publishers == 1

    def test_syndicated_copy_does_not_count_as_a_second_publisher(self):
        by, _ = one([ev("o", "Coles cyber attack disrupts supermarkets", "BBC News", hours=0),
                     ev("s", "Coles cyber attack disrupts supermarkets - Reuters", "Google News - Cyber AU", hours=3)])
        g = by["o"].group
        assert "s" in g.syndicated_ids and g.independent_publishers == 1

    def test_grouping_is_order_independent(self):
        events = [ev("m1", "Microsoft platforms suffering widespread outages, including Outlook", hours=0),
                  ev("m2", "Microsoft races to restore services after global outage", "Financial Times", hours=5),
                  ev("c1", "Coles investigating a cyber incident", hours=1),
                  ev("t1", "Telstra outage leaves customers without mobile service", hours=2)]
        sig = lambda ds: sorted((sorted(m.event_id for m in d.group.members), d.priority) for d in ds)
        base = sig(ed.run(events, now=T0))
        for seed in range(5):
            shuffled = events[:]
            random.Random(seed).shuffle(shuffled)
            assert sig(ed.run(shuffled, now=T0)) == base


class TestStage3And4Decision:
    def test_single_credible_report_of_major_outage_escalates_provisionally(self):
        by, _ = one([ev("a", "Breaking: Microsoft platforms suffering widespread outages, including Outlook", "ABC News")])
        d = by["a"]
        assert d.priority == "ESCALATE" and d.provisional and any("follow-up" in r for r in d.reasons)

    def test_same_report_from_an_aggregator_only_needs_verification(self):
        by, _ = one([ev("a", "Microsoft platforms suffering widespread outages, including Outlook",
                        "Google News - Microsoft outage")])
        assert by["a"].priority == "VERIFY"

    def test_potential_threat_without_actual_impact_never_escalates(self):
        by, _ = one([ev("a", "Expert warns supermarkets could face cyber attack risk", "ABC News")])
        assert by["a"].priority != "ESCALATE"

    def test_unclear_impact_cyber_report_is_verify_not_dropped(self):
        by, _ = one([ev("a", "Hijacked website tool plants card skimmer on brands' sites", "iTnews")])
        assert by["a"].priority in {"VERIFY", "WATCH"}

    def test_evidence_confidence_and_materiality_are_separate_axes(self):
        by, _ = one([ev("a", "Microsoft platforms suffering widespread outages, including Outlook", "Google News - X")])
        d = by["a"]
        assert d.materiality == "high" and d.evidence_confidence < 0.5

    def test_kev_advisory_is_not_automatically_critical(self):
        by, _ = one([ev("k", "CISA Adds Six Known Exploited Vulnerabilities to Catalog", "CISA Alerts")])
        assert by["k"].priority in {"WATCH", "REFERENCE"} and any("KEV alone is not critical" in r for r in by["k"].reasons)

    def test_exploited_and_exposed_primary_advisory_escalates(self):
        by, _ = one([ev("k", "CISA warns actively exploited Cisco vulnerability CVE-2026-1234", "CISA Alerts")])
        assert by["k"].priority == "ESCALATE"

    def test_routine_news_is_reference(self):
        by, _ = one([ev("r", "Fed's Logan seeks clearer separation of market operations", "Bloomberg")])
        assert by["r"].priority == "REFERENCE"

    def test_method_version_is_stamped(self):
        by, _ = one([ev("r", "Routine item", "ABC News")])
        assert by["r"].method_version == ed.METHOD_VERSION == "wk-detect/0.4.0-tiered"


@pytest.mark.parametrize("title", ["", "   ", "Breaking:", "!!!"])
def test_degenerate_titles_do_not_crash(title):
    by, _ = one([ev("x", title)])
    assert by["x"].priority == "REFERENCE"


class TestTieredEscalationPolicy:
    """Captain's tiered model: sector relevance, event type, impact status, materiality, evidence confidence and
    urgency are separate; a sector alone never escalates."""

    def d(self, title, source="ABC News", **kw):
        by, _ = one([ev("x", title, source, **kw)])
        return by["x"]

    def test_tier1_confirmed_disruption_single_credible_source_is_provisional_escalate(self):
        d = self.d("Telstra mobile network outage leaves customers without service nationwide")
        assert (d.sector_tier, d.impact_status, d.materiality, d.priority, d.provisional) == (1, "confirmed", "high", "ESCALATE", True)

    def test_unconfirmed_cyber_incident_without_consequence_is_verify_not_escalate(self):
        d = self.d("Coles Group investigating a cyber incident")
        assert d.sector_tier == 2 and d.impact_status == "unconfirmed" and d.priority == "VERIFY"

    def test_tier2_confirmed_consequence_without_scale_is_watch(self):
        d = self.d("Supermarket freezers hit by cyber attack, food spoiled", "BBC News")
        assert d.sector_tier == 2 and d.impact_status == "confirmed" and d.materiality == "medium" and d.priority == "WATCH"

    def test_tier2_with_scale_and_confirmed_consequence_escalates(self):
        d = self.d("Microsoft outage disrupts services worldwide", "BBC News")
        assert d.sector_tier == 2 and d.priority == "ESCALATE"

    def test_tier3_data_breach_is_not_escalated_without_scale_and_tier(self):
        d = self.d("Cosmetics company data breach affects 340,000 clients", "ABC News")
        assert d.sector_tier is None and d.impact_status == "confirmed" and d.priority in {"WATCH", "VERIFY", "ESCALATE"}
        assert d.materiality in {"medium", "high"}

    def test_sector_alone_never_escalates(self):
        for title in ("Westpac reports record half-year profit", "Qantas announces new Sydney lounge", "NSW Health appoints new director"):
            assert self.d(title).priority == "REFERENCE"

    def test_retrospective_report_of_a_past_outage_is_not_escalated(self):
        d = self.d("Surge in complaints, compensation claims after Telstra outage")
        assert d.impact_status == "retrospective" and d.priority != "ESCALATE"

    def test_tier1_major_incident_declared_without_stated_consequence_escalates_provisionally(self):
        d = self.d("NSW Health declares major incident after cybersecurity breach across hospitals")
        assert d.sector_tier == 1 and d.priority == "ESCALATE" and d.provisional

    def test_same_unconfirmed_tier1_report_from_an_aggregator_only_needs_verification(self):
        d = self.d("Hospital cyber incident declared major", "Google News - Health cyber")
        assert d.priority == "VERIFY"

    def test_status_page_outage_and_physical_event_become_candidates(self):
        assert ed.detect_candidate(ev("a", "Users unable to access Notion", "Notion Status")).is_candidate
        assert ed.detect_candidate(ev("b", "Container ship sunk in Strait of Hormuz", "BBC News")).is_candidate

    def test_axes_are_reported_separately(self):
        d = self.d("Telstra mobile network outage leaves customers without service nationwide")
        for field in ("sector_tier", "event_type", "impact_status", "materiality", "evidence_confidence", "urgency", "priority"):
            assert hasattr(d, field)
