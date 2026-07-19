#!/usr/bin/env python3
"""Tests for MSN-0066 Increment 1 — Lifecycle Reconciler.

Drives `build_recommendations` with a SYNTHETIC ledger (the same shape
`delivery_reconciler.reconcile()` returns), so the tests need no network,
Supabase, or GitHub. Runnable under pytest or directly:
`python3 tests/test_lifecycle_reconciler.py` from the repo root.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.coordination.lifecycle_reconciler import (
    build_recommendations,
    format_recommendations,
)
from core.coordination.lifecycle_status_map import LifecycleStage


def _ledger(*items):
    return {"items": list(items), "actions_taken": [], "github_error": "",
            "supabase_ok": True, "applied": False}


def _item(kind, _id, claimed, bucket, evidence="", title=""):
    return {"kind": kind, "id": _id, "title": title, "claimed": claimed,
            "bucket": bucket, "evidence": evidence}


def test_review_item_emits_recommendation():
    rep = build_recommendations(_ledger(
        _item("handoff", "ENG-1", "DELIVERED", "AWAITING_REVIEW", "PR #5 draft")))
    assert len(rep["recommendations"]) == 1
    rec = rep["recommendations"][0]
    assert rec["stage"] == LifecycleStage.REVIEW.value
    assert rec["id"] == "ENG-1"
    # next-actor is reused verbatim from the delivery reconciler's table.
    assert "review" in rec["next_actor"].lower()


def test_unapproved_request_is_capture_not_a_recommendation():
    # An un-approved build request is pre-approval → CAPTURE (Inc 3 triage's job),
    # not an Inc 1 human-action recommendation. The delivery bucket names the
    # next action (approve); the spine names the current stage (Capture).
    rep = build_recommendations(_ledger(
        _item("build_request", "BREQ-1", "pending_triage", "AWAITING_APPROVAL", "no marker")))
    assert rep["recommendations"] == []
    assert rep["stage_counts"][LifecycleStage.CAPTURE.value] == 1


def test_build_and_closed_items_emit_no_recommendation():
    rep = build_recommendations(_ledger(
        _item("mission", "M-1", "Implemented", "ASSIGNED", "no PR yet"),   # BUILD
        _item("mission", "M-2", "Closed", "DELIVERED", "merged")))         # CLOSED
    assert rep["recommendations"] == []
    # but they are still counted on the spine
    assert rep["stage_counts"][LifecycleStage.BUILD.value] == 1
    assert rep["stage_counts"][LifecycleStage.CLOSED.value] == 1


def test_pr_reality_advances_a_stale_claimed_status():
    # Mission row still claims "Implemented" (BUILD) but its PR is merged →
    # delivery bucket DELIVERED pulls the effective stage to CLOSED (frontier).
    rep = build_recommendations(_ledger(
        _item("mission", "M-3", "Implemented", "DELIVERED", "PR #9 merged")))
    assert rep["stage_counts"][LifecycleStage.CLOSED.value] == 1
    assert rep["stage_counts"][LifecycleStage.BUILD.value] == 0
    assert rep["recommendations"] == []  # done → no human action


def test_mislabeled_surfaces_as_review():
    # Claims Closed, but PR still open → delivery_reconciler bucket MISLABELED.
    rep = build_recommendations(_ledger(
        _item("mission", "M-4", "Closed", "MISLABELED", "PR #2 still open")))
    recs = rep["recommendations"]
    assert len(recs) == 1
    assert recs[0]["stage"] == LifecycleStage.REVIEW.value


def test_review_recommendations_are_deterministically_ordered():
    # Two review items sort stably by id (and review outranks any approval item,
    # though no current bucket maps to APPROVAL).
    rep = build_recommendations(_ledger(
        _item("handoff", "ENG-Z", "DELIVERED", "AWAITING_REVIEW"),
        _item("handoff", "ENG-A", "DELIVERED", "AWAITING_REVIEW")))
    ids = [r["id"] for r in rep["recommendations"]]
    assert ids == ["ENG-A", "ENG-Z"]
    assert all(r["stage"] == LifecycleStage.REVIEW.value for r in rep["recommendations"])


def test_empty_ledger_is_clean():
    rep = build_recommendations(_ledger())
    assert rep["recommendations"] == []
    assert all(v == 0 for v in rep["stage_counts"].values())
    assert "Nothing parked" in format_recommendations(rep)


def test_format_renders_grouped_actions():
    rep = build_recommendations(_ledger(
        _item("handoff", "ENG-7", "DELIVERED", "AWAITING_REVIEW", "PR #7 draft", "Fix X")))
    out = format_recommendations(rep)
    assert "need a human" in out
    assert "ENG-7" in out
    assert "Review" in out


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
