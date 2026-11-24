"""Tests for the non-production analytics prototypes in tools/intelligence/analytics/.

All offline: synthetic rows plus the committed hand-checked sample. No network, no database.
"""

import json
import os
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ANALYTICS = Path(__file__).resolve().parent.parent / "tools" / "intelligence" / "analytics"
sys.path.insert(0, str(ANALYTICS))

import analytics_common as ac
import patching_velocity as pv
import provider_failure as pf
import provider_tagging as pt

AS_OF = datetime(2026, 11, 24, 0, 40, tzinfo=timezone.utc)


def row(eid, src, title, summary="", url=None, pub="2026-11-10 10:00:00+00", col=None):
    return {"event_id": eid, "source_name": src, "raw_title": title, "raw_summary": summary,
            "canonical_url": url, "published_at": pub, "collected_at": col or pub}


class TestCommon(unittest.TestCase):
    def test_parse_ts_variants(self):
        self.assertEqual(ac.parse_ts("2026-11-10 10:00:00+00").hour, 10)
        self.assertEqual(ac.parse_ts("2026-11-10T10:00:00Z").tzinfo, timezone.utc)
        self.assertIsNone(ac.parse_ts(None))
        self.assertIsNone(ac.parse_ts("not a date"))

    def test_windows_are_30_and_60_days(self):
        recent, prior = ac.windows(AS_OF)
        self.assertEqual((recent[1] - recent[0]).days, 30)
        self.assertEqual((prior[1] - prior[0]).days, 60)
        self.assertEqual(prior[1], recent[0])

    def test_labels_defined(self):
        for label in ("OBSERVED FACT", "PLAUSIBLE RELATIONSHIP", "UNVERIFIED HYPOTHESIS"):
            self.assertIn(label, ac.LABEL_LEGEND)


class TestIncidentIdentity(unittest.TestCase):
    def test_stspg_link_merges_with_full_incident_url(self):
        rows = [
            row("1", "GitHub Status", "GitHub Status: Incident with Actions (investigating)",
                url="https://stspg.io/abc123def456"),
            row("2", "GitHub Status", "GitHub Status: Incident with Actions (resolved)",
                url="https://www.githubstatus.com/incidents/zzzz1111aaaa"),
        ]
        incs = pf.build_incidents(rows)
        self.assertEqual(len(incs), 1)
        self.assertEqual(incs[0]["n_entries"], 2)
        self.assertTrue(incs[0]["resolved"])

    def test_unmatched_stspg_stays_its_own_incident(self):
        rows = [row("1", "X Status", "X Status: Thing (investigating)", url="https://stspg.io/abc123def456"),
                row("2", "X Status", "X Status: Other (resolved)", url="https://x.example/incidents/qqqq1111aaaa",
                    pub="2026-11-11 10:00:00+00")]
        self.assertEqual(len(pf.build_incidents(rows)), 2)

    def test_url_less_rows_merge_by_stem_and_day(self):
        rows = [row("1", "Akamai Status", "Bot Manager issues (investigating)"),
                row("2", "Akamai Status", "Bot Manager issues (resolved)", pub="2026-11-10 14:00:00+00")]
        self.assertEqual(len(pf.build_incidents(rows)), 1)

    def test_same_id_repeated_counts_once(self):
        rows = [row("1", "Y Status", "Y: a", url="https://y.example/incidents/idid11112222"),
                row("2", "Y Status", "Y: a", url="https://y.example/incidents/idid11112222")]
        incs = pf.build_incidents(rows)
        self.assertEqual((len(incs), incs[0]["n_entries"]), (1, 2))

    def test_id_extraction(self):
        self.assertEqual(pf.url_incident_id("https://status.x.com/incidents/abcdef123456"), ("id", "abcdef123456"))
        self.assertEqual(pf.url_incident_id("https://www.fastlystatus.com/incident/378710"), ("id", "378710"))
        self.assertEqual(pf.url_incident_id("https://stspg.io/xyz789"), ("stspg", "xyz789"))
        self.assertIsNone(pf.url_incident_id("https://www.fastlystatus.com/incidents"))
        self.assertIsNone(pf.url_incident_id(None))


