"""Transfer orchestration engine for the Secure File Transfer to VM agent
(USS-TJR-MSN-0205B).

Reads the manifest produced by the Mac Collector Agent (MSN-0205A),
applies a transfer-time exclude blocklist, pushes files to the VM's
inbox/pending via rsync-over-SSH with retry, verifies SHA256 checksums
remotely, and moves each file to inbox/received (checksum OK) or
inbox/failed (checksum mismatch / rsync exhausted retries).

Depends on `transport` only via duck-typed methods (ensure_remote_dirs,
rsync_push, push_text_file, verify_checksums, run_remote_script) so tests
run against a fake with no network access.

Commits happen per source-group, right after rsync success (status →
'transferred') and again after the checksum/move step (status →
'verified'/'failed'). That makes an interrupted run resumable: if the
process dies between the rsync succeeding and the checksum step
finishing, the files are durably left in 'transferred' state and
`verify_transfer()` can pick them up without re-sending anything.
"""

from __future__ import annotations

import json
import shlex
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_manifest(path) -> list:
    with open(path, "r") as f:
        data = json.load(f)
    return data.get("files", [])


def source_root_from_entry(entry) -> Path:
    """Reconstruct a source's local root dir from one manifest/state entry.

    mac-collector's export-manifest builds abs_path as `source_root /
    rel_path`; walking up len(rel_path.parts) directories from abs_path
    recovers source_root regardless of how deep rel_path is nested.
    """
    abs_path = Path(entry["abs_path"])
    root = abs_path
    for _ in Path(entry["rel_path"]).parts:
        root = root.parent
    return root


def parse_checksum_output(stdout: str) -> dict:
    """Parse `sha256sum -c -` stdout into {rel_path: bool_ok}."""
    results = {}
    for line in stdout.splitlines():
        line = line.rstrip()
        if not line or ": " not in line:
            continue
        path, status = line.rsplit(": ", 1)
        results[path] = status.strip().upper().startswith("OK")
    return results


@dataclass
class TransferSummary:
    batch_id: int
    dry_run: bool
    requested_count: int = 0
    excluded_count: int = 0
    skipped_count: int = 0
    transferred_count: int = 0
    verified_count: int = 0
    failed_count: int = 0
    failures: list = field(default_factory=list)
    planned: list = field(default_factory=list)

    def as_dict(self):
        return {
            "batch_id": self.batch_id,
            "dry_run": self.dry_run,
            "requested_count": self.requested_count,
            "excluded_count": self.excluded_count,
            "skipped_count": self.skipped_count,
            "transferred_count": self.transferred_count,
            "verified_count": self.verified_count,
            "failed_count": self.failed_count,
            "failures": self.failures,
            "planned": self.planned,
        }


