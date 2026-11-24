#!/usr/bin/env python3
"""PreToolUse scope guard for the READ-ONLY Supabase MCP server (mcp__supabase_ro__execute_sql).

Write safety does NOT depend on this file: that server runs every query as the platform's `supabase_read_only_user`, a role with
`default_transaction_read_only=on` and no write privileges, so SQL text is irrelevant to safety and is not parsed here.
This guard only addresses *data scope*: that role can read every table (pg_read_all_data), so credential/auth schemas are
refused (decision "deny") and any table the Captain lists under `ask_tables` goes to the normal permission prompt ("ask").

Reads the hook JSON on stdin. Prints a decision only when a rule matches; otherwise prints nothing (the settings allow rule applies).
Never prints "allow".
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CONFIG = Path(__file__).with_name("supabase_ro_scope.json")


def _load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Fail closed on the credential schemas even when the config cannot be read.
        return {"deny_schemas": ["vault", "auth", "storage", "net", "pgsodium"], "deny_catalog_names": ["pg_authid", "pg_shadow"], "ask_tables": []}


def _strip_literals_and_comments(sql: str) -> str:
    """Blank string-literal contents and drop comments so a mention inside text does not trip the guard."""
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    return sql


def classify(sql: str, config: dict | None = None) -> tuple[str, str] | None:
    """Return ("deny"|"ask", reason) or None. Quoted identifiers are unquoted first so \"vault\".secrets is still caught."""
    config = config or _load_config()
    text = _strip_literals_and_comments(sql or "").replace('"', "").lower()
    for schema in config.get("deny_schemas", []):
        if re.search(rf"(?<![\w.]){re.escape(schema.lower())}\s*\.\s*\w", text):
            return "deny", f"schema '{schema}' holds credentials or platform internals and is not available to read-only research"
    for name in config.get("deny_catalog_names", []):
        if re.search(rf"(?<!\w){re.escape(name.lower())}(?!\w)", text):
            return "deny", f"'{name}' is not available to read-only research"
    for table in config.get("ask_tables", []):
        if re.search(rf"(?<![\w]){re.escape(table.lower())}(?![\w])", text):
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
