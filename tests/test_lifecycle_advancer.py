#!/usr/bin/env python3
"""Tests for MSN-0066 Increment 6 — Lifecycle Advancer (write-side, gate-stop).

Injects a synthetic triage report and writes the overlay to a TEMP dir, so no
live data, Supabase, GLM or the real ledger is touched. Runnable under pytest or
directly: `python3 tests/test_lifecycle_advancer.py` from the repo root.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.coordination import lifecycle_advancer as la


def _report(*pkgs):
    return {"generated_at": "2026-06-18T00:00:00Z", "count": len(pkgs), "packages": list(pkgs)}


def _pkg(_id, title="x", band="Moderate", prio="P2", dup=False, kind="build_request"):
    return {"id": _id, "title": title, "kind": kind,
            "risk": {"score": 40, "band": band, "reasons": []},
            "suggested_priority": prio, "is_likely_duplicate": dup}


def test_dry_run_writes_nothing():
    with tempfile.TemporaryDirectory() as d:
        rep = la.advance(_report(_pkg("BREQ-1")), apply=False, ledger_dir=Path(d))
        assert rep["advanced"] == 1
        assert rep["results"][0]["action"] == "would_advance"
        assert la.load_ledger(Path(d)) == {}             # nothing persisted


def test_apply_records_triage_ready():
    with tempfile.TemporaryDirectory() as d:
        rep = la.advance(_report(_pkg("BREQ-1", title="Add auth")), apply=True, ledger_dir=Path(d))
        assert rep["advanced"] == 1
        ledger = la.load_ledger(Path(d))
        assert "BREQ-1" in ledger
        assert ledger["BREQ-1"]["stage"] == la.TRIAGE_READY
        assert ledger["BREQ-1"]["suggested_priority"] == "P2"
        # an audit record was written alongside (transitions sibling dir)
        audits = list((Path(d).parent / "transitions").glob("TRIAGE-READY-ADVANCE-*.json"))
        assert len(audits) == 1


def test_idempotent_no_double_advance():
    with tempfile.TemporaryDirectory() as d:
        la.advance(_report(_pkg("BREQ-1")), apply=True, ledger_dir=Path(d))
        rep2 = la.advance(_report(_pkg("BREQ-1")), apply=True, ledger_dir=Path(d))
        assert rep2["advanced"] == 0
        assert rep2["already_ready"] == 1
        assert len(la.load_ledger(Path(d))) == 1


def test_never_writes_a_forbidden_post_gate_stage():
    # The target is pinned to Triage Ready and guarded against the forbidden set.
    assert la.TRIAGE_READY not in la._FORBIDDEN_TARGETS
    with tempfile.TemporaryDirectory() as d:
        la.advance(_report(_pkg("BREQ-1")), apply=True, ledger_dir=Path(d))
        entry = la.load_ledger(Path(d))["BREQ-1"]
        assert entry["stage"] == la.TRIAGE_READY
        assert entry["stage"] not in la._FORBIDDEN_TARGETS
        # crucially, it never records an "approved" state — approval stays human
        assert all(v["stage"] != "approved" for v in la.load_ledger(Path(d)).values())


def test_list_triage_ready_reflects_overlay():
    with tempfile.TemporaryDirectory() as d:
        assert la.list_triage_ready(Path(d)) == []
        la.advance(_report(_pkg("BREQ-1"), _pkg("BREQ-2")), apply=True, ledger_dir=Path(d))
        ids = {e["id"] for e in la.list_triage_ready(Path(d))}
        assert ids == {"BREQ-1", "BREQ-2"}


def test_empty_report_advances_nothing():
    with tempfile.TemporaryDirectory() as d:
        rep = la.advance(_report(), apply=True, ledger_dir=Path(d))
        assert rep["advanced"] == 0
        assert la.load_ledger(Path(d)) == {}


def test_format_distinguishes_dry_run_and_apply():
    with tempfile.TemporaryDirectory() as d:
        dry = la.advance(_report(_pkg("BREQ-1")), apply=False, ledger_dir=Path(d))
        assert "dry-run" in la.format_advance(dry)
        assert "Would advance" in la.format_advance(dry)
        applied = la.advance(_report(_pkg("BREQ-1")), apply=True, ledger_dir=Path(d))
        assert "Advanced" in la.format_advance(applied)
        assert "NOT approved" in la.format_advance(applied)


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
