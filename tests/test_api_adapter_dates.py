"""API adapter feed-entry dates are UTC whatever timezone the host runs in.

feedparser's *_parsed fields are UTC struct_times. time.mktime reads them as host-local time, so on a Melbourne host every date was shifted
10-11 hours (the audit's ~10h RSS lag floor); calendar.timegm does not depend on the host.
"""
from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

feedparser = pytest.importorskip("feedparser")

from intelligence.ingestion.api_adapter import APIAdapter
from intelligence.models import SourceRecord


def adapter():
    return APIAdapter(SourceRecord(source_id="s1", source_name="Some Status", category="cloud_technology", priority_rank=2,
                                   url="https://status.example.com", source_type="api", jurisdiction="GLOBAL", confidence_weight=0.8,
                                   active=True))


def entry(published):
    xml = (f'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>t</title><entry><id>x</id><title>e</title>'
           f"<published>{published}</published></entry></feed>")
    return feedparser.parse(xml).entries[0]


@pytest.mark.parametrize("tz", ["UTC", "Australia/Melbourne", "America/Los_Angeles"])
def test_feed_entry_dates_do_not_depend_on_the_host_timezone(monkeypatch, tz):
    monkeypatch.setenv("TZ", tz)
    time.tzset()
    try:
        assert adapter()._parse_date_from_entry(entry("2026-11-20T00:00:00Z")) == datetime(2026, 11, 20, tzinfo=UTC)
        assert adapter()._parse_date_from_entry(entry("2026-11-20T10:30:00+11:00")) == datetime(2026, 11, 19, 23, 30, tzinfo=UTC)
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()
