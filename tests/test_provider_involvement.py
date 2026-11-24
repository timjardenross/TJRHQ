"""Tests for tools/intelligence/analytics/provider_involvement.py (offline, default-OFF taxonomy)."""

import sys
import unittest
from pathlib import Path

ANALYTICS = (
    Path(__file__).resolve().parent.parent / "tools" / "intelligence" / "analytics"
)
sys.path.insert(0, str(ANALYTICS))

import provider_involvement as pi

T = pi.InvolvementTagger()


def tags(title, summary="", src=None):
    return {t.provider: t for t in T.tag(title, summary, src)}


class TestTaxonomy(unittest.TestCase):
    def test_default_off(self):
        self.assertEqual(pi.tag_item("Cloudflare outage"), [])
        self.assertTrue(pi.tag_item("Cloudflare outage", enabled=True))

    def test_plain_mention(self):
        t = tags("Cloudflare launches new developer platform features")
        self.assertEqual(t["cloudflare"].cls, pi.MENTIONED)

    def test_directly_involved_subject_with_incident(self):
        t = tags("Okta confirms breach of support system")
        self.assertEqual(t["okta"].cls, pi.DIRECTLY_INVOLVED)
        self.assertIn("Okta confirms breach", t["okta"].evidence_span)

    def test_outage_at_provider(self):
        t = tags("Major outage at Optus leaves customers without service")
        self.assertEqual(t["optus"].cls, pi.DIRECTLY_INVOLVED)

    def test_own_feed(self):
        t = tags("Scheduled maintenance", "", "GitHub Status")
        self.assertEqual(t["github"].cls, pi.DIRECTLY_INVOLVED)
        self.assertEqual(t["github"].rule, "own_feed")

    def test_affected_named_agent(self):
        t = tags("Slack and Zoom disrupted by AWS outage")
        self.assertEqual(t["slack"].cls, pi.AFFECTED)
        self.assertEqual(t["slack"].agent, "aws")
        self.assertEqual(t["aws"].cls, pi.DIRECTLY_INVOLVED)

    def test_active_agent(self):
        t = tags("Cloudflare outage knocks out Atlassian and Canva")
        self.assertEqual(t["atlassian"].cls, pi.AFFECTED)
        self.assertEqual(t["cloudflare"].cls, pi.DIRECTLY_INVOLVED)

    def test_supplying(self):
        t = tags("Retail sites hosted by Fastly returned errors")
        self.assertEqual(t["fastly"].cls, pi.SUPPLYING)
        t = tags("Telco relies on Akamai for web delivery")
        self.assertEqual(t["akamai"].cls, pi.SUPPLYING)

    def test_uncertain_hedged(self):
        t = tags("Okta may have been breached, reportedly")
        self.assertEqual(t["okta"].cls, pi.UNCERTAIN)
        self.assertTrue(t["okta"].hedged)

    def test_uncertain_unnamed_agent(self):
        t = tags("Services disrupted by a cloud outage hit Telstra")
        self.assertIn(t["telstra"].cls, (pi.UNCERTAIN, pi.MENTIONED))
        self.assertNotEqual(t["telstra"].cls, pi.AFFECTED)


