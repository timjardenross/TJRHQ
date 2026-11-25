"""Shared harness for tests/test_wp11_cutover_db.py (integrated cut-over validation on an isolated Postgres).

Nothing here talks to production. It provides:
  * psql over `docker exec` into the disposable container named by INTEL_TEST_PG_CONTAINER (own databases `wp11_*` only),
  * a faithful replica of the production tables the cut-over touches, rebuilt from information_schema / pg_constraint /
    pg_indexes / pg_policies / relacl SELECTs taken on 2026-11-25 (embedded below),
  * FakeRest: an in-process PostgREST emulator mapping the Python writers' and readers' HTTP calls onto SQL executed as the
    request role (service_role / authenticated) with the API session limits of the hosted project (lock_timeout and
    statement_timeout 8 s). PostgREST itself is NOT available in the container: status codes and error bodies are emulated,
  * the four actors of the cut-over (old/new Python writer, old/new portal reader) with exactly the query semantics of the
    source files they stand for.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "intelligence" / "analytics"))

from intelligence import intel_products_job as job

CONTAINER = os.environ.get("INTEL_TEST_PG_CONTAINER")
EVID = os.environ.get("INTEL_PRODUCTS_EVIDENCE_DIR")
DRAFTS = ROOT / "docs" / "migration-drafts"
UTC = timezone.utc
RUN = os.getpid()
TPL = f"wp11_t{RUN}"
API_SETTINGS = "set lock_timeout='8s'; set statement_timeout='8s';"   # authenticator role settings of the hosted project

MIG = {
    "0263a": "0263a_intelligence_products_history_expand.DRAFT.sql",
    "0263b": "0263b_intelligence_products_history_contract.DRAFT.sql",
    "0263r": "0263r_intelligence_products_history_rollback.DRAFT.sql",
    "0264": "0264_intelligence_delivery.DRAFT.sql",
    "0263h": "0263h_intelligence_history_privilege_hardening.PROPOSAL.sql",
    "0263z": "0263z_intelligence_products_history_full_rollback.PROPOSAL.sql",
    "0264r": "0264r_intelligence_delivery_rollback.PROPOSAL.sql",
}


class PgError(Exception):
    def __init__(self, sqlstate, text):
        super().__init__(f"{sqlstate}: {text[:300]}")
        self.sqlstate = sqlstate
        self.text = text


import atexit
import select
import threading

_TLS = threading.local()
_ALL_SESSIONS = []
_END = "@@END@@"


class _Session:
    """One persistent psql connection (docker exec) so a test run is not dominated by process start-up. ON_ERROR_STOP makes psql
    exit on the first error, which closes the connection (aborting any open transaction); the next call opens a fresh one."""

    def __init__(self, db):
        self.db = db
        self.p = subprocess.Popen(
            ["docker", "exec", "-i", CONTAINER, "sh", "-c",
             f"psql -U postgres -d {db} -X -q -A -t -v ON_ERROR_STOP=1 -v VERBOSITY=verbose 2>&1"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
        _ALL_SESSIONS.append(self)

    def run(self, sql, timeout):
        try:
            self.p.stdin.write((sql + f"\n;\n\\echo {_END}\n").encode())
            self.p.stdin.flush()
        except (BrokenPipeError, ValueError):
            return None, "connection closed"
        import os as _os
        import time as _time
        buf = b""
        end = (_END + "\n").encode()
        deadline = _time.time() + timeout
        fd = self.p.stdout.fileno()
        while True:
            left = deadline - _time.time()
            if left <= 0:
                self.close()
                return None, "psql timeout"
            r, _, _ = select.select([fd], [], [], min(left, 1.0))
            if not r:
                continue
            chunk = _os.read(fd, 65536)
            if not chunk:
                self.close()
                return None, buf.decode("utf-8", "replace")
            buf += chunk
            if buf.startswith(end) or b"\n" + end in buf:
                return buf.split(end)[0].decode("utf-8"), None

    def close(self):
        try:
            self.p.stdin.close()
        except Exception:  # noqa: BLE001, S110
            pass
        try:
            self.p.kill()
            self.p.wait(timeout=5)
        except Exception:  # noqa: BLE001, S110
            pass


def _close_all():
    for s in _ALL_SESSIONS:
        s.close()


atexit.register(_close_all)


def close_sessions(db):
    for x in _ALL_SESSIONS:
        if x.db == db:
            x.close()
    getattr(_TLS, "s", {}).pop(db, None)


def psql(sql, db, role=None, settings="", timeout=180):
    sess = getattr(_TLS, "s", {}).get(db)
    if sess is None or sess.p.poll() is not None:
        sess = _Session(db)
        _TLS.__dict__.setdefault("s", {})[db] = sess
    pre = "reset all;\nreset role;\n" + (f"set role {role};\n" if role else "") + settings + "\n"
    out, err = sess.run(pre + sql, timeout)
    if err is not None:
        _TLS.s.pop(db, None)
        m = re.search(r"ERROR:\s+(\w{5}):", err)
        raise PgError(m.group(1) if m else "?????", err)
    return out.strip()


def psql_once(sql, db, role=None, settings="", timeout=180):
    """Fresh process per call (for scripts whose session state must not leak)."""
    pre = (f"set role {role};\n" if role else "") + settings
    p = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "postgres", "-d", db, "-X", "-q", "-A", "-t",
         "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose"],
        input=pre + sql, capture_output=True, text=True, timeout=timeout, check=False)
    if p.returncode != 0:
        m = re.search(r"ERROR:\s+(\w{5}):", p.stderr)
        raise PgError(m.group(1) if m else "?????", p.stderr)
    return p.stdout.strip()


def lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def jlit(obj):
    tag = "j" + uuid.uuid4().hex[:8]
    return f"${tag}${json.dumps(obj, ensure_ascii=False)}${tag}$::jsonb"


def sha(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def drop_db(name):
    close_sessions(name)
    subprocess.run(["docker", "exec", CONTAINER, "psql", "-U", "postgres", "-c", f"drop database if exists {name} with (force)"],
                   capture_output=True, check=False)


def create_db(name, template=None):
    drop_db(name)
    cmd = ["docker", "exec", CONTAINER, "createdb", "-U", "postgres", name]
    if template:
        cmd[-1:] = ["-T", template, name]
    subprocess.run(cmd, check=True, capture_output=True)


# ---------------------------------------------------------------------------------------------------------------------
# Production replica (catalog facts SELECTed from the production project on 2026-11-25; PostgreSQL 17.6)
# ---------------------------------------------------------------------------------------------------------------------
PROD_ACL = "{postgres=arwdDxtm/postgres,anon=rm/postgres,authenticated=arwdDxtm/postgres,service_role=arwdDxtm/postgres}"
PROD_SNAPSHOT = {
    "intelligence_products": {
        "columns": ["product_key text NO", "generated_for date NO", "as_of timestamp with time zone NO", "title text NO",
                    "summary text NO", "sections jsonb NO", "exceptions jsonb NO '[]'::jsonb", "body_md text NO",
                    "created_at timestamp with time zone NO now()"],
        "constraints": ["intelligence_products_pkey PRIMARY KEY (product_key, generated_for)",
                        ("intelligence_products_product_key_check CHECK ((product_key = ANY (ARRAY['recurring_provider'::text, "
                        "'systemic_risk'::text, 'forward_watch'::text])))")],
        "indexes": ["CREATE UNIQUE INDEX intelligence_products_pkey ON public.intelligence_products USING btree (product_key, generated_for)"],
        "policies": ["intelligence_products_read SELECT {authenticated} true"],
        "acl": PROD_ACL, "rls": True, "triggers": [],
    },
}

REPLICA_DDL = r"""
-- default privileges as hosted Supabase gives them to objects the migration role (postgres) creates in schema public
alter default privileges in schema public grant select, maintain on tables to anon;
alter default privileges in schema public grant all on tables to authenticated, service_role;
grant usage on schema public to anon, authenticated, service_role;

