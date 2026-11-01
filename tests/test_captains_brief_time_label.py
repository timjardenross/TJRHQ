"""The brief header time label must match the clock the job fired on (OR_INTEL_SCHEDULE_TZ, default
Australia/Melbourne), not Brisbane's fixed AEST: a 07:00 AEDT job printed "06:00 AEST"."""
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from intelligence import captains_brief as cb

BRISBANE = ZoneInfo("Australia/Brisbane")


def _at(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=BRISBANE)


def test_label_is_melbourne_local_time_in_daylight_saving():
    # 07:00 in Melbourne on 2026-10-16 (AEDT, UTC+11) is 06:00 in Brisbane (UTC+10)
    assert cb._clock_label(_at(2026, 10, 16, 6, 0)) == "07:00 AEDT"


def test_label_is_aest_outside_daylight_saving():
    assert cb._clock_label(_at(2026, 6, 16, 7, 0)) == "07:00 AEST"


def test_label_follows_the_schedule_zone_setting(monkeypatch):
    monkeypatch.setenv("OR_INTEL_SCHEDULE_TZ", "Australia/Brisbane")
    assert cb._clock_label(_at(2026, 10, 16, 6, 0)) == "06:00 AEST"


def test_label_falls_back_to_the_old_fixed_label_on_a_bad_zone(monkeypatch):
    monkeypatch.setenv("OR_INTEL_SCHEDULE_TZ", "Not/AZone")
    assert cb._clock_label(_at(2026, 10, 16, 6, 0)) == "06:00 AEST"


def _patched(now):
    return [
        patch.object(cb, "_now_aest", return_value=now),
        patch.object(cb, "_get_latest_ori_brief", return_value=None),
        patch.object(cb, "_get_capacity_today", return_value=None),
        patch.object(cb, "_get_recent_signals", return_value=[]),
        patch.object(cb, "_get_infra_verification", return_value=None),
        patch.object(cb, "_get_todays_morning_brief_text", return_value=None),
        patch.object(cb, "build_daily_digest", None),
    ]


@pytest.mark.parametrize("builder,marker", [
    (lambda: cb.generate_morning_brief(), "Stardate 2026.289 · 07:00 AEDT"),
    (lambda: cb.generate_eod_summary(), "<i>18:00 AEDT</i>"),
])
def test_headers_show_the_local_zone_label(builder, marker):
    now = _at(2026, 10, 16, 6, 0) if "07:00" in marker else _at(2026, 10, 16, 17, 0)
    ctx = _patched(now)
    for c in ctx:
        c.start()
    try:
        text = builder()
    finally:
        for c in ctx:
            c.stop()
    assert marker in text
    assert " AEST" not in text.split("\n")[1]


def test_midday_header_shows_the_local_zone_label():
    with patch.object(cb, "_now_aest", return_value=_at(2026, 10, 16, 11, 30)):
        text = cb.generate_midday_update([])
    assert "MIDDAY UPDATE — 12:30 AEDT" in text
