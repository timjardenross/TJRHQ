import hashlib
import json
import textwrap
from pathlib import Path

import pytest

from config import load_config
from transfer_db import TransferDB
from engine import TransferEngine, parse_checksum_output
from fake_transport import FakeTransport


# -- parse_checksum_output ---------------------------------------------------------------

def test_parse_checksum_output_mixed():
    stdout = "a/one.txt: OK\nb/two.txt: FAILED\nc/three.txt: FAILED open or read\n"
    results = parse_checksum_output(stdout)
    assert results == {"a/one.txt": True, "b/two.txt": False, "c/three.txt": False}


# -- helpers ---------------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_config(tmp_path: Path, exclude_patterns=None) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(textwrap.dedent(f"""
        remote:
          host: "vm.test.internal"
          port: 22
          user: "transferbot"
          ssh_key: "~/.ssh/id_test"
          base_path: "/opt/inbox"
        retry:
          max_attempts: 2
          backoff_seconds: 0
        exclude_patterns: {exclude_patterns or []}
        database:
          path: "./transfer.db"
        logs:
          dir: "./logs"
    """))
    return config_path


def _make_source_files(tmp_path: Path, source_name: str, files: dict) -> list:
    """files: {rel_path: content_bytes}. Returns manifest-style entries."""
    root = tmp_path / f"src-{source_name}"
    root.mkdir(exist_ok=True)
    entries = []
    for rel_path, content in files.items():
        p = root / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        entries.append({
            "source": source_name,
            "rel_path": rel_path,
            "abs_path": str(p),
            "sha256": _sha256(content),
            "size_bytes": len(content),
            "mtime": p.stat().st_mtime,
        })
    return entries


def _write_manifest(tmp_path: Path, entries: list) -> Path:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "generated_at": "2026-07-03T00:00:00+00:00",
        "file_count": len(entries),
        "total_size_bytes": sum(e["size_bytes"] for e in entries),
        "files": entries,
    }))
    return manifest_path


def _engine(tmp_path, exclude_patterns=None, transport=None):
    config = load_config(str(_write_config(tmp_path, exclude_patterns)))
    db = TransferDB(config.db_path)
    transport = transport or FakeTransport()
    return config, db, TransferEngine(config, db, transport), transport


# -- transfer ---------------------------------------------------------------

def test_transfer_success_marks_verified_and_moves(tmp_path):
    entries = _make_source_files(tmp_path, "onedrive", {"a.txt": b"alpha", "sub/b.txt": b"beta"})
    manifest = _write_manifest(tmp_path, entries)
    config, db, engine, transport = _engine(tmp_path)

    summary = engine.run_transfer(str(manifest), dry_run=False)

    assert summary.transferred_count == 2
    assert summary.verified_count == 2
    assert summary.failed_count == 0
    assert transport.ensure_dirs_calls == 1
    assert any("received" in script for script in transport.moved_scripts)

    for e in entries:
        row = db.get_file_state("onedrive", e["rel_path"])
        assert row["status"] == "verified"


def test_transfer_excludes_pattern(tmp_path):
    entries = _make_source_files(tmp_path, "onedrive", {"keep.txt": b"keep", "hold.draft": b"draft"})
    manifest = _write_manifest(tmp_path, entries)
    config, db, engine, transport = _engine(tmp_path, exclude_patterns=["*.draft"])

    summary = engine.run_transfer(str(manifest), dry_run=False)

    assert summary.excluded_count == 1
    assert summary.transferred_count == 1
    rsync_calls = [c for c in transport.calls if c[0] == "rsync_push"]
    assert len(rsync_calls) == 1
    assert rsync_calls[0][3] == ["keep.txt"]
    assert db.get_file_state("onedrive", "hold.draft")["status"] == "excluded"


def test_dry_run_transfer_persists_nothing(tmp_path):
    entries = _make_source_files(tmp_path, "onedrive", {"a.txt": b"alpha"})
    manifest = _write_manifest(tmp_path, entries)
    config, db, engine, transport = _engine(tmp_path)

    summary = engine.run_transfer(str(manifest), dry_run=True)

    assert summary.dry_run is True
    assert summary.transferred_count == 0
    assert len(summary.planned) == 1
    assert transport.ensure_dirs_calls == 0
    assert transport.moved_scripts == []
    assert db.get_file_state("onedrive", "a.txt") is None
    assert db.summary()["by_status"] == {}


def test_checksum_mismatch_marks_failed_and_routes_to_failed_dir(tmp_path):
    entries = _make_source_files(tmp_path, "onedrive", {"good.txt": b"good", "bad.txt": b"bad"})
    manifest = _write_manifest(tmp_path, entries)
    transport = FakeTransport(checksum_overrides={"onedrive": {"bad.txt": False}})
    config, db, engine, transport = _engine(tmp_path, transport=transport)

    summary = engine.run_transfer(str(manifest), dry_run=False)

    assert summary.verified_count == 1
    assert summary.failed_count == 1
    good_row = db.get_file_state("onedrive", "good.txt")
    bad_row = db.get_file_state("onedrive", "bad.txt")
    assert good_row["status"] == "verified"
    assert bad_row["status"] == "failed"
    assert bad_row["attempts"] == 1
    move_script = "\n".join(transport.moved_scripts)
    assert "received" in move_script and "/failed/" in move_script


def test_rsync_failure_after_retries_marks_failed_without_verifying(tmp_path):
    entries = _make_source_files(tmp_path, "onedrive", {"a.txt": b"alpha"})
    manifest = _write_manifest(tmp_path, entries)
    transport = FakeTransport(rsync_results={"onedrive": [(1, "", "boom"), (1, "", "boom again")]})
    config, db, engine, transport = _engine(tmp_path, transport=transport)

    summary = engine.run_transfer(str(manifest), dry_run=False)

    assert summary.transferred_count == 0
    assert summary.failed_count == 1
    verify_calls = [c for c in transport.calls if c[0] == "verify_checksums"]
    assert verify_calls == []
    row = db.get_file_state("onedrive", "a.txt")
    assert row["status"] == "failed"
    assert row["attempts"] == 1


def test_second_run_skips_already_verified_files(tmp_path):
    entries = _make_source_files(tmp_path, "onedrive", {"a.txt": b"alpha"})
    manifest = _write_manifest(tmp_path, entries)
    config, db, engine, transport = _engine(tmp_path)

    engine.run_transfer(str(manifest), dry_run=False)
    transport.calls.clear()

    summary = engine.run_transfer(str(manifest), dry_run=False)

    assert summary.skipped_count == 1
    assert summary.transferred_count == 0
    rsync_calls = [c for c in transport.calls if c[0] == "rsync_push"]
    assert rsync_calls == []


# -- retry-failed ---------------------------------------------------------------

def test_retry_failed_requeues_and_succeeds(tmp_path):
    entries = _make_source_files(tmp_path, "onedrive", {"bad.txt": b"bad"})
    manifest = _write_manifest(tmp_path, entries)
    failing_transport = FakeTransport(checksum_overrides={"onedrive": {"bad.txt": False}})
    config, db, engine, _ = _engine(tmp_path, transport=failing_transport)
    engine.run_transfer(str(manifest), dry_run=False)
    assert db.get_file_state("onedrive", "bad.txt")["status"] == "failed"

    engine.transport = FakeTransport()  # now checksum succeeds
    summary = engine.retry_failed()

    assert summary.verified_count == 1
    row = db.get_file_state("onedrive", "bad.txt")
    assert row["status"] == "verified"
    assert row["attempts"] == 1  # only incremented on the original failure


def test_retry_failed_respects_max_attempts(tmp_path):
    entries = _make_source_files(tmp_path, "onedrive", {"bad.txt": b"bad"})
    manifest = _write_manifest(tmp_path, entries)
    failing_transport = FakeTransport(rsync_results={"onedrive": [(1, "", "x"), (1, "", "x")]})
    config, db, engine, _ = _engine(tmp_path, transport=failing_transport)
    engine.run_transfer(str(manifest), dry_run=False)
    assert db.get_file_state("onedrive", "bad.txt")["attempts"] == 1

    summary = engine.retry_failed(max_attempts=1)

    assert summary.requested_count == 0  # attempts (1) is not < max_attempts (1)


# -- verify-transfer resume path ---------------------------------------------------------------

def test_verify_transfer_resumes_interrupted_run(tmp_path):
    entries = _make_source_files(tmp_path, "onedrive", {"a.txt": b"alpha"})
    config, db, engine, transport = _engine(tmp_path)

    # Simulate a crash after rsync succeeded (status='transferred') but before
    # the checksum/move step ran.
    now = "2026-07-03T00:00:00+00:00"
    batch_id = db.start_batch(None, dry_run=False, now=now, kind="transfer")
    e = entries[0]
    db.upsert_pending(e["source"], e["rel_path"], e["abs_path"], e["sha256"], e["size_bytes"], now, batch_id)
    db.mark_transferred(e["source"], e["rel_path"], now, batch_id)
    db.commit()

    summary = engine.verify_transfer(status="transferred")

    assert summary.verified_count == 1
    row = db.get_file_state("onedrive", "a.txt")
    assert row["status"] == "verified"
    assert any("received" in s for s in transport.moved_scripts)
