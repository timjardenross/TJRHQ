"""Migration + writer cut-over tests against a throwaway Postgres (draft 0263).

Skipped unless INTEL_TEST_PG_CONTAINER names a disposable container (psql reachable via `docker exec`) and
INTEL_PRODUCTS_EVIDENCE_DIR points at a directory holding the preserved product rows
(intelligence_products_20261124_25.raw.json + body_hashes.tsv). Creates and drops its own database; never touches anything else.
"""

import json
import os
import re
import subprocess
import sys
import threading
import unittest
import urllib.error
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "intelligence" / "analytics"))

from intelligence import intel_products_job as job
from intelligence import product_history as ph

CONTAINER = os.environ.get("INTEL_TEST_PG_CONTAINER")
EVID = os.environ.get("INTEL_PRODUCTS_EVIDENCE_DIR")
# each psql round trip through docker exec costs ~1 s; the repo default of 30 s per test is too short for this scenario
pytestmark = pytest.mark.timeout(600)
DB = "wp1_migration_test"
UTC = timezone.utc
DRAFTS = ROOT / "docs" / "migration-drafts"


class PgError(Exception):
    def __init__(self, sqlstate, text):
        super().__init__(f"{sqlstate}: {text[:200]}")
        self.sqlstate = sqlstate
        self.text = text


def psql(sql, db=DB, role=None):
    prefix = f"set role {role};\n" if role else ""
    p = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "postgres", "-d", db, "-X", "-q", "-A", "-t",
         "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose"],
        input=prefix + sql, capture_output=True, text=True, timeout=120, check=False,
    )
    if p.returncode != 0:
        m = re.search(r"ERROR:\s+(\w{5}):", p.stderr)
        raise PgError(m.group(1) if m else "?????", p.stderr)
    return p.stdout.strip()


def q(sql, role=None):
    return psql(sql, role=role)


def lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def jlit(obj):
    tag = "j" + uuid.uuid4().hex[:8]
    return f"${tag}${json.dumps(obj, ensure_ascii=False)}${tag}$::jsonb"


def part(name, _text=None):
    """SQL of one separately-fileable migration: A = 0263a (expand), B = 0263b (contract), R = 0263r (rollback)."""
    files = {"A": "0263a_intelligence_products_history_expand.DRAFT.sql",
             "B": "0263b_intelligence_products_history_contract.DRAFT.sql",
             "R": "0263r_intelligence_products_history_rollback.DRAFT.sql"}
    return (DRAFTS / files[name]).read_text()


class PsqlGateway:
    """Gateway over real SQL (as the service role): INSERT only, optimistic unique-key retry lives in product_history."""

    def latest_generation(self, product_key, cadence):
        out = q(f"select row_to_json(t) from (select * from intelligence_products where product_key={lit(product_key)} "
                f"and cadence={lit(cadence)} order by as_of desc, id desc limit 1) t", role="service_role")
        return json.loads(out) if out else None

    def max_generation_seq(self, product_key, cadence, reporting_date):
        return int(q(f"select coalesce(max(generation_seq),0) from intelligence_products where product_key={lit(product_key)} "
                     f"and cadence={lit(cadence)} and reporting_date={lit(reporting_date)}", role="service_role"))

    def insert_generation(self, rec):
        cols = [c for c in rec if c not in ("id",)]
        try:
            out = q(f"with ins as (insert into intelligence_products ({','.join(cols)}) select {','.join(cols)} "
                    f"from jsonb_populate_record(null::intelligence_products, {jlit(rec)}) returning *) "
                    f"select row_to_json(ins) from ins", role="service_role")
        except PgError as e:
            if e.sqlstate == "23505":
                raise ph.UniqueViolation(str(e), legacy_key="(product_key, generated_for)" in e.text) from e
            raise
        return json.loads(out)

    def overwrite_generation(self, rec):
        """What PostgREST does for on_conflict=product_key,generated_for with merge-duplicates: only the payload columns are set."""
        cols = [c for c in rec if c not in ("id",)]
        sets = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("product_key", "generated_for"))
        out = q(f"with ins as (insert into intelligence_products ({','.join(cols)}) select {','.join(cols)} "
                f"from jsonb_populate_record(null::intelligence_products, {jlit(rec)}) "
                f"on conflict (product_key,generated_for) do update set {sets} returning *) select row_to_json(ins) from ins",
                role="service_role")
        return json.loads(out)

    def insert_refresh(self, rec):
        cols = list(rec)
        q(f"insert into intelligence_product_refreshes ({','.join(cols)}) select {','.join(cols)} "
          f"from jsonb_populate_record(null::intelligence_product_refreshes, {jlit(rec)})", role="service_role")


