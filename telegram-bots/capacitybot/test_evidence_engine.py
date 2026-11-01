#!/usr/bin/env python3
"""
Tests for evidence_engine.py — personal causal-effect estimator.

Covers the pandas/tfcausalimpact-free layers directly: _prepare_window's
sufficiency checks, EvidenceEstimate's derived properties, day-aggregation
via a mocked Supabase client, and compute_and_write/run_all's
write-payload shape and dry-run behaviour. _fit_causal_impact (the one
function that needs the real tfcausalimpact/pandas dependency, not
installable in the authoring sandbox — see the module docstring) is
exercised only via monkeypatching compute_estimate's call into it, never
by loading the real library.

Same check()/main() style as the other capacitybot test files.

Run from repo root:
    python telegram-bots/capacitybot/test_evidence_engine.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parents[2]))

from telegram_bots.capacitybot import evidence_engine as ee

PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, str]] = []


def check(label: str, condition: bool) -> bool:
    tag = PASS if condition else FAIL
    _results.append((tag, label))
    print(f"  [{tag}] {label}")
    return condition


# ── _prepare_window — pure function, no DB, no pandas ────────────────────────

def test_window_none_when_pre_days_short():
    onset = date(2026, 6, 1)
    series = {onset + timedelta(days=i): 70.0 for i in range(15)}  # only post-onset data
    window = ee._prepare_window(series, onset, today=onset + timedelta(days=20))
    check("insufficient pre-period data returns None", window is None)


def test_window_none_when_post_days_short():
    onset = date(2026, 6, 1)
    series = {onset - timedelta(days=i): 70.0 for i in range(1, 15)}  # only pre-onset data
    window = ee._prepare_window(series, onset, today=onset + timedelta(days=2))
    check("insufficient post-period data returns None", window is None)


def test_window_ok_with_enough_both_sides():
    onset = date(2026, 6, 1)
    series = {}
    for i in range(1, 15):
        series[onset - timedelta(days=i)] = 70.0
    for i in range(15):
        series[onset + timedelta(days=i)] = 70.0
    window = ee._prepare_window(series, onset, today=onset + timedelta(days=20))
    check("sufficient both sides returns a Window", window is not None)
    if window is not None:
        check("pre_days counted correctly", window.pre_days == 14)
        check("post_days counted correctly", window.post_days == 15)


def test_window_none_when_onset_in_future():
    onset = date(2026, 6, 10)
    window = ee._prepare_window({}, onset, today=date(2026, 6, 1))
    check("onset after 'today' returns None", window is None)


def test_window_ignores_none_values_in_series():
    onset = date(2026, 6, 1)
    # 20 pre-onset days present in the dict, but only 5 carry a real value —
    # below min_pre_days=10 even though the *key* coverage looks sufficient.
    series = {
        onset - timedelta(days=i): (70.0 if i <= 5 else None)
        for i in range(1, 21)
    }
    for i in range(15):
        series[onset + timedelta(days=i)] = 70.0
    window = ee._prepare_window(series, onset, today=onset + timedelta(days=20), min_pre_days=10)
    check("None-valued days are not counted as coverage", window is None)


# ── EvidenceEstimate — derived properties ────────────────────────────────────

def _estimate(**overrides) -> ee.EvidenceEstimate:
    base = {
        "intervention_id": "rest_20",
        "onset": date(2026, 6, 1),
        "pre_days": 14,
        "post_days": 14,
        "effect": 8.5,
        "ci_lower": 2.0,
        "ci_upper": 15.0,
        "p_value": 0.01,
    }
    base.update(overrides)
    return ee.EvidenceEstimate(**base)


def test_significant_true_when_ci_excludes_zero_positive():
    check("positive CI excluding zero is significant", _estimate(ci_lower=2.0, ci_upper=15.0).significant)


def test_significant_true_when_ci_excludes_zero_negative():
    check("negative CI excluding zero is significant", _estimate(ci_lower=-15.0, ci_upper=-2.0).significant)


def test_significant_false_when_ci_includes_zero():
    check("CI spanning zero is not significant", not _estimate(ci_lower=-3.0, ci_upper=5.0).significant)


def test_summary_text_mentions_direction_and_caveat():
    sig_text = _estimate(ci_lower=2.0, ci_upper=15.0).summary_text()
    check("significant summary omits 'not significant'", "not significant" not in sig_text)
    check("summary mentions observational caveat", "Observational" in sig_text)

    nonsig_text = _estimate(ci_lower=-3.0, ci_upper=5.0).summary_text()
    check("non-significant summary flags it", "not significant" in nonsig_text)


def test_to_payload_shape():
    payload = _estimate().to_payload(computed_at="2026-06-15T00:00:00+00:00")
    check("payload has effect column", payload[ee.EFFECT_COLUMN] == 8.5)
    check("payload has ci_lower column", payload[ee.CI_LOWER_COLUMN] == 2.0)
    check("payload has ci_upper column", payload[ee.CI_UPPER_COLUMN] == 15.0)
    check("payload has p_value column", payload[ee.P_VALUE_COLUMN] == 0.01)
    check("payload has summary text", isinstance(payload[ee.SUMMARY_COLUMN], str) and len(payload[ee.SUMMARY_COLUMN]) > 0)
    check("payload has computed_at", payload[ee.COMPUTED_AT_COLUMN] == "2026-06-15T00:00:00+00:00")
    check("payload never touches evidence_strength", "evidence_strength" not in payload)
    check("payload never touches evidence_basis", "evidence_basis" not in payload)


# ── compute_estimate orchestration — _fit_causal_impact monkeypatched ────────

def test_compute_estimate_returns_none_below_threshold():
    onset = date(2026, 6, 1)
    series = {onset + timedelta(days=i): 70.0 for i in range(3)}  # far too little data
    result = ee.compute_estimate("rest_20", series, onset, today=onset + timedelta(days=5))
    check("compute_estimate returns None when window insufficient", result is None)


def test_compute_estimate_builds_estimate_from_fit(monkeypatch):
    onset = date(2026, 6, 1)
    series = {}
    for i in range(1, 15):
        series[onset - timedelta(days=i)] = 60.0
    for i in range(15):
        series[onset + timedelta(days=i)] = 75.0

    monkeypatch.setattr(ee, "_fit_causal_impact", lambda series, window: (12.3, 4.0, 20.0, 0.02))
    result = ee.compute_estimate("rest_20", series, onset, today=onset + timedelta(days=20))
    check("compute_estimate returns an EvidenceEstimate", isinstance(result, ee.EvidenceEstimate))
    if result:
        check("effect passed through from fit", result.effect == 12.3)
        check("pre_days/post_days come from the window, not the fit", result.pre_days == 14 and result.post_days == 15)


def test_compute_estimate_none_when_fit_fails(monkeypatch):
    onset = date(2026, 6, 1)
    series = {}
    for i in range(1, 15):
        series[onset - timedelta(days=i)] = 60.0
    for i in range(15):
        series[onset + timedelta(days=i)] = 75.0

    monkeypatch.setattr(ee, "_fit_causal_impact", lambda series, window: None)
    result = ee.compute_estimate("rest_20", series, onset, today=onset + timedelta(days=20))
    check("compute_estimate propagates a fit failure as None", result is None)


# ── _fetch_daily_series — mocked Supabase client ─────────────────────────────

def _mock_checkins_response(rows: list[dict]):
    db = MagicMock()
    execute_result = MagicMock()
    execute_result.data = rows
    db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = execute_result
    return db


def test_fetch_daily_series_averages_multiple_checkins_per_day():
    rows = [
        {"log_date": "2026-06-01", "capacity_state": "green"},   # 90
        {"log_date": "2026-06-01", "capacity_state": "orange"},  # 60
        {"log_date": "2026-06-02", "capacity_state": "red"},     # 25
    ]
    db = _mock_checkins_response(rows)
    series = asyncio.run(ee._fetch_daily_series(db, date(2026, 6, 1), date(2026, 6, 2)))
    check("day with two checkins is averaged", series[date(2026, 6, 1)] == 75.0)
    check("day with one checkin uses that value", series[date(2026, 6, 2)] == 25.0)


def test_fetch_daily_series_skips_rows_without_capacity_state():
    rows = [{"log_date": "2026-06-01", "capacity_state": None}]
    db = _mock_checkins_response(rows)
    series = asyncio.run(ee._fetch_daily_series(db, date(2026, 6, 1), date(2026, 6, 1)))
    check("row with no capacity_state contributes nothing", series == {})


def test_fetch_daily_series_empty_without_db():
    series = asyncio.run(ee._fetch_daily_series(None, date(2026, 6, 1), date(2026, 6, 1)))
    check("no db configured returns empty series, not an error", series == {})


# ── compute_and_write / run_all — mocked db, monkeypatched compute_estimate ──

def _mock_db_for_pipeline(onset_iso: str | None, interventions: list[str]):
    db = MagicMock()

    def table(name):
        m = MagicMock()
        if name == "capacity_intervention_events":
            rows = [{"started_at": onset_iso}] if onset_iso else []
            m.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = rows
        elif name == ee.CHECKINS_TABLE:
            m.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value.data = []
        elif name == ee.INTERVENTIONS_TABLE:
            m.select.return_value.eq.return_value.execute.return_value.data = [
                {"intervention_id": iid} for iid in interventions
            ]
        return m

    db.table.side_effect = table
    return db


def test_compute_and_write_dry_run_does_not_call_update(monkeypatch):
    db = _mock_db_for_pipeline("2026-06-01T00:00:00+00:00", [])
    monkeypatch.setattr(ee, "compute_estimate", lambda *a, **k: _estimate())
    result = asyncio.run(ee.compute_and_write(db, "rest_20", dry_run=True))
    check("dry_run still returns an estimate", result is not None)
    events_table_calls = [c for c in db.table.call_args_list if c.args and c.args[0] == ee.INTERVENTIONS_TABLE]
    check("dry_run never opens the interventions table for writing", len(events_table_calls) == 0)


def test_compute_and_write_none_when_never_tried():
    db = _mock_db_for_pipeline(None, [])
    result = asyncio.run(ee.compute_and_write(db, "never_tried_action"))
    check("no events at all returns None, writes nothing", result is None)


def test_run_all_counts_only_successful_estimates(monkeypatch):
    db = _mock_db_for_pipeline("2026-06-01T00:00:00+00:00", ["a", "b", "c"])

    async def fake_compute_and_write(db, intervention_id, dry_run=False, **kw):
        return _estimate(intervention_id=intervention_id) if intervention_id != "b" else None

    monkeypatch.setattr(ee, "compute_and_write", fake_compute_and_write)
    results = asyncio.run(ee.run_all(db, dry_run=True))
    check("run_all returns one estimate per successful intervention", len(results) == 2)
    check("run_all skips interventions with no estimate", all(r.intervention_id != "b" for r in results))


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    import inspect

    tests = [
        (name, obj) for name, obj in sorted(globals().items())
        if name.startswith("test_") and inspect.isfunction(obj)
    ]
    for name, fn in tests:
        print(f"\n{name}")
        sig = inspect.signature(fn)
        if "monkeypatch" in sig.parameters:
            mp = _SimpleMonkeypatch()
            try:
                fn(mp)
            finally:
                mp.undo()
        else:
            fn()

    failed = [label for tag, label in _results if tag == FAIL]
    print(f"\n{len(_results) - len(failed)}/{len(_results)} checks passed")
    if failed:
        print("FAILED:")
        for label in failed:
            print(f"  - {label}")
        return 1
    return 0


class _SimpleMonkeypatch:
    """Minimal stand-in for pytest's monkeypatch fixture so these tests run
    unmodified under either `pytest` or `python3 test_evidence_engine.py`."""

    def __init__(self):
        self._restores: list[tuple[object, str, object]] = []

    def setattr(self, obj, name: str, value) -> None:
        self._restores.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self) -> None:
        for obj, name, old in reversed(self._restores):
            setattr(obj, name, old)


if __name__ == "__main__":
    raise SystemExit(main())
