"""Tests for the offline forward watch generator (default OFF). Vendored from the products branch."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ANALYTICS = (
    Path(__file__).resolve().parent.parent / "tools" / "intelligence" / "analytics"
)
sys.path.insert(0, str(ANALYTICS))

import forward_watch as fw

AS_OF = datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S+00")


def frow(eid, source, title, summary, day=20):
    pub = datetime(2026, 11, day, 1, 0, tzinfo=timezone.utc)
    return {
        "event_id": eid,
        "source_name": source,
        "published_at": iso(pub),
        "collected_at": iso(pub),
        "canonical_url": f"https://x.example/{eid}",
        "raw_title": title,
        "raw_summary": summary,
    }


class TestForwardWatch(unittest.TestCase):
    def run_watch(self, rows, horizon=42):
        return fw.extract_items(rows, AS_OF, horizon)

    def test_supabase_scheduled_window(self):
        rows = [
            frow(
                "s1",
                "Supabase Status",
                "Maintenance: Scheduled maintenance: Shared Pooler (Supavisor), eu-west-2",
                "Status: Scheduled (Wed, 09 Dec 2026 13:00:00 GMT - Wed, 09 Dec 2026 15:00:00 GMT) We will perform scheduled maintenance.",
            )
        ]
        items, _, _ = self.run_watch(rows)
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it["date"].isoformat(), "2026-12-09")
        self.assertEqual(it["label"], "SCHEDULED_BY_OWNER")
        self.assertEqual(it["tier"], "PRIMARY_PROVIDER")
        self.assertIn("13:00", it["when"])

    def test_twilio_style_text_and_entities(self):
        rows = [
            frow(
                "t1",
                "Twilio Status",
                "Malaysia SMS Carrier Maintenance",
                "THIS IS A SCHEDULED EVENT Scheduled - &#60;p&#62;Our carrier is conducting a planned maintenance "
                "from 25 November 2026 at 09:00 PST until 25 November 2026 at 13:00 PST&#60;/p&#62;",
            )
        ]
        items, _, _ = self.run_watch(rows)
        self.assertEqual(items[0]["when"], "2026-11-25 09:00 PST")
        self.assertNotIn("<p>", items[0]["quote"])

    def test_past_and_beyond_horizon_dates_not_listed(self):
        rows = [
            frow(
                "p",
                "Zoom Status",
                "Scheduled update",
                "THIS IS A SCHEDULED EVENT new minimum version on November 7, 2026",
            ),
            frow(
                "f",
                "Zoom Status",
                "Scheduled update 2",
                "THIS IS A SCHEDULED EVENT planned maintenance on 15 March 2027",
            ),
        ]
        items, _, later = self.run_watch(rows)
        self.assertEqual(items, [])
        self.assertEqual(later, 1)

    def test_no_year_not_inferred(self):
        rows = [
            frow(
                "n",
                "Supabase Status",
                "Scheduled maintenance",
                "We will perform scheduled maintenance on Tuesday, December 8, from 13:00 to 15:00 UTC.",
            )
        ]
        items, undated, _ = self.run_watch(rows)
        self.assertEqual(items, [])
        self.assertEqual(undated, [])  # provider notices without a year are not guessed

    def test_latest_row_cancelled_removes_item(self):
        base = "Scheduled maintenance: database upgrade"
        rows = [
            frow(
                "m1",
                "Vercel Status",
                base,
                "THIS IS A SCHEDULED EVENT planned maintenance on 01 December 2026",
                day=18,
            ),
            frow(
                "m2",
                "Vercel Status",
                "Cancelled: " + base,
                "Maintenance cancelled. Was planned for 01 December 2026",
                day=20,
            ),
        ]
        items, _, _ = self.run_watch(rows)
        self.assertEqual(items, [])

    def test_rescheduled_keeps_latest_date(self):
        base = "Storage network maintenance"
        rows = [
            frow(
                "r1",
                "DigitalOcean Status",
                base,
                "Scheduled maintenance planned for 01 December 2026",
                day=18,
            ),
            frow(
                "r2",
                "DigitalOcean Status",
                "Rescheduled: " + base,
                "Scheduled maintenance planned for 05 December 2026",
                day=20,
            ),
        ]
        items, _, _ = self.run_watch(rows)
        self.assertEqual([i["date"].isoformat() for i in items], ["2026-12-05"])

    def test_official_deadline_label(self):
        rows = [
            frow(
                "o1",
                "APRA Media Releases",
                "Consultation on prudential standard",
                "Submissions close on 15 December 2026.",
            )
        ]
        items, _, _ = self.run_watch(rows)
        self.assertEqual(items[0]["tier"], "PRIMARY_OFFICIAL")
        self.assertEqual(items[0]["kind"], "deadline")
        self.assertEqual(items[0]["label"], "OFFICIAL_DATE_STATED")

    def test_news_is_secondary_and_never_confirmed(self):
        rows = [
            frow(
                "w1",
                "ARN - Australian IT Channel",
                "Vendor to retire product",
                "The vendor will retire the product on 10 December 2026.",
            )
        ]
        items, _, _ = self.run_watch(rows)
        self.assertEqual(items[0]["label"], "RELAYED_BY_NEWS")
        text = fw.render(items, [], 0, AS_OF, 42, 1, "fixture")
        self.assertIn("## Relayed by news (not authoritative, not confirmed)", text)
        self.assertNotIn("### Week commencing", text)

    def test_month_precision_label(self):
        rows = [
            frow(
                "mp",
                "AEMO Market Notices",
                "Planned maintenance",
                "Planned maintenance of the market network in December 2026.",
            )
        ]
        items, _, _ = self.run_watch(rows, horizon=60)
        self.assertEqual(items[0]["label"], "DATE_PRECISION_MONTH")

    def test_undated_official_planned_maintenance(self):
        rows = [
            frow(
                "u1",
                "AEMO Market Notices",
                "Initial - CHG0112685 - Planned maintenance affecting the AEMO Market Network.",
                "",
            )
        ]
        items, undated, _ = self.run_watch(rows)
        self.assertEqual(items, [])
        self.assertEqual(len(undated), 1)

    def test_cve_feeds_excluded(self):
        rows = [
            frow(
                "c1",
                "NVD / NIST CVE Database",
                "CVE-2026-1",
                "End of life product, will be removed on 10 December 2026, scheduled",
            )
        ]
        self.assertEqual(self.run_watch(rows)[0], [])

    def test_render_states_basis_date_and_label(self):
        rows = [
            frow(
                "s1",
                "Supabase Status",
                "Maintenance: Scheduled maintenance",
                "Status: Scheduled (Wed, 09 Dec 2026 13:00:00 GMT - Wed, 09 Dec 2026 15:00:00 GMT) scheduled maintenance.",
            )
        ]
        items, undated, later = self.run_watch(rows)
        text = fw.render(items, undated, later, AS_OF, 42, 1, "fixture")
        self.assertIn("Week commencing 2026-12-07", text)
        self.assertIn("SCHEDULED_BY_OWNER", text)
        self.assertIn("provider's own status feed", text)
        self.assertIn("`s1`", text)
        self.assertIn("not a forecast", text)

    def test_default_off(self):
        self.assertEqual(fw.main(["--input", "nonexistent.jsonl"]), 2)


if __name__ == "__main__":
    unittest.main()
