"""Tests for tools/intelligence/analytics/cascading_exposure.py (offline, default OFF, unwired)."""

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANALYTICS = ROOT / "tools" / "intelligence" / "analytics"
sys.path.insert(0, str(ANALYTICS))

import cascading_exposure as ce
import dependency_evidence as de

AS_OF = datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc)
REAL = [
    json.loads(x)
    for x in (ANALYTICS / "fixtures" / "cascade" / "real_cases.jsonl")
    .read_text()
    .splitlines()
]
DOC = ce.load_documented_records()
SECTIONS = {
    "confirmed_evidence",
    "analytical_inference",
    "potential_exposure",
    "unknowns",
}


def iso(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S+00")


def status_feed(feed, per_week, weeks, start, tag="Incident", bulk_week=None):
    """Synthetic status feed: per_week[i] unplanned incidents in week i (Monday start)."""
    rows = []
    n = 0
    for i in range(weeks):
        for k in range(per_week[i]):
            pub = start + timedelta(days=7 * i, hours=3 + k % 100)
            n += 1
            col = pub + timedelta(minutes=30)
            rows.append(
                {
                    "event_id": f"{feed[:3]}-{n}",
                    "source_name": feed,
                    "published_at": iso(pub),
                    "collected_at": iso(col),
                    "canonical_url": f"https://status.example.com/incidents/{feed[:3].lower()}{n:06d}xyz",
                    "raw_title": f"{tag} {n}: elevated errors (investigating)",
                    "raw_summary": "Elevated error rates.",
                }
            )
    return rows


MONDAY = datetime(2026, 8, 31, tzinfo=timezone.utc)  # a Monday inside the 90-day window


class TestDefaultOff(unittest.TestCase):
    def test_off_without_flag(self):
        os.environ.pop(ce.ENV_FLAG, None)
        self.assertFalse(ce.is_enabled())
        self.assertIsNone(ce.build_product([], [], AS_OF, documented=[]))

    def test_env_flag_and_explicit(self):
        os.environ[ce.ENV_FLAG] = "1"
        try:
            self.assertTrue(ce.is_enabled())
            self.assertFalse(ce.is_enabled(False))
        finally:
            os.environ.pop(ce.ENV_FLAG)

    def test_not_registered_in_existing_products(self):
        import intel_products as ip

        self.assertNotIn(ce.PRODUCT_KEY, ip.PRODUCT_KEYS)
        self.assertNotIn(
            ce.PRODUCT_KEY, {p["product_key"] for p in ip.build_products([], [], AS_OF)}
        )


class TestDocumentedRecords(unittest.TestCase):
    def test_fixture_rebuild_matches_json_and_is_documented_only(self):
        rebuilt = ce.documented_records_from_fixtures()
        self.assertEqual(len(rebuilt), 47)
        self.assertEqual(rebuilt, DOC)
        self.assertTrue(all(r["relation_basis"] == de.BASIS_DOCUMENTED for r in DOC))

    def test_demonstrated_record_refused_as_documented(self):
        bad = dict(DOC[0], relation_basis=de.BASIS_DEMONSTRATED)
        with self.assertRaises(ValueError):
            ce.potential_exposure([], [bad])


class TestRealCases(unittest.TestCase):
    """Real past incidents from the 90-day production export (SELECT-only)."""

    def demo(self, as_of):
        return ce.extract_demonstrated(REAL, as_of)

    def test_notion_microsoft_outlook_is_demonstrated(self):
        recs, _ = self.demo(AS_OF)
        n = [r for r in recs if r["provider_from"] == "notion"]
        self.assertEqual(
            [(r["provider_to"], r["date"]) for r in n], [("microsoft", "2026-11-12")]
        )
        self.assertIn("due to the Microsoft Outlook outage", n[0]["evidence_span"])
        self.assertEqual(n[0]["relation_basis"], de.BASIS_DEMONSTRATED)

    def test_uk_banks_google_cloud_headline_is_demonstrated_as_group(self):
        recs, _ = self.demo(AS_OF)
        g = [r for r in recs if r["provider_to"] == "google"]
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["affected_kind"], "group_as_written")
        self.assertIn("Halifax and Revolut", g[0]["evidence_span"])

    def test_telstra_aws_is_co_reported_not_demonstrated(self):
        recs, _ = self.demo(AS_OF)
        self.assertFalse([r for r in recs if r["provider_from"] == "telstra"])
        co = ce.co_reported(REAL, AS_OF, recs)
        self.assertEqual(
            [(c["named_party"], c["outage_of"]) for c in co], [("telstra", "aws")]
        )

    def test_unnamed_upstream_is_coincidence_only(self):
        recs, ex = self.demo(AS_OF)
        self.assertFalse([r for r in recs if r["provider_from"] == "anthropic"])
        co = ce.temporal_coincidences(REAL, AS_OF, ex)
        self.assertTrue(co)
        self.assertTrue(all(c["provider"] == "microsoft" for c in co))

    def test_negated_headline_not_an_incident(self):
        news = ce.detect_news_incidents(
            REAL, datetime(2026, 11, 14, 12, tzinfo=timezone.utc), 3
        )
        self.assertNotIn(
            "7d6db127-28bd-4a65-a91d-8df8317b6061", {n["event_id"] for n in news}
        )

    def test_replay_microsoft_exposure_lists_documented_dependents_only(self):
        as_of = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
        prod = ce.build_product(
            REAL, REAL, as_of, documented=DOC, enabled=True, recent_days=3
        )
        exp = [e for e in prod["analysis"]["exposure"] if e["upstream"] == "microsoft"]
        self.assertEqual(
            [d["provider_from"] for d in exp[0]["dependents"]],
            ["anthropic", "openai", "zoom"],
        )
        text = "\n".join(prod["sections"]["potential_exposure"])
        self.assertIn(ce.POTENTIAL_LABEL, text)
        self.assertNotIn(
            "notion documents microsoft", text
        )  # Notion is demonstrated, not documented
        self.assertIn("REPLAY", text)


