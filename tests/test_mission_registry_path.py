"""Tests for the mission registry resolver and its consumers.

Covers: default path resolution, the MISSION_REGISTRY_PATH override, missing or
unreadable registry handling, sync-job append to an external path, the memory
adapter reading the resolved file, and a guard that no consumer rebuilds the
tracked path by hand.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mission_registry_path import (
    ENV_VAR,
    TRACKED_DEFAULT,
    MissionRegistryError,
    read_registry_text,
    registry_path,
)

TRACKED_RELATIVE = Path("core") / "mission-control" / "registry" / "mission-index.txt"


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)


# --- default resolution -----------------------------------------------------

def test_default_path_is_tracked_checkout_path():
    assert registry_path() == TRACKED_DEFAULT
    assert TRACKED_DEFAULT == REPO_ROOT / TRACKED_RELATIVE


def test_blank_env_value_uses_default(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "   ")
    assert registry_path() == TRACKED_DEFAULT


# --- override ---------------------------------------------------------------

def test_absolute_override_is_returned(monkeypatch, tmp_path):
    external = tmp_path / "state" / "mission-index.txt"
    monkeypatch.setenv(ENV_VAR, str(external))
    assert registry_path() == external


def test_relative_override_is_rejected(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "mission-index.txt")
    with pytest.raises(ValueError, match="absolute path"):
        registry_path()


# --- missing / unreadable registry -------------------------------------------

def test_read_missing_registry_raises_registry_error(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "absent.txt"))
    with pytest.raises(MissionRegistryError, match="missing or not a regular file"):
        read_registry_text()


def test_read_directory_raises_registry_error(tmp_path):
    with pytest.raises(MissionRegistryError, match="not a regular file"):
        read_registry_text(tmp_path)


def test_read_undecodable_registry_raises_registry_error(tmp_path):
    bad = tmp_path / "mission-index.txt"
    bad.write_bytes(b"\xff\xfe\xfd not utf-8")
    with pytest.raises(MissionRegistryError, match="unreadable"):
        read_registry_text(bad)


def test_error_message_names_path_but_not_content(tmp_path):
    bad = tmp_path / "mission-index.txt"
    bad.write_bytes(b"SECRET-LIKE-CONTENT \xff")
    with pytest.raises(MissionRegistryError) as info:
        read_registry_text(bad)
    assert "SECRET-LIKE-CONTENT" not in str(info.value)


def test_read_uses_override_when_no_path_given(monkeypatch, tmp_path):
    external = tmp_path / "mission-index.txt"
    external.write_text("- USS-TJR-MSN-0001 | x\n", encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(external))
    assert "USS-TJR-MSN-0001" in read_registry_text()


# --- sync job --------------------------------------------------------------



def _load_sync():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sync_supabase_to_registry", REPO_ROOT / "tools" / "sync_supabase_to_registry.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_sync_reads_ids_from_override(monkeypatch, tmp_path):
    external = tmp_path / "mission-index.txt"
    external.write_text("- USS-TJR-MSN-0042 | 2026-11-08 | Supabase | Idea | t\n", encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(external))
    sync = _load_sync()
    assert "USS-TJR-MSN-0042" in sync.load_registry_ids()


def test_sync_missing_external_registry_yields_no_ids(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "not-yet.txt"))
    assert _load_sync().load_registry_ids() == set()


def test_sync_append_creates_external_file_and_parent_dirs(tmp_path):
    sync = _load_sync()
    target = tmp_path / "var" / "lib" / "registry" / "mission-index.txt"
    before = TRACKED_DEFAULT.read_bytes() if TRACKED_DEFAULT.exists() else None
    sync._append_entries(
        target,
        [{"mission_id": "uss-tjr-msn-0777", "title": "A|B", "status": "Idea"}],
        "2026-11-08 06:45",
    )
    text = target.read_text(encoding="utf-8")
    assert "# MSN-0145 SUPABASE SYNC (2026-11-08 06:45)" in text
    assert "- USS-TJR-MSN-0777 | 2026-11-08 06:45 | Supabase | Idea | A—B" in text
    # the tracked checkout file must not be touched by an external write
    after = TRACKED_DEFAULT.read_bytes() if TRACKED_DEFAULT.exists() else None
    assert before == after


def test_sync_append_is_additive(tmp_path):
    sync = _load_sync()
    target = tmp_path / "mission-index.txt"
    target.write_text("- USS-TJR-MSN-0001 | keep\n", encoding="utf-8")
    sync._append_entries(target, [{"mission_id": "USS-TJR-MSN-0002"}], "2026-11-08 06:45")
    text = target.read_text(encoding="utf-8")
    assert text.startswith("- USS-TJR-MSN-0001 | keep\n")
    assert "USS-TJR-MSN-0002" in text


# --- memory adapter (consumer compatibility) -------------------------------

def test_memory_adapter_reads_override_file(monkeypatch, tmp_path):
    external = tmp_path / "mission-index.txt"
    external.write_text("- USS-TJR-MSN-9999 | probe line\n", encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(external))
    from core.coordination.mission_registry_memory_adapter import (
        MissionRegistryMemoryAdapter,
    )

    rows = MissionRegistryMemoryAdapter()._load_from_files()
    assert any("USS-TJR-MSN-9999" in row["mission_id"] or "USS-TJR-MSN-9999" in row["title"] for row in rows)


def test_memory_adapter_tolerates_missing_override(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "absent.txt"))
    from core.coordination.mission_registry_memory_adapter import (
        MissionRegistryMemoryAdapter,
    )

    rows = MissionRegistryMemoryAdapter()._load_from_files()
    assert isinstance(rows, list)


# --- guard: no consumer rebuilds the tracked path ---------------------------

CONSUMERS = [
    "core/coordination/number_one_exporter.py",
    "core/coordination/mission_registry_memory_adapter.py",
    "platform-runtime/commands/mission_brief.py",
    "tools/sync_supabase_to_registry.py",
]
HARDCODED = re.compile(r'"registry"\s*/\s*"mission-index\.txt"|core/mission-control/registry/mission-index\.txt"')


@pytest.mark.parametrize("rel", CONSUMERS)
def test_consumer_does_not_hardcode_registry_path(rel):
    source = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "registry_path" in source, f"{rel} must use the resolver"
    assert not HARDCODED.search(source), f"{rel} still builds the tracked registry path by hand"