create table public.intelligence_products (
    product_key   text        not null,
    generated_for date        not null,
    as_of         timestamptz not null,
    title         text        not null,
    summary       text        not null,
    sections      jsonb       not null,
    exceptions    jsonb       not null default '[]'::jsonb,
    body_md       text        not null,
    created_at    timestamptz not null default now(),
    constraint intelligence_products_pkey primary key (product_key, generated_for),
    constraint intelligence_products_product_key_check check (product_key = any (array['recurring_provider','systemic_risk','forward_watch']))
);
alter table public.intelligence_products enable row level security;
create policy intelligence_products_read on public.intelligence_products for select to authenticated using (true);

create table public.captains_daily_briefs (
    id uuid not null default gen_random_uuid(),
    brief_type text not null,
    generated_at timestamptz not null default now(),
    brief_date date not null default current_date,
    brief_text text not null,
    signals_count integer default 0,
    health_snapshot jsonb,
    created_at timestamptz not null default now(),
    evidence_window_hours integer,
    collection_caveat text,
    constraint captains_daily_briefs_pkey primary key (id),
    constraint captains_daily_briefs_brief_type_check check (brief_type = any (array['morning','midday','eod','weekly','weekly_debrief']))
);
create index idx_cdb_brief_date on public.captains_daily_briefs (brief_date desc);
create index idx_cdb_generated_at on public.captains_daily_briefs (generated_at desc);
alter table public.captains_daily_briefs enable row level security;
create policy authenticated_read on public.captains_daily_briefs for select to authenticated using (true);

