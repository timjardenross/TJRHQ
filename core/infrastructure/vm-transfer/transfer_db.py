"""SQLite transfer-state DB for the Secure File Transfer to VM agent
(USS-TJR-MSN-0205B).

Tracks per-file transfer status keyed on (source_name, rel_path) so repeat
runs are idempotent and failed transfers can be retried, plus an
append-only event log satisfying the "add transfer logs" requirement.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    dry_run INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL DEFAULT 'transfer',
    manifest_path TEXT,
    requested_count INTEGER NOT NULL DEFAULT 0,
    excluded_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    transferred_count INTEGER NOT NULL DEFAULT 0,
    verified_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS files_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    abs_path TEXT NOT NULL,
    expected_sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    remote_sha256 TEXT,
    last_batch_id INTEGER,
    updated_at TEXT NOT NULL,
    UNIQUE(source_name, rel_path)
);

CREATE TABLE IF NOT EXISTS transfer_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER,
    source_name TEXT,
    rel_path TEXT,
    event TEXT NOT NULL,
    detail TEXT,
    at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_status ON files_state(status);
CREATE INDEX IF NOT EXISTS idx_log_batch ON transfer_log(batch_id);
"""

# Statuses: pending, excluded, transferred (rsynced, not yet verified),
# verified (checksum OK, moved to received/), failed (checksum mismatch,
# rsync error, or exhausted retries — moved to failed/ where applicable).
TERMINAL_SUCCESS = "verified"


class TransferDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.conn.close()

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    # -- batches -----------------------------------------------------------

    def start_batch(self, manifest_path, dry_run: bool, now: str, kind: str = "transfer") -> int:
        cur = self.conn.execute(
            "INSERT INTO batches (created_at, dry_run, kind, manifest_path) VALUES (?, ?, ?, ?)",
            (now, int(dry_run), kind, str(manifest_path) if manifest_path else None),
        )
        return cur.lastrowid

    def finish_batch(self, batch_id, now, **counts):
        fields = {
            "requested_count": 0, "excluded_count": 0, "skipped_count": 0,
            "transferred_count": 0, "verified_count": 0, "failed_count": 0,
        }
        fields.update(counts)
        self.conn.execute(
            """UPDATE batches SET finished_at = ?, requested_count = ?, excluded_count = ?,
               skipped_count = ?, transferred_count = ?, verified_count = ?, failed_count = ?
               WHERE id = ?""",
            (now, fields["requested_count"], fields["excluded_count"], fields["skipped_count"],
             fields["transferred_count"], fields["verified_count"], fields["failed_count"], batch_id),
        )

    def get_batch(self, batch_id: int):
        cur = self.conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,))
        return cur.fetchone()

    # -- files_state -----------------------------------------------------------

    def get_file_state(self, source_name: str, rel_path: str):
        cur = self.conn.execute(
            "SELECT * FROM files_state WHERE source_name = ? AND rel_path = ?",
            (source_name, rel_path),
        )
        return cur.fetchone()

    def upsert_pending(self, source_name, rel_path, abs_path, sha256, size_bytes, now, batch_id):
        existing = self.get_file_state(source_name, rel_path)
        if existing is None:
            self.conn.execute(
                """INSERT INTO files_state
                   (source_name, rel_path, abs_path, expected_sha256, size_bytes, status,
                    attempts, last_batch_id, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?)""",
                (source_name, rel_path, abs_path, sha256, size_bytes, batch_id, now),
            )
        else:
            self.conn.execute(
                """UPDATE files_state SET abs_path = ?, expected_sha256 = ?, size_bytes = ?,
                   status = 'pending', last_error = NULL, last_batch_id = ?, updated_at = ?
                   WHERE id = ?""",
                (abs_path, sha256, size_bytes, batch_id, now, existing["id"]),
            )

    def mark_excluded(self, source_name, rel_path, now, batch_id, sha256=None, size_bytes=None, abs_path=None):
        existing = self.get_file_state(source_name, rel_path)
        if existing is not None:
            self.conn.execute(
                "UPDATE files_state SET status = 'excluded', last_batch_id = ?, updated_at = ? "
                "WHERE id = ?",
                (batch_id, now, existing["id"]),
            )
        else:
            self.conn.execute(
                """INSERT INTO files_state
                   (source_name, rel_path, abs_path, expected_sha256, size_bytes, status,
                    attempts, last_batch_id, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'excluded', 0, ?, ?)""",
                (source_name, rel_path, abs_path or "", sha256 or "", size_bytes or 0, batch_id, now),
            )

    def mark_transferred(self, source_name, rel_path, now, batch_id):
        self.conn.execute(
            "UPDATE files_state SET status = 'transferred', last_batch_id = ?, updated_at = ? "
            "WHERE source_name = ? AND rel_path = ?",
            (batch_id, now, source_name, rel_path),
        )

    def mark_verified(self, source_name, rel_path, remote_sha256, now, batch_id):
        self.conn.execute(
            "UPDATE files_state SET status = 'verified', remote_sha256 = ?, last_error = NULL, "
            "last_batch_id = ?, updated_at = ? WHERE source_name = ? AND rel_path = ?",
            (remote_sha256, batch_id, now, source_name, rel_path),
        )

    def mark_failed(self, source_name, rel_path, error, now, batch_id, remote_sha256=None):
        self.conn.execute(
            "UPDATE files_state SET status = 'failed', attempts = attempts + 1, last_error = ?, "
            "remote_sha256 = ?, last_batch_id = ?, updated_at = ? "
            "WHERE source_name = ? AND rel_path = ?",
            (error, remote_sha256, batch_id, now, source_name, rel_path),
        )

    def files_by_status(self, status: str):
        cur = self.conn.execute(
            "SELECT * FROM files_state WHERE status = ? ORDER BY source_name, rel_path",
            (status,),
        )
        return cur.fetchall()

    def failed_files(self, max_attempts: int):
        cur = self.conn.execute(
            "SELECT * FROM files_state WHERE status = 'failed' AND attempts < ? "
            "ORDER BY source_name, rel_path",
            (max_attempts,),
        )
        return cur.fetchall()

    # -- transfer_log -----------------------------------------------------------

    def log_event(self, batch_id, source_name, rel_path, event, detail, now):
        self.conn.execute(
            """INSERT INTO transfer_log (batch_id, source_name, rel_path, event, detail, at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (batch_id, source_name, rel_path, event, detail, now),
        )

    def events_for_batch(self, batch_id: int):
        cur = self.conn.execute(
            "SELECT * FROM transfer_log WHERE batch_id = ? ORDER BY id", (batch_id,)
        )
        return cur.fetchall()

    # -- summary -----------------------------------------------------------

    def summary(self):
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS c FROM files_state GROUP BY status"
        ).fetchall()
        latest = self.conn.execute(
            "SELECT * FROM batches WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {
            "by_status": {row["status"]: row["c"] for row in rows},
            "latest_batch": dict(latest) if latest else None,
        }
