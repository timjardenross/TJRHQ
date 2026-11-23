"""Scrape adapter publication dates (AEMO Market Notices bug).

AEMO notices carry a header like '146578 RECLASSIFY CONTINGENCY 24/11/2026 05:53:57 AM': day/month/year, a time, in NEM time (AEST, fixed UTC+10).
The adapter read slash dates month-first (12/09/2026 -> 9 December), dropped the time and zone, and took a forecast date from the title when it came
first, so 51 stored notices are dated up to months in the future. These tests pin the corrected behaviour on the real page structure.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

bs4 = pytest.importorskip("bs4")

from intelligence.ingestion import scrape_adapter as sa
from intelligence.models import SourceRecord

NOW = datetime(2026, 11, 24, 0, 0, tzinfo=timezone.utc)


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    monkeypatch.setattr(sa, "datetime", _FixedDatetime)


def adapter(name="AEMO Market Notices"):
    return sa.ScrapeAdapter(SourceRecord(source_id="s1", source_name=name, category="critical_infrastructure", priority_rank=1,
                                         url="https://www.aemo.com.au/market-notices", source_type="scrape", jurisdiction="AU",
                                         confidence_weight=0.9, active=True))


def el(html):
    return bs4.BeautifulSoup(f"<div class='item'>{html}</div>", "html.parser").find("div", class_="item")


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


# ── day-first, with time, in the source's own timezone ──────────────────────────────────────────────────────────
def test_a_slash_date_is_day_first_not_month_first():
    # production bug: '12/09/2026 08:57:00 PM' (12 September) was stored as 9 December
    got = adapter()._extract_date(el("146001MINIMUM SYSTEM LOAD12/09/2026 08:57:00 PM<h3>Actual MSL1 condition in the SA Region</h3>"))
    assert got.month == 9 and got.day == 12
    assert got == utc(2026, 9, 12, 10, 57, 0)                       # 20:57 AEST is 10:57 UTC


def test_the_time_of_day_is_kept_and_nem_time_is_utc_plus_10():
    got = adapter()._extract_date(el("146578RECLASSIFY CONTINGENCY24/11/2026 05:53:57 AM<h3>Cancellation of a Non-Credible Contingency Event</h3>"))
    assert got == utc(2026, 11, 23, 19, 53, 57)                      # 05:53 AEST on the 24th is 19:53 UTC on the 23rd


@pytest.mark.parametrize("text,expected", [
    ("10/11/2026 12:05:00 AM", utc(2026, 11, 9, 14, 5)),            # 12:05 AM is just after midnight
    ("10/11/2026 12:30:00 PM", utc(2026, 11, 10, 2, 30)),           # 12:30 PM is half past noon
    ("10/11/2026 11:59:59 PM", utc(2026, 11, 10, 13, 59, 59)),
    ("10/11/2026 17:45", utc(2026, 11, 10, 7, 45)),                  # 24-hour clock, no seconds
    ("10/11/2026", utc(2026, 11, 9, 14, 0)),                         # date only: midnight AEST
])
def test_time_formats(text, expected):
    assert adapter()._extract_date(el(f"1460XX GENERAL NOTICE{text}<h3>Notice</h3>")) == expected


def test_a_source_without_a_stated_timezone_stays_utc():
    got = adapter("Some Other Source")._extract_date(el("Release 10/11/2026 05:30:00 AM"))
    assert got == utc(2026, 11, 10, 5, 30)


# ── which date wins ─────────────────────────────────────────────────────────────────────────────────────────────
def test_the_header_date_beats_a_forecast_date_later_in_the_title():
    got = adapter()._extract_date(el("146100RESERVE NOTICE10/11/2026 07:05:00 AM<h3>Forecast Lack Of Reserve Level 1 in the NSW Region on 12/11/2026</h3>"))
    assert got == utc(2026, 11, 9, 21, 5)                            # the notice's own issue time, not 12 November


def test_a_forecast_date_with_no_header_is_not_a_publication_date():
    # 12/10/2099 is far ahead of the clock: an event date, so no publication date rather than a future one
    assert adapter()._extract_date(el("<h3>Forecast Lack Of Reserve Level 1 in the NSW Region on 12/10/2099</h3>")) is None


def test_a_recent_event_date_with_no_header_is_accepted():
    assert adapter()._extract_date(el("<h3>Actual MSL1 condition in the SA Region on 22/11/2026</h3>")) == utc(2026, 11, 21, 14, 0)


@pytest.mark.parametrize("text", ["31/02/2026", "13/13/2026", "00/10/2026", "10/11/2026 13:00:00 PM"])
def test_impossible_dates_are_not_invented(text):
    assert adapter()._extract_date(el(f"Notice {text}")) is None


# ── other formats unchanged ─────────────────────────────────────────────────────────────────────────────────────
def test_iso_dates_are_not_flipped():
    # dateutil's dayfirst=True would read 2026-11-12 as 12 December
    assert adapter("Some Other Source")._extract_date(el("Posted 2026-11-12")) == utc(2026, 11, 12)


def test_named_month_dates_still_work():
    assert adapter("Some Other Source")._extract_date(el("Released 5 November 2026 by the regulator")) == utc(2026, 11, 5)


def test_no_date_is_none():
    assert adapter()._extract_date(el("<h3>Notice with no date at all</h3>")) is None


# ── end to end on the real page structure ───────────────────────────────────────────────────────────────────────
PAGE = """<html><body><div class="items">
<div class="item"><span>146578</span><span>RECLASSIFY CONTINGENCY</span><span>24/11/2026 05:53:57 AM</span>
<h3>Cancellation of a Non-Credible Contingency Event: Gordon - Chapel St No 1 220kV line in TAS1 due to Lightning.</h3>
<p>Cancellation time: 24/11/2026 04:53</p></div>
<div class="item"><span>146000</span><span>RESERVE NOTICE</span><span>12/09/2026 08:57:00 PM</span>
<h3>Forecast Lack Of Reserve Level 1 (LOR1) in the NSW Region on 12/10/2026</h3><p>Forecast LOR1.</p></div>
</div></body></html>"""


def test_items_extracted_from_the_page_carry_the_corrected_dates():
    items = adapter()._extract_items(bs4.BeautifulSoup(PAGE, "html.parser"))
    by_title = {i.raw_title.split(":")[0].split(" (")[0]: i for i in items}
    assert by_title["Cancellation of a Non-Credible Contingency Event"].published_at == utc(2026, 11, 23, 19, 53, 57)
    assert by_title["Forecast Lack Of Reserve Level 1"].published_at == utc(2026, 9, 12, 10, 57)       # not 10 December, not 12 October
    assert all(i.published_at <= NOW for i in items)