create table public.intelligence_briefs (
    brief_id uuid not null default gen_random_uuid(),
    generated_at timestamptz not null default now(),
    period_start date not null, period_end date not null,
    sources_checked integer not null default 0, sources_available integer not null default 0,
    sources_failed integer not null default 0, sources_stale integer not null default 0,
    events_evaluated integer not null default 0, events_included integer not null default 0, events_suppressed integer not null default 0,
    executive_snapshot text, emerging_themes jsonb, forward_watch jsonb, cps230_implications jsonb, bottom_line text, top_events jsonb,
    overall_risk text, llm_used boolean not null default false, provider_used text, confidence numeric,
    narrative_available boolean not null default false, created_by text not null default 'OR-Intelligence-Agent',
    trigger_type text, approval_status text not null default 'IN_REVIEW', approval_audit jsonb not null default '{}'::jsonb,
    signal_ids jsonb, published_at timestamptz, morning_cycle_id text, coverage jsonb, comparison jsonb, domain_picture jsonb, known_unknowns jsonb,
    constraint intelligence_briefs_pkey primary key (brief_id),
    constraint intelligence_briefs_approval_status_check check (approval_status = any (array['IN_REVIEW','QA_PASSED','PUBLISHED'])),
    constraint intelligence_briefs_overall_risk_check check (overall_risk = any (array['GREEN','AMBER','RED','UNKNOWN'])),
    constraint intelligence_briefs_trigger_type_check check (trigger_type = any (array['scheduled','on_demand','test']))
);
create index idx_ib_generated_at on public.intelligence_briefs (generated_at desc);
create index idx_ib_period on public.intelligence_briefs (period_start, period_end);
create index idx_ibriefs_approval_status on public.intelligence_briefs (approval_status);
create index idx_intelligence_briefs_morning_cycle_id on public.intelligence_briefs (morning_cycle_id);
alter table public.intelligence_briefs enable row level security;
create policy auth_read on public.intelligence_briefs for select to authenticated using (true);
-- (production also has role xo_bot with SELECT on intelligence_briefs; that role does not exist in the container)

