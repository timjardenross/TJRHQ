"""Regression tests for the DB/migration review fixes that need no database (writer protocol, freshness, brief block)."""

import copy
import sys
import unittest
import urllib.error
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools" / "intelligence" / "analytics"))

from test_product_history import MemGateway, mel, rec

from intelligence import brief_products_block as bpb
from intelligence import intel_products_job as job
from intelligence import product_history as ph

UTC = timezone.utc
F = ph.Freshness


def gen(body="B", as_of=datetime(2026, 11, 25, 19, 20, tzinfo=UTC), cadence="daily", legacy=False, key="forward_watch"):
    return ph.build_generation(rec(body=body, as_of=as_of, key=key), cadence=cadence, legacy_attribution=legacy, watermark=None)


class LegacyKeyGateway(MemGateway):
    """A 0263a-only database: the original key (product_key, generated_for) still exists; an overwrite replaces the row."""

    def __init__(self):
        super().__init__()
        self.archive = []

    def insert_generation(self, rec_):
        with self._lock:
            for g in self.gens:
                if (g["product_key"], g["generated_for"]) == (rec_["product_key"], rec_["generated_for"]):
                    raise ph.UniqueViolation("legacy pk", legacy_key=True)
        return super().insert_generation(rec_)

    def overwrite_generation(self, rec_):
        with self._lock:
            for i, g in enumerate(self.gens):
                if (g["product_key"], g["generated_for"]) == (rec_["product_key"], rec_["generated_for"]):
                    self.archive.append(copy.deepcopy(g))
                    self.gens[i] = dict(rec_, id=g["id"])
                    return dict(self.gens[i])
        raise AssertionError("no row to overwrite")


class TestLatestSelectionAndSequence(unittest.TestCase):
    def test_mixed_attribution_does_not_wedge_flag_off_fallback(self):
        # live row: generated 19:20Z 25 Nov, Melbourne date 26 Nov (reporting_date 26), legacy key 25 Nov
        mem = MemGateway()
        ph.record_run(mem, gen("live", cadence="unknown"))      # flag-ON style attribution, cadence unknown
        # a flag-OFF fallback run at 22:00Z the same UTC day uses the UTC date (25 Nov) as reporting_date
        g2 = gen("later", as_of=datetime(2026, 11, 25, 22, 0, tzinfo=UTC), cadence="unknown", legacy=True)
        self.assertEqual((g2["reporting_date"], mem.gens[0]["reporting_date"]), ("2026-11-25", "2026-11-26"))
        r = ph.record_run(mem, g2)
        self.assertEqual((r.outcome, r.generation_seq, r.attempts), ("new_generation", 1, 1))
        # the next fallback run the same UTC day gets seq 2 for the exact key, not a collision
        r3 = ph.record_run(mem, gen("later2", as_of=datetime(2026, 11, 25, 23, 0, tzinfo=UTC), cadence="unknown", legacy=True))
        self.assertEqual((r3.generation_seq, r3.attempts), (2, 1))

    def test_latest_is_by_generation_time_not_reporting_date(self):
        mem = MemGateway()
        ph.record_run(mem, gen("old", cadence="unknown"))   # reporting_date 26 Nov, as_of 19:20Z
        newer = gen("new", as_of=datetime(2026, 11, 25, 22, 0, tzinfo=UTC), cadence="unknown", legacy=True)
        ph.record_run(mem, newer)
        self.assertEqual(mem.latest_generation("forward_watch", "unknown")["body_md"], "new")

    def test_change_summary_carries_write_nonce_and_stays_deterministic_otherwise(self):
        mem = MemGateway()
        ph.record_run(mem, gen("a"))
        cs = mem.gens[0]["change_summary"]
        self.assertTrue(cs.pop("write_id"))
        self.assertEqual(cs, {"first_generation": True})


