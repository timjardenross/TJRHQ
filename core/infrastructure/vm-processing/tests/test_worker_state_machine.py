import textwrap
from pathlib import Path

import eligibility
from config import load_config
from healthcheck import HealthThresholds, compute_health, run_healthcheck
from ocr.base import OCRResult
from parsers.base import ExtractionResult
from worker import ProcessingWorker

from fakes import FakeSupabase, FakeModelRouter


def _write_config(tmp_path: Path, inbox_base: Path, max_retries: int = 3) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(textwrap.dedent(f"""
        inbox:
          base_path: "{inbox_base}"
        model_router:
          url: "http://127.0.0.1:8891"
        processing:
          batch_limit: 20
          chunk_chars: 50
          chunk_overlap_chars: 10
          low_text_chars_per_page: 50
          max_retries: {max_retries}
        ocr:
          workdir: "{tmp_path / 'ocr-work'}"
    """))
    return config_path


def _make_worker(tmp_path, monkeypatch, extract_fn=None, run_ocr_fn=None,
                  classify_result=None, summary="A short summary.", fail_on=None,
                  check_filename_fn=None, check_content_fn=None, max_retries=3):
    inbox_base = tmp_path / "inbox"
    (inbox_base / "received").mkdir(parents=True)
    monkeypatch.setenv("SUPABASE_URL", "http://fake-supabase.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-key")
    config = load_config(str(_write_config(tmp_path, inbox_base, max_retries=max_retries)))
    db = FakeSupabase()
    model_router = FakeModelRouter(classify_result=classify_result, summary=summary, fail_on=fail_on)
    worker = ProcessingWorker(
        config, db, model_router,
        extract_fn=extract_fn or (lambda path, threshold: ExtractionResult(
            text="Plenty of extractable text here. " * 5, needs_ocr=False, page_count=1)),
        run_ocr_fn=run_ocr_fn or (lambda *a, **k: OCRResult(text="", engine=None, success=False)),
        sleep_fn=lambda seconds: None,
        check_filename_fn=check_filename_fn or eligibility.check_filename,
        check_content_fn=check_content_fn or eligibility.check_content,
    )
    return inbox_base, db, model_router, worker


# -- scan ---------------------------------------------------------------

def test_scan_creates_received_rows_and_is_idempotent(tmp_path, monkeypatch):
    inbox_base, db, _, worker = _make_worker(tmp_path, monkeypatch)
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    (inbox_base / "received" / "onedrive" / "report.txt").write_text("hello")

    result = worker.scan()
    assert result == {"new": 1, "skipped": 0, "root_missing": False}
    rows = db.get("processing_documents?select=id,status,source_name,filename")
    assert len(rows) == 1
    assert rows[0]["status"] == "received"
    assert rows[0]["source_name"] == "onedrive"
    assert rows[0]["filename"] == "report.txt"

    result2 = worker.scan()
    assert result2 == {"new": 0, "skipped": 1, "root_missing": False}
    assert len(db.get("processing_documents?select=id")) == 1


def test_scan_handles_missing_received_dir(tmp_path, monkeypatch):
    inbox_base, db, _, worker = _make_worker(tmp_path, monkeypatch)
    import shutil
    shutil.rmtree(inbox_base / "received")
    result = worker.scan()
    assert result["root_missing"] is True
    assert result["new"] == 0


def test_scan_records_canonical_path_for_symlinked_source(tmp_path, monkeypatch):
    """MSN-0205E: staging a source tree of symlinks (so scan() only walks a
    curated subset of a larger real folder, e.g. skipping cloud-only
    OneDrive files) must record each file's real target path, not the
    symlink's own location in the scratch staging tree — otherwise
    citations in Command Memory would point at a throwaway path instead
    of where the Captain's file actually lives."""
    inbox_base, db, _, worker = _make_worker(tmp_path, monkeypatch)

    real_dir = tmp_path / "real-onedrive-location" / "A_Cleanup"
    real_dir.mkdir(parents=True)
    real_file = real_dir / "Change of Member Details.pdf"
    real_file.write_text("real content living outside the staging tree")

    staged_dir = inbox_base / "received" / "onedrive-starship-intake" / "A_Cleanup"
    staged_dir.mkdir(parents=True)
    staged_symlink = staged_dir / "Change of Member Details.pdf"
    staged_symlink.symlink_to(real_file)

    result = worker.scan()
    assert result == {"new": 1, "skipped": 0, "root_missing": False}

    row = db.get_one("processing_documents?select=source_path,source_name,filename")
    assert row["source_path"] == str(real_file)
    assert row["source_path"] != str(staged_symlink)
    assert row["source_name"] == "onedrive-starship-intake"
    assert row["filename"] == "Change of Member Details.pdf"