class TestClassification(unittest.TestCase):
    def test_scheduled_vs_unplanned(self):
        self.assertEqual(pf.classify_schedule("SMS Carrier Partner Maintenance", "THIS IS A SCHEDULED EVENT Oct 26"), "scheduled")
        self.assertEqual(pf.classify_schedule("Elevated errors", "We are investigating"), "unplanned")
        self.assertEqual(pf.classify_schedule("Emergency maintenance", "unplanned maintenance"), "unplanned")

    def test_severity_and_services(self):
        s = "[Impact: major] Affected: Actions, Pull Requests. We are investigating."
        self.assertEqual(pf.parse_severity("t", s), "major")
        self.assertEqual(pf.parse_services(s), ["Actions", "Pull Requests"])
        self.assertIsNone(pf.parse_severity("Hello", "nothing here"))

    def test_au_relevance_levels(self):
        self.assertEqual(pf.au_relevance("Errors in Sydney", ""), "strong")
        self.assertEqual(pf.au_relevance("t", "region ap-southeast-2 degraded"), "strong")
        self.assertEqual(pf.au_relevance("Incident in APAC", ""), "weak")
        self.assertEqual(pf.au_relevance("Errors in Frankfurt", ""), "none")

    def test_stated_duration(self):
        self.assertEqual(pf.stated_duration_minutes("Between 19:05 and 21:27 UTC on November 13"), (142, "stated_window"))
        self.assertEqual(pf.stated_duration_minutes("from 23:30 to 00:20 UTC"), (50, "stated_window"))
        self.assertEqual(pf.stated_duration_minutes("Start: 2026-08-27 05:30 UTC End: 2026-08-27 08:30 UTC"),
                         (180, "scheduled_window"))
        self.assertEqual(pf.stated_duration_minutes("no times"), (None, None))

    def test_resolved_markers(self):
        self.assertTrue(pf.RESOLVED_MARKERS.search("Title (resolved)"))
        self.assertTrue(pf.RESOLVED_MARKERS.search("Status: Resolved We fixed it"))
        self.assertFalse(pf.RESOLVED_MARKERS.search("We are investigating"))

    def test_provider_of(self):
        self.assertEqual(pf.provider_of("GitHub Status"), "GitHub")
        self.assertEqual(pf.provider_of("Salesforce Trust Status"), "Salesforce")
        self.assertEqual(pf.provider_of("Anthropic (Claude) Status"), "Anthropic")


