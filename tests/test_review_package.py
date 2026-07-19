#!/usr/bin/env python3
"""Tests for MSN-0066 Increment 2 — Review Package generator (AP5).

Injects a SYNTHETIC reconciler report and a FAKE qa_fn, so no Mistral agent,
network, Supabase or GitHub is touched. Runnable under pytest or directly:
`python3 tests/test_review_package.py` from the repo root.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.coordination.lifecycle_status_map import LifecycleStage
from core.coordination.review_package import (
    build_review_packages,
    collect_evidence,
    format_review_packages,
)


def _report(*recs):
    return {"generated_at": "2026-06-18T00:00:00Z", "stage_counts": {},
            "recommendations": list(recs), "source": {"supabase_ok": True}}


def _rec(_id, stage, kind="handoff", title="", next_actor="Captain — review/merge the PR",
         evidence="PR #1 draft"):
    return {"id": _id, "kind": kind, "title": title, "stage": stage,
            "bucket": "AWAITING_REVIEW", "next_actor": next_actor,
            "claimed": "DELIVERED", "evidence": evidence}


def _fake_qa(calls):
    def _fn(mission_id, dossier):
        calls.append((mission_id, dossier))
        return f"APPROVE-TO-REVIEW: evidence sufficient for {mission_id}"
    return _fn


def test_only_review_stage_items_become_packages():
    rep = build_review_packages(
        _report(
            _rec("ENG-1", LifecycleStage.REVIEW.value),
            _rec("BREQ-1", LifecycleStage.APPROVAL.value, kind="build_request"),
        ),
        qa_fn=None,
    )
    assert rep["count"] == 1
    assert rep["packages"][0]["id"] == "ENG-1"


def test_qa_advisory_is_attached_when_available():
    calls = []
    rep = build_review_packages(
        _report(_rec("ENG-2", LifecycleStage.REVIEW.value, title="Fix login")),
        qa_fn=_fake_qa(calls),
    )
    pkg = rep["packages"][0]
    assert pkg["qa_available"] is True
    assert "APPROVE-TO-REVIEW" in pkg["qa_advisory"]
    # the QA officer was called exactly once with this item's mission id
    assert len(calls) == 1
    assert calls[0][0] == "ENG-2"            # mission_id falls back to the item id
    assert "REVIEW PACKAGE DOSSIER" in calls[0][1]


def test_qa_unavailable_degrades_gracefully():
    def _none_qa(mission_id, dossier):
        return None
    rep = build_review_packages(
        _report(_rec("ENG-3", LifecycleStage.REVIEW.value)),
        qa_fn=_none_qa,
    )
    pkg = rep["packages"][0]
    assert pkg["qa_available"] is False
    assert pkg["qa_advisory"] is None
    assert "advisory unavailable" in format_review_packages(rep)


def test_skipping_qa_entirely():
    rep = build_review_packages(
        _report(_rec("ENG-4", LifecycleStage.REVIEW.value)),
        qa_fn=None,
    )
    assert rep["packages"][0]["qa_available"] is False


def test_evidence_includes_ledger_evidence_even_without_handoff_file():
    # No handoff file on disk for a synthetic id → still captures ledger evidence.
    ev = collect_evidence(_rec("ENG-NOFILE", LifecycleStage.REVIEW.value,
                               evidence="PR #99 draft"))
    assert ev["ledger_evidence"] == "PR #99 draft"
    assert ev["mission_id"] == "ENG-NOFILE"   # falls back to id when no handoff Mission ID
    assert ev["handoff_file"] == ""           # file absent → empty, no crash


def test_empty_report_is_clean():
    rep = build_review_packages(_report(), qa_fn=None)
    assert rep["count"] == 0
    assert "nothing at the Review stage" in format_review_packages(rep)


def test_format_includes_pr_and_next_actor():
    rep = build_review_packages(
        _report(_rec("ENG-5", LifecycleStage.REVIEW.value, title="Add cache")),
        qa_fn=None,
    )
    out = format_review_packages(rep)
    assert "ENG-5" in out
    assert "Add cache" in out
    assert "next:" in out


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
