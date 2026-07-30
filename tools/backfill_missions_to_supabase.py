#!/usr/bin/env python3
"""MSN-0173 WP2 — Safe Mission Ingestion Tool.

Backfills canonical USS-TJR-MSN-NNNN mission records into the Supabase
missions table. Idempotent: existing mission_ids are skipped.

Usage:
    python3 tools/backfill_missions_to_supabase.py [--dry-run] [--file missions.csv]

Without --file, backfills the hardcoded canonical missions list defined below.
With --file, expects CSV with columns: mission_id,title,status,priority,description

Status constraint (Supabase CHECK):
    Idea | Designed | Implemented | Tested | Awaiting Number One Review
    Validated | Awaiting XO Approval | Closed | Blocked | Archived

Env vars (from .env or environment):
    SUPABASE_URL, SUPABASE_KEY
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / "telegram-bots" / "xo" / ".env")
    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

VALID_STATUSES = {
    "Idea", "Designed", "Approved for Engineering", "Implemented", "Tested",
    "Awaiting Number One Review", "Validated", "Awaiting XO Approval",
    "Awaiting Captain Approval", "Approved",
    "Closed", "Blocked", "Archived", "Requires Rework",
}

REPO = "timjardenross/USSTJROS"

# Canonical missions absent from Supabase as of MSN-0173 assessment (2026-06-27).
# Extend this list for future backfills.
CANONICAL_MISSIONS = [
    ("USS-TJR-MSN-0144", "LCARS Canonical Mission Minting",              "Closed",      "P1", ""),
    ("USS-TJR-MSN-0145", "Runtime Registry Synchronisation",             "Closed",      "P1", ""),
    ("USS-TJR-MSN-0147", "Single Mission Minting Service",               "Closed",      "P1", ""),
    ("USS-TJR-MSN-0165", "Mission Minting Service Operationalisation",   "Implemented", "P1", ""),
    ("USS-TJR-MSN-0166", "Mobile Mission Operations Layer",              "Closed",      "P1", ""),
    ("USS-TJR-MSN-0167", "Telegram Mission Operations MVP: Phase 1 Read-Only", "Implemented", "P1", ""),
    ("USS-TJR-MSN-0168", "Mission Control API: Read Layer",              "Implemented", "P1", ""),
    ("USS-TJR-MSN-0169", "LCARS Mobile Sidebar Drawer",                 "Implemented", "P1", ""),
    ("USS-TJR-MSN-0170", "LCARS Mobile Drawer: Live Data Binding",      "Implemented", "P1", ""),
    ("USS-TJR-MSN-0171", "Mission Control API: Write Layer",            "Implemented", "P1", ""),
    ("USS-TJR-MSN-0172", "Telegram Mission Create: Phase 2",            "Implemented", "P1", ""),
    ("USS-TJR-MSN-0173", "Mission Control Data Reconciliation & Telegram Operational Readiness",
                                                                         "Idea",        "P1", ""),
]


def _get_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set.", file=sys.stderr)
        sys.exit(1)
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _existing_ids(db) -> set[str]:
    res = db.table("missions").select("mission_id").execute()
    return {r["mission_id"] for r in (res.data or []) if r.get("mission_id")}


def _validate_status(status: str) -> str:
    if status in VALID_STATUSES:
        return status
    print(f"  WARNING: '{status}' is not a valid status — defaulting to 'Idea'")
    return "Idea"


def backfill(missions: list[tuple], dry_run: bool = False) -> None:
    db = _get_client()
    existing = _existing_ids(db)
    print(f"Supabase: {len(existing)} existing mission_ids found.")

    to_insert = [m for m in missions if m[0] not in existing]
    skipped   = [m[0] for m in missions if m[0] in existing]

    if skipped:
        print(f"Skipping {len(skipped)} already-present: {', '.join(skipped)}")

    if not to_insert:
        print("Nothing to insert — all missions already present.")
        return

    print(f"Inserting {len(to_insert)} missions{' (DRY RUN)' if dry_run else ''}:")
    for row in to_insert:
        mission_id, title, status, priority, description = row
        status = _validate_status(status)
        print(f"  {mission_id}  [{status}]  {title[:60]}")
        if not dry_run:
            payload: dict = {
                "mission_id":  mission_id,
                "title":       title,
                "status":      status,
                "priority":    priority or None,
                "created_by":  "Chief Engineer",
                "repo":        REPO,
            }
            if description:
                payload["description"] = description
            result = db.table("missions").insert(payload).execute()
            if not result.data:
                print(f"  ERROR inserting {mission_id}: {result}")

    if not dry_run:
        print("Done.")


def backfill_from_csv(path: str, dry_run: bool = False) -> None:
    missions = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            missions.append((
                row["mission_id"].strip(),
                row["title"].strip(),
                row.get("status", "Idea").strip(),
                row.get("priority", "P1").strip(),
                row.get("description", "").strip(),
            ))
    backfill(missions, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill canonical missions to Supabase.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be inserted without writing.")
    parser.add_argument("--file", metavar="CSV", help="CSV file to import (mission_id,title,status,priority,description).")
    args = parser.parse_args()

    if args.file:
        backfill_from_csv(args.file, dry_run=args.dry_run)
    else:
        backfill(CANONICAL_MISSIONS, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