class TestExpandOnlyDatabase(unittest.TestCase):
    def test_second_generation_of_same_day_overwrites_via_archive_when_legacy_key_exists(self):
        gw = LegacyKeyGateway()
        r1 = ph.record_run(gw, gen("one", as_of=datetime(2026, 11, 25, 19, 20, tzinfo=UTC)))
        r2 = ph.record_run(gw, gen("two", as_of=datetime(2026, 11, 25, 19, 40, tzinfo=UTC)))
        self.assertEqual((r1.outcome, r2.outcome, r2.generation_seq), ("new_generation", "new_generation", 2))
        self.assertEqual([g["body_md"] for g in gw.gens], ["two"])
        self.assertEqual([g["body_md"] for g in gw.archive], ["one"])
        self.assertIsNone(gw.gens[0]["supersedes_id"])               # no self-reference
        self.assertTrue(gw.gens[0]["change_summary"]["previous_version_archived"])
        self.assertEqual([r["outcome"] for r in gw.refreshes], ["new_generation", "new_generation"])

    def test_unreadable_conflict_fails_closed_without_overwriting(self):
        class NoOverwrite(MemGateway):
            def insert_generation(self, rec_):
                raise ph.UniqueViolation("?", legacy_key=False)

            def overwrite_generation(self, rec_):
                raise AssertionError("must not overwrite")

        with self.assertRaises(RuntimeError):
            ph.record_run(NoOverwrite(), gen("x"))


class TestRestGatewayClassification(unittest.TestCase):
    def _err(self, body):
        return urllib.error.HTTPError("u", 409, "conflict", {}, BytesIO(body))

    def _gw(self, body):
        def poster(table, record, **kw):
            raise self._err(body)
        return job.RestGateway(getter=lambda *a: [], poster=poster)

    def test_legacy_pk_conflict_is_flagged(self):
        gw = self._gw(b'{"code":"23505","details":"Key (product_key, generated_for)=(forward_watch, 2026-11-25) already exists."}')
        with self.assertRaises(ph.UniqueViolation) as cm:
            gw.insert_generation({"generation_seq": 2})
        self.assertTrue(cm.exception.legacy_key)

    def test_generation_key_conflict_is_not_legacy(self):
        gw = self._gw(b'{"code":"23505","details":"Key (product_key, cadence, reporting_date, generation_seq)=(a, daily, 2026-11-25, 2) already exists."}')
        with self.assertRaises(ph.UniqueViolation) as cm:
            gw.insert_generation({"generation_seq": 2})
        self.assertFalse(cm.exception.legacy_key)

    def test_overwrite_uses_legacy_on_conflict_target_and_latest_orders_by_generation_time(self):
        calls, gets = [], []
        gw = job.RestGateway(getter=lambda t, q: gets.append(q) or [], poster=lambda t, r, **kw: calls.append((t, kw)) or {"id": 1})
        gw.overwrite_generation({"a": 1})
        self.assertEqual(calls[0][1]["query"], "?on_conflict=product_key%2Cgenerated_for")
        self.assertTrue(calls[0][1]["merge"])
        gw.latest_generation("forward_watch", "daily")
        self.assertIn("order=as_of.desc%2Cid.desc", gets[0])
        self.assertNotIn("reporting_date.desc", gets[0])


class TestFailedGenerationIsRecorded(unittest.TestCase):
    def test_failure_before_any_product_is_built_is_recorded_for_all_products(self):
        mem = MemGateway()

        def boom(*a):
            raise urllib.error.URLError("down")

        with mock.patch.dict("os.environ", {"INTEL_PRODUCTS_ENABLED": "1", "INTEL_PRODUCTS_APPEND_V1": "1"}, clear=True):  # noqa: SIM117 - nested contexts kept for readability
            with self.assertRaises(urllib.error.URLError):
                job.run(datetime(2026, 11, 25, 19, 20, tzinfo=UTC), getter=boom, gateway=mem, cadence="daily")
        self.assertEqual(sorted(r["product_key"] for r in mem.refreshes),
                         ["forward_watch", "recurring_provider", "systemic_risk"])
        self.assertTrue(all(r["outcome"] == "failed" and r["cadence"] == "daily" and r["error_class"] == "URLError" for r in mem.refreshes))

    def test_flag_off_records_nothing_on_failure(self):
        mem = MemGateway()
        with mock.patch.dict("os.environ", {"INTEL_PRODUCTS_ENABLED": "1"}, clear=True):  # noqa: SIM117 - nested contexts kept for readability
            with self.assertRaises(RuntimeError):
                job.run(datetime(2026, 11, 25, 19, 20, tzinfo=UTC), getter=lambda *a: (_ for _ in ()).throw(RuntimeError("x")), gateway=mem)
        self.assertEqual(mem.refreshes, [])