class TestCollectionConsistency(unittest.TestCase):
    def _backfilled_provider(self):
        rows = []
        # prior window: 8 old incidents all ingested in one bulk batch (backfill) on 2026-11-01
        for i in range(8):
            rows.append(row(f"b{i}", "Demo Status", f"Demo Status: old {i} (resolved)",
                            url=f"https://d.example/incidents/old{i:08d}",
                            pub=f"2026-10-{6 + i:02d} 10:00:00+00", col="2026-11-01 20:49:00+00"))
        # recent window: 6 contemporaneous incidents
        for i in range(6):
            rows.append(row(f"r{i}", "Demo Status", f"Demo Status: new {i} (resolved)",
                            url=f"https://d.example/incidents/new{i:08d}",
                            pub=f"2026-11-{10 + i:02d} 10:00:00+00", col=f"2026-11-{10 + i:02d} 10:30:00+00"))
        return rows

    def test_backfill_batch_detected(self):
        batches = pf.detect_backfill_batches(self._backfilled_provider())
        self.assertEqual(len(batches), 1)
        (src, minute), info = next(iter(batches.items()))
        self.assertEqual((src, minute), ("Demo Status", "2026-11-01T20:49"))
        self.assertEqual(info["rows"], 8)

    def test_contemporaneous_vs_backfilled_counts(self):
        rows = self._backfilled_provider()
        res = pf.analyse(rows, AS_OF)
        c = res["comparison"]["Demo Status"]
        self.assertEqual(c["recent"]["distinct_incidents"], 6)
        self.assertEqual(c["prior"]["distinct_incidents"], 8)
        self.assertEqual(c["prior"]["distinct_incidents_collected_contemporaneously"], 0)
        self.assertEqual(c["recent"]["entries_in_backfill_batches_collected_basis"], 8)

    def test_entry_vs_incident_bases_differ_under_backfill(self):
        res = pf.analyse(self._backfilled_provider(), AS_OF)
        c = res["comparison"]["Demo Status"]
        # collected basis puts the 8 backfilled rows in the RECENT window, inflating it
        self.assertEqual(c["recent"]["entries_collected_basis"], 14)
        self.assertEqual(c["recent"]["entries_published_basis"], 6)

    def test_publication_gap_marks_unevidenced_days(self):
        rows = []
        for i in range(12):
            rows.append(row(f"g{i}", "Gap Status", f"Gap Status: a{i} (resolved)",
                            url=f"https://g.example/incidents/ggg{i:09d}",
                            pub=f"2026-09-{1 + i:02d} 10:00:00+00"))
        for i in range(12):
            rows.append(row(f"h{i}", "Gap Status", f"Gap Status: b{i} (resolved)",
                            url=f"https://g.example/incidents/hhh{i:09d}",
                            pub=f"2026-11-{1 + i:02d} 10:00:00+00"))
        incs = pf.build_incidents(rows)
        gaps = pf.publication_gaps(incs, AS_OF)
        self.assertTrue(any((b - a).days > 40 for a, b in gaps))

    def test_verdict_uses_labels_and_flags_artefact(self):
        res = pf.analyse(self._backfilled_provider(), AS_OF)
        text = "\n".join(pf.focus_verdict("Demo Status", res["comparison"], res["flags"]))
        self.assertIn("[OBSERVED FACT]", text)
        self.assertIn("[PLAUSIBLE RELATIONSHIP]", text)
        self.assertIn("[UNVERIFIED HYPOTHESIS]", text)
        self.assertIn("collection artefact", text)

    def test_markdown_report_carries_labels_and_scope(self):
        res = pf.analyse(self._backfilled_provider(), AS_OF)
        md = pf.render_markdown(res, AS_OF, focus="Demo Status")
        for label in ("OBSERVED FACT", "PLAUSIBLE RELATIONSHIP", "UNVERIFIED HYPOTHESIS", "DISTINCT INCIDENT"):
            self.assertIn(label, md)
        self.assertIn("What this adds beyond the intelligence brief", md)

    def test_non_status_sources_excluded(self):
        res = pf.analyse([row("1", "Bloomberg", "Markets"), row("2", "X Status", "X: t", url="https://x/incidents/aaaaaaaaaaaa")], AS_OF)
        self.assertNotIn("Bloomberg", res["comparison"])


