#!/usr/bin/env python3
"""PreToolUse guard for the PRIVILEGED Supabase connector's mutating tools (migrations, edge-function deploys and secrets, branches,
project pause/restore/create, notebooks, feedback). Always prints an explicit "ask": with the connector set to Always Allow these tools
would otherwise run unprompted against production (and some spend money). Never prints "allow" or "deny".

Matched in .claude/settings.json by tool name; the read tools and execute_sql (handled by supabase_readonly_sql.py) are not matched.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        tool = str(payload.get("tool_name") or "this Supabase tool")
    except Exception:  # noqa: BLE001
        tool = "this Supabase tool"
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "ask",
        "permissionDecisionReason": f"{tool} changes production or incurs cost: explicit approval required (the connector is set to Always Allow).",
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
