"""Mission 2 (Capacity & Attention Engine) fix: intelligence/adhd/
follow_through_engine.py's _apply_capacity_gate() was the platform's one
real precedent for capacity-aware notification suppression, but had two
gaps:

1. No Amber behaviour at all -- the function only branched on
   `!= "red"`, so Amber got identical (fully unrestricted) treatment to
   Green.
2. Unknown capacity (no check-in today) was silently treated as
   unrestricted/Green -- the exact "absence must not imply Green" risk
   Mission 2's brief explicitly warns against.

Fix: unknown capacity is treated as Amber (a safe middle ground -- no
signal should never be read as full confidence), and Amber trims only the
lowest-urgency "gentle" mode items not due soon; Red (unchanged) also
trims "normal" mode items.

Mission 3 update: _apply_capacity_gate() now takes the canonical
"Green"/"Amber"/"Red"/"Unknown" vocabulary (from
core/health/capacity_score.py's capacity_zone_from_checkin(), the same
mapper every other capacity-status consumer in the platform uses) instead
of the raw capacity_checkins "green"/"orange"/"red"/None strings this
engine used to interpret itself. The gating BEHAVIOUR below is unchanged
-- only the input vocabulary is canonical now, closing the duplicated-
capacity-policy gap Mission 3 discovery found.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

import intelligence.adhd.follow_through_engine as fte

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
TODAY = fte._today(NOW)
FAR_DUE = (TODAY + timedelta(days=10)).isoformat()
NEAR_DUE = (TODAY + timedelta(days=1)).isoformat()


def _task(mode: str, due_date: str | None = FAR_DUE, **overrides) -> dict:
    row = {"id": f"t-{mode}", "follow_through_mode": mode, "due_date": due_date}
    row.update(overrides)
    return row


ALL_MODES_FAR_DUE = [
    _task("gentle"),
    _task("normal"),
    _task("persistent"),
    _task("deadline"),
    _task("waiting"),
]


class TestCapacityNeverTrimsNudges:
    """Owner decision 2026-11-02: no capacity reading (Green, Amber, Red or Unknown)
    trims follow-through nudges. Replaces the old Amber / Red / Unknown trimming rules."""

    @pytest.mark.parametrize("status", ["Green", "Amber", "Red", "Unknown"])
    def test_every_mode_is_kept(self, status):
        kept = fte._apply_capacity_gate(ALL_MODES_FAR_DUE, status, NOW)
        assert [t["id"] for t in kept] == [t["id"] for t in ALL_MODES_FAR_DUE]

    def test_gentle_item_with_no_due_date_is_kept(self):
        tasks = [_task("gentle", due_date=None)]
        assert fte._apply_capacity_gate(tasks, "Red", NOW) == tasks


class TestCanonicalCapacityMapping:
    """Mission 3: confirms the gate now consumes capacity_score.py's
    canonical mapper rather than reimplementing zone-string handling."""

    def test_fetch_todays_capacity_state_uses_canonical_mapper(self, monkeypatch):
        monkeypatch.setattr(fte, "_pg_get", lambda query: ([{"capacity_state": "orange"}], None))
        assert fte._fetch_todays_capacity_state(NOW) == "Amber"

    def test_fetch_todays_capacity_state_no_checkin_is_unknown(self, monkeypatch):
        monkeypatch.setattr(fte, "_pg_get", lambda query: ([], None))
        assert fte._fetch_todays_capacity_state(NOW) == "Unknown"
