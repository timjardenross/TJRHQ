"""Append-only product history: hashing, refresh vs generation, freshness states, flag-off behaviour, brief block, growth."""

import copy
import json
import sys
import threading
import unittest
import urllib.error
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools" / "intelligence" / "analytics"))

from intelligence import brief_products_block as bpb
from intelligence import intel_products_job as job
from intelligence import product_history as ph
from intelligence.reporting_time import MELBOURNE

UTC = timezone.utc
F = ph.Freshness


class MemGateway:
    """In-memory gateway with the same unique key as the migration; thread-safe like a database."""

    def __init__(self, fail_first_insert=False):
        self.gens, self.refreshes = [], []
        self._lock = threading.Lock()
        self.fail_first_insert = fail_first_insert

    def latest_generation(self, product_key, cadence):
        with self._lock:
            rows = [g for g in self.gens if g["product_key"] == product_key and g["cadence"] == cadence]
            if not rows:
                return None
            return copy.deepcopy(max(rows, key=lambda g: (g["as_of"], g["id"])))

    def max_generation_seq(self, product_key, cadence, reporting_date):
        with self._lock:
            return max([g["generation_seq"] for g in self.gens if (g["product_key"], g["cadence"], g["reporting_date"])
                        == (product_key, cadence, reporting_date)] or [0])

    def insert_generation(self, rec):
        with self._lock:
            if self.fail_first_insert:
                self.fail_first_insert = False
                raise ph.UniqueViolation("simulated race")
            k = (rec["product_key"], rec["cadence"], rec["reporting_date"], rec["generation_seq"])
            if any((g["product_key"], g["cadence"], g["reporting_date"], g["generation_seq"]) == k for g in self.gens):
                raise ph.UniqueViolation(str(k))
            row = dict(rec, id=len(self.gens) + 1)
            self.gens.append(row)
            return dict(row)

    def insert_refresh(self, rec):
        with self._lock:
            self.refreshes.append(dict(rec))


def rec(body="body A", as_of=datetime(2026, 11, 24, 19, 22, tzinfo=UTC), key="forward_watch", exceptions=None):
    return {
        "product_key": key, "generated_for": as_of.date().isoformat(), "as_of": as_of.isoformat(),
        "title": "T", "summary": "S", "sections": {"x": [1, 2], "brief_findings": []},
        "exceptions": exceptions or [], "body_md": body,
    }


def gen(r, cadence="daily", legacy=False):
    return ph.build_generation(r, cadence=cadence, legacy_attribution=legacy, watermark={"event_count": 3})


class TestHashAndLineage(unittest.TestCase):
    def test_hash_is_stable_and_content_only(self):
        a, b = rec(), rec(as_of=datetime(2026, 11, 25, 19, 22, tzinfo=UTC))
        self.assertEqual(ph.content_hash(a), ph.content_hash(b))      # as_of is not content
        self.assertNotEqual(ph.content_hash(a), ph.content_hash(rec(body="body B")))
        reordered = dict(a, sections={"brief_findings": [], "x": [1, 2]})
        self.assertEqual(ph.content_hash(a), ph.content_hash(reordered))

    def test_watermark(self):
        rows = [{"event_id": "b", "collected_at": "2026-11-24T01:00:00+00:00"}, {"event_id": "a", "collected_at": "2026-11-24T05:00:00+00:00"}]
        w = ph.input_watermark(rows, 90)
        self.assertEqual((w["event_count"], w["max_collected_at"], w["window_days"]), (2, "2026-11-24T05:00:00+00:00", 90))
        self.assertEqual(w["id_hash"], ph.input_watermark(list(reversed(rows)), 90)["id_hash"])
        self.assertEqual(ph.input_watermark([], 90)["max_collected_at"], None)

    def test_change_summary_facts_only(self):
        prev = rec(exceptions=[{"dedupe_key": "k1"}])
        new = rec(body="other", exceptions=[{"dedupe_key": "k2"}])
        cs = ph.change_summary(prev, new)
        self.assertIn("body_md", cs["changed_fields"])
        self.assertEqual((cs["exception_keys_added"], cs["exception_keys_removed"]), (["k2"], ["k1"]))
        self.assertEqual(ph.change_summary(None, new), {"first_generation": True})