insert into public.captains_daily_briefs (brief_type, brief_text) values ('morning', 'replica row');
insert into public.intelligence_briefs (period_start, period_end) values ('2026-11-24', '2026-11-25');
"""


def build_template():
    """wp11_tpl: production replica + the six preserved rows (loaded byte-exactly from the evidence folder)."""
    create_db(TPL)
    psql(REPLICA_DDL, TPL)
    raw = json.loads((Path(EVID) / "intelligence_products_20261124_25.raw.json").read_text(encoding="utf-8"))
    for r in raw:
        psql("insert into public.intelligence_products (product_key,generated_for,as_of,title,summary,sections,exceptions,body_md,created_at) "
             "select product_key,generated_for,as_of,title,summary,sections,exceptions,body_md,created_at "
             f"from jsonb_populate_record(null::public.intelligence_products, {jlit(r)})", TPL)
    close_sessions(TPL)
    return raw


def catalog_snapshot(db, table):
    cols = psql(f"select column_name||' '||data_type||' '||is_nullable||coalesce(' '||column_default,'') from information_schema.columns "
                f"where table_schema='public' and table_name={lit(table)} order by ordinal_position", db).splitlines()
    cons = psql(f"select conname||' '||pg_get_constraintdef(oid) from pg_constraint where conrelid='public.{table}'::regclass order by 1", db).splitlines()
    idx = psql(f"select indexdef from pg_indexes where schemaname='public' and tablename={lit(table)} order by 1", db).splitlines()
    pol = psql(f"select policyname||' '||cmd||' '||roles::text||' '||coalesce(qual,'') from pg_policies where tablename={lit(table)} order by 1", db).splitlines()
    acl = psql(f"select relacl::text from pg_class where oid='public.{table}'::regclass", db)
    return {"columns": cols, "constraints": cons, "indexes": idx, "policies": pol, "acl": acl}


# ---------------------------------------------------------------------------------------------------------------------
# PostgREST emulator
# ---------------------------------------------------------------------------------------------------------------------
class _Resp:
    def __init__(self, body: bytes, status=200):
        self._b, self.status = body, status

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(url, pg: PgError):
    s = pg.sqlstate
    detail = re.search(r"DETAIL:\s+(.*)", pg.text)
    msg = re.search(r"ERROR:\s+\w{5}:\s+(.*)", pg.text)
    code, status = s, 500
    if s in ("23505", "23503"):
        status = 409
    elif s.startswith(("23", "PGRST2")) or s in ("42P10", "42703", "42883", "22P02", "22007", "22023", "23514"):
        status = 400
    elif s == "42501":
        status = 403
    elif s == "42P01":
        code, status = "PGRST205", 404      # PostgREST answers from its schema cache: unknown relation = PGRST205
    elif s == "55P03":
        status = 503
    body = {"code": code, "message": (msg.group(1) if msg else pg.text[:200]).strip(), "details": detail.group(1).strip() if detail else None, "hint": None}
    if code == "PGRST205":
        body["message"] = "Could not find the table in the schema cache"
    return urllib.error.HTTPError(url, status, str(status), {}, BytesIO(json.dumps(body).encode()))


def _filters(qs):
    out = []
    for k, vals in qs.items():
        if k in ("select", "order", "limit", "on_conflict", "offset"):
            continue
        for v in vals:
            op, _, arg = v.partition(".")
            if op == "eq":
                out.append(f"{k} = {lit(arg)}")
            elif op == "gt":
                out.append(f"{k} > {lit(arg)}")
            elif op == "gte":
                out.append(f"{k} >= {lit(arg)}")
            elif op == "is" and arg == "null":
                out.append(f"{k} is null")
            else:
                raise AssertionError(f"filter not emulated: {k}={v}")
    return " and ".join(out)


class FakeRest:
    """urlopen replacement for one database. role by apikey: SVC -> service_role, AUTH -> authenticated."""

    SVC, AUTH = "wp11-service-key", "wp11-authenticated-key"

    def __init__(self, db):
        self.db = db
        self.log = []          # [{method, table, status, body_sha, as_of, role}]
        self.fail_next = []    # optional injected PgError list (consumed per request)

    def role_of(self, req):
        key = req.headers.get("Apikey") or req.headers.get("apikey")
        return "service_role" if key == self.SVC else "authenticated"

    def __call__(self, req, timeout=None):
        url = req.full_url
        pu = urllib.parse.urlparse(url)
        table = pu.path.rsplit("/", 1)[-1]
        qs = urllib.parse.parse_qs(pu.query, keep_blank_values=True)
        role = self.role_of(req)
        method = req.get_method()
        prefer = req.headers.get("Prefer", "")
        entry = {"method": method, "table": table, "role": role, "status": None}
        self.log.append(entry)
        try:
            if method == "GET":
                sel = qs.get("select", ["*"])[0]
                where = _filters(qs)
                order = qs.get("order", [""])[0]
                ob = ""
                if order:
                    ob = " order by " + ", ".join(p.replace(".desc", " desc").replace(".asc", " asc") for p in order.split(","))
                lim = f" limit {int(qs['limit'][0])}" if "limit" in qs else ""
                sql = (f"select coalesce(json_agg(row_to_json(t)),'[]'::json) from (select {sel} from public.{table}"
                       f"{' where ' + where if where else ''}{ob}{lim}) t")
                out = psql(sql, self.db, role=role, settings=API_SETTINGS)
                entry["status"] = 200
                return _Resp(out.encode())
            body = json.loads(req.data.decode()) if req.data else {}
            if method == "POST":
                cols_known = set(psql(f"select column_name from information_schema.columns where table_schema='public' and table_name={lit(table)}",
                                      self.db).split())
                unknown = [c for c in body if c not in cols_known]
                if unknown:
                    raise PgError("PGRST204", f"ERROR:  PGRST204: Could not find the '{unknown[0]}' column of '{table}' in the schema cache")
                cols = list(body)
                cl = ",".join(cols)
                ins = (f"insert into public.{table} ({cl}) select {cl} from jsonb_populate_record(null::public.{table}, {jlit(body)})")
                oc = qs.get("on_conflict", [None])[0]
                if oc:
                    sets = ",".join(f"{c}=excluded.{c}" for c in cols if c not in oc.split(","))
                    ins += (f" on conflict ({oc}) do update set {sets}" if "merge-duplicates" in prefer else f" on conflict ({oc}) do nothing")
                if "return=representation" in prefer:
                    sql = f"with ins as ({ins} returning *) select coalesce(json_agg(row_to_json(ins)),'[]'::json) from ins"
                else:
                    sql = ins
                out = psql(sql, self.db, role=role, settings=API_SETTINGS)
                entry["status"] = 201
                if table == "intelligence_products":
                    entry.update(body_sha=sha(body["body_md"]), summary_sha=sha(body["summary"]), as_of=body["as_of"], product_key=body["product_key"])
                return _Resp(out.encode() if out else b"", 201)
            if method == "PATCH":
                sets = ",".join(f"{k}={'null' if v is None else (jlit(v) if isinstance(v, (list, dict)) else lit(v))}" for k, v in body.items())
                where = _filters(qs)
                sql = (f"with u as (update public.{table} set {sets} where {where} returning *) "
                       f"select coalesce(json_agg(row_to_json(u)),'[]'::json) from u")
                out = psql(sql, self.db, role=role, settings=API_SETTINGS)
                entry["status"] = 200
                return _Resp(out.encode())
            raise AssertionError(method)
        except PgError as pg:
            err = _http_error(url, pg)
            entry["status"] = err.code
            entry["sqlstate"] = pg.sqlstate
            raise err from None


@contextmanager
def rest(db, fr=None):
    """Patch urlopen + Supabase env for the duration; yields the FakeRest (its .log lists every request)."""
    fr = fr or FakeRest(db)
    env = {"SUPABASE_URL": "http://postgrest.invalid", "SUPABASE_SERVICE_ROLE_KEY": FakeRest.SVC}
    nosleep = lambda s: None
    old_defaults = job._get.__defaults__
    job._get.__defaults__ = (3, nosleep)
    try:
        with mock.patch.dict(os.environ, env), mock.patch("urllib.request.urlopen", fr):
            yield fr
    finally:
        job._get.__defaults__ = old_defaults


# ---------------------------------------------------------------------------------------------------------------------
# Actors
# ---------------------------------------------------------------------------------------------------------------------
KEYS = ("recurring_provider", "systemic_risk", "forward_watch")


def make_products(tag):
    return [{"product_key": k, "title": f"{k} title", "summary": f"{k} summary {tag}",
             "sections": {"confirmed_evidence": [f"{tag}"], "analytical_inference": [], "potential_exposure": [], "unknowns": []},
             "exceptions": [], "body_md": f"# {k} — {tag}\n\nbody é中 {tag}\n"} for k in KEYS]


def _stub_getter(table, query):
    return []


@contextmanager
def _producer(tag):
    with mock.patch.object(job.ip, "build_products", lambda status, context, as_of, basis: make_products(tag)):
        yield


def new_writer(as_of: datetime, tag: str, *, flag_on: bool, cadence="daily", gateway=None):
    """The integrated Python writer (job.run). Returns None on success, else the exception class and HTTP/SQL detail."""
    with _producer(tag), mock.patch.dict(os.environ, {job.APPEND_FLAG: "1" if flag_on else "0"}):
        try:
            job.run(as_of, getter=_stub_getter, force=True, cadence=cadence, gateway=gateway)
            return None
        except urllib.error.HTTPError as e:
            return f"HTTP{e.code}"
        except Exception as e:  # noqa: BLE001
            return type(e).__name__


def old_writer(as_of: datetime, tag: str):
    """The writer as it is in production today: one `on_conflict=product_key,generated_for` merge upsert per product."""
    try:
        for rec in job.to_records(make_products(tag), as_of):
            job._upsert(rec)
        return None
    except urllib.error.HTTPError as e:
        return f"HTTP{e.code}"
    except Exception as e:  # noqa: BLE001
        return type(e).__name__


def _first_per_key(rows):
    seen, out = set(), []
    for r in rows:
        if r["product_key"] not in seen:
            seen.add(r["product_key"])
            out.append(r)
    return out


def _bodies(rows):
    return {r["product_key"]: sha(r["body_md"]) for r in rows}


def _is_missing(err):
    return err["code"] in ("42P01", "PGRST205") or bool(re.search(r"does not exist|schema cache", err.get("message", ""), re.IGNORECASE))


def _query(db, table, cols, order, limit, role="authenticated"):
    """Returns (rows, None) or (None, {code, message}) the way supabase-js reports it."""
    sql = (f"select coalesce(json_agg(row_to_json(t)),'[]'::json) from (select {cols} from public.{table} order by {order} limit {limit}) t")
    try:
        return json.loads(psql(sql, db, role=role, settings=API_SETTINGS)), None
    except PgError as e:
        code = "PGRST205" if e.sqlstate == "42P01" else e.sqlstate
        m = re.search(r"ERROR:\s+\w{5}:\s+(.*)", e.text)
        return None, {"code": code, "message": ("Could not find the table in the schema cache" if code == "PGRST205" else (m.group(1) if m else e.text[:120]))}


BASE_COLS = "product_key, generated_for, as_of, title, summary, sections, exceptions, body_md"
CUR_COLS = f"id, {BASE_COLS}, cadence, reporting_date, generation_seq, last_refresh_as_of"


def old_portal(db):
    """lcars-portal intelligenceProducts.ts at the production baseline: base table, order generated_for desc, limit 30, first row per key."""
    rows, err = _query(db, "intelligence_products", BASE_COLS, "generated_for desc", 30)
    if err:
        if _is_missing(err):
            return "unavailable"
        return f"throws:{err['code']}"
    return _bodies(_first_per_key(rows))


def _newer(a, b):
    ta, tb = datetime.fromisoformat(a["as_of"]), datetime.fromisoformat(b["as_of"])
    if ta != tb:
        return ta > tb
    if (a.get("generation_seq") or 0) != (b.get("generation_seq") or 0):
        return (a.get("generation_seq") or 0) > (b.get("generation_seq") or 0)
    return (a.get("id") or 0) > (b.get("id") or 0)


def new_portal(db):
    """lcars-portal intelligenceProducts.ts (WP9): view first (order as_of desc, limit 30, newest per key); only a MISSING relation
    falls back to the base table (order generated_for desc, as_of desc); any other error throws."""
    rows, err = _query(db, "intelligence_products_current", CUR_COLS, "as_of desc", 30)
    if not err:
        best = {}
        for r in rows:
            cur = best.get(r["product_key"])
            if cur is None or _newer(r, cur):
                best[r["product_key"]] = r
        return _bodies(best.values())
    if not _is_missing(err):
        return f"throws:{err['code']}"
    rows, err = _query(db, "intelligence_products", BASE_COLS, "generated_for desc, as_of desc", 30)
    if err:
        return "unavailable" if _is_missing(err) else f"throws:{err['code']}"
    return _bodies(_first_per_key(rows))


def sql_scalar_set(db, sql):
    out = psql(sql, db)
    return set(out.split()) if out else set()


def all_body_shas(db):
    """sha256 of every stored body: live rows plus the archive (when it exists)."""
    s = sql_scalar_set(db, "select encode(sha256(convert_to(body_md,'UTF8')),'hex') from public.intelligence_products")
    if psql("select to_regclass('public.intelligence_products_revisions') is not null", db) == "t":
        s |= sql_scalar_set(db, "select encode(sha256(convert_to(body_md,'UTF8')),'hex') from public.intelligence_products_revisions")
    return s


class Oracle:
    """What the readers must show and what history must survive, derived from the writers' acknowledged (2xx) writes only."""

    def __init__(self, raw):
        self.written = {}   # (sha) -> (product_key, as_of)
        self.summary = {}   # body sha -> sha(summary)
        for r in raw:
            self.written[sha(r["body_md"])] = (r["product_key"], r["as_of"])
            self.summary[sha(r["body_md"])] = sha(r["summary"])

    def absorb(self, fr: FakeRest):
        for e in fr.log:
            if e["table"] == "intelligence_products" and e["method"] == "POST" and e["status"] == 201 and e.get("body_sha"):
                self.written[e["body_sha"]] = (e["product_key"], e["as_of"])
                self.summary[e["body_sha"]] = e["summary_sha"]
        fr.log.clear()

    def newest(self):
        best = {}
        for h, (k, t) in self.written.items():
            tt = datetime.fromisoformat(t)
            if k not in best or tt > best[k][0]:
                best[k] = (tt, h)
        return {k: v[1] for k, v in best.items()}

    def newest_summary(self):
        return {k: self.summary[h] for k, h in self.newest().items()}

    def lost(self, db):
        return sorted(set(self.written) - all_body_shas(db))


