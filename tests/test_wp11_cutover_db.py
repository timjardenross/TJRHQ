"""WP11: integrated cut-over, skew and rollback validation for the history-preserving products migration (0263a/b/r) and the
delivery-attempt records (0264), on a replica of production, with the real Python writer/readers and an emulated PostgREST.

SKIPPED unless INTEL_TEST_PG_CONTAINER names a disposable Postgres 17 container (psql reachable through `docker exec`, roles anon /
authenticated / service_role present) AND INTEL_PRODUCTS_EVIDENCE_DIR points at the preserved product rows
(`intelligence_products_20261124_25.raw.json`, read only). Creates and drops its own databases `wp11_*` (and one login role
`wp11_plain`); never touches anything else, never talks to production.

Run:  INTEL_TEST_PG_CONTAINER=<isolated-test-container> INTEL_PRODUCTS_EVIDENCE_DIR=<dir> INTEL_WP11_MATRIX_OUT=<file.json> \
      python -m pytest tests/test_wp11_cutover_db.py -q
Runtime: about 7 minutes (395 s measured for 41 tests on a moderately loaded 8-core host; 880 s at load average 17). It uses persistent psql
connections and ~40 database clones of one template. The scale test is sized by INTEL_WP11_SCALE_ROWS (default 6000 rows).
The results matrix (every sequence x writer x reader outcome) is written to INTEL_WP11_MATRIX_OUT (default: system temp dir).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import pytest

from tests import (
    wp11_harness as H,
)
from tests.wp11_harness import (
    D1,
    D1M,
    D2,
    D2M,
    D3,
    D3M,
    D4,
    D5,
    D5M,
    DRAFTS,
    MIG,
    PROD_ACL,
    PROD_SNAPSHOT,
    W1,
    PgError,
    Scn,
    iso,
    jlit,
    lit,
    psql,
    psql_once,
    sha,
)

pytestmark = pytest.mark.timeout(3600)
RAW = None
ROLE = "wp11_plain"


def setUpModule():
    global RAW
    if not (H.CONTAINER and H.EVID):
        raise unittest.SkipTest("needs INTEL_TEST_PG_CONTAINER and INTEL_PRODUCTS_EVIDENCE_DIR")
    RAW = H.build_template()
    subprocess.run(["docker", "exec", H.CONTAINER, "psql", "-U", "postgres", "-c",
                    f"do $$ begin if not exists (select 1 from pg_roles where rolname='{ROLE}') then create role {ROLE} login; end if; end $$"],
                   check=True, capture_output=True)


def tearDownModule():
    out = os.environ.get("INTEL_WP11_MATRIX_OUT") or str(Path(tempfile.gettempdir()) / "wp11_cutover_matrix.json")
    Path(out).write_text(json.dumps(H.MATRIX, indent=1, default=str))
    for db in H._DBS + [H.TPL]:
        H.drop_db(db)
    subprocess.run(["docker", "exec", H.CONTAINER, "psql", "-U", "postgres", "-c", f"drop role if exists {ROLE}"], capture_output=True, check=False)


def ok(res):
    return res is None


# ======================================================================================================================
class TestReplicaFidelity(unittest.TestCase):
    """The replica must equal what production's catalogs said on 2026-11-25 (embedded snapshot), or nothing below means anything."""

    def test_products_table_matches_production_catalog(self):
        s = Scn("fidelity", RAW)
        snap = H.catalog_snapshot(s.db, "intelligence_products")
        exp = PROD_SNAPSHOT["intelligence_products"]
        got_cols = [c.rsplit(" ", 0)[0] for c in snap["columns"]]
        norm = lambda c: c.replace("YES", "").replace("  ", " ").strip()
        want = [c.replace(" NO", " NO") for c in exp["columns"]]
        self.assertEqual([norm(c) for c in got_cols], [norm(c) for c in want])
        self.assertEqual(snap["constraints"], sorted(exp["constraints"]))
        self.assertEqual(snap["indexes"], exp["indexes"])
        self.assertEqual(snap["policies"], ["intelligence_products_read SELECT {authenticated} true"])
        self.assertEqual(set(snap["acl"].strip("{}").split(",")), set(PROD_ACL.strip("{}").split(",")))
        self.assertEqual(s.q("select relrowsecurity::text||relforcerowsecurity::text from pg_class where oid='public.intelligence_products'::regclass"), "truefalse")
        self.assertEqual(s.q("select count(*) from intelligence_products"), "6")
        self.assertFalse(any(s.shape().values()), "nothing of 0263/0264 may exist yet")
        self.assertEqual(s.q("select count(*) from information_schema.columns where table_name in ('captains_daily_briefs','intelligence_briefs') "
                             "and column_name in ('production_status','telegram_status')"), "0")

    def test_brief_tables_match_production_catalog(self):
        s = Scn("fidelity_b", RAW)
        for t, acl in (("captains_daily_briefs", PROD_ACL), ("intelligence_briefs", PROD_ACL)):
            snap = H.catalog_snapshot(s.db, t)
            self.assertEqual(set(snap["acl"].strip("{}").split(",")), set(acl.strip("{}").split(",")), t)
        self.assertEqual(s.q("select count(*) from information_schema.columns where table_name='captains_daily_briefs'"), "10")
        self.assertEqual(s.q("select count(*) from information_schema.columns where table_name='intelligence_briefs'"), "33")

    def test_emulator_error_shapes_the_readers_depend_on(self):
        """Missing relation -> the portal falls back (PGRST205 / 'schema cache'); permission denied -> it must throw, not fall back."""
        s = Scn("fidelity_e", RAW)
        self.assertIsInstance(H.new_portal(s.db), dict)      # view missing: falls back to the base table
        s.q("revoke select on public.intelligence_products from authenticated")
        self.assertEqual(H.old_portal(s.db), "throws:42501")
        self.assertEqual(H.new_portal(s.db), "throws:42501")      # view missing -> base denied -> throws (never silently empty)
        s.q("drop table public.intelligence_products cascade")
        self.assertEqual(H.old_portal(s.db), "unavailable")
        self.assertEqual(H.new_portal(s.db), "unavailable")

    def test_old_writer_is_byte_identical_to_the_production_baseline(self):
        base = "53085dde8"
        try:
            old = subprocess.run(["git", "show", f"{base}:intelligence/intel_products_job.py"], capture_output=True, text=True, check=True,
                                 cwd=H.ROOT).stdout
        except Exception:  # noqa: BLE001
            self.skipTest("baseline commit not available in this checkout")
        import inspect

        def body(src, name):
            i = src.index(f"def {name}(")
            j = src.index("\ndef ", i + 1)
            return src[i:j]
        for fn in ("_upsert", "to_records"):
            self.assertEqual(body(old, fn).strip(), inspect.getsource(getattr(H.job, fn)).strip(), fn)
        # the flag-OFF persistence loop is the same single writer(rec) call per product
        self.assertIn("writer(rec)", old)


