#!/usr/bin/env python3
"""PreToolUse hook for mcp__Supabase__execute_sql: auto-approve statements that are provably read-only.

Reads the hook JSON on stdin. Prints an "allow" decision only when EVERY statement in the query is a plain read; for
anything else (a write, DDL, a transaction, an unknown function, something it cannot parse) it prints nothing and exits 0,
so the normal permission prompt applies. It never denies and never lets a write through: when in doubt it asks.

Deliberately conservative:
  - a statement must start with SELECT / WITH / VALUES / TABLE / SHOW, or EXPLAIN without ANALYZE;
  - any write, DDL, privilege, transaction or locking keyword anywhere (outside string literals) means "ask";
  - every function call must be on a short allowlist of pure/read functions, because a SELECT can call a function that
    writes (this database has prune_* functions that delete rows); a schema-qualified or unknown function means "ask";
  - dollar-quoting, block comments that do not close, or an empty query means "ask".
Apply_migration and every other Supabase tool are untouched: this hook only matches execute_sql (see .claude/settings.json).
"""

from __future__ import annotations

import json
import re
import sys

_FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "create", "truncate", "grant", "revoke", "copy", "merge", "call", "do",
    "vacuum", "analyze", "reindex", "cluster", "refresh", "lock", "set", "reset", "comment", "security", "listen", "notify",
    "unlisten", "begin", "start", "commit", "rollback", "savepoint", "release", "abort", "prepare", "execute", "deallocate",
    "declare", "fetch", "move", "close", "discard", "load", "import", "into", "returning", "for", "attach", "detach", "checkpoint",
}
# Pure or read-only functions and constructs that may be followed by "(".
_SAFE_CALLS = {
    "count", "sum", "avg", "min", "max", "bool_and", "bool_or", "array_agg", "string_agg", "jsonb_agg", "json_agg", "jsonb_object_agg",
    "percentile_cont", "percentile_disc", "mode", "stddev", "variance", "row_number", "rank", "dense_rank", "lag", "lead", "first_value",
    "last_value", "ntile", "now", "current_date", "current_timestamp", "date_trunc", "date_part", "extract", "age", "make_interval",
    "to_char", "to_timestamp", "to_date", "to_number", "round", "floor", "ceil", "ceiling", "abs", "greatest", "least", "coalesce",
    "nullif", "lower", "upper", "length", "char_length", "left", "right", "substring", "substr", "position", "strpos", "replace",
    "trim", "ltrim", "rtrim", "split_part", "concat", "concat_ws", "format", "regexp_match", "regexp_matches", "regexp_replace",
    "regexp_split_to_array", "starts_with", "md5", "initcap", "cast", "exists", "any", "all", "in", "values", "over", "filter",
    "within", "lateral", "unnest", "generate_series", "jsonb_array_length", "jsonb_array_elements", "jsonb_array_elements_text",
    "jsonb_each", "jsonb_each_text", "jsonb_object_keys", "jsonb_typeof", "jsonb_build_object", "jsonb_extract_path_text",
    "jsonb_path_exists", "json_array_length", "array_length", "cardinality", "array_to_string", "string_to_array", "pg_typeof",
    "octet_length", "sign", "mod", "power", "sqrt", "log", "ln", "exp", "timezone", "isfinite", "date", "interval", "numeric", "int",
    "integer", "bigint", "text", "varchar", "timestamptz", "timestamp", "boolean", "uuid", "jsonb", "json", "double", "precision",
    "char", "bit", "time", "tsvector", "to_tsvector", "to_tsquery", "plainto_tsquery", "ts_rank", "pg_size_pretty",
    "pg_total_relation_size", "pg_relation_size", "pg_database_size", "obj_description", "col_description", "current_setting",
    "has_table_privilege", "has_schema_privilege", "to_regclass", "row", "array", "rows", "between", "and", "or", "not", "when",
    "then", "else", "end", "case", "as", "on", "using", "from", "where", "by", "group", "order", "having", "limit", "offset",
    "union", "intersect", "except", "distinct", "select", "with", "recursive", "join", "inner", "outer", "full",
    "cross", "natural", "table", "show", "explain", "like", "ilike", "similar", "to", "is", "null", "true", "false", "asc", "desc",
    "nulls", "first", "last", "partition", "range", "preceding", "following", "unbounded", "current", "window", "at", "zone",
}
_READ_STARTS = ("select", "with", "values", "table", "show", "explain")


def _strip(sql: str) -> str | None:
    """SQL with comments removed and string / quoted-identifier contents blanked; None if it cannot be tokenised safely."""
    if "$$" in sql or re.search(r"\$[A-Za-z_]*\$", sql):
        return None
    out, i, n = [], 0, len(sql)
    while i < n:
        two = sql[i:i + 2]
        if two == "--":
            j = sql.find("\n", i)
            i = n if j == -1 else j
        elif two == "/*":
            j = sql.find("*/", i + 2)
            if j == -1:
                return None
            i = j + 2
            out.append(" ")
        elif sql[i] in ("'", '"'):
            quote, j = sql[i], i + 1
            while j < n:
                if sql[j] == quote:
                    if sql[j + 1:j + 2] == quote:  # doubled quote inside the literal
                        j += 2
                        continue
                    break
                j += 1
            if j >= n:
                return None
            out.append(" '' " if quote == "'" else ' "" ')
            i = j + 1
        else:
            out.append(sql[i])
            i += 1
    return "".join(out)


def is_read_only(sql: str) -> bool:
    cleaned = _strip(sql or "")
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
        if any(w in _FORBIDDEN for w in words if words[0] != "show"):
            return False
        # every identifier directly followed by "(" is a call: it must be allowlisted and not schema-qualified
        for match in re.finditer(r"([a-z_][a-z0-9_.]*)\s*\(", statement.lower()):
            name = match.group(1)
            if "." in name or name not in _SAFE_CALLS:
                return False
    return True


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        query = (payload.get("tool_input") or {}).get("query")
        if payload.get("tool_name") == "mcp__Supabase__execute_sql" and isinstance(query, str) and is_read_only(query):
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "allow",
                "permissionDecisionReason": "read-only SQL (auto-approved by .claude/hooks/supabase_readonly_sql.py)",
            }}))
    except Exception:  # noqa: BLE001 - any failure means "no decision": the normal permission prompt applies
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
