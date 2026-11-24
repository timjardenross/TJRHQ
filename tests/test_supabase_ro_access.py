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


# ── 2. scope guard (application-level) ────────────────────────────────────────────────────────────────────────────────────

CFG = scope._load_config()

ALLOWED_RESEARCH = [
    "select count(*) from intelligence_events where collected_at > now() - interval '7 days'",
    "with k(id, rx, d0) as (values ('RS-001','NAB','2026-09-23')) select * from k",  # CTE column list: the old parser could not classify this
    "select * from generate_series(1,3) as g(n)",
    "select * from intelligence_events tablesample system (1)",
    "select sha256(convert_to(raw_title,'UTF8')), pg_get_viewdef('intelligence_source_health_latest'::regclass) from intelligence_events limit 1",
    "select brief_date, brief_type, brief_text from captains_daily_briefs where brief_text ~* 'optus'",
    "select e.event_id, s.source_name from intelligence_events e join intelligence_source_registry s using (source_id)",
    "select * from information_schema.columns where table_name = 'intelligence_events'",
    "explain select * from intelligence_events limit 1",
    "select relname, reltuples from pg_class where relnamespace = 'public'::regnamespace",  # metadata inspection stays available
    "select row_to_json(t) from (select * from alerts limit 3) t",
    "select e.raw_title from intelligence_events e -- tasks and vault.secrets only in a comment",
    "select source_id, percentile_cont(0.5) within group (order by latency_ms) from llm_call_metrics group by 1",
]

DENIED = [
    # direct, schema-qualified, quoted, upper-case, aliased, subquery, join, TABLE form, JSON wrapping
    "select * from health_daily_logs",
    "select * from public.health_daily_logs",
    'select * from public."health_daily_logs"',
    'select * from "Health_Daily_Logs"',
    "select * from HEALTH_DAILY_LOGS",
    "select h.* from health_daily_logs as h",
    "select * from (select * from capacity_checkins) x",
    "with x as (select * from pain_recovery_sessions) select * from x",
    "select e.raw_title from intelligence_events e join google_calendar_tokens g on true",
    "select * from intelligence_events, health_insights",
    "table mood_chart",
    "select row_to_json(t) from conversation_turns t",
    "select to_jsonb(c) from public . captured_items c",
    # views and functions that read outside scope
    "select * from analytics_health_daily",
    "select * from human_systems_daily",
    "select compute_recovery_score()",
    "select * from get_recovery_posture()",
    "select * from public.match_document_chunks(null, 1)",
    # SQL-executing builtins, including names built from pieces
    "select query_to_xml('select * from ' || 'health_' || 'daily_logs', true, false, '')",
    "select table_to_xml('x'::regclass, true, false, '')",
    "select * from ts_stat('select 1')",
    "select cursor_to_xml('c'::refcursor, 1, true, false, '')",
    # catalogs that expose other sessions' text or credentials
    "select query from pg_stat_statements",
    "select query from pg_stat_activity",
    "select * from pg_authid",
    "select usename, passwd from pg_shadow",
    "select pg_read_file('/etc/passwd')",
    "select lo_import('/etc/passwd')",
    # credential / platform schemas
    "select * from vault.secrets",
    "select * from vault.decrypted_secrets",
    'select * from "vault"."secrets"',
    "select * from auth.users",
    "select * from storage.objects",
    "select * from net.http_request_queue",
    "select * from cron.job",
    "select * from pgmq.q_xo",
    # names passed as text
    "select * from intelligence_events where raw_title = 'health_daily_logs'",
]

ASK = [
    # routes to dynamic SQL, or statements a person should decide
    "do $$ begin execute 'select 1'; end $$",
    "create temp table x as select 1",
    "create function pg_temp.f() returns int language sql as 'select 1'",
    "begin; set transaction read write; select 1; commit",
    "set role postgres",
    "select set_config('role','postgres',true)" if False else "prepare p as select 1",
    "execute p",
    'select * from U&"health\\005fdaily_logs"',
    "select 1 from U&'x'",
    "select 'unterminated",
    "",
]


@pytest.mark.parametrize("sql", ALLOWED_RESEARCH)
def test_scope_guard_leaves_routine_research_alone(sql):
    assert scope.classify(sql, CFG) is None


@pytest.mark.parametrize("sql", DENIED)
def test_scope_guard_denies_out_of_scope_reads_however_they_are_written(sql):
    result = scope.classify(sql, CFG)
    assert result is not None and result[0] == "deny", (sql, result)