# ======================================================================================================================
class TestRecommendedOrder(unittest.TestCase):
    """Apply order of the Batch 1 durable-state engineering report section 3 with the recommended reader-first deployment, every reader checked at every step.
    The old reader is checked throughout to show what an un-switched portal sees."""

    def test_full_sequence(self):
        s = Scn("order", RAW)
        # R0 baseline: production today
        s.check("R0 baseline", old_portal="ok", new_portal="ok", history_lost=0)
        # reader first: new portal deployed while the view does not exist -> falls back, same answer
        self.assertIsInstance(H.new_portal(s.db), dict)
        s.apply("0264")
        s.check("R2 after 0264 (delivery)", old_portal="ok", new_portal="ok", history_lost=0)
        s.apply("0263a")
        s.check("R3 after 0263a", old_portal="ok", new_portal="ok", history_lost=0)
        # the 26 Nov 06:20 run of the OLD writer collides with the preserved 25 Nov key; the database archives instead of destroying
        r = s.write("old", D1, "old-D1")
        row = s.check("R3b old writer 26 Nov 06:20 on 0263a", writers={"old": r}, old_portal="ok", new_portal="ok", history_lost=0)
        self.assertIsNone(r)
        self.assertEqual(s.q("select count(*) from intelligence_products_revisions where archive_reason='update'"), "3")
        # code deploy, flag OFF: the original upsert; a same-day manual rerun archives
        a, b = s.write("new_off", D2, "off-D2"), s.write("new_off", D2M, "off-D2M")
        s.check("R4 code deployed flag OFF", writers={"scheduled": a, "manual": b}, old_portal="ok", new_portal="ok", history_lost=0)
        self.assertEqual((a, b), (None, None))
        # flag ON: Melbourne date key; same-day collision takes the archive-overwrite path; Monday weekly after daily
        a, b = s.write("new_on", D3, "on-D3"), s.write("new_on", D3M, "on-D3M")
        c, d = s.write("new_on", D4, "on-D4"), s.write("new_on", W1, "on-W1", cadence="weekly")
        s.check("R5 flag ON (daily, manual rerun, Monday daily then weekly)", writers={"r": [a, b, c, d]},
                old_portal="ok", new_portal="ok", history_lost=0)
        self.assertEqual((a, b, c, d), (None, None, None, None))
        rows = s.q("select string_agg(cadence||':'||source, ',' order by cadence, source) from intelligence_products_current where product_key='forward_watch'")
        self.assertEqual(rows, "daily:archived,unknown:live,weekly:live")     # daily assessment still visible next to the weekly one
        seen = H.brief_block_readers(s, iso(2026, 11, 29, 21, 0))
        self.assertEqual(seen["off"], s.o.newest_summary())
        self.assertIsInstance(seen["on"], dict)
        # B: optional contract. Old portal is now ambiguous (several rows per generated_for); the new one is right.
        s.apply("0263b")
        row = s.check("R7 after 0263b", new_portal="ok", history_lost=0)
        self.assertTrue(row["old_portal"].startswith("WRONG"), f"old reader must be shown to be unsafe after Part B: {row}")
        before = int(s.q("select count(*) from intelligence_products"))
        a, b = s.write("new_on", D5, "on-D5"), s.write("new_on", D5M, "on-D5M")
        e = s.write("new_off", iso(2026, 12, 1, 19, 20), "off-D6")
        self.assertEqual((a, b, e), (None, None, None))            # new writer: ON appends, OFF falls back to appending
        n_after_new = int(s.q("select count(*) from intelligence_products"))
        self.assertGreater(n_after_new, before)
        f = s.write("old", iso(2026, 12, 2, 19, 20), "old-D7")
        self.assertEqual(f, "HTTP400", "the original writer must be refused (42P10), not silently overwrite")
        self.assertEqual(int(s.q("select count(*) from intelligence_products")), n_after_new, "refused old writer changed nothing")
        s.check("R7b writers after 0263b", writers={"new_on": [a, b], "new_off": e, "old": f}, new_portal="ok", history_lost=0)
        # R: emergency rollback of B keeps every generation, original writer works again
        s.apply("0263r")
        s.check("R8 after 0263r", old_portal="ok", new_portal="ok", history_lost=0)
        g = s.write("old", iso(2026, 12, 3, 19, 20), "old-D8")
        self.assertIsNone(g)
        s.check("R8b old writer after rollback", writers={"old": g}, old_portal="ok", new_portal="ok", history_lost=0)
        # re-contract after rollback works
        s.apply("0263b")
        s.check("R9 re-contract", new_portal="ok", history_lost=0)
        # the six preserved bodies are still byte-exact somewhere
        shas = H.all_body_shas(s.db)
        for line in (Path(H.EVID) / "body_hashes.tsv").read_text().splitlines():
            self.assertIn(line.split("\t")[3], shas)


# ======================================================================================================================
# Skew matrix: every schema stage x every writer x every reader (frozen expectations; WRONG = documented hazard)
# ======================================================================================================================
def _expect_stage(test, stage, rows, table):
    """table: {writer: (results, old_portal, new_portal, history_lost, row_count)}; old_portal may be 'ANY' (tie order is undefined)."""
    for row in rows:
        results, old_p, new_p, lost, n = table[row["writer"]]
        where = f"{stage}|{row['writer']}"
        test.assertEqual(row["writers"]["results"], results, where)
        test.assertEqual(row["new_portal"], new_p, where)
        if old_p == "ANY":
            test.assertTrue(row["old_portal"] == "ok" or row["old_portal"].startswith("WRONG"), where)
        else:
            test.assertEqual(row["old_portal"], old_p, where)
        test.assertEqual(row["history_lost"], lost, where)
        test.assertEqual(row["row_count"], n, where)


class TestSkewMatrix(unittest.TestCase):
    """Deployment skew between Python services (old writer / new writer flag OFF / flag ON) and the portal (old / new reader) at every
    schema stage. history_lost counts bodies ever acknowledged (including the six preserved rows) that no longer exist anywhere."""

    def test_stage_base_production_today(self):
        # nothing applied: the old writer overwrites (history lost: this is the defect being fixed), flag ON fails closed
        _, rows = H.cross_stage(RAW, "base")
        _expect_stage(self, "base", rows, {
            "old": ([None, None], "ok", "ok", 6, 6), "new_off": ([None, None], "ok", "ok", 9, 9),
            "new_on_daily": (["HTTP400", "HTTP400"], "ok", "ok", 9, 9), "new_on_weekly": (["HTTP400", "HTTP400"], "ok", "ok", 9, 9)})

    def test_stage_0264_delivery_only_changes_nothing_for_products(self):
        _, rows = H.cross_stage(RAW, "0264")
        _expect_stage(self, "0264", rows, {
            "old": ([None, None], "ok", "ok", 6, 6), "new_off": ([None, None], "ok", "ok", 9, 9),
            "new_on_daily": (["HTTP400", "HTTP400"], "ok", "ok", 9, 9), "new_on_weekly": (["HTTP400", "HTTP400"], "ok", "ok", 9, 9)})

    def test_stage_A_expand_is_safe_for_every_writer_and_reader(self):
        _, rows = H.cross_stage(RAW, "A")
        _expect_stage(self, "A", rows, {
            "old": ([None, None], "ok", "ok", 0, 6), "new_off": ([None, None], "ok", "ok", 0, 9),
            "new_on_daily": ([None, None], "ok", "ok", 0, 12), "new_on_weekly": ([None, None], "ok", "ok", 0, 15)})

    def test_stage_AB_contract_old_writer_refused_old_reader_unsafe(self):
        _s, rows = H.cross_stage(RAW, "A+B")
        _expect_stage(self, "A+B", rows, {
            "old": (["HTTP400", "HTTP400"], "ANY", "ok", 0, 6), "new_off": ([None, None], "ANY", "ok", 0, 12),
            "new_on_daily": ([None, None], "ANY", "ok", 0, 18), "new_on_weekly": ([None, None], "ANY", "ok", 0, 24)})
        self.assertTrue(any(r["old_portal"].startswith("WRONG") for r in rows),
                        "the un-switched portal must be observed showing a non-newest generation after Part B")

    def test_stage_ABR_rollback_restores_every_actor(self):
        _, rows = H.cross_stage(RAW, "A+B+R")
        _expect_stage(self, "A+B+R", rows, {
            "old": ([None, None], "ok", "ok", 0, 6), "new_off": ([None, None], "ok", "ok", 0, 9),
            "new_on_daily": ([None, None], "ok", "ok", 0, 12), "new_on_weekly": ([None, None], "ok", "ok", 0, 15)})


