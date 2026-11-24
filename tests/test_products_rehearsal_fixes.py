"""Regression tests for defects found by the 2026-11-24 products rehearsal on production data (all default OFF paths)."""

import sys
import unittest
import urllib.parse
from datetime import date, timedelta
from pathlib import Path
from typing import ClassVar
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools" / "intelligence" / "analytics"))

import forward_watch as fw
import intel_products as ip
import provider_disruption_report as pdr
from test_systemic_intel_products import AS_OF, frow, status_rows

from intelligence import brief_products_block as bpb
from intelligence import intel_products_job as job


class TestNullPublishedRows(unittest.TestCase):
    def test_fetch_asks_for_undated_rows_by_collected_at(self):
        seen = []

        def getter(table, query):
            seen.append((table, query))
            return [{"source_id": 1, "source_name": "x"}] if table == "intelligence_source_registry" else []

        job.fetch_rows(AS_OF - timedelta(days=90), getter)
        q = urllib.parse.unquote(seen[-1][1])
        self.assertIn("published_at.is.null", q)
        self.assertIn("collected_at.gte.", q)
        self.assertIn("event_id.asc", q)  # stable paging when many rows share a null published_at

    def test_undated_completion_notice_retires_the_planned_item(self):
        planned = frow("p1", "AEMO Market Notices", "Initial - CHG1 - Planned maintenance affecting the AEMO Market Network.", "", day=2)
        done = frow("p2", "AEMO Market Notices", "Completed - CHG1 - Planned maintenance affecting the AEMO Market Network.", "", day=3)
        planned["canonical_url"] = "https://nemweb.example/Market_Notice/NEMITWEB1_MKTNOTICE_20261102.R144962"
        done["canonical_url"] = "https://nemweb.example/Market_Notice/NEMITWEB1_MKTNOTICE_20261111.R145121"
        done["published_at"] = None  # the feed gives no publication date; collected later
        done["collected_at"] = "2026-11-03 02:00:00+00"
        items, undated, _ = fw.extract_items([planned, done], AS_OF)
        self.assertEqual(undated, [])
        self.assertEqual(items, [])
        items, undated, _ = fw.extract_items([planned], AS_OF)
        self.assertEqual(len(undated), 1)  # without the completion row the item is still listed

    def test_feed_with_only_undated_rows_is_named_not_dropped(self):
        rows = status_rows("Eps Status", 12, 2.4, start=AS_OF - timedelta(days=29))
        fastly = [
            {"event_id": f"f{i}", "source_name": "Fastly Status", "published_at": None,
             "collected_at": "2026-11-20 01:00:00+00", "canonical_url": None, "raw_title": "x", "raw_summary": ""}
            for i in range(3)
        ]
        self.assertEqual(pdr.undated_feeds(rows + fastly), {"Fastly Status": 3})
        prod = ip.recurring_provider_product(rows + fastly, AS_OF, "t")
        self.assertTrue(any("Fastly Status: 3 status rows carry no publication date" in u for u in prod["sections"]["unknowns"]))
        self.assertIn("Fastly Status: 3 undated rows", prod["body_md"])
        self.assertIn("only undated rows", prod["sections"]["coverage_note"])
        clean = ip.recurring_provider_product(rows, AS_OF, "t")
        self.assertNotIn("undated", clean["body_md"].lower())


class TestDatedEventsInProduct(unittest.TestCase):
    ROWS: ClassVar[list] = [
        frow("r1", "Cisco Security Advisories", "Advance notice", "The next planned publication of advisories will be 28 November 2026. Customers should prepare.", day=20),
        frow("m1", "Twilio Status", "UK carrier maintenance", "THIS IS A SCHEDULED EVENT planned maintenance from 24 November 2026 at 08:00 PST until 25 November 2026 at 01:00 PST", day=20),
    ]

    def test_default_off_output_unchanged(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            p = ip.forward_watch_product(self.ROWS, AS_OF, "t")
        self.assertNotIn("Dated events (extractor", p["body_md"])

    def test_flag_adds_dated_events_without_duplicating_listed_windows(self):
        with mock.patch.dict("os.environ", {"INTEL_DATED_EVENTS_ENABLED": "1"}):
            p = ip.forward_watch_product(self.ROWS, AS_OF, "t")
        self.assertIn("Dated events (extractor", p["body_md"])
        ids = [l for l in p["sections"]["confirmed_evidence"] if "(m1)" in l]
        self.assertLessEqual(len(ids), 1)  # the maintenance window is one event, listed once
        self.assertEqual(sum(1 for l in p["body_md"].splitlines() if "`m1`" in l), 1)


class TestBriefBlockRobustness(unittest.TestCase):
    def rec(self, key, finding, note, gen="2026-11-20"):
        return {"product_key": key, "generated_for": gen, "sections": {"brief_findings": [finding], "coverage_note": note}, "exceptions": []}

    def setUp(self):
        p = mock.patch.dict("os.environ", {"INTEL_PRODUCTS_IN_BRIEF": "1"})
        p.start()
        self.addCleanup(p.stop)

    def test_row_without_product_key_does_not_blank_the_block(self):
        rows = [{"generated_for": "2026-11-20"}, self.rec("recurring_provider", "A higher", "note A")]
        lines = bpb.brief_lines(date(2026, 11, 21), reader=lambda: rows)
        self.assertIn("- Recurring provider: A higher", lines)

    def test_each_contributing_product_keeps_its_own_coverage_caveat(self):
        rows = [self.rec("forward_watch", "W due", "note W"), self.rec("recurring_provider", "R higher", "note R")]
        lines = bpb.brief_lines(date(2026, 11, 21), reader=lambda: rows)
        cov = [l for l in lines if l.startswith("Coverage:")]
        self.assertEqual(len(cov), 1)
        self.assertIn("note W", cov[0])
        self.assertIn("note R", cov[0])

    def test_missing_or_stale_product_degrades_to_nothing(self):
        self.assertEqual(bpb.brief_lines(date(2026, 11, 21), reader=list), [])
        stale = [self.rec("forward_watch", "W due", "n", gen="2026-11-01")]
        self.assertEqual(bpb.brief_lines(date(2026, 11, 21), reader=lambda: stale), [])


if __name__ == "__main__":
    unittest.main()