# -- full pipeline ---------------------------------------------------------------

def test_full_pipeline_text_file_reaches_awaiting_review(tmp_path, monkeypatch):
    inbox_base, db, model_router, worker = _make_worker(tmp_path, monkeypatch)
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    (inbox_base / "received" / "onedrive" / "report.txt").write_text("hello")
    worker.scan()

    result = worker.process_batch(limit=10)
    assert result == {"documents": 1, "awaiting_review": 1, "failed": 0, "excluded": 0}

    row = db.get_one("processing_documents?select=*")
    assert row["status"] == "awaiting_review"
    assert row["category"] == "Reference"
    assert row["sensitivity"] == "standard"
    assert row["memory_recommendation"] == "recommend_full"
    assert row["summary"] == "A short summary."
    assert row["chunk_count"] > 0
    assert row["failure_reason"] is None
    assert [e["event"] for e in row["processing_log"]] == [
        "extracted", "classified", "summarised", "embedded", "awaiting_review",
    ]

    chunks = db.get(f"processing_chunks?document_id=eq.{row['id']}")
    assert len(chunks) == row["chunk_count"]
    assert all(c["embedding_model"] == "nomic-embed-text" for c in chunks)
    assert all(isinstance(c["embedding"], list) and c["embedding"] for c in chunks)


def test_pipeline_routes_low_text_pdf_through_ocr(tmp_path, monkeypatch):
    def fake_extract(path, threshold):
        return ExtractionResult(text="", needs_ocr=True, page_count=1,
                                 metadata={"avg_chars_per_page": 0})

    def fake_ocr(path, workdir, threshold, language=None):
        assert language == "eng"  # MSN-0206A: worker must pass config.ocr_language through
        return OCRResult(text="OCR recovered this text about a scanned form.",
                          engine="ocrmypdf", success=True, language=language)

    inbox_base, db, _, worker = _make_worker(
        tmp_path, monkeypatch, extract_fn=fake_extract, run_ocr_fn=fake_ocr,
    )
    (inbox_base / "received" / "icloud").mkdir(parents=True)
    (inbox_base / "received" / "icloud" / "scan.pdf").write_bytes(b"%PDF-fake")
    worker.scan()

    result = worker.process_batch(limit=10)
    assert result == {"documents": 1, "awaiting_review": 1, "failed": 0, "excluded": 0}

    row = db.get_one("processing_documents?select=*")
    assert row["status"] == "awaiting_review"
    assert row["ocr_used"] is True
    assert row["ocr_engine"] == "ocrmypdf"
    assert row["extracted_text"] == "OCR recovered this text about a scanned form."
    assert [e["event"] for e in row["processing_log"]][:2] == ["ocr_required", "ocr_complete"]
    # MSN-0206A: language provenance recorded in metadata alongside the
    # dedicated ocr_used/ocr_engine columns.
    assert row["metadata"]["ocr"] == {"engine": "ocrmypdf", "language": "eng"}


# -- failure capture ---------------------------------------------------------------

def test_ocr_failure_marks_document_failed_with_reason(tmp_path, monkeypatch):
    def fake_extract(path, threshold):
        return ExtractionResult(text="", needs_ocr=True, page_count=1)

    def fake_ocr(path, workdir, threshold, language=None):
        return OCRResult(text="", engine=None, success=False, error="ocrmypdf: not available; tesseract: not available")

    inbox_base, db, _, worker = _make_worker(
        tmp_path, monkeypatch, extract_fn=fake_extract, run_ocr_fn=fake_ocr,
    )
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    (inbox_base / "received" / "onedrive" / "scan.pdf").write_bytes(b"%PDF-fake")
    worker.scan()

    result = worker.process_batch(limit=10)
    assert result == {"documents": 1, "awaiting_review": 0, "failed": 1, "excluded": 0}

    row = db.get_one("processing_documents?select=*")
    assert row["status"] == "failed"
    assert "OCR failed" in row["failure_reason"]
    assert row["processing_log"][-1]["event"] == "failed"