# ======================================================================================================================
class TestGuards(unittest.TestCase):
    """The writer must refuse or degrade safely whenever the uniqueness constraints it needs are not there."""

    def test_flag_on_before_expand_fails_closed_and_recovers_after_expand(self):
        s = Scn("g_flagfirst", RAW)
        n0 = s.q("select count(*) from intelligence_products")
        res = s.write("new_on", D3, "t")
        self.assertEqual(res, "HTTP400")                           # missing columns: fails at the first read, nothing written
        self.assertEqual(s.q("select count(*) from intelligence_products"), n0)
        s.check("flag ON before 0263a", old_portal="ok", new_portal="ok", history_lost=0)
        s.apply("0263a")
        self.assertIsNone(s.write("new_on", D3, "t"))
        s.check("flag ON after 0263a", old_portal="ok", new_portal="ok", history_lost=0)

    def test_contract_before_expand_is_refused(self):
        s = Scn("g_bfirst", RAW)
        self.assertEqual(s.apply("0263b", expect="42P01").sqlstate, "42P01")
        self.assertEqual(s.apply("0263r", expect="42P17").sqlstate, "42P17")      # nothing to roll back
        self.assertFalse(any(s.shape().values()))

    def test_expand_twice_is_idempotent_and_refused_after_contract(self):
        s = Scn("g_twice", RAW)
        s.apply("0263a")
        before = (s.q("select count(*) from intelligence_products"), s.q("select md5(string_agg(body_md, '' order by product_key, generated_for)) from intelligence_products"))
        s.apply("0263a")
        after = (s.q("select count(*) from intelligence_products"), s.q("select md5(string_agg(body_md, '' order by product_key, generated_for)) from intelligence_products"))
        self.assertEqual(before, after)
        self.assertEqual(s.q("select count(*) from intelligence_products_revisions"), "0")
        s.check("A twice", old_portal="ok", new_portal="ok", history_lost=0)
        s.write("new_on", D3, "t1")
        s.apply("0263b")
        err = s.apply("0263a", expect="42P17")                       # added guard: no mixing of expand triggers with the contract
        self.assertIn("0263b is already applied", err.text)
        self.assertEqual(s.q("select count(*) from pg_trigger where tgname='intelligence_products_archive_trg'"), "0")

    def test_old_writer_on_contracted_table_changes_nothing(self):
        s = Scn("g_oldafterB", RAW)
        s.apply("0263a")
        s.apply("0263b")
        snap = s.q("select md5(string_agg(body_md||id::text, '' order by id)) from intelligence_products")
        self.assertEqual(s.write("old", D3, "t"), "HTTP400")
        self.assertEqual(s.q("select md5(string_agg(body_md||id::text, '' order by id)) from intelligence_products"), snap)

    def test_flag_toggle_on_then_off_within_one_melbourne_day(self):
        """Rollback of the flag after a flag-ON run: ON keys by Melbourne date, OFF by UTC date (one day earlier at 06:20), so an old
        reader ordering by generated_for keeps showing the older ON row. Readers that order by as_of (view, brief block) are right."""
        s = Scn("g_toggle", RAW)
        s.apply("0263a")
        a = s.write("new_on", D3, "on")             # 28 Nov 06:20 -> generated_for 2026-11-28
        b = s.write("new_off", D3M, "off")          # 28 Nov 09:00 -> generated_for = UTC date 2026-11-27
        row = s.check("toggle ON then OFF same Melbourne day", writers={"on": a, "off": b}, new_portal="ok", history_lost=0)
        MATRIX_NOTE = row["old_portal"]
        self.assertEqual((a, b), (None, None))
        self.assertTrue(MATRIX_NOTE.startswith("WRONG"), "documented hazard: old reader shows the older ON generation after an OFF rerun")
        seen = H.brief_block_readers(s, iso(2026, 11, 27, 23, 0))
        self.assertEqual(seen["off"], s.o.newest_summary())


# ======================================================================================================================
def _fingerprint(s):
    return s.q("select md5(coalesce((select string_agg(c.relname||c.relkind::text||coalesce(c.relacl::text,''), ',' order by c.relname) from pg_class c "
               "where c.relnamespace='public'::regnamespace),'') || coalesce((select string_agg(table_name||column_name||data_type, ',' order by table_name, column_name) "
               "from information_schema.columns where table_schema='public'),'') || coalesce((select string_agg(conname, ',' order by conname) from pg_constraint "
               "where connamespace='public'::regnamespace),'') || coalesce((select string_agg(tgname, ',' order by tgname) from pg_trigger where not tgisinternal),'') "
               "|| coalesce((select string_agg(proname, ',' order by proname) from pg_proc where pronamespace='public'::regnamespace),'') "
               "|| coalesce((select string_agg(policyname||tablename, ',' order by policyname) from pg_policies),'') "
               "|| coalesce((select md5(definition) from pg_views where schemaname='public' and viewname='intelligence_products_current'),''))")


def _inject_failure(text):
    import re
    idx = [m.start() for m in re.finditer(r"^commit;", text, re.MULTILINE)][-1]
    return text[:idx] + "select 1/0;\n" + text[idx:]


class TestPartialFailure(unittest.TestCase):
    """A failure at the very end of each migration rolls everything back (one transaction) and a re-run completes."""

    def _run(self, mig, pre, seedwrites):
        s = Scn(f"pf_{mig}", RAW)
        for m in pre:
            s.apply(m)
        for kind, t, tag in seedwrites:
            self.assertIsNone(s.write(kind, t, tag))
        fp = _fingerprint(s)
        data = s.q("select count(*)||':'||md5(string_agg(body_md, '' order by product_key, generated_for, as_of)) from intelligence_products")
        err = s.apply(mig, sql=_inject_failure((DRAFTS / MIG[mig]).read_text()), expect="22012")
        self.assertEqual(err.sqlstate, "22012")
        self.assertEqual(_fingerprint(s), fp, f"{mig}: failed run left schema changes behind")
        self.assertEqual(s.q("select count(*)||':'||md5(string_agg(body_md, '' order by product_key, generated_for, as_of)) from intelligence_products"), data)
        return s

    def test_0264_partial_failure(self):
        s = self._run("0264", [], [("old", D1, "p1")])
        self.assertFalse(s.shape()["attempts"])
        self.assertIsNone(s.write("old", D1M, "p2"))                # production writers unaffected
        s.apply("0264")
        self.assertTrue(s.shape()["attempts"])

    def test_0263a_partial_failure_old_writer_keeps_working(self):
        s = self._run("0263a", [], [("old", D1, "p1")])
        self.assertFalse(s.shape()["a"])
        self.assertIsNone(s.write("old", D1M, "p2"))
        self.assertEqual(s.write("new_on", D2, "p3"), "HTTP400")    # flag ON still fails closed on the unmigrated table
        s.apply("0263a")
        s.check("A re-run after failure", old_portal="ok", new_portal="ok")

    def test_0263b_partial_failure_keeps_the_original_key_and_writers(self):
        s = self._run("0263b", ["0263a"], [("new_on", D3, "p1"), ("new_on", D3M, "p2")])
        self.assertEqual(s.q("select pg_get_constraintdef(oid) from pg_constraint where conname='intelligence_products_pkey'"), "PRIMARY KEY (product_key, generated_for)")
        self.assertIsNone(s.write("old", D4, "p3"))                  # original writer still valid after the aborted contract
        s.apply("0263b")
        s.check("B re-run after failure", new_portal="ok", history_lost=0)

    def test_0263r_partial_failure_keeps_contracted_state_and_history(self):
        s = self._run("0263r", ["0263a", "0263b"], [("new_on", D3, "p1"), ("new_on", D3M, "p2")])
        self.assertEqual(s.q("select pg_get_constraintdef(oid) from pg_constraint where conname='intelligence_products_pkey'"), "PRIMARY KEY (id)")
        s.apply("0263r")
        s.check("R re-run after failure", old_portal="ok", new_portal="ok", history_lost=0)


