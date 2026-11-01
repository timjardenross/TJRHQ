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


class TestGreenIsFullyUnrestricted:
    def test_green_keeps_every_mode(self):
        kept = fte._apply_capacity_gate(ALL_MODES_FAR_DUE, "Green", NOW)
        assert {t["id"] for t in kept} == {t["id"] for t in ALL_MODES_FAR_DUE}


class TestAmberTrimsOnlyGentle:
    def test_amber_drops_far_due_gentle_item(self):
        kept = fte._apply_capacity_gate(ALL_MODES_FAR_DUE, "Amber", NOW)
        assert "t-gentle" not in {t["id"] for t in kept}

    def test_amber_keeps_far_due_normal_item(self):
        """This is the gap: pre-fix, Amber == Green, so a far-due normal
        item wasn't distinguished from Red's stricter cut. Post-fix, Amber
        must still be looser than Red -- normal items survive Amber."""
        kept = fte._apply_capacity_gate(ALL_MODES_FAR_DUE, "Amber", NOW)
        assert "t-normal" in {t["id"] for t in kept}

    def test_amber_keeps_far_due_persistent_deadline_waiting(self):
        kept = fte._apply_capacity_gate(ALL_MODES_FAR_DUE, "Amber", NOW)
        ids = {t["id"] for t in kept}
        assert {"t-persistent", "t-deadline", "t-waiting"} <= ids

    def test_amber_keeps_near_due_gentle_item(self):
        near = [_task("gentle", due_date=NEAR_DUE)]
        kept = fte._apply_capacity_gate(near, "Amber", NOW)
        assert len(kept) == 1

    def test_amber_keeps_gentle_item_with_no_due_date_if_not_urgent_by_other_signal(self):
        """No due_date is treated the same as "far due" (existing Red
        logic's own `due is None or (due - today).days > 1` treats a
        missing due date as eligible-for-trim) -- confirms Amber inherits
        that same interpretation for gentle items rather than a new one."""
        no_due = [_task("gentle", due_date=None)]
        kept = fte._apply_capacity_gate(no_due, "Amber", NOW)
        assert kept == []

    def test_amber_is_strictly_looser_than_red(self):
        red_kept = {t["id"] for t in fte._apply_capacity_gate(ALL_MODES_FAR_DUE, "Red", NOW)}
        amber_kept = {t["id"] for t in fte._apply_capacity_gate(ALL_MODES_FAR_DUE, "Amber", NOW)}
        assert red_kept < amber_kept


class TestRedUnchanged:
    def test_red_drops_far_due_gentle_and_normal(self):
        kept = fte._apply_capacity_gate(ALL_MODES_FAR_DUE, "Red", NOW)
        ids = {t["id"] for t in kept}
        assert "t-gentle" not in ids
        assert "t-normal" not in ids

    def test_red_keeps_persistent_deadline_waiting(self):
        kept = fte._apply_capacity_gate(ALL_MODES_FAR_DUE, "Red", NOW)
        ids = {t["id"] for t in kept}
        assert {"t-persistent", "t-deadline", "t-waiting"} <= ids


class TestUnknownCapacityIsNotTreatedAsGreen:
    """The core safety fix: capacity_status="Unknown" (no check-in today)
    must not silently behave like Green (fully unrestricted)."""

    def test_unknown_capacity_drops_far_due_gentle_item(self):
        kept = fte._apply_capacity_gate(ALL_MODES_FAR_DUE, "Unknown", NOW)
        assert "t-gentle" not in {t["id"] for t in kept}

    def test_unknown_capacity_behaves_identically_to_amber(self):
        unknown_kept = {t["id"] for t in fte._apply_capacity_gate(ALL_MODES_FAR_DUE, "Unknown", NOW)}
        amber_kept = {t["id"] for t in fte._apply_capacity_gate(ALL_MODES_FAR_DUE, "Amber", NOW)}
        assert unknown_kept == amber_kept

    def test_unknown_capacity_is_not_identical_to_green(self):
        unknown_kept = {t["id"] for t in fte._apply_capacity_gate(ALL_MODES_FAR_DUE, "Unknown", NOW)}
        green_kept = {t["id"] for t in fte._apply_capacity_gate(ALL_MODES_FAR_DUE, "Green", NOW)}
        assert unknown_kept != green_kept


class TestCanonicalCapacityMapping:
    """Mission 3: confirms the gate now consumes capacity_score.py's
    canonical mapper rather than reimplementing zone-string handling."""

    def test_fetch_todays_capacity_state_uses_canonical_mapper(self, monkeypatch):
        monkeypatch.setattr(fte, "_pg_get", lambda query: ([{"capacity_state": "orange"}], None))
        assert fte._fetch_todays_capacity_state(NOW) == "Amber"

    def test_fetch_todays_capacity_state_no_checkin_is_unknown(self, monkeypatch):
        monkeypatch.setattr(fte, "_pg_get", lambda query: ([], None))
        assert fte._fetch_todays_capacity_state(NOW) == "Unknown"