def test_classify_failure_marks_failed_and_is_not_auto_retried(tmp_path, monkeypatch):
    inbox_base, db, model_router, worker = _make_worker(
        tmp_path, monkeypatch, fail_on={"classify"},
    )
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    (inbox_base / "received" / "onedrive" / "report.txt").write_text("hello")
    worker.scan()

    result = worker.process_batch(limit=10)
    assert result == {"documents": 1, "awaiting_review": 0, "failed": 1, "excluded": 0}
    row = db.get_one("processing_documents?select=*")
    assert row["status"] == "failed"
    assert "classify-document unreachable" in row["failure_reason"]

    # A second process_batch call must not pick up 'failed' rows again —
    # MSN-0205C has no auto-retry; that's deliberately out of this mission's scope.
    result2 = worker.process_batch(limit=10)
    assert result2 == {"documents": 0, "awaiting_review": 0, "failed": 0, "excluded": 0}


def test_missing_extracted_text_fails_before_calling_model_router(tmp_path, monkeypatch):
    def fake_extract(path, threshold):
        return ExtractionResult(text="   ", needs_ocr=False, page_count=1)

    inbox_base, db, model_router, worker = _make_worker(
        tmp_path, monkeypatch, extract_fn=fake_extract,
    )
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    (inbox_base / "received" / "onedrive" / "empty.txt").write_text(" ")
    worker.scan()

    worker.process_batch(limit=10)
    row = db.get_one("processing_documents?select=*")
    assert row["status"] == "failed"
    assert "no extracted text" in row["failure_reason"]
    assert model_router.calls == []


# -- status ---------------------------------------------------------------

def test_status_summary_counts_by_status(tmp_path, monkeypatch):
    inbox_base, db, _, worker = _make_worker(tmp_path, monkeypatch)
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    (inbox_base / "received" / "onedrive" / "a.txt").write_text("a")
    (inbox_base / "received" / "onedrive" / "b.txt").write_text("b")
    worker.scan()
    worker.process_batch(limit=1)  # only advance one document fully

    summary = worker.status_summary()
    assert summary.get("awaiting_review") == 1
    assert summary.get("received") == 1


# -- content eligibility engine (USS-TJR-MSN-0206B) ---------------------------------------------------------------

def test_epub_filename_is_excluded_before_extraction(tmp_path, monkeypatch):
    """A hard-blocked extension must never reach extract_fn — no parsing
    cost spent on a format this pipeline can't read anyway."""
    calls = []

    def tracking_extract(path, threshold):
        calls.append(path)
        return ExtractionResult(text="should never run", needs_ocr=False, page_count=1)

    inbox_base, db, model_router, worker = _make_worker(tmp_path, monkeypatch, extract_fn=tracking_extract)
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    (inbox_base / "received" / "onedrive" / "Some_Novel_-_Jane_Doe.epub").write_bytes(b"fake epub bytes")
    worker.scan()

    result = worker.process_batch(limit=10)
    assert result == {"documents": 1, "awaiting_review": 0, "failed": 0, "excluded": 1}

    row = db.get_one("processing_documents?select=*")
    assert row["status"] == "excluded"
    assert row["exclusion_reason"] == "unsupported_media"
    assert calls == []  # extraction never attempted
    assert model_router.calls == []  # classify/summarise/embed never attempted
    assert row["processing_log"][-1]["event"] == "excluded"


