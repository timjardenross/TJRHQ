"""Migration 0261: a decided build request cannot be flipped approved<->rejected.

Runs the real migration file against a throwaway local Postgres (the same
approach as tests/test_supabase_ro_access.py: a temporary cluster on a unix
socket). Skipped when no local Postgres binaries are available.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parent.parent / "core/infrastructure/supabase/migrations/0261_build_request_decision_integrity.sql"


def _pg_bin() -> str | None:
    for d in sorted(glob.glob("/usr/lib/postgresql/*/bin"), reverse=True):
        if os.path.exists(os.path.join(d, "initdb")):
            return d
    which = shutil.which("initdb")
    return os.path.dirname(which) if which else None


@pytest.fixture(scope="module")
def pg():
    b = _pg_bin()
    psql = shutil.which("psql")
    if not b or not psql:
        pytest.skip("local Postgres binaries not available")
    root = tempfile.mkdtemp(prefix="brd-guard-")
    sock = os.path.join(root, "sock")
    os.makedirs(sock)
    prefix: list[str] = []
    if os.geteuid() == 0:
        os.chmod(root, 0o777)
        os.chmod(sock, 0o777)
        prefix = ["runuser", "-u", "postgres", "--"]
    port = str(54700 + os.getpid() % 200)
    data = os.path.join(root, "data")
    subprocess.run(prefix + [os.path.join(b, "initdb"), "-D", data, "-A", "trust", "-U", "owner_admin"], check=True, capture_output=True)
    subprocess.run(prefix + [os.path.join(b, "pg_ctl"), "-D", data, "-o", f"-p {port} -k {sock} -c listen_addresses=''", "-w", "-l", os.path.join(root, "log"), "start"], check=True, capture_output=True)

    def run(sql: str, check: bool = True):
        r = subprocess.run([psql, "-h", sock, "-p", port, "-U", "owner_admin", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-At", "-c", sql], capture_output=True, text=True)
        if check and r.returncode != 0:
            raise AssertionError(r.stderr)
        return r

    run("create table public.build_request_inbox (id uuid primary key default gen_random_uuid(), request_id text not null unique, title text not null, status text not null default 'pending_triage', action_type text, action_result jsonb, record_path text)")
    r = subprocess.run([psql, "-h", sock, "-p", port, "-U", "owner_admin", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-f", str(MIGRATION)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    yield run
    subprocess.run(prefix + [os.path.join(b, "pg_ctl"), "-D", data, "-m", "immediate", "stop"], capture_output=True)
    shutil.rmtree(root, ignore_errors=True)


def _row(run, rid: str, status: str):
    run(f"insert into public.build_request_inbox (request_id, title, status) values ('{rid}', 't', '{status}')")


def _set(run, rid: str, status: str):
    return run(f"update public.build_request_inbox set status = '{status}' where request_id = '{rid}'", check=False)


def _status(run, rid: str) -> str:
    return run(f"select status from public.build_request_inbox where request_id = '{rid}'").stdout.strip()


def test_approved_cannot_be_flipped_to_rejected(pg):
    _row(pg, "a1", "approved")
    r = _set(pg, "a1", "rejected")
    assert r.returncode != 0 and "cannot be changed from approved to rejected" in r.stderr
    assert _status(pg, "a1") == "approved"


def test_rejected_cannot_be_flipped_to_approved(pg):
    _row(pg, "a2", "rejected")
    assert _set(pg, "a2", "approved").returncode != 0
    assert _status(pg, "a2") == "rejected"


def test_case_insensitive(pg):
    _row(pg, "a3", "Approved")
    assert _set(pg, "a3", "REJECTED").returncode != 0


@pytest.mark.parametrize("start,end", [
    ("awaiting_review", "approved"), ("awaiting_review", "rejected"),
    ("pending_triage", "approved"), ("PENDING_TRIAGE", "rejected"),
    ("approved", "awaiting_review"),            # Undo
    ("approved", "in_progress"), ("approved", "completed"),   # engineering lifecycle
    ("rejected", "awaiting_review"),            # reopen, then decide again
])
def test_valid_transitions_still_work(pg, start, end):
    rid = f"v-{start}-{end}"
    _row(pg, rid, start)
    r = _set(pg, rid, end)
    assert r.returncode == 0, r.stderr
    assert _status(pg, rid) == end


def test_undo_then_decide_again_is_the_supported_way_to_change_a_decision(pg):
    _row(pg, "u1", "approved")
    assert _set(pg, "u1", "awaiting_review").returncode == 0
    assert _set(pg, "u1", "rejected").returncode == 0


def test_updates_that_leave_status_alone_are_unaffected(pg):
    _row(pg, "n1", "approved")
    r = pg("update public.build_request_inbox set action_result = '{\"success\": true}', record_path = '/x' where request_id = 'n1'", check=False)
    assert r.returncode == 0, r.stderr
    # re-asserting the same status is also fine
    assert _set(pg, "n1", "approved").returncode == 0


def test_inserts_are_unaffected(pg):
    _row(pg, "i1", "rejected")
    _row(pg, "i2", "approved")
