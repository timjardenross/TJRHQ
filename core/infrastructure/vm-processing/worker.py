#!/usr/bin/env python3
"""VM Knowledge Processing Engine worker — USS-TJR-MSN-0205C.

One-shot script (systemd timer invoked, following the core/capture/
enrichment_worker.py template): scan the VM inbox's received/ tree for new
files, then drive each processing_documents row through the status state
machine — received -> extracted/ocr_required -> ocr_complete -> classified
-> summarised -> embedded -> awaiting_review, or -> failed with a captured
reason at any step. `awaiting_review` is the pipeline's terminal success
state for every document, sensitive or not — final memory ingestion is
MSN-0205D's Captain-approval queue, explicitly out of scope here.

Two additional eligibility checkpoints (USS-TJR-MSN-0206B) can short-circuit
a document straight to the `excluded` terminal state: a filename check
before extraction (EPUB/MOBI/temp files), and a content check before
classification (ISBN/ebook-producer/book-structure signals) — see
eligibility.py. Excluded documents never reach OCR/classify/summarise/embed.

Bounded manual retry (USS-TJR-MSN-0206J-4): `worker.py retry --id ID` moves
a `failed` document to `retry_pending` (picked up by process_batch() like
any other non-terminal status) as long as `retry_count < max_retries`;
beyond the cap it moves to the `permanently_failed` terminal state instead.
`retry_pending` -> `retrying` clears stale artifacts from the previous
attempt (extracted text, classification, summary, chunks) before falling
through to re-extraction. A retry that fails again returns to plain
`failed`, retriable again if still under cap.

Bounded automatic retry sweep (USS-TJR-MSN-0207A): `worker.py retry-all`
calls the existing `retry()` for every currently-`failed` document, letting
its existing cap logic do exactly what it already does per-document — some
requeue to `retry_pending`, some already at cap correctly become
`permanently_failed`. This automates the *act of calling* `retry()` on a
schedule (see systemd/vm-processing-retry.timer); it does not change the
bounding logic itself, and there is still no auto-retry-on-failure at the
point of failure — a document only gets retried when scan/process/run or
the retry-sweep timer next runs.

Usage:
    worker.py scan       [--config config.yaml]
    worker.py process    [--config config.yaml] [--limit N]
    worker.py run        [--config config.yaml] [--limit N]   # scan + process
    worker.py status     [--config config.yaml]
    worker.py excluded   [--config config.yaml]
    worker.py list-failed [--config config.yaml]
    worker.py override --id ID [--config config.yaml]
    worker.py retry     --id ID [--config config.yaml]
    worker.py retry-all  [--config config.yaml]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from config import load_config  # noqa: E402
from supabase_client import SupabaseClient  # noqa: E402
from model_router_client import ModelRouterClient  # noqa: E402
from chunking import chunk_text  # noqa: E402
import parsers  # noqa: E402
from ocr import orchestrator as ocr_orchestrator  # noqa: E402
import eligibility  # noqa: E402

DEFAULT_CONFIG = _HERE / "config.yaml"

NON_TERMINAL_STATUSES = (
    "received", "extracted", "ocr_required", "ocr_complete",
    "classified", "summarised", "embedded",
    "retry_pending", "retrying",
)
TERMINAL_STATUSES = ("failed", "awaiting_review", "excluded", "permanently_failed")

# SUOC Wave 3 / MSN-0210K: additive Task Engine dual-write. processing_documents
# remains the sole source of truth for this worker's own behaviour — these
# calls only mirror status into the shared Task Engine (tasks/task_events) so
# it's visible cross-platform. Every call is best-effort and non-blocking; a
# Task Engine failure must never affect document processing.
_TASK_ENGINE_STATUS_MAP = {
    "received": "in_progress", "extracted": "in_progress", "ocr_required": "in_progress",
    "ocr_complete": "in_progress", "classified": "in_progress", "summarised": "in_progress",
    "embedded": "in_progress", "retry_pending": "in_progress", "retrying": "in_progress",
    "awaiting_review": "completed", "failed": "failed", "permanently_failed": "failed",
    "excluded": "cancelled",
}


_REPO_ROOT = _HERE.parents[2]  # .../vm-processing -> infrastructure -> core -> repo root


def _task_engine_create(source_path: str, source_name: str, filename: str) -> None:
    """Best-effort, non-blocking: mirror a newly-scanned document into the
    shared Task Engine. Never raises — a Task Engine outage must never stop
    scan() from tracking the document in processing_documents."""
    try:
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        from core.platform.task_engine import create_task
        create_task(
            "engineering", domain="vm-processing", owner="vm-processing-worker",
            idempotency_key=source_path,
            metadata={"source_name": source_name, "filename": filename},
        )
    except Exception:
        pass


def _task_engine_transition(source_path: str | None, status: str, failure_reason: str | None) -> None:
    """Best-effort, non-blocking: mirror a status change onto the matching
    Task Engine task (correlated by idempotency_key=source_path). Never
    raises — see _task_engine_create."""
    if not source_path:
        return
    try:
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        from core.platform.task_engine import get_task_by_idempotency_key, transition_task
        new_status = _TASK_ENGINE_STATUS_MAP.get(status)
        if new_status is None:
            return
        task = get_task_by_idempotency_key(source_path)
        if task is None:
            return
        transition_task(task["task_id"], new_status, error=failure_reason)
    except Exception:
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


class ProcessingWorker:
    def __init__(self, config, db, model_router,
                 extract_fn=parsers.extract, run_ocr_fn=ocr_orchestrator.run_ocr,
                 chunk_fn=chunk_text, sleep_fn=time.sleep,
                 check_filename_fn=eligibility.check_filename,
                 check_content_fn=eligibility.check_content):
        self.config = config
        self.db = db
        self.model_router = model_router
        self.extract_fn = extract_fn
        self.run_ocr_fn = run_ocr_fn
        self.chunk_fn = chunk_fn
        self.sleep_fn = sleep_fn
        self.check_filename_fn = check_filename_fn
        self.check_content_fn = check_content_fn

    # -- scan -----------------------------------------------------------

    def scan(self) -> dict:
        """Walk <inbox_base>/received/<source>/** for files not yet tracked."""
        received_root = self.config.inbox_base_path / "received"
        if not received_root.exists():
            return {"new": 0, "skipped": 0, "root_missing": True}

        new_count = skipped_count = 0
        for path in sorted(received_root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(received_root)
            source_name = rel.parts[0] if len(rel.parts) > 1 else "unknown"
            # Resolve symlinks so source_path records the file's real
            # canonical location, not a staging symlink's own path.
            source_path = str(path.resolve())

            existing = self.db.get_one(
                f"processing_documents?source_path=eq.{_quote(source_path)}&select=id"
            )
            if existing:
                skipped_count += 1
                continue

            self.db.insert("processing_documents", {
                "source_name": source_name,
                "source_path": source_path,
                "filename": path.name,
                "file_type": path.suffix.lower().lstrip("."),
                "size_bytes": path.stat().st_size,
                "status": "received",
            })
            _task_engine_create(source_path, source_name, path.name)
            new_count += 1
        return {"new": new_count, "skipped": skipped_count, "root_missing": False}

    # -- batch processing -----------------------------------------------------------

    def process_batch(self, limit: int = 20) -> dict:
        status_filter = ",".join(NON_TERMINAL_STATUSES)
        rows = self.db.get(
            f"processing_documents?status=in.({status_filter})&order=created_at.asc&limit={limit}"
        )
        by_id = {row["id"]: dict(row) for row in rows}
        counts = {"documents": len(by_id), "awaiting_review": 0, "failed": 0, "excluded": 0}

        # Advance every document by one stage per pass instead of driving
        # each one fully through the pipeline before starting the next.
        # Documents scanned/retried together mostly start in the same
        # status, so this naturally groups all classify calls together,
        # then all summarise calls, then all embeds — the model router's
        # Ollama model (gemma3:4b, then nomic-embed-text) stays resident for
        # a whole pass instead of reloading on every single document.
        pending_ids = list(by_id.keys())
        max_passes = len(NON_TERMINAL_STATUSES) + 2  # generous bound on the longest status chain
        for _ in range(max_passes):
            if not pending_ids:
                break
            still_pending = []
            for doc_id in pending_ids:
                current = by_id[doc_id]
                try:
                    current = self._advance(current)
                except Exception as exc:  # noqa: BLE001 — any step failure is captured, not fatal to the batch
                    current = self._mark_failed(current, f"{type(exc).__name__}: {exc}")
                by_id[doc_id] = current
                if current["status"] in NON_TERMINAL_STATUSES:
                    still_pending.append(doc_id)
                self.sleep_fn(0.2)  # be gentle with the local model router between calls
            pending_ids = still_pending

        for current in by_id.values():
            if current["status"] == "failed":
                counts["failed"] += 1
            elif current["status"] == "awaiting_review":
                counts["awaiting_review"] += 1
            elif current["status"] == "excluded":
                counts["excluded"] += 1
        return counts

    def _advance(self, current: dict) -> dict:
        status = current["status"]
        if status == "retry_pending":
            return self._do_retry_reset(current)
        if status == "retrying":
            return self._do_extract(current)
        if status == "received":
            return self._do_extract(current)
        if status == "ocr_required":
            return self._do_ocr(current)
        if status in ("extracted", "ocr_complete"):
            return self._do_classify(current)
        if status == "classified":
            return self._do_summarise(current)
        if status == "summarised":
            return self._do_embed(current)
        if status == "embedded":
            return self._do_finalize(current)
        raise RuntimeError(f"unexpected status for advance: {status}")

    # -- state transitions -----------------------------------------------------------

    def _do_extract(self, current: dict) -> dict:
        # MSN-0206B: cheap filename/extension check before any parsing —
        # catches EPUB/MOBI and temp/placeholder files at zero parsing cost.
        filename_check = self.check_filename_fn(current["filename"])
        if not filename_check.eligible:
            return self._mark_excluded(current, filename_check)

        result = self.extract_fn(current["source_path"], self.config.processing.low_text_chars_per_page)
        next_status = "ocr_required" if result.needs_ocr else "extracted"
        update = {
            "status": next_status,
            "extracted_text": result.text,
            "metadata": {**(current.get("metadata") or {}),
                         "extraction": {**result.metadata, "page_count": result.page_count}},
            "processing_log": self._log_event(current, next_status,
                                               "low-text PDF, routed to OCR" if result.needs_ocr else None),
        }
        return self._patch_and_return(current, update)

    def _do_ocr(self, current: dict) -> dict:
        ocr_result = self.run_ocr_fn(
            current["source_path"], self.config.ocr_workdir, self.config.processing.low_text_chars_per_page,
            language=self.config.ocr_language,
        )
        if not ocr_result.success:
            raise RuntimeError(f"OCR failed: {ocr_result.error}")
        update = {
            "status": "ocr_complete",
            "extracted_text": ocr_result.text,
            "ocr_used": True,
            "ocr_engine": ocr_result.engine,
            # ocr_used/ocr_engine are dedicated columns (MSN-0205C); language
            # is finer-grained provenance folded into metadata (MSN-0206A) —
            # not worth a schema change for one field (ADR-0020: reuse
            # before create).
            "metadata": {**(current.get("metadata") or {}),
                         "ocr": {"engine": ocr_result.engine, "language": ocr_result.language}},
            "processing_log": self._log_event(
                current, "ocr_complete", f"engine={ocr_result.engine} language={ocr_result.language}"
            ),
        }
        return self._patch_and_return(current, update)

    def _do_classify(self, current: dict) -> dict:
        text = (current.get("extracted_text") or "").strip()
        if not text:
            raise RuntimeError("no extracted text available to classify")

        # MSN-0206B: content-based eligibility check, now that extracted/OCR'd
        # text and (for PDFs) page count + Info-dict metadata are available.
        extraction_meta = (current.get("metadata") or {}).get("extraction") or {}
        content_check = self.check_content_fn(
            current["filename"], text,
            page_count=extraction_meta.get("page_count"),
            pdf_metadata=extraction_meta.get("pdf_info") or {},
        )
        if not content_check.eligible:
            return self._mark_excluded(current, content_check)

        classification = self.model_router.classify_document(text)
        update = {
            "status": "classified",
            "category": classification["category"],
            "tags": classification["tags"],
            "sensitivity": classification["sensitivity"],
            "memory_recommendation": classification["memory_recommendation"],
            "metadata": {**(current.get("metadata") or {}),
                         "classification_confidence": classification["confidence"]},
            "processing_log": self._log_event(current, "classified", classification["category"]),
        }
        return self._patch_and_return(current, update)

    def _do_summarise(self, current: dict) -> dict:
        text = (current.get("extracted_text") or "").strip()
        if not text:
            raise RuntimeError("no extracted text available to summarise")
        summary = self.model_router.summarise_document(text)
        update = {
            "status": "summarised",
            "summary": summary,
            "processing_log": self._log_event(current, "summarised", None),
        }
        return self._patch_and_return(current, update)

    def _do_embed(self, current: dict) -> dict:
        text = (current.get("extracted_text") or "").strip()
        chunks = self.chunk_fn(text, self.config.processing.chunk_chars, self.config.processing.chunk_overlap_chars)
        if not chunks:
            raise RuntimeError("no chunks produced from extracted text")
        for idx, chunk in enumerate(chunks):
            embedding = self.model_router.embed(chunk)
            self.db.insert("processing_chunks", {
                "document_id": current["id"],
                "chunk_index": idx,
                "chunk_text": chunk,
                "embedding": embedding,
                "embedding_model": "nomic-embed-text",
                "embedded_at": _now(),
            })
            self.sleep_fn(0.1)
        update = {
            "status": "embedded",
            "chunk_count": len(chunks),
            "processing_log": self._log_event(current, "embedded", f"{len(chunks)} chunks"),
        }
        return self._patch_and_return(current, update)

    def _do_finalize(self, current: dict) -> dict:
        update = {
            "status": "awaiting_review",
            "processing_log": self._log_event(current, "awaiting_review",
                                               "processing complete, pending Captain approval"),
        }
        return self._patch_and_return(current, update)

    def _do_retry_reset(self, current: dict) -> dict:
        """USS-TJR-MSN-0206J-4: `retry_pending` -> `retrying` — clear every
        artifact a previous failed attempt may have left behind before
        falling through to re-extraction on the next _advance() call. A
        partial _do_embed may have inserted some processing_chunks rows
        before a later step failed; those must be deleted here or re-embed
        would collide on the (document_id, chunk_index) unique constraint."""
        self.db.delete("processing_chunks", {"document_id": current["id"]})
        update = {
            "status": "retrying",
            "extracted_text": None,
            "ocr_used": False,
            "ocr_engine": None,
            "category": None,
            "tags": [],
            "summary": None,
            "memory_recommendation": None,
            "chunk_count": 0,
            "processing_log": self._log_event(current, "retrying",
                                               "cleared prior attempt's artifacts, re-processing from extraction"),
        }
        return self._patch_and_return(current, update)

    # -- helpers -----------------------------------------------------------

    def _log_event(self, current: dict, event: str, detail: str = None) -> list:
        log = list(current.get("processing_log") or [])
        log.append({"event": event, "detail": detail, "at": _now()})
        return log

    def _mark_failed(self, current: dict, reason: str) -> dict:
        update = {
            "status": "failed",
            "failure_reason": reason[:2000],
            "processing_log": self._log_event(current, "failed", reason[:500]),
        }
        return self._patch_and_return(current, update)

    def _mark_excluded(self, current: dict, result) -> dict:
        """MSN-0206B: short-circuit to the `excluded` terminal state — no
        further OCR/classify/summarise/embed happens for this document."""
        update = {
            "status": "excluded",
            "exclusion_reason": result.reason,
            "metadata": {**(current.get("metadata") or {}), "eligibility": result.evidence},
            "processing_log": self._log_event(current, "excluded", f"{result.reason}: {result.detail}"),
        }
        return self._patch_and_return(current, update)

    # -- manual override (MSN-0206B) -----------------------------------------------------------

    def override(self, document_id: str) -> dict:
        """Force a document back into the pipeline regardless of its current
        status (excluded or failed) — the eligibility engine is a heuristic,
        not a Captain's judgement; a false-positive exclusion must be
        recoverable without a raw SQL write."""
        current = self.db.get_one(f"processing_documents?id=eq.{_quote(document_id)}&select=*")
        if current is None:
            raise ValueError(f"no processing_documents row with id={document_id}")
        update = {
            "status": "received",
            "exclusion_reason": None,
            "failure_reason": None,
            "processing_log": self._log_event(current, "override_reprocess",
                                               f"manually reset from '{current['status']}' for reprocessing"),
        }
        return self._patch_and_return(current, update)

    # -- bounded manual retry (MSN-0206J-4) -----------------------------------------------------------

    def retry(self, document_id: str) -> dict:
        """Request a retry of a `failed` document. Bounded by
        `config.processing.max_retries`, enforced at the moment of request
        (not silently during processing): under the cap, the document goes
        to `retry_pending` for process_batch() to pick up; at/over the cap
        it goes to `permanently_failed` instead and a ValueError is raised
        so the CLI can tell the Captain that `override` is needed to force
        another attempt anyway."""
        current = self.db.get_one(f"processing_documents?id=eq.{_quote(document_id)}&select=*")
        if current is None:
            raise ValueError(f"no processing_documents row with id={document_id}")
        if current["status"] != "failed":
            raise ValueError(
                f"document {document_id} is not in status 'failed' (currently '{current['status']}') — "
                "retry only operates on failed documents"
            )

        retry_count = current.get("retry_count") or 0
        if retry_count >= self.config.processing.max_retries:
            update = {
                "status": "permanently_failed",
                "processing_log": self._log_event(
                    current, "retry_cap_exceeded",
                    f"retry_count={retry_count} >= max_retries={self.config.processing.max_retries}",
                ),
            }
            self._patch_and_return(current, update)
            raise ValueError(
                f"document {document_id} has reached max_retries={self.config.processing.max_retries} "
                "and has been marked permanently_failed — use `worker.py override --id "
                f"{document_id}` to force it back to 'received' if another attempt is wanted anyway"
            )

        update = {
            "status": "retry_pending",
            "retry_count": retry_count + 1,
            "last_retry_at": _now(),
            "failure_reason": None,
            "processing_log": self._log_event(
                current, "retry_requested", f"retry {retry_count + 1}/{self.config.processing.max_retries}"
            ),
        }
        return self._patch_and_return(current, update)

    def retry_all(self) -> dict:
        """USS-TJR-MSN-0207A: bounded automatic retry sweep. Calls the
        existing `retry()` for every currently-`failed` document — this
        does not change the cap logic in `retry()` at all, it just
        automates the act of invoking it on a schedule instead of one
        Captain `worker.py retry --id ID` call at a time. `permanently_failed`
        documents are excluded from the query up front (they're already
        exhausted; calling retry() on them would just raise). A single
        document landing at/over the cap during this sweep is an expected
        outcome, not an exceptional one — its ValueError is caught and
        logged so the rest of the batch still gets attempted."""
        rows = self.db.get("processing_documents?status=eq.failed&select=id,filename")
        summary = {"attempted": 0, "requeued": 0, "permanently_failed": 0}
        for row in rows:
            summary["attempted"] += 1
            try:
                self.retry(row["id"])
                summary["requeued"] += 1
            except ValueError:
                # Expected for a document already at/over max_retries —
                # retry() has already moved it to permanently_failed.
                summary["permanently_failed"] += 1
        return summary

    def _patch_and_return(self, current: dict, update: dict) -> dict:
        self.db.patch("processing_documents", {"id": current["id"]}, update)
        merged = {**current, **update}
        if "status" in update:
            _task_engine_transition(merged.get("source_path"), update["status"], update.get("failure_reason"))
        return merged

    # -- status -----------------------------------------------------------

    def status_summary(self) -> dict:
        rows = self.db.get("processing_documents?select=status")
        counts = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return counts

    def list_excluded(self) -> list:
        """MSN-0206B: report on excluded documents — filename, reason, and
        the scoring evidence that triggered the exclusion."""
        rows = self.db.get(
            "processing_documents?status=eq.excluded"
            "&select=id,filename,source_name,exclusion_reason,metadata&order=filename.asc"
        )
        return [
            {
                "id": row["id"],
                "filename": row["filename"],
                "source_name": row["source_name"],
                "exclusion_reason": row["exclusion_reason"],
                "evidence": (row.get("metadata") or {}).get("eligibility", {}),
            }
            for row in rows
        ]

    def list_failed(self) -> list:
        """USS-TJR-MSN-0206J-4: report on `failed` and `permanently_failed`
        documents together — filename, retry state, and the failure reason
        — so the Captain can see what's still retriable vs. exhausted."""
        rows = self.db.get(
            "processing_documents?status=in.(failed,permanently_failed)"
            "&select=id,filename,status,retry_count,failure_reason,last_retry_at&order=filename.asc"
        )
        return [
            {
                "id": row["id"],
                "filename": row["filename"],
                "status": row["status"],
                "retry_count": row.get("retry_count") or 0,
                "failure_reason": row.get("failure_reason"),
                "last_retry_at": row.get("last_retry_at"),
            }
            for row in rows
        ]


def _build_worker(config_path) -> tuple:
    config = load_config(config_path)
    db = SupabaseClient(config.supabase.url, config.supabase.service_role_key)
    model_router = ModelRouterClient(config.model_router.url, config.model_router.timeout_seconds)
    return config, ProcessingWorker(config, db, model_router)


def cmd_scan(args) -> int:
    _, worker = _build_worker(args.config)
    result = worker.scan()
    print(json.dumps(result, indent=2))
    return 0


def cmd_process(args) -> int:
    _, worker = _build_worker(args.config)
    result = worker.process_batch(limit=args.limit)
    print(json.dumps(result, indent=2))
    return 1 if result["failed"] else 0


def cmd_run(args) -> int:
    _, worker = _build_worker(args.config)
    scan_result = worker.scan()
    process_result = worker.process_batch(limit=args.limit)
    print(json.dumps({"scan": scan_result, "process": process_result}, indent=2))
    return 1 if process_result["failed"] else 0


def cmd_status(args) -> int:
    _, worker = _build_worker(args.config)
    print(json.dumps(worker.status_summary(), indent=2))
    return 0


def cmd_excluded(args) -> int:
    _, worker = _build_worker(args.config)
    print(json.dumps(worker.list_excluded(), indent=2))
    return 0


def cmd_override(args) -> int:
    _, worker = _build_worker(args.config)
    row = worker.override(args.id)
    print(json.dumps({"id": row["id"], "filename": row["filename"], "status": row["status"]}, indent=2))
    return 0


def cmd_list_failed(args) -> int:
    _, worker = _build_worker(args.config)
    print(json.dumps(worker.list_failed(), indent=2))
    return 0


def cmd_retry(args) -> int:
    _, worker = _build_worker(args.config)
    try:
        row = worker.retry(args.id)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({
        "id": row["id"], "filename": row["filename"], "status": row["status"],
        "retry_count": row["retry_count"],
    }, indent=2))
    return 0


def cmd_retry_all(args) -> int:
    _, worker = _build_worker(args.config)
    print(json.dumps(worker.retry_all(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="USS-TJR-MSN-0205C VM Knowledge Processing Engine")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Discover new received/ files")
    p_scan.set_defaults(func=cmd_scan)

    p_process = sub.add_parser("process", help="Advance pending documents through the pipeline")
    p_process.add_argument("--limit", type=int, default=20)
    p_process.set_defaults(func=cmd_process)

    p_run = sub.add_parser("run", help="scan + process in one invocation")
    p_run.add_argument("--limit", type=int, default=20)
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="Summary counts by status")
    p_status.set_defaults(func=cmd_status)

    p_excluded = sub.add_parser("excluded", help="List documents excluded by the Content Eligibility Engine")
    p_excluded.set_defaults(func=cmd_excluded)

    p_override = sub.add_parser("override", help="Force an excluded/failed document back into the pipeline")
    p_override.add_argument("--id", required=True, help="processing_documents.id to reprocess")
    p_override.set_defaults(func=cmd_override)

    p_list_failed = sub.add_parser("list-failed", help="List failed and permanently_failed documents")
    p_list_failed.set_defaults(func=cmd_list_failed)

    p_retry = sub.add_parser("retry", help="Request a bounded retry of a failed document")
    p_retry.add_argument("--id", required=True, help="processing_documents.id to retry")
    p_retry.set_defaults(func=cmd_retry)

    p_retry_all = sub.add_parser("retry-all", help="Bounded automatic retry sweep over every failed document")
    p_retry_all.set_defaults(func=cmd_retry_all)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
