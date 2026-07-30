#!/usr/bin/env python3
"""Tests for MSN-0066 Increment 5 — Pending Actions aggregator + dashboard surface.

Drives the aggregator with a SYNTHETIC ledger (no network/Supabase/GitHub). The
Flask `register()` hook is exercised only if flask is importable; otherwise that
test is skipped. Runnable under pytest or directly:
`python3 tests/test_pending_actions.py` from the repo root.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.coordination.lifecycle_status_map import LifecycleStage
from core.coordination.pending_actions import build_pending_actions, register


def _ledger(*items):
    return {"items": list(items), "actions_taken": [], "github_error": "",
            "supabase_ok": True, "applied": False}


def _item(kind, _id, claimed, bucket, title="", evidence=""):
    return {"kind": kind, "id": _id, "title": title, "claimed": claimed,
            "bucket": bucket, "evidence": evidence}


def _mixed_ledger():
    return _ledger(
        _item("handoff", "ENG-REV", "DELIVERED", "AWAITING_REVIEW", "Fix login", "PR #1 draft"),
        _item("build_request", "BREQ-CAP", "pending_triage", "AWAITING_APPROVAL", evidence="no marker"),
        _item("handoff", "ENG-BUILD", "PENDING", "IN_PROGRESS", "WIP feature"),
        _item("mission", "M-DONE", "Closed", "DELIVERED", evidence="merged"),
    )


def test_payload_partitions_items_by_view():
    p = build_pending_actions(_mixed_ledger(), triage_ready=[])
    assert [r["id"] for r in p["review"]] == ["ENG-REV"]
    assert [t["id"] for t in p["triage"]] == ["BREQ-CAP"]
    assert [b["id"] for b in p["ready_for_engineering"]] == ["ENG-BUILD"]


def test_totals_and_spine_counts():
    p = build_pending_actions(_mixed_ledger(), triage_ready=[])
    assert p["totals"]["needs_human"] == 3        # review + triage + ready
    assert p["totals"]["review"] == 1
    assert p["totals"]["triage"] == 1
    assert p["totals"]["ready_for_engineering"] == 1
    # spine has every stage and reflects the ledger
    assert set(p["spine"].keys()) == {s.value for s in LifecycleStage}
    assert p["spine"][LifecycleStage.REVIEW.value] == 1
    assert p["spine"][LifecycleStage.CAPTURE.value] == 1
    assert p["spine"][LifecycleStage.BUILD.value] == 1
    assert p["spine"][LifecycleStage.CLOSED.value] == 1


def test_empty_ledger_is_clean():
    p = build_pending_actions(_ledger(), triage_ready=[])
    assert p["totals"]["needs_human"] == 0
    assert p["review"] == [] and p["triage"] == [] and p["ready_for_engineering"] == []
    assert all(v == 0 for v in p["spine"].values())


def test_advanced_item_moves_from_triage_to_awaiting_approval():
    # The same Capture item, before vs after the advancer recorded it Triage Ready.
    led = _ledger(_item("build_request", "BREQ-CAP", "pending_triage",
                        "AWAITING_APPROVAL", evidence="no marker"))
    before = build_pending_actions(led, triage_ready=[])
    assert [t["id"] for t in before["triage"]] == ["BREQ-CAP"]
    assert before["totals"]["awaiting_approval"] == 0

    after = build_pending_actions(led, triage_ready=[{"id": "BREQ-CAP", "stage": "Triage Ready"}])
    assert after["triage"] == []                       # moved off the triage list
    assert [a["id"] for a in after["awaiting_approval"]] == ["BREQ-CAP"]
    assert after["totals"]["awaiting_approval"] == 1
    assert after["totals"]["needs_human"] == 1         # still one item, now at the gate


def test_review_items_carry_next_actor():
    p = build_pending_actions(_mixed_ledger(), triage_ready=[])
    assert "review" in p["review"][0]["next_actor"].lower()


def test_register_mounts_a_get_route():
    try:
        from flask import Flask
    except Exception:  # noqa: BLE001 - flask not installed in this env → skip
        print("    (flask unavailable — skipping route mount test)")
        return
    app = Flask(__name__)
    register(app)
    rules = {r.rule: r for r in app.url_map.iter_rules()}
    assert "/api/dashboard/pending-actions" in rules
    assert "GET" in rules["/api/dashboard/pending-actions"].methods
    # The view must not raise even when the live reconciler can't run; it returns
    # a graceful payload. Use the test client.
    client = app.test_client()
    resp = client.get("/api/dashboard/pending-actions")
    assert resp.status_code in (200, 503)
    assert "totals" in resp.get_json()


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
