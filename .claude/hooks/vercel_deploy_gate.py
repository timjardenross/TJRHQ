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


_GIT_PUSH = re.compile(r"(?:^|[;&|\s])git\s+(?:-C\s+\S+\s+)?push\b")


def push_guard_missing(project_dir: str) -> str | None:
    """A branch that does not yet contain the lcars-portal/vercel.json branch guard triggers a Vercel preview on every push (each one
    counts toward the daily allowance). Returns the reason when the guard is absent from the checked-out commit, else None."""
    try:
        with open(os.path.join(project_dir, "lcars-portal", "vercel.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return None                                # no portal config in this checkout: nothing to protect
    enabled = ((cfg.get("git") or {}).get("deploymentEnabled")) or {}
    if isinstance(enabled, dict) and enabled.get("claude/**") is False:
        return None
    return ("this branch lacks the Vercel branch guard (lcars-portal/vercel.json git.deploymentEnabled 'claude/**': false), so each push "
            "would trigger a counted preview deployment. Merge origin/main into the branch first (the merge commit carries the guard), then push.")


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    tool, tool_input = event.get("tool_name", ""), event.get("tool_input") or {}
    if tool == "Bash" and _GIT_PUSH.search(str(tool_input.get("command", ""))):
        why = push_guard_missing(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
        if why:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                              "permissionDecisionReason": f"Vercel deployment policy (docs/ops/VERCEL-DEPLOYMENT-POLICY.md): {why}"}}))
        return 0
    kind = kind_of(tool, tool_input)
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