# ---------------------------------------------------------------------------------------------------------------------
# Scenario driver
# ---------------------------------------------------------------------------------------------------------------------
MATRIX: list[dict] = []
_DBS: list[str] = []


def iso(y, mo, d, h, mi, s=5):
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


D1 = iso(2026, 11, 25, 19, 20)    # Thu 26 Nov 06:20 AEDT daily slot (UTC date 25 Nov: collides with the preserved 25 Nov key)
D1M = iso(2026, 11, 25, 21, 0)    # manual run later the same Melbourne day
D2 = iso(2026, 11, 26, 19, 20)
D2M = iso(2026, 11, 26, 21, 0)
D3 = iso(2026, 11, 27, 19, 20)
D3M = iso(2026, 11, 27, 22, 0)
D4 = iso(2026, 11, 29, 19, 20)    # Mon 30 Nov 06:20 daily
W1 = iso(2026, 11, 29, 20, 20)    # Mon 30 Nov 07:20 weekly (same legacy UTC key as D4)
D5 = iso(2026, 11, 30, 19, 20)
D5M = iso(2026, 11, 30, 21, 30)


class Scn:
    """One scenario database cloned from the production replica, with an oracle of acknowledged writes."""

    def __init__(self, name, raw):
        self.name = name
        self.db = f"wp11_{RUN}_{name}"
        create_db(self.db, TPL)
        _DBS.append(self.db)
        self.o = Oracle(raw)
        self.lost_floor = None

    # -- actors
    def write(self, kind, as_of, tag, cadence="daily", **kw):
        with rest(self.db) as fr:
            if kind == "old":
                res = old_writer(as_of, tag)
            elif kind == "new_off":
                res = new_writer(as_of, tag, flag_on=False, cadence=cadence)
            elif kind == "new_on":
                res = new_writer(as_of, tag, flag_on=True, cadence=cadence)
            else:
                raise AssertionError(kind)
            self.o.absorb(fr)
        return res

    def apply(self, mig, sql=None, expect=None):
        """Run a migration draft as the migration role. expect = sqlstate the run must fail with (else it must succeed)."""
        text = sql if sql is not None else (DRAFTS / MIG[mig]).read_text()
        try:
            psql(text, self.db, timeout=240)
        except PgError as e:
            if expect and e.sqlstate == expect:
                return e
            raise
        if expect:
            raise AssertionError(f"{mig} unexpectedly succeeded (wanted {expect})")
        return None

    def q(self, sql, role=None, settings=""):
        return psql(sql, self.db, role=role, settings=settings)

    def shape(self):
        have = lambda t: self.q(f"select to_regclass('public.{t}') is not null") == "t"
        return {"a": have("intelligence_products_revisions") and have("intelligence_products_current"),
                "b": self.q("select count(*) from pg_trigger where tgname='intelligence_products_append_only'") == "1",
                "attempts": have("intelligence_delivery_attempts")}

    def readers(self):
        want = self.o.newest()

        def judge(got):
            if isinstance(got, str):
                return got
            return "ok" if got == want else "WRONG(" + ",".join(sorted(k for k in want if got.get(k) != want[k])) + ")"
        return {"old_portal": judge(old_portal(self.db)), "new_portal": judge(new_portal(self.db))}

    def check(self, step, writers=None, **expect):
        r = self.readers()
        lost = self.o.lost(self.db)
        row = {"scenario": self.name, "step": step, "schema": "".join(k for k, v in self.shape().items() if v) or "base",
               "writers": writers or {}, **r, "history_lost": len(lost)}
        MATRIX.append(row)
        for k, v in expect.items():
            got = row.get(k)
            assert got == v, f"[{self.name}/{step}] {k}: expected {v!r}, got {got!r} (row={row})"
        return row

    def floor_lost(self):
        self.lost_floor = len(self.o.lost(self.db))