def legacy_upsert(rec):
    """What the original writer sends through PostgREST: ON CONFLICT (product_key,generated_for) DO UPDATE."""
    cols = list(rec)
    sets = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("product_key", "generated_for"))
    q(f"insert into intelligence_products ({','.join(cols)}) select {','.join(cols)} "
      f"from jsonb_populate_record(null::intelligence_products, {jlit(rec)}) "
      f"on conflict (product_key,generated_for) do update set {sets}", role="service_role")


def body_sha(where):
    return q(f"select encode(sha256(convert_to(body_md,'UTF8')),'hex') from intelligence_products where {where}")


@unittest.skipUnless(CONTAINER and EVID, "needs INTEL_TEST_PG_CONTAINER and INTEL_PRODUCTS_EVIDENCE_DIR")
class TestMigrationAndCutover(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["docker", "exec", CONTAINER, "psql", "-U", "postgres", "-c", f"drop database if exists {DB}"], check=True, capture_output=True)
        subprocess.run(["docker", "exec", CONTAINER, "createdb", "-U", "postgres", DB], check=True, capture_output=True)
        cls.sql = None
        # Hosted Supabase gives new public tables to these roles by default privileges; mirror that, RLS does the gating.
        psql("alter default privileges in schema public grant all on tables to service_role; "
             "alter default privileges in schema public grant select on tables to authenticated")
        psql((DRAFTS / "0261_intelligence_products.DRAFT.sql").read_text())
        psql("grant usage on schema public to anon, authenticated, service_role; "
             "grant all on all tables in schema public to service_role; grant select on all tables in schema public to authenticated")
        cls.raw = json.loads((Path(EVID) / "intelligence_products_20261124_25.raw.json").read_text(encoding="utf-8"))
        cls.expected = {}
        for line in (Path(EVID) / "body_hashes.tsv").read_text().splitlines():
            f = line.split("\t")
            cls.expected[(f[0], f[1])] = f[3]
        for r in cls.raw:
            psql(f"insert into intelligence_products (product_key,generated_for,as_of,title,summary,sections,exceptions,body_md,created_at) "
                 f"select product_key,generated_for,as_of,title,summary,sections,exceptions,body_md,created_at "
                 f"from jsonb_populate_record(null::intelligence_products, {jlit(r)})")
        psql("grant all on all tables in schema public to service_role; grant select on all tables in schema public to authenticated")

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["docker", "exec", CONTAINER, "psql", "-U", "postgres", "-c", f"drop database if exists {DB}"], capture_output=True, check=False)

    # -- helpers
    def all_body_shas(self):
        """sha256 of every stored body across generations and the archive."""
        out = q("select encode(sha256(convert_to(body_md,'UTF8')),'hex') from intelligence_products")
        if q("select to_regclass('public.intelligence_products_revisions') is not null") == "t":
            out += "\n" + q("select encode(sha256(convert_to(body_md,'UTF8')),'hex') from intelligence_products_revisions")
        return set(out.split())

    def assert_six_preserved_byte_exact(self):
        shas = self.all_body_shas()
        for key, want in self.expected.items():
            self.assertIn(want, shas, f"body {key} not preserved byte-exactly")

    def assert_json_columns_preserved(self, table="intelligence_products"):
        for r in self.raw:
            row = json.loads(q(
                f"select row_to_json(t) from (select sections, exceptions, title, summary, created_at, as_of from {table} "
                f"where product_key={lit(r['product_key'])} and generated_for={lit(r['generated_for'])} and as_of={lit(r['as_of'])}::timestamptz "
                f"order by 1 limit 1) t"))
            self.assertEqual(row["sections"], r["sections"])
            self.assertEqual(row["exceptions"], r["exceptions"])
            self.assertEqual((row["title"], row["summary"]), (r["title"], r["summary"]))

    # -- 01 baseline
    def test_01_baseline_matches_preserved_evidence(self):
        self.assertEqual(q("select count(*) from intelligence_products"), "6")
        self.assert_six_preserved_byte_exact()
        self.assert_json_columns_preserved()
        # the loaded copy also matches the preserved md5 column
        md5 = {(f.split("\t")[0], f.split("\t")[1]): f.split("\t")[2]
               for f in (Path(EVID) / "body_hashes.tsv").read_text().splitlines()}
        for (d, k), want in md5.items():
            self.assertEqual(q(f"select md5(body_md) from intelligence_products where product_key={lit(k)} and generated_for={lit(d)}"), want)

    # -- 02 expand
    def test_02_part_a_expand_preserves_rows_and_labels_history(self):
        psql(part("A", self.sql))
        self.assert_six_preserved_byte_exact()
        self.assert_json_columns_preserved()
        rows = json.loads(q("select json_agg(t) from (select generated_for::text g, reporting_date::text rd, reporting_date_basis rb, cadence, "
                            "cadence_basis cb, content_hash, generation_seq from intelligence_products order by 1,2) t"))
        self.assertEqual(len(rows), 6)
        for r in rows:
            self.assertEqual((r["cadence"], r["cb"], r["rb"], r["content_hash"], r["generation_seq"]),
                             ("unknown", "legacy_unknown", "as_of_melbourne_date", None, 1))
            self.assertEqual(r["rd"], r["g"])   # for these six, Melbourne date of as_of equals the stored date
        # created_at untouched by backfill
        for r in self.raw:
            self.assertEqual(q(f"select created_at = {lit(r['created_at'])}::timestamptz from intelligence_products where product_key={lit(r['product_key'])} and generated_for={lit(r['generated_for'])}"), "t")

    # -- 03 old writer during expand: overwrite is archived, not lost
    def test_03_old_writer_overwrite_during_expand_is_archived_byte_exact(self):
        victim = next(r for r in self.raw if r["product_key"] == "forward_watch" and r["generated_for"] == "2026-11-25")
        new = {"product_key": "forward_watch", "generated_for": "2026-11-25", "as_of": "2026-11-25T19:20:05+00:00", "title": "Forward watch",
               "summary": "scheduled run content", "sections": {"x": 1}, "exceptions": [], "body_md": "replacement body"}
        legacy_upsert(new)
        self.assertEqual(q("select body_md from intelligence_products where product_key='forward_watch' and generated_for='2026-11-25'"), "replacement body")
        arch = q("select encode(sha256(convert_to(body_md,'UTF8')),'hex') from intelligence_products_revisions where product_key='forward_watch' and generated_for='2026-11-25'")
        self.assertEqual(arch, self.expected[("2026-11-25", "forward_watch")])
        self.assertEqual(json.loads(q("select sections from intelligence_products_revisions where product_key='forward_watch' and generated_for='2026-11-25'")), victim["sections"])
        # the legacy-written row is labelled, never presented as daily/weekly
        row = json.loads(q("select row_to_json(t) from (select reporting_date::text rd, reporting_date_basis b, cadence c from intelligence_products where product_key='forward_watch' and generated_for='2026-11-25') t"))
        self.assertEqual(row, {"rd": "2026-11-26", "b": "as_of_melbourne_date", "c": "unknown"})
        self.assert_six_preserved_byte_exact()

    def test_04_old_writer_delete_is_archived_too(self):
        psql("insert into intelligence_products (product_key,generated_for,as_of,title,summary,sections,exceptions,body_md) "
             "values ('systemic_risk','2026-11-30','2026-11-30T01:00:00Z','t','s','{}','[]','to be deleted')", )
        q("delete from intelligence_products where generated_for='2026-11-30'", role="service_role")
        self.assertEqual(q("select archive_reason||':'||body_md from intelligence_products_revisions where archive_reason='delete'"), "delete:to be deleted")

    # -- 05 contract
    def test_05_part_b_contract(self):
        psql(part("B", self.sql))
        # evidence rows all still stored; the overwritten original is folded back as its own generation
        self.assert_six_preserved_byte_exact()
        self.assertEqual(q("select count(*) from intelligence_products where product_key='forward_watch'"), "3")
        # 24 Nov, 25 Nov (original) and 26 Nov (the legacy overwrite, generated 06:20 AEDT on the 26th): three Melbourne days
        self.assertEqual(q("select string_agg(reporting_date::text||':'||generation_seq, ',' order by as_of) from intelligence_products where product_key='forward_watch'"),
                         "2026-11-24:1,2026-11-25:1,2026-11-26:1")
        # lineage: each supersedes the previous; the first has none
        self.assertEqual(q("select count(*) from intelligence_products g join intelligence_products p on p.id=g.supersedes_id where g.product_key='forward_watch' and p.as_of < g.as_of"), "2")
        self.assertEqual(q("select count(*) from intelligence_products where product_key='forward_watch' and supersedes_id is null"), "1")
        self.assertEqual(q("select count(*) from intelligence_products where cadence is null or reporting_date is null"), "0")
        # the overwrite row keeps the legacy generated_for next to its Melbourne reporting date (both visible, nothing rewritten)
        self.assertEqual(q("select generated_for::text||'/'||reporting_date::text from intelligence_products where body_md='replacement body'"), "2026-11-25/2026-11-26")

    def test_06_old_writer_incompatible_after_key_swap(self):
        with self.assertRaises(PgError) as cm:
            legacy_upsert({"product_key": "forward_watch", "generated_for": "2026-11-27", "as_of": "2026-11-27T19:20:00+00:00",
                           "title": "t", "summary": "s", "sections": {}, "exceptions": [], "body_md": "b"})
        self.assertEqual(cm.exception.sqlstate, "42P10")
        self.assertEqual(q("select count(*) from intelligence_products where generated_for='2026-11-27'"), "0")

    def test_07_append_only_enforced(self):
        q("insert into intelligence_product_refreshes (product_key,cadence,reporting_date,as_of,outcome) "
          "values ('forward_watch','daily','2026-11-26','2026-11-26T00:00:00Z','failed')", role="service_role")
        for sql in ("update intelligence_products set title='x'", "delete from intelligence_products",
                    "update intelligence_product_refreshes set outcome='unchanged'", "delete from intelligence_products_revisions",
                    "truncate intelligence_product_refreshes", "truncate intelligence_products_revisions"):
            with self.assertRaises(PgError, msg=sql) as cm:
                q(sql, role="service_role")
            # TRUNCATE is now refused at the privilege layer (42501, revoked from service_role by the blocker fix) and, for the owner,
            # by the BEFORE TRUNCATE guard (23000); UPDATE/DELETE are refused by the append-only trigger (23000).
            expected = ("42501", "23000") if sql.startswith("truncate") else ("23000",)
            self.assertIn(cm.exception.sqlstate, expected, sql)
        with self.assertRaises(PgError):      # referenced by foreign keys, so TRUNCATE is refused by the database itself
            q("truncate intelligence_products", role="service_role")

    # -- 08 new writer
    def test_08_new_writer_generation_vs_refresh_and_reconstruction(self):
        gw = PsqlGateway()
        t1 = datetime(2026, 12, 1, 19, 20, 30, tzinfo=UTC)   # 06:20 AEDT 2 Dec
        body1 = "v1 body é中\U0001F600 \r\n trailing  "
        mk = lambda body, t: ph.build_generation(
            {"product_key": "recurring_provider", "generated_for": "x", "as_of": t.isoformat(), "title": "T", "summary": "S",
             "sections": {"a": [1, 2.5, None]}, "exceptions": [{"dedupe_key": "k"}], "body_md": body},
            cadence="daily", legacy_attribution=False, watermark={"event_count": 10, "id_hash": "h1"})
        r1 = ph.record_run(gw, mk(body1, t1))
        r2 = ph.record_run(gw, mk(body1, datetime(2026, 12, 1, 19, 40, tzinfo=UTC)))     # identical content, later refresh
        r3 = ph.record_run(gw, mk("v2 body", datetime(2026, 12, 1, 20, 10, tzinfo=UTC)))  # changed, same reporting date
        self.assertEqual([r.outcome for r in (r1, r2, r3)], ["new_generation", "unchanged", "new_generation"])
        self.assertEqual((r1.generation_seq, r2.generation_seq, r3.generation_seq), (1, 1, 2))
        # generation 1 byte-exact (incl. non-ASCII, CRLF, trailing spaces)
        got = q("select encode(convert_to(body_md,'UTF8'),'hex') from intelligence_products where product_key='recurring_provider' and cadence='daily' and generation_seq=1")
        self.assertEqual(got, body1.encode("utf-8").hex())
        self.assertEqual(q("select count(*) from intelligence_product_refreshes where product_key='recurring_provider' and cadence='daily'"), "3")
        # current view: latest generation + latest successful refresh (the identical one must not move content as_of)
        cur = json.loads(q("select row_to_json(t) from (select generation_seq gs, as_of, last_refresh_as_of lr, last_refresh_outcome o from intelligence_products_current where product_key='recurring_provider' and cadence='daily') t"))
        self.assertEqual(cur["gs"], 2)
        self.assertEqual(cur["o"], "new_generation")
        # reconstruction: what was current at 19:50Z on 1 Dec and on which input watermark?
        at = json.loads(q("select row_to_json(t) from (select generation_seq gs, input_watermark w, content_hash h, change_summary cs from intelligence_products "
                          "where product_key='recurring_provider' and cadence='daily' and as_of <= '2026-12-01T19:50:00Z' order by as_of desc limit 1) t"))
        self.assertEqual((at["gs"], at["w"]["id_hash"], at["h"]), (1, "h1", r1.content_hash))
        self.assertTrue(at["cs"].pop("write_id"))
        self.assertEqual(at["cs"], {"first_generation": True})
        later = json.loads(q("select change_summary from intelligence_products where product_key='recurring_provider' and cadence='daily' and generation_seq=2"))
        self.assertEqual(later["changed_fields"], ["body_md"])
        # when was evidence reassessed? refresh rows for the unchanged run reference generation 1
        self.assertEqual(q("select count(*) from intelligence_product_refreshes where outcome='unchanged' and generation_seq=1 and product_key='recurring_provider'"), "1")

    def test_09_flag_off_after_key_swap_appends_with_legacy_attribution(self):
        def err_writer(_rec):
            raise urllib.error.HTTPError("u", 400, "bad", {}, BytesIO(b'{"code":"42P10"}'))

        as_of = datetime(2026, 12, 3, 20, 20, tzinfo=UTC)
        before = q("select count(*) from intelligence_products")
        with mock.patch.dict("os.environ", {"INTEL_PRODUCTS_ENABLED": "1"}, clear=True):
            job.run(as_of, getter=lambda *a: [], writer=err_writer, gateway=PsqlGateway())
            job.run(as_of, getter=lambda *a: [], writer=err_writer, gateway=PsqlGateway())   # same content again
        after = q("select count(*) from intelligence_products")
        self.assertEqual(int(after) - int(before), 3)        # 3 products once; the rerun added refreshes only
        self.assertEqual(q("select count(*) from intelligence_products where reporting_date_basis='legacy_utc_key' and generated_for='2026-12-03'"), "3")
        self.assertEqual(q("select count(*) from intelligence_product_refreshes where outcome='unchanged' and reporting_date='2026-12-03'"), "3")

    # -- 10 concurrency
    def test_10_concurrent_writers_same_key_same_content(self):
        gw_results, barrier = [], threading.Barrier(6)
        base = {"product_key": "systemic_risk", "generated_for": "x", "title": "T", "summary": "S", "sections": {}, "exceptions": [], "body_md": "concurrent body"}

        def work(i):
            g = ph.build_generation(dict(base, as_of=datetime(2026, 12, 5, 19, 20, i, tzinfo=UTC).isoformat()), cadence="daily",
                                    legacy_attribution=False, watermark={"i": i})
            barrier.wait()
            gw_results.append(ph.record_run(PsqlGateway(), g))

        ts = [threading.Thread(target=work, args=(i,)) for i in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(gw_results), 6)
        self.assertEqual(sorted(r.outcome for r in gw_results), ["new_generation"] + ["unchanged"] * 5)
        self.assertEqual(q("select count(*) from intelligence_products where product_key='systemic_risk' and cadence='daily' and reporting_date='2026-12-06'"), "1")
        self.assertEqual(q("select count(*) from intelligence_product_refreshes where product_key='systemic_risk' and reporting_date='2026-12-06'"), "6")

    def test_11_concurrent_writers_same_key_different_content_no_loss_no_duplicate_seq(self):
        results, barrier = [], threading.Barrier(5)

        def work(i):
            rec = {"product_key": "systemic_risk", "generated_for": "x", "title": "T", "summary": "S", "sections": {}, "exceptions": [],
                   "body_md": f"racing body {i}", "as_of": datetime(2026, 12, 8, 19, 20, i, tzinfo=UTC).isoformat()}
            g = ph.build_generation(rec, cadence="daily", legacy_attribution=False, watermark=None)
            barrier.wait()
            results.append(ph.record_run(PsqlGateway(), g))

        ts = [threading.Thread(target=work, args=(i,)) for i in range(5)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        seqs = sorted(r.generation_seq for r in results if r.outcome == "new_generation")
        self.assertEqual(seqs, [1, 2, 3, 4, 5])             # every distinct content kept, in a gap-free unique sequence
        bodies = q("select string_agg(body_md, '|' order by body_md) from intelligence_products where product_key='systemic_risk' and reporting_date='2026-12-09'")
        self.assertEqual(bodies, "|".join(f"racing body {i}" for i in range(5)))
        # lineage: predecessor = newest generation by assessment time at insert time; always an earlier-inserted row, never self/cyclic
        self.assertEqual(q("select count(*) from intelligence_products where product_key='systemic_risk' and reporting_date='2026-12-09' "
                           "and supersedes_id is not null and supersedes_id >= id"), "0")
        self.assertEqual(q("select count(*) from intelligence_products c where product_key='systemic_risk' and reporting_date='2026-12-09' "
                           "and supersedes_id is not null and not exists (select 1 from intelligence_products p where p.id=c.supersedes_id)"), "0")

    # -- 12 RLS
    def test_12_rls_authenticated_reads_only(self):
        self.assertGreater(int(q("select count(*) from intelligence_products_current", role="authenticated")), 0)
        self.assertGreater(int(q("select count(*) from intelligence_product_refreshes", role="authenticated")), 0)
        for sql in ("insert into intelligence_product_refreshes (product_key,cadence,reporting_date,as_of,outcome) values ('forward_watch','daily','2026-12-01',now(),'failed')",):
            with self.assertRaises(PgError) as cm:
                q(sql, role="authenticated")
            self.assertEqual(cm.exception.sqlstate, "42501")
        with self.assertRaises(PgError) as cm:      # anon has no grant at all
            q("select count(*) from intelligence_products", role="anon")
        self.assertEqual(cm.exception.sqlstate, "42501")

    # -- 13 growth query works
    def test_13_growth_sql_and_report(self):
        out = q(ph.GROWTH_SQL)
        self.assertIn("intelligence_products|", out)
        rows = json.loads(q("select json_agg(t) from (select product_key, as_of, title, summary, sections, exceptions, body_md from intelligence_products) t"))
        rep = ph.storage_growth_report(rows, refresh_count=int(q("select count(*) from intelligence_product_refreshes")))
        self.assertEqual(rep.generations, int(q("select count(*) from intelligence_products")))
        self.assertGreater(rep.projected_bytes_per_year, 0)

    # -- 14 rollback
    def test_14_rollback_part_r_restores_original_key_without_losing_generations(self):
        before_shas = self.all_body_shas()
        before_gens = int(q("select count(*) from intelligence_products"))
        psql(part("R", self.sql))
        # original key back: legacy writer works again
        legacy_upsert({"product_key": "forward_watch", "generated_for": "2026-12-20", "as_of": "2026-12-20T19:20:00+00:00",
                       "title": "t", "summary": "s", "sections": {}, "exceptions": [], "body_md": "after rollback"})
        # every stored body (including non-latest generations) is still held, byte-exact, in the archive or the table
        self.assertTrue(before_shas <= self.all_body_shas())
        self.assert_six_preserved_byte_exact()
        exported = int(q("select count(*) from intelligence_products_revisions where archive_reason='rollback_export'"))
        self.assertGreater(exported, 0)
        self.assertEqual(int(q("select count(*) from intelligence_products")) + exported - 1, before_gens)   # -1: the row just written
        self.assertEqual(q("select count(*) from (select 1 from intelligence_products group by product_key, generated_for having count(*)>1) x"), "0")


if __name__ == "__main__":
    unittest.main()
