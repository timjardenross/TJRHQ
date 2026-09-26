"""Mission 2 (USS-TJR-MSN-2) fix: health_context_adapter.py's
build_health_context_live() -- the actual live path feeding
/api/recommendations via context_service.py and recommendation_engine.py's
rank_missions() -- derived capacity_score/capacity_status from
captains_log_entries via a weighted pain/energy/sleep formula
(compute_capacity_score), a second, competing capacity derivation from
capacity_checkins' direct Captain self-report (capacity_zone_from_checkin,
the canonical source per Mission 1). It also had no staleness cutoff: "no
today entry, try latest" regardless of age, served as current with no
Unknown flag.

These tests prove: (1) capacity now comes from capacity_checkins, not
captains_log_entries: (2) a missing today capacity_checkins row means
Unknown, never a stale prior reading served as current; (3) the other
(non-capacity) fields -- pain/mood/energy/themes -- are untouched, still
sourced from captains_log_entries, since that's a genuinely different
domain (a daily journal), not part of this fix's scope.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import health_context_adapter as hca


def _captains_log_stub(entry=None):
    """Fake _get_captains_log_live() -- always "configured", returns the
    given captains_log_entries row (or None) for both the today and
    latest-fallback queries, plus an empty trend series."""
    def fake_get(path_and_query: str):
        if path_and_query.startswith("captains_log_entries?log_date=gte."):
            return []  # no 7-day trend data needed for these tests
        return [entry] if entry else []
    return fake_get, (lambda: True), None  # compute_cap unused post-fix


def _capacity_checkin_stub(row=None):
    """Fake _get_capacity_checkin_live() -- always "configured", returns
    the given capacity_checkins row (or None) for the today query."""
    def fake_get(path_and_query: str):
        assert path_and_query.startswith("capacity_checkins?log_date=eq.")
        return [row] if row else []
    from core.health.capacity_score import capacity_zone_from_checkin
    return fake_get, (lambda: True), capacity_zone_from_checkin


class TestCapacitySourcedFromCapacityCheckins:
    def test_red_capacity_checkin_produces_red_status_regardless_of_captains_log(self):
        """The captains_log_entries row here has healthy-looking pain/energy
        (which the OLD weighted formula would likely have scored well above
        Red) -- if capacity_status still comes out Red, it proves the source
        is capacity_checkins, not the old formula."""
        entry = {"pain_score": 1, "energy": "high", "mood": "good", "sleep_quality": "good"}
        checkin = {"capacity_state": "red"}
        with mock.patch.object(hca, "_get_captains_log_live", return_value=_captains_log_stub(entry)), \
             mock.patch.object(hca, "_get_capacity_checkin_live", return_value=_capacity_checkin_stub(checkin)):
            pkg = hca.build_health_context_live()
        assert pkg.capacity_status == "Red"
        assert pkg.capacity_score == 25

    def test_green_capacity_checkin_produces_green_status(self):
        checkin = {"capacity_state": "green"}
        with mock.patch.object(hca, "_get_captains_log_live", return_value=_captains_log_stub(None)), \
             mock.patch.object(hca, "_get_capacity_checkin_live", return_value=_capacity_checkin_stub(checkin)):
            pkg = hca.build_health_context_live()
        assert pkg.capacity_status == "Green"
        assert pkg.capacity_score == 90

    def test_amber_capacity_checkin_produces_amber_status(self):
        checkin = {"capacity_state": "orange"}
        with mock.patch.object(hca, "_get_captains_log_live", return_value=_captains_log_stub(None)), \
             mock.patch.object(hca, "_get_capacity_checkin_live", return_value=_capacity_checkin_stub(checkin)):
            pkg = hca.build_health_context_live()
        assert pkg.capacity_status == "Amber"
        assert pkg.capacity_score == 60


class TestNoStaleCapacityFallback:
    def test_no_todays_checkin_is_unknown_not_a_stale_fallback(self):
        """Core of the fix: no today capacity_checkins row must produce
        Unknown, never silently reuse an old reading (this test's fake
        capacity_checkins fetcher only ever answers the *today* query --
        confirmed by _capacity_checkin_stub's own assert -- so there is no
        "latest regardless of age" path available for it to fall back to)."""
        with mock.patch.object(hca, "_get_captains_log_live", return_value=_captains_log_stub(None)), \
             mock.patch.object(hca, "_get_capacity_checkin_live", return_value=_capacity_checkin_stub(None)):
            pkg = hca.build_health_context_live()
        assert pkg.capacity_status == "Unknown"
        assert pkg.capacity_score is None

    def test_capacity_checkin_service_unreachable_is_unknown_not_a_crash_or_green(self):
        def raising_get(path_and_query: str):
            raise ConnectionError("simulated Supabase outage")
        from core.health.capacity_score import capacity_zone_from_checkin
        with mock.patch.object(hca, "_get_captains_log_live", return_value=_captains_log_stub(None)), \
             mock.patch.object(
                 hca, "_get_capacity_checkin_live",
                 return_value=(raising_get, (lambda: True), capacity_zone_from_checkin),
             ):
            pkg = hca.build_health_context_live()  # must not raise
        assert pkg.capacity_status == "Unknown"


class TestNarrativeFieldsUnaffectedByThisFix:
    def test_pain_mood_energy_still_sourced_from_captains_log_entries(self):
        """Non-capacity fields are a different domain (daily journal) and
        must be untouched by the capacity-source fix."""
        entry = {"pain_score": 7, "energy": "low", "mood": "low", "sleep_quality": "poor"}
        with mock.patch.object(hca, "_get_captains_log_live", return_value=_captains_log_stub(entry)), \
             mock.patch.object(hca, "_get_capacity_checkin_live", return_value=_capacity_checkin_stub(None)):
            pkg = hca.build_health_context_live()
        assert pkg.status_summary.energy == "low"
        assert pkg.status_summary.mood == "low"
        # Capacity is independently Unknown (no checkin), proving the two
        # domains are now decoupled -- a "bad day" captain's-log entry no
        # longer forces a particular capacity reading, and vice versa.
        assert pkg.capacity_status == "Unknown"
