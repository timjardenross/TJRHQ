"""Tests for the offline intelligence products: disruption report, systemic view, forward watch (all default OFF)."""

import gzip
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ANALYTICS = (
    Path(__file__).resolve().parent.parent / "tools" / "intelligence" / "analytics"
)
sys.path.insert(0, str(ANALYTICS))

import forward_watch as fw
import provider_disruption_report as pdr
import systemic_risk_view as srv
from product_common import clean_text, load_rows, require_enabled

AS_OF = datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S+00")


def status_rows(feed, n, step_days, prefix="Incident", start=None, scheduled=0):
    start = start or AS_OF - timedelta(days=88)
    rows = []
    for i in range(n):
        pub = start + timedelta(days=i * step_days)
        rows.append(
            {
                "event_id": f"{feed[:3].lower()}-{i}",
                "source_name": feed,
                "published_at": iso(pub),
                "collected_at": iso(pub + timedelta(hours=1)),
                "canonical_url": f"https://status.example.com/incidents/{feed[:3].lower()}{prefix[:3]}{i:04d}xyz",
                "raw_title": f"{prefix} {i}: elevated errors (investigating)",
                "raw_summary": "Elevated error rates.",
            }
        )
    for j in range(scheduled):
        pub = start + timedelta(days=j)
        rows.append(
            {
                "event_id": f"{feed[:3].lower()}-s{j}",
                "source_name": feed,
                "published_at": iso(pub),
                "collected_at": iso(pub + timedelta(hours=1)),
                "canonical_url": f"https://status.example.com/incidents/sched{j:04d}abc",
                "raw_title": f"Scheduled maintenance {j}",
                "raw_summary": "THIS IS A SCHEDULED EVENT planned maintenance",
            }
        )
    return rows


class TestReport(unittest.TestCase):
    def setUp(self):
        self.rows = (
            status_rows(
                "Alpha Status", 30, 2.9
            )  # 30 incidents over ~87 days, 13 ISO weeks
            + status_rows("Beta Status", 6, 14)  # too few incidents
            + status_rows("Gamma Status", 24, 3.6)  # will get a bulk re-ingest artefact
        )
        bulk_time = AS_OF - timedelta(days=1)
        for r in self.rows:
            if (
                r["source_name"] == "Gamma Status"
                and int(r["event_id"].split("-")[1]) < 20
            ):
                r["collected_at"] = iso(bulk_time)
        self.feeds, self.start = pdr.analyse(self.rows, AS_OF)

    def test_sufficient_feed_scored(self):
        f = self.feeds["Alpha Status"]
        self.assertTrue(f["sufficient"])
        self.assertEqual(len(f["unplanned"]), 30)
        self.assertGreaterEqual(len(f["weeks"]), 10)
        self.assertAlmostEqual(f["median_gap_days"], 2.9, places=1)

    def test_below_threshold_not_scored(self):
        f = self.feeds["Beta Status"]
        self.assertFalse(f["sufficient"])
        self.assertNotIn("median_gap_days", f)
        self.assertNotIn("trend", f)
        self.assertTrue(any(r.startswith("(a)") for r in f["reasons"]))

    def test_bulk_artefact_blocks_scoring(self):
        f = self.feeds["Gamma Status"]
        self.assertFalse(f["sufficient"])
        self.assertGreaterEqual(f["bulk_share"], 0.2)
        self.assertTrue(any(r.startswith("(c)") for r in f["reasons"]))
        self.assertNotIn("median_gap_days", f)

    def test_scheduled_excluded_from_unplanned(self):
        feeds, _ = pdr.analyse(status_rows("Delta Status", 25, 3, scheduled=10), AS_OF)
        self.assertEqual(len(feeds["Delta Status"]["unplanned"]), 25)
        self.assertEqual(feeds["Delta Status"]["scheduled"], 10)

    def test_render_has_evidence_and_insufficient_section(self):
        text = pdr.render(self.feeds, AS_OF, self.start, "fixture")
        self.assertIn("generated 2026-11-24", text)
        self.assertIn("`alp-29`", text)  # latest evidence id for Alpha
        self.assertIn("## Insufficient evidence (listed, never scored)", text)
        self.assertIn("Beta Status", text.split("## Insufficient evidence")[1])
        self.assertNotIn("### Beta", text)  # no per-provider scored section

    def test_trend_requires_both_windows_and_no_bulk(self):
        incs = pdr._unplanned(pdr.build_incidents(status_rows("Alpha Status", 30, 2.9)))
        label, detail = pdr.trend(incs, AS_OF, bulk_in_windows=True)
        self.assertEqual(label, "not assessed")
        self.assertIn("collection artefact", detail)
        label, _ = pdr.trend(incs[:3], AS_OF, bulk_in_windows=False)
        self.assertEqual(label, "not assessed")

    def test_trend_higher(self):
        recent = status_rows("Eps Status", 12, 2.4, start=AS_OF - timedelta(days=29))
        prior = status_rows(
            "Eps Status", 8, 7, start=AS_OF - timedelta(days=88), prefix="Old"
        )
        incs = pdr._unplanned(pdr.build_incidents(recent + prior))
        label, _ = pdr.trend(incs, AS_OF, bulk_in_windows=False)
        self.assertEqual(label, "higher")

    def test_default_off(self):
        self.assertFalse(require_enabled(False))
        self.assertEqual(pdr.main(["--input", "nonexistent.jsonl"]), 2)


