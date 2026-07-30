#!/usr/bin/env python3
"""Tests for MSN-0066 Increment 7 — Lifecycle Coverage sweep ("nothing gets lost").

Synthetic ledger + injected advancer; no live data/writes. Runnable under pytest
or directly: `python3 tests/test_lifecycle_coverage.py` from the repo root.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.coordination.lifecycle_coverage import build_coverage, format_coverage, sweep


def _ledger(*items):
    return {"items": list(items), "actions_taken": [], "github_error": "",
            "supabase_ok": True, "applied": False}


def _item(kind, _id, claimed, bucket, title=""):
    return {"kind": kind, "id": _id, "title": title, "claimed": claimed, "bucket": bucket}


def test_every_classifiable_item_is_assigned_a_stage():
    cov = build_coverage(_ledger(
        _item("mission", "M-1", "Closed", "DELIVERED"),            # Closed
        _item("build_request", "BREQ-1", "pending_triage", "AWAITING_APPROVAL"),  # Capture
        _item("handoff", "ENG-1", "DELIVERED", "AWAITING_REVIEW"),  # Review
    ))
    assert cov["total_items"] == 3
    assert cov["classified"] == 3
    assert cov["fully_covered"] is True
    assert cov["stage_counts"]["Closed"] == 1
    assert cov["stage_counts"]["Capture"] == 1
    assert cov["stage_counts"]["Review"] == 1


def test_unclassifiable_item_is_flagged_not_lost():
    cov = build_coverage(_ledger(
        _item("mission", "M-OK", "Closed", "DELIVERED"),
        _item("mission", "M-LOST", "Frobnicated", "WEIRD_BUCKET"),   # nothing maps this
    ))
    assert cov["fully_covered"] is False
    lost_ids = [u["id"] for u in cov["unclassified"]]
    assert lost_ids == ["M-LOST"]
    assert cov["classified"] == 1
    assert "UNCLASSIFIED" in format_coverage(cov)


def test_kind_breakdown_covers_missions_and_build_requests():
    cov = build_coverage(_ledger(
        _item("mission", "M-1", "Idea", "AWAITING_APPROVAL"),         # Capture (mission)
        _item("build_request", "BREQ-1", "pending_triage", "AWAITING_APPROVAL"),  # Capture (BREQ)
    ))
    assert cov["kind_counts"] == {"mission": 1, "build_request": 1}
    assert cov["kind_by_stage"]["Capture"] == {"mission": 1, "build_request": 1}


def test_fully_covered_message_when_clean():
    cov = build_coverage(_ledger(_item("mission", "M-1", "Closed", "DELIVERED")))
    assert "nothing is lost" in format_coverage(cov)


class _FakeAdvancer:
    def __init__(self):
        self.called_apply = None
    def advance(self, apply=False):
        self.called_apply = apply
        return {"advanced": 2 if apply else 0, "already_ready": 0, "results": []}


def test_sweep_classifies_and_advances_capture_items():
    fake = _FakeAdvancer()
    rep = sweep(_ledger(
        _item("mission", "M-1", "Idea", "AWAITING_APPROVAL"),
        _item("build_request", "BREQ-1", "pending_triage", "AWAITING_APPROVAL"),
    ), apply=True, advancer=fake)
    assert rep["apply"] is True
    assert fake.called_apply is True                  # advancement was triggered
    assert rep["advance"]["advanced"] == 2
    assert rep["coverage"]["stage_counts"]["Capture"] == 2
    out = format_coverage(rep)
    assert "advanced 2 enriched Capture" in out


def test_sweep_dry_run_does_not_apply():
    fake = _FakeAdvancer()
    rep = sweep(_ledger(_item("build_request", "BREQ-1", "pending_triage", "AWAITING_APPROVAL")),
                apply=False, advancer=fake)
    assert fake.called_apply is False
    assert "would advance" in format_coverage(rep)


def test_empty_ledger_is_fully_covered():
    cov = build_coverage(_ledger())
    assert cov["total_items"] == 0
    assert cov["fully_covered"] is True


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
