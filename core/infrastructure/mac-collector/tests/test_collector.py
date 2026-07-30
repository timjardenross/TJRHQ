import hashlib
import textwrap
from pathlib import Path

import pytest

from config import load_config
from db import TrackingDB
from collector import Collector, sha256_file
from ignore_rules import IgnoreMatcher


# -- ignore_rules ------------------------------------------------------------

def test_ignore_matches_simple_pattern():
    m = IgnoreMatcher(patterns=["*.tmp", ".DS_Store"], max_file_size_mb=500, ignore_hidden=False)
    assert m.match("notes.tmp").ignored
    assert m.match("sub/dir/.DS_Store").ignored
    assert not m.match("notes.txt").ignored


def test_ignore_matches_directory_pattern():
    m = IgnoreMatcher(patterns=["node_modules/**"], max_file_size_mb=500, ignore_hidden=False)
    assert m.match("node_modules/leftpad/index.js").ignored
    assert not m.match("src/node_modules_readme.txt").ignored


def test_ignore_hidden_files():
    m = IgnoreMatcher(patterns=[], max_file_size_mb=500, ignore_hidden=True)
    assert m.match(".hidden/file.txt").ignored
    assert m.match("visible/.hiddenfile").ignored
    assert not m.match("visible/file.txt").ignored


def test_ignore_max_size():
    m = IgnoreMatcher(patterns=[], max_file_size_mb=1, ignore_hidden=False)
    decision = m.match("big.bin", size_bytes=2 * 1024 * 1024)
    assert decision.ignored
    assert not m.match("small.bin", size_bytes=100).ignored


# -- sha256_file ---------------------------------------------------------------

def test_sha256_file_matches_hashlib(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_bytes(b"hello world" * 1000)
    expected = hashlib.sha256(f.read_bytes()).hexdigest()
    assert sha256_file(f) == expected


# -- helpers ---------------------------------------------------------------

def _write_config(tmp_path: Path, source_dir: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(textwrap.dedent(f"""
        sources:
          - name: testsrc
            path: "{source_dir}"
            enabled: true
        ignore:
          patterns:
            - ".DS_Store"
            - "*.tmp"
          max_file_size_mb: 500
          ignore_hidden: true
        database:
          path: "./collector.db"
        manifest:
          output_dir: "./manifests"
    """))
    return config_path


# -- Collector.scan ---------------------------------------------------------------

def test_scan_detects_new_files(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("alpha")
    (source_dir / "b.txt").write_text("beta")
    (source_dir / ".DS_Store").write_text("junk")

    config = load_config(str(_write_config(tmp_path, source_dir)))
    collector = Collector(config)
    with TrackingDB(config.db_path) as db:
        result = collector.scan(db, dry_run=False)

    assert result.files_scanned == 2
    assert {f["path"] for f in result.new_files} == {"a.txt", "b.txt"}
    assert result.ignored_count == 1


def test_scan_detects_changed_and_unchanged(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("alpha")

    config = load_config(str(_write_config(tmp_path, source_dir)))
    collector = Collector(config)

    with TrackingDB(config.db_path) as db:
        collector.scan(db, dry_run=False)

    (source_dir / "a.txt").write_text("alpha-modified")

    with TrackingDB(config.db_path) as db:
        result = collector.scan(db, dry_run=False)

    assert [f["path"] for f in result.changed_files] == ["a.txt"]
    assert result.new_files == []


def test_scan_detects_deleted_files(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("alpha")
    (source_dir / "b.txt").write_text("beta")

    config = load_config(str(_write_config(tmp_path, source_dir)))
    collector = Collector(config)

    with TrackingDB(config.db_path) as db:
        collector.scan(db, dry_run=False)

    (source_dir / "b.txt").unlink()

    with TrackingDB(config.db_path) as db:
        result = collector.scan(db, dry_run=False)
        active_after = {r["rel_path"] for r in db.active_files()}

    assert [f["path"] for f in result.deleted_files] == ["b.txt"]
    assert active_after == {"a.txt"}


def test_dry_run_does_not_persist(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("alpha")

    config = load_config(str(_write_config(tmp_path, source_dir)))
    collector = Collector(config)

    with TrackingDB(config.db_path) as db:
        result = collector.scan(db, dry_run=True)
        assert result.dry_run is True
        assert [f["path"] for f in result.new_files] == ["a.txt"]

    with TrackingDB(config.db_path) as db:
        assert db.active_files() == []
        assert db.latest_scan() is None


def test_unmounted_source_does_not_wipe_tracking(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("alpha")

    config = load_config(str(_write_config(tmp_path, source_dir)))
    collector = Collector(config)

    with TrackingDB(config.db_path) as db:
        collector.scan(db, dry_run=False)

    # Simulate the source folder being unavailable (e.g. drive unmounted).
    for child in source_dir.iterdir():
        child.unlink()
    source_dir.rmdir()

    with TrackingDB(config.db_path) as db:
        result = collector.scan(db, dry_run=False)
        active_after = {r["rel_path"] for r in db.active_files()}

    assert result.deleted_files == []
    assert any("source path not found" in e for e in result.errors)
    assert active_after == {"a.txt"}