class TestSeparation(unittest.TestCase):
    def test_four_sections_and_scope_lines(self):
        prod = ce.build_product(REAL, REAL, AS_OF, documented=DOC, enabled=True)
        self.assertEqual(SECTIONS, set(prod["sections"]) & SECTIONS)
        for k in SECTIONS:
            self.assertTrue(prod["sections"][k][0].startswith("[Scope] MAY claim"), k)
            self.assertIn("MAY NOT", prod["sections"][k][0])
        self.assertEqual(prod["exceptions"], [])
        self.assertEqual(prod["product_key"], ce.PRODUCT_KEY)

    def test_documented_never_in_confirmed_and_demonstrated_never_in_exposure(self):
        prod = ce.build_product(REAL, REAL, AS_OF, documented=DOC, enabled=True)
        confirmed = "\n".join(prod["sections"]["confirmed_evidence"][1:])
        self.assertNotIn("vendor_subprocessor_list", confirmed)
        self.assertNotIn("documents", confirmed)
        for line in prod["sections"]["potential_exposure"][1:]:
            self.assertNotIn("[demonstrated", line)

    def test_provider_without_documents_lists_nothing(self):
        inc = [
            {
                "provider": "Akamai",
                "provider_id": "akamai",
                "first_pub": AS_OF,
                "event_id": "a",
                "title": "t",
                "url": None,
                "marked_resolved": False,
                "kind": "status_feed",
            }
        ]
        out, _ = ce.potential_exposure(inc, DOC)
        self.assertEqual(out[0]["dependents"], [])

    def test_purpose_hint_separates_support_from_service_path(self):
        by = {(r["provider_from"], r["provider_to"]): ce.purpose_hint(r) for r in DOC}
        self.assertEqual(by[("supabase", "vercel")], ce.PURPOSE_SERVICE_PATH)
        self.assertEqual(by[("supabase", "notion")], ce.PURPOSE_OTHER)


def demo_rec(frm, to, day, ev):
    return {
        "provider_from": frm,
        "provider_to": to,
        "relation_basis": de.BASIS_DEMONSTRATED,
        "observed_at": f"2026-11-{day:02d} 10:00:00+00",
        "event_id": ev,
    }


class TestEmergingPattern(unittest.TestCase):
    def test_two_downstreams_same_upstream_within_30d(self):
        recs = [
            demo_rec("notion", "microsoft", 5, "e1"),
            demo_rec("zoom", "microsoft", 12, "e2"),
        ]
        p = ce.emerging_pattern(recs, AS_OF)
        self.assertEqual(
            [(x["upstream"], x["statements"]) for x in p], [("microsoft", 2)]
        )

    def test_same_pair_within_episode_window_counts_once(self):
        recs = [
            demo_rec("notion", "microsoft", 5, "e1"),
            demo_rec("notion", "microsoft", 7, "e2"),
        ]
        self.assertEqual(ce.emerging_pattern(recs, AS_OF), [])

    def test_outside_30_days_does_not_count(self):
        old = demo_rec("zoom", "microsoft", 1, "e0")
        old["observed_at"] = "2026-09-01 10:00:00+00"
        self.assertEqual(
            ce.emerging_pattern(
                [old, demo_rec("notion", "microsoft", 12, "e2")], AS_OF
            ),
            [],
        )

    def test_documented_records_never_count(self):
        docs = [dict(r) for r in DOC if r["provider_to"] == "aws"]
        for r in docs:
            r["observed_at"] = "2026-11-20"
        self.assertEqual(ce.emerging_pattern(docs, AS_OF), [])

    def test_real_data_has_no_pattern(self):
        recs, _ = ce.extract_demonstrated(REAL, AS_OF)
        self.assertEqual(ce.emerging_pattern(recs, AS_OF), [])


