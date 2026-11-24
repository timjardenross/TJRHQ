"""Tests for tools/intelligence/analytics/dependency_evidence.py (offline, default OFF)."""

import json
import sys
import unittest
from pathlib import Path

ANALYTICS = Path(__file__).resolve().parent.parent / "tools" / "intelligence" / "analytics"
FIX = ANALYTICS / "fixtures" / "dependency_evidence"
sys.path.insert(0, str(ANALYTICS))

import dependency_evidence as de

D, M = de.BASIS_DOCUMENTED, de.BASIS_DEMONSTRATED


def inc(text, source="Some News", cls=de.CLASS_NEWS_INCIDENT):
    return de.extract_from_incident(text, source, "https://x/1", "2026-11-01", cls, enabled=True)


def sub(name, vendor):
    return de.extract_from_subprocessor_list((FIX / name).read_text(), vendor, "https://v/sub", "2026-11-24", enabled=True)


class TestDefaultOff(unittest.TestCase):
    def test_off_without_flag(self):
        import os

        os.environ.pop(de.ENV_FLAG, None)
        self.assertTrue(de.extract_from_incident("x due to the AWS outage", "n", "u", "t").disabled)
        self.assertTrue(de.extract_events([]).disabled)
        self.assertTrue(de.extract_from_subprocessor_list("", "Zoom", "u", "t").disabled)

    def test_env_flag_enables(self):
        import os

        os.environ[de.ENV_FLAG] = "1"
        try:
            self.assertFalse(de.extract_events([]).disabled)
        finally:
            os.environ.pop(de.ENV_FLAG)


class TestDemonstrated(unittest.TestCase):
    def test_named_party_cause_clause(self):
        r = inc("Telstra and Optus websites disrupted by AWS outage")
        self.assertEqual({(x["provider_from"], x["provider_to"]) for x in r.records},
                         {("telstra", "aws"), ("optus", "aws")})
        self.assertTrue(all(x["relation_basis"] == M and x["relation"] == "depends_on" for x in r.records))
        self.assertTrue(all(x["evidence_span"] for x in r.records))

    def test_own_feed_first_person(self):
        r = inc("We're experiencing degraded service for Outlook integrations (e.g. mail, calendar) due to the Microsoft "
                "Outlook outage here: https://s", "Notion Status", de.CLASS_STATUS_INCIDENT)
        self.assertEqual([(x["provider_from"], x["provider_to"]) for x in r.records], [("notion", "microsoft")])
        self.assertIn("Microsoft Outlook outage", r.records[0]["evidence_span"])

    def test_own_feed_needs_first_person(self):
        r = inc("Degraded service due to the Microsoft Outlook outage", "Notion Status", de.CLASS_STATUS_INCIDENT)
        self.assertEqual(r.records, [])
        self.assertEqual(r.excluded[0]["reason"], "no_named_affected_party")

    def test_unnamed_affected_party_not_recorded(self):
        r = inc("Dozens of Triple Zero calls fail due to Optus outage")
        self.assertEqual(r.records, [])

    def test_unnamed_upstream_not_inferred(self):
        r = inc("We have identified an issue with an upstream provider affecting the Microsoft 365 connector.",
                "Anthropic (Claude) Status", de.CLASS_STATUS_INCIDENT)
        self.assertEqual(r.records, [])
        self.assertEqual(r.excluded[0]["reason"], "unnamed_upstream_provider")

    def test_hedged_and_negated(self):
        for t in ("Slack was not affected by the AWS outage", "Zoom may have been hit by the Cloudflare outage",
                  "Reportedly Salesforce was disrupted by the Azure outage"):
            self.assertEqual(inc(t).records, [], t)

    def test_self_reference_and_distance(self):
        self.assertEqual(inc("Cloudflare degraded due to the Cloudflare outage").records, [])
        far = "Telstra reported " + "x " * 80 + "calls failed due to the Optus outage"
        self.assertEqual(inc(far).records, [])

    def test_static_claims_are_excluded_not_recorded(self):
        r = inc("NAB deploys AI for staff called Ruby that is built on Anthropic.")
        self.assertEqual(r.records, [])
        self.assertTrue(r.excluded[0]["reason"].startswith("static_supply_claim"))

    def test_class_must_be_incident(self):
        with self.assertRaises(ValueError):
            de.extract_from_incident("t", "n", "u", "t", de.CLASS_SUBPROCESSOR, enabled=True)

    def test_name_collision(self):
        self.assertEqual(inc("Chaos due to the Notion of fairness issue").records, [])

    def test_forward_pattern(self):
        r = inc("A major Cloudflare outage is impacting Zoom")
        self.assertEqual([(x["provider_from"], x["provider_to"]) for x in r.records], [("zoom", "cloudflare")])