# ======================================================================================================================
def hold(db, body_sql, seconds):
    """Background session that runs `body_sql` inside a transaction and keeps it open for `seconds` (a long-held lock)."""
    p = subprocess.Popen(["docker", "exec", "-i", H.CONTAINER, "psql", "-U", "postgres", "-d", db, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
                         stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
    p.stdin.write(f"begin;\n{body_sql};\nselect pg_sleep({seconds});\ncommit;\n")
    p.stdin.close()
    time.sleep(1.5)       # let it take the lock
    return p


def timed(fn):
    t = time.time()
    try:
        out = fn()
        return time.time() - t, out, None
    except PgError as e:
        return time.time() - t, None, e


class Poller:
    """Portal-style reader (role authenticated, 8 s lock/statement timeouts like the hosted API) polling the products in a loop."""

    def __init__(self, db, table="intelligence_products"):
        self.db, self.table = db, table
        self.lat, self.errors = [], []
        self._stop = threading.Event()
        self.t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            t = time.time()
            try:
                psql(f"select count(*) from public.{self.table}", self.db, role="authenticated", settings=H.API_SETTINGS)
            except PgError as e:
                self.errors.append(e.sqlstate)
            self.lat.append(time.time() - t)
            time.sleep(0.02)

    def __enter__(self):
        self.t.start()
        return self

    def __exit__(self, *a):
        self._stop.set()
        self.t.join(timeout=30)

    @property
    def max_latency(self):
        return max(self.lat) if self.lat else 0.0


def _spawn_overhead():
    """Wall time of an empty psql_once call: `docker exec` start-up is slow on a loaded host and is not lock wait."""
    return min(timed(lambda: psql_once("select 1", f"wp11_t{H.RUN}"))[0] for _ in range(2))


class TestLocks(unittest.TestCase):
    """lock_timeout behaviour: a long-held reader/writer lock must neither hang the migration nor the portal."""

    def test_long_reader_transaction_makes_expand_fail_fast_and_retry(self):
        s = Scn("l_reader", RAW)
        overhead = _spawn_overhead()
        p = hold(s.db, "select count(*) from public.intelligence_products", 12)
        try:
            with ThreadPoolExecutor(2) as ex:
                mig = ex.submit(timed, lambda: psql_once((DRAFTS / MIG["0263a"]).read_text(), s.db))
                time.sleep(0.8)
                rdr = ex.submit(timed, lambda: psql("select count(*) from public.intelligence_products", s.db, role="authenticated", settings=H.API_SETTINGS))
                mig_t, _, mig_err = mig.result(timeout=60)
                rdr_t, _rdr_out, rdr_err = rdr.result(timeout=60)
        finally:
            p.wait(timeout=60)
        self.assertIsNotNone(mig_err)
        self.assertEqual(mig_err.sqlstate, "55P03")
        mig_t = max(mig_t - overhead, 0)
        self.assertLess(mig_t, 6, "migration must give up at its own lock_timeout (3 s), not wait for the 12 s holder")
        self.assertIsNone(rdr_err, "a portal read queued behind the waiting migration must still succeed")
        self.assertLess(rdr_t, 8, "the queued portal read must finish inside the API's 8 s limits")
        H.MATRIX.append({"scenario": "locks", "step": "reader holds ACCESS SHARE 12 s; 0263a", "migration": "55P03", "migration_wait_s": round(mig_t, 1),
                         "queued_portal_read_s": round(rdr_t, 1), "queued_portal_read_ok": rdr_err is None})
        self.assertFalse(s.shape()["a"], "nothing partially applied")
        self.assertIsNone(s.write("old", D1, "w"))                   # writers unaffected by the aborted attempt
        s.apply("0263a")                                             # retry after the holder finished
        s.check("retry after lock failure", old_portal="ok", new_portal="ok", history_lost=3)   # 3 = the pre-expand overwrite by the old writer

    def test_long_writer_transaction_makes_contract_fail_fast_and_retry(self):
        s = Scn("l_writer", RAW)
        s.apply("0263a")
        overhead = _spawn_overhead()
        p = hold(s.db, "update public.intelligence_products set title = title where product_key='forward_watch' and generated_for='2026-11-25'", 12)
        try:
            with ThreadPoolExecutor(2) as ex:
                mig = ex.submit(timed, lambda: psql_once((DRAFTS / MIG["0263b"]).read_text(), s.db))
                time.sleep(0.8)
                wr = ex.submit(timed, lambda: s.write("new_on", D3, "queued"))
                mig_t, _, mig_err = mig.result(timeout=60)
                wr_t, wr_res, _ = wr.result(timeout=60)
        finally:
            p.wait(timeout=60)
        self.assertIsNotNone(mig_err)
        self.assertEqual(mig_err.sqlstate, "55P03")
        mig_t = max(mig_t - overhead, 0)
        self.assertLess(mig_t, 6)
        self.assertIsNone(wr_res, "a writer queued behind the waiting contract must complete after it gives up")
        H.MATRIX.append({"scenario": "locks", "step": "writer holds row lock 12 s; 0263b", "migration": "55P03", "migration_wait_s": round(mig_t, 1),
                         "queued_writer_s": round(wr_t, 1), "queued_writer_result": wr_res})
        self.assertEqual(s.q("select pg_get_constraintdef(oid) from pg_constraint where conname='intelligence_products_pkey'"), "PRIMARY KEY (product_key, generated_for)")
        s.apply("0263b")
        s.check("contract retry after lock failure", new_portal="ok", history_lost=0)

    def test_lock_hold_time_and_reader_impact_on_small_data(self):
        s = Scn("l_hold", RAW)
        out = {}
        with Poller(s.db) as pl:
            for mig in ("0264", "0263a", "0263b", "0263r"):
                t0 = time.time()
                s.apply(mig)
                out[mig] = round(time.time() - t0, 2)
        H.MATRIX.append({"scenario": "locks", "step": "migration durations with a portal-style poller (6 rows)", "seconds": out,
                         "reader_max_latency_s": round(pl.max_latency, 2), "reader_errors": pl.errors, "reader_calls": len(pl.lat)})
        self.assertEqual(pl.errors, [], "no portal read may fail while migrations run")
        self.assertLess(pl.max_latency, 8)

    def test_scale_lock_hold_with_many_generations(self):
        n = int(os.environ.get("INTEL_WP11_SCALE_ROWS", "6000"))
        s = Scn("l_scale", RAW)
        # n synthetic legacy rows (distinct dates) with ~4 KB bodies, loaded as the postgres role before the migrations
        s.q("insert into public.intelligence_products (product_key, generated_for, as_of, title, summary, sections, exceptions, body_md) "
            f"select k, date '2000-01-01' + g, timestamptz '2000-01-01 19:20+00' + g * interval '1 day', 't', 's', '{{}}'::jsonb, '[]'::jsonb, "
            f"repeat(md5(g::text||k), 125) from generate_series(1, {n // 3}) g, unnest(array['recurring_provider','systemic_risk','forward_watch']) k")
        total = int(s.q("select count(*) from intelligence_products"))
        out = {}
        with Poller(s.db) as pl:
            for mig in ("0263a", "0263b"):
                t0 = time.time()
                s.apply(mig)
                out[mig] = round(time.time() - t0, 2)
            # after the contract every generation is a row: add a second generation for half of the keys, then roll back
            s.q("insert into public.intelligence_products (product_key,generated_for,as_of,title,summary,sections,exceptions,body_md,reporting_date,"
                "reporting_date_basis,cadence,cadence_basis,generation_seq,writer_version) select product_key, generated_for, as_of + interval '1 hour', "
                "title, summary, sections, exceptions, repeat(md5('x'||id::text), 125), reporting_date, reporting_date_basis, cadence, cadence_basis, 2, 2 "
                "from public.intelligence_products where id % 2 = 0")
            t0 = time.time()
            s.apply("0263r")
            out["0263r"] = round(time.time() - t0, 2)
        self.assertEqual(s.q("select count(*) from intelligence_products_revisions where archive_reason='rollback_export'"), str(total // 2))
        H.MATRIX.append({"scenario": "locks", "step": f"migration durations with {total} rows, ~4 KB bodies", "seconds": out,
                         "reader_max_latency_s": round(pl.max_latency, 2), "reader_errors": pl.errors, "reader_calls": len(pl.lat)})
        # ACCESS EXCLUSIVE is held for the whole of each transaction: a reader that waits longer than the API's 8 s lock_timeout errors.
        overhead = _spawn_overhead()
        for mig, secs in out.items():
            self.assertLess(secs - overhead, 8, f"{mig} took {secs}s at {total} rows: portal reads would time out while it holds the table lock")
        self.assertEqual(pl.errors, [])


# ======================================================================================================================
class TestConcurrency(unittest.TestCase):
    """Cut-over under load: parallel writers and readers, and migrations applied while writers run."""

    @staticmethod
    def _parallel(s, specs, flag_on=True):
        """Run writer specs [(kind, as_of, tag, cadence)] on threads against the same database; returns the list of results."""
        import threading as th
        tls = th.local()
        with H.rest(s.db) as fr, mock.patch.dict(os.environ, {H.job.APPEND_FLAG: "1" if flag_on else "0"}), \
                mock.patch.object(H.job.ip, "build_products", lambda a, b, c, d: H.make_products(tls.tag)):
            def one(spec):
                kind, as_of, tag, cad = spec
                tls.tag = tag
                if kind == "old":
                    return H.old_writer(as_of, tag)
                try:
                    H.job.run(as_of, getter=H._stub_getter, force=True, cadence=cad)
                    return None
                except urllib.error.HTTPError as e:
                    return f"HTTP{e.code}"
                except Exception as e:  # noqa: BLE001
                    return type(e).__name__
            with ThreadPoolExecutor(len(specs)) as ex:
                res = list(ex.map(one, specs))
            s.o.absorb(fr)
        return res

    def _six_writers(self, stage):
        s = Scn(f"c_six_{stage.replace('+', '')}", RAW)
        for m in H.STAGES[stage]:
            s.apply(m)
        specs = [("new_on", iso(2026, 11, 27, 19, 20, 5 + i), f"par{i // 2}", "daily") for i in range(6)]
        specs[5] = ("new_on", iso(2026, 11, 27, 19, 20, 11), "par2", "weekly")
        stop = threading.Event()
        errs = []

        def readers():
            while not stop.is_set():
                for fn in (H.old_portal, H.new_portal):
                    r = fn(s.db)
                    if isinstance(r, str) and r.startswith("throws"):
                        errs.append(r)
        th = threading.Thread(target=readers, daemon=True)
        th.start()
        res = self._parallel(s, specs)
        stop.set()
        th.join(timeout=60)
        self.assertEqual(res, [None] * 6, f"{stage}: every parallel writer must succeed: {res}")
        self.assertEqual(errs, [], "readers must never error during the burst")
        row = s.check(f"six parallel writers on {stage}", writers={"results": res}, new_portal="ok", history_lost=0)
        # no duplicate generation sequence per (product, cadence, reporting_date)
        seq_col = "generation_seq"
        dup = s.q(f"select count(*) from (select 1 from intelligence_products where cadence<>'unknown' group by product_key, cadence, reporting_date, {seq_col} having count(*)>1) x")
        self.assertEqual(dup, "0")
        return s, row

    def test_six_parallel_writers_and_readers_on_expand(self):
        s, _row = self._six_writers("A")
        # the content bodies all survive (live or archived); identical content never duplicated as a generation
        self.assertEqual(s.q("select count(*) from intelligence_products_current where cadence in ('daily','weekly')"), "6")

    def test_six_parallel_writers_and_readers_after_contract(self):
        s, _row = self._six_writers("A+B")
        self.assertEqual(s.q("select count(*) from (select 1 from intelligence_products group by product_key, cadence, reporting_date, generation_seq having count(*)>1) x"), "0")

    def test_old_and_new_writers_race_on_expand(self):
        s = Scn("c_mixed", RAW)
        s.apply("0263a")
        specs = [("old", iso(2026, 11, 27, 19, 20, 5), "mo1", "daily"), ("new_on", iso(2026, 11, 27, 19, 20, 6), "mn1", "daily"),
                 ("old", iso(2026, 11, 27, 19, 20, 7), "mo2", "daily"), ("new_on", iso(2026, 11, 27, 19, 20, 8), "mn2", "daily")]
        res = self._parallel(s, specs)
        self.assertEqual(res, [None] * 4)
        s.check("old and new writers racing on 0263a", writers={"results": res}, new_portal="ok", history_lost=0)

    def test_migrations_applied_while_writers_run(self):
        """Writers loop while 0263a, then 0263b and 0263r, are applied. Allowed outcomes: success, or a refused write that changes nothing
        (HTTP400 = the old key vanished mid-flight or the old writer after 0263b, HTTP503/500 = lock wait). Never lost history after the
        expand, never a hung migration, and the new writer keeps succeeding."""
        s = Scn("c_during", RAW)
        tls = threading.local()
        lock, clock = threading.Lock(), [0]

        def phase(flag_on, kinds, during):
            """Run writer loops for the duration of `during()`; returns [(kind, result)]."""
            results, stop = [], threading.Event()

            def loop(kind, idx):
                i = 0
                while not stop.is_set():
                    i += 1
                    with lock:
                        clock[0] += 1
                        n = clock[0]
                    t = iso(2026, 12, 1 + (n // 3000), 19, (n // 60) % 60, n % 60)
                    tag = f"{kind}-{idx}-{i}-{n}"
                    tls.tag = tag
                    try:
                        if kind == "old":
                            r = H.old_writer(t, tag)
                        else:
                            H.job.run(t, getter=H._stub_getter, force=True, cadence="daily")
                            r = None
                    except urllib.error.HTTPError as e:
                        r = f"HTTP{e.code}"
                    except Exception as e:  # noqa: BLE001
                        r = type(e).__name__
                    with lock:
                        results.append((kind, r))
                    time.sleep(0.15)
            with H.rest(s.db) as fr, mock.patch.dict(os.environ, {H.job.APPEND_FLAG: "1" if flag_on else "0"}), \
                    mock.patch.object(H.job.ip, "build_products", lambda a, b, c, d: H.make_products(tls.tag)):
                ths = [threading.Thread(target=loop, args=(k, i), daemon=True) for i, k in enumerate(kinds)]
                for t in ths:
                    t.start()
                time.sleep(2.0)
                during()
                time.sleep(2.0)
                stop.set()
                for t in ths:
                    t.join(timeout=60)
                s.o.absorb(fr)
            return results

        times = {}

        def timed_apply(name):
            def go():
                t0 = time.time()
                s.apply(name)
                times[name] = round(time.time() - t0, 2)
            return go

        r1 = phase(False, ["old", "new_off"], timed_apply("0263a"))
        self.assertEqual([r for _, r in r1 if r is not None], [], f"expand under old/flag-OFF writers: unexpected failures {r1}")
        pre_lost = len(s.o.lost(s.db))           # overwrites that happened on the unmigrated table before the expand landed
        r2 = phase(True, ["new_on", "new_on"], lambda: (timed_apply("0263b")(), time.sleep(2.0), timed_apply("0263r")()))
        allowed = (None, "HTTP400", "HTTP503", "HTTP500")
        self.assertTrue(all(r in allowed for _, r in r2), f"phase 2 results {r2}")
        self.assertGreaterEqual(sum(1 for _, r in r2 if r is None), 1)
        self.assertEqual(len(s.o.lost(s.db)), pre_lost, "no history may be lost after 0263a, through 0263b and 0263r, under live writers")
        self.assertIsNone(s.write("new_on", iso(2026, 12, 20, 19, 20), "after"))
        H.MATRIX.append({"scenario": "concurrency", "step": "migrations applied under live writers", "apply_seconds": times,
                         "phase1_writer_calls": len(r1), "phase2_writer_calls": len(r2), "phase2_failures": sorted({str(r) for _, r in r2 if r}),
                         "pre_expand_loss": pre_lost})
        s.check("after migrations under load", new_portal="ok")


# ======================================================================================================================
def _export(s, table, tmpdir, name):
    """Client-side style export: one JSON document per row written to a file outside the database, returned as parsed rows."""
    out = s.q(f"select coalesce(json_agg(row_to_json(t)),'[]'::json) from public.{table} t")
    f = Path(tmpdir) / f"{name}.json"
    f.write_text(out, encoding="utf-8")
    return json.loads(f.read_text(encoding="utf-8"))


class TestRollback(unittest.TestCase):
    """A code revert alone is not a rollback. Each stage: what a code-only revert does, and the DB-side steps that complete it."""

    def test_code_revert_alone_after_expand_preserves_history_without_db_steps(self):
        s = Scn("rb_a", RAW)
        s.apply("0264")
        s.apply("0263a")
        for kind, t, tag, cad in (("new_on", D3, "on1", "daily"), ("new_on", D3M, "on2", "daily"), ("new_on", W1, "on3", "weekly")):
            self.assertIsNone(s.write(kind, t, tag, cadence=cad))
        revs = int(s.q("select count(*) from intelligence_products_revisions"))
        # revert the code: old writer + old reader, flag state irrelevant. No migration is touched.
        self.assertIsNone(s.write("old", D5, "reverted1"))
        self.assertIsNone(s.write("old", D5M, "reverted2"))        # same-key overwrite by the OLD writer
        s.check("A: code reverted (old writer, old reader), DB untouched", old_portal="ok", new_portal="ok", history_lost=0)
        self.assertGreater(int(s.q("select count(*) from intelligence_products_revisions")), revs)
        # the delivery table is independent of the products code path
        self.assertTrue(s.shape()["attempts"])

    def test_code_revert_alone_after_contract_is_insufficient_and_rollback_script_completes_it(self):
        s = Scn("rb_b", RAW)
        s.apply("0263a")
        self.assertIsNone(s.write("new_on", D3, "on1"))
        s.apply("0263b")
        self.assertIsNone(s.write("new_on", D3M, "on2"))
        newest_before = s.q("select max(as_of) from intelligence_products")
        # code reverted: the old writer is refused (42P10) and the products stop refreshing: NOT a rollback
        self.assertEqual(s.write("old", D5, "reverted"), "HTTP400")
        self.assertEqual(s.q("select max(as_of) from intelligence_products"), newest_before)
        # DB-side step: 0263r. Then the reverted code works and nothing was lost.
        s.apply("0263r")
        self.assertIsNone(s.write("old", D5, "reverted"))
        s.check("B: code revert + 0263r", old_portal="ok", new_portal="ok", history_lost=0)

    def test_full_db_rollback_of_expand_is_export_backed(self):
        s = Scn("rb_full", RAW)
        s.apply("0264")
        s.apply("0263a")
        for kind, t, tag, cad in (("old", D1, "o1", "daily"), ("new_off", D2, "f1", "daily"), ("new_off", D2M, "f2", "daily"),
                                  ("new_on", D3, "n1", "daily"), ("new_on", D3M, "n2", "daily"), ("new_on", D4, "n3", "daily"),
                                  ("new_on", W1, "n4", "weekly")):
            self.assertIsNone(s.write(kind, t, tag, cadence=cad))
        s.check("before full rollback", old_portal="ok", new_portal="ok", history_lost=0)
        with tempfile.TemporaryDirectory() as td:
            exp = {t: _export(s, t, td, t) for t in ("intelligence_products", "intelligence_products_revisions", "intelligence_product_refreshes")}
            exported = {sha(r["body_md"]) for t in ("intelligence_products", "intelligence_products_revisions") for r in exp[t]}
            self.assertTrue(set(s.o.written) <= exported, "the export must contain every body ever written (incl. the six preserved)")
            self.assertGreater(len(exp["intelligence_product_refreshes"]), 0)
            # without the confirmation the script refuses; nothing changes
            fp = _fingerprint(s)
            self.assertEqual(s.apply("0263z", expect="42501").sqlstate, "42501")
            self.assertEqual(_fingerprint(s), fp)
            # B must be rolled back first
            s.apply("0263z", sql="set intelligence.export_confirmed = 'yes';\n" + (DRAFTS / MIG["0263z"]).read_text())
            self.assertFalse(s.shape()["a"])
            self.assertEqual(s.q("select string_agg(column_name, ',' order by ordinal_position) from information_schema.columns where table_name='intelligence_products'"),
                             "product_key,generated_for,as_of,title,summary,sections,exceptions,body_md,created_at")
            self.assertEqual(s.q("select pg_get_constraintdef(oid) from pg_constraint where conname='intelligence_products_pkey'"), "PRIMARY KEY (product_key, generated_for)")
            # production shape restored: reverted code works, both readers right (new reader falls back: view gone)
            self.assertIsNone(s.write("old", D5, "after-rollback"))
            s.check("after full DB rollback", old_portal="ok", new_portal="ok")
            # every body that is no longer in the database exists in the export (byte-exact)
            gone = set(s.o.lost(s.db))
            self.assertTrue(gone <= exported, "history removed from the database must be recoverable from the export")
            self.assertGreater(len(gone), 0, "the rollback does remove versions from the database: the export is what keeps them")
            # restore rehearsal: the export loads back byte-exact into a scratch table
            s.q(f"create table public.wp11_restore as select * from jsonb_populate_recordset(null::public.intelligence_products, "
                f"{jlit(exp['intelligence_products'] + exp['intelligence_products_revisions'])})")
            restored = H.sql_scalar_set(s.db, "select encode(sha256(convert_to(body_md,'UTF8')),'hex') from public.wp11_restore")
            self.assertEqual(restored, exported)
        H.MATRIX.append({"scenario": "rollback", "step": "full DB rollback of 0263a, export-backed", "bodies_in_export": len(exported), "bodies_removed_from_db": len(gone)})

    def test_rollback_of_contract_then_expand_then_reapply(self):
        s = Scn("rb_chain", RAW)
        for m in ("0263a", "0263b"):
            s.apply(m)
        self.assertIsNone(s.write("new_on", D3, "x1"))
        s.apply("0263r")
        # 0263z refuses while contracted; works after 0263r (checked in the full test); re-apply expand is clean
        s.apply("0263a")
        s.check("R then A re-run", old_portal="ok", new_portal="ok", history_lost=0)

    def test_delivery_attempts_rollback_is_export_backed_and_reversible(self):
        s = Scn("rb_0264", RAW)
        s.apply("0264")
        s.q(H.SEED_ATTEMPTS)
        with tempfile.TemporaryDirectory() as td:
            attempts = _export(s, "intelligence_delivery_attempts", td, "attempts")
            self.assertEqual(len(attempts), 2)
            self.assertEqual(s.apply("0264r", expect="42501").sqlstate, "42501")
            self.assertTrue(s.shape()["attempts"])
            s.apply("0264r", sql="set intelligence.export_confirmed = 'yes';\n" + (DRAFTS / MIG["0264r"]).read_text())
        self.assertFalse(s.shape()["attempts"])
        self.assertEqual(s.q("select count(*) from information_schema.columns where table_name in ('captains_daily_briefs','intelligence_briefs') "
                             "and column_name in ('production_status','telegram_status','telegram_at','delivery_disclosure','production_status_reasons')"), "0")
        # existing brief writers/readers unaffected; the old shape is exactly the production shape again
        s.q("insert into public.captains_daily_briefs (brief_type, brief_text) values ('morning','after rollback')", role="service_role")
        self.assertEqual(s.q("select count(*) from public.captains_daily_briefs", role="authenticated"), "2")
        s.apply("0264")                                  # and the forward migration re-applies cleanly
        self.assertTrue(s.shape()["attempts"])


# ======================================================================================================================
class TestDeliveryAttemptStoreThroughTheApi(unittest.TestCase):
    """The real PostgrestAttemptStore against the real 0264 table, as the service role the bots use (emulated PostgREST)."""

    def test_claim_update_refusals_and_no_silent_overwrite(self):
        from intelligence import delivery_record as dr
        s = Scn("d_store", RAW)
        s.apply("0264")
        with H.rest(s.db):
            store = dr.PostgrestAttemptStore("http://postgrest.invalid", H.FakeRest.SVC)
            ch = dr.content_hash("brief text")
            rec = dr.AttemptRecord("captains_daily_briefs", "brief-1", "telegram", ch, chunks_total=2)
            store.claim(rec)
            dup = dr.AttemptRecord("captains_daily_briefs", "brief-1", "telegram", ch, chunks_total=2)
            with self.assertRaises(dr.AttemptConflict):                       # same (brief, content, attempt_no): unique index
                store.claim(dup)
            rec.chunks = [dr.ChunkResult(0, "CONFIRMED", 11, None, 1), dr.ChunkResult(1, "UNKNOWN", None, "timeout", 1)]
            rec.state, rec.outcome, rec.finished_at = "finished", dr.DeliveryOutcome.UNKNOWN, dr.utcnow()
            store.update(rec)
            # a second process that read the row earlier cannot overwrite it blindly
            stale = store.load("captains_daily_briefs", "brief-1", "telegram")[0]
            stale._persisted = ("sending", None)
            stale.outcome = dr.DeliveryOutcome.FAILED
            with self.assertRaises(dr.AttemptConflict):
                store.update(stale)                                            # zero rows matched: stale_update
            # forward transition allowed, backward refused by the trigger
            fresh = store.load("captains_daily_briefs", "brief-1", "telegram")[0]
            fresh.chunks[1] = dr.ChunkResult(1, "CONFIRMED", 12, None, 1)
            fresh.outcome = dr.DeliveryOutcome.CONFIRMED
            store.update(fresh)
            back = store.load("captains_daily_briefs", "brief-1", "telegram")[0]
            back.outcome = dr.DeliveryOutcome.FAILED
            with self.assertRaises(dr.AttemptConflict):
                store.update(back)
            tamper = store.load("captains_daily_briefs", "brief-1", "telegram")[0]
            tamper.chunks[0] = dr.ChunkResult(0, "CONFIRMED", 999, None, 1)
            with self.assertRaises(dr.AttemptConflict):
                store.update(tamper)
        stored = json.loads(s.q("select json_agg(row_to_json(t)) from public.intelligence_delivery_attempts t"))
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["outcome"], "CONFIRMED")
        self.assertEqual([c["message_id"] for c in stored[0]["chunks"]], [11, 12])


# ======================================================================================================================
RELS = ["intelligence_products", "intelligence_products_revisions", "intelligence_product_refreshes", "intelligence_products_current",
        "intelligence_delivery_attempts", "captains_daily_briefs", "intelligence_briefs"]
# Effective privileges (has_table_privilege; r=SELECT a=INSERT w=UPDATE d=DELETE D=TRUNCATE x=REFERENCES t=TRIGGER m=MAINTAIN).
# AS DRAFTED = production replica + 0264 + 0263a + 0263b exactly as in the drafts (hosted default ACLs of the migration role).
FULL = "Dadmrtwx"
# After the round-three blocker fixes (r3-db): TRUNCATE (D) is revoked from service_role on the four history/attempts tables
# (N1, 0263a/0264) and authenticated has no access to delivery attempts (N2). Everything else is unchanged.
NO_TRUNC = "admrtwx"
EXPECT_DRAFTED = {
    "intelligence_products": {"anon": "mr", "authenticated": "mr", "service_role": NO_TRUNC, "PUBLIC": ""},
    "intelligence_products_revisions": {"anon": "", "authenticated": "r", "service_role": NO_TRUNC, "PUBLIC": ""},
    "intelligence_product_refreshes": {"anon": "", "authenticated": "r", "service_role": NO_TRUNC, "PUBLIC": ""},
    "intelligence_products_current": {"anon": "", "authenticated": FULL, "service_role": FULL, "PUBLIC": ""},
    "intelligence_delivery_attempts": {"anon": "", "authenticated": "", "service_role": NO_TRUNC, "PUBLIC": ""},
    # not touched by this work; shown because they are in the same blast radius (identical to production today)
    "captains_daily_briefs": {"anon": "mr", "authenticated": FULL, "service_role": FULL, "PUBLIC": ""},
    "intelligence_briefs": {"anon": "mr", "authenticated": FULL, "service_role": FULL, "PUBLIC": ""},
}
EXPECT_HARDENED = {
    "intelligence_products": {"anon": "", "authenticated": "r", "service_role": "arw", "PUBLIC": ""},
    "intelligence_products_revisions": {"anon": "", "authenticated": "r", "service_role": "ar", "PUBLIC": ""},
    "intelligence_product_refreshes": {"anon": "", "authenticated": "r", "service_role": "ar", "PUBLIC": ""},
    "intelligence_products_current": {"anon": "", "authenticated": "r", "service_role": "r", "PUBLIC": ""},
    "intelligence_delivery_attempts": {"anon": "", "authenticated": "", "service_role": "arw", "PUBLIC": ""},
    "captains_daily_briefs": EXPECT_DRAFTED["captains_daily_briefs"],
    "intelligence_briefs": EXPECT_DRAFTED["intelligence_briefs"],
}


def _norm(m):
    return {rel: ({r: "".join(sorted(v)) for r, v in roles.items()} if roles else None) for rel, roles in m.items()}


def perm_scn(name, stage, hardened):
    s = Scn(name, RAW)
    s.apply("0264")
    s.apply("0263a")
    # seed archive + refresh rows so row-level guards can fire: the old writer's 26 Nov run archives the 25 Nov versions
    assert s.write("old", D1, "seed-old") is None
    assert s.write("new_on", D3, "seed-new") is None
    if stage == "A+B":
        s.apply("0263b")
    if hardened:
        s.apply("0263h")
    s.q(H.SEED_ATTEMPTS)
    return s


class TestPermissions(unittest.TestCase):
    """Effective permissions and role-path behaviour of the new tables, the view and the existing tables, as drafted and with the
    proposed hardening (0263h). service_role is the only application writer; authenticated is the portal session; anon is the public key."""

    def test_effective_privilege_matrix_as_drafted_and_hardened(self):
        d = perm_scn("p_matrix_d", "A+B", False)
        h = perm_scn("p_matrix_h", "A+B", True)
        got_d, got_h = _norm(H.priv_matrix(d.db, RELS)), _norm(H.priv_matrix(h.db, RELS))
        H.MATRIX.append({"scenario": "permissions", "step": "effective privileges as drafted", "matrix": got_d})
        H.MATRIX.append({"scenario": "permissions", "step": "effective privileges with 0263h", "matrix": got_h})
        self.assertEqual(got_d, _norm(EXPECT_DRAFTED))
        self.assertEqual(got_h, _norm(EXPECT_HARDENED))
        # ACL-level cross-check: nothing is granted to PUBLIC anywhere, and PUBLIC is not hiding behind has_table_privilege
        for rel in RELS:
            self.assertEqual(got_d[rel]["PUBLIC"], "")
        # information_schema agrees with the ACLs for the roles of interest (a superuser sees every grantee)
        for s_, exp in ((d, EXPECT_DRAFTED), (h, EXPECT_HARDENED)):
            rows = s_.q("select grantee||'|'||table_name||'|'||string_agg(privilege_type, ',' order by privilege_type) from information_schema.table_privileges "
                        "where table_schema='public' and grantee in ('anon','authenticated','service_role') and table_name = any(array["
                        + ",".join(lit(r) for r in RELS[:5]) + "]) group by grantee, table_name").splitlines()
            have = {(r.split("|")[0], r.split("|")[1]) for r in rows}
            for rel in RELS[:5]:
                for role in ("anon", "authenticated", "service_role"):
                    self.assertEqual(((role, rel) in have), bool(exp[rel][role]), f"information_schema vs matrix for {role} on {rel}")
        # the explicit-GRANT question: authenticated can read the view and its three base relations, in both variants
        for s_ in (d, h):
            for rel in ("intelligence_products_current", "intelligence_products", "intelligence_products_revisions", "intelligence_product_refreshes"):
                self.assertEqual(s_.q(f"select has_table_privilege('authenticated','public.{rel}','SELECT')"), "t", rel)
            self.assertEqual(s_.q("select has_table_privilege('service_role','public.intelligence_products_current','SELECT')"), "t")

    def _invariants(self, s, label, hardened, stage):
        res = {}
        for role in ("service_role", "authenticated", "anon", "postgres"):
            r = None if role == "postgres" else role
            res[role] = {"attempts": H.run_ops(s.db, r, H.ATTEMPT_OPS), "history": H.run_ops(s.db, r, H.HISTORY_OPS),
                         "products": H.run_ops(s.db, r, H.PRODUCT_OPS), "view": H.run_ops(s.db, r, H.VIEW_OPS)}
        H.MATRIX.append({"scenario": "permissions", "step": f"role paths {label}", "results": res})
        refused = lambda v: v != "ok"
        for role in ("authenticated", "anon"):
            for table in ("attempts", "history", "view"):
                for op, v in res[role][table].items():
                    if op != "select":
                        self.assertTrue(refused(v), f"{role} {table}.{op} must be refused, got {v}")
            for op, v in res[role]["products"].items():
                if op not in ("select", "maintain_lock"):
                    self.assertTrue(refused(v), f"{role} products.{op} must be refused, got {v}")
        sr = res["service_role"]
        # delivery attempts: forward transitions and inserts only
        self.assertEqual((sr["attempts"]["insert"], sr["attempts"]["update_forward"]), ("ok", "ok"))
        for op in ("update_backward", "update_confirmed_chunk", "delete", "truncate", "upsert_merge_overwrite", "disable_trigger", "drop_trigger",
                   "replace_guard_function", "session_replication_role_replica_delete"):
            self.assertTrue(refused(sr["attempts"][op]), f"service_role attempts.{op}: {sr['attempts'][op]}")
        self.assertEqual(sr["attempts"]["session_replication_role_replica_delete"], "42501")
        self.assertEqual(sr["attempts"]["disable_trigger"], "42501")
        # history tables: insert only
        self.assertEqual(sr["history"]["insert"], "ok")
        for op in ("update", "delete", "truncate", "disable_trigger", "session_replication_role_replica_delete"):
            self.assertTrue(refused(sr["history"][op]), f"service_role history.{op}: {sr['history'][op]}")
        # products table
        for op in ("disable_trigger", "session_replication_role_replica_delete"):
            self.assertEqual(sr["products"][op], "42501")
        return res

    def test_role_paths_as_drafted_after_expand(self):
        s = perm_scn("p_ops_da", "A", False)
        res = self._invariants(s, "as drafted, 0263a", False, "A")
        sr, au, an = res["service_role"]["products"], res["authenticated"]["products"], res["anon"]["products"]
        # The TRUNCATE defect found by the independent database review (the application role could truncate the live table with no
        # trace in the archive) is FIXED in 0263a (r3-db: revoke + BEFORE TRUNCATE guard). The MAINTAIN grant to anon/authenticated
        # (LOCK TABLE ... ACCESS EXCLUSIVE) is still open and is addressed only by the proposed 0263h.
        self.assertEqual(sr["truncate"], "42501")
        self.assertEqual((au["maintain_lock"], an["maintain_lock"]), ("ok", "ok"))
        self.assertEqual(sr["delete_row"], "ok")        # a row delete is archived by the trigger (checked below)
        self.assertEqual(res["postgres"]["attempts"]["disable_trigger"], "ok")   # residual: the owner role can switch triggers off
        self.assertEqual(res["postgres"]["products"]["session_replication_role_replica_delete"], "ok")

    def test_service_role_delete_and_update_on_expand_are_archived_not_lost(self):
        s = perm_scn("p_arch", "A", False)
        shas = H.all_body_shas(s.db)
        s.q("update public.intelligence_products set body_md = 'tampered' where product_key = 'forward_watch' and generated_for = '2026-11-28'", role="service_role")
        s.q("delete from public.intelligence_products where product_key = 'systemic_risk' and generated_for = '2026-11-28'", role="service_role")
        after = H.all_body_shas(s.db)
        self.assertTrue(shas <= after, "an update or delete by the application role must leave the previous bodies in the archive")

    def test_role_paths_as_drafted_after_contract(self):
        s = perm_scn("p_ops_db", "A+B", False)
        res = self._invariants(s, "as drafted, 0263a+0263b", False, "A+B")
        sr = res["service_role"]["products"]
        for op in ("update_content", "delete_row", "truncate"):
            self.assertNotEqual(sr[op], "ok", op)
        self.assertEqual(sr["update_content"], "23000")
        self.assertEqual(sr["delete_row"], "23000")

    def test_role_paths_with_hardening_after_expand(self):
        s = perm_scn("p_ops_ha", "A", True)
        res = self._invariants(s, "with 0263h, 0263a", True, "A")
        sr, au, an = res["service_role"]["products"], res["authenticated"]["products"], res["anon"]["products"]
        self.assertEqual((sr["truncate"], sr["delete_row"]), ("42501", "42501"))
        self.assertEqual((au["maintain_lock"], an["maintain_lock"]), ("42501", "42501"))
        self.assertEqual(res["authenticated"]["attempts"]["select"], "42501")        # minimum roles: service_role only
        self.assertEqual(res["service_role"]["history"]["update"], "42501")
        # the hardened roles still do their work
        self.assertIsNone(s.write("old", D5, "h-old"))
        self.assertIsNone(s.write("new_off", iso(2026, 12, 2, 19, 20), "h-off"))
        self.assertIsNone(s.write("new_on", iso(2026, 12, 3, 19, 20), "h-on"))
        self.assertIsNone(s.write("new_on", iso(2026, 12, 3, 20, 20), "h-on2"))     # same-key overwrite path
        s.check("hardened stage A, all writers", old_portal="ok", new_portal="ok")
        self.assertEqual(s.q("select count(*) from intelligence_products_current", role="authenticated"), s.q("select count(*) from intelligence_products_current"))

    def test_role_paths_with_hardening_after_contract_and_rollback(self):
        s = perm_scn("p_ops_hb", "A+B", True)
        self._invariants(s, "with 0263h, 0263a+0263b", True, "A+B")
        self.assertIsNone(s.write("new_on", D5, "hb-on"))
        self.assertIsNone(s.write("new_off", iso(2026, 12, 2, 19, 20), "hb-off"))
        s.apply("0263r")                                   # the rollback runs as the table owner and still works
        s.apply("0263h")                                   # hardening is re-runnable after the rollback (view re-created)
        self.assertEqual(_norm(H.priv_matrix(s.db, RELS[:5])), _norm({k: EXPECT_HARDENED[k] for k in RELS[:5]}))
        self.assertIsNone(s.write("old", iso(2026, 12, 4, 19, 20), "hr-old"))
        s.check("hardened after rollback", old_portal="ok", new_portal="ok", history_lost=0)

    def test_missing_default_acls_break_writers_unless_grants_are_explicit(self):
        """The drafts rely on the hosted default ACLs for service_role. Without them the archive trigger and the refresh insert fail
        (permission denied) on the writer's first same-key overwrite. 0263h makes every grant explicit."""
        s = Scn("p_nodefaults", RAW)
        s.q("alter default privileges in schema public revoke all on tables from anon, authenticated, service_role")
        s.apply("0264")
        s.apply("0263a")
        self.assertEqual(s.write("old", D1, "w1"), "HTTP403")          # trigger cannot insert into the archive as service_role
        self.assertEqual(s.q("select has_table_privilege('authenticated','public.intelligence_products_current','SELECT')"), "t")   # explicit grant present
        self.assertIsInstance(H.new_portal(s.db), dict)
        s.apply("0263h")
        self.assertIsNone(s.write("old", D1, "w1"))
        self.assertIsNone(s.write("new_on", D3, "w2"))
        s.check("explicit grants only", old_portal="ok", new_portal="ok", history_lost=0)

    def test_missing_view_grant_makes_the_portal_throw_not_fall_back(self):
        s = Scn("p_viewgrant", RAW)
        s.apply("0263a")
        s.check("view readable", old_portal="ok", new_portal="ok")
        s.q("revoke select on public.intelligence_products_current from authenticated")
        self.assertEqual(H.new_portal(s.db), "throws:42501")            # only a MISSING relation falls back; denied must be fixed
        self.assertIsInstance(H.old_portal(s.db), dict)
        H.MATRIX.append({"scenario": "permissions", "step": "view SELECT revoked from authenticated", "new_portal": "throws:42501"})
        s.q("grant select on public.intelligence_products_current to authenticated")
        self.assertIsInstance(H.new_portal(s.db), dict)
