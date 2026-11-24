"""Tests: Optus outage register (retrospective), provider disclaimer/ordering, brief block, generation CLI."""

import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools" / "intelligence" / "analytics"))

import generate_intel_products as gen
import intel_products as ip
import provider_disruption_report as pdr
import register_records as rr
from test_systemic_intel_products import AS_OF, status_rows

from intelligence import brief_products_block as bpb

FIXTURE = ROOT / "tests" / "fixtures" / "optus_outage_register_rendered_20261124.html"


def register_rows():
    return rr.rows_from_register_html(FIXTURE.read_text(encoding="utf-8"))


class TestRegister(unittest.TestCase):
    def test_fixture_parses_into_entries(self):
        rows = register_rows()
        self.assertEqual(len(rows), 5)
        e = rr.parse_entry(rows[0])
        self.assertEqual(e["reference"], "IM2450998")
        self.assertEqual(e["start"], date(2026, 11, 22))
        self.assertEqual(e["duration_h"], 18.0)
        self.assertEqual(e["cause"], "Damage by a third party")
        self.assertIn("Mobile voice", e["services"])

    def test_bucketed_by_event_start_not_collection_date(self):
        rows = register_rows()
        for r in rows:  # simulate a historical import: collected/published just now, outages are older or newer
            r["collected_at"] = r["published_at"] = "2026-11-24 05:00:00+00"
        inside = rr.analyse(rows, AS_OF)
        self.assertEqual(len(inside["entries"]), 5)
        old = rr.analyse(
            rows, AS_OF + timedelta(days=200)
        )  # entries now far outside the 90-day window by their own date
        self.assertEqual(old["entries"], [])

    def test_evidence_is_labelled_retrospective_and_never_an_exception(self):
        rows = register_rows()
        prods = {
            p["product_key"]: p
            for p in ip.build_products(
                status_rows("Alpha Status", 30, 2.9), rows, AS_OF
            )
        }
        rec = prods["recurring_provider"]
        reg_lines = [
            x
            for x in rec["sections"]["confirmed_evidence"]
            if "retrospective record" in x
        ]
        self.assertGreaterEqual(len(reg_lines), 2)
        self.assertTrue(
            any(
                "IM2450998" in x and "Damage by a third party" in x and "18.0 h" in x
                for x in reg_lines
            )
        )
        self.assertTrue(all("Optus" in x for x in reg_lines))
        for p in prods.values():
            self.assertFalse(
                any(
                    "IM2450998" in json.dumps(e) or "register" in e["dedupe_key"]
                    for e in p["exceptions"]
                )
            )
        # register rows never feed the systemic view or the forward watch
        self.assertNotIn("IM2450998", prods["systemic_risk"]["body_md"])
        self.assertNotIn("IM2450998", prods["forward_watch"]["body_md"])

    def test_unreadable_entry_counted_not_guessed(self):
        r = dict(register_rows()[0], raw_summary="Restored. no dates here")
        res = rr.analyse([r], AS_OF)
        self.assertEqual((res["entries"], res["unreadable"]), ([], 1))


class TestDisclaimerAndOrder(unittest.TestCase):
    def test_disclaimer_and_alphabetical(self):
        rows = status_rows("Zeta Status", 40, 2.1) + status_rows(
            "Alpha Status", 25, 3.4
        )
        feeds, start = pdr.analyse(rows, AS_OF)
        text = pdr.render(feeds, AS_OF, start, "fixture")
        self.assertIn(pdr.DISCLAIMER, text)
        self.assertLess(
            text.index("### Alpha"), text.index("### Zeta")
        )  # Zeta has the larger count but sorts last
        self.assertIn("Context (read before comparing)", text)
        self.assertIn("status-page publisher", text)
        prod = ip.recurring_provider_product(rows, AS_OF, "fixture")
        self.assertTrue(
            any(pdr.DISCLAIMER in x for x in prod["sections"]["analytical_inference"])
        )
        self.assertIn(pdr.DISCLAIMER, prod["sections"]["coverage_note"])


def rec(key, findings, gen_day="2026-11-24", note="coverage note"):
    return {
        "product_key": key,
        "generated_for": gen_day,
        "sections": {"brief_findings": findings, "coverage_note": note},
    }


TODAY = date(2026, 11, 24)