class TestDocumented(unittest.TestCase):
    def test_supabase_rows_and_relations(self):
        r = sub("supabase_subprocessors.md", "Supabase")
        pairs = {(x["provider_to"], x["relation"]) for x in r.records}
        for exp in [("aws", "hosted_on"), ("cloudflare", "hosted_on"), ("google", "hosted_on"), ("fly_io", "hosted_on"),
                    ("vercel", "hosted_on"), ("github", "supplied_by"), ("notion", "supplied_by")]:
            self.assertIn(exp, pairs)
        self.assertEqual(len(r.records), 17)  # includes header-less continuation table
        self.assertTrue(all(x["provider_from"] == "supabase" and x["relation_basis"] == D for x in r.records))
        self.assertFalse([x for x in r.records if x["provider_to"] == "supabase"])  # vendor's own row skipped

    def test_anthropic_bullet_rows(self):
        r = sub("anthropic_subprocessors.md", "Anthropic")
        self.assertEqual({(x["provider_to"], x["relation"]) for x in r.records},
                         {("aws", "hosted_on"), ("microsoft", "hosted_on"), ("cloudflare", "supplied_by"),
                          ("stripe", "supplied_by"), ("twilio", "supplied_by")})

    def test_relation_read_from_purpose_column_only(self):
        # Cloudflare's OpenAI row mentions "cloud infrastructure" only in the location column: supplier, not host.
        r = sub("cloudflare_subprocessors.md", "Cloudflare")
        got = {(x["provider_to"], x["relation"]) for x in r.records}
        self.assertIn(("openai", "supplied_by"), got)
        self.assertNotIn(("openai", "hosted_on"), got)
        self.assertEqual(len(r.records), 8)

    def test_anthropic_span_has_no_markup_residue(self):
        for x in sub("anthropic_subprocessors.md", "Anthropic").records:
            self.assertFalse(x["evidence_span"].startswith("<br>"))

    def test_entity_tables_are_skipped(self):
        for f, v in (("openai_subprocessors.md", "OpenAI"), ("cloudflare_subprocessors.md", "Cloudflare"),
                     ("zoom_subprocessors.md", "Zoom")):
            r = sub(f, v)
            names = {x["provider_to"] for x in r.records}
            self.assertFalse(names & {"OpenAI, OpCo, LLC", "OpenAI Ireland Ltd.", "Cloudflare Ltd.", "Cloudflare Pte. Ltd.",
                                      "Zoom Communications, Inc.", "ZVC Netherlands B.V."}, f)

    def test_openai_counts(self):
        self.assertEqual(len(sub("openai_subprocessors.md", "OpenAI").records), 8)

    def test_evidence_span_is_the_row(self):
        for x in sub("zoom_subprocessors.md", "Zoom").records:
            self.assertTrue(x["evidence_span"].startswith("|"))
            self.assertIn("Cloud Service Provider" if x["relation"] == "hosted_on" else "|", x["evidence_span"])

    def test_vendor_prose_requires_vendor_subject(self):
        txt = (FIX / "notion_data_residency_excerpt.txt").read_text()
        r = de.extract_from_vendor_prose(txt, "Notion", "https://n", "2026-11-24", enabled=True)
        self.assertEqual([(x["provider_from"], x["provider_to"], x["relation"]) for x in r.records],
                         [("notion", "aws", "hosted_on")])
        r2 = de.extract_from_vendor_prose("Zoom is hosted by AWS.", "Notion", "u", "t", enabled=True)
        self.assertEqual(r2.records, [])
        self.assertEqual(r2.excluded[0]["reason"], "subject_is_not_the_publishing_vendor")

    def test_status_components_names_groups_regions_yield_nothing(self):
        txt = (FIX / "cloudflare_components_excerpt.json").read_text()
        self.assertEqual(de.extract_from_status_components(txt, "Cloudflare", "u", "t", enabled=True).records, [])
        regions = {"components": [{"name": "ap-southeast-1", "description": None}, {"name": "us-east-1"}]}
        self.assertEqual(de.extract_from_status_components(regions, "Supabase", "u", "t", enabled=True).records, [])

    def test_status_components_explicit_description_synthetic(self):
        synthetic = {"components": [{"name": "Payments", "description": "Card processing hosted on AWS"}]}
        r = de.extract_from_status_components(synthetic, "Acme", "u", "t", enabled=True)
        self.assertEqual([(x["provider_to"], x["relation"], x["relation_basis"]) for x in r.records],
                         [("aws", "hosted_on", D)])


