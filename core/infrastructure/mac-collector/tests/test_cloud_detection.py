import sys
import textwrap
from pathlib import Path

import pytest

from config import load_config
from db import TrackingDB
from collector import Collector
import cloud_detection


# -- helpers ---------------------------------------------------------------

def _write_config(tmp_path: Path, source_dir: Path, include_cloud_only: bool = False) -> Path:
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
          include_cloud_only: {"true" if include_cloud_only else "false"}
        database:
          path: "./collector.db"
        manifest:
          output_dir: "./manifests"
    """))
    return config_path


def _fake_availability(statuses: dict, default: str = "local"):
    """Build a fake check_availability_fn keyed by rel-path-matching filename."""
    def fn(path: Path) -> str:
        return statuses.get(path.name, default)
    return fn


# -- Collector.scan: cloud-only / unavailable handling ----------------------

def test_scan_excludes_cloud_only_file(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("alpha")
    (source_dir / "placeholder.txt").write_text("")  # simulated dataless stub

    config = load_config(str(_write_config(tmp_path, source_dir)))
    collector = Collector(config, check_availability_fn=_fake_availability(
        {"placeholder.txt": "cloud_only"}
    ))

    with TrackingDB(config.db_path) as db:
        result = collector.scan(db, dry_run=False)
        active_after = {r["rel_path"] for r in db.active_files()}

    assert result.cloud_only_count == 1
    assert [f["path"] for f in result.cloud_only_files] == ["placeholder.txt"]
    assert {f["path"] for f in result.new_files} == {"a.txt"}
    assert active_after == {"a.txt"}


def test_scan_reports_unavailable_file(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("alpha")
    (source_dir / "gone.txt").write_text("will vanish")

    config = load_config(str(_write_config(tmp_path, source_dir)))
    collector = Collector(config, check_availability_fn=_fake_availability(
        {"gone.txt": "unavailable"}
    ))

    with TrackingDB(config.db_path) as db:
        result = collector.scan(db, dry_run=False)
        active_after = {r["rel_path"] for r in db.active_files()}

    assert result.unavailable_count == 1
    assert [f["path"] for f in result.unavailable_files] == ["gone.txt"]
    assert result.errors == []
    assert {f["path"] for f in result.new_files} == {"a.txt"}
    assert active_after == {"a.txt"}


def test_include_cloud_only_override_hashes_file(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "placeholder.txt").write_text("actually has content")

    config = load_config(str(_write_config(tmp_path, source_dir, include_cloud_only=True)))
    collector = Collector(config, check_availability_fn=_fake_availability(
        {"placeholder.txt": "cloud_only"}
    ))

    with TrackingDB(config.db_path) as db:
        result = collector.scan(db, dry_run=False)
        active_after = {r["rel_path"] for r in db.active_files()}

    assert result.cloud_only_count == 0
    assert result.cloud_only_files == []
    assert {f["path"] for f in result.new_files} == {"placeholder.txt"}
    assert active_after == {"placeholder.txt"}


def test_ordinary_local_files_unaffected(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("alpha")
    (source_dir / "b.txt").write_text("beta")

    config = load_config(str(_write_config(tmp_path, source_dir)))
    collector = Collector(config, check_availability_fn=_fake_availability({}))

    with TrackingDB(config.db_path) as db:
        result = collector.scan(db, dry_run=False)

    assert result.cloud_only_count == 0
    assert result.unavailable_count == 0
    assert {f["path"] for f in result.new_files} == {"a.txt", "b.txt"}


# -- cloud_detection.check_availability (unit-level, fully faked) -----------

def test_check_availability_unavailable_on_missing_path(tmp_path):
    missing = tmp_path / "does-not-exist.txt"
    assert cloud_detection.check_availability(missing) == "unavailable"


def test_check_availability_detects_legacy_icloud_placeholder(tmp_path):
    real_name = tmp_path / "photo.heic"
    stub = tmp_path / ".photo.heic.icloud"
    stub.write_text("")
    # The real file doesn't exist under its real name yet — only the stub does.
    assert cloud_detection.check_availability(real_name) == "cloud_only"


def test_check_availability_local_file_with_icloud_sibling_stub_for_other_file(tmp_path):
    (tmp_path / "a.txt").write_text("alpha")
    (tmp_path / ".b.txt.icloud").write_text("")
    assert cloud_detection.check_availability(tmp_path / "a.txt") == "local"


@pytest.mark.skipif(sys.platform != "darwin", reason="st_flags/SF_DATALESS is macOS-only")
def test_check_availability_real_local_file_on_macos(tmp_path):
    real_file = tmp_path / "real.txt"
    real_file.write_text("this file is fully on disk")
    # Can't fabricate a real OneDrive/iCloud placeholder in a test — this
    # just proves the st_flags code path runs cleanly on a real macOS file
    # without crashing and correctly reports it as local.
    assert cloud_detection.check_availability(real_file) == "local"
