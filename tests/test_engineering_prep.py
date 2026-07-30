#!/usr/bin/env python3
"""Tests for MSN-0066 Increment 4 — Ready-for-engineering prep + linkage (AP3/AP4).

Injects a SYNTHETIC ledger and a FAKE planner, so no GLM/network is touched.
Build-stage handoffs come from the reconciler's `items_at_stage`, which depends
on the delivery bucket — so the synthetic items carry IN_PROGRESS (→ Build).
Runnable under pytest or directly: `python3 tests/test_engineering_prep.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.coordination.engineering_prep import (
    build_prep_packages,
    format_prep_packages,
)
from core.coordination.lifecycle_status_map import LifecycleStage


def _ledger(*items):
    return {"items": list(items), "actions_taken": [], "github_error": "",
            "supabase_ok": True, "applied": False}


def _handoff(_id, claimed="PENDING", bucket="IN_PROGRESS", title="", evidence="pending"):
    # A pending handoff → delivery bucket IN_PROGRESS → Build stage.
    return {"kind": "handoff", "id": _id, "title": title, "claimed": claimed,
            "bucket": bucket, "evidence": evidence}


def test_build_stage_handoffs_get_prep_packages():
    rep = build_prep_packages(
        _ledger(_handoff("ENG-1", title="Add cache")),
        plan_fn=lambda title, ctx: "1. IMPLEMENTATION PLAN\n- step")
    assert rep["count"] == 1
    p = rep["packages"][0]
    assert p["stage"] == LifecycleStage.BUILD.value
    assert p["prep_available"] is True
    assert "IMPLEMENTATION PLAN" in p["prep_advisory"]


def test_non_build_items_are_ignored():
    review = {"kind": "handoff", "id": "ENG-R", "title": "", "claimed": "DELIVERED",
              "bucket": "AWAITING_REVIEW", "evidence": "PR draft"}    # → Review
    mission = {"kind": "mission", "id": "M-1", "title": "", "claimed": "Implemented",
               "bucket": "ASSIGNED", "evidence": "no PR"}             # Build but not a handoff
    rep = build_prep_packages(_ledger(review, mission), plan_fn=lambda t, c: "x")
    assert rep["count"] == 0


def test_plan_unavailable_degrades_gracefully():
    rep = build_prep_packages(_ledger(_handoff("ENG-2")), plan_fn=lambda t, c: None)
    assert rep["packages"][0]["prep_available"] is False
    assert "plan unavailable" in format_prep_packages(rep)


def test_planning_can_be_skipped():
    rep = build_prep_packages(_ledger(_handoff("ENG-3")), plan_fn=None)
    assert rep["packages"][0]["prep_available"] is False


def test_linkage_gap_surfaced_for_orphan_handoff():
    # No handoff file on disk for a synthetic id → mission_id blank → linkage gap.
    rep = build_prep_packages(_ledger(_handoff("ENG-ORPHAN")), plan_fn=None)
    p = rep["packages"][0]
    assert p["linkage"]["linked"] is False
    assert rep["linkage_gaps"] == 1
    assert "not linked" in p["linkage"]["gap"]
    assert "linkage gap" in format_prep_packages(rep)


def test_empty_ledger_is_clean():
    rep = build_prep_packages(_ledger(), plan_fn=None)
    assert rep["count"] == 0
    assert "no approved-pending handoffs" in format_prep_packages(rep)


def test_packages_sorted_by_id():
    rep = build_prep_packages(
        _ledger(_handoff("ENG-Z"), _handoff("ENG-A")), plan_fn=None)
    assert [p["id"] for p in rep["packages"]] == ["ENG-A", "ENG-Z"]


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
