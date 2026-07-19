"""
Governance dispatch CLI — the Python side of the Phase B transport bridge (D2).

The LCARS portal (Vercel) cannot call Python and cannot write past RLS with its
anon client. So a governed write flows:

    browser action
      -> Next.js route handler (injects X-User-Role server-side)
      -> Node Command-Centre backend route (X-Api-Key)
      -> spawn: python -m intelligence.workflow.cli   (this file)
      -> dispatch(SupabaseRepository(), action, role, payload)   [service-role]
      -> {status, body} JSON back up the chain

Contract:
  stdin  : JSON object {"action": str, "role": str, "payload": {...}}
           (or {action, role, payload} may be passed as a single --json arg)
  stdout : JSON object {"status": int, "body": {...}}   (always emitted)
  exit   : 0 for 2xx, 1 for 4xx/5xx  (the Node caller reads status from stdout
           regardless; the exit code is a convenience for shell callers)

This never sends the browser's asserted role — the caller must set `role`
server-side. Mirrors the spawn pattern of
core/command-centre/backend/connectors/intelligence-adapter.js.
"""

from __future__ import annotations

import json
import sys


def _read_request(argv: list[str]) -> dict:
    # Prefer an explicit --json arg (easier for spawn); else read stdin.
    if "--json" in argv:
        i = argv.index("--json")
        return json.loads(argv[i + 1])
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        req = _read_request(argv)
    except (json.JSONDecodeError, IndexError, ValueError) as exc:
        print(json.dumps({"status": 400, "body": {"error": f"bad request: {exc}"}}))
        return 1

    action = req.get("action", "")
    role = req.get("role", "")
    payload = req.get("payload") or {}

    try:
        from intelligence.workflow.api import dispatch
        from intelligence.workflow.repository import SupabaseRepository
        status, body = dispatch(SupabaseRepository(), action, role, payload)
    except Exception as exc:  # never leak a traceback to the transport
        print(json.dumps({"status": 500, "body": {"error": f"dispatch failed: {exc}"}}))
        return 1

    print(json.dumps({"status": status, "body": body}))
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    sys.exit(main())
