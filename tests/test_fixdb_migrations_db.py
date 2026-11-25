"""DB review fixes proven against a throwaway Postgres: 0263a (expand-only operation), 0263b (contract), 0263r (rollback), 0264.

Skipped unless INTEL_TEST_PG_CONTAINER names a disposable container (psql via `docker exec`). Creates and drops its own databases
(fixdb_*); never touches anything else. Production is not involved.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "intelligence" / "analytics"))

from intelligence import brief_products_block as bpb
from intelligence import intel_products_job as job
from intelligence import product_history as ph

CONTAINER = os.environ.get("INTEL_TEST_PG_CONTAINER")
pytestmark = pytest.mark.timeout(600)
UTC = timezone.utc
DRAFTS = ROOT / "docs" / "migration-drafts"
SQL_A = "0263a_intelligence_products_history_expand.DRAFT.sql"
SQL_B = "0263b_intelligence_products_history_contract.DRAFT.sql"
SQL_R = "0263r_intelligence_products_history_rollback.DRAFT.sql"


class PgError(Exception):
    def __init__(self, sqlstate, text):
        super().__init__(f"{sqlstate}: {text[:300]}")
        self.sqlstate, self.text = sqlstate, text


def _run(db, sql, role=None, timeout=120):
    prefix = f"set role {role};\n" if role else ""
    p = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "postgres", "-d", db, "-X", "-q", "-A", "-t",
         "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose"],
        input=prefix + sql, capture_output=True, text=True, timeout=timeout, check=False)
    if p.returncode != 0:
        m = re.search(r"ERROR:\s+(\w{5}):", p.stderr)
        raise PgError(m.group(1) if m else "?????", p.stderr)
    return p.stdout.strip()


def lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def jlit(obj):
    tag = "j" + uuid.uuid4().hex[:8]
    return f"${tag}${json.dumps(obj, ensure_ascii=False)}${tag}$::jsonb"


def mkdb(name):
    subprocess.run(["docker", "exec", CONTAINER, "psql", "-U", "postgres", "-c", f"drop database if exists {name}"], check=True, capture_output=True)
    subprocess.run(["docker", "exec", CONTAINER, "createdb", "-U", "postgres", name], check=True, capture_output=True)


def dropdb(name):
    subprocess.run(["docker", "exec", CONTAINER, "psql", "-U", "postgres", "-c", f"drop database if exists {name}"], capture_output=True, check=False)


GRANTS = ("alter default privileges in schema public grant all on tables to service_role; "
          "alter default privileges in schema public grant select on tables to authenticated; "
          "alter default privileges in schema public grant select on tables to anon; "
          "alter default privileges in schema public grant all on tables to authenticated; ")


def hold_lock(db, table, seconds, mode="access exclusive"):
    """Background transaction holding a table lock; returns the Popen (wait on it)."""
    p = subprocess.Popen(["docker", "exec", "-i", CONTAINER, "psql", "-U", "postgres", "-d", db, "-X", "-q", "-v", "ON_ERROR_STOP=1"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    p.stdin.write(f"begin; lock table {table} in {mode} mode; select pg_sleep({seconds}); commit;\n")
    p.stdin.close()
    time.sleep(1.5)
    return p


@unittest.skipUnless(CONTAINER, "needs INTEL_TEST_PG_CONTAINER")
class ProductsBase(unittest.TestCase):
    DB = "fixdb_products"

    @classmethod
    def setUpClass(cls):
        mkdb(cls.DB)
        cls.q = staticmethod(lambda sql, role=None, timeout=120: _run(cls.DB, sql, role, timeout))
        cls.q(GRANTS)
        cls.q((DRAFTS / "0261_intelligence_products.DRAFT.sql").read_text())
        cls.q("grant usage on schema public to anon, authenticated, service_role; "
              "grant all on all tables in schema public to service_role; grant all on all tables in schema public to authenticated; "
              "grant select on all tables in schema public to anon")

    @classmethod
    def tearDownClass(cls):
        dropdb(cls.DB)

    def apply(self, name):
        self.q((DRAFTS / name).read_text())

    def legacy_upsert(self, **kw):
        rec = {"product_key": "forward_watch", "generated_for": "2026-11-25", "as_of": "2026-11-25T19:20:05+00:00", "title": "t",
               "summary": "s", "sections": {}, "exceptions": [], "body_md": "b"}
        rec.update(kw)
        cols = list(rec)
        sets = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("product_key", "generated_for"))
        self.q(f"insert into intelligence_products ({','.join(cols)}) select {','.join(cols)} "
               f"from jsonb_populate_record(null::intelligence_products, {jlit(rec)}) on conflict (product_key,generated_for) do update set {sets}",
               role="service_role")


class PsqlGateway:
    def __init__(self, q):
        self.q = q

    def latest_generation(self, pk, cadence):
        out = self.q(f"select row_to_json(t) from (select * from intelligence_products where product_key={lit(pk)} and cadence={lit(cadence)} "
                     f"order by as_of desc, id desc limit 1) t", role="service_role")
        return json.loads(out) if out else None

    def max_generation_seq(self, pk, cadence, rd):
        return int(self.q(f"select coalesce(max(generation_seq),0) from intelligence_products where product_key={lit(pk)} and cadence={lit(cadence)} "
                          f"and reporting_date={lit(rd)}", role="service_role"))

    def insert_generation(self, rec):
        cols = [c for c in rec if c != "id"]
        try:
            out = self.q(f"with ins as (insert into intelligence_products ({','.join(cols)}) select {','.join(cols)} "
                         f"from jsonb_populate_record(null::intelligence_products, {jlit(rec)}) returning *) select row_to_json(ins) from ins",
                         role="service_role")
        except PgError as e:
            if e.sqlstate == "23505":
                raise ph.UniqueViolation(str(e), legacy_key="(product_key, generated_for)" in e.text) from e
            raise
        return json.loads(out)

    def overwrite_generation(self, rec):
        cols = [c for c in rec if c != "id"]
        sets = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("product_key", "generated_for"))
        out = self.q(f"with ins as (insert into intelligence_products ({','.join(cols)}) select {','.join(cols)} "
                     f"from jsonb_populate_record(null::intelligence_products, {jlit(rec)}) on conflict (product_key,generated_for) do update "
                     f"set {sets} returning *) select row_to_json(ins) from ins", role="service_role")
        return json.loads(out)

    def insert_refresh(self, rec):
        cols = list(rec)
        self.q(f"insert into intelligence_product_refreshes ({','.join(cols)}) select {','.join(cols)} "
               f"from jsonb_populate_record(null::intelligence_product_refreshes, {jlit(rec)})", role="service_role")


def gen(body, as_of, cadence="daily", key="forward_watch", legacy=False):
    rec = {"product_key": key, "generated_for": "x", "as_of": as_of.isoformat(), "title": "T", "summary": "S", "sections": {"k": [1]},
           "exceptions": [], "body_md": body}
    return ph.build_generation(rec, cadence=cadence, legacy_attribution=legacy, watermark={"n": 1})


# ======================================================================================================================
class TestExpandOnly(ProductsBase):
    """Everything here runs on 0263a ALONE (original primary key still in place)."""

    DB = "fixdb_expand"

    def test_01_expand_is_rerunnable_and_backfills_labels(self):
        self.q("insert into intelligence_products (product_key,generated_for,as_of,title,summary,sections,exceptions,body_md) "
               "values ('systemic_risk','2026-11-25','2026-11-25T19:20:00Z','t','s','{}','[]','seed')")
        self.apply(SQL_A)
        self.apply(SQL_A)       # second run: idempotent, no error
        row = json.loads(self.q("select row_to_json(t) from (select reporting_date::text rd, reporting_date_basis b, cadence c, cadence_basis cb "
                                "from intelligence_products where body_md='seed') t"))
        # generated_for 25 Nov, Melbourne date of the instant 26 Nov: labelled as the Melbourne date of as_of, nothing more is claimed
        self.assertEqual(row, {"rd": "2026-11-26", "b": "as_of_melbourne_date", "c": "unknown", "cb": "legacy_unknown"})

    def test_02_view_exists_and_unknown_legacy_row_is_visible(self):
        cur = self.q("select count(*) from intelligence_products_current where product_key='systemic_risk' and cadence='unknown'")
        self.assertEqual(cur, "1")

    def test_03_identical_content_overwrite_adds_no_revision_changed_content_does(self):
        self.legacy_upsert(product_key="recurring_provider", body_md="same", as_of="2026-11-25T19:20:00+00:00")
        n0 = int(self.q("select count(*) from intelligence_products_revisions"))
        self.legacy_upsert(product_key="recurring_provider", body_md="same", as_of="2026-11-25T19:40:00+00:00")   # identical content
        self.assertEqual(int(self.q("select count(*) from intelligence_products_revisions")), n0)
        self.legacy_upsert(product_key="recurring_provider", body_md="changed", as_of="2026-11-25T20:10:00+00:00")
        self.assertEqual(int(self.q("select count(*) from intelligence_products_revisions")), n0 + 1)
        self.assertEqual(self.q("select body_md from intelligence_products_revisions where product_key='recurring_provider' order by revision_id desc limit 1"), "same")

    def test_04_new_writer_flag_on_works_without_part_b_and_history_is_preserved(self):
        gw = PsqlGateway(self.q)
        t1 = datetime(2026, 12, 1, 19, 20, tzinfo=UTC)          # 06:20 AEDT 2 Dec
        r1 = ph.record_run(gw, gen("v1", t1))
        r2 = ph.record_run(gw, gen("v1", datetime(2026, 12, 1, 19, 40, tzinfo=UTC)))              # identical -> refresh only
        r3 = ph.record_run(gw, gen("v2", datetime(2026, 12, 1, 20, 10, tzinfo=UTC)))              # same day, new content
        self.assertEqual([r.outcome for r in (r1, r2, r3)], ["new_generation", "unchanged", "new_generation"])
        self.assertEqual(r3.generation_seq, 2)
        live = self.q("select body_md||':'||generation_seq from intelligence_products where product_key='forward_watch' and cadence='daily' and reporting_date='2026-12-02'")
        self.assertEqual(live, "v2:2")
        # the replaced generation is archived byte-exactly by the database
        self.assertEqual(self.q("select body_md from intelligence_products_revisions where product_key='forward_watch' and cadence='daily' and reporting_date='2026-12-02'"), "v1")
        self.assertEqual(self.q("select count(*) from intelligence_product_refreshes where product_key='forward_watch' and cadence='daily'"), "3")
        # no self-referencing lineage
        self.assertEqual(self.q("select count(*) from intelligence_products where supersedes_id = id"), "0")

    def test_05_monday_weekly_overwrite_keeps_daily_visible_through_the_view(self):
        gw = PsqlGateway(self.q)
        ph.record_run(gw, gen("daily body", datetime(2026, 12, 6, 19, 20, tzinfo=UTC), cadence="daily", key="systemic_risk"))     # Mon 7 Dec 06:20
        ph.record_run(gw, gen("weekly body", datetime(2026, 12, 6, 20, 20, tzinfo=UTC), cadence="weekly", key="systemic_risk"))   # 07:20 same key
        rows = json.loads(self.q("select json_agg(t) from (select cadence, body_md, source, is_latest_for_product l from intelligence_products_current "
                                 "where product_key='systemic_risk' and cadence in ('daily','weekly') order by cadence) t"))
        self.assertEqual([(r["cadence"], r["body_md"], r["source"]) for r in rows],
                         [("daily", "daily body", "archived"), ("weekly", "weekly body", "live")])
        self.assertEqual(self.q("select cadence from intelligence_products_current where product_key='systemic_risk' and is_latest_for_product"), "weekly")

    def test_06_view_has_one_row_per_product_cadence_and_per_day(self):
        self.assertEqual(self.q("select count(*) from (select 1 from intelligence_products_current group by product_key, cadence having count(*)>1) x"), "0")
        self.assertEqual(self.q("select count(*) from (select 1 from intelligence_products_current group by product_key, cadence, reporting_date having count(*)>1) x"), "0")
        self.assertEqual(self.q("select count(*) from (select 1 from intelligence_products_current where is_latest_for_product group by product_key having count(*)<>1) x"), "0")
        self.assertEqual(self.q("select count(distinct product_key) from intelligence_products_current where is_latest_for_product"),
                         self.q("select count(distinct product_key) from intelligence_products_current"))

    def test_07_legacy_writer_after_new_writer_row_resets_labels_not_stale_history(self):
        # a row written by the new writer, then overwritten by the original writer (flag turned off)
        gw = PsqlGateway(self.q)
        ph.record_run(gw, gen("by new writer", datetime(2026, 12, 8, 19, 20, tzinfo=UTC), cadence="daily", key="recurring_provider"))
        self.legacy_upsert(product_key="recurring_provider", generated_for="2026-12-09", body_md="by old writer", as_of="2026-12-08T19:50:00+00:00")
        row = json.loads(self.q("select row_to_json(t) from (select cadence, cadence_basis cb, content_hash h, writer_version wv, reporting_date_basis b, "
                                "generation_seq gs from intelligence_products where product_key='recurring_provider' and generated_for='2026-12-09') t"))
        self.assertEqual((row["cadence"], row["cb"], row["h"], row["wv"], row["b"], row["gs"]),
                         ("unknown", "legacy_unknown", None, 1, "as_of_melbourne_date", 2))
        self.assertEqual(self.q("select body_md from intelligence_products_revisions where product_key='recurring_provider' and generated_for='2026-12-09'"), "by new writer")

    def test_08_privileges_signed_in_users_read_only(self):
        for tbl in ("intelligence_products_revisions", "intelligence_product_refreshes", "intelligence_products"):
            with self.assertRaises(PgError, msg=tbl) as cm:
                self.q(f"truncate {tbl}", role="authenticated")
            self.assertEqual(cm.exception.sqlstate, "42501", tbl)
        with self.assertRaises(PgError) as cm:
            self.q("insert into intelligence_product_refreshes (product_key,cadence,reporting_date,as_of,outcome) values ('forward_watch','daily','2026-12-01',now(),'failed')", role="authenticated")
        self.assertEqual(cm.exception.sqlstate, "42501")
        with self.assertRaises(PgError) as cm:
            self.q("update intelligence_products set title='x'", role="authenticated")
        self.assertEqual(cm.exception.sqlstate, "42501")
        self.assertGreater(int(self.q("select count(*) from intelligence_products_current", role="authenticated")), 0)
        self.assertGreater(int(self.q("select count(*) from intelligence_products_revisions", role="authenticated")), 0)
        with self.assertRaises(PgError) as cm:
            self.q("select count(*) from intelligence_products_current", role="anon")
        self.assertEqual(cm.exception.sqlstate, "42501")
        with self.assertRaises(PgError):
            self.q("select count(*) from intelligence_products_revisions", role="anon")

    def test_09_service_role_cannot_rewrite_history_tables(self):
        for sql in ("update intelligence_products_revisions set title='x'", "delete from intelligence_products_revisions",
                    "update intelligence_product_refreshes set outcome='unchanged'"):
            with self.assertRaises(PgError, msg=sql) as cm:
                self.q(sql, role="service_role")
            self.assertEqual(cm.exception.sqlstate, "23000", sql)
        for t in ("intelligence_products_revisions", "intelligence_product_refreshes"):    # TRUNCATE: privilege revoked
            with self.assertRaises(PgError, msg=t) as cm:
                self.q(f"truncate {t}", role="service_role")
            self.assertEqual(cm.exception.sqlstate, "42501", t)

    def test_10_truncate_of_live_table_refused_for_every_role_and_history_survives(self):
        """N1: TRUNCATE is not archived by the row triggers. Refused for anon/authenticated/service_role (privilege) and for the
        table owner (statement trigger); the stored rows are byte-identical afterwards."""
        ev = os.environ.get("INTEL_PRODUCTS_EVIDENCE_DIR")
        if ev and (Path(ev) / "intelligence_products_20261124_25.raw.json").exists():
            rows = json.loads((Path(ev) / "intelligence_products_20261124_25.raw.json").read_text())
            cols = ["product_key", "generated_for", "as_of", "title", "summary", "sections", "exceptions", "body_md"]
            self.q(f"insert into intelligence_products ({','.join(cols)}) select {','.join(cols)} from "
                   f"jsonb_populate_recordset(null::intelligence_products, {jlit(rows)}) on conflict do nothing")
        ledger = ("select count(*)||':'||coalesce(string_agg(encode(sha256(convert_to(body_md,'UTF8')),'hex'),',' order by product_key,generated_for),'') "
                  "from %s")
        before = (self.q(ledger % "intelligence_products"), self.q(ledger % "intelligence_products_revisions"))
        self.assertGreaterEqual(int(before[0].split(":")[0]), 1)
        for t in ("intelligence_products", "intelligence_products_revisions", "intelligence_product_refreshes"):
            for role in ("anon", "authenticated", "service_role"):
                with self.assertRaises(PgError, msg=f"{t} as {role}") as cm:
                    self.q(f"truncate {t}", role=role)
                self.assertEqual(cm.exception.sqlstate, "42501", f"{t} as {role}")
                self.assertEqual(self.q(f"select has_table_privilege('{role}','{t}','TRUNCATE')"), "f")
            with self.assertRaises(PgError, msg=f"{t} as owner") as cm:        # trigger refuses even the owner
                self.q(f"truncate {t}")
            self.assertEqual(cm.exception.sqlstate, "23000", t)
            with self.assertRaises(PgError, msg=f"{t} cascade") as cm:
                self.q(f"truncate {t} cascade")
            self.assertEqual(cm.exception.sqlstate, "23000", t)
        self.assertEqual((self.q(ledger % "intelligence_products"), self.q(ledger % "intelligence_products_revisions")), before)


# ======================================================================================================================
class TestContractAndRollback(ProductsBase):
    DB = "fixdb_contract"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.apply_a = lambda: cls.q((DRAFTS / SQL_A).read_text())

    def test_01_part_b_requires_part_a_and_refuses_when_already_applied(self):
        with self.assertRaises(PgError) as cm:
            self.apply(SQL_B)
        self.assertEqual(cm.exception.sqlstate, "42P01")          # 0263b requires 0263a
        self.apply(SQL_A)

    def test_02_part_b_fails_fast_under_lock_and_is_retry_safe(self):
        self.q("insert into intelligence_products (product_key,generated_for,as_of,title,summary,sections,exceptions,body_md) "
               "values ('systemic_risk','2026-11-25','2026-11-25T19:20:00Z','t','s','{}','[]','a')")
        holder = hold_lock(self.DB, "public.intelligence_products", 9, mode="row exclusive")
        t0 = time.time()
        with self.assertRaises(PgError) as cm:
            self.apply(SQL_B)
        waited = time.time() - t0
        self.assertEqual(cm.exception.sqlstate, "55P03")
        self.assertLess(waited, 8, "must give up at lock_timeout, not queue behind the holder")
        # nothing was applied: original key, transitional triggers still present
        self.assertEqual(self.q("select pg_get_constraintdef(oid) from pg_constraint where conname='intelligence_products_pkey'"), "PRIMARY KEY (product_key, generated_for)")
        self.assertEqual(self.q("select count(*) from pg_trigger where tgrelid='public.intelligence_products'::regclass and tgname in ('intelligence_products_archive_trg','intelligence_products_legacy_fill_trg') and not tgisinternal"), "2")
        # readers were not blocked behind a queued exclusive lock
        t1 = time.time()
        self.q("select count(*) from intelligence_products")
        self.assertLess(time.time() - t1, 6)
        holder.wait(timeout=30)
        self.apply(SQL_B)           # retry succeeds
        self.assertEqual(self.q("select pg_get_constraintdef(oid) from pg_constraint where conname='intelligence_products_pkey'"), "PRIMARY KEY (id)")

    def test_03_part_b_rerun_is_refused_cleanly(self):
        with self.assertRaises(PgError) as cm:
            self.apply(SQL_B)
        self.assertEqual(cm.exception.sqlstate, "42P17")
        self.assertIn("already applied", cm.exception.text)

    def test_04_view_after_b_one_row_per_key_cadence_and_date(self):
        gw = PsqlGateway(self.q)
        for cad, body, t in (("daily", "d1", datetime(2026, 12, 1, 19, 20, tzinfo=UTC)), ("daily", "d2", datetime(2026, 12, 1, 20, 0, tzinfo=UTC)),
                             ("weekly", "w1", datetime(2026, 12, 1, 20, 20, tzinfo=UTC))):
            ph.record_run(gw, gen(body, t, cadence=cad, key="forward_watch"))
        # all three generations kept as rows (no overwrite after the key swap); the view shows the newest per cadence
        self.assertEqual(self.q("select count(*) from intelligence_products where product_key='forward_watch' and reporting_date='2026-12-02'"), "3")
        self.assertEqual(self.q("select string_agg(cadence||':'||body_md, ',' order by cadence) from intelligence_products_current where product_key='forward_watch' and cadence<>'unknown'"),
                         "daily:d2,weekly:w1")
        self.assertEqual(self.q("select count(*) from (select 1 from intelligence_products_current group by product_key, cadence, reporting_date having count(*)>1) x"), "0")
        self.assertEqual(self.q("select count(*) from intelligence_products_current where source <> 'live'"), "0")

    def test_05_reader_selects_daily_vs_weekly_vs_unknown_explicitly(self):
        rows = json.loads(self.q("select json_agg(t) from (select product_key, cadence, generated_for, as_of, last_refresh_as_of, last_failed_as_of, "
                                 "title, summary, sections, exceptions from intelligence_products_current) t"))
        now = datetime(2026, 12, 2, 20, 1, tzinfo=UTC)         # 07:01 AEDT 3 Dec: daily d2 is 10 h old, weekly w1 too
        primary, _extras = bpb._select(rows, now)
        row, _fr = primary["forward_watch"]
        self.assertIn(row["cadence"], ("daily", "weekly"))
        self.assertNotEqual(row["cadence"], "unknown")

    def test_06_flag_off_fallback_after_swap_never_wedges_on_mixed_attribution(self):
        import urllib.error
        from io import BytesIO
        # legacy-attributed live row: as_of 19:20Z 25 Nov: generated_for 25 Nov, Melbourne reporting date 26 Nov
        gw = PsqlGateway(self.q)
        ph.record_run(gw, ph.build_generation(
            {"product_key": "recurring_provider", "generated_for": "2026-11-25", "as_of": "2026-11-25T19:20:00+00:00", "title": "T", "summary": "S",
             "sections": {}, "exceptions": [], "body_md": "live"}, cadence="unknown", legacy_attribution=False, watermark=None))
        self.assertEqual(self.q("select reporting_date::text from intelligence_products where body_md='live'"), "2026-11-26")

        def err_writer(_r):
            raise urllib.error.HTTPError("u", 400, "bad", {}, BytesIO(b'{"code":"42P10"}'))

        with mock.patch.dict("os.environ", {"INTEL_PRODUCTS_ENABLED": "1"}, clear=True):
            for hh in (22, 23):           # two flag-OFF runs on the same UTC day after the live row (same content: second is a refresh)
                job.run(datetime(2026, 11, 25, hh, 0, tzinfo=UTC), getter=lambda *a: [], writer=err_writer, gateway=gw)
        # no RuntimeError (the old reporting_date-ordered selection collided here); one legacy-attributed generation per product
        self.assertEqual(self.q("select count(*) from intelligence_products where reporting_date_basis='legacy_utc_key' and reporting_date='2026-11-25'"), "3")
        # a changed generation on the same UTC day gets the next sequence number for the exact key, first try
        r = ph.record_run(gw, ph.build_generation(
            {"product_key": "recurring_provider", "generated_for": "x", "as_of": "2026-11-25T23:30:00+00:00", "title": "T", "summary": "S",
             "sections": {}, "exceptions": [], "body_md": "changed"}, cadence="unknown", legacy_attribution=True, watermark=None))
        self.assertEqual((r.generation_seq, r.attempts), (2, 1))

    def test_07_append_only_after_swap(self):
        for sql in ("update intelligence_products set title='x'", "delete from intelligence_products", "truncate intelligence_products"):
            with self.assertRaises(PgError, msg=sql):
                self.q(sql, role="service_role")

    def test_07b_part_a_refuses_to_rerun_after_part_b(self):
        with self.assertRaises(PgError) as cm:
            self.apply(SQL_A)
        self.assertEqual(cm.exception.sqlstate, "42P17")
        self.assertIn("0263b is already applied", cm.exception.text)
        self.assertEqual(self.q("select count(*) from pg_trigger where tgrelid='public.intelligence_products'::regclass and tgname='intelligence_products_archive_trg'"), "0")

    def test_08_rollback_recreates_archive_triggers_and_protects_old_writer(self):
        before = {l for l in self.q("select encode(sha256(convert_to(body_md,'UTF8')),'hex') from intelligence_products").split()}
        self.apply(SQL_R)
        names = set(self.q("select tgname from pg_trigger where tgrelid='public.intelligence_products'::regclass and not tgisinternal").split())
        self.assertTrue({"intelligence_products_archive_trg", "intelligence_products_archive_del_trg", "intelligence_products_legacy_fill_trg"} <= names, names)
        self.assertNotIn("intelligence_products_append_only", names)
        self.assertEqual(self.q("select pg_get_constraintdef(oid) from pg_constraint where conname='intelligence_products_pkey'"), "PRIMARY KEY (product_key, generated_for)")
        # old writer overwrite after rollback is ARCHIVED, not silent
        rows_before = int(self.q("select count(*) from intelligence_products_revisions"))
        self.legacy_upsert(product_key="systemic_risk", generated_for="2026-11-25", body_md="after rollback", as_of="2026-11-25T21:00:00+00:00")
        self.assertEqual(int(self.q("select count(*) from intelligence_products_revisions")), rows_before + 1)
        # every previously stored body still exists somewhere
        after = {l for l in self.q("select encode(sha256(convert_to(body_md,'UTF8')),'hex') from intelligence_products union all "
                                   "select encode(sha256(convert_to(body_md,'UTF8')),'hex') from intelligence_products_revisions").split()}
        self.assertTrue(before <= after, "a stored generation was lost by the rollback")
        # the 0263a view still returns exactly one row per (product, cadence), including exported generations
        self.assertEqual(self.q("select count(*) from (select 1 from intelligence_products_current group by product_key, cadence having count(*)>1) x"), "0")

    def test_08b_rollback_restores_truncate_protection(self):
        # state here: 0263r applied (test_08). The 0263a TRUNCATE guard and revokes must be back (N1).
        names = set(self.q("select tgname from pg_trigger where tgrelid='public.intelligence_products'::regclass and not tgisinternal").split())
        self.assertIn("intelligence_products_a_no_truncate", names)
        self.assertNotIn("intelligence_products_no_truncate", names)       # 0263b's trigger is gone, A's replaces it
        n = self.q("select count(*) from intelligence_products")
        for role in ("anon", "authenticated", "service_role"):
            with self.assertRaises(PgError, msg=role) as cm:
                self.q("truncate intelligence_products", role=role)
            self.assertEqual(cm.exception.sqlstate, "42501")
        with self.assertRaises(PgError) as cm:
            self.q("truncate intelligence_products")                       # owner: statement trigger
        self.assertEqual(cm.exception.sqlstate, "23000")
        self.assertEqual(self.q("select count(*) from intelligence_products"), n)

    def test_09_rollback_refused_when_part_b_not_applied_and_b_can_be_reapplied(self):
        with self.assertRaises(PgError) as cm:
            self.apply(SQL_R)
        self.assertEqual(cm.exception.sqlstate, "42P17")
        n_live = int(self.q("select count(*) from intelligence_products"))
        self.apply(SQL_B)           # contract again after a rollback: exported generations fold back
        self.assertGreaterEqual(int(self.q("select count(*) from intelligence_products")), n_live)
        self.assertEqual(self.q("select count(*) from (select 1 from intelligence_products group by product_key, cadence, reporting_date, generation_seq having count(*)>1) x"), "0")
        # the refresh foreign key is enforced for NEW rows even though old orphans (from the rollback) are tolerated
        with self.assertRaises(PgError) as cm:
            self.q("insert into intelligence_product_refreshes (product_key,cadence,reporting_date,as_of,outcome,generation_id) "
                   "values ('forward_watch','daily','2026-12-01',now(),'unchanged',999999)", role="service_role")
        self.assertEqual(cm.exception.sqlstate, "23503")


# ======================================================================================================================
class TestFoldDoesNotCreateDuplicateGenerations(ProductsBase):
    DB = "fixdb_fold"

    def test_01_adjacent_duplicate_revisions_are_not_folded(self):
        self.apply(SQL_A)
        self.legacy_upsert(body_md="A", as_of="2026-11-25T01:00:00+00:00")
        self.legacy_upsert(body_md="B", as_of="2026-11-25T02:00:00+00:00")       # revision of A
        # a duplicate revision of B inserted by an older/other mechanism (identical content, adjacent in time)
        self.q("insert into intelligence_products_revisions (archive_reason, source_id, product_key, generated_for, as_of, title, summary, sections, exceptions, body_md, created_at) "
               "select 'update', id, product_key, generated_for, as_of - interval '10 minutes', title, summary, sections, exceptions, body_md, created_at from intelligence_products")
        self.legacy_upsert(body_md="A", as_of="2026-11-25T03:00:00+00:00")       # content returns to A: a real, non-adjacent repeat
        self.apply(SQL_B)
        bodies = self.q("select string_agg(body_md, '' order by as_of) from intelligence_products where product_key='forward_watch'")
        # A (rev), B (dup revision dropped, B's revision kept once), A again (live): adjacent identical copies are not folded
        self.assertEqual(bodies, "ABA")


# ======================================================================================================================
@unittest.skipUnless(CONTAINER, "needs INTEL_TEST_PG_CONTAINER")
class TestDeliveryMigration(unittest.TestCase):
    DB = "fixdb_delivery"
    SQL = "0264_intelligence_delivery.DRAFT.sql"

    @classmethod
    def setUpClass(cls):
        mkdb(cls.DB)
        cls.q = staticmethod(lambda sql, role=None, timeout=120: _run(cls.DB, sql, role, timeout))
        cls.q(GRANTS + "grant usage on schema public to anon, authenticated, service_role;")
        for t in ("captains_daily_briefs", "intelligence_briefs"):
            cls.q(f"create table public.{t} (id uuid primary key default gen_random_uuid(), body text not null default 'x', created_at timestamptz default now()); "
                  f"insert into public.{t} (body) values ('legacy row'); alter table public.{t} enable row level security; "
                  f"grant all on public.{t} to service_role; grant select on public.{t} to authenticated;")

    @classmethod
    def tearDownClass(cls):
        dropdb(cls.DB)

    def apply(self):
        self.q((DRAFTS / self.SQL).read_text())

    def attempt(self, **kw):
        a = {"attempt_id": str(uuid.uuid4()), "brief_table": "ref", "brief_id": "b1", "channel": "telegram", "content_hash": "h1", "kind": "PRIMARY",
             "attempt_no": 1, "chunks_total": 2, "planned_chunks": [], "chunks": [], "state": "sending", "outcome": None}
        a.update(kw)
        cols = list(a)
        self.q(f"insert into intelligence_delivery_attempts ({','.join(cols)}) select {','.join(cols)} "
               f"from jsonb_populate_record(null::intelligence_delivery_attempts, {jlit(a)})", role="service_role")
        return a

    def test_01_atomic_and_rerunnable(self):
        # a conflicting pre-existing object makes the script fail part-way: nothing may stay applied (single transaction)
        mkdb("fixdb_delivery_conflict")
        try:
            qq = lambda sql, role=None: _run("fixdb_delivery_conflict", sql, role)
            qq("create table public.captains_daily_briefs (id uuid primary key default gen_random_uuid()); "
               "create table public.intelligence_briefs (id uuid primary key default gen_random_uuid()); "
               "create table public.intelligence_delivery_attempts (attempt_id uuid primary key);")
            with self.assertRaises(PgError):
                qq((DRAFTS / self.SQL).read_text())
            self.assertEqual(qq("select count(*) from information_schema.columns where table_name='captains_daily_briefs' and column_name='production_status'"), "0")
        finally:
            dropdb("fixdb_delivery_conflict")
        self.apply()
        self.apply()                  # re-run on a fully applied database: no error
        self.assertEqual(self.q("select count(*) from information_schema.columns where table_name='captains_daily_briefs' and column_name in ('production_status','production_status_reasons','telegram_status','telegram_at','delivery_disclosure')"), "5")

    def test_02_lock_timeout_instead_of_queueing(self):
        holder = hold_lock(self.DB, "public.captains_daily_briefs", 9, mode="row exclusive")
        t0 = time.time()
        with self.assertRaises(PgError) as cm:
            self.apply()
        # the migration is a no-op when applied, but its ALTERs still need the lock: fails fast (55P03) instead of blocking writers
        self.assertEqual(cm.exception.sqlstate, "55P03")
        self.assertLess(time.time() - t0, 8)
        holder.wait(timeout=30)

    def test_03_legacy_inserts_and_checks(self):
        self.q("insert into captains_daily_briefs (body) values ('new legacy shaped row')", role="service_role")
        self.q("update captains_daily_briefs set telegram_status='CONFIRMED', telegram_at=now(), delivery_disclosure=null where body='new legacy shaped row'", role="service_role")
        for sql in ("update captains_daily_briefs set telegram_status='SENT'",                       # planning vocabulary is not accepted
                    "update captains_daily_briefs set production_status='OK'",
                    "update intelligence_briefs set telegram_at=now()",                              # timestamp without a status
                    "update intelligence_briefs set delivery_disclosure='x'"):
            with self.assertRaises(PgError, msg=sql) as cm:
                self.q(sql, role="service_role")
            self.assertEqual(cm.exception.sqlstate, "23514", sql)

    def test_04_attempt_constraints(self):
        with self.assertRaises(PgError) as cm:                     # sending with an outcome
            self.attempt(state="sending", outcome="CONFIRMED")
        self.assertEqual(cm.exception.sqlstate, "23514")
        with self.assertRaises(PgError) as cm:                     # finished without an outcome
            self.attempt(state="finished", outcome=None)
        self.assertEqual(cm.exception.sqlstate, "23514")
        with self.assertRaises(PgError) as cm:                     # email is not a recorded channel
            self.attempt(channel="email")
        self.assertEqual(cm.exception.sqlstate, "23514")
        with self.assertRaises(PgError) as cm:
            self.attempt(chunks={"not": "an array"})
        self.assertEqual(cm.exception.sqlstate, "23514")

    def test_05_confirmed_attempt_is_immutable_and_undeletable(self):
        a = self.attempt(brief_id="b-conf", state="finished", outcome="CONFIRMED", finished_at="2026-11-25T20:00:00Z",
                         chunks=[{"index": 0, "state": "CONFIRMED", "message_id": 42}, {"index": 1, "state": "CONFIRMED", "message_id": 43}])
        aid = lit(a["attempt_id"])
        refused = [
            f"update intelligence_delivery_attempts set outcome='FAILED' where attempt_id={aid}",
            f"update intelligence_delivery_attempts set outcome='UNKNOWN' where attempt_id={aid}",
            f"update intelligence_delivery_attempts set chunks='[]'::jsonb where attempt_id={aid}",
            f"update intelligence_delivery_attempts set chunks='[{{\"index\":0,\"state\":\"FAILED\"}},{{\"index\":1,\"state\":\"CONFIRMED\",\"message_id\":43}}]'::jsonb where attempt_id={aid}",
            f"update intelligence_delivery_attempts set chunks='[{{\"index\":0,\"state\":\"CONFIRMED\",\"message_id\":99}},{{\"index\":1,\"state\":\"CONFIRMED\",\"message_id\":43}}]'::jsonb where attempt_id={aid}",
            f"update intelligence_delivery_attempts set state='sending', outcome=null where attempt_id={aid}",
            f"update intelligence_delivery_attempts set content_hash='other' where attempt_id={aid}",
            f"update intelligence_delivery_attempts set finished_at=now() where attempt_id={aid}",
            f"delete from intelligence_delivery_attempts where attempt_id={aid}",
        ]
        for sql in refused:
            with self.assertRaises(PgError, msg=sql) as cm:
                self.q(sql, role="service_role")
            self.assertIn(cm.exception.sqlstate, ("23000", "23514"), sql)
        # the blind-upsert shape the old PostgrestAttemptStore.update used
        blind = (f"insert into intelligence_delivery_attempts (attempt_id,brief_table,brief_id,channel,content_hash,kind,attempt_no,chunks_total,chunks,state,outcome) "
                 f"values ({aid},'ref','b-conf','telegram','h1','PRIMARY',1,2,'[]','finished','FAILED') on conflict (attempt_id) do update set outcome='FAILED', chunks='[]'")
        with self.assertRaises(PgError) as cm:
            self.q(blind, role="service_role")
        self.assertEqual(cm.exception.sqlstate, "23000")
        self.assertEqual(self.q(f"select outcome||':'||jsonb_array_length(chunks) from intelligence_delivery_attempts where attempt_id={aid}"), "CONFIRMED:2")

    def test_06_permitted_forward_transitions_only(self):
        a = self.attempt(brief_id="b-fwd", attempt_no=1)                       # sending -> finished UNKNOWN (a permitted PENDING->terminal)
        aid = lit(a["attempt_id"])
        self.q(f"update intelligence_delivery_attempts set chunks='[{{\"index\":0,\"state\":\"UNKNOWN\"}}]'::jsonb where attempt_id={aid}", role="service_role")   # append during sending
        self.q(f"update intelligence_delivery_attempts set state='finished', outcome='UNKNOWN', finished_at=now() where attempt_id={aid}", role="service_role")
        self.q(f"update intelligence_delivery_attempts set outcome='UNCONFIRMED', reason='provider_cannot_confirm' where attempt_id={aid}", role="service_role")   # forward
        with self.assertRaises(PgError) as cm:                                  # backward
            self.q(f"update intelligence_delivery_attempts set outcome='UNKNOWN' where attempt_id={aid}", role="service_role")
        self.assertEqual(cm.exception.sqlstate, "23000")
        with self.assertRaises(PgError):                                        # sideways to FAILED
            self.q(f"update intelligence_delivery_attempts set outcome='FAILED' where attempt_id={aid}", role="service_role")
        # reconciled by provider proof: UNCONFIRMED -> CONFIRMED with the chunk upgraded
        self.q(f"update intelligence_delivery_attempts set outcome='CONFIRMED', chunks='[{{\"index\":0,\"state\":\"CONFIRMED\",\"message_id\":7}}]'::jsonb where attempt_id={aid}", role="service_role")
        f = self.attempt(brief_id="b-failed", state="finished", outcome="FAILED", finished_at="2026-11-25T20:00:00Z")
        with self.assertRaises(PgError):                                        # FAILED is final
            self.q(f"update intelligence_delivery_attempts set outcome='CONFIRMED' where attempt_id={lit(f['attempt_id'])}", role="service_role")

    def test_07_one_confirmed_full_primary_and_one_resend(self):
        self.attempt(brief_id="b-dup", state="finished", outcome="CONFIRMED", finished_at="2026-11-25T20:00:00Z", attempt_no=1)
        with self.assertRaises(PgError) as cm:
            self.attempt(brief_id="b-dup", state="finished", outcome="CONFIRMED", finished_at="2026-11-25T20:01:00Z", attempt_no=2)
        self.assertEqual(cm.exception.sqlstate, "23505")
        # a continuation of a PARTIAL send carries planned_chunks and may also be CONFIRMED
        self.attempt(brief_id="b-part", state="finished", outcome="PARTIAL", finished_at="2026-11-25T20:00:00Z", attempt_no=1)
        self.attempt(brief_id="b-part", state="finished", outcome="CONFIRMED", finished_at="2026-11-25T20:01:00Z", attempt_no=2, planned_chunks=[1])

    def test_08_privileges_service_role_only(self):
        """N2: no signed-in or anonymous role may touch delivery records; service_role is the only reader/writer."""
        self.attempt(brief_id="b-priv")
        for role in ("anon", "authenticated"):
            for sql in ("select count(*) from intelligence_delivery_attempts", "truncate intelligence_delivery_attempts",
                        "insert into intelligence_delivery_attempts (attempt_id) values (gen_random_uuid())",
                        "update intelligence_delivery_attempts set reason='x'", "delete from intelligence_delivery_attempts"):
                with self.assertRaises(PgError, msg=f"{role}: {sql}") as cm:
                    self.q(sql, role=role)
                self.assertEqual(cm.exception.sqlstate, "42501", f"{role}: {sql}")
            for priv in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                self.assertEqual(self.q(f"select has_table_privilege('{role}','public.intelligence_delivery_attempts','{priv}')"), "f", f"{role} {priv}")
        # PUBLIC pseudo-role holds nothing, and there is no read policy left (RLS on, zero policies)
        self.assertEqual(self.q("select count(*) from pg_class c, aclexplode(c.relacl) a where c.oid='public.intelligence_delivery_attempts'::regclass and a.grantee=0"), "0")
        self.assertEqual(self.q("select count(*) from pg_policies where tablename='intelligence_delivery_attempts'"), "0")
        self.assertEqual(self.q("select relrowsecurity from pg_class where oid='public.intelligence_delivery_attempts'::regclass"), "t")
        # service_role: reads and writes, but TRUNCATE is revoked and (trigger) refused for the owner too
        self.assertGreater(int(self.q("select count(*) from intelligence_delivery_attempts", role="service_role")), 0)
        self.assertEqual(self.q("select has_table_privilege('service_role','public.intelligence_delivery_attempts','TRUNCATE')"), "f")
        with self.assertRaises(PgError) as cm:
            self.q("truncate intelligence_delivery_attempts", role="service_role")
        self.assertEqual(cm.exception.sqlstate, "42501")
        with self.assertRaises(PgError) as cm:
            self.q("truncate intelligence_delivery_attempts")
        self.assertEqual(cm.exception.sqlstate, "23000")

    def test_08b_reason_of_finished_attempt_is_append_only(self):
        a = self.attempt(brief_id="b-reason", state="finished", outcome="UNKNOWN", finished_at="2026-11-25T20:00:00Z", reason="first")
        aid = lit(a["attempt_id"])
        self.q(f"update intelligence_delivery_attempts set reason='first;provider_cannot_confirm' where attempt_id={aid}", role="service_role")   # extend: ok
        self.q(f"update intelligence_delivery_attempts set reason='first;provider_cannot_confirm' where attempt_id={aid}", role="service_role")   # unchanged: ok
        for new in ("'rewritten'", "null", "'first'"):
            with self.assertRaises(PgError, msg=new) as cm:
                self.q(f"update intelligence_delivery_attempts set reason={new} where attempt_id={aid}", role="service_role")
            self.assertEqual(cm.exception.sqlstate, "23000", new)
        self.assertEqual(self.q(f"select reason from intelligence_delivery_attempts where attempt_id={aid}"), "first;provider_cannot_confirm")
        # a sending attempt may still set its reason freely, and a null reason may be started
        b = self.attempt(brief_id="b-reason2")
        self.q(f"update intelligence_delivery_attempts set reason='x' where attempt_id={lit(b['attempt_id'])}", role="service_role")
        c = self.attempt(brief_id="b-reason3", state="finished", outcome="UNKNOWN", finished_at="2026-11-25T20:00:00Z")
        self.q(f"update intelligence_delivery_attempts set reason='added later' where attempt_id={lit(c['attempt_id'])}", role="service_role")

    def test_09_concurrent_claims_exactly_one_wins(self):
        results = []
        barrier = threading.Barrier(5)

        def work(i):
            barrier.wait()
            try:
                self.attempt(brief_id="b-race", attempt_no=1, content_hash="hr")
                results.append("won")
            except PgError as e:
                results.append(e.sqlstate)

        ts = [threading.Thread(target=work, args=(i,)) for i in range(5)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sorted(results), ["23505"] * 4 + ["won"])


if __name__ == "__main__":
    unittest.main()