# ---------------------------------------------------------------------------------------------------------------------
# Python-side readers (brief block) through the emulator
# ---------------------------------------------------------------------------------------------------------------------
def brief_block_readers(scn: Scn, now: datetime):
    """What intelligence/brief_products_block.py picks per product: flag OFF (base table, newest by as_of) and flag ON (view, freshness
    ranking). Returns {off: {...}|'throws', on: {...}|'throws'} keyed to the sha of the summary text."""
    from intelligence import brief_products_block as bpb
    out = {}
    with rest(scn.db):
        try:
            out["off"] = {k: sha(r["summary"]) for k, r in {r["product_key"]: r for r in bpb._latest(bpb._from_table())}.items()}
        except Exception as e:  # noqa: BLE001
            out["off"] = f"throws:{type(e).__name__}"
        try:
            prim, _ = bpb._select(bpb._from_current_view(), now)
            out["on"] = {k: sha(v[0]["summary"]) for k, v in prim.items()}
        except Exception as e:  # noqa: BLE001
            out["on"] = f"throws:{type(e).__name__}"
    return out


# stage builders -------------------------------------------------------------------------------------------------------
STAGES = {
    "base": [],
    "0264": ["0264"],
    "A": ["0264", "0263a"],
    "A+B": ["0264", "0263a", "0263b"],
    "A+B+R": ["0264", "0263a", "0263b", "0263r"],
}
WRITERS = ("old", "new_off", "new_on_daily", "new_on_weekly")


