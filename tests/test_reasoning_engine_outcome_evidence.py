"""Reasoning Engine outcome-evidence wiring (Mission 5: Evidence &
Adaptive Support).

Covers `reasoning_engine._apply_outcome_evidence()` — the first real
reader of `insight_outcomes` (`fetch_outcome_history()`/
`fetch_similar_outcomes()` had zero call sites anywhere in the repo
before this mission). No pytest available in this environment (matches
`test_cognitive_core_regression.py`'s own documented workaround) —
every scenario is a plain function returning True/False, runnable
directly via `python3 tests/test_reasoning_engine_outcome_evidence.py`.

Network/model-router calls are never exercised here — these scenarios
call `_apply_outcome_evidence()` directly with a hand-built
`Recommendation`, monkeypatching `reasoning_engine.fetch_similar_outcomes`
so no real Supabase access is required (matches insight_engine.py's own
degrade-to-[] contract: this module doesn't need a live table to be
testable).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.platform import reasoning_engine
from core.platform.captain_brief_contract import Recommendation
from core.platform.insight_engine import Insight


def _insight(source_kind="relationship", domains=("health-intelligence",)) -> Insight:
    return Insight(
        observation="obs", why_it_matters="why", evidence_chain=["1", "2"],
        confidence=70, potential_impact="impact", source_kind=source_kind,
        source_domains=list(domains),
    )


def _recommendation(confidence: int = 70) -> Recommendation:
    return Recommendation(description="do the thing", confidence=confidence, supporting_context="because reasons")


def _with_history(rows):
    def _fake(source_kind, source_domains, *, limit=200):
        return rows
    return _fake


def scenario_below_floor_returns_unchanged() -> bool:
    """Fewer than 3 recorded outcomes — the exact `_MIN_OUTCOMES_FOR_ADJUSTMENT`
    floor mirroring `mission_knowledge_store._MIN_OUTCOMES_FOR_SCORE` — must
    make zero changes: no confidence shift, no note appended, no error."""
    reasoning_engine.fetch_similar_outcomes = _with_history([
        {"outcome": "useful"}, {"outcome": "useful"},
    ])
    rec = _recommendation(confidence=70)
    out = reasoning_engine._apply_outcome_evidence(rec, _insight())
    return out.confidence == 70 and out.supporting_context == "because reasons"


def scenario_single_row_never_treated_as_proof() -> bool:
    """Exactly one recorded outcome must never move confidence — spec §36's
    explicit "not from one data point" requirement, at the boundary."""
    reasoning_engine.fetch_similar_outcomes = _with_history([{"outcome": "useful"}])
    rec = _recommendation(confidence=50)
    out = reasoning_engine._apply_outcome_evidence(rec, _insight())
    return out.confidence == 50


def scenario_strong_positive_history_raises_confidence_within_clamp() -> bool:
    """4 of 5 useful (80%) — top tier, +0.08, well inside the ±0.15 clamp
    mission_knowledge_store.py uses for the same kind of adjustment."""
    rows = [{"outcome": "useful"}] * 4 + [{"outcome": "not_useful"}]
    reasoning_engine.fetch_similar_outcomes = _with_history(rows)
    rec = _recommendation(confidence=60)
    out = reasoning_engine._apply_outcome_evidence(rec, _insight())
    return out.confidence == 68 and "5 of 5" not in out.supporting_context and "4 of 5" in out.supporting_context


def scenario_strong_negative_history_lowers_confidence() -> bool:
    """4 of 5 not_useful (20% useful) — bottom tier, -0.08."""
    rows = [{"outcome": "not_useful"}] * 4 + [{"outcome": "useful"}]
    reasoning_engine.fetch_similar_outcomes = _with_history(rows)
    rec = _recommendation(confidence=60)
    out = reasoning_engine._apply_outcome_evidence(rec, _insight())
    return out.confidence == 52


def scenario_mixed_history_makes_no_adjustment_but_still_explains() -> bool:
    """50/50 split — no confidence change, but the trace still names the
    sample size (spec §30: an explainable answer even when the evidence
    itself is inconclusive, not silence)."""
    rows = [{"outcome": "useful"}, {"outcome": "useful"}, {"outcome": "not_useful"}, {"outcome": "not_useful"}]
    reasoning_engine.fetch_similar_outcomes = _with_history(rows)
    rec = _recommendation(confidence=60)
    out = reasoning_engine._apply_outcome_evidence(rec, _insight())
    return out.confidence == 60 and "2 of 4" in out.supporting_context and "mixed evidence" in out.supporting_context


def scenario_confidence_never_exceeds_100() -> bool:
    """A recommendation already near the ceiling must clamp at 100, not
    overshoot past it."""
    rows = [{"outcome": "useful"}] * 5
    reasoning_engine.fetch_similar_outcomes = _with_history(rows)
    rec = _recommendation(confidence=97)
    out = reasoning_engine._apply_outcome_evidence(rec, _insight())
    return out.confidence == 100


def scenario_no_evidence_note_leaked_into_recommendation_below_floor() -> bool:
    """Empty history (e.g. Supabase disabled/unreachable) must behave
    identically to below-floor: no change at all."""
    reasoning_engine.fetch_similar_outcomes = _with_history([])
    rec = _recommendation(confidence=42)
    out = reasoning_engine._apply_outcome_evidence(rec, _insight())
    return out.confidence == 42 and out.supporting_context == "because reasons"


SCENARIOS = {
    "below_floor_returns_unchanged": scenario_below_floor_returns_unchanged,
    "single_row_never_treated_as_proof": scenario_single_row_never_treated_as_proof,
    "strong_positive_history_raises_confidence_within_clamp": scenario_strong_positive_history_raises_confidence_within_clamp,
    "strong_negative_history_lowers_confidence": scenario_strong_negative_history_lowers_confidence,
    "mixed_history_makes_no_adjustment_but_still_explains": scenario_mixed_history_makes_no_adjustment_but_still_explains,
    "confidence_never_exceeds_100": scenario_confidence_never_exceeds_100,
    "no_evidence_note_leaked_into_recommendation_below_floor": scenario_no_evidence_note_leaked_into_recommendation_below_floor,
}


def run_all() -> bool:
    all_passed = True
    for name, fn in SCENARIOS.items():
        try:
            passed = fn()
        except Exception as exc:  # noqa: BLE001 - test-runner harness: must catch any failure from a scenario fn to report it and keep running the rest
            passed = False
            print(f"  ERROR  {name}: {exc}")
        else:
            print(f"  {'PASS' if passed else 'FAIL'}  {name}")
        all_passed = all_passed and passed
    return all_passed


if __name__ == "__main__":
    ok = run_all()
    print()
    print("ALL SCENARIOS PASSED" if ok else "SOME SCENARIOS FAILED")
    sys.exit(0 if ok else 1)
