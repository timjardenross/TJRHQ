#!/usr/bin/env python3
"""Tests for MSN-0066 Increment 3 — Triage Recommendation packages (AP1-2).

Injects a SYNTHETIC ledger and FAKE search/risk/glm functions, so no Supabase,
Mistral, GLM or network is touched. Runnable under pytest or directly:
`python3 tests/test_triage_package.py` from the repo root.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.coordination.lifecycle_status_map import LifecycleStage
from core.coordination.triage_package import (
    build_triage_packages,
    format_triage_packages,
)


def _ledger(*items):
    return {"items": list(items), "actions_taken": [], "github_error": "",
            "supabase_ok": True, "applied": False}


def _idea(_id, title, claimed="Idea"):
    # An Idea mission with no PR maps to the Capture stage.
    return {"kind": "mission", "id": _id, "title": title, "claimed": claimed,
            "bucket": "AWAITING_APPROVAL", "evidence": "Idea — needs triage"}


def _fake_risk(score, band):
    return lambda mission: {"mission_id": mission["id"], "score": score, "band": band,
                            "reasons": [f"{band} risk"], "components": {}}


def test_capture_items_become_triage_packages():
    rep = build_triage_packages(
        _ledger(_idea("M-1", "Add auth")),
        search_fn=None, risk_fn=_fake_risk(40, "Moderate"), glm_fn=None)
    assert rep["count"] == 1
    p = rep["packages"][0]
    assert p["stage"] == LifecycleStage.CAPTURE.value
    assert p["risk"]["band"] == "Moderate"
    assert p["suggested_priority"] == "P2"   # Moderate → P2


def test_non_capture_items_are_ignored():
    review_item = {"kind": "handoff", "id": "ENG-1", "title": "", "claimed": "DELIVERED",
                   "bucket": "AWAITING_REVIEW", "evidence": "PR #1 draft"}
    rep = build_triage_packages(_ledger(review_item),
                                search_fn=None, risk_fn=None, glm_fn=None)
    assert rep["count"] == 0


def test_suggested_priority_tracks_risk_band():
    bands = {"Critical": "P0", "High": "P1", "Moderate": "P2", "Low": "P3"}
    for band, prio in bands.items():
        rep = build_triage_packages(
            _ledger(_idea("M-x", "x")),
            search_fn=None, risk_fn=_fake_risk(50, band), glm_fn=None)
        assert rep["packages"][0]["suggested_priority"] == prio, band


def test_duplicate_detection_excludes_self_and_flags():
    def _search(query):
        return {"missions": [{"id": "M-1", "title": "Add auth"},        # self — excluded
                             {"id": "M-OLD", "title": "Add auth (old)"}],  # real candidate
                "decisions": [{"id": "DEC-9", "statement": "auth policy"}]}
    rep = build_triage_packages(
        _ledger(_idea("M-1", "Add auth")),
        search_fn=_search, risk_fn=None, glm_fn=None)
    p = rep["packages"][0]
    assert p["is_likely_duplicate"] is True
    ids = [m["id"] for m in p["duplicate_candidates"]]
    assert "M-OLD" in ids and "M-1" not in ids       # self excluded
    assert p["related_decisions"][0]["id"] == "DEC-9"


def test_empty_title_skips_search():
    calls = []
    def _search(query):
        calls.append(query)
        return {"missions": [], "decisions": []}
    # build_request items carry an empty title → no search attempted.
    breq = {"kind": "build_request", "id": "BREQ-1", "title": "", "claimed": "pending_triage",
            "bucket": "AWAITING_APPROVAL", "evidence": "no marker"}
    rep = build_triage_packages(_ledger(breq), search_fn=_search, risk_fn=None, glm_fn=None)
    assert rep["count"] == 1
    assert calls == []                                # never searched on empty title
    assert rep["packages"][0]["is_likely_duplicate"] is False


def test_glm_complexity_attached_and_degrades():
    rep_on = build_triage_packages(
        _ledger(_idea("M-2", "Cache layer")),
        search_fn=None, risk_fn=None,
        glm_fn=lambda title, desc: "• Complexity: Medium\n• Dep: redis")
    assert rep_on["packages"][0]["complexity_available"] is True
    assert "Medium" in rep_on["packages"][0]["complexity_analysis"]

    rep_off = build_triage_packages(
        _ledger(_idea("M-2", "Cache layer")),
        search_fn=None, risk_fn=None, glm_fn=lambda title, desc: None)
    assert rep_off["packages"][0]["complexity_available"] is False
    assert "analysis unavailable" in format_triage_packages(rep_off)


def test_packages_sorted_by_risk_score_desc():
    rep = build_triage_packages(
        _ledger(_idea("M-LOW", "low"), _idea("M-HIGH", "high")),
        search_fn=None,
        risk_fn=lambda m: {"score": 80 if m["id"] == "M-HIGH" else 10,
                           "band": "High" if m["id"] == "M-HIGH" else "Low",
                           "reasons": []},
        glm_fn=None)
    assert [p["id"] for p in rep["packages"]] == ["M-HIGH", "M-LOW"]


def test_empty_ledger_is_clean():
    rep = build_triage_packages(_ledger(), search_fn=None, risk_fn=None, glm_fn=None)
    assert rep["count"] == 0
    assert "nothing at the Capture stage" in format_triage_packages(rep)


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