class TestAttribution(unittest.TestCase):
    def test_scheduled_melbourne_morning_gets_melbourne_date_and_cadence(self):
        r = rec(as_of=datetime(2026, 11, 25, 6, 22, tzinfo=MELBOURNE).astimezone(UTC))
        g = gen(r)
        self.assertEqual(r["generated_for"], "2026-11-24")           # legacy UTC key: a day behind
        self.assertEqual((g["reporting_date"], g["generated_for"]), ("2026-11-25", "2026-11-25"))
        self.assertEqual((g["cadence"], g["cadence_basis"], g["reporting_date_basis"]), ("daily", "job", "writer_melbourne"))

    def test_weekly_and_daily_are_distinct_rows_on_monday(self):
        mon = datetime(2026, 11, 23, 6, 20, tzinfo=MELBOURNE).astimezone(UTC)
        mem = MemGateway()
        ph.record_run(mem, gen(rec(body="daily body", as_of=mon), "daily"))
        ph.record_run(mem, gen(rec(body="weekly body", as_of=mon + timedelta(hours=1)), "weekly"))
        self.assertEqual({(g["cadence"], g["reporting_date"], g["generation_seq"]) for g in mem.gens},
                         {("daily", "2026-11-23", 1), ("weekly", "2026-11-23", 1)})

    def test_unspecified_cadence_is_unknown_not_guessed(self):
        g = ph.build_generation(rec(), cadence=None, legacy_attribution=False, watermark=None)
        self.assertEqual((g["cadence"], g["cadence_basis"]), ("unknown", "caller_unspecified"))

    def test_legacy_attribution_keeps_utc_key(self):
        r = rec(as_of=datetime(2026, 11, 24, 19, 22, tzinfo=UTC))
        g = gen(r, legacy=True)
        self.assertEqual((g["reporting_date"], g["generated_for"], g["cadence"]), ("2026-11-24", "2026-11-24", "unknown"))
        self.assertEqual(g["reporting_date_basis"], "legacy_utc_key")


class TestAppendProtocol(unittest.TestCase):
    def test_identical_rerun_adds_refresh_not_generation(self):
        mem = MemGateway()
        r1 = ph.record_run(mem, gen(rec()))
        r2 = ph.record_run(mem, gen(rec(as_of=datetime(2026, 11, 24, 19, 40, tzinfo=UTC))))
        self.assertEqual((r1.outcome, r2.outcome), ("new_generation", "unchanged"))
        self.assertEqual(len(mem.gens), 1)
        self.assertEqual([x["outcome"] for x in mem.refreshes], ["new_generation", "unchanged"])
        self.assertEqual(mem.refreshes[1]["generation_id"], mem.gens[0]["id"])

    def test_changed_content_appends_generation_2_and_generation_1_is_untouched(self):
        mem = MemGateway()
        ph.record_run(mem, gen(rec(body="v1")))
        snapshot = copy.deepcopy(mem.gens[0])
        res = ph.record_run(mem, gen(rec(body="v2", as_of=datetime(2026, 11, 24, 20, 0, tzinfo=UTC))))
        self.assertEqual((res.outcome, res.generation_seq), ("new_generation", 2))
        self.assertEqual(mem.gens[0], snapshot)
        self.assertEqual(mem.gens[1]["supersedes_id"], mem.gens[0]["id"])
        self.assertEqual(mem.gens[1]["change_summary"]["changed_fields"], ["body_md"])

    def test_new_day_starts_at_seq_1_and_links_to_previous(self):
        mem = MemGateway()
        ph.record_run(mem, gen(rec(body="v1")))
        ph.record_run(mem, gen(rec(body="v2", as_of=datetime(2026, 11, 25, 19, 22, tzinfo=UTC))))
        self.assertEqual([(g["reporting_date"], g["generation_seq"]) for g in mem.gens], [("2026-11-25", 1), ("2026-11-26", 1)])
        self.assertEqual(mem.gens[1]["supersedes_id"], mem.gens[0]["id"])

    def test_race_loser_retries_and_records_unchanged(self):
        mem = MemGateway(fail_first_insert=True)
        res = ph.record_run(mem, gen(rec()))
        self.assertEqual((res.outcome, res.attempts), ("new_generation", 2))
        self.assertEqual(len(mem.gens), 1)

    def test_two_threads_same_key_same_content_one_generation(self):
        mem = MemGateway()
        out = []
        barrier = threading.Barrier(4)

        def work():
            g = gen(rec())
            barrier.wait()
            out.append(ph.record_run(mem, g).outcome)

        ts = [threading.Thread(target=work) for _ in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(mem.gens), 1)
        self.assertEqual(sorted(out), ["new_generation"] + ["unchanged"] * 3)
        self.assertEqual(len(mem.refreshes), 4)

    def test_failure_record_has_class_only(self):
        mem = MemGateway()
        ph.record_failure(mem, product_key="forward_watch", cadence="daily",
                          as_of=datetime(2026, 11, 24, 19, 22, tzinfo=UTC), error=ValueError("secret detail"))
        self.assertEqual(mem.refreshes[0]["error_class"], "ValueError")
        self.assertNotIn("secret", json.dumps(mem.refreshes))
        self.assertEqual(mem.refreshes[0]["outcome"], "failed")


