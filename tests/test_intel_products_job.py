"""Tests for intel_products (product records) and intelligence/intel_products_job.py (default OFF)."""

import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools" / "intelligence" / "analytics"))

import intel_products as ip
from test_systemic_intel_products import AS_OF, ctx, frow, status_rows

from intelligence import intel_products_job as job

SECTIONS = {
    "confirmed_evidence",
    "analytical_inference",
    "potential_exposure",
    "unknowns",
}


def sample():
    recent = status_rows("Eps Status", 12, 2.4, start=AS_OF - timedelta(days=29))
    prior = status_rows(
        "Eps Status", 8, 7, start=AS_OF - timedelta(days=88), prefix="Old"
    )
    ctx_rows = [
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
    fwd = [
        frow(
            "o1",
            "APRA Media Releases",
            "Consultation on standard",
            "Submissions close on 27 November 2026.",
            day=20,
        ),
        frow(
            "m1",
            "Twilio Status",
            "Carrier maintenance",
            "THIS IS A SCHEDULED EVENT planned maintenance from 25 November 2026 at 09:00 PST",
            day=20,
        ),
    ]
    return recent + prior, ctx_rows + fwd


class TestProducts(unittest.TestCase):
    def setUp(self):
        status, context = sample()
        self.products = {
            p["product_key"]: p for p in ip.build_products(status, context, AS_OF)
        }

    def test_three_products_each_with_four_sections(self):
        self.assertEqual(set(self.products), set(ip.PRODUCT_KEYS))
        for p in self.products.values():
            self.assertTrue(SECTIONS <= set(p["sections"]))
            self.assertTrue(p["sections"]["unknowns"])
            self.assertTrue(p["body_md"])

    def test_recurring_exception_has_stable_key(self):
        status, context = sample()
        again = {p["product_key"]: p for p in ip.build_products(status, context, AS_OF)}
        keys = [
            e["dedupe_key"] for e in self.products["recurring_provider"]["exceptions"]
        ]
        self.assertEqual(
            keys, [e["dedupe_key"] for e in again["recurring_provider"]["exceptions"]]
        )
        for k in keys:
            self.assertRegex(k, r"^recurring-provider:[a-z0-9-]+:higher:\d{4}-W\d{2}$")

    def test_concentration_exception_and_forward_exception(self):
        sys_keys = [
            e["dedupe_key"] for e in self.products["systemic_risk"]["exceptions"]
        ]
        self.assertTrue(
            any(k.startswith("systemic:concentration:telstra:") for k in sys_keys)
        )
        fw_ex = self.products["forward_watch"]["exceptions"]
        self.assertEqual(
            [e["dedupe_key"] for e in fw_ex], ["forward-watch:o1:2026-11-27"]
        )  # official, due in 3 days; Twilio maintenance does not raise

    def test_weekly_message_has_summary_and_link(self):
        text = ip.weekly_message(
            list(self.products.values()), "https://portal.example/", AS_OF
        )
        self.assertIn("https://portal.example/intelligence", text)
        self.assertIn("flagged for attention", text)
        self.assertLess(len(text), 1500)


class TestJob(unittest.TestCase):
    def test_default_off(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                job.run(AS_OF, getter=lambda *a: 1 / 0, writer=lambda r: 1 / 0), []
            )
            self.assertFalse(job.send_weekly([], AS_OF, notifier=lambda t: True))
            sched = mock.Mock()
            job.register_jobs(sched, None)
            sched.add_job.assert_not_called()

    def test_run_reads_and_writes_one_record_per_product(self):
        status, context = sample()
        registry = [
            {"source_id": 1, "source_name": "Eps Status"},
            {"source_id": 2, "source_name": "News"},
        ]
        events = [dict(r, source_id=1) for r in status] + [
            dict(r, source_id=2) for r in context
        ]
        for e in events:
            e.pop("source_name", None)

        def getter(table, query):
            self.assertNotIn("&delete", query)
            return registry if table == "intelligence_source_registry" else events

        written = []
        with mock.patch.dict("os.environ", {"INTEL_PRODUCTS_ENABLED": "1"}):
            products = job.run(AS_OF, getter=getter, writer=written.append)
        self.assertEqual(len(products), 3)
        self.assertEqual({w["product_key"] for w in written}, set(ip.PRODUCT_KEYS))
        self.assertEqual({w["generated_for"] for w in written}, {"2026-11-24"})

    def test_weekly_send_gated_separately(self):
        sent = []
        with mock.patch.dict(
            "os.environ",
            {
                "INTEL_PRODUCTS_WEEKLY_TELEGRAM": "1",
                "PORTAL_BASE_URL": "https://p.example",
            },
        ):
            ok = job.send_weekly(
                [{"title": "T", "summary": "S", "exceptions": []}],
                AS_OF,
                notifier=sent.append,
            )
        self.assertTrue(ok or sent)
        self.assertIn("https://p.example/intelligence", sent[0])

    @unittest.skipUnless(
        importlib.util.find_spec("apscheduler"), "apscheduler not installed"
    )
    def test_register_when_enabled(self):
        sched = mock.Mock()
        with mock.patch.dict("os.environ", {"INTEL_PRODUCTS_ENABLED": "1"}):
            job.register_jobs(sched, None)
        self.assertEqual(sched.add_job.call_args.kwargs["id"], "intel_products_weekly")

    def test_utc_aware(self):
        self.assertEqual(AS_OF.tzinfo, timezone.utc)
        self.assertIsInstance(AS_OF, datetime)


if __name__ == "__main__":
    unittest.main()
