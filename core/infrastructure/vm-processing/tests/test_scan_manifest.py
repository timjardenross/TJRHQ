"""USS-TJR-MSN-0412 egress fix: scan() must not ask Supabase about every file on every run.

An unchanged inbox makes no Supabase request; only new or changed files are checked; once a day the
manifest is rebuilt from one batched read so it cannot drift from the database. Uses the in-memory
FakeSupabase, whose get_log records every read.
"""
import json
import os
import time

import worker as worker_module
from test_worker_state_machine import _make_worker


def _put(inbox_base, name, text="hello", source="onedrive"):
    d = inbox_base / "received" / source
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_text(text)
    return f


def _reads(db):
    return [p for p in db.get_log if p.startswith("processing_documents")]


def test_unchanged_inbox_makes_no_supabase_request(tmp_path, monkeypatch):
    inbox, db, _, w = _make_worker(tmp_path, monkeypatch)
    for i in range(12):
        _put(inbox, f"f{i}.txt")
    w.scan()  # first scan: manifest empty -> one full sync
    db.get_log.clear()

    result = w.scan()
    assert result == {"new": 0, "skipped": 12, "root_missing": False}
    assert db.get_log == []
    assert w.last_scan_stats["read_requests"] == 0
    assert w.last_scan_stats["full_sync"] is False


def test_first_scan_uses_one_batched_read_not_one_per_file(tmp_path, monkeypatch):
    inbox, db, _, w = _make_worker(tmp_path, monkeypatch)
    for i in range(30):
        _put(inbox, f"f{i}.txt")
    result = w.scan()
    assert result["new"] == 30
    assert len(_reads(db)) == 1  # the batched source_path read
    assert "select=source_path" in _reads(db)[0]


def test_existing_rows_are_adopted_without_reinserting(tmp_path, monkeypatch):
    inbox, db, _, w = _make_worker(tmp_path, monkeypatch)
    for i in range(8):
        _put(inbox, f"f{i}.txt")
    w.scan()
    (tmp_path / "scan_manifest.json").unlink()  # lose the manifest (e.g. new machine)
    db.get_log.clear()

    result = w.scan()
    assert result == {"new": 0, "skipped": 8, "root_missing": False}
    assert len(db.get("processing_documents?select=id")) == 8  # nothing duplicated
    assert len([p for p in _reads(db) if "select=source_path" in p]) == 1


def test_one_new_file_costs_one_request(tmp_path, monkeypatch):
    inbox, db, _, w = _make_worker(tmp_path, monkeypatch)
    for i in range(10):
        _put(inbox, f"f{i}.txt")
    w.scan()
    _put(inbox, "fresh.txt")
    db.get_log.clear()

    result = w.scan()
    assert result == {"new": 1, "skipped": 10, "root_missing": False}
    assert len(db.get_log) == 1
    assert "source_path=eq." in db.get_log[0]


def test_changed_file_is_checked_once_and_not_duplicated(tmp_path, monkeypatch):
    inbox, db, _, w = _make_worker(tmp_path, monkeypatch)
    f = _put(inbox, "report.txt", "one")
    w.scan()
    f.write_text("a longer second version")
    os.utime(f, ns=(time.time_ns(), time.time_ns() + 5_000_000_000))
    db.get_log.clear()

    result = w.scan()
    assert result == {"new": 0, "skipped": 1, "root_missing": False}
    assert len(db.get_log) == 1  # per-file check, row exists
    assert len(db.get("processing_documents?select=id")) == 1
    db.get_log.clear()
    w.scan()
    assert db.get_log == []  # manifest updated, quiet again


def test_many_changed_files_use_one_batched_read(tmp_path, monkeypatch):
    inbox, db, _, w = _make_worker(tmp_path, monkeypatch)
    files = [_put(inbox, f"f{i}.txt") for i in range(20)]
    w.scan()
    for f in files:
        os.utime(f, ns=(time.time_ns(), time.time_ns() + 9_000_000_000))
    db.get_log.clear()

    w.scan()
    assert len(db.get_log) == 1 and "select=source_path" in db.get_log[0]


def test_daily_full_sync_reinserts_a_row_deleted_in_the_database(tmp_path, monkeypatch):
    inbox, db, _, w = _make_worker(tmp_path, monkeypatch)
    for i in range(6):
        _put(inbox, f"f{i}.txt")
    w.scan()
    db.delete("processing_documents", {"filename": "f3.txt"})
    assert w.scan()["new"] == 0  # manifest still believes it exists (within the day)

    manifest_file = tmp_path / "scan_manifest.json"
    data = json.loads(manifest_file.read_text())
    data["last_full_sync"] = time.time() - worker_module.SCAN_FULL_SYNC_SECONDS - 60
    manifest_file.write_text(json.dumps(data))

    result = w.scan()
    assert result["new"] == 1 and w.last_scan_stats["full_sync"] is True
    assert {r["filename"] for r in db.get("processing_documents?select=filename")} >= {"f3.txt"}


def test_batched_read_pages_through_all_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(worker_module, "SCAN_PAGE_SIZE", 2)
    inbox, db, _, w = _make_worker(tmp_path, monkeypatch)
    for i in range(5):
        _put(inbox, f"f{i}.txt")
    w.scan()
    (tmp_path / "scan_manifest.json").unlink()
    db.get_log.clear()

    assert w.scan()["new"] == 0
    # 5 rows, page size 2 -> pages of 2, 2, 1 = 3 requests
    assert len([p for p in db.get_log if "select=source_path" in p]) == 3


def test_corrupt_manifest_is_treated_as_empty(tmp_path, monkeypatch):
    inbox, db, _, w = _make_worker(tmp_path, monkeypatch)
    for i in range(7):
        _put(inbox, f"f{i}.txt")
    w.scan()
    (tmp_path / "scan_manifest.json").write_text("{not json")
    assert w.scan() == {"new": 0, "skipped": 7, "root_missing": False}
    assert len(db.get("processing_documents?select=id")) == 7


def test_deleted_files_are_dropped_from_the_manifest(tmp_path, monkeypatch):
    inbox, _db, _, w = _make_worker(tmp_path, monkeypatch)
    keep = _put(inbox, "keep.txt")
    gone = _put(inbox, "gone.txt")
    w.scan()
    gone.unlink()
    w.scan()
    files = json.loads((tmp_path / "scan_manifest.json").read_text())["files"]
    assert list(files) == [str(keep.resolve())]


def test_unwritable_manifest_does_not_break_scan(tmp_path, monkeypatch):
    inbox, db, _, w = _make_worker(tmp_path, monkeypatch)
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    w.manifest_path = blocker / "scan_manifest.json"
    _put(inbox, "a.txt")
    assert w.scan() == {"new": 1, "skipped": 0, "root_missing": False}
    assert w.scan()["skipped"] == 1  # falls back to checking, still no duplicate row
    assert len(db.get("processing_documents?select=id")) == 1


def test_old_behaviour_would_have_made_one_request_per_file(tmp_path, monkeypatch):
    """Guard on the number that matters: 40 unchanged files, steady state, zero reads."""
    inbox, db, _, w = _make_worker(tmp_path, monkeypatch)
    for i in range(40):
        _put(inbox, f"f{i}.txt")
    w.scan()
    db.get_log.clear()
    for _ in range(5):
        w.scan()
    assert len(db.get_log) == 0
