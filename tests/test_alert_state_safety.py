"""Tests for the shared alert-state file: locking, atomic replacement, cooldown.

Every test redirects the module's state path into a temporary directory. The
production path is asserted untouched, so these tests can never write the real
cooldown state.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import stat
import sys
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import alert_on_systemd_failure as aosf

PRODUCTION_STATE = Path("/opt/starship-endeavour/data/alert_state/last_alert.json")


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    state = tmp_path / "alert_state" / "last_alert.json"
    monkeypatch.setattr(aosf, "_STATE_PATH", state)
    assert state != PRODUCTION_STATE
    return state


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


def _worker(start: int, count: int) -> None:
    for j in range(count):
        aosf._record_alert(f"worker-{start}-unit-{j}")


class TestCooldown:
    def test_recorded_unit_is_in_cooldown(self, isolated_state):
        aosf._record_alert("auto-deploy.service")
        assert aosf._cooldown_active("auto-deploy.service") is True

    def test_unrecorded_unit_is_not_in_cooldown(self, isolated_state):
        aosf._record_alert("auto-deploy.service")
        assert aosf._cooldown_active("some-other.service") is False

    def test_expired_entry_is_not_in_cooldown(self, isolated_state):
        isolated_state.parent.mkdir(parents=True, exist_ok=True)
        expired = time.time() - aosf.ALERT_COOLDOWN_SECONDS - 10
        isolated_state.write_text(json.dumps({"auto-deploy.service": expired}))
        assert aosf._cooldown_active("auto-deploy.service") is False

    def test_no_state_file_means_no_cooldown(self, isolated_state):
        assert not isolated_state.exists()
        assert aosf._cooldown_active("auto-deploy.service") is False


class TestReadModifyWrite:
    def test_other_entries_are_preserved_exactly(self, isolated_state):
        isolated_state.parent.mkdir(parents=True, exist_ok=True)
        seeded = {"self-improving-system.service": 1700000000.5, "daily-ops-cycle.service": 1699999999.25}
        isolated_state.write_text(json.dumps(seeded))
        aosf._record_alert("auto-deploy.service")
        after = _read(isolated_state)
        assert {k: after[k] for k in seeded} == seeded
        assert "auto-deploy.service" in after and len(after) == 3

    def test_corrupt_existing_state_is_replaced_with_valid_json(self, isolated_state):
        isolated_state.parent.mkdir(parents=True, exist_ok=True)
        isolated_state.write_text("{not json")
        aosf._record_alert("auto-deploy.service")
        assert list(_read(isolated_state)) == ["auto-deploy.service"]


class TestAtomicReplacement:
    def test_failed_replace_leaves_previous_file_intact_and_no_temp_files(self, isolated_state, monkeypatch):
        isolated_state.parent.mkdir(parents=True, exist_ok=True)
        isolated_state.write_text(json.dumps({"keep.service": 1.0}))
        before = isolated_state.read_bytes()

        def boom(src, dst):
            raise OSError("simulated crash during rename")

        monkeypatch.setattr(aosf.os, "replace", boom)
        aosf._record_alert("auto-deploy.service")  # must not raise; error is reported
        assert isolated_state.read_bytes() == before
        leftovers = [p.name for p in isolated_state.parent.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []

    def test_mode_is_preserved_on_replace(self, isolated_state):
        isolated_state.parent.mkdir(parents=True, exist_ok=True)
        isolated_state.write_text("{}")
        os.chmod(isolated_state, 0o640)
        aosf._record_alert("auto-deploy.service")
        assert stat.S_IMODE(os.stat(isolated_state).st_mode) == 0o640

    def test_new_file_gets_group_writable_default_mode(self, isolated_state):
        aosf._record_alert("auto-deploy.service")
        assert stat.S_IMODE(os.stat(isolated_state).st_mode) == aosf._DEFAULT_STATE_MODE

    def test_ownership_is_preserved_when_it_can_be(self, isolated_state):
        isolated_state.parent.mkdir(parents=True, exist_ok=True)
        isolated_state.write_text("{}")
        before = os.stat(isolated_state)
        aosf._record_alert("auto-deploy.service")
        after = os.stat(isolated_state)
        assert (after.st_uid, after.st_gid) == (before.st_uid, before.st_gid)


class TestLocking:
    def test_lock_file_is_a_stable_sibling_and_never_replaced(self, isolated_state):
        lock = aosf._lock_path()
        assert lock.parent == isolated_state.parent and lock.name == "last_alert.lock"
        aosf._record_alert("a.service")
        inode_first = os.stat(lock).st_ino
        aosf._record_alert("b.service")
        assert os.stat(lock).st_ino == inode_first

    def test_concurrent_writers_lose_no_updates(self, isolated_state):
        ctx = multiprocessing.get_context("fork")
        workers = [ctx.Process(target=_worker, args=(w, 25)) for w in range(8)]
        for w in workers:
            w.start()
        for w in workers:
            w.join(timeout=120)
            assert w.exitcode == 0
        state = _read(isolated_state)  # valid JSON after concurrent replacement
        expected = {f"worker-{w}-unit-{j}" for w in range(8) for j in range(25)}
        assert expected <= set(state), f"lost {len(expected - set(state))} updates"


class TestTestIsolation:
    def test_production_state_is_never_written(self, isolated_state):
        def fingerprint(path: Path):
            if not path.exists():
                return None
            st = os.stat(path)
            return (st.st_mtime_ns, st.st_size)

        before = fingerprint(PRODUCTION_STATE)
        aosf._record_alert("isolation-check.service")
        aosf._cooldown_active("isolation-check.service")
        assert fingerprint(PRODUCTION_STATE) == before
        assert isolated_state.exists()


class TestLockFailureDoesNotDropAlerts:
    def test_unopenable_lock_still_records_the_alert(self, isolated_state, capsys):
        lock = aosf._lock_path()
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.mkdir()  # a directory cannot be opened as the lock file
        aosf._record_alert("auto-deploy.service")
        assert "auto-deploy.service" in _read(isolated_state)
        assert "proceeding unlocked" in capsys.readouterr().err