def test_recreational_content_is_excluded_before_classify(tmp_path, monkeypatch):
    """A calibre-produced ebook (real signature from the MSN-0205E intake
    set) must be excluded after extraction, before the model router is ever
    called for classification."""
    def fake_extract(path, threshold):
        return ExtractionResult(
            text="Some recovered book text.", needs_ocr=False, page_count=464,
            metadata={"pdf_info": {"creator": "calibre 7.4.0", "producer": "calibre 7.4.0"}},
        )

    inbox_base, db, model_router, worker = _make_worker(tmp_path, monkeypatch, extract_fn=fake_extract)
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    (inbox_base / "received" / "onedrive" / "Physicians_Directory_Of_Trusted_Remedies_-_Mark_E_Johnson.pdf").write_bytes(b"%PDF-fake")
    worker.scan()

    result = worker.process_batch(limit=10)
    assert result == {"documents": 1, "awaiting_review": 0, "failed": 0, "excluded": 1}

    row = db.get_one("processing_documents?select=*")
    assert row["status"] == "excluded"
    assert row["exclusion_reason"] == "recreational_content"
    assert row["metadata"]["eligibility"]["ebook_producer_tool"] == "calibre"
    assert model_router.calls == []  # never reached classify/summarise/embed


def test_excluded_document_is_terminal_and_not_reprocessed(tmp_path, monkeypatch):
    inbox_base, db, _, worker = _make_worker(tmp_path, monkeypatch)
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    (inbox_base / "received" / "onedrive" / "book.mobi").write_bytes(b"fake")
    worker.scan()

    worker.process_batch(limit=10)
    result2 = worker.process_batch(limit=10)
    assert result2 == {"documents": 0, "awaiting_review": 0, "failed": 0, "excluded": 0}


def test_override_forces_excluded_document_back_into_pipeline(tmp_path, monkeypatch):
    """Manual override (USS-TJR-MSN-0206B): a false-positive exclusion must
    be recoverable without a raw SQL write."""
    inbox_base, db, _, worker = _make_worker(tmp_path, monkeypatch)
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    (inbox_base / "received" / "onedrive" / "book.mobi").write_bytes(b"fake")
    worker.scan()
    worker.process_batch(limit=10)

    excluded_row = db.get_one("processing_documents?select=*")
    assert excluded_row["status"] == "excluded"

    overridden = worker.override(excluded_row["id"])
    assert overridden["status"] == "received"
    assert overridden["exclusion_reason"] is None
    assert overridden["processing_log"][-1]["event"] == "override_reprocess"

    row_after = db.get_one("processing_documents?select=*")
    assert row_after["status"] == "received"
    assert row_after["exclusion_reason"] is None


def test_list_excluded_reports_reason_and_evidence(tmp_path, monkeypatch):
    inbox_base, db, _, worker = _make_worker(tmp_path, monkeypatch)
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    (inbox_base / "received" / "onedrive" / "book.mobi").write_bytes(b"fake")
    (inbox_base / "received" / "onedrive" / "report.txt").write_text("a real document")
    worker.scan()
    worker.process_batch(limit=10)

    excluded = worker.list_excluded()
    assert len(excluded) == 1
    assert excluded[0]["filename"] == "book.mobi"
    assert excluded[0]["exclusion_reason"] == "unsupported_media"
    assert excluded[0]["evidence"]["extension"] == "mobi"


def test_status_summary_includes_excluded(tmp_path, monkeypatch):
    inbox_base, db, _, worker = _make_worker(tmp_path, monkeypatch)
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    (inbox_base / "received" / "onedrive" / "book.mobi").write_bytes(b"fake")
    (inbox_base / "received" / "onedrive" / "report.txt").write_text("a real document")
    worker.scan()
    worker.process_batch(limit=10)

    summary = worker.status_summary()
    assert summary.get("excluded") == 1
    assert summary.get("awaiting_review") == 1


# -- failed document recovery (USS-TJR-MSN-0206J-4) ---------------------------------------------------------------

def _make_failed_document(tmp_path, monkeypatch, max_retries=3):
    """Helper: drive a document to plain `failed` via a classify failure,
    matching test_classify_failure_marks_failed_and_is_not_auto_retried."""
    inbox_base, db, model_router, worker = _make_worker(
        tmp_path, monkeypatch, fail_on={"classify"}, max_retries=max_retries,
    )
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    (inbox_base / "received" / "onedrive" / "report.txt").write_text("hello")
    worker.scan()
    worker.process_batch(limit=10)

    row = db.get_one("processing_documents?select=*")
    assert row["status"] == "failed"
    return inbox_base, db, model_router, worker, row


