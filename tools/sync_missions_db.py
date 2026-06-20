"""
WP-4: Sync mission-index.txt → missions.db

One-time (and repeatable) sync from the flat-file mission registry into the
local SQLite missions.db. Safe to re-run — uses INSERT OR REPLACE.

Usage:
    python3 tools/sync_missions_db.py
    python3 tools/sync_missions_db.py --dry-run   # print without writing
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

_REPO_ROOT  = Path(__file__).resolve().parents[1]
_REGISTRY   = _REPO_ROOT / "core" / "mission-control" / "registry" / "mission-index.txt"
_DB_PATH    = _REPO_ROOT / "missions.db"


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS missions (
    id              TEXT PRIMARY KEY,
    title           TEXT,
    priority        TEXT,
    status          TEXT,
    mission_owner   TEXT,
    assigned_specialist TEXT,
    reference       TEXT,
    source          TEXT DEFAULT 'mission-index.txt',
    synced_at       TEXT
);
"""

INSERT_MISSION = """
INSERT OR REPLACE INTO missions
    (id, title, priority, status, mission_owner, assigned_specialist, reference, source, synced_at)
VALUES
    (?, ?, ?, ?, ?, ?, ?, 'mission-index.txt', ?);
"""


def parse_registry(path: Path) -> list[dict]:
    """Parse mission-index.txt table rows."""
    missions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or "Mission ID" in line or line.startswith("|---"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 6 or not parts[1]:
            continue
        missions.append({
            "id":           parts[1],
            "title":        parts[2] if len(parts) > 2 else "",
            "priority":     parts[3] if len(parts) > 3 else "",
            "status":       parts[4] if len(parts) > 4 else "",
            "owner":        parts[5] if len(parts) > 5 else "",
            "specialist":   parts[6] if len(parts) > 6 else "",
            "reference":    parts[7] if len(parts) > 7 else "",
        })
    return missions


def sync(dry_run: bool = False) -> int:
    if not _REGISTRY.exists():
        print(f"ERROR: Registry not found: {_REGISTRY}", file=sys.stderr)
        return 1

    missions = parse_registry(_REGISTRY)
    if not missions:
        print("ERROR: No missions parsed from registry.", file=sys.stderr)
        return 1

    print(f"Parsed {len(missions)} missions from {_REGISTRY.name}")

    if dry_run:
        for m in missions[:10]:
            print(f"  {m['id']:<30} {m['status']:<25} {m['title'][:50]}")
        if len(missions) > 10:
            print(f"  ... and {len(missions) - 10} more")
        print("[dry-run] No changes written.")
        return 0

    conn = sqlite3.connect(str(_DB_PATH))
    try:
        conn.execute(CREATE_TABLE)
        now = datetime.utcnow().isoformat() + "Z"
        inserted = 0
        for m in missions:
            conn.execute(INSERT_MISSION, (
                m["id"], m["title"], m["priority"], m["status"],
                m["owner"], m["specialist"], m["reference"], now,
            ))
            inserted += 1
        conn.commit()
        print(f"Synced {inserted} missions to {_DB_PATH}")
    finally:
        conn.close()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Sync mission registry to missions.db")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing")
    args = parser.parse_args()
    sys.exit(sync(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
