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
        assert by["r"].method_version == ed.METHOD_VERSION == "wk-detect/0.6.0-v1c"


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
        assert (d.sector_tier, d.impact_status, d.materiality, d.priority, d.provisional) == (1, "stated", "high", "ESCALATE", True)

    def test_unconfirmed_cyber_incident_without_consequence_is_verify_not_escalate(self):
        d = self.d("Coles Group investigating a cyber incident")
        assert d.sector_tier == 2 and d.impact_status == "unconfirmed" and d.priority == "VERIFY"

    def test_tier2_confirmed_consequence_without_scale_is_watch(self):
        d = self.d("Supermarket freezers hit by cyber attack, food spoiled", "BBC News")
        assert d.sector_tier == 2 and d.impact_status == "stated" and d.materiality == "medium" and d.priority == "WATCH"

    def test_tier2_with_scale_and_confirmed_consequence_escalates(self):
        d = self.d("Microsoft outage disrupts services worldwide", "BBC News")
        assert d.sector_tier == 2 and d.priority == "ESCALATE"

    def test_confirmed_breach_at_unrecognised_sector_is_not_escalated_by_a_number_alone(self):
        d = self.d("Cosmetics company data breach affects 340,000 clients", "ABC News")
        assert d.sector_tier is None and d.impact_status == "stated" and d.priority == "WATCH"   # "340,000" must not read as 000 (triple zero)

    def test_sector_alone_never_escalates(self):
        for title in ("Westpac reports record half-year profit", "Qantas announces new Sydney lounge", "NSW Health appoints new director"):
            assert self.d(title).priority == "REFERENCE"

    def test_retrospective_report_of_a_past_outage_is_not_escalated(self):
        d = self.d("Surge in complaints, compensation claims after Telstra outage")
        assert d.impact_status == "retrospective" and d.priority != "ESCALATE"

    def test_unconfirmed_tier1_breach_is_verify_even_when_called_a_major_incident(self):
        d = self.d("NSW Health declares major incident after cybersecurity breach across hospitals")
        assert d.sector_tier == 1 and d.impact_status == "unconfirmed" and d.priority == "VERIFY" and not d.provisional

    def test_brief_tier1_outage_is_not_severe_on_its_own(self):
        d = self.d("Authorities investigating four-minute Triple Zero outage in Canberra")
        assert d.sector_tier == 1 and d.materiality == "medium" and d.priority == "WATCH"

    def test_safety_consequence_is_high_materiality_in_any_tier(self):
        d = self.d("Resort fire injures 12 guests, evacuation under way", "ABC News")
        assert d.impact_status == "stated" and d.materiality == "high" and d.priority == "ESCALATE" and d.provisional

    def test_cascading_impact_is_high_materiality(self):
        d = self.d("Power outage cascades across multiple sectors in Victoria", "ABC News")
        assert d.materiality == "high" and d.priority == "ESCALATE"

    def test_kev_listing_is_not_escalated(self):
        d = self.d("CISA Adds Six Known Exploited Vulnerabilities to Catalog", "CISA Alerts")
        assert d.priority in {"WATCH", "REFERENCE"}

    def test_tier_lists_follow_the_approved_model(self):
        assert {k: v for k, v in ed.SECTOR_TIER.items() if v == 1} == {k: 1 for k in
            ("emergency_services", "energy", "telecom", "health", "aviation", "transport_water", "finance")}
        assert {k for k, v in ed.SECTOR_TIER.items() if v == 2} == {"cloud_platform", "retail_food", "government"}
        assert ed.SECTOR_TIER["consumer_service"] == 3

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


class TestRegionalOutageProportionality:
    """Captain, 2026-11-23: a credible report of a significant active regional electricity outage of about 20,000 customers is
    a provisional ESCALATE; customer count is not a universal threshold; the record carries the facts to verify."""

    def d(self, title, source="ABC News", **kw):
        by, _ = one([ev("x", title, source, **kw)])
        return by["x"]

    def test_thousands_separator_comma_is_not_a_roundup_boundary(self):
        c = ed.detect_candidate(ev("a", "Breaking: Transmission towers 'crushed', knocking out power to 20,000 customers"))
        assert not c.commentary and c.customers == 20000

    def test_active_regional_outage_of_20000_customers_is_provisional_escalate(self):
        d = self.d("Regional power outage still affecting 20,000 customers after transmission towers crushed")
        assert d.priority == "ESCALATE" and d.provisional and d.materiality == "high"

    def test_restored_outage_is_not_escalated(self):
        d = self.d("Power restored to 20,000 customers after storm")
        assert d.priority != "ESCALATE"

    def test_small_regional_outage_is_not_escalated_by_the_rule(self):
        d = self.d("Power out for 300 customers after a car hits a pole, partial outage in one suburb")
        assert d.priority != "ESCALATE"

    def test_escalation_record_carries_the_required_facts(self):
        d = self.d("Breaking: Transmission towers 'crushed', knocking out power to 20,000 customers")
        r = ed.escalation_record(d)
        assert r["impact"] == "stated in headline" and r["affected_customers"] == 20000 and r["restoration_status"] == "ongoing"
        assert r["critical_service_dependencies"] == ["energy"] and r["sector_tier"] == 1 and r["geographic_scope"] == ["AU"]
        assert r["source_confidence"]["provisional"] is True and r["source_confidence"]["independent_publishers"] == 1
        assert "operator" in r["next_verification_action"] and r["report_ids"] == ["x"]

    def test_more_reports_reassess_the_same_incident_and_clear_provisional(self):
        by, _ = one([ev("a", "Transmission towers crushed, knocking out power to 20,000 customers", "ABC News", hours=0),
                     ev("b", "Power still out for 20,000 customers after towers crushed - AEMO update", "AEMO Market Notices", hours=3)])
        assert by["a"].group is by["b"].group and by["a"].provisional is False


class TestV1PrecisionGuards:
    """Defects found when the V1 pipeline was run on a real week (2,514 reports): false escalations from summaries, court verdicts,
    commentary magazines, politics, market words and hedged reports."""

    def d(self, title, source="ABC News"):
        by, _ = one([ev("x", title, source)])
        return by["x"]

    def test_detection_uses_the_headline_only(self):
        e = ev("a", "Bloomberg wrap of the day", "Bloomberg", summary="a data breach, outage and blackout were discussed")
        assert not ed.detect_candidate(e).is_candidate

    def test_court_verdict_about_a_fire_is_not_an_incident(self):
        assert self.d("Man convicted of starting deadly Palisades fire in Los Angeles", "BBC News").priority != "ESCALATE"

    def test_magazine_commentary_is_not_an_incident_report(self):
        assert self.d("All these outages show how corporate America needs to modernize", "Inc. Magazine — Leadership").priority == "REFERENCE"

    def test_political_framing_of_blackout_risk_is_not_a_confirmed_blackout(self):
        assert self.d("Blackout warnings as Victorian Liberal leader throws open doors to gas").priority != "ESCALATE"

    def test_hedged_data_exposure_is_unconfirmed_and_goes_to_verify(self):
        d = self.d("Australia's Bell Financial says some client data likely accessed", "iTnews")
        assert d.impact_status == "unconfirmed" and d.priority == "VERIFY"

    def test_deal_failure_is_not_a_system_failure(self):
        assert self.d("Breaking: COP31 deal failure 'very disappointing', Chris Bowen says").priority == "REFERENCE"

    def test_post_incident_investigation_is_retrospective(self):
        assert self.d("'One-in-2,000-year weather' to be investigated post-blackout").priority != "ESCALATE"
