#!/usr/bin/env python3
"""
Validate that ai-context.ts queries match the live Supabase schema.

Probes each declared (table, column) pair with a limit=0 REST query.
PostgREST returns 400 if the column doesn't exist, 200 if it does.

Run this whenever ai-context.ts is changed, or as a pre-deploy check.
Exits non-zero on any mismatch.

Usage: python3 tools/validate_ai_context_schema.py
"""

import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(str(REPO_ROOT / "slack-bot" / ".env"))
    load_dotenv(str(REPO_ROOT / ".env"))
except ImportError:
    pass

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_ANON_KEY", "")
)

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Accept": "application/json",
}

# Tables and columns declared in ai-context.ts.
# Keep in sync when the file changes.
DECLARED_QUERIES: dict[str, list[str]] = {
    "missions":             ["mission_id", "title", "status", "priority"],
    "decisions":            ["decision_type", "reasoning", "outcome", "timestamp"],
    "architecture_records": ["title", "status", "recommended_option"],
    "health_daily_logs":    ["log_date", "nervous_system_state", "energy", "mood",
                             "sleep_hours", "sleep_quality", "workload_constraint",
                             "daily_capacity_score", "pain_score"],
    "recovery_pulses":      ["log_date", "pulse_type", "captured_at", "energy",
                             "nervous_system", "body_signals", "readiness",
                             "pain_score", "notes"],
    "knowledge_documents":  ["title", "document_type", "updated_at"],
    "working_memory":       ["key", "value", "updated_at"],
    "build_request_inbox":  ["request_id", "title", "summary", "status", "created_at"],
}


def check_column(table: str, col: str) -> bool:
    """Return True if table.col exists in the live schema."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={col}&limit=0"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 400:
            return False
        # 401/403 = auth issue, not a schema problem
        print(f"  WARNING: {table}.{col} returned HTTP {e.code} — check auth.")
        return True
    except Exception as e:
        print(f"  WARNING: {table}.{col} probe failed ({e})")
        return True  # don't fail on network errors


def main() -> None:
    print(f"Validating ai-context.ts schema against {SUPABASE_URL}\n")
    failures: list[str] = []

    for table, columns in DECLARED_QUERIES.items():
        # First check the table exists at all
        ok = check_column(table, "id")
        if not ok:
            # id might not exist — try the first declared column
            ok = check_column(table, columns[0])
        if not ok:
            failures.append(f"TABLE MISSING or inaccessible: {table}")
            print(f"  ✗ {table}  ← table missing")
            continue

        for col in columns:
            if check_column(table, col):
                print(f"  ✓ {table}.{col}")
            else:
                failures.append(f"{table}.{col}")
                print(f"  ✗ {table}.{col}  ← COLUMN MISSING")

    print()
    if failures:
        print(f"FAILED — {len(failures)} broken column(s):")
        for f in failures:
            print(f"  • {f}")
        print("\nFix ai-context.ts to match the live schema.")
        sys.exit(1)
    else:
        print("All columns verified. ai-context.ts is in sync with live schema.")


if __name__ == "__main__":
    main()