class TestPatchingVelocity(unittest.TestCase):
    def test_cve_regex(self):
        self.assertEqual(pv.cves_in("CVE-2026-0310 and CVE-2024-123456 plus cve-2020-1"), {"CVE-2026-0310", "CVE-2024-123456"})

    def test_disclosure_to_kev_negative_interval_reported_as_is(self):
        rows = [
            {"source_name": pv.NVD_SRC, "published_at": "2026-11-01 00:00:00+00", "raw_title": "CVE-2026-1111",
             "affected_cves": ["CVE-2026-1111"]},
            {"source_name": pv.KEV_SRC, "published_at": "2026-10-27 00:00:00+00", "raw_title": "CVE-2026-1111: Vendor Thing"},
            {"source_name": pv.KEV_SRC, "published_at": "2026-10-28 00:00:00+00", "raw_title": "CVE-2020-2222: Old"},
        ]
        res = pv.disclosure_to_kev(rows)
        self.assertEqual(len(res["pairs"]), 1)
        self.assertEqual(res["pairs"][0]["days"], -5)
        self.assertEqual(res["n_kev_cves"], 2)

    def test_first_advisory_to_kev_groups_and_signs(self):
        kev = {"CVE-2026-1001": datetime(2026, 8, 18, tzinfo=timezone.utc)}
        rows = [
            {"source_name": "Cisco Security Advisories", "published_at": "2026-08-10 00:00:00+00",
             "raw_title": "CVE-2026-1001 thing", "raw_summary": "", "canonical_url": ""},
            {"source_name": "CISA Alerts", "published_at": "2026-08-18 00:00:00+00",
             "raw_title": "Adds", "raw_summary": "CVE-2026-1001", "canonical_url": ""},
            {"source_name": "Bloomberg", "published_at": "2026-08-01 00:00:00+00",
             "raw_title": "CVE-2026-1001", "raw_summary": "", "canonical_url": ""},
        ]
        summary, _ = pv.first_advisory_to_kev(rows, kev)
        self.assertEqual(summary["vendor_advisory"]["median_days"], -8)
        self.assertEqual(summary["mirror"]["same_day_share"], 1.0)
        self.assertEqual(set(summary), {"vendor_advisory", "mirror"})  # unrelated sources ignored

    def test_kev_due_dates_absent_is_reported_not_invented(self):
        rows = [{"source_name": pv.KEV_SRC, "published_at": "2026-08-04 00:00:00+00", "raw_title": "CVE-2026-9: X",
                 "raw_summary": "allows attackers to run code due to improper handling"}]
        out = pv.kev_due_dates(rows)
        self.assertEqual(out["rows_with_due_date_text"], 0)
        self.assertNotIn("hypothetical_deadlines", out)

    def test_kev_due_date_parsed_when_present_and_assumption_marked(self):
        rows = [{"source_name": pv.KEV_SRC, "published_at": "2026-08-04 00:00:00+00", "raw_title": "CVE-2026-9: X",
                 "raw_summary": "Required action due date: 2026-08-25."}]
        self.assertEqual(pv.kev_due_dates(rows)["rows_with_due_date_text"], 1)
        out = pv.kev_due_dates(rows, assume_days=21)
        self.assertEqual(out["hypothetical_deadlines"][0]["hypothetical_due"], "2026-08-25")

    def test_change_markers_ignore_status_update_words(self):
        self.assertIsNone(pv.CHANGE_MARKERS.search("Update - we will provide an update soon"))
        self.assertTrue(pv.CHANGE_MARKERS.search("caused by a configuration change deployed earlier"))
        self.assertTrue(pv.CHANGE_MARKERS.search("rolled back the release"))

    def test_change_related_counts_only_unplanned(self):
        rows = [
            row("1", "A Status", "A Status: Errors (resolved)", "Caused by a deployment.", url="https://a/incidents/aaaaaaaaaaaa"),
            row("2", "A Status", "A Status: Errors2 (resolved)", "Network issue.", url="https://a/incidents/bbbbbbbbbbbb"),
            row("3", "A Status", "Planned maintenance", "THIS IS A SCHEDULED EVENT deployment", url="https://a/incidents/cccccccccccc"),
        ]
        per, _ = pv.change_related_incidents(rows)
        self.assertEqual((per["A Status"]["unplanned"], per["A Status"]["unplanned_change_named"], per["A Status"]["scheduled"]), (2, 1, 1))

    def test_coincidence_reports_baseline_and_skips_thin_data(self):
        rows = []
        for i in range(6):
            rows.append(row(f"s{i}", "B Status", f"B Status: Maintenance {i}", "THIS IS A SCHEDULED EVENT",
                            url=f"https://b/incidents/s{i:011d}", pub=f"2026-10-{1 + 4 * i:02d} 08:00:00+00"))
            rows.append(row(f"u{i}", "B Status", f"B Status: Errors {i} (resolved)", "Errors.",
                            url=f"https://b/incidents/u{i:011d}", pub=f"2026-10-{1 + 4 * i:02d} 20:00:00+00"))
        _, incs = pv.change_related_incidents(rows)
        res = pv.coincidence_after_scheduled(incs)
        self.assertEqual(res["B Status"]["observed_followers"], 6)
        self.assertIn("baseline_mean", res["B Status"])
        self.assertEqual(pv.coincidence_after_scheduled(incs[:3]), {})

    def test_report_labels_and_not_computable_statements(self):
        rows = [
            {"source_name": pv.KEV_SRC, "published_at": "2026-08-04 00:00:00+00", "raw_title": "CVE-2026-9: X", "raw_summary": ""},
        ]
        md = pv.render_markdown(pv.analyse(rows, AS_OF))
        for label in ("OBSERVED FACT", "PLAUSIBLE RELATIONSHIP", "UNVERIFIED HYPOTHESIS"):
            self.assertIn(label, md)
        self.assertIn("NOT computable", md)
        self.assertIn("What this adds beyond the intelligence brief", md)