class TestAdversarial(unittest.TestCase):
    def test_provider_named_only_in_headline_about_another_provider(self):
        # Okta is a bystander in a story about Cisco; must stay MENTIONED.
        t = tags("Cisco patches firewall flaw, says Okta customers were not targeted")
        self.assertEqual(t["cisco"].cls, pi.DIRECTLY_INVOLVED)
        self.assertEqual(t["okta"].cls, pi.MENTIONED)
        t = tags(
            "Fortinet warns of exploited flaw, compared with last year's Cisco bug"
        )
        self.assertEqual(t["fortinet"].cls, pi.DIRECTLY_INVOLVED)
        self.assertEqual(t["cisco"].cls, pi.MENTIONED)

    def test_customer_named_as_affected_is_not_a_dependency(self):
        t = tags("Telstra and Optus websites disrupted by AWS outage")
        self.assertEqual(t["telstra"].cls, pi.AFFECTED)
        self.assertEqual(t["optus"].cls, pi.AFFECTED)
        for x in t.values():
            self.assertFalse(x.dependency_proven)
            self.assertFalse(pi.reportable_as_dependency(x))
            self.assertNotIn(
                "depends on",
                pi.describe(x)
                .replace("not evidence that", "")
                .replace("depends on", "", 0)
                .split("(")[0],
            )

    def test_unmapped_customer_does_not_create_tag(self):
        t = tags("Qantas and Commonwealth Bank customers hit by CrowdStrike outage")
        self.assertEqual(set(t), {"crowdstrike"})
        self.assertEqual(t["crowdstrike"].cls, pi.DIRECTLY_INVOLVED)

    def test_negation_is_not_affected(self):
        t = tags("Slack not affected by AWS outage, company says")
        self.assertEqual(t["slack"].cls, pi.MENTIONED)

    def test_no_class_is_ever_proven_dependency(self):
        samples = [
            "Okta breach",
            "Slack disrupted by AWS outage",
            "sites hosted by Fastly down",
            "Cloudflare launches X",
            "Okta may be breached",
        ]
        for s in samples:
            for tg in T.tag(s):
                self.assertFalse(tg.dependency_proven)

    def test_ambiguous_common_words_do_not_match(self):
        self.assertEqual(tags("Notion of fairness in sentencing"), {})
        self.assertEqual(tags("Slack Technologies founder speaks"), {})
        self.assertEqual(tags("Climbers missing after avalanche"), {})

    def test_conflicting_roles_become_uncertain(self):
        t = tags(
            "Okta confirms breach", "Okta customers disrupted by Cloudflare outage"
        )
        self.assertEqual(t["okta"].cls, pi.UNCERTAIN)
        self.assertTrue(t["okta"].rule.startswith("conflict:"))

    def test_evidence_span_recorded(self):
        t = tags(
            "Weekly roundup",
            "Quiet week. Fastly reports degraded performance in Sydney. More later.",
        )
        self.assertEqual(t["fastly"].field, "summary")
        self.assertIn("degraded performance", t["fastly"].evidence_span)
        self.assertEqual(t["fastly"].cls, pi.DIRECTLY_INVOLVED)

    def test_every_class_has_requirement_text(self):
        self.assertEqual(set(pi.EVIDENCE_REQUIREMENTS), set(pi.CLASSES))


class TestAuditRegressions(unittest.TestCase):
    """Defects found by hand-auditing the first 30-item sample (docs/PROVIDER-TAXONOMY-AND-DEPENDENCY-EVIDENCE.md)."""

    def test_users_using_is_not_supplying(self):
        t = tags(
            "Service Degradation Affecting Subset of Users using Zoom Phone Calls in Europe"
        )
        self.assertNotEqual(t["zoom"].cls, pi.SUPPLYING)

    def test_backed_by_investor_is_not_supplying(self):
        t = tags(
            "Anthropic strikes deal",
            "New company backed by Anthropic and a buyout group will advise firms",
        )
        self.assertNotEqual(t["anthropic"].cls, pi.SUPPLYING)

    def test_researchers_using_models_is_not_supplying(self):
        t = tags("OpenAI breached by researchers using Anthropic models")
        self.assertNotEqual(t["anthropic"].cls, pi.SUPPLYING)

    def test_built_on_still_supplying(self):
        t = tags("NAB deploys AI for staff called Ruby that is built on Anthropic")
        self.assertEqual(t["anthropic"].cls, pi.SUPPLYING)

    def test_vuln_boilerplate_could_allow_is_not_hedged(self):
        t = tags(
            "CVE-2026-1",
            "A vulnerability in Cisco ISE could allow an attacker to execute commands.",
        )
        self.assertEqual(t["cisco"].cls, pi.DIRECTLY_INVOLVED)

    def test_vulnerabilities_affecting_product(self):
        t = tags(
            "Alert",
            "Alert on critical vulnerabilities affecting Citrix NetScaler ADC and Gateway products.",
        )
        self.assertEqual(t["citrix"].cls, pi.DIRECTLY_INVOLVED)

    def test_own_incident_before_effect(self):
        t = tags("Telstra admits glitch as Griffith customers hit by network problems")
        self.assertEqual(t["telstra"].cls, pi.DIRECTLY_INVOLVED)

    def test_unnamed_cause_still_not_affected_class(self):
        t = tags("Slack users hit by cloud outage")
        self.assertEqual(t["slack"].cls, pi.UNCERTAIN)

    def test_kev_cve_product(self):
        t = tags(
            "CISA adds KEVs",
            "CVE-2026-1 GitLab Edition flaw CVE-2026-2 Cisco Secure Firewall ASA Software",
        )
        self.assertEqual(t["cisco"].cls, pi.DIRECTLY_INVOLVED)

    def test_di_beats_supplying_across_clauses(self):
        t = tags(
            "Telstra enterprise experiences ordering issues",
            "Service provided by Telstra.",
        )
        self.assertEqual(t["telstra"].cls, pi.DIRECTLY_INVOLVED)


if __name__ == "__main__":
    unittest.main()