def test_retry_under_cap_sets_retry_pending_and_increments_count(tmp_path, monkeypatch):
    inbox_base, db, model_router, worker, failed_row = _make_failed_document(tmp_path, monkeypatch)

    retried = worker.retry(failed_row["id"])
    assert retried["status"] == "retry_pending"
    assert retried["retry_count"] == 1
    assert retried["failure_reason"] is None
    assert retried["processing_log"][-1]["event"] == "retry_requested"

    row_after = db.get_one("processing_documents?select=*")
    assert row_after["status"] == "retry_pending"
    assert row_after["retry_count"] == 1
    assert row_after["failure_reason"] is None


def test_full_retry_cycle_reaches_awaiting_review_with_fresh_chunks(tmp_path, monkeypatch):
    """A retry_pending document must advance through retrying back to
    awaiting_review, with prior stale processing_chunks gone and new ones
    inserted without a unique-constraint collision."""
    inbox_base, db, model_router, worker, failed_row = _make_failed_document(tmp_path, monkeypatch)

    # Simulate a prior partial embed leaving a stale chunk behind.
    db.insert("processing_chunks", {
        "document_id": failed_row["id"], "chunk_index": 0,
        "chunk_text": "stale chunk from the failed attempt",
        "embedding": [0.0] * 8, "embedding_model": "nomic-embed-text",
    })
    assert len(db.get(f"processing_chunks?document_id=eq.{failed_row['id']}")) == 1

    # classify no longer fails — the retry should succeed this time.
    model_router.fail_on = set()
    worker.retry(failed_row["id"])

    result = worker.process_batch(limit=10)
    assert result == {"documents": 1, "awaiting_review": 1, "failed": 0, "excluded": 0}

    row = db.get_one("processing_documents?select=*")
    assert row["status"] == "awaiting_review"
    assert row["retry_count"] == 1
    events = [e["event"] for e in row["processing_log"]]
    assert "retry_requested" in events
    assert "retrying" in events
    assert events[-1] == "awaiting_review"

    chunks = db.get(f"processing_chunks?document_id=eq.{row['id']}")
    assert len(chunks) == row["chunk_count"] > 0
    assert all(c["chunk_text"] != "stale chunk from the failed attempt" for c in chunks)
    # no duplicate chunk_index collisions
    assert sorted(c["chunk_index"] for c in chunks) == list(range(len(chunks)))


def test_retry_that_fails_again_returns_to_plain_failed(tmp_path, monkeypatch):
    inbox_base, db, model_router, worker, failed_row = _make_failed_document(tmp_path, monkeypatch)

    # Leave classify failing — the retry will fail again.
    worker.retry(failed_row["id"])
    result = worker.process_batch(limit=10)
    assert result == {"documents": 1, "awaiting_review": 0, "failed": 1, "excluded": 0}

    row = db.get_one("processing_documents?select=*")
    assert row["status"] == "failed"
    assert row["retry_count"] == 1  # still retriable — under the default cap of 3

    # Still retriable: a second retry() call should succeed (under cap).
    retried_again = worker.retry(row["id"])
    assert retried_again["status"] == "retry_pending"
    assert retried_again["retry_count"] == 2


def test_retry_at_cap_sets_permanently_failed_and_raises(tmp_path, monkeypatch):
    inbox_base, db, model_router, worker, failed_row = _make_failed_document(tmp_path, monkeypatch, max_retries=1)

    # First retry: under cap (retry_count 0 -> 1).
    worker.retry(failed_row["id"])
    worker.process_batch(limit=10)  # fails again (classify still fails), retry_count stays 1

    row = db.get_one("processing_documents?select=*")
    assert row["status"] == "failed"
    assert row["retry_count"] == 1

    # Second retry request: at the cap (max_retries=1) -> permanently_failed + raises.
    try:
        worker.retry(row["id"])
        assert False, "expected ValueError when retrying at/over max_retries"
    except ValueError as exc:
        assert "override" in str(exc)

    row_after = db.get_one("processing_documents?select=*")
    assert row_after["status"] == "permanently_failed"
    assert row_after["processing_log"][-1]["event"] == "retry_cap_exceeded"

    # A further retry() call must refuse — it's no longer status 'failed'.
    try:
        worker.retry(row_after["id"])
        assert False, "expected ValueError when retrying a permanently_failed document"
    except ValueError:
        pass