def mel(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=MELBOURNE)


class TestFreshness(unittest.TestCase):
    def test_unavailable_without_refresh(self):
        self.assertEqual(ph.freshness(mel(2026, 11, 25, 8, 0), "daily", None).state, F.UNAVAILABLE)

    def test_daily_current_after_todays_run(self):
        self.assertEqual(ph.freshness(mel(2026, 11, 25, 8, 0), "daily", mel(2026, 11, 25, 6, 22)).state, F.CURRENT)

    def test_daily_current_before_deadline_even_if_run_not_yet_done(self):
        # deadline is slot start + 25 min = 06:45 (proposal), so it falls BEFORE the 07:00 brief
        r = ph.freshness(mel(2026, 11, 25, 6, 40), "daily", mel(2026, 11, 24, 6, 22))
        self.assertEqual(r.state, F.CURRENT)
        self.assertEqual(ph.freshness(mel(2026, 11, 25, 6, 50), "daily", mel(2026, 11, 24, 6, 22)).state, F.REFRESH_OVERDUE)

    def test_daily_overdue_within_usable_age(self):
        # 25 h old is inside the 36 h maximum but today's run is missing after its deadline
        r = ph.freshness(mel(2026, 11, 25, 7, 30), "daily", mel(2026, 11, 24, 6, 22))
        self.assertEqual(r.state, F.REFRESH_OVERDUE)
        self.assertLess(r.age_hours, 36)

    def test_daily_stale_beyond_36h(self):
        r = ph.freshness(mel(2026, 11, 26, 8, 0), "daily", mel(2026, 11, 24, 6, 22))
        self.assertEqual(r.state, F.STALE)

    def test_daily_boundary_exactly_36h_is_not_stale(self):
        r = ph.freshness(mel(2026, 11, 25, 18, 22), "daily", mel(2026, 11, 24, 6, 22))
        self.assertNotEqual(r.state, F.STALE)

    def test_weekly(self):
        sched = mel(2026, 11, 23, 7, 22)
        self.assertEqual(ph.freshness(mel(2026, 11, 27, 9, 0), "weekly", sched).state, F.CURRENT)
        self.assertEqual(ph.freshness(mel(2026, 11, 30, 7, 30), "weekly", sched).state, F.CURRENT)   # next run not yet due
        self.assertEqual(ph.freshness(mel(2026, 11, 30, 8, 30), "weekly", sched).state, F.REFRESH_OVERDUE)
        self.assertEqual(ph.freshness(mel(2026, 12, 2, 8, 0), "weekly", sched).state, F.STALE)       # > 8 days

    def test_identical_content_refresh_counts_as_fresh(self):
        # content last changed days ago, but the latest successful refresh was this morning
        content_as_of, last_refresh = mel(2026, 11, 20, 6, 22), mel(2026, 11, 25, 6, 21)
        self.assertEqual(ph.freshness(mel(2026, 11, 25, 8, 0), "daily", last_refresh).state, F.CURRENT)
        self.assertEqual(ph.freshness(mel(2026, 11, 25, 8, 0), "daily", content_as_of).state, F.STALE)

    def test_unknown_cadence_never_overdue(self):
        r = ph.freshness(mel(2026, 11, 25, 7, 30), "unknown", mel(2026, 11, 24, 6, 22))
        self.assertEqual(r.state, F.CURRENT)
        self.assertEqual(ph.freshness(mel(2026, 11, 26, 8, 0), None, mel(2026, 11, 24, 6, 22)).state, F.STALE)

    def test_dst_change_day_slot(self):
        # Sunday 4 Oct 2026 (AEDT starts): 07:30 local with no run today is overdue; slot start is 06:20 +11
        r = ph.freshness(mel(2026, 10, 4, 7, 30), "daily", mel(2026, 10, 3, 6, 22))
        self.assertEqual(r.state, F.REFRESH_OVERDUE)
        slot = ph.latest_slot(mel(2026, 10, 4, 7, 30), "daily")
        self.assertEqual(slot[0].astimezone(UTC), datetime(2026, 10, 3, 19, 20, tzinfo=UTC))


