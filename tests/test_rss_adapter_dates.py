"""RSS/Atom entry dates (Twilio Status bug).

Statuspage Atom feeds put the scheduled-maintenance *start* in <published> (e.g. 2027-02-19) and the announcement time in <updated> (2026-11-19).
The adapter preferred <published>, so all 240 scheduled-maintenance rows were stored with dates up to 3 months ahead.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

feedparser = pytest.importorskip("feedparser")

from intelligence.ingestion import rss_adapter as ra
from intelligence.models import SourceRecord

NOW = datetime(2026, 11, 23, 22, 0, tzinfo=UTC)


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    monkeypatch.setattr(ra, "datetime", _FixedDatetime)


def adapter():
    return ra.RSSAdapter(SourceRecord(source_id="s1", source_name="Twilio Status", category="cloud_technology", priority_rank=3,
                                      url="https://status.twilio.com", source_type="rss", jurisdiction="GLOBAL",
                                      confidence_weight=0.85, active=True))


def entry(published=None, updated=None):
    parts = []
    if published:
        parts.append(f"<published>{published}</published>")
    if updated:
        parts.append(f"<updated>{updated}</updated>")
    xml = (f'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>t</title><entry><id>x</id><title>e</title>'
           f'{"".join(parts)}</entry></feed>')
    return feedparser.parse(xml).entries[0]


def utc(*a):
    return datetime(*a, tzinfo=UTC)


def test_scheduled_maintenance_is_dated_by_the_announcement_not_the_start():
    # real Twilio entry: maintenance 19 Feb 2027, announced 19 Nov 2026
    got = adapter()._parse_date(entry("2027-02-19T15:00:00-08:00", "2026-11-19T04:55:55-08:00"))
    assert got == utc(2026, 11, 19, 12, 55, 55)


def test_maintenance_starting_in_a_few_days_is_still_the_announcement_time():
    got = adapter()._parse_date(entry("2026-11-30T15:00:00-08:00", "2026-11-23T01:18:07-08:00"))
    assert got == utc(2026, 11, 23, 9, 18, 7)


def test_a_normal_incident_keeps_its_published_time():
    got = adapter()._parse_date(entry("2026-11-20T10:00:00-08:00", "2026-11-21T09:00:00-08:00"))
    assert got == utc(2026, 11, 20, 18, 0)


def test_a_few_hours_of_clock_skew_is_not_discarded():
    assert adapter()._parse_date(entry("2026-11-24T08:00:00Z", None)) == utc(2026, 11, 24, 8, 0)


def test_future_published_and_no_updated_is_none_not_a_future_date():
    assert adapter()._parse_date(entry("2027-02-19T15:00:00-08:00", None)) is None


def test_everything_in_the_future_is_none():
    assert adapter()._parse_date(entry("2027-02-19T15:00:00Z", "2027-02-20T00:00:00Z")) is None


def test_updated_only_is_used():
    assert adapter()._parse_date(entry(None, "2026-11-22T00:00:00Z")) == utc(2026, 11, 22)


def test_no_dates_is_none():
    assert adapter()._parse_date(entry()) is None


def test_the_parsed_time_is_utc_whatever_the_server_timezone(monkeypatch):
    # feedparser *_parsed values are UTC; time.mktime would shift them by the local offset
    import time
    monkeypatch.setenv("TZ", "Australia/Melbourne")
    time.tzset()
    try:
        assert adapter()._parse_date(entry("2026-11-20T00:00:00Z")) == utc(2026, 11, 20)
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()
