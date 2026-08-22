"""
Tests for intervention_engine.py — MY CAPACITY TODAY V02 WP03.

Covers the deterministic scoring function (_score) directly, and
rank_interventions/create_event/complete_reassessment against a mocked
Supabase client. Same check()/main() style as the other capacitybot test
files.

Run from repo root:
    python telegram-bots/capacitybot/test_intervention_engine.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parents[2]))

from telegram_bots.capacitybot.intervention_engine import (
    MIN_SAMPLE_FOR_WEIGHTING,
    _score,
    complete_reassessment,
    create_event,
    personal_effectiveness_summary,
    rank_interventions,
)

PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, str]] = []


def check(label: str, condition: bool) -> bool:
    tag = PASS if condition else FAIL
    _results.append((tag, label))
    print(f"  [{tag}] {label}")
    return condition


def _row(**overrides) -> dict:
    base = dict(
        intervention_id="test_action",
        target_states=[],
        capacity_allowed=["green", "orange", "red"],
        stimulation_effect="neutral",
        pain_compatible=True,
        executive_effort="low",
    )
    base.update(overrides)
    return base


# ── _score — pure function, no DB ────────────────────────────────────────────

def test_score_help_state_match_bonus():
    print("\n── _score — help_state match beats a non-match ──────────────────")
    matching = _row(target_states=["overwhelmed"])
    other = _row(target_states=["flat"])
    s_match = _score(matching, help_state="overwhelmed", stimulation_state=None,
                      pain_state=None, capacity_state=None, executive_function=None, outcomes=None)
    s_other = _score(other, help_state="overwhelmed", stimulation_state=None,
                      pain_state=None, capacity_state=None, executive_function=None, outcomes=None)
    check("matching target_state scores higher", s_match > s_other)


def test_score_no_help_state_gives_flat_base():
    print("\n── _score — no help_state (Q9/guide path) still scores ──────────")
    s = _score(_row(), help_state=None, stimulation_state=None, pain_state=None,
               capacity_state=None, executive_function=None, outcomes=None)
    check("flat base score applied even with no help_state signal", s == 5.0)


def test_score_stimulation_compatibility():
    print("\n── _score — stimulation direction compatibility ─────────────────")
    increase_row = _row(stimulation_effect="increase")
    decrease_row = _row(stimulation_effect="decrease")
    s_good = _score(increase_row, help_state=None, stimulation_state="low", pain_state=None,
                     capacity_state=None, executive_function=None, outcomes=None)
    s_bad = _score(decrease_row, help_state=None, stimulation_state="low", pain_state=None,
                    capacity_state=None, executive_function=None, outcomes=None)
    check("an increase-effect action scores higher when understimulated", s_good > s_bad)
    check("a mismatched decrease-effect action is penalised, not just unrewarded", s_bad < 5.0)


def test_score_pain_incompatible_is_hard_excluded():
    print("\n── _score — pain-incompatible action excluded outright on elevated pain ─")
    incompatible = _row(pain_compatible=False)
    s = _score(incompatible, help_state=None, stimulation_state=None, pain_state="elevated",
               capacity_state=None, executive_function=None, outcomes=None)
    check("returns None (hard exclude), not just a low score", s is None)


def test_score_pain_compatible_not_excluded():
    print("\n── _score — pain-compatible action survives elevated pain ───────")
    compatible = _row(pain_compatible=True)
    s = _score(compatible, help_state=None, stimulation_state=None, pain_state="elevated",
               capacity_state=None, executive_function=None, outcomes=None)
    check("pain-compatible action is not excluded", s is not None)


def test_score_high_executive_effort_penalised_in_red():
    print("\n── _score — high executive_effort penalised when capacity is red ─")
    high_effort = _row(executive_effort="high")
    s_red = _score(high_effort, help_state=None, stimulation_state=None, pain_state=None,
                    capacity_state="red", executive_function=None, outcomes=None)
    s_green = _score(high_effort, help_state=None, stimulation_state=None, pain_state=None,
                      capacity_state="green", executive_function=None, outcomes=None)
    check("high-effort action scores worse in red than in green (spec §10 — no productivity push in red)",
          s_red < s_green)


def test_score_personal_outcomes_below_sample_floor_ignored():
    print("\n── _score — outcome weighting skipped below MIN_SAMPLE_FOR_WEIGHTING ─")
    check("floor is a small positive number", 1 <= MIN_SAMPLE_FOR_WEIGHTING <= 5)
    row = _row()
    # exactly one "worse" — below the sample floor AND below the 2-in-a-row
    # fresh-failure check, so neither penalty path should fire.
    s_no_outcomes = _score(row, help_state=None, stimulation_state=None, pain_state=None,
                            capacity_state=None, executive_function=None, outcomes=None)
    s_one_bad = _score(row, help_state=None, stimulation_state=None, pain_state=None,
                        capacity_state=None, executive_function=None, outcomes=["worse"])
    check("a single outcome below both the sample floor and the 2-in-a-row check doesn't move the score",
          s_no_outcomes == s_one_bad)


def test_score_recent_double_failure_penalised_even_below_floor():
    print("\n── _score — two most-recent failures penalised regardless of sample size ─")
    row = _row()
    s_clean = _score(row, help_state=None, stimulation_state=None, pain_state=None,
                      capacity_state=None, executive_function=None, outcomes=None)
    s_failed_twice = _score(row, help_state=None, stimulation_state=None, pain_state=None,
                             capacity_state=None, executive_function=None, outcomes=["worse", "worse"])
    check("an intervention that just failed twice scores lower, even with only 2 data points",
          s_failed_twice < s_clean)


def test_score_sufficient_sample_applies_weighting():
    print("\n── _score — enough samples -> net positive outcomes score higher ─")
    row = _row()
    good_outcomes = ["better"] * MIN_SAMPLE_FOR_WEIGHTING
    bad_outcomes = ["worse"] * MIN_SAMPLE_FOR_WEIGHTING
    s_good = _score(row, help_state=None, stimulation_state=None, pain_state=None,
                     capacity_state=None, executive_function=None, outcomes=good_outcomes)
    s_bad = _score(row, help_state=None, stimulation_state=None, pain_state=None,
                    capacity_state=None, executive_function=None, outcomes=bad_outcomes)
    check("a track record of 'better' outcomes outranks a track record of 'worse'", s_good > s_bad)


# ── rank_interventions / create_event / complete_reassessment — mocked DB ───

def _make_db(interventions, events=None):
    db = MagicMock()

    _table_mocks: dict[str, MagicMock] = {}

    def table_side_effect(name):
        if name in _table_mocks:
            return _table_mocks[name]
        t = MagicMock()
        if name == "capacity_interventions":
            select_mock = MagicMock()
            select_mock.eq.return_value.contains.return_value.execute.return_value = MagicMock(data=interventions)
            select_mock.eq.return_value.execute.return_value = MagicMock(data=interventions)
            t.select.return_value = select_mock
            t.insert.return_value.execute.return_value = MagicMock(data=[{"id": 1}])
        elif name == "capacity_intervention_events":
            sel = MagicMock()
            sel.in_.return_value.not_.is_.return_value.order.return_value.limit.return_value.execute.return_value = \
                MagicMock(data=events or [])
            sel.execute.return_value = MagicMock(data=events or [])
            t.select.return_value = sel
            t.insert.return_value.execute.return_value = MagicMock(data=[{"id": 42}])
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        _table_mocks[name] = t
        return t

    db.table.side_effect = table_side_effect
    return db


def test_rank_interventions_filters_and_sorts():
    print("\n── rank_interventions — safety filter + ordering ─────────────────")
    candidates = [
        _row(intervention_id="a", target_states=["overwhelmed"], capacity_allowed=["orange", "red"]),
        _row(intervention_id="b", target_states=["flat"], capacity_allowed=["orange", "red"]),
        _row(intervention_id="c", target_states=["overwhelmed"], pain_compatible=False, capacity_allowed=["orange", "red"]),
    ]
    db = _make_db(candidates, events=[])
    ranked = asyncio.run(rank_interventions(
        db, help_state="overwhelmed", capacity_state="red", pain_state="elevated", limit=5,
    ))
    ids = [r["intervention_id"] for r in ranked]
    check("pain-incompatible candidate excluded", "c" not in ids)
    check("matching help_state candidate ranks first", ids[0] == "a")


def test_rank_interventions_empty_catalogue_returns_empty():
    print("\n── rank_interventions — no candidates, no crash ──────────────────")
    db = _make_db([], events=[])
    ranked = asyncio.run(rank_interventions(db, capacity_state="green"))
    check("empty list, not an exception", ranked == [])


def test_rank_interventions_no_db_returns_empty():
    print("\n── rank_interventions — Supabase unavailable degrades gracefully ─")
    ranked = asyncio.run(rank_interventions(None, capacity_state="green"))
    check("no db -> empty list, no crash", ranked == [])


def test_create_event_writes_expected_payload():
    print("\n── create_event — writes source/intervention_id/before-state ────")
    db = _make_db([])
    ok, row, err = asyncio.run(create_event(
        db, source="helpme", intervention_id="quiet_10", help_state="overwhelmed",
        capacity_before="red",
    ))
    check("reports success", ok)
    check("returns the inserted row", row == {"id": 42})
    check("no error", err is None)
    payload = db.table("capacity_intervention_events").insert.call_args[0][0]
    check("source recorded", payload["source"] == "helpme")
    check("intervention_id recorded", payload["intervention_id"] == "quiet_10")
    check("capacity_before recorded", payload["capacity_before"] == "red")


def test_create_event_no_db_fails_gracefully():
    print("\n── create_event — no Supabase, fails without raising ─────────────")
    ok, row, err = asyncio.run(create_event(None, source="helpme", intervention_id="x"))
    check("reports failure", not ok)
    check("row is None", row is None)
    check("error message present", err is not None)


def test_complete_reassessment_writes_outcome():
    print("\n── complete_reassessment — writes Better/Same/Worse outcome ─────")
    db = _make_db([])
    ok, err = asyncio.run(complete_reassessment(
        db, 42, outcome="better", capacity_after="orange", would_use_again="yes",
    ))
    check("reports success", ok)
    check("no error", err is None)
    payload = db.table("capacity_intervention_events").update.call_args[0][0]
    check("outcome recorded", payload["outcome"] == "better")
    check("capacity_after recorded", payload["capacity_after"] == "orange")
    check("would_use_again recorded", payload["would_use_again"] == "yes")


def test_personal_effectiveness_summary_counts_by_outcome():
    print("\n── personal_effectiveness_summary — counts, not percentages ─────")
    events = [
        {"intervention_id": "quiet_10", "outcome": "better"},
        {"intervention_id": "quiet_10", "outcome": "better"},
        {"intervention_id": "quiet_10", "outcome": "worse"},
    ]
    catalogue = [{"intervention_id": "quiet_10", "title": "Move somewhere quieter"}]
    db = _make_db(catalogue, events=events)
    summary = asyncio.run(personal_effectiveness_summary(db))
    row = next(r for r in summary if r["intervention_id"] == "quiet_10")
    check("attempts counted correctly", row["attempts"] == 3)
    check("better count correct", row["better"] == 2)
    check("worse count correct", row["worse"] == 1)
    check("no percentage field present — counts only (spec §15/§31)", "percentage" not in row and "pct" not in row)


def main():
    print("=" * 60)
    print("Intervention Engine — V02 WP03 test suite")
    print("=" * 60)

    test_score_help_state_match_bonus()
    test_score_no_help_state_gives_flat_base()
    test_score_stimulation_compatibility()
    test_score_pain_incompatible_is_hard_excluded()
    test_score_pain_compatible_not_excluded()
    test_score_high_executive_effort_penalised_in_red()
    test_score_personal_outcomes_below_sample_floor_ignored()
    test_score_recent_double_failure_penalised_even_below_floor()
    test_score_sufficient_sample_applies_weighting()
    test_rank_interventions_filters_and_sorts()
    test_rank_interventions_empty_catalogue_returns_empty()
    test_rank_interventions_no_db_returns_empty()
    test_create_event_writes_expected_payload()
    test_create_event_no_db_fails_gracefully()
    test_complete_reassessment_writes_outcome()
    test_personal_effectiveness_summary_counts_by_outcome()

    passed = sum(1 for tag, _ in _results if tag == PASS)
    total = len(_results)
    failed = [label for tag, label in _results if tag == FAIL]

    print(f"\n{'=' * 60}")
    print(f"{passed}/{total} tests passed")
    if failed:
        print("FAILED:")
        for f in failed:
            print(f"  ✗ {f}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