def cross_stage(raw, stage):
    """Skew matrix for one schema stage: every writer runs against it (a scheduled run and a manual rerun the same Melbourne day, with
    different content), strictly in time order, and every reader is checked after each writer. Returns the matrix rows."""
    s = Scn(f"x_{stage.replace('+', '')}", raw)
    for m in STAGES[stage]:
        s.apply(m)
    rows = []
    plan = (("old", "old", D1, D1M, "daily", "daily"), ("new_off", "new_off", D2, D2M, "daily", "daily"),
            ("new_on_daily", "new_on", D3, D3M, "daily", "daily"), ("new_on_weekly", "new_on", D4, W1, "daily", "weekly"))
    for name, kind, t1, t2, c1, c2 in plan:
        res = [s.write(kind, t1, f"{name}-1", cadence=c1), s.write(kind, t2, f"{name}-2", cadence=c2)]
        row = s.check(f"{stage}|{name}", writers={"results": res})
        row["stage"], row["writer"] = stage, name
        row["row_count"] = int(s.q("select count(*) from intelligence_products"))
        rows.append(row)
    return s, rows


# permissions ----------------------------------------------------------------------------------------------------------
PRIV_CODE = {"SELECT": "r", "INSERT": "a", "UPDATE": "w", "DELETE": "d", "TRUNCATE": "D", "REFERENCES": "x", "TRIGGER": "t", "MAINTAIN": "m"}


def priv_matrix(db, rels, roles=("anon", "authenticated", "service_role")):
    """{relation: {role: 'rawdDxtm' subset, 'PUBLIC': ...}} from has_table_privilege (effective, includes PUBLIC and inheritance)
    plus PUBLIC taken from the ACL itself."""
    out = {}
    for rel in rels:
        if psql(f"select to_regclass('public.{rel}') is not null", db) != "t":
            out[rel] = None
            continue
        out[rel] = {}
        for role in roles:
            have = "".join(c for p, c in PRIV_CODE.items()
                           if psql(f"select has_table_privilege({lit(role)}, 'public.{rel}', {lit(p)})", db) == "t")
            out[rel][role] = "".join(sorted(have))
        pub = psql(f"select coalesce(string_agg(privilege_type,','),'') from (select (aclexplode(relacl)).* from pg_class "
                   f"where oid='public.{rel}'::regclass) a where grantee = 0", db)
        out[rel]["PUBLIC"] = pub
    return out