@pytest.mark.parametrize("sql", ASK)
def test_scope_guard_sends_dynamic_or_non_read_statements_to_a_person(sql):
    result = scope.classify(sql, CFG)
    assert result is not None and result[0] == "ask", (sql, result)


def test_scope_lists_are_consistent():
    all_rel, permitted = set(CFG["all_public_relations"]), set(CFG["permitted_relations"])
    assert permitted <= all_rel
    assert len(CFG["all_public_relations"]) == len(all_rel), "duplicate relation names"
    personal_markers = ("health_", "pain_", "mood_", "capacity_", "physical_", "weight_", "recovery_", "burnout", "human_systems", "comms_",
                        "conversation_", "personal_", "shopping_", "google_calendar", "captain_readiness", "captured_items", "debrief_",
                        "user_settings", "wellness_", "captains_log", "alert_sites", "analytics_health", "intelligence_notes",
                        "intelligence_health_correlations", "daily_health")
    leaked = sorted(r for r in permitted if r.startswith(personal_markers))
    assert not leaked, f"personal or credential-bearing relations must not be permitted: {leaked}"
    # captains_daily_briefs holds health_snapshot and llm_call_metrics holds free-form metadata: both are column-limited
    assert set(CFG["column_grants"]) >= {"captains_daily_briefs", "llm_call_metrics"}
    assert "health_snapshot" not in CFG["column_grants"]["captains_daily_briefs"]
    assert "metadata" not in CFG["column_grants"]["llm_call_metrics"]


def test_scope_guard_fails_closed_on_credential_schemas_when_config_is_unreadable(monkeypatch):
    monkeypatch.setattr(scope, "CONFIG", Path("/nonexistent/supabase_ro_scope.json"))
    assert scope.classify("select * from vault.secrets")[0] == "deny"
    assert scope.classify("select query from pg_stat_statements")[0] == "deny"


def test_scope_guard_sends_listed_sensitive_tables_to_the_prompt():
    cfg = {**CFG, "ask_tables": ["intelligence_notes_x"], "all_public_relations": [], "denied_user_functions": []}
    assert scope.classify("select * from intelligence_notes_x", cfg)[0] == "ask"
    assert scope.classify("select * from intelligence_events", cfg) is None


def test_scope_guard_hook_never_prints_allow():
    for sql in ALLOWED_RESEARCH + DENIED + ASK:
        out = subprocess.run(
            [sys.executable, str(ROOT / ".claude" / "hooks" / "supabase_ro_scope.py")],
            input=json.dumps({"tool_input": {"query": sql}}),
            capture_output=True, text=True, check=True,
        ).stdout
        if out:
            assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] in {"deny", "ask"}


def test_verify_script_is_generated_from_the_same_lists():
    sys.path.insert(0, str(ROOT / "tools" / "intelligence"))
    import ro_scope

    rendered = ro_scope.render_verify(CFG)
    assert rendered == (ROOT / "tools" / "intelligence" / "ro_scope_verify.sql").read_text(encoding="utf-8"), "regenerate: python tools/intelligence/ro_scope.py > tools/intelligence/ro_scope_verify.sql"
    assert all(f"'{r}'" in rendered for r in CFG["permitted_relations"])


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


def test_postgres_cannot_revoke_a_platform_granted_membership_so_table_scope_is_not_database_enforceable(pg):
    """Why read scope is application-level: on Supabase the role `postgres` (CREATEROLE, ADMIN OPTION on pg_read_all_data, not a superuser)
    holds pg_read_all_data/pg_monitor with ADMIN OPTION, but supabase_read_only_user received its membership from supabase_admin, and
    PostgreSQL only lets a role revoke grants it made itself. This reproduces that arrangement locally."""
    admin = pg("owner_admin")
    admin.autocommit = True
    cur = admin.cursor()
    for sql in (
        "drop role if exists pgrole", "drop role if exists ro_member",
        "create role pgrole createrole login", "create role ro_member login",
        "grant pg_read_all_data to pgrole with admin option",
        "grant pg_read_all_data to ro_member",
    ):
        cur.execute(sql)
    conn = pg("pgrole")
    conn.autocommit = True
    c = conn.cursor()
    c.execute("revoke pg_read_all_data from ro_member")  # emits a WARNING and changes nothing
    cur.execute("select pg_has_role('ro_member', 'pg_read_all_data', 'member')")
    assert cur.fetchone()[0] is True
    with pytest.raises(psycopg2.Error) as excinfo:
        c.execute("revoke pg_read_all_data from ro_member granted by owner_admin")
    assert "permission denied" in str(excinfo.value).lower()
    conn.close()
    admin.close()
