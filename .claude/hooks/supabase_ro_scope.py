#!/usr/bin/env python3
"""PreToolUse scope guard for the READ-ONLY Supabase MCP server (mcp__supabase_ro__execute_sql).  APPLICATION-LEVEL, not database-enforced.

What is enforced where
  * WRITES: by the database. That server runs every query as the platform's `supabase_read_only_user` (default_transaction_read_only=on, no
    write privileges, no executable SECURITY DEFINER functions), so SQL text is irrelevant to write safety and is not judged here.
  * READ SCOPE: by THIS FILE only. The role is a member of pg_read_all_data and can read every table; the `postgres` role we hold cannot revoke
    that platform-granted membership (tests/test_supabase_ro_access.py reproduces the refusal), so table-level scope cannot be made
    database-enforced from here. This guard is the interim control, backed by tools/intelligence/ro_scope_verify.sql.

Decisions (printed only when a rule matches; this guard NEVER prints "allow"; with no decision the settings allow-rule applies):
  deny  - the query names a public relation that is not on `permitted_relations`, a user-defined function, a credential/platform schema,
          a SQL-executing builtin (query_to_xml, ts_stat, ...), or a catalog object that exposes other sessions' text/credentials.
  ask   - the query is not a plain read (DO blocks, SET, CREATE, PREPARE/EXECUTE, multi-step transactions, unicode-escaped identifiers):
          those are the routes by which a session could build SQL dynamically and slip past a text scan, so a person decides.
          A table listed under `ask_tables` also asks.

Known limits (documented, tested): the scan is on text, so it can be too strict (an ordinary word equal to a table name, e.g. "tasks", is
refused) but not blind to quoting, case, schema-qualification or aliases; it cannot see inside a permitted VIEW (the verify script checks every
permitted view depends only on permitted relations); dynamic SQL is closed by refusing the executing functions and non-read statements.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from supabase_readonly_sql import (
    _FORBIDDEN,
    _READ_STARTS,
    _strip,
)

CONFIG = Path(__file__).with_name("supabase_ro_scope.json")

_FALLBACK = {
    "deny_schemas": ["vault", "auth", "storage", "net", "pgsodium"],
    "deny_catalog_names": ["pg_authid", "pg_shadow", "pg_stat_statements", "pg_stat_activity", "query_to_xml", "ts_stat"],
    "all_public_relations": [],
    "permitted_relations": [],
    "denied_user_functions": [],
    "ask_tables": [],
    "_unreadable": True,
}


def _load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(_FALLBACK)  # fail closed on credential schemas; with no relation lists everything except these is left to the DB role


def _remove_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)


def _is_plain_read(sql: str) -> bool:
    """True when every statement is a SELECT/WITH/VALUES/TABLE/SHOW/EXPLAIN (no ANALYZE) with no write, DDL, DO, SET or transaction keyword."""
    cleaned = _strip(sql)
    if cleaned is None:
        return False
    statements = [s.strip() for s in cleaned.split(";") if s.strip()]
    if not statements:
        return False
    for statement in statements:
        words = re.findall(r"[a-z_][a-z0-9_]*", statement.lower())
        if not words or words[0] not in _READ_STARTS:
            return False
        if words[0] == "explain" and any(w in ("analyze", "analyse") for w in words):
            return False
        if words[0] != "show" and any(w in _FORBIDDEN for w in words):
            return False
    return True


def classify(sql: str, config: dict | None = None) -> tuple[str, str] | None:
    config = config or _load_config()
    sql = sql or ""
    text = _remove_comments(sql)
    # Unicode-escaped identifiers/strings (U&"..", U&'..') can spell a name the scan would not recognise.
    if re.search(r"\bu\s*&\s*[\"']", text, flags=re.IGNORECASE):
        return "ask", "unicode-escaped identifiers cannot be scope-checked"
    if not _is_plain_read(sql):
        return "ask", "not a plain read (DO/SET/CREATE/PREPARE/transaction or unparseable): a person decides"
    # Scan the WHOLE text, string literals included: names passed as text to SQL-executing functions must not slip through.
    scan = text.replace('"', "").lower()

    def has(name: str) -> bool:
        return re.search(rf"(?<![a-z0-9_]){re.escape(name.lower())}(?![a-z0-9_])", scan) is not None

    for schema in config.get("deny_schemas", []):
        if re.search(rf"(?<![a-z0-9_.]){re.escape(schema.lower())}\s*\.\s*\w", scan):
            return "deny", f"schema '{schema}' holds credentials or platform internals and is not available to read-only research"
    for name in config.get("deny_catalog_names", []):
        if has(name):
            return "deny", f"'{name}' is not available to read-only research"
    if config.get("_unreadable"):
        return "ask", "scope configuration could not be read, so no standing approval applies (fail closed)"
    permitted = set(config.get("permitted_relations", []))
    for relation in config.get("all_public_relations", []):
        if relation not in permitted and has(relation):
            return "deny", f"'{relation}' is outside the permitted intelligence-research scope (see .claude/hooks/supabase_ro_scope.json)"
    for function in config.get("denied_user_functions", []):
        if has(function):
            return "deny", f"user-defined function '{function}' can read outside the permitted scope"
    # Column limits on permitted tables: forbidden columns by name, and no way to pull every column (`*`, whole-row JSON) from such a table.
    for table, columns in config.get("column_denies", {}).items():
        if has(table):
            for column in columns:
                if has(column):
                    return "deny", f"column '{column}' of '{table}' is outside the permitted scope"
            without_count_star = re.sub(r"count\s*\(\s*\*\s*\)", " ", scan)
            if re.search(r"(?:\bselect|\bdistinct|,|\.)\s*\*", without_count_star):  # `select *`, `b.*`, `, *`; not `~*` or `a * b`
                return "deny", f"list columns explicitly when reading '{table}' (a wildcard would include '{columns[0]}')"
            if re.search(r"\b(to_jsonb|to_json|row_to_json|json_agg|jsonb_agg)\s*\(\s*\w+\s*\)", without_count_star):
                return "deny", f"whole-row JSON of '{table}' would include '{columns[0]}': select named columns"
    for table in config.get("ask_tables", []):
        if has(table):
            return "ask", f"table '{table}' is listed as sensitive and needs explicit approval"
    return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    sql = ((payload.get("tool_input") or {}).get("query")) or ""
    result = classify(sql)
    if result:
        decision, reason = result
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