class TestBasisSeparation(unittest.TestCase):
    def test_basis_matches_class_and_is_enforced(self):
        with self.assertRaises(AssertionError):
            de._record("a", "b", "depends_on", D, "s", "u", de.CLASS_NEWS_INCIDENT, "t")
        with self.assertRaises(AssertionError):
            de._record("a", "b", "depends_on", M, "s", "u", de.CLASS_SUBPROCESSOR, "t")

    def test_fixture_events_end_to_end(self):
        rows = [json.loads(line) for line in (FIX / "events_candidates.jsonl").read_text().splitlines()]
        res = de.extract_events(rows, enabled=True)
        self.assertEqual([(r["provider_from"], r["provider_to"], r["relation_basis"]) for r in res.records],
                         [("notion", "microsoft", M)])
        reasons = {e["reason"] for e in res.excluded}
        self.assertTrue({"unnamed_upstream_provider", "no_named_affected_party"} <= reasons)
        self.assertTrue(any(e["reason"].startswith("static_supply_claim") for e in res.excluded))


class TestConcentrationRule(unittest.TestCase):
    def _recs(self):
        out = []
        for f, v in (("supabase_subprocessors.md", "Supabase"), ("anthropic_subprocessors.md", "Anthropic"),
                     ("openai_subprocessors.md", "OpenAI"), ("zoom_subprocessors.md", "Zoom")):
            out += sub(f, v).records
        return out

    def test_unverified_records_give_nothing(self):
        r = de.concentration_eligibility(self._recs(), "aws")
        self.assertFalse(r[D]["eligible"] or r[M]["eligible"])

    def test_verified_documented_only_never_merges_bases(self):
        recs = self._recs()
        for x in recs:
            x["verified"] = True
        r = de.concentration_eligibility(recs, "aws")
        self.assertTrue(r[D]["eligible"])
        self.assertEqual(r[D]["distinct_dependents"], 4)
        self.assertFalse(r[M]["eligible"])
        self.assertEqual(r[M]["distinct_dependents"], 0)
        self.assertNotIn("score", json.dumps(r).replace("no score is computed", ""))

    def test_demonstrated_needs_independent_events(self):
        recs = []
        for i, frm in enumerate(["a", "b", "c"]):
            recs.append({"provider_from": frm, "provider_to": "aws", "relation_basis": M, "source_url": "same", "verified": True})
        self.assertFalse(de.concentration_eligibility(recs, "aws")[M]["eligible"])  # one event
        recs[2]["source_url"] = "other"
        self.assertTrue(de.concentration_eligibility(recs, "aws")[M]["eligible"])


if __name__ == "__main__":
    unittest.main()
