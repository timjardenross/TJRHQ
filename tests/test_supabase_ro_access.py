"""Standing, capability-based authorisation for read-only Supabase research.

Three layers, each tested here:
  1. Repo config: a second MCP server that the platform runs as a read-only Postgres role, and a standing allow rule for ONLY that
     server's read tools. The write-capable server is never allowed by rule.
  2. Scope guard hook: refuses credential/auth schemas on the read-only server (data scope, not write safety).
  3. Database enforcement (local Postgres emulation of `supabase_read_only_user`): the role cannot write, whatever the SQL text says.
     Skipped when no local Postgres/psycopg2 is available (CI), so it is a developer and agent self-test.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
import supabase_ro_scope as scope

# ── 1. repo config ───────────────────────────────────────────────────────────────────────────────────────────────────────


def test_mcp_json_defines_a_read_only_scoped_server():
    cfg = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    server = cfg["mcpServers"]["supabase_ro"]
    url = server["url"]
    assert url.startswith("https://mcp.supabase.com/mcp?")
    assert "read_only=true" in url, "the platform read-only role is what makes a standing allow rule safe"
    assert "project_ref=" in url, "scope the server to this project"
    assert "features=database,docs" in url, "no account, edge-function, branching or storage tools"
    assert set(cfg["mcpServers"]) == {"supabase_ro"}, "only the read-only server is defined here; the write-capable one is not auto-added"


def test_standing_allow_rules_cover_only_read_tools_of_the_read_only_server():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    allow = settings["permissions"]["allow"]
    assert set(allow) == {"mcp__supabase_ro__execute_sql", "mcp__supabase_ro__list_tables"}
    for forbidden in ("apply_migration", "deploy_edge_function", "create_branch", "merge_branch", "create_project", "pause_project"):
        assert not any(forbidden in rule for rule in allow)


# ── 2. scope guard ───────────────────────────────────────────────────────────────────────────────────────────────────────

ALLOWED_RESEARCH = [
    "select count(*) from intelligence_events where collected_at > now() - interval '7 days'",
    "with k(id, rx, d0) as (values ('RS-001','NAB','2026-09-23')) select * from k",  # CTE column list: the old parser could not classify this
    "select * from generate_series(1,3) as g(n)",
    "select * from intelligence_events tablesample system (1)",
    "select sha256(convert_to('x','UTF8')), pg_get_viewdef('x'::regclass)",
    "select * from information_schema.columns where table_name = 'intelligence_events'",
    "explain select * from intelligence_events limit 1",
    "select 'vault.secrets is mentioned inside text only'",
    "select e.raw_title from intelligence_events e -- vault.secrets in a comment",
]

REFUSED = [
    "select * from vault.secrets",
    "select * from vault.decrypted_secrets",
    'select * from "vault"."secrets"',
    "select * from auth.users",
    "select * from storage.objects",
    "select * from net.http_request_queue",
    "select * from cron.job",
    "select * from pgmq.q_xo",
    "select usename, passwd from pg_shadow",
    "select * from pg_authid",
    "select pg_read_file('/etc/passwd')",
    "select lo_import('/etc/passwd')",
]


@pytest.mark.parametrize("sql", ALLOWED_RESEARCH)
def test_scope_guard_leaves_routine_research_alone(sql):
    assert scope.classify(sql, scope._load_config()) is None


@pytest.mark.parametrize("sql", REFUSED)
def test_scope_guard_refuses_credential_and_platform_schemas(sql):
    result = scope.classify(sql, scope._load_config())
    assert result is not None and result[0] == "deny"


def test_scope_guard_sends_listed_sensitive_tables_to_the_prompt():
    cfg = {"deny_schemas": [], "deny_catalog_names": [], "ask_tables": ["pain_checkins"]}
    assert scope.classify("select * from pain_checkins", cfg)[0] == "ask"
    assert scope.classify("select * from intelligence_events", cfg) is None


def test_scope_guard_hook_never_prints_allow():
    for sql in ALLOWED_RESEARCH + REFUSED:
        out = subprocess.run(
            [sys.executable, str(ROOT / ".claude" / "hooks" / "supabase_ro_scope.py")],
            input=json.dumps({"tool_input": {"query": sql}}),
            capture_output=True, text=True, check=True,
        ).stdout
        if out:
            decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
            assert decision in {"deny", "ask"}


def test_scope_guard_fails_closed_when_config_is_unreadable(monkeypatch):
    monkeypatch.setattr(scope, "CONFIG", Path("/nonexistent/supabase_ro_scope.json"))
    assert scope.classify("select * from vault.secrets")[0] == "deny"


# ── 3. database enforcement (local Postgres emulation of supabase_read_only_user) ─────────────────────────────────────────

psycopg2 = None  # imported lazily inside the pg fixture so the config and scope tests above still run where it is not installed


def _pg_bin():
    for base in sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True):
        if (base / "initdb").exists():
            return base
    found = shutil.which("initdb")
    return Path(found).parent if found else None


@pytest.fixture(scope="module")
def pg():
    global psycopg2
    psycopg2 = pytest.importorskip("psycopg2")
    binp = _pg_bin()
    if binp is None:
        pytest.skip("no local PostgreSQL binaries")
    root = Path(tempfile.mkdtemp(prefix="ro-selftest-"))
    data, sock = root / "data", root / "sock"
    sock.mkdir()
    prefix = ["runuser", "-u", "postgres", "--"] if os.geteuid() == 0 else []
    if prefix:
        os.chmod(root, 0o777)
        os.chmod(sock, 0o777)
    port = 54329 + (os.getpid() % 500)
    subprocess.run([*prefix, str(binp / "initdb"), "-D", str(data), "-A", "trust", "-U", "owner_admin"], check=True, capture_output=True)
    subprocess.run([*prefix, str(binp / "pg_ctl"), "-D", str(data), "-o", f"-p {port} -k {sock} -c listen_addresses=''", "-w", "-l", str(root / "log"), "start"], check=True, capture_output=True)

    def connect(user, db="postgres"):
        return psycopg2.connect(host=str(sock), port=port, user=user, dbname=db)

    admin = connect("owner_admin")
    admin.autocommit = True
    cur = admin.cursor()
    # Mirror production: read-only login role = pg_read_all_data + default_transaction_read_only=on, no grants of its own.
    cur.execute("create role ro_user login")
    cur.execute("grant pg_read_all_data to ro_user")
    cur.execute("alter role ro_user set default_transaction_read_only = on")
    cur.execute("create table events (id int primary key, title text)")
    cur.execute("insert into events values (1,'a'),(2,'b'),(3,'c')")
    cur.execute("create schema vault_like")
    cur.execute("create table vault_like.secrets (id int, secret text)")
    cur.execute("insert into vault_like.secrets values (1,'s3cret')")
    # a SECURITY DEFINER writer, revoked from PUBLIC exactly like the production prune_* functions
    cur.execute("create function prune_events() returns int language sql security definer as 'delete from events returning 1'")
    cur.execute("revoke all on function prune_events() from public")
    # the dangerous variant (PUBLIC-executable secdef writer) used to document the residual risk
    cur.execute("create function leaky_prune() returns int language sql security definer as 'delete from events where id = 3 returning 1'")
    cur.execute("grant execute on function leaky_prune() to public")
    yield connect
    admin.close()
    subprocess.run([*prefix, str(binp / "pg_ctl"), "-D", str(data), "-m", "immediate", "stop"], capture_output=True, check=False)
    shutil.rmtree(root, ignore_errors=True)


def _try(connect, sql, user="ro_user"):
    """Run sql as the read-only role; return ("ok", rows) or ("error", message). Always rolls back."""
    conn = connect(user)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall() if cur.description else []
        return "ok", rows
    except psycopg2.Error as exc:
        return "error", str(exc).strip().splitlines()[0]
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("sql", [
    "with k(id, rx) as (values (1,'a')) select * from k",
    "select * from generate_series(1,3) as g(n)",
    "select * from events tablesample system (100)",
    "select id, row_number() over (order by id), (select percentile_cont(0.5) within group (order by id) from events) from events",
    "explain select * from events",
    "explain analyze select * from events",
    "select sha256(convert_to(title,'UTF8')) from events",
])
def test_routine_analysis_runs_without_any_parsing_limits(pg, sql):
    assert _try(pg, sql)[0] == "ok"


@pytest.mark.parametrize("sql", [
    "insert into events values (9,'x')",
    "update events set title='x'",
    "delete from events",
    "truncate events",
    "drop table events",
    "create table t (a int)",
    "create temp table t (a int)",
    "create schema s",
    "alter table events add column c int",
    "grant all on events to public",
    "create role evil superuser",
    "alter role ro_user set default_transaction_read_only = off",
    "select prune_events()",
    "select pg_read_file('/etc/passwd')",
    "copy events to program 'id'",
    "copy events from program 'id'",
    "select lo_import('/etc/passwd')",
    "do $$ begin delete from events; end $$",
])
def test_writes_and_privileged_operations_fail_whatever_the_sql_says(pg, sql):
    assert _try(pg, sql)[0] == "error"


def test_cannot_signal_another_roles_backend(pg):
    admin = pg("owner_admin")
    try:
        cur = admin.cursor()
        cur.execute("select pg_backend_pid()")
        pid = cur.fetchone()[0]
        status, message = _try(pg, f"select pg_terminate_backend({pid})")
        assert status == "error" and "permission" in message.lower()
    finally:
        admin.close()


def test_flipping_to_read_write_still_cannot_write_without_privileges(pg):
    # the default_transaction_read_only setting is user-changeable; safety comes from the absence of write privileges, not from it.
    status, _ = _try(pg, "begin; select set_config('default_transaction_read_only','off',false); delete from events; commit")
    assert status == "error"
    status, _ = _try(pg, "begin; set transaction read write; delete from events; commit")
    assert status == "error"
    status, _ = _try(pg, "begin; set transaction read write; create table t (a int); commit")
    assert status == "error"


def test_data_is_unchanged_after_all_attempts(pg):
    assert _try(pg, "select count(*) from events", user="owner_admin")[1] == [(3,)]


def test_residual_risk_a_public_executable_security_definer_writer_defeats_the_role(pg):
    """DOCUMENTED RESIDUAL: the role's safety rests on there being NO PUBLIC-executable SECURITY DEFINER writers.
    Production currently has none (verified by tools/intelligence/ro_access_verification.sql); keep that query in the routine checks."""
    assert _try(pg, "select leaky_prune()")[0] == "error"  # default read-only transaction stops it ...
    conn = pg("ro_user")
    try:
        cur = conn.cursor()
        cur.execute("begin; set transaction read write")
        cur.execute("select leaky_prune()")  # ... until the session flips the transaction to read-write first
        flipped = True
    except psycopg2.Error:
        flipped = False
    finally:
        conn.rollback()
        conn.close()
    assert flipped, "if this stops being true the residual-risk note and verification query can be relaxed"


def test_credential_schema_is_readable_by_pg_read_all_data_which_is_why_the_scope_guard_exists(pg):
    assert _try(pg, "select secret from vault_like.secrets")[0] == "ok"
    assert scope.classify("select secret from vault.secrets")[0] == "deny"
