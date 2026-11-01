"""2026-10-08 HQ Status regression: the Sunday auto-curation run (--limit 100)
hit the scheduler's 900s subprocess timeout on 2026-09-19 and 2026-09-26 with
zero signals applied, and the scheduler recorded it as a
health_osint_weekly_fetch failure (Health Intelligence "unavailable"). The
script now stops cleanly on a wall-clock budget, bails out of a hung
provider call, and skips signals the model already escalated.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "tools" / "health-osint"))

import health_signal_curation as hsc


def _signals(n):
    return [{"signal_id": f"s{i}", "title": f"Distinct title {i}", "source_id": "src"} for i in range(n)]


def _curator(pending, time_budget=None):
    c = hsc.HealthSignalCurator(dry_run=True, time_budget=time_budget)
    c.dry_run = False  # bypass the dry-run early return without a Supabase client
    c._pending = lambda: pending
    c._apply = mock.Mock()
    return c


_ESCALATE = {"decision": "ESCALATE", "reason": "r", "mission_relevance": "RELEVANT",
             "evidence_contribution": None, "population_fit": None, "safety_relevance": False}


def test_time_budget_stops_cleanly_with_partial_counts():
    clock = iter(range(0, 10_000, 100))  # each monotonic() call advances 100s
    with mock.patch.object(hsc, "_classify", return_value=_ESCALATE), \
         mock.patch.object(hsc.time, "monotonic", side_effect=lambda: next(clock)):
        result = _curator(_signals(10), time_budget=780).run()
    assert 0 < result["total"] < 10
    assert result["fetched"] == 10
    assert "time budget" in result["stopped_reason"]


def test_no_budget_processes_everything():
    with mock.patch.object(hsc, "_classify", return_value=_ESCALATE):
        c = _curator(_signals(5))
        result = c.run()
    assert result["total"] == 5
    assert result["stopped_reason"] is None
    assert c._apply.call_count == 5


def test_hung_classify_raises_instead_of_blocking():
    import threading
    release = threading.Event()

    def hang(_signal):
        release.wait(5)
        return _ESCALATE

    with mock.patch.object(hsc, "_classify", side_effect=hang), pytest.raises(hsc.ClassifyHung):
        hsc._classify_with_deadline({"signal_id": "x"}, 0.05)
    release.set()


def test_pending_query_skips_already_escalated():
    q = mock.MagicMock()
    for m in ("table", "select", "eq", "is_", "order", "limit"):
        getattr(q, m).return_value = q
    q.execute.return_value.data = []
    c = hsc.HealthSignalCurator(dry_run=True)
    c.supabase = q
    c._pending()
    q.is_.assert_called_once_with("mission_relevance", "null")
