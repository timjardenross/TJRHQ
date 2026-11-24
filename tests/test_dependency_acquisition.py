"""Tests for tools/intelligence/analytics/dependency_acquisition.py and its dependency_evidence extensions (offline)."""

import copy
import json
import os
import sys
import unittest
from pathlib import Path

ANALYTICS = Path(__file__).resolve().parent.parent / "tools" / "intelligence" / "analytics"
FIX = Path(__file__).resolve().parent / "fixtures" / "dependency_acquisition"
sys.path.insert(0, str(ANALYTICS))

import dependency_acquisition as da
import dependency_evidence as de

D, M = de.BASIS_DOCUMENTED, de.BASIS_DEMONSTRATED
ACQ = da.build_acquired(enabled=True)


def inc(text, source="Some News", cls=de.CLASS_NEWS_INCIDENT):
    return de.extract_from_incident(text, source, "https://x/1", "2026-11-01", cls, enabled=True)


class TestDefaultOff(unittest.TestCase):
    def test_off_without_flag(self):
        os.environ.pop(da.ENV_FLAG, None)
        self.assertTrue(da.build_acquired()["disabled"])


class TestAcquiredSet(unittest.TestCase):
    def test_no_invalid_records_and_counts_are_pinned(self):
        self.assertEqual(ACQ["invalid"], [])
        self.assertEqual(len(ACQ["demonstrated"]), 9)
        self.assertEqual(len(ACQ["documented"]), 65)

    def test_every_record_has_the_required_fields_and_a_short_verbatim_span(self):
        for rec in ACQ["documented"] + ACQ["demonstrated"]:
            self.assertEqual(da.validate_record(rec, da.source_text_for(rec)), [], rec["evidence_span"])
            self.assertLessEqual(len(rec["evidence_span"].replace(" …", "").split()), 40)

    def test_bases_never_mixed_and_no_score_fields(self):
        self.assertTrue(all(r["relation_basis"] == D and r["source_class"] in de.DOCUMENTED_CLASSES for r in ACQ["documented"]))
        self.assertTrue(all(r["relation_basis"] == M and r["source_class"] in de.DEMONSTRATED_CLASSES for r in ACQ["demonstrated"]))
        banned = {"score", "rank", "ranking", "concentration_score", "exposure_score"}
        for r in ACQ["documented"] + ACQ["demonstrated"]:
            self.assertFalse(banned & set(r))

    def test_demonstrated_records_are_dated_events(self):
        for r in ACQ["demonstrated"]:
            self.assertRegex(r["evidence_date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_committed_output_matches_rebuild(self):
        committed = json.loads((ANALYTICS / "fixtures" / "cascade" / "acquired_dependency_records.json").read_text())
        self.assertEqual(committed["documented"], json.loads(json.dumps(ACQ["documented"], default=str)))
        self.assertEqual(committed["demonstrated"], json.loads(json.dumps(ACQ["demonstrated"], default=str)))

    def test_pairs_found(self):
        dem = {(r["provider_from"], r["provider_to"]) for r in ACQ["demonstrated"]}
        for pair in [("miro", "aws"), ("canva", "cloudflare"), ("slack", "aws"), ("atlassian", "aws"), ("optus", "singtel"),
                     ("optus", "nokia"), ("telstra", "crowdstrike"), ("telstra", "microsoft")]:
            self.assertIn(pair, dem)
        doc = {(r["provider_from"], r["provider_to"]) for r in ACQ["documented"]}
        for pair in [("salesforce", "aws"), ("twilio", "aws"), ("atlassian", "aws"), ("datadog", "aws"), ("okta", "cloudflare"),
                     ("vercel", "aws"), ("github", "microsoft"), ("slack", "aws"), ("australian_carriers_and_csps", "telstra")]:
            self.assertIn(pair, doc)


class TestValidator(unittest.TestCase):
    def setUp(self):
        self.rec = copy.deepcopy(next(r for r in ACQ["demonstrated"] if r["provider_from"] == "canva"))
        self.src = da.source_text_for(self.rec)

    def test_baseline_valid(self):
        self.assertEqual(da.validate_record(self.rec, self.src), [])

    def test_span_not_in_source(self):
        self.rec["evidence_span"] = "Canva is down due to a Cloudflare outage that never happened."
        self.assertIn("span_not_verbatim_in_source", da.validate_record(self.rec, self.src))

    def test_span_over_40_words(self):
        self.rec["evidence_span"] = " ".join(["Cloudflare"] * 41)
        self.assertIn("span_over_40_words", da.validate_record(self.rec, " ".join(["Cloudflare"] * 41)))

    def test_demonstrated_needs_date(self):
        self.rec["evidence_date"] = da.NOT_STATED
        self.assertIn("demonstrated_needs_a_dated_event", da.validate_record(self.rec, self.src))

    def test_basis_class_mismatch(self):
        self.rec["relation_basis"] = D
        self.assertIn("basis_does_not_match_source_class", da.validate_record(self.rec, self.src))

    def test_missing_au_relevance(self):
        self.rec["au_relevance"] = ""
        self.assertIn("missing:au_relevance", da.validate_record(self.rec, self.src))

    def test_span_must_name_provider_to(self):
        self.rec["provider_to"] = "oracle"
        self.assertIn("span_does_not_name_provider_to", da.validate_record(self.rec, self.src))


class TestExtractorExtensions(unittest.TestCase):
    def test_own_feed_retrospective_disruption(self):
        r = inc("[Impact: minor] Earlier disruptions were due to a significant Amazon Web Services outage.", "Miro Status",
                de.CLASS_STATUS_INCIDENT)
        self.assertEqual([(x["provider_from"], x["provider_to"]) for x in r.records], [("miro", "aws")])

    def test_bare_degraded_service_still_not_attributed(self):
        r = inc("Degraded service due to the Microsoft Outlook outage", "Notion Status", de.CLASS_STATUS_INCIDENT)
        self.assertEqual(r.records, [])

    def test_retrospective_rule_needs_the_own_feed(self):
        r = inc("Earlier disruptions were due to a significant Amazon Web Services outage.", "Some News")
        self.assertEqual(r.records, [])

    def test_named_party_in_title(self):
        r = inc("Canva Status: Canva is down due to Cloudflare outage (resolved).", "Canva Status", de.CLASS_STATUS_INCIDENT)
        self.assertEqual([(x["provider_from"], x["provider_to"]) for x in r.records], [("canva", "cloudflare")])

    def test_services_that_rely_on(self):
        r = inc("The outage impacted multiple services that rely on AWS including Slack, Atlassian, Snapchat, and others.")
        self.assertEqual({(x["provider_from"], x["provider_to"]) for x in r.records},
                         {("slack", "aws"), ("atlassian", "aws"), ("Snapchat", "aws")})

    def test_services_that_rely_on_needs_an_impact_verb(self):
        self.assertEqual(inc("Services that rely on AWS including Slack and Atlassian are common.").records, [])

    def test_hedged_rely_sentence_excluded(self):
        self.assertEqual(inc("The outage may have impacted services that rely on AWS including Slack.").records, [])

    def test_unnamed_providers_produce_no_record(self):
        rows = {json.loads(x)["event_id"]: json.loads(x) for x in (FIX / "incident_rows_20261124.jsonl").read_text().splitlines()}
        for eid, row in rows.items():
            if eid.startswith(("7d82213a", "931b9719", "67e2e043", "2b3003e8", "21b1a1ba")):
                res = de.extract_events([row], enabled=True)
                self.assertEqual(res.records, [], row["raw_title"])

    def test_cloudflare_post_mortem_names_no_provider(self):
        ex = json.loads((FIX / "source_excerpts_20261124.json").read_text())["cloudflare_june12_2025"]["text"]
        self.assertNotRegex(ex, r"Google|Amazon|Microsoft|Oracle")
        self.assertEqual(inc(ex, "Cloudflare Status", de.CLASS_STATUS_INCIDENT).records, [])

    def test_activities_column_is_a_purpose_column(self):
        md = "| Name | Activities |\n| --- | --- |\n| AWS | hosting |\n"
        res = de.extract_from_subprocessor_list(md, "Twilio", "https://v", "2026-11-24", enabled=True)
        self.assertEqual([(r["provider_to"], r["relation"]) for r in res.records], [("aws", de.REL_HOSTED_ON)])

    def test_parenthetical_entity_resolves(self):
        self.assertEqual(de.canonical("Amazon Web Services, Inc. (AWS Bedrock)")[0], "aws")
        self.assertEqual(de.canonical("Google LLC (Vertex AI)")[0], "google")

    def test_purpose_first_table_one_record_per_pair_and_skips_unknown(self):
        md = (
            "| Purpose of Processing | Sub-processors | Locations |\n| --- | --- | --- |\n"
            "| Hosting Provider for all functionality. | Amazon Web Services, Inc. | United States |\n"
            "| Hosting Provider for all functionality. | Amazon Web Services, Inc. | Australia |\n"
            "| Hosting Provider for all functionality | Heroku, Inc. (on Amazon Web Services, Inc.) | United States |\n"
            "| Provider of translation services | Google LLC | United States |\n"
        )
        res = de.extract_from_purpose_first_table(md, "Salesforce", "https://v", "2026-11-24", enabled=True)
        self.assertEqual({(r["provider_to"], r["relation"]) for r in res.records},
                         {("aws", de.REL_HOSTED_ON), ("google", de.REL_SUPPLIED_BY)})
        aws = next(r for r in res.records if r["provider_to"] == "aws")
        self.assertEqual(aws["occurrences"], 2)
        self.assertTrue(aws["australia_listed"])

    def test_purpose_first_prefers_the_all_functionality_row_as_span(self):
        md = (
            "| Purpose of Processing | Sub-processors | Locations |\n| --- | --- | --- |\n"
            "| Hosting Provider for Einstein Case Classification. | Amazon Web Services, Inc. | Australia |\n"
            "| Hosting Provider for all functionality. | Amazon Web Services, Inc. | United States |\n"
        )
        res = de.extract_from_purpose_first_table(md, "Salesforce", "https://v", "2026-11-24", enabled=True)
        self.assertEqual(len(res.records), 1)
        self.assertIn("all functionality", res.records[0]["evidence_span"])
        self.assertEqual(res.records[0]["occurrences"], 2)
        self.assertTrue(res.records[0]["australia_listed"])

    def test_purpose_first_off_by_default(self):
        os.environ.pop(de.ENV_FLAG, None)
        self.assertTrue(de.extract_from_purpose_first_table("", "Salesforce", "u", "t").disabled)


class TestHonestyOfCuratedRecords(unittest.TestCase):
    def test_optus_singtel_is_flagged_as_trigger_not_root_cause(self):
        r = next(x for x in ACQ["demonstrated"] if x["provider_to"] == "singtel")
        self.assertIn("root cause", r["causal_note"])
        self.assertEqual(r["source_class"], de.CLASS_REGULATOR_INCIDENT)

    def test_telstra_ecp_is_documented_group_not_demonstrated(self):
        r = next(x for x in ACQ["documented"] if x["provider_to"] == "telstra")
        self.assertEqual(r["dependent_kind"], "group_as_written")
        self.assertEqual(r["relation_basis"], D)
        self.assertFalse(any(x["provider_to"] == "telstra" for x in ACQ["demonstrated"]))

    def test_unnamed_context_never_becomes_a_record(self):
        self.assertEqual(len(ACQ["unnamed_context"]), 3)
        spans = {u["evidence_span"] for u in ACQ["unnamed_context"]}
        for r in ACQ["documented"] + ACQ["demonstrated"]:
            self.assertNotIn(r["evidence_span"], spans)

    def test_concentration_needs_verified_records(self):
        recs = ACQ["demonstrated"] + ACQ["documented"]
        res = de.concentration_eligibility(recs, "aws")
        self.assertFalse(res[M]["eligible"])  # nothing is reviewer-verified, so nothing is eligible
        self.assertEqual(res[M]["distinct_dependents"], 0)


class TestCascadeBeforeAfter(unittest.TestCase):
    def test_only_documented_changes_and_demonstrated_is_untouched(self):
        committed = json.loads((ANALYTICS / "fixtures" / "cascade" / "acquired_cascade_before_after.json").read_text())
        self.assertEqual(committed, json.loads(json.dumps(da.cascade_summary(ACQ), default=str)))
        b, a = committed["before"], committed["after"]
        self.assertEqual(b["demonstrated_statements_90d"], a["demonstrated_statements_90d"])
        self.assertEqual(b["recent_status_incidents"], a["recent_status_incidents"])
        self.assertEqual(b["documented_records"], 47)
        self.assertGreater(a["potential_exposure_links"], b["potential_exposure_links"])

    def test_acquired_documented_file_loads_as_documented_only(self):
        import cascading_exposure as ce

        path = ANALYTICS / "fixtures" / "cascade" / "acquired_dependency_records.json"
        recs = json.loads(path.read_text())["documented"]
        tmp = Path(os.environ.get("TMPDIR", "/tmp")) / "acq_doc_only_test.json"
        tmp.write_text(json.dumps({"records": recs}))
        try:
            self.assertEqual(len(ce.load_documented_records(tmp)), len(recs))
            tmp.write_text(json.dumps({"records": recs + ACQ["demonstrated"][:1]}))
            with self.assertRaises(ValueError):
                ce.load_documented_records(tmp)
        finally:
            tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