class TestFlagOffJob(unittest.TestCase):
    AS_OF = datetime(2026, 11, 22, 20, 20, tzinfo=UTC)   # Monday 23 Nov 07:20 AEDT; UTC says Sunday W47

    def _run(self, env, writer):
        with mock.patch.dict("os.environ", env, clear=True):
            return job.run(self.AS_OF, getter=lambda *a: [], writer=writer, cadence="weekly", gateway=MemGateway())

    def test_flag_off_writes_exactly_the_legacy_record_shape(self):
        written = []
        self._run({"INTEL_PRODUCTS_ENABLED": "1"}, written.append)
        self.assertEqual(len(written), 3)
        for w in written:
            self.assertEqual(set(w), {"product_key", "generated_for", "as_of", "title", "summary", "sections", "exceptions", "body_md"})
            self.assertEqual(w["generated_for"], "2026-11-22")      # unchanged legacy UTC key
        # also: the legacy writer is what is called, with the legacy on_conflict target
        self.assertIn("product_key,generated_for", __import__("inspect").getsource(job._upsert))

    def test_flag_off_does_not_touch_history_tables_when_upsert_works(self):
        mem = MemGateway()
        with mock.patch.dict("os.environ", {"INTEL_PRODUCTS_ENABLED": "1"}, clear=True):
            job.run(self.AS_OF, getter=lambda *a: [], writer=lambda r: None, gateway=mem)
        self.assertEqual((mem.gens, mem.refreshes), ([], []))

    def test_flag_off_after_key_swap_appends_with_legacy_attribution(self):
        err = urllib.error.HTTPError("u", 400, "bad", {}, BytesIO(b'{"code":"42P10","message":"no unique constraint"}'))
        calls = []

        def writer(r):
            calls.append(r)
            raise err

        mem = MemGateway()
        with mock.patch.dict("os.environ", {"INTEL_PRODUCTS_ENABLED": "1"}, clear=True):
            job.run(self.AS_OF, getter=lambda *a: [], writer=writer, gateway=mem)
        self.assertEqual(len(calls), 1)                              # probed once, then append-only storage
        self.assertEqual(len(mem.gens), 3)
        self.assertTrue(all(g["reporting_date_basis"] == "legacy_utc_key" and g["cadence"] == "unknown" for g in mem.gens))
        self.assertTrue(all(g["generated_for"] == "2026-11-22" for g in mem.gens))

    def test_other_write_errors_still_propagate_flag_off(self):
        err = urllib.error.HTTPError("u", 500, "boom", {}, BytesIO(b"x"))
        with self.assertRaises(urllib.error.HTTPError), mock.patch.dict("os.environ", {"INTEL_PRODUCTS_ENABLED": "1"}, clear=True):
            job.run(self.AS_OF, getter=lambda *a: [], writer=mock.Mock(side_effect=err), gateway=MemGateway())

    def test_flag_on_uses_melbourne_date_cadence_and_week_key(self):
        mem = MemGateway()
        env = {"INTEL_PRODUCTS_ENABLED": "1", "INTEL_PRODUCTS_APPEND_V1": "1"}
        with mock.patch.dict("os.environ", env, clear=True):
            products = job.run(self.AS_OF, getter=lambda *a: [], writer=lambda r: 1 / 0, cadence="weekly", gateway=mem)
        self.assertEqual({(g["reporting_date"], g["cadence"]) for g in mem.gens}, {("2026-11-23", "weekly")})
        self.assertEqual(len(mem.refreshes), 3)
        keys = [e["dedupe_key"] for p in products for e in p["exceptions"]]
        self.assertFalse([k for k in keys if k.endswith("2026-W47")])

    def test_rekey_iso_week(self):
        prods = [{"exceptions": [{"dedupe_key": "systemic:concentration:x:2026-W47"}, {"dedupe_key": "forward-watch:e1:2026-11-30"}]}]
        job._rekey_iso_week(prods, self.AS_OF)
        self.assertEqual([e["dedupe_key"] for e in prods[0]["exceptions"]],
                         ["systemic:concentration:x:2026-W48", "forward-watch:e1:2026-11-30"])

    def test_failure_is_recorded_then_raised(self):
        class Boom(MemGateway):
            def insert_generation(self, rec):
                raise RuntimeError("db down")
        mem = Boom()
        env = {"INTEL_PRODUCTS_ENABLED": "1", "INTEL_PRODUCTS_APPEND_V1": "1"}
        with self.assertRaises(RuntimeError), mock.patch.dict("os.environ", env, clear=True):
            job.run(self.AS_OF, getter=lambda *a: [], gateway=mem, cadence="daily")
        self.assertEqual([r["outcome"] for r in mem.refreshes], ["failed"])


