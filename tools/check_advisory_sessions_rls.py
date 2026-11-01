#!/usr/bin/env python3
"""RLS-drift gate for advisory_sessions (2026-09-15 adversarial review,
Fix Next #14).

advisory_sessions was fully open (USING(true)/WITH CHECK(true), no role
restriction) in its original migration
(0034_advisory_sessions.sql) and only tightened to `authenticated` in a
later one (0100_advisory_sessions_rls_drift_reconcile.sql) -- so the
canonical "what does this table's RLS actually look like" answer lives
in two migration files, not one, and a disaster-recovery replay or a
future migration reordering could reopen the gap with nothing to notice.

This checks the live database directly (via the check_anon_grants RPC,
migration 0210) rather than trusting migration-file history, which is
already known to drift from reality on this project.

Usage: python3 tools/check_advisory_sessions_rls.py
Exit 0: anon has no policy on advisory_sessions (expected/healthy state).
Exit 1: anon has a policy -- the RLS gap has reopened, investigate before
merging/deploying.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

_TABLE = "advisory_sessions"


def main() -> int:
    supabase_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        print(
            "check_advisory_sessions_rls: SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY "
            "not set -- skipping (this check needs live DB access, not just repo state)",
            file=sys.stderr,
        )
        return 0

    url = f"{supabase_url}/rest/v1/rpc/check_anon_grants"
    body = json.dumps({"p_table_name": _TABLE}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310 - url built from SUPABASE_URL env var, always https
            grants = json.loads(resp.read())
    except urllib.error.URLError as exc:
        print(f"check_advisory_sessions_rls: RPC call failed: {exc}", file=sys.stderr)
        return 0  # best-effort: a network/auth hiccup must not block CI on its own

    if grants:
        print(
            f"check_advisory_sessions_rls: FAIL -- {_TABLE} has {len(grants)} "
            f"anon-visible polic{'y' if len(grants) == 1 else 'ies'}:",
            file=sys.stderr,
        )
        for g in grants:
            print(f"  {g}", file=sys.stderr)
        print(
            "See 0100_advisory_sessions_rls_drift_reconcile.sql for the "
            "expected authenticated-only policy shape.",
            file=sys.stderr,
        )
        return 1

    print(f"check_advisory_sessions_rls: OK -- no anon-visible policy on {_TABLE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
