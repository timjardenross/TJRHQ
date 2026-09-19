"""Mission 2 (Capacity & Attention Engine) §15 — Recovery From Suppression,
follow-through domain. Companion to tests/test_follow_through_engine_
capacity_gate.py (which covers the Amber/Red/Unknown gating rules
themselves) — this file covers the specific recovery claim: an item
trimmed by _apply_capacity_gate() under Red must reappear once capacity
recovers, and the function must not mutate its input, so recovery is a
structural consequence of the filter being pure rather than something that
had to be separately engineered.
"""
from __future__ import annotations

import copy
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

import intelligence.adhd.follow_through_engine as fte

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
TODAY = fte._today(NOW)
FAR_DUE = (TODAY + timedelta(days=10)).isoformat()

CANDIDATES = [
    {"id": "t-gentle", "follow_through_mode": "gentle", "due_date": FAR_DUE},
    {"id": "t-normal", "follow_through_mode": "normal", "due_date": FAR_DUE},
    {"id": "t-persistent", "follow_through_mode": "persistent", "due_date": FAR_DUE},
]


class TestTrimmedItemsReturnWhenCapacityRecovers:
    def test_red_trims_gentle_and_normal(self):
        kept = fte._apply_capacity_gate(CANDIDATES, "Red", NOW)
        assert {t["id"] for t in kept} == {"t-persistent"}

    def test_green_on_the_identical_candidates_restores_everything(self):
        kept = fte._apply_capacity_gate(CANDIDATES, "Green", NOW)
        assert {t["id"] for t in kept} == {"t-gentle", "t-normal", "t-persistent"}

    def test_full_recovery_sequence_red_then_amber_then_green(self):
        """Same list object, three capacity readings in sequence -- each
        step's result must match what a fresh call with that state alone
        would produce, proving no state leaks between calls."""
        red = fte._apply_capacity_gate(CANDIDATES, "Red", NOW)
        amber = fte._apply_capacity_gate(CANDIDATES, "Amber", NOW)
        green = fte._apply_capacity_gate(CANDIDATES, "Green", NOW)

        assert {t["id"] for t in red} == {"t-persistent"}
        assert {t["id"] for t in amber} == {"t-normal", "t-persistent"}
        assert {t["id"] for t in green} == {"t-gentle", "t-normal", "t-persistent"}


class TestNoStatefulSuppression:
    def test_candidates_list_and_dicts_are_not_mutated_by_a_red_pass(self):
        before = copy.deepcopy(CANDIDATES)
        fte._apply_capacity_gate(CANDIDATES, "Red", NOW)
        assert CANDIDATES == before

    def test_unknown_capacity_recovery_path_is_also_stateless(self):
        """Unknown is treated as Amber (Mission 2 fix) -- confirm that
        treatment doesn't persist once a real reading arrives."""
        unknown = fte._apply_capacity_gate(CANDIDATES, "Unknown", NOW)
        green = fte._apply_capacity_gate(CANDIDATES, "Green", NOW)
        assert {t["id"] for t in unknown} == {"t-normal", "t-persistent"}  # Amber-equivalent
        assert {t["id"] for t in green} == {"t-gentle", "t-normal", "t-persistent"}