# role-path behaviour ---------------------------------------------------------------------------------------------------
A1, A2 = "00000000-0000-0000-0000-0000000000a1", "00000000-0000-0000-0000-0000000000a2"
SEED_ATTEMPTS = (
    "insert into public.intelligence_delivery_attempts (attempt_id,brief_table,brief_id,channel,content_hash,kind,attempt_no,chunks_total,chunks,state,outcome,finished_at) values "
    f"('{A1}','captains_daily_briefs','b1','telegram','h1','PRIMARY',1,2,"
    "'[{\"index\":0,\"state\":\"CONFIRMED\",\"message_id\":11},{\"index\":1,\"state\":\"UNKNOWN\"}]','finished','UNKNOWN',now()),"
    f"('{A2}','captains_daily_briefs','b1','telegram','h2','PRIMARY',1,1,"
    "'[{\"index\":0,\"state\":\"CONFIRMED\",\"message_id\":22}]','finished','CONFIRMED',now())")

T = "public.intelligence_delivery_attempts"
ATTEMPT_OPS = {
    "select": f"select count(*) from {T}",
    "insert": f"insert into {T} (attempt_id,brief_table,brief_id,channel,content_hash,kind,attempt_no) values (gen_random_uuid(),'captains_daily_briefs','b9','telegram','h9','PRIMARY',1)",
    "update_forward": f"update {T} set outcome='CONFIRMED' where attempt_id='{A1}'",
    "update_backward": f"update {T} set outcome='FAILED' where attempt_id='{A2}'",
    "update_confirmed_chunk": f"update {T} set chunks='[{{\"index\":0,\"state\":\"CONFIRMED\",\"message_id\":999}}]'::jsonb where attempt_id='{A2}'",
    "delete": f"delete from {T} where attempt_id='{A2}'",
    "truncate": f"truncate {T}",
    "upsert_merge_overwrite": (f"insert into {T} (attempt_id,brief_table,brief_id,channel,content_hash,kind,attempt_no,chunks,state,outcome) values "
                               f"('{A2}','captains_daily_briefs','b1','telegram','h2','PRIMARY',1,'[]','finished','FAILED') "
                               "on conflict (attempt_id) do update set chunks=excluded.chunks, outcome=excluded.outcome"),
    "disable_trigger": f"alter table {T} disable trigger intelligence_delivery_attempts_guard_trg",
    "drop_trigger": f"drop trigger intelligence_delivery_attempts_guard_trg on {T}",
    "replace_guard_function": "create or replace function public.intelligence_delivery_attempts_guard() returns trigger language plpgsql as $$ begin return new; end $$",
    "session_replication_role_replica_delete": ("set session_replication_role = replica", f"delete from {T} where attempt_id='{A2}'"),
}


def run_ops(db, role, ops):
    """Each op runs in a sub-transaction that is always rolled back (the session survives errors); returns {op: 'ok' | sqlstate}.
    An op value may be one statement or a tuple of statements executed in order inside the same sub-transaction."""
    parts = []
    for name, sql in ops.items():
        stmts = sql if isinstance(sql, tuple) else (sql,)
        body = "\n".join(f"execute $q${st}$q$;" for st in stmts)
        parts.append(
            "do $w$ begin begin\n" + body + "\nraise sqlstate 'ZZ001' using message = 'wp11-rollback';\n"
            f"exception when sqlstate 'ZZ001' then raise notice 'WP11|{name}|ok'; "
            f"when others then raise notice 'WP11|{name}|%', sqlstate; end; end $w$;")
    out = psql("\n".join(parts), db, role=role)
    res = dict(re.findall(r"WP11\|(\w+)\|(\w+)", out))
    missing = set(ops) - set(res)
    if missing:
        raise AssertionError(f"no result for {sorted(missing)}: {out[-500:]}")
    return res


HIST = "public.intelligence_products_revisions"
HISTORY_OPS = {
    "select": f"select count(*) from {HIST}",
    "insert": f"insert into {HIST} (archive_reason,product_key,generated_for,as_of,title,summary,sections,exceptions,body_md,created_at) values ('update','forward_watch','2026-01-01',now(),'t','s','{{}}','[]','b',now())",
    "update": f"update {HIST} set body_md='x'",
    "delete": f"delete from {HIST}",
    "truncate": f"truncate {HIST}",
    "disable_trigger": f"alter table {HIST} disable trigger intelligence_products_revisions_append_only",
    "session_replication_role_replica_delete": ("set session_replication_role = replica", f"delete from {HIST}"),
}
P = "public.intelligence_products"
PRODUCT_OPS = {
    "select": f"select count(*) from {P}",
    "update_content": f"update {P} set body_md='tampered' where product_key='forward_watch' and generated_for='2026-11-25'",
    "delete_row": f"delete from {P} where product_key='forward_watch' and generated_for='2026-11-25'",
    "truncate": f"truncate {P}",
    "maintain_lock": f"lock table {P} in access exclusive mode",
    "disable_trigger": f"alter table {P} disable trigger all",
    "session_replication_role_replica_delete": ("set session_replication_role = replica", f"delete from {P}"),
}
VIEW_OPS = {
    "select": "select count(*) from public.intelligence_products_current",
    "insert": "insert into public.intelligence_products_current (product_key) values ('forward_watch')",
    "update": "update public.intelligence_products_current set title='x'",
    "delete": "delete from public.intelligence_products_current",
}