class TestBriefBlock(unittest.TestCase):
    NOW = mel(2026, 11, 25, 7, 5).astimezone(UTC)

    def row(self, key="forward_watch", refreshed=None, cadence="daily", finding="Item due soon", as_of=None):
        refreshed = refreshed or mel(2026, 11, 25, 6, 22)
        return {"product_key": key, "cadence": cadence, "generated_for": "2026-11-25", "as_of": (as_of or refreshed).isoformat(),
                "last_refresh_as_of": refreshed.isoformat(),
                "sections": {"brief_findings": [finding], "coverage_note": f"note {key}"}, "exceptions": []}

    def lines(self, rows, env=None, now=None):
        env = {"INTEL_PRODUCTS_IN_BRIEF": "1", "INTEL_PRODUCTS_APPEND_V1": "1", **(env or {})}
        with mock.patch.dict("os.environ", env, clear=True):
            return bpb.brief_lines(reader=lambda: rows, now=now or self.NOW)

    def test_current_lines_carry_asof_date_and_age(self):
        out = self.lines([self.row()])
        self.assertIn("- Forward watch [as of 25 Nov 06:22 AEDT, <1 h old]: Item due soon", out)
        out2 = self.lines([self.row()], now=mel(2026, 11, 25, 9, 22).astimezone(UTC))
        self.assertIn("- Forward watch [as of 25 Nov 06:22 AEDT, 3 h old]: Item due soon", out2)

    def test_overdue_is_labelled_and_stale_is_status_only(self):
        late = mel(2026, 11, 25, 7, 40).astimezone(UTC)
        out = self.lines([self.row(refreshed=mel(2026, 11, 24, 6, 22))], now=late)
        self.assertTrue(any("REFRESH OVERDUE, as of 24 Nov 06:22 AEDT" in l for l in out))
        old = self.lines([self.row(refreshed=mel(2026, 11, 20, 6, 22))])
        self.assertFalse(any("Item due soon" in l for l in old))
        self.assertTrue(any(l.startswith("- Status: Forward watch: Stale, last assessed 20 Nov 06:22 AEDT") for l in old))

    def test_identical_refresh_keeps_product_current_but_shows_content_age_only_via_refresh(self):
        r = self.row(refreshed=mel(2026, 11, 25, 6, 22), as_of=mel(2026, 11, 20, 6, 22))
        out = self.lines([r])
        self.assertTrue(any("[as of 25 Nov 06:22 AEDT" in l for l in out))

    def test_cadences_pick_most_recent_refresh(self):
        weekly = self.row(refreshed=mel(2026, 11, 23, 7, 22), cadence="weekly", finding="WEEKLY")
        daily = self.row(refreshed=mel(2026, 11, 25, 6, 22), cadence="daily", finding="DAILY")
        out = "\n".join(self.lines([weekly, daily]))
        self.assertIn("DAILY", out)
        self.assertNotIn("WEEKLY", out)

    def test_unreadable_store_is_explicit_not_silent(self):
        def boom():
            raise RuntimeError("down")
        with mock.patch.dict("os.environ", {"INTEL_PRODUCTS_IN_BRIEF": "1", "INTEL_PRODUCTS_APPEND_V1": "1"}, clear=True):
            out = bpb.brief_lines(reader=boom, now=self.NOW)
        self.assertEqual(out[1], "- Status: Unavailable (stored products could not be read)")

    def test_missing_product_reported_unavailable_when_others_exist(self):
        out = self.lines([self.row()])
        self.assertTrue(any("Recurring provider: Unavailable" in l for l in out))

    def test_flag_off_uses_legacy_path_unchanged(self):
        rows = [{"product_key": "forward_watch", "generated_for": "2026-11-24", "sections": {"brief_findings": ["F"], "coverage_note": "n"}, "exceptions": []}]
        env = {"INTEL_PRODUCTS_IN_BRIEF": "1"}
        with mock.patch.dict("os.environ", env, clear=True):
            out = bpb.brief_lines(date(2026, 11, 25), reader=lambda: rows)
        self.assertEqual(out, ["INTELLIGENCE PRODUCTS", "- Forward watch: F", "Coverage: n", ""])

    def test_legacy_latest_prefers_latest_asof_within_a_day(self):
        rows = [{"product_key": "forward_watch", "generated_for": "2026-11-25", "as_of": "2026-11-25T01:00:00+00:00"},
                {"product_key": "forward_watch", "generated_for": "2026-11-25", "as_of": "2026-11-25T05:00:00+00:00"}]
        self.assertEqual(bpb._latest(rows)[0]["as_of"], "2026-11-25T05:00:00+00:00")