class TestReliability(unittest.TestCase):
    start = MONDAY

    def read(self, per_week, extra=()):
        rows = status_feed("Eps Status", per_week, len(per_week), self.start) + list(
            extra
        )
        as_of = self.start + timedelta(days=7 * len(per_week))
        reads, insuff = ce.weekly_reliability_reads(rows, as_of)
        return reads, insuff

    def test_higher_rate_labelled(self):
        reads, _ = self.read([2] * 8 + [6] * 4 + [0])
        self.assertEqual(len(reads), 1)
        self.assertEqual(reads[0]["label"], "reported rate higher")

    def test_stable_rate_not_flagged(self):
        reads, _ = self.read([3] * 13)
        self.assertEqual(reads[0]["label"], "reported rate about the same")

    def test_insufficient_feed_is_not_scored(self):
        rows = status_feed("Tiny Status", [1, 1, 1], 3, self.start)
        reads, insuff = ce.weekly_reliability_reads(
            rows, self.start + timedelta(days=84)
        )
        self.assertEqual(reads, [])
        self.assertEqual(insuff[0]["feed"], "Tiny Status")
        self.assertTrue(insuff[0]["reasons"])

    def test_bulk_ingest_week_is_confounded_and_excluded(self):
        per = [3] * 13
        rows = status_feed("Eps Status", per, 13, self.start)
        # a bulk re-ingest of 10 old incidents published in week 4, collected in one minute 60 days later
        bulk_pub = self.start + timedelta(days=28, hours=1)
        for k in range(10):
            rows.append(
                {
                    "event_id": f"bulk-{k}",
                    "source_name": "Eps Status",
                    "published_at": iso(bulk_pub + timedelta(minutes=k)),
                    "collected_at": iso(self.start + timedelta(days=80, minutes=1)),
                    "canonical_url": f"https://status.example.com/incidents/bulk{k:04d}abc",
                    "raw_title": f"Old {k}: errors (resolved)",
                    "raw_summary": "Errors.",
                }
            )
        reads, insuff = ce.weekly_reliability_reads(
            rows, self.start + timedelta(days=91)
        )
        got = reads[0] if reads else None
        if (
            got is None
        ):  # share of bulk rows may push the feed under threshold (c); then it must be listed, not scored
            self.assertTrue(any("bulk" in x for x in insuff[0]["reasons"]))
        else:
            self.assertTrue(
                any(
                    "bulk" in s["confounded"][0]
                    for s in got["series"]
                    if s["confounded"]
                )
            )

    def test_listing_is_alphabetical_never_ranked(self):
        rows = status_feed("Zed Status", [4] * 13, 13, self.start) + status_feed(
            "Abc Status", [9] * 13, 13, self.start
        )
        reads, _ = ce.weekly_reliability_reads(rows, self.start + timedelta(days=91))
        self.assertEqual([r["feed"] for r in reads], ["Abc Status", "Zed Status"])


class TestIncidentDetection(unittest.TestCase):
    def test_status_incident_recent_window_and_provider_id(self):
        rows = [
            {
                "event_id": "c1",
                "source_name": "Cloudflare Status",
                "published_at": iso(AS_OF - timedelta(hours=5)),
                "collected_at": iso(AS_OF - timedelta(hours=4)),
                "canonical_url": "https://www.cloudflarestatus.com/incidents/abcdef123456",
                "raw_title": "Cloudflare Status: Elevated errors (investigating)",
                "raw_summary": "Elevated errors.",
            },
            {
                "event_id": "c0",
                "source_name": "Cloudflare Status",
                "published_at": iso(AS_OF - timedelta(days=20)),
                "collected_at": iso(AS_OF - timedelta(days=20)),
                "canonical_url": "https://www.cloudflarestatus.com/incidents/old000000001",
                "raw_title": "Cloudflare Status: Old (resolved)",
                "raw_summary": "Old.",
            },
        ]
        inc, late = ce.detect_status_incidents(rows, AS_OF, 7)
        self.assertEqual(
            [(i["event_id"], i["provider_id"]) for i in inc], [("c1", "cloudflare")]
        )
        self.assertFalse(late)

    def test_late_collected_incident_not_live(self):
        rows = [
            {
                "event_id": "l1",
                "source_name": "Cloudflare Status",
                "published_at": iso(AS_OF - timedelta(days=3)),
                "collected_at": iso(AS_OF),
                "canonical_url": "https://www.cloudflarestatus.com/incidents/late00000001",
                "raw_title": "Cloudflare Status: Late (investigating)",
                "raw_summary": "Late.",
            }
        ]
        inc, late = ce.detect_status_incidents(rows, AS_OF, 7)
        self.assertEqual((inc, len(late)), ([], 1))


if __name__ == "__main__":
    unittest.main()
