"""TasALERT adapter (intelligence/ingestion/emergency_alert_adapters/tas_fire.py):
maps the LIST "TasAlert Warnings" layer to canonical alerts without guessing
severity, and drops planned burns and already-expired records."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence.ingestion.emergency_alert_adapters import tas_fire

NOW_MS = 1_793_600_000_000  # 2026-11-02, inside the live record's window


def _feature(**attrs) -> dict:
    base = {
        "ALERT_TYPE": "Watch and Act", "EVENT": "Bushfire", "ALERT_SUMMARY": "Bushfire Watch and Act - Test Town",
        "AREA_DESCRIPTION": "Test Town and surrounds", "ALERT_INSTRUCTIONS": "Prepare to leave",
        "FULL_DESCRIPTION": "A fire is burning near Test Town.", "IDENTIFIER": "id-1",
        "TASALERT_LINK": "https://alert.tas.gov.au/?id=abc",
        # The layer's dates are Hobart wall-clock written as UTC (measured 2026-11-06), so a
        # record that is really live for another hour is written ~11 h further ahead than the
        # real instant: give the synthetic record a full day so it is unambiguously live.
        "EFFECTIVE_FROM_DATE": NOW_MS - 3_600_000, "EXPIRES_DATE": NOW_MS + 86_400_000,
    }
    base.update(attrs)
    return {"attributes": base, "geometry": {"x": 146.9856, "y": -42.9727}}


def test_maps_a_watch_and_act_with_coordinates_and_expiry():
    [a] = tas_fire.parse({"features": [_feature()]}, now_ms=NOW_MS)
    assert (a.source_key, a.jurisdiction, a.severity, a.alert_type) == ("tas_fire", "TAS", "watch_and_act", "bushfire")
    assert a.event_key == "id-1" and a.canonical_url == "https://alert.tas.gov.au/?id=abc"
    assert (a.latitude, a.longitude) == (-42.9727, 146.9856)
    assert a.location == "Test Town and surrounds" and a.expiry and a.issued_at
    assert "Prepare to leave" in a.raw_text


@pytest.mark.parametrize("label,expected", [
    ("Emergency Warning", "emergency_warning"),
    ("Watch & Act", "watch_and_act"),
    ("Advice", "advice"),
])
def test_severity_only_from_stated_tier(label, expected):
    [a] = tas_fire.parse({"features": [_feature(ALERT_TYPE=label, ALERT_SUMMARY="x")]}, now_ms=NOW_MS)
    assert a.severity == expected


def test_unrecognised_type_stays_unknown_not_guessed():
    [a] = tas_fire.parse({"features": [_feature(ALERT_TYPE="Smoke Alert", EVENT="Smoke Alert", ALERT_SUMMARY="Smoke near Test Town")]}, now_ms=NOW_MS)
    assert a.severity == "unknown"


def test_planned_burn_is_dropped():
    f = _feature(ALERT_TYPE="Smoke Alert", FULL_DESCRIPTION="There is a planned backburn at Fletchers Hill.")
    assert tas_fire.parse({"features": [f]}, now_ms=NOW_MS) == []


def test_expired_record_is_dropped():
    assert tas_fire.parse({"features": [_feature(EXPIRES_DATE=NOW_MS - 1)]}, now_ms=NOW_MS) == []


def test_missing_headline_is_skipped_and_empty_payload_is_empty():
    assert tas_fire.parse({"features": [_feature(ALERT_SUMMARY="", EVENT="", ALERT_TYPE="")]}, now_ms=NOW_MS) == []
    assert tas_fire.parse({}, now_ms=NOW_MS) == []


def test_service_error_raises_so_the_heartbeat_fails_instead_of_looking_empty():
    with pytest.raises(RuntimeError):
        tas_fire.parse({"error": {"code": 500, "message": "boom"}}, now_ms=NOW_MS)


def test_no_longer_flagged_not_implemented():
    # A NOT_YET_IMPLEMENTED marker makes run_source heartbeat 'skipped'.
    assert not hasattr(tas_fire, "NOT_YET_IMPLEMENTED")


def test_live_record_shape_parses_to_nothing_because_it_is_a_planned_burn():
    live = {"features": [{"attributes": {
        "ALERT_TYPE": "Smoke Alert", "ALERT_SUMMARY": "Bushfire Smoke Alert - Judbury - Avoid smoke",
        "AREA_DESCRIPTION": "Judbury and surrounds", "ALERT_INSTRUCTIONS": "Unknown",
        "FULL_DESCRIPTION": "There is a planned backburn at Fletchers Hill, Ranelagh.There is no threat to communities.",
        "IDENTIFIER": "042685-21102026-89177", "EVENT": "Smoke Alert",
        "TASALERT_LINK": "https://alert.tas.gov.au/?id=3f6b4c7d", "EFFECTIVE_FROM_DATE": 1793552370000,
        "EXPIRES_DATE": 1793649367000}, "geometry": {"x": 146.98556, "y": -42.97268}}]}
    assert tas_fire.parse(live, now_ms=1793560000000) == []


def test_layer_dates_are_hobart_wall_clock_not_utc_instants():
    """MEASURED 2026-11-06: the layer stores local Hobart time as if it were UTC (issued_at landed ~10.8 h
    after first seen). Epoch 2026-11-06T16:18:14 'UTC' is really 16:18:14 AEDT (+11:00)."""
    epoch_ms = 1_793_981_894_000  # 2026-11-06T16:18:14 read as a UTC instant
    assert tas_fire._iso(epoch_ms) == "2026-11-06T16:18:14+11:00"
    assert tas_fire._iso(1_783_000_000_000).endswith("+10:00")  # July: AEST, daylight saving handled by the zone
    assert tas_fire._iso(None) is None


def test_expiry_check_uses_the_real_instant_so_it_no_longer_lags_by_eleven_hours():
    """A record whose wall-clock expiry is 10 h after 'now' (as UTC) is really expired already in November
    (AEDT is +11): the old check kept it for ~11 more hours."""
    feature = _feature(EXPIRES_DATE=NOW_MS + 10 * 3_600_000)
    assert tas_fire.parse({"features": [feature]}, now_ms=NOW_MS) == []
    live = _feature(EXPIRES_DATE=NOW_MS + 12 * 3_600_000)
    assert len(tas_fire.parse({"features": [live]}, now_ms=NOW_MS)) == 1
