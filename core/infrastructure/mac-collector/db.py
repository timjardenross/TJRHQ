"""SQLite tracking database for the Mac File Collector Agent (USS-TJR-MSN-0205A).

Tracks known files by (source_name, rel_path), their content hash and
metadata, and a per-scan change log (new / changed / deleted) so that
`list-new`, `list-changed`, and `status` don't need to recompute diffs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_scan_id INTEGER,
    UNIQUE(source_name, rel_path)
);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    dry_run INTEGER NOT NULL DEFAULT 0,
    sources TEXT NOT NULL,
    files_scanned INTEGER NOT NULL DEFAULT 0,
    ignored_count INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    changed_count INTEGER NOT NULL DEFAULT 0,
    deleted_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL,
    source_name TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    change_type TEXT NOT NULL,
    sha256_old TEXT,
    sha256_new TEXT,
    size_bytes INTEGER,
    detected_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_source ON files(source_name);
CREATE INDEX IF NOT EXISTS idx_changes_scan ON changes(scan_id, change_type);
"""


class TrackingDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.conn.close()

    # -- files -----------------------------------------------------------

    def get_file(self, source_name: str, rel_path: str):
        cur = self.conn.execute(
            "SELECT * FROM files WHERE source_name = ? AND rel_path = ?",
            (source_name, rel_path),
        )
        return cur.fetchone()

    def upsert_file(self, source_name, rel_path, sha256, size_bytes, mtime, now, scan_id):
        existing = self.get_file(source_name, rel_path)
        if existing is None:
            self.conn.execute(
                """INSERT INTO files
                   (source_name, rel_path, sha256, size_bytes, mtime, status,
                    first_seen, last_seen, last_scan_id)
                   VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
                (source_name, rel_path, sha256, size_bytes, mtime, now, now, scan_id),
            )
            return "new", None
        if existing["sha256"] != sha256 or existing["status"] != "active":
            old_sha = existing["sha256"]
            self.conn.execute(
                """UPDATE files SET sha256 = ?, size_bytes = ?, mtime = ?, status = 'active',
                   last_seen = ?, last_scan_id = ? WHERE id = ?""",
                (sha256, size_bytes, mtime, now, scan_id, existing["id"]),
            )
            return "changed", old_sha
        self.conn.execute(
            "UPDATE files SET last_seen = ?, last_scan_id = ? WHERE id = ?",
            (now, scan_id, existing["id"]),
        )
        return "unchanged", None

    def mark_missing_as_deleted(self, source_name: str, seen_rel_paths: set, now: str, scan_id: int):
        cur = self.conn.execute(
            "SELECT rel_path FROM files WHERE source_name = ? AND status = 'active'",
            (source_name,),
        )
        deleted = []
        for row in cur.fetchall():
            if row["rel_path"] not in seen_rel_paths:
                self.conn.execute(
                    "UPDATE files SET status = 'deleted', last_seen = ?, last_scan_id = ? "
                    "WHERE source_name = ? AND rel_path = ?",
                    (now, scan_id, source_name, row["rel_path"]),
                )
                deleted.append(row["rel_path"])
        return deleted

    def active_files(self, source_name=None):
        if source_name:
            cur = self.conn.execute(
                "SELECT * FROM files WHERE status = 'active' AND source_name = ? "
                "ORDER BY source_name, rel_path",
                (source_name,),
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM files WHERE status = 'active' ORDER BY source_name, rel_path"
            )
        return cur.fetchall()

    # -- scans -------------------------------------------------------------

    def start_scan(self, sources: str, dry_run: bool, now: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO scans (started_at, dry_run, sources) VALUES (?, ?, ?)",
            (now, int(dry_run), sources),
        )
        return cur.lastrowid

    def finish_scan(self, scan_id: int, now: str, files_scanned, ignored_count,
                     new_count, changed_count, deleted_count):
        self.conn.execute(
            """UPDATE scans SET finished_at = ?, files_scanned = ?, ignored_count = ?,
               new_count = ?, changed_count = ?, deleted_count = ? WHERE id = ?""",
            (now, files_scanned, ignored_count, new_count, changed_count, deleted_count, scan_id),
        )

    def latest_scan(self):
        cur = self.conn.execute(
            "SELECT * FROM scans WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
        )
        return cur.fetchone()

    def get_scan(self, scan_id: int):
        cur = self.conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,))
        return cur.fetchone()

    # -- changes -------------------------------------------------------------

    def record_change(self, scan_id, source_name, rel_path, change_type,
                       sha256_old, sha256_new, size_bytes, now):
        self.conn.execute(
            """INSERT INTO changes
               (scan_id, source_name, rel_path, change_type, sha256_old, sha256_new,
                size_bytes, detected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (scan_id, source_name, rel_path, change_type, sha256_old, sha256_new,
             size_bytes, now),
        )

    def changes_for_scan(self, scan_id: int, change_type: str):
        cur = self.conn.execute(
            "SELECT * FROM changes WHERE scan_id = ? AND change_type = ? "
            "ORDER BY source_name, rel_path",
            (scan_id, change_type),
        )
        return cur.fetchall()

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    # -- summary -------------------------------------------------------------

    def summary(self):
        total = self.conn.execute(
            "SELECT COUNT(*) AS c FROM files WHERE status = 'active'"
        ).fetchone()["c"]
        by_source = self.conn.execute(
            "SELECT source_name, COUNT(*) AS c FROM files WHERE status = 'active' "
            "GROUP BY source_name"
        ).fetchall()
        deleted = self.conn.execute(
            "SELECT COUNT(*) AS c FROM files WHERE status = 'deleted'"
        ).fetchone()["c"]
        latest = self.latest_scan()
        return {
            "total_active_files": total,
            "deleted_files": deleted,
            "by_source": {row["source_name"]: row["c"] for row in by_source},
            "latest_scan": dict(latest) if latest else None,
        }