class TransferEngine:
    def __init__(self, config, db, transport):
        self.config = config
        self.db = db
        self.transport = transport
        self.matcher = config.build_exclude_matcher()

    # -- selection -----------------------------------------------------------

    def _select(self, entries, batch_id, dry_run):
        to_transfer, excluded, skipped = [], [], []
        now = _now()
        for entry in entries:
            decision = self.matcher.match(entry["rel_path"])
            if decision.ignored:
                excluded.append(entry)
                if not dry_run:
                    self.db.mark_excluded(entry["source"], entry["rel_path"], now, batch_id,
                                           sha256=entry.get("sha256"), size_bytes=entry.get("size_bytes"),
                                           abs_path=entry.get("abs_path"))
                self.db.log_event(batch_id, entry["source"], entry["rel_path"],
                                   "excluded", decision.reason, now)
                continue

            existing = self.db.get_file_state(entry["source"], entry["rel_path"])
            if (existing is not None and existing["status"] == "verified"
                    and existing["expected_sha256"] == entry["sha256"]):
                skipped.append(entry)
                self.db.log_event(batch_id, entry["source"], entry["rel_path"],
                                   "skipped_already_verified", None, now)
                continue

            to_transfer.append(entry)
            if not dry_run:
                self.db.upsert_pending(
                    entry["source"], entry["rel_path"], entry["abs_path"],
                    entry["sha256"], entry["size_bytes"], now, batch_id,
                )
            self.db.log_event(batch_id, entry["source"], entry["rel_path"], "queued", None, now)

        if not dry_run:
            self.db.commit()
        return to_transfer, excluded, skipped

    @staticmethod
    def _group_by_source(entries):
        groups = {}
        for entry in entries:
            groups.setdefault(entry["source"], []).append(entry)
        return groups

    # -- core batch execution (shared by transfer + retry) -----------------------------------------------------------

    def _execute_batch(self, entries, batch_id, dry_run):
        totals = {"transferred_count": 0, "verified_count": 0, "failed_count": 0,
                  "failures": [], "planned": []}

        for source_name, group in self._group_by_source(entries).items():
            local_root = source_root_from_entry(group[0])
            rel_paths = [e["rel_path"] for e in group]
            remote_pending = f"{self.config.remote.base_path}/pending/{source_name}"

            if dry_run:
                rc, out, err = self.transport.rsync_push(
                    local_root, remote_pending, rel_paths, dry_run=True,
                    extra_args=self.config.rsync_extra_args,
                )
                totals["planned"].append({
                    "source": source_name, "files": rel_paths,
                    "total_bytes": sum(e["size_bytes"] for e in group),
                    "rsync_preview": out or err,
                })
                self.db.log_event(batch_id, source_name, None, "dry_run_preview",
                                   (out or err)[:2000], _now())
                continue

            rc, out, err = self._rsync_with_retry(local_root, remote_pending, rel_paths,
                                                    source_name, batch_id)
            now = _now()
            if rc != 0:
                for e in group:
                    detail = f"rsync failed after retries: {err.strip()[:500]}"
                    self.db.mark_failed(source_name, e["rel_path"], detail, now, batch_id)
                    self.db.log_event(batch_id, source_name, e["rel_path"], "rsync_failed",
                                       detail, now)
                    totals["failures"].append({"source": source_name, "rel_path": e["rel_path"],
                                                "error": "rsync failed"})
                    totals["failed_count"] += 1
                self.db.commit()
                continue

            for e in group:
                self.db.mark_transferred(source_name, e["rel_path"], now, batch_id)
                self.db.log_event(batch_id, source_name, e["rel_path"], "transferred", None, now)
                totals["transferred_count"] += 1
            self._push_batch_manifest(group, source_name, batch_id, now)
            self.db.commit()  # durable checkpoint: files physically landed remotely

            v_count, f_count, v_failures = self._verify_and_move(group, source_name, batch_id)
            totals["verified_count"] += v_count
            totals["failed_count"] += f_count
            totals["failures"].extend(v_failures)
            self.db.commit()

        return totals

    def _push_batch_manifest(self, group, source_name, batch_id, now):
        payload = {
            "batch_id": batch_id, "source": source_name, "generated_at": now,
            "files": [{"rel_path": e["rel_path"], "sha256": e["sha256"],
                       "size_bytes": e["size_bytes"]} for e in group],
        }
        remote_path = f"{self.config.remote.base_path}/pending/_manifests/manifest-{batch_id}-{source_name}.json"
        self.transport.push_text_file(remote_path, json.dumps(payload, indent=2))

    def _rsync_with_retry(self, local_root, remote_dir, rel_paths, source_name, batch_id):
        attempts = 0
        rc, out, err = 1, "", ""
        while attempts < self.config.retry.max_attempts:
            attempts += 1
            rc, out, err = self.transport.rsync_push(
                local_root, remote_dir, rel_paths, dry_run=False,
                extra_args=self.config.rsync_extra_args,
            )
            self.db.log_event(batch_id, source_name, None, "rsync_attempt",
                               f"attempt={attempts} rc={rc}", _now())
            if rc == 0:
                return rc, out, err
            if attempts < self.config.retry.max_attempts:
                self._sleep(self.config.retry.backoff_seconds * attempts)
        return rc, out, err

    @staticmethod
    def _sleep(seconds):
        if seconds > 0:
            time.sleep(seconds)

    def _verify_and_move(self, group, source_name, batch_id):
        checksums_text = "\n".join(f"{e['sha256']}  {e['rel_path']}" for e in group)
        remote_pending = f"{self.config.remote.base_path}/pending/{source_name}"
        rc, out, err = self.transport.verify_checksums(remote_pending, checksums_text)
        results = parse_checksum_output(out)

        now = _now()
        base = self.config.remote.base_path
        move_lines = []
        verified_count = failed_count = 0
        failures = []

        for e in group:
            rel = e["rel_path"]
            ok = results.get(rel, False)
            if ok:
                self.db.mark_verified(source_name, rel, e["sha256"], now, batch_id)
                self.db.log_event(batch_id, source_name, rel, "verified", None, now)
                verified_count += 1
                dest = "received"
            else:
                reason = "checksum mismatch" if rel in results else "checksum verify missing/error"
                self.db.mark_failed(source_name, rel, reason, now, batch_id)
                self.db.log_event(batch_id, source_name, rel, "verify_failed", reason, now)
                failed_count += 1
                failures.append({"source": source_name, "rel_path": rel, "error": reason})
                dest = "failed"

            src_q = shlex.quote(f"{base}/pending/{source_name}/{rel}")
            dst_full = f"{base}/{dest}/{source_name}/{rel}"
            dst_dir_q = shlex.quote(str(Path(dst_full).parent))
            dst_q = shlex.quote(dst_full)
            move_lines.append(f"mkdir -p {dst_dir_q} && mv {src_q} {dst_q}")

        if move_lines:
            move_rc, move_out, move_err = self.transport.run_remote_script("\n".join(move_lines))
            self.db.log_event(batch_id, source_name, None,
                               "moved" if move_rc == 0 else "move_failed",
                               None if move_rc == 0 else move_err.strip()[:500], _now())

        return verified_count, failed_count, failures

    # -- public entry points -----------------------------------------------------------

    def run_transfer(self, manifest_path, dry_run=False) -> TransferSummary:
        entries = load_manifest(manifest_path)
        now = _now()
        batch_id = self.db.start_batch(manifest_path, dry_run, now, kind="transfer")

        to_transfer, excluded, skipped = self._select(entries, batch_id, dry_run)

        if not dry_run and to_transfer:
            self.transport.ensure_remote_dirs()

        result = (self._execute_batch(to_transfer, batch_id, dry_run) if to_transfer
                  else {"transferred_count": 0, "verified_count": 0, "failed_count": 0,
                        "failures": [], "planned": []})

        summary = TransferSummary(
            batch_id=batch_id, dry_run=dry_run,
            requested_count=len(entries), excluded_count=len(excluded), skipped_count=len(skipped),
            transferred_count=result["transferred_count"], verified_count=result["verified_count"],
            failed_count=result["failed_count"], failures=result["failures"], planned=result["planned"],
        )
        self.db.finish_batch(batch_id, _now(), requested_count=summary.requested_count,
                              excluded_count=summary.excluded_count, skipped_count=summary.skipped_count,
                              transferred_count=summary.transferred_count,
                              verified_count=summary.verified_count, failed_count=summary.failed_count)

        if dry_run:
            self.db.rollback()
        else:
            self.db.commit()
        return summary

    def retry_failed(self, max_attempts=None) -> TransferSummary:
        max_attempts = max_attempts or self.config.retry.max_attempts
        rows = self.db.failed_files(max_attempts)
        now = _now()
        batch_id = self.db.start_batch(None, dry_run=False, now=now, kind="retry")

        entries, excluded = [], []
        for row in rows:
            decision = self.matcher.match(row["rel_path"])
            if decision.ignored:
                excluded.append(row)
                self.db.mark_excluded(row["source_name"], row["rel_path"], now, batch_id)
                self.db.log_event(batch_id, row["source_name"], row["rel_path"],
                                   "excluded", decision.reason, now)
                continue
            entries.append({
                "source": row["source_name"], "rel_path": row["rel_path"],
                "abs_path": row["abs_path"], "sha256": row["expected_sha256"],
                "size_bytes": row["size_bytes"],
            })
            self.db.log_event(batch_id, row["source_name"], row["rel_path"], "retry_queued", None, now)
        self.db.commit()

        if entries:
            self.transport.ensure_remote_dirs()

        result = (self._execute_batch(entries, batch_id, dry_run=False) if entries
                  else {"transferred_count": 0, "verified_count": 0, "failed_count": 0, "failures": []})

        summary = TransferSummary(
            batch_id=batch_id, dry_run=False, requested_count=len(rows), excluded_count=len(excluded),
            transferred_count=result["transferred_count"], verified_count=result["verified_count"],
            failed_count=result["failed_count"], failures=result["failures"],
        )
        self.db.finish_batch(batch_id, _now(), requested_count=summary.requested_count,
                              excluded_count=summary.excluded_count,
                              transferred_count=summary.transferred_count,
                              verified_count=summary.verified_count, failed_count=summary.failed_count)
        self.db.commit()
        return summary

    def verify_transfer(self, status="transferred") -> TransferSummary:
        """Resume the checksum-verify + move step for files rsynced but not
        yet reconciled to received/ or failed/ (e.g. an interrupted run)."""
        rows = self.db.files_by_status(status)
        now = _now()
        batch_id = self.db.start_batch(None, dry_run=False, now=now, kind="verify")

        entries = [{
            "source": row["source_name"], "rel_path": row["rel_path"],
            "sha256": row["expected_sha256"], "size_bytes": row["size_bytes"],
        } for row in rows]

        verified_count = failed_count = 0
        failures = []
        for source_name, group in self._group_by_source(entries).items():
            v, f, fl = self._verify_and_move(group, source_name, batch_id)
            verified_count += v
            failed_count += f
            failures.extend(fl)
            self.db.commit()

        summary = TransferSummary(
            batch_id=batch_id, dry_run=False, requested_count=len(rows),
            verified_count=verified_count, failed_count=failed_count, failures=failures,
        )
        self.db.finish_batch(batch_id, _now(), requested_count=summary.requested_count,
                              verified_count=verified_count, failed_count=failed_count)
        self.db.commit()
        return summary
