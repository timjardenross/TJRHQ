"""Scan engine for the Mac File Collector Agent (USS-TJR-MSN-0205A).

Walks configured source folders, fingerprints eligible files with SHA256,
and diffs against the SQLite tracking DB to detect new / changed / deleted
files. In dry-run mode the same walk + diff logic runs but the DB
transaction is rolled back instead of committed, so nothing is persisted.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import cloud_detection
from config import Config, Source
from db import TrackingDB
from ignore_rules import IgnoreMatcher

CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path, chunk_size: int = CHUNK_SIZE) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ScanResult:
    scan_id: int
    dry_run: bool
    files_scanned: int = 0
    ignored_count: int = 0
    cloud_only_count: int = 0
    unavailable_count: int = 0
    new_files: list = field(default_factory=list)
    changed_files: list = field(default_factory=list)
    deleted_files: list = field(default_factory=list)
    ignored_files: list = field(default_factory=list)
    cloud_only_files: list = field(default_factory=list)
    unavailable_files: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def iter_source_files(root: Path):
    """Yield (rel_posix_path, absolute_path) for regular files under root.

    Skips symlinks (files and directories) to avoid escaping the source
    root or following loops.
    """
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            abs_path = Path(dirpath) / name
            if abs_path.is_symlink():
                continue
            rel = abs_path.relative_to(root)
            yield rel.as_posix(), abs_path


class Collector:
    def __init__(self, config: Config, check_availability_fn=cloud_detection.check_availability):
        self.config = config
        self.matcher = IgnoreMatcher(
            patterns=config.ignore.patterns,
            max_file_size_mb=config.ignore.max_file_size_mb,
            ignore_hidden=config.ignore.ignore_hidden,
        )
        self.check_availability_fn = check_availability_fn

    def scan(self, db: TrackingDB, source_names=None, dry_run: bool = False) -> ScanResult:
        sources = [s for s in self.config.sources if s.enabled]
        if source_names:
            sources = [s for s in sources if s.name in source_names]

        now = _now()
        scan_id = db.start_scan(
            sources=",".join(s.name for s in sources), dry_run=dry_run, now=now
        )
        result = ScanResult(scan_id=scan_id, dry_run=dry_run)

        for source in sources:
            if not source.path.exists():
                result.errors.append(f"{source.name}: source path not found: {source.path}")
                continue

            seen_rel_paths = set()
            for rel_posix, abs_path in iter_source_files(source.path):
                try:
                    size_bytes = abs_path.stat().st_size
                except OSError as exc:
                    result.errors.append(f"{source.name}:{rel_posix}: {exc}")
                    continue

                decision = self.matcher.match(rel_posix, size_bytes)
                if decision.ignored:
                    result.ignored_count += 1
                    result.ignored_files.append(
                        {"source": source.name, "path": rel_posix, "reason": decision.reason}
                    )
                    continue

                seen_rel_paths.add(rel_posix)

                # MSN-0206J-3: check for cloud-only placeholders before
                # hashing — hashing a not-yet-downloaded file either reads
                # garbage/zero-byte data or silently triggers an OS-level
                # download. Skipped when the operator opts in via
                # include_cloud_only.
                if not self.config.ignore.include_cloud_only:
                    availability = self.check_availability_fn(abs_path)
                    if availability == "cloud_only":
                        result.cloud_only_count += 1
                        result.cloud_only_files.append(
                            {"source": source.name, "path": rel_posix, "reason": "cloud-only placeholder"}
                        )
                        continue
                    if availability == "unavailable":
                        result.unavailable_count += 1
                        result.unavailable_files.append(
                            {"source": source.name, "path": rel_posix, "reason": "not available on disk"}
                        )
                        continue

                try:
                    digest = sha256_file(abs_path)
                    mtime = abs_path.stat().st_mtime
                except OSError as exc:
                    result.errors.append(f"{source.name}:{rel_posix}: {exc}")
                    continue

                result.files_scanned += 1
                change_type, old_sha = db.upsert_file(
                    source.name, rel_posix, digest, size_bytes, mtime, now, scan_id
                )
                if change_type == "new":
                    result.new_files.append(
                        {"source": source.name, "path": rel_posix, "sha256": digest, "size_bytes": size_bytes}
                    )
                    db.record_change(scan_id, source.name, rel_posix, "new", None, digest, size_bytes, now)
                elif change_type == "changed":
                    result.changed_files.append(
                        {
                            "source": source.name,
                            "path": rel_posix,
                            "sha256": digest,
                            "sha256_old": old_sha,
                            "size_bytes": size_bytes,
                        }
                    )
                    db.record_change(scan_id, source.name, rel_posix, "changed", old_sha, digest, size_bytes, now)

            # Only reconcile deletions for a source we actually walked —
            # never wipe tracked files because a drive was unmounted.
            deleted = db.mark_missing_as_deleted(source.name, seen_rel_paths, now, scan_id)
            for rel_posix in deleted:
                result.deleted_files.append({"source": source.name, "path": rel_posix})
                db.record_change(scan_id, source.name, rel_posix, "deleted", None, None, None, now)

        db.finish_scan(
            scan_id,
            now,
            files_scanned=result.files_scanned,
            ignored_count=result.ignored_count,
            new_count=len(result.new_files),
            changed_count=len(result.changed_files),
            deleted_count=len(result.deleted_files),
        )

        if dry_run:
            db.rollback()
        else:
            db.commit()

        return result