class TestFreshnessAtBriefTime(unittest.TestCase):
    def test_missed_daily_refresh_is_overdue_at_the_0700_brief_summer_and_winter(self):
        # summer: brief 07:01 AEDT, last success 24.65 h earlier (yesterday 06:22 + missed today)
        r = ph.freshness(mel(2026, 11, 25, 7, 1), "daily", mel(2026, 11, 24, 6, 22))
        self.assertEqual(r.state, F.REFRESH_OVERDUE)
        self.assertEqual(r.expected_deadline, mel(2026, 11, 25, 6, 45))
        # a refresh that ran at 06:22 today is current
        self.assertEqual(ph.freshness(mel(2026, 11, 25, 7, 1), "daily", mel(2026, 11, 25, 6, 22)).state, F.CURRENT)
        # winter (AEST): the brief is after the slot as well
        self.assertEqual(ph.freshness(mel(2026, 7, 15, 7, 1), "daily", mel(2026, 7, 14, 6, 22)).state, F.REFRESH_OVERDUE)

    def test_weekly_monday_deadline_is_equivalent(self):
        sched = mel(2026, 11, 23, 7, 22)
        self.assertEqual(ph.freshness(mel(2026, 11, 30, 7, 40), "weekly", sched).state, F.CURRENT)         # before 07:45
        self.assertEqual(ph.freshness(mel(2026, 11, 30, 7, 50), "weekly", sched).state, F.REFRESH_OVERDUE)
        # the 07:00 Monday brief reads last Monday's weekly assessment: Current
        self.assertEqual(ph.freshness(mel(2026, 11, 30, 7, 1), "weekly", sched).state, F.CURRENT)

    def test_failed_attempt_makes_previous_assessment_not_current_before_the_deadline(self):
        last_ok, failed = mel(2026, 11, 24, 6, 22), mel(2026, 11, 25, 6, 22)
        r = ph.freshness(mel(2026, 11, 25, 6, 40), "daily", last_ok, failed)   # before the 06:45 deadline
        self.assertEqual(r.state, F.REFRESH_OVERDUE)
        self.assertTrue(r.failed_since_success)
        self.assertEqual(ph.freshness(mel(2026, 11, 25, 6, 40), "daily", last_ok, None).state, F.CURRENT)

    def test_failure_older_than_last_success_or_than_the_slot_is_ignored(self):
        self.assertEqual(ph.freshness(mel(2026, 11, 25, 8, 0), "daily", mel(2026, 11, 25, 6, 25), mel(2026, 11, 25, 6, 21)).state, F.CURRENT)
        # a failure from two days ago does not by itself flag today's refresh
        self.assertEqual(ph.freshness(mel(2026, 11, 25, 6, 30), "daily", mel(2026, 11, 24, 6, 25), mel(2026, 11, 23, 6, 21)).state, F.CURRENT)

    def test_manual_run_shortly_before_the_slot_satisfies_it(self):
        self.assertEqual(ph.freshness(mel(2026, 11, 25, 7, 10), "daily", mel(2026, 11, 25, 6, 10)).state, F.CURRENT)

    def test_unknown_cadence_failure_flags_overdue(self):
        r = ph.freshness(mel(2026, 11, 25, 7, 0), "unknown", mel(2026, 11, 24, 20, 0), mel(2026, 11, 25, 6, 0))
        self.assertEqual(r.state, F.REFRESH_OVERDUE)