def test_permanently_failed_is_terminal_and_not_reprocessed(tmp_path, monkeypatch):
    inbox_base, db, model_router, worker, failed_row = _make_failed_document(tmp_path, monkeypatch, max_retries=0)

    try:
        worker.retry(failed_row["id"])
        assert False, "expected ValueError with max_retries=0"
    except ValueError:
        pass

    row = db.get_one("processing_documents?select=*")
    assert row["status"] == "permanently_failed"

    result = worker.process_batch(limit=10)
    assert result == {"documents": 0, "awaiting_review": 0, "failed": 0, "excluded": 0}


def test_list_failed_reports_failed_and_permanently_failed(tmp_path, monkeypatch):
    inbox_base, db, model_router, worker, failed_row = _make_failed_document(tmp_path, monkeypatch, max_retries=0)
    try:
        worker.retry(failed_row["id"])
    except ValueError:
        pass  # moved to permanently_failed

    (inbox_base / "received" / "onedrive" / "report2.txt").write_text("hello again")
    worker.scan()
    model_router.fail_on = {"classify"}
    worker.process_batch(limit=10)

    reported = worker.list_failed()
    statuses = {row["filename"]: row["status"] for row in reported}
    assert statuses["report.txt"] == "permanently_failed"
    assert statuses["report2.txt"] == "failed"
    assert all("retry_count" in row and "failure_reason" in row and "last_retry_at" in row for row in reported)


# -- bounded automatic retry sweep (USS-TJR-MSN-0207A) ---------------------------------------------------------------

def test_retry_all_requeues_under_cap_and_permanently_fails_at_cap(tmp_path, monkeypatch):
    """A sweep over a mix of under-cap and at-cap `failed` documents must
    requeue the former, correctly permanently_fail the latter via the
    existing retry() cap logic, and not let one document's ValueError stop
    the rest of the sweep from being attempted."""
    inbox_base, db, model_router, worker = _make_worker(
        tmp_path, monkeypatch, fail_on={"classify"}, max_retries=1,
    )
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    for name in ("under_cap.txt", "at_cap.txt", "also_under_cap.txt"):
        (inbox_base / "received" / "onedrive" / name).write_text("hello")
    worker.scan()
    worker.process_batch(limit=10)  # all three fail on classify -> status 'failed', retry_count 0

    rows = {r["filename"]: r for r in db.get("processing_documents?select=*")}
    assert all(r["status"] == "failed" for r in rows.values())

    # Push at_cap.txt to retry_count == max_retries (1) via one retry cycle
    # that fails again, so the next retry() call in the sweep hits the cap.
    worker.retry(rows["at_cap.txt"]["id"])
    worker.process_batch(limit=10)  # classify still fails -> back to 'failed', retry_count stays 1
    at_cap_before = db.get_one(f"processing_documents?id=eq.{rows['at_cap.txt']['id']}&select=*")
    assert at_cap_before["status"] == "failed"
    assert at_cap_before["retry_count"] == 1  # == max_retries=1, so next retry() hits the cap

    summary = worker.retry_all()
    assert summary == {"attempted": 3, "requeued": 2, "permanently_failed": 1}

    at_cap_after = db.get_one(f"processing_documents?id=eq.{rows['at_cap.txt']['id']}&select=*")
    assert at_cap_after["status"] == "permanently_failed"

    for name in ("under_cap.txt", "also_under_cap.txt"):
        row_after = db.get_one(f"processing_documents?id=eq.{rows[name]['id']}&select=*")
        assert row_after["status"] == "retry_pending"
        assert row_after["retry_count"] == 1


def test_retry_all_is_noop_when_no_failed_documents(tmp_path, monkeypatch):
    inbox_base, db, model_router, worker = _make_worker(tmp_path, monkeypatch)
    (inbox_base / "received" / "onedrive").mkdir(parents=True)
    (inbox_base / "received" / "onedrive" / "report.txt").write_text("hello")
    worker.scan()
    worker.process_batch(limit=10)  # succeeds -> awaiting_review, nothing failed

    summary = worker.retry_all()
    assert summary == {"attempted": 0, "requeued": 0, "permanently_failed": 0}


