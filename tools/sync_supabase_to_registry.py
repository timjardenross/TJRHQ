"""
MSN-0145: Sync Supabase missions → core/mission-control/registry/mission-index.txt

Reads the Supabase `missions` table and appends any canonical mission_ids
(USS-TJR-MSN-NNNN format) that are not already present in the authoritative
registry. Additive-only: no existing rows are modified or deleted.

Usage:
    python3 tools/sync_supabase_to_registry.py
    python3 tools/sync_supabase_to_registry.py --dry-run

Requirements:
    SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY) in env.
    pip install supabase  (already a project dependency)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REGISTRY = _REPO_ROOT / "core" / "mission-control" / "registry" / "mission-index.txt"

# Pattern that matches canonical table rows AND dash-list runtime entries in the registry
_REGISTRY_ID_RE = re.compile(r"USS-TJR-MSN-\d{4}[A-Za-z]?", re.IGNORECASE)


def load_registry_ids() -> set[str]:
    """Return all canonical mission IDs already present in the registry."""
    if not _REGISTRY.exists():
        return set()
    return set(_REGISTRY_ID_RE.findall(_REGISTRY.read_text(encoding="utf-8")))


def fetch_supabase_missions() -> list[dict]:
    """Fetch missions from Supabase that have a canonical USS-TJR-MSN-NNNN mission_id."""
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in environment.", file=sys.stderr)
        sys.exit(1)

    try:
        from supabase import create_client  # type: ignore[import]
    except ImportError:
        print("ERROR: supabase package not installed. Run: pip install supabase", file=sys.stderr)
        sys.exit(1)

    client = create_client(url, key)
    result = (
        client.table("missions")
        .select("mission_id, title, status, priority, created_at")
        .order("created_at")
        .execute()
    )
    rows = result.data or []
    canonical_pattern = re.compile(r"^USS-TJR-MSN-\d{4}[A-Za-z]?$", re.IGNORECASE)
    return [r for r in rows if r.get("mission_id") and canonical_pattern.match(r["mission_id"])]


def sync(dry_run: bool = False) -> int:
    registry_ids = load_registry_ids()
    missions = fetch_supabase_missions()

    new_missions = [m for m in missions if m["mission_id"].upper() not in {i.upper() for i in registry_ids}]

    if not new_missions:
        print(f"Registry already up-to-date. {len(missions)} Supabase canonical missions, all present.")
        return 0

    print(f"Found {len(new_missions)} missions in Supabase not yet in registry:")
    for m in new_missions:
        print(f"  {m['mission_id']:<25} {(m.get('status') or '—'):<20} {(m.get('title') or '')[:60]}")

    if dry_run:
        print("[dry-run] No changes written.")
        return 0

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    with _REGISTRY.open("a", encoding="utf-8") as f:
        f.write(f"\n# MSN-0145 SUPABASE SYNC ({ts})\n")
        for m in new_missions:
            mid = m["mission_id"].upper()
            title = (m.get("title") or "—").replace("|", "—")
            status = (m.get("status") or "—")
            f.write(f"\n- {mid} | {ts} | Supabase | {status} | {title}\n")

    print(f"Appended {len(new_missions)} entries to {_REGISTRY.relative_to(_REPO_ROOT)}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Supabase missions to authoritative registry")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing")
    args = parser.parse_args()
    sys.exit(sync(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