class TestProviderMapFiles(unittest.TestCase):
    def setUp(self):
        self.pmap = pt.load_map()
        self.deps = pt.load_dependencies()

    def test_all_patterns_compile_and_ids_unique(self):
        for spec in self.pmap["providers"].values():
            for rx in spec.get("patterns", []) + spec.get("exclude_patterns", []):
                re.compile(rx, re.IGNORECASE)
            self.assertTrue(spec["family"])
            self.assertTrue(spec["layer"])

    def test_dependency_ids_exist_in_map(self):
        for pid in self.deps["entries"]:
            self.assertIn(pid, self.pmap["providers"])

    def test_org_links_never_sector_assumption(self):
        for e in self.deps["entries"].values():
            for link in e["org_links"]:
                self.assertIn(link["evidence_class"], ("publicly_evidenced", "unverified"))
                self.assertTrue(link.get("scope_note"))

    def test_layer_hypotheses_cover_map_layers_used_by_deps(self):
        for pid in self.deps["entries"]:
            self.assertIn(self.pmap["providers"][pid]["layer"], self.deps["layer_cascade_hypotheses"])

    def test_no_duplicate_json_keys(self):
        def no_dupes(pairs):
            keys = [k for k, _ in pairs]
            self.assertEqual(len(keys), len(set(keys)))
            return dict(pairs)
        for name in ("provider_map.json", "dependency_extract.json"):
            json.loads((ANALYTICS / name).read_text(encoding="utf-8"), object_pairs_hook=no_dupes)