class TestGrowth(unittest.TestCase):
    def test_report(self):
        gens = [rec(body="x" * 1000, as_of=datetime(2026, 11, 24, 0, 0, tzinfo=UTC) + timedelta(days=i)) for i in range(3)]
        rep = ph.storage_growth_report(gens, refresh_count=9)
        self.assertEqual((rep.generations, rep.refreshes), (3, 9))
        self.assertEqual(rep.by_product["forward_watch"]["generations"], 3)
        self.assertGreater(rep.projected_bytes_per_year, rep.content_bytes)
        self.assertEqual(ph.storage_growth_report([]).projected_bytes_per_year, 0)


class TestPeriodFlag(unittest.TestCase):
    def test_period_datetime(self):
        from intelligence.reporting_time import period_datetime
        ts = datetime(2026, 11, 24, 21, 0, tzinfo=UTC)
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIs(period_datetime(ts), ts)
        with mock.patch.dict("os.environ", {"INTEL_PRODUCTS_APPEND_V1": "1"}, clear=True):
            self.assertEqual(period_datetime(ts).strftime("%Y-%m-%d"), "2026-11-25")

    def test_notifier_prefers_melbourne_cycle_date_only_when_flag_on(self):
        from intelligence import brief_published_notifier as n
        sent = []
        row = {"period_end": "2026-11-24", "morning_cycle_id": "2026-11-25", "overall_risk": "low"}
        with mock.patch.object(n, "send_email", side_effect=lambda **kw: sent.append(kw["subject"]) or True):
            with mock.patch.dict("os.environ", {}, clear=True):
                n.notify_published(row)
            with mock.patch.dict("os.environ", {"INTEL_PRODUCTS_APPEND_V1": "1"}, clear=True):
                n.notify_published(row)
        self.assertTrue(sent[0].endswith("2026-11-24") and sent[1].endswith("2026-11-25"))


if __name__ == "__main__":
    unittest.main()
