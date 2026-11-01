"""2026-10-08 HQ Status regression: a health_signal_curation.py timeout was
recorded as a health_osint_weekly_fetch failure (the fetch had already
succeeded), which HQ Status maps to Health Discovery and reports Health
Intelligence as "unavailable". Curation failures must only ever heartbeat
health_osint_auto_curation.
"""
from __future__ import annotations

import subprocess
from unittest import mock

import intelligence.scheduler as sched


def _ok():
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")


def test_curation_timeout_does_not_fail_the_fetch_heartbeat():
    calls = [_ok(), subprocess.TimeoutExpired(cmd="curation", timeout=900)]

    def fake_run(*_a, **_k):
        r = calls.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    with mock.patch("subprocess.run", side_effect=fake_run), \
         mock.patch.object(sched, "_record_heartbeat") as hb:
        sched._health_osint_weekly_fetch_job()

    recorded = [(c.args[0], c.args[1]) for c in hb.call_args_list]
    assert ("health_osint_weekly_fetch", "ok") in recorded
    assert ("health_osint_auto_curation", "failed") in recorded
    assert ("health_osint_weekly_fetch", "failed") not in recorded


def test_curation_is_invoked_with_a_time_budget_under_the_hard_timeout():
    with mock.patch("subprocess.run", return_value=_ok()) as run, \
         mock.patch.object(sched, "_record_heartbeat"):
        sched._health_osint_weekly_fetch_job()
    cmd = run.call_args_list[1].args[0]
    budget = float(cmd[cmd.index("--time-budget") + 1])
    assert budget < run.call_args_list[1].kwargs["timeout"]
