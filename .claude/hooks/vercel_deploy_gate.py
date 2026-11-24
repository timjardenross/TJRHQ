#!/usr/bin/env python3
"""PreToolUse hook: no agent creates a Vercel deployment without a budget ticket.

Matches the Vercel create_deployment tool and `vercel` CLI deploys run through Bash. A deployment is refused unless a fresh,
single-use ticket for its kind (preview or production) exists; tickets are issued only by tools/ops/vercel_deploy_budget.py
from a current deployment list when the internal budget (10 previews, 10 routine production deployments per rolling 24 h) allows it.
It never auto-approves: with a ticket the normal permission prompt still applies. Rollbacks, promotions and every read tool are untouched.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()), "tools", "ops"))
import vercel_deploy_budget as vb

_CLI_DEPLOY = re.compile(r"(?:^|[;&|\s])vercel(?:\s+deploy|\s+--prod|\s+-p\b|\s*$)|vercel\s+(?:build\s+&&\s+)?deploy|\bvercel\s+--prebuilt", re.IGNORECASE)


def kind_of(tool: str, tool_input: dict) -> str | None:
    if tool == "mcp__Vercel__create_deployment":
        body = tool_input.get("requestBody") or {}
        return "production" if str(body.get("target", "")).lower() == "production" else "preview"
    if tool == "Bash":
        cmd = str(tool_input.get("command", ""))
        if _CLI_DEPLOY.search(cmd):
            return "production" if re.search(r"--prod\b|--target[= ]production", cmd) else "preview"
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    kind = kind_of(event.get("tool_name", ""), event.get("tool_input") or {})
    if kind is None:
        return 0
    ok, why = vb.consume_ticket(kind)
    if ok:
        return 0                        # a ticket was valid: the normal permission prompt applies, nothing is auto-approved
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                      "permissionDecisionReason": f"Vercel deployment policy (docs/ops/VERCEL-DEPLOYMENT-POLICY.md): {why}"}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