class TestTagger(unittest.TestCase):
    def setUp(self):
        self.t = pt.Tagger()

    def test_source_tag(self):
        tags = self.t.tag(row("1", "Cloudflare Status", "Cloudflare Status: x"))
        self.assertEqual(tags[0]["provider"], "cloudflare")
        self.assertEqual(tags[0]["method"], "source")

    def test_title_beats_text(self):
        tags = self.t.tag(row("1", "iTnews", "Cisco flaw exploited", "Cisco says"))
        self.assertEqual([x["method"] for x in tags if x["provider"] == "cisco"], ["title"])

    def test_text_only_match(self):
        tags = self.t.tag(row("1", "BBC News", "AI chat", "Anthropic cofounder said"))
        self.assertEqual(tags[0]["method"], "text")

    def test_word_boundaries(self):
        self.assertEqual(self.t.tag(row("1", "BBC News", "Notionally speaking", "AWSome stuff")), [])

    def test_search_term_feed_not_counted_until_confirmed(self):
        r = row("1", "Google News - Telstra", "Local footy results", "")
        tags = self.t.tag(r)
        self.assertEqual([x["method"] for x in tags], ["source_query"])
        self.assertEqual(pt.confirmed(tags), [])

    def test_family_rollup_changes_ranking(self):
        vis = {pid: {"own_feed_incidents_or_items": 0, "external_mentions": 0} for pid in self.t.providers}
        vis["github"]["own_feed_incidents_or_items"] = 10
        vis["microsoft_azure"]["own_feed_incidents_or_items"] = 5
        fam = pt.family_rollup(vis, self.t)
        self.assertEqual(fam["Microsoft"]["own_feed_incidents_or_items"], 15)

    def test_concentration_not_computable_with_thin_evidence(self):
        conc, n = pt.concentration_from_evidence(pt.load_dependencies())
        self.assertEqual(conc, {})
        self.assertEqual(n, 2)

    def test_concentration_computed_only_when_two_orgs_evidenced(self):
        deps = {"entries": {"x": {"sector_exposure": [], "org_links": [
            {"org": "A", "evidence_class": "publicly_evidenced"}, {"org": "B", "evidence_class": "publicly_evidenced"},
            {"org": "C", "evidence_class": "unverified"}]}}}
        conc, n = pt.concentration_from_evidence(deps)
        self.assertEqual(conc, {"x": ["A", "B"]})
        self.assertEqual(n, 2)

    def test_visibility_dedupes_status_updates(self):
        rows = [row("1", "GitHub Status", "GitHub Status: Incident (investigating)", url="https://stspg.io/aaaaaaaaaaaa"),
                row("2", "GitHub Status", "GitHub Status: Incident (resolved)", url="https://www.githubstatus.com/incidents/bbbbbbbbbbbb")]
        vis = pt.visibility(rows, self.t)
        self.assertEqual(vis["github"]["own_feed_incidents_or_items"], 1)

    def test_divergence_example_visibility_not_evidence(self):
        vis = {pid: {"own_feed_incidents_or_items": 0, "external_mentions": 0} for pid in self.t.providers}
        vis["twilio"]["own_feed_incidents_or_items"] = 250
        div = {r["provider"]: r for r in pt.divergence(vis, pt.load_dependencies())}
        self.assertEqual(div["twilio"]["evidenced_org_links"], 0)
        self.assertEqual(div["nokia"]["evidenced_org_links"], 1)
        self.assertGreater(div["twilio"]["visibility"], div["nokia"]["visibility"])


class TestHandCheckedSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = json.loads((ANALYTICS / "fixtures" / "hand_checked_sample.json").read_text(encoding="utf-8"))
        cls.ev = pt.evaluate_full(cls.sample, pt.Tagger())

    def test_sample_is_large_enough(self):
        self.assertGreaterEqual(self.ev["n_events"], 60)

    def test_mention_precision_is_high_and_involved_precision_is_low(self):
        self.assertGreaterEqual(self.ev["mention_title_text"]["precision"], 0.85)
        self.assertLess(self.ev["involved_title_text"]["precision"], 0.5)

    def test_known_misses_are_recorded(self):
        kinds = {(e[0], e[2]) for e in self.ev["errors"]}
        self.assertIn(("FN", "microsoft_365"), kinds)
        self.assertIn(("FP", "telstra"), kinds)

    def test_report_renders_all_five_concepts(self):
        rows = self.sample["rows"]
        md = pt.render_markdown(rows, pt.Tagger(), pt.load_dependencies(), self.ev)
        for heading in ("(a) Provider VISIBILITY", "(b) Evidenced service dependencies", "(c) Sector-level exposure",
                        "(d) Actual concentration risk", "(e) Potential cascading consequences"):
            self.assertIn(heading, md)
        for label in ("OBSERVED FACT", "PLAUSIBLE RELATIONSHIP", "UNVERIFIED HYPOTHESIS"):
            self.assertIn(label, md)
        self.assertIn("NOT computable", md)


class TestNoProductionSideEffects(unittest.TestCase):
    def test_modules_do_not_import_network_or_db_clients(self):
        for name in ("analytics_common.py", "provider_failure.py", "patching_velocity.py", "provider_tagging.py"):
            src = (ANALYTICS / name).read_text(encoding="utf-8")
            for banned in ("import requests", "import urllib", "import socket", "import psycopg", "supabase", "import subprocess"):
                self.assertNotIn(banned, src, f"{name} contains {banned}")


if __name__ == "__main__":
    unittest.main()
    os._exit(0)