def ctx(
    eid, title, sector, org=None, geo="AU", etype="technology_outage", day=1, summary=""
):
    pub = datetime(2026, 11, day, 3, 0, tzinfo=timezone.utc)
    return {
        "event_id": eid,
        "source_name": "News",
        "published_at": iso(pub),
        "collected_at": iso(pub),
        "canonical_url": f"https://n.example/{eid}",
        "raw_title": title,
        "raw_summary": summary,
        "sector": sector,
        "geography": geo,
        "event_type": etype,
        "organisation": org,
    }


class TestSystemicView(unittest.TestCase):
    def test_sector_span_link_with_evidence(self):
        rows = [
            ctx("e1", "Cloudflare outage knocks sites offline", "technology", day=3),
            ctx(
                "e2",
                "Cloudflare outage disrupts online banking",
                "financial_services",
                day=5,
            ),
            ctx("e3", "Okta confirms breach of support system", "technology", day=6),
        ]
        tagged = srv.tag_rows(rows)
        links = srv.find_links(tagged, AS_OF)
        self.assertEqual([link["provider"] for link in links], ["cloudflare"])
        self.assertEqual(links[0]["sectors"], ["financial_services", "technology"])
        self.assertEqual(
            {i["row"]["event_id"] for i in links[0]["items"]}, {"e1", "e2"}
        )
        text = srv.render(tagged, AS_OF, "fixture")
        self.assertIn("`e1`", text)
        self.assertIn("Evidence span", text)

    def test_cross_sector_label_and_other_type_do_not_count(self):
        rows = [
            ctx("e1", "Cloudflare outage knocks sites offline", "technology", day=3),
            ctx("e2", "Cloudflare outage hits users", "cross_sector", day=4),
            ctx(
                "e3",
                "Cloudflare outage hits shoppers",
                "transport",
                etype="other",
                day=4,
            ),
        ]
        self.assertEqual(srv.find_links(srv.tag_rows(rows), AS_OF), [])

    def test_same_headline_counts_once(self):
        rows = [
            ctx("e1", "Cloudflare outage knocks sites offline", "technology", day=3),
            ctx("e2", "Cloudflare outage knocks sites offline", "energy", day=4),
        ]
        self.assertEqual(srv.find_links(srv.tag_rows(rows), AS_OF), [])

    def test_outside_window_no_link(self):
        rows = [
            ctx("e1", "Cloudflare outage knocks sites offline", "technology", day=1),
            ctx(
                "e2",
                "Cloudflare outage disrupts online banking",
                "financial_services",
                day=20,
            ),
        ]
        self.assertEqual(srv.find_links(srv.tag_rows(rows), AS_OF), [])

    def test_insufficient_concentration_statement(self):
        rows = [
            ctx("e1", "Cloudflare outage knocks sites offline", "technology", day=3)
        ]
        text = srv.render(srv.tag_rows(rows), AS_OF, "fixture")
        self.assertIn(
            "INSUFFICIENT EVIDENCE. No concentration score is produced.", text
        )
        self.assertIn("AFFECTED tags: 0; SUPPLYING tags: 0", text)

    def test_concentration_candidates_need_three_orgs_two_events(self):
        rows = [
            ctx(
                "a",
                "Telstra services disrupted by AWS outage in Sydney",
                "technology",
                org="OrgA",
                day=2,
            ),
            ctx(
                "b",
                "Telstra customers hit by AWS outage again",
                "technology",
                org="OrgB",
                day=9,
            ),
            ctx(
                "c",
                "Telstra apps knocked offline by AWS outage",
                "technology",
                org="OrgC",
                day=15,
            ),
        ]
        tagged = srv.tag_rows(rows)
        counts, _, eligible = srv.concentration_evidence(tagged, AS_OF)
        self.assertGreaterEqual(counts["AFFECTED"], 3)
        self.assertIn("telstra", eligible)
        text = srv.render(tagged, AS_OF, "fixture")
        self.assertIn("CANDIDATES", text)
        self.assertIn("No numeric concentration score is produced", text)

    def test_two_orgs_not_enough(self):
        rows = [
            ctx(
                "a",
                "Telstra services disrupted by AWS outage in Sydney",
                "technology",
                org="OrgA",
                day=2,
            ),
            ctx(
                "b",
                "Telstra customers hit by AWS outage again",
                "technology",
                org="OrgB",
                day=9,
            ),
        ]
        _, _, eligible = srv.concentration_evidence(srv.tag_rows(rows), AS_OF)
        self.assertEqual(eligible, {})

    def test_critical_infra_cut_counts(self):
        rows = [
            ctx("a", "Optus outage knocks out calls", "technology", day=2),
            ctx("b", "Optus outage in UK", "technology", geo="GB", day=2),
        ]
        sel, cls = srv.critical_infra_cut(srv.tag_rows(rows), AS_OF)
        self.assertEqual(len(sel), 1)
        self.assertEqual(cls.get("AFFECTED", 0), 0)

    def test_default_off(self):
        self.assertEqual(srv.main(["--input", "nonexistent.jsonl"]), 2)


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


class TestCommon(unittest.TestCase):
    def test_clean_text_double_escaped(self):
        self.assertEqual(clean_text("AT&amp;T &#60;p&#62;x&#60;/p&#62;"), "AT&T x")

    def test_load_rows_gz(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.jsonl.gz"
            with gzip.open(p, "wt", encoding="utf-8") as fh:
                fh.write(json.dumps({"a": 1}) + "\n")
            self.assertEqual(load_rows([str(p)]), [{"a": 1}])


if __name__ == "__main__":
    unittest.main()