def test_retry_all_ignores_already_permanently_failed_documents(tmp_path, monkeypatch):
    """retry_all() must query only status='failed' — a permanently_failed
    document is already exhausted and calling retry() on it would just
    raise for no benefit; the sweep should skip it outright rather than
    counting it as an attempt."""
    inbox_base, db, model_router, worker, failed_row = _make_failed_document(
        tmp_path, monkeypatch, max_retries=0,
    )
    try:
        worker.retry(failed_row["id"])
    except ValueError:
        pass  # moved to permanently_failed
    row = db.get_one("processing_documents?select=*")
    assert row["status"] == "permanently_failed"

    summary = worker.retry_all()
    assert summary == {"attempted": 0, "requeued": 0, "permanently_failed": 0}


# -- healthcheck (USS-TJR-MSN-0207A) ---------------------------------------------------------------

def test_compute_health_healthy_with_no_failures():
    report = compute_health(
        status_counts={"awaiting_review": 10, "received": 2},
        failed_rows=[],
        thresholds=HealthThresholds(),
    )
    assert report["healthy"] is True
    assert report["failed_count"] == 0
    assert report["permanently_failed_count"] == 0
    assert report["retry_eligible_count"] == 0
    assert report["status_counts"] == {"awaiting_review": 10, "received": 2}


def test_compute_health_unhealthy_when_permanently_failed_exceeds_threshold():
    failed_rows = [
        {"id": "1", "filename": "a.txt", "status": "permanently_failed", "retry_count": 3,
         "failure_reason": "boom", "last_retry_at": None},
    ]
    report = compute_health(
        status_counts={"permanently_failed": 1},
        failed_rows=failed_rows,
        thresholds=HealthThresholds(permanently_failed_threshold=0),
    )
    assert report["healthy"] is False
    assert report["permanently_failed_count"] == 1


def test_compute_health_unhealthy_when_failed_count_exceeds_threshold():
    failed_rows = [
        {"id": str(i), "filename": f"f{i}.txt", "status": "failed", "retry_count": 0,
         "failure_reason": "boom", "last_retry_at": None}
        for i in range(3)
    ]
    report = compute_health(
        status_counts={"failed": 3},
        failed_rows=failed_rows,
        thresholds=HealthThresholds(failed_threshold=2),
    )
    assert report["healthy"] is False
    assert report["failed_count"] == 3
    assert report["retry_eligible_count"] == 3


def test_compute_health_default_threshold_flags_a_single_permanently_failed_document():
    """Regression test: HealthThresholds()'s *default* permanently_failed_threshold
    must be 0, not 1 — the module's own docstring says "even a single
    [permanently_failed document] is worth flagging", which only holds if a
    single occurrence exceeds the default threshold. Every other test in
    this file passes an explicit threshold override, so none of them would
    have caught a wrong default value here."""
    failed_rows = [
        {"id": "1", "filename": "a.txt", "status": "permanently_failed", "retry_count": 3,
         "failure_reason": "boom", "last_retry_at": None},
    ]
    report = compute_health(
        status_counts={"permanently_failed": 1},
        failed_rows=failed_rows,
        thresholds=HealthThresholds(),  # defaults, no override
    )
    assert report["healthy"] is False


def test_compute_health_stays_healthy_at_exactly_the_threshold():
    failed_rows = [
        {"id": "1", "filename": "a.txt", "status": "failed", "retry_count": 0,
         "failure_reason": "boom", "last_retry_at": None},
    ]
    report = compute_health(
        status_counts={"failed": 1},
        failed_rows=failed_rows,
        thresholds=HealthThresholds(failed_threshold=1, permanently_failed_threshold=0),
    )
    assert report["healthy"] is True


def test_run_healthcheck_uses_worker_read_methods_end_to_end(tmp_path, monkeypatch):
    """Integration check that run_healthcheck() actually calls the real
    worker.status_summary()/list_failed() (via FakeSupabase) rather than
    querying the DB independently."""
    inbox_base, db, model_router, worker, failed_row = _make_failed_document(
        tmp_path, monkeypatch, max_retries=3,
    )
    report = run_healthcheck(worker, HealthThresholds())
    assert report["status_counts"].get("failed") == 1
    assert report["failed_count"] == 1
    assert report["permanently_failed_count"] == 0
    assert report["retry_eligible_count"] == 1
    assert report["healthy"] is True
