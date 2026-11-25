"""Melbourne reporting-date helpers: DST, ISO week, period conversion."""

from datetime import date, datetime, timedelta, timezone

import pytest

from intelligence.reporting_time import (
    MELBOURNE,
    age_hours,
    format_as_of,
    iso_week_key,
    melbourne_period,
    reporting_date,
)

UTC = timezone.utc


def test_naive_rejected():
    with pytest.raises(ValueError):
        reporting_date(datetime(2026, 11, 25, 6, 20))  # noqa: DTZ001 - naive on purpose


def test_scheduled_run_belongs_to_melbourne_day_not_utc_day():
    # 06:20 AEDT on 25 Nov 2026 is 19:20 UTC on 24 Nov: the old UTC key was a day behind.
    ts = datetime(2026, 11, 25, 6, 20, tzinfo=MELBOURNE)
    assert ts.astimezone(UTC).date() == date(2026, 11, 24)
    assert reporting_date(ts) == date(2026, 11, 25)
    assert reporting_date(ts.astimezone(UTC)) == date(2026, 11, 25)


def test_monday_23_nov_2026_is_w48_in_melbourne_but_w47_by_utc_instant():
    mon = datetime(2026, 11, 23, 6, 20, tzinfo=MELBOURNE)
    assert iso_week_key(reporting_date(mon)) == "2026-W48"
    assert iso_week_key(mon.astimezone(UTC).date()) == "2026-W47"
    assert iso_week_key(date(2026, 12, 31)) == "2026-W53"
    assert iso_week_key(date(2027, 1, 1)) == "2026-W53"


def test_dst_start_4_oct_2026():
    # AEDT starts Sun 4 Oct 2026 at 02:00 (+10 -> +11). Before that the offset is +10: local midnight 4 Oct is 14:00 UTC on 3 Oct.
    assert reporting_date(datetime(2026, 10, 3, 14, 0, tzinfo=UTC)) == date(2026, 10, 4)
    assert reporting_date(datetime(2026, 10, 3, 13, 59, tzinfo=UTC)) == date(2026, 10, 3)
    # 06:20 local on 4 Oct is 19:20 UTC on 3 Oct (+11)
    ts = datetime(2026, 10, 4, 6, 20, tzinfo=MELBOURNE)
    assert ts.astimezone(UTC) == datetime(2026, 10, 3, 19, 20, tzinfo=UTC)
    assert reporting_date(ts.astimezone(UTC)) == date(2026, 10, 4)
    # the day before the change is +10: 06:20 local is 20:20 UTC the previous day
    assert datetime(2026, 10, 3, 6, 20, tzinfo=MELBOURNE).astimezone(UTC) == datetime(2026, 10, 2, 20, 20, tzinfo=UTC)


def test_dst_end_4_apr_2027_and_the_2026_one():
    # AEDT ends Sun 5 Apr 2026 (03:00 -> 02:00) ; check 4 Apr (the date named in the requirement) in both years.
    for yr in (2026, 2027):
        ts = datetime(yr, 4, 4, 6, 20, tzinfo=MELBOURNE)
        assert reporting_date(ts.astimezone(UTC)) == date(yr, 4, 4)
    # Sun 5 Apr 2026: 06:20 is +10 (AEST): 20:20 UTC on 4 Apr
    ts = datetime(2026, 4, 5, 6, 20, tzinfo=MELBOURNE)
    assert ts.astimezone(UTC) == datetime(2026, 4, 4, 20, 20, tzinfo=UTC)
    assert reporting_date(ts.astimezone(UTC)) == date(2026, 4, 5)
    # 15:30 UTC on 4 Apr 2026: AEDT until 03:00 5 Apr = 16:00 UTC; 15:30 UTC is 02:30 AEDT, 5 Apr
    assert reporting_date(datetime(2026, 4, 4, 15, 30, tzinfo=UTC)) == date(2026, 4, 5)
    assert reporting_date(datetime(2026, 4, 4, 12, 59, tzinfo=UTC)) == date(2026, 4, 4)
    assert reporting_date(datetime(2026, 4, 4, 13, 0, tzinfo=UTC)) == date(2026, 4, 5)


def test_period_pair_same_instants_and_melbourne_dates():
    now = datetime(2026, 11, 24, 21, 0, tzinfo=UTC)  # 08:00 AEDT 25 Nov
    start, end = melbourne_period(now, 7)
    assert end == now and start == now - timedelta(days=7)
    assert end.strftime("%Y-%m-%d") == "2026-11-25"
    assert now.strftime("%Y-%m-%d") == "2026-11-24"   # what the UTC value stored before
    assert start.strftime("%Y-%m-%d") == "2026-11-18"


def test_period_span_across_dst_keeps_absolute_duration():
    now = datetime(2026, 10, 6, 3, 0, tzinfo=UTC)
    start, end = melbourne_period(now, 7)   # window crosses the 4 Oct change
    assert end.astimezone(UTC) - start.astimezone(UTC) == timedelta(days=7)


def test_age_and_label():
    a = datetime(2026, 11, 24, 19, 22, tzinfo=UTC)
    assert age_hours(a, a + timedelta(hours=3, minutes=30)) == pytest.approx(3.5)
    assert age_hours(a, a - timedelta(hours=1)) == 0.0
    assert format_as_of(a) == "25 Nov 06:22 AEDT"
