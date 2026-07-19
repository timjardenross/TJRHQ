#!/usr/bin/env python3
"""Tests for MSN-0066 Increment 0 — unified lifecycle status spine.

Pure module, so these are pure assertions (no mocks, no I/O). Runnable either
under pytest or directly: `python3 tests/test_lifecycle_status_map.py` from the
repo root.
"""

import sys
from pathlib import Path

# Repo root on path so `core.coordination.*` namespace-package imports resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.coordination.engineering_handoff_reader import EngineeringStatus
from core.coordination.lifecycle_status_map import (
    LIFECYCLE_SPINE,
    LifecycleStage,
    from_canonical_status,
    from_engineering_status,
    from_inbox_status,
    from_slack_status,
    reconcile,
    stage_order,
)

S = LifecycleStage


def test_spine_is_ordered_capture_to_closed():
    assert LIFECYCLE_SPINE[0] is S.CAPTURE
    assert LIFECYCLE_SPINE[-1] is S.CLOSED
    orders = [stage_order(s) for s in LIFECYCLE_SPINE]
    assert orders == sorted(orders) == list(range(len(LIFECYCLE_SPINE)))


def test_slack_vocabulary_fully_mapped():
    expected = {
        "Idea": S.CAPTURE, "Planned": S.CAPTURE, "Active": S.BUILD,
        "Blocked": S.BUILD, "Review": S.REVIEW, "Completed": S.CLOSED,
        "Closed": S.CLOSED,
    }
    for raw, stage in expected.items():
        assert from_slack_status(raw) is stage, raw


def test_canonical_vocabulary_fully_mapped():
    expected = {
        "Idea": S.CAPTURE, "Designed": S.CAPTURE, "Implemented": S.BUILD,
        "Tested": S.REVIEW, "Awaiting Number One Review": S.REVIEW,
        "Validated": S.REVIEW, "Awaiting XO Approval": S.REVIEW,
        "Closed": S.CLOSED, "Blocked": S.BUILD, "Archived": S.CLOSED,
    }
    for raw, stage in expected.items():
        assert from_canonical_status(raw) is stage, raw


def test_engineering_vocabulary_fully_mapped():
    expected = {
        EngineeringStatus.PENDING_TRIAGE: S.BUILD,
        EngineeringStatus.ASSIGNED: S.BUILD,
        EngineeringStatus.IN_PROGRESS: S.BUILD,
        EngineeringStatus.AWAITING_REVIEW: S.REVIEW,
        EngineeringStatus.COMPLETED: S.CLOSED,
    }
    for es, stage in expected.items():
        assert from_engineering_status(es) is stage, es
        # Also accept the string label and a raw batch-status token.
        assert from_engineering_status(es.value) is stage, es.value
    # Raw Batch Status tokens resolve via the reader (reuse, no drift).
    assert from_engineering_status("DELIVERED") is S.REVIEW
    assert from_engineering_status("SUBMITTED") is S.BUILD  # → Assigned → BUILD
    # Terminal-but-not-completed handoffs are excluded (reader returns None).
    assert from_engineering_status("FAILED") is None


def test_inbox_vocabulary_fully_mapped():
    expected = {
        "pending_triage": S.CAPTURE, "approved": S.APPROVAL,
        "engineering_running": S.BUILD, "engineering_delivered": S.REVIEW,
        "engineering_failed": S.REVIEW,
    }
    for raw, stage in expected.items():
        assert from_inbox_status(raw) is stage, raw


def test_pending_triage_is_stage_sensitive_to_source():
    # The crux of the unified spine: same words, different stages.
    assert from_inbox_status("pending_triage") is S.CAPTURE          # raw request, pre-approval
    assert from_engineering_status("Pending Triage") is S.BUILD      # approved handoff, awaiting pickup


def test_unknown_values_return_none():
    assert from_slack_status("Frobnicated") is None
    assert from_canonical_status(None) is None
    assert from_inbox_status("") is None


def test_reconcile_picks_furthest_frontier_and_flags_disagreement():
    # Mission row says Active (BUILD) but engineering delivered (REVIEW):
    # the work has really reached review — frontier wins, disagreement flagged.
    r = reconcile(slack_status="Active", engineering_status="Awaiting Review")
    assert r.stage is S.REVIEW
    assert r.disagreement is True
    assert r.inputs["slack"] is S.BUILD
    assert r.inputs["engineering"] is S.REVIEW


def test_reconcile_agreement_has_no_disagreement():
    r = reconcile(slack_status="Closed", canonical_status="Archived")
    assert r.stage is S.CLOSED
    assert r.disagreement is False


def test_reconcile_with_no_inputs_is_empty():
    r = reconcile()
    assert r.stage is None
    assert r.disagreement is False
    assert all(v is None for v in r.inputs.values())


def test_reconcile_ignores_unresolved_inputs_for_frontier():
    # An unknown slack status contributes None and must not affect the frontier.
    r = reconcile(slack_status="Frobnicated", inbox_status="approved")
    assert r.stage is S.APPROVAL
    assert r.disagreement is False  # only one resolved input


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