class TestBriefBlockCadences(unittest.TestCase):
    NOW = mel(2026, 11, 25, 7, 1).astimezone(UTC)

    def row(self, cadence, refreshed, key="forward_watch", finding="F", failed=None):
        return {"product_key": key, "cadence": cadence, "generated_for": "2026-11-25", "as_of": refreshed.isoformat(),
                "last_refresh_as_of": refreshed.isoformat(),
                "last_failed_as_of": failed.isoformat() if failed else None,
                "sections": {"brief_findings": [finding], "coverage_note": f"note {key}"}, "exceptions": []}

    def lines(self, rows, now=None):
        env = {"INTEL_PRODUCTS_IN_BRIEF": "1", "INTEL_PRODUCTS_APPEND_V1": "1"}
        with mock.patch.dict("os.environ", env, clear=True):
            return bpb.brief_lines(reader=lambda: rows, now=now or self.NOW)

    def test_stale_weekly_row_is_not_hidden_by_a_current_daily_row(self):
        rows = [self.row("daily", mel(2026, 11, 25, 6, 22), finding="DAILY"),
                self.row("weekly", mel(2026, 11, 10, 7, 22), finding="WEEKLY")]
        out = self.lines(rows)
        text = "\n".join(out)
        self.assertIn("DAILY", text)
        self.assertNotIn("WEEKLY", text)
        self.assertTrue(any(l.startswith("- Status: Forward watch (weekly): Stale, last assessed 10 Nov 07:22 AEDT") for l in out), out)

    def test_legacy_unknown_row_is_never_reported_as_an_extra(self):
        rows = [self.row("daily", mel(2026, 11, 25, 6, 22), finding="DAILY"), self.row("unknown", mel(2026, 11, 1, 6, 22))]
        out = self.lines(rows)
        self.assertFalse(any("unknown" in l.lower() for l in out), out)

    def test_current_daily_beats_older_unknown_and_unknown_wins_only_if_newer(self):
        rows = [self.row("unknown", mel(2026, 11, 25, 6, 30), finding="UNKNOWN-NEWER"), self.row("daily", mel(2026, 11, 25, 6, 22), finding="DAILY")]
        self.assertIn("UNKNOWN-NEWER", "\n".join(self.lines(rows)))
        rows2 = [self.row("unknown", mel(2026, 11, 24, 6, 30), finding="UNKNOWN-OLD"), self.row("daily", mel(2026, 11, 25, 6, 22), finding="DAILY")]
        out2 = "\n".join(self.lines(rows2))
        self.assertIn("DAILY", out2)
        self.assertNotIn("UNKNOWN-OLD", out2)

    def test_usable_row_beats_a_more_recent_but_unusable_one(self):
        # weekly refreshed 8.5 days ago is Stale; daily 20 h old is usable: findings from daily
        rows = [self.row("weekly", mel(2026, 11, 16, 20, 0), finding="WEEKLY"), self.row("daily", mel(2026, 11, 24, 11, 0), finding="DAILY")]
        self.assertIn("DAILY", "\n".join(self.lines(rows)))

    def test_missed_refresh_shows_overdue_at_brief_time_and_failed_attempt_is_named(self):
        rows = [self.row("daily", mel(2026, 11, 24, 6, 22))]
        self.assertTrue(any("REFRESH OVERDUE, as of 24 Nov 06:22 AEDT" in l for l in self.lines(rows)))
        failed = [self.row("daily", mel(2026, 11, 24, 6, 22), failed=mel(2026, 11, 25, 6, 22))]
        out = self.lines(failed, now=mel(2026, 11, 25, 6, 40).astimezone(UTC))
        self.assertTrue(any("LAST REFRESH FAILED 25 Nov 06:22 AEDT, as of 24 Nov 06:22 AEDT" in l for l in out), out)

    def test_flag_off_table_read_orders_newest_generation_first_and_is_deep_enough(self):
        seen = []
        with mock.patch("intelligence.intel_products_job._get", lambda t, q: seen.append((t, q)) or []):
            bpb._from_table()
            bpb._from_current_view()
        self.assertIn("order=as_of.desc&limit=60", seen[0][1])
        self.assertTrue(seen[1][0] == "intelligence_products_current" and "limit=30" in seen[1][1])

    def test_legacy_latest_picks_newest_of_several_generations_on_one_day(self):
        rows = [{"product_key": "forward_watch", "generated_for": "2026-11-25", "as_of": f"2026-11-25T0{i}:00:00+00:00", "n": i}
                for i in (1, 5, 3, 2, 4)]
        self.assertEqual(bpb._latest(rows)[0]["n"], 5)


if __name__ == "__main__":
    unittest.main()


class TestSequenceReadOrder(unittest.TestCase):
    def test_sequence_is_read_before_latest_so_a_racing_commit_cannot_append_a_duplicate(self):
        calls = []

        class Racy(MemGateway):
            def max_generation_seq(self, *a):
                calls.append("seq")
                return super().max_generation_seq(*a)

            def latest_generation(self, *a):
                calls.append("latest")
                return super().latest_generation(*a)

        ph.record_run(Racy(), gen("x"))
        self.assertEqual(calls[:2], ["seq", "latest"])
