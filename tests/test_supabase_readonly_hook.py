"""The PreToolUse hook that auto-approves read-only Supabase execute_sql calls (.claude/hooks/supabase_readonly_sql.py).

The contract that matters: it may only ever turn a prompt into an approval for a provably read-only statement. Anything
that writes, changes schema, opens a transaction, calls a function it does not know, or that it cannot parse must produce
no decision (so the normal permission prompt applies)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "supabase_readonly_sql.py"
sys.path.insert(0, str(HOOK.parent))

from supabase_readonly_sql import is_read_only

READ_ONLY = [
    "select 1",
    "select 1;",
    "select count(*) from alerts where severity='advice'",
    "SELECT source_key, round(avg(items_seen)::numeric,1) FROM emergency_alert_source_integrity GROUP BY 1 ORDER BY 1;",
    "with x as (select * from alerts) select count(*) from x",
    "select * from alerts where headline = 'drop table alerts; delete from x'",  # keywords inside a string literal
    "select column_name from information_schema.columns where table_name='alerts' order by ordinal_position",
    "select 1; select 2",
    "select percentile_cont(0.5) within group (order by extract(epoch from (a-b))/60) from t",
    "select date_trunc('hour', last_seen_at), count(*) from alerts group by 1 -- trailing comment",
    "select regexp_match(raw_text, 'Issued at (\\d{1,2}:\\d{2})') from alerts",
    "explain select * from alerts",
    "select (substring(event_key from '-(\\d{4})$'))::timestamptz from alerts",
]

NOT_READ_ONLY = [
    "", "   ", "select 1; delete from alerts", "delete from alerts", "update alerts set x=1", "insert into t values (1)",
    "drop table alerts", "create table t as select 1", "select * into t from alerts", "begin; select 1; commit",
    "select prune_high_churn_log_tables()",  # a SELECT can call a function that deletes rows
    "select public.prune_x()", "select nextval('s')", "select set_config('a','b',false)", "select pg_terminate_backend(1)",
    "select * from alerts for update", "explain analyze select 1", "with d as (delete from alerts returning *) select * from d",
    "select 1 /* unterminated", "select $$x$$", "do $$ begin end $$", "copy alerts to stdout", "set role postgres", "truncate alerts",
    "vacuum alerts", "select lo_import('/etc/passwd')", "select dblink('x','y')", "call p()", "grant all on alerts to anon",
    "select 'unterminated", "select 1 --\n; drop table t",
]


@pytest.mark.parametrize("sql", READ_ONLY)
def test_read_only_statements_are_approved(sql):
    assert is_read_only(sql)


@pytest.mark.parametrize("sql", NOT_READ_ONLY)
def test_anything_else_is_left_to_the_permission_prompt(sql):
    assert not is_read_only(sql)


def _run(payload) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(HOOK)], input=payload if isinstance(payload, str) else json.dumps(payload), capture_output=True, text=True, timeout=10, check=False)
    return result.returncode, result.stdout.strip()


def test_hook_prints_an_allow_decision_for_a_read():
    code, out = _run({"tool_name": "mcp__Supabase__execute_sql", "tool_input": {"project_id": "p", "query": "select count(*) from alerts"}})
    assert code == 0
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse" and decision["permissionDecision"] == "allow"


@pytest.mark.parametrize("payload", [
    {"tool_name": "mcp__Supabase__execute_sql", "tool_input": {"project_id": "p", "query": "update alerts set severity='x'"}},
    {"tool_name": "mcp__Supabase__apply_migration", "tool_input": {"project_id": "p", "query": "select 1"}},  # other tools are never touched
    {"tool_name": "mcp__Supabase__execute_sql", "tool_input": {}},
    {"tool_name": "mcp__Supabase__execute_sql", "tool_input": {"query": 42}},
    "not json at all",
    "",
])
def test_hook_says_nothing_otherwise(payload):
    code, out = _run(payload)
    assert code == 0 and out == ""


def test_settings_wire_the_hook_to_execute_sql_only():
    settings = json.loads((HOOK.parent.parent / "settings.json").read_text(encoding="utf-8"))
    entries = settings["hooks"]["PreToolUse"]
    assert [e["matcher"] for e in entries] == ["mcp__Supabase__execute_sql"]
    assert "supabase_readonly_sql.py" in entries[0]["hooks"][0]["command"]
    assert not settings.get("permissions", {}).get("allow"), "no blanket Supabase allow rule: only the hook may approve, and only reads"
