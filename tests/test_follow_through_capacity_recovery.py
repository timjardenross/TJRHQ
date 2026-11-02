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


class TestNothingIsTrimmedSoNothingNeedsRecovering:
    """Capacity never trims nudges (owner decision 2026-11-02), so there is no
    suppression to recover from. These tests pin that for every reading and sequence."""

    def test_red_keeps_everything(self):
        kept = fte._apply_capacity_gate(CANDIDATES, "Red", NOW)
        assert {t["id"] for t in kept} == {"t-gentle", "t-normal", "t-persistent"}

    def test_any_sequence_of_readings_gives_the_same_result(self):
        results = [
            {t["id"] for t in fte._apply_capacity_gate(CANDIDATES, s, NOW)}
            for s in ("Red", "Amber", "Green", "Unknown", "Red")
        ]
        assert all(r == {"t-gentle", "t-normal", "t-persistent"} for r in results)


class TestNoStatefulSuppression:
    def test_candidates_list_and_dicts_are_not_mutated_by_a_red_pass(self):
        before = copy.deepcopy(CANDIDATES)
        fte._apply_capacity_gate(CANDIDATES, "Red", NOW)
        assert CANDIDATES == before