class TestBriefBlock(unittest.TestCase):
    def on(self):
        return mock.patch.dict("os.environ", {bpb.FLAG: "1"}, clear=True)

    def test_flag_off_returns_nothing(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                bpb.brief_lines(TODAY, reader=lambda: [rec("forward_watch", ["x"])]), []
            )

    def test_nothing_qualifies_prints_nothing(self):
        with self.on():
            self.assertEqual(
                bpb.brief_lines(
                    TODAY,
                    reader=lambda: [rec("forward_watch", []), rec("systemic_risk", [])],
                ),
                [],
            )
            self.assertEqual(bpb.brief_lines(TODAY, reader=list), [])

    def test_forward_watch_finding_expires_after_due_date(self):
        ex = {
            "title": "2026-11-25: Consultation closes",
            "detail": "APRA; OFFICIAL_DATE_STATED; due within 7 days.",
            "due_date": "2026-11-25",
        }
        row = rec("forward_watch", [f"{ex['title']} ({ex['detail']})"])
        row["exceptions"] = [ex]
        with self.on():
            self.assertEqual(bpb.brief_lines(date(2026, 11, 25), reader=lambda: [row])[0], "INTELLIGENCE PRODUCTS")
            self.assertEqual(bpb.brief_lines(date(2026, 11, 26), reader=lambda: [row]), [])

    def test_findings_render_few_lines_with_one_coverage_line(self):
        rows = [
            rec("forward_watch", ["2026-11-27: APRA consultation closes"]),
            rec("recurring_provider", ["Zoom: higher"]),
        ]
        with self.on():
            lines = bpb.brief_lines(TODAY, reader=lambda: rows)
        text = "\n".join(lines)
        self.assertIn("APRA consultation closes", text)
        self.assertEqual(sum(1 for line in lines if line.startswith("Coverage:")), 1)
        self.assertLessEqual(len([line for line in lines if line]), 6)

    def test_stale_products_ignored(self):
        with self.on():
            self.assertEqual(
                bpb.brief_lines(
                    TODAY,
                    reader=lambda: [rec("forward_watch", ["x"], gen_day="2026-11-01")],
                ),
                [],
            )

    def test_fail_soft_on_reader_and_bad_data(self):
        def boom():
            raise RuntimeError("db down")

        with self.on():
            self.assertEqual(
                bpb.brief_lines(TODAY, reader=boom), []
            )  # no dir configured: files fallback finds nothing
            self.assertEqual(
                bpb.brief_lines(
                    TODAY, reader=lambda: [{"product_key": "forward_watch"}, "junk"]
                ),
                [],
            )

    def test_file_fallback_when_table_missing(self):
        def missing():
            raise RuntimeError("relation does not exist")

        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "portal-product-records-2026-11-24.json").write_text(
                json.dumps(
                    [
                        rec(
                            "forward_watch",
                            ["2026-11-26: planned window"],
                            gen_day="2026-11-24",
                        )
                    ]
                )
            )
            with mock.patch.dict(
                "os.environ", {bpb.FLAG: "1", "INTEL_PRODUCTS_DIR": d}, clear=True
            ):
                text = "\n".join(bpb.brief_lines(TODAY, reader=missing))
        self.assertIn("planned window", text)


class TestCli(unittest.TestCase):
    def test_default_off(self):
        self.assertEqual(gen.main([]), 2)

    def test_dry_run_from_files_writes_preview_and_no_db(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "s.jsonl"
            sp.write_text(
                "".join(
                    json.dumps(r) + "\n" for r in status_rows("Alpha Status", 30, 2.9)
                )
            )
            cp = Path(d) / "c.jsonl"
            cp.write_text("")
            out = Path(d) / "out"
            with mock.patch(
                "intelligence.intel_products_job._upsert",
                side_effect=AssertionError("no db write"),
            ):
                rc = gen.main(
                    [
                        "--enable",
                        "--dry-run",
                        "--status",
                        str(sp),
                        "--context",
                        str(cp),
                        "--as-of",
                        "2026-11-24",
                        "--out-dir",
                        str(out),
                    ]
                )
            self.assertEqual(rc, 0)
            files = {p.name for p in out.iterdir()}
            self.assertIn("portal-product-records-2026-11-24.json", files)
            self.assertIn("recurring_provider-2026-11-24.md", files)
            recs = json.loads(
                (out / "portal-product-records-2026-11-24.json").read_text()
            )
            self.assertEqual({r["product_key"] for r in recs}, set(ip.PRODUCT_KEYS))

    def test_utc(self):
        self.assertEqual(AS_OF.tzinfo, timezone.utc)
        self.assertIsInstance(AS_OF, datetime)


if __name__ == "__main__":
    unittest.main()
