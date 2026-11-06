"""BOM adapter: real NSW state-list snapshot + a marked-synthetic detail page (offline)."""

from __future__ import annotations

import pytest

from intelligence.ingestion.emergency_alert_adapters import bom_warnings
from tests.emergency_alert_helpers import (  # noqa: F401
    assert_in_schema,
    block_network,
    by,
    fixture_bytes,
    fixture_meta,
    fixture_text,
)

pytestmark = pytest.mark.usefixtures("block_network")

FIRE_LINK = "http://reg.bom.gov.au/nsw/warnings/fire.shtml"


@pytest.fixture(scope="module")
def raw():
    return fixture_bytes("bom_nsw", "feed.xml")


def _detail_for(link, pubdate_raw):
    return bom_warnings.parse_detail(fixture_text("bom_nsw", "detail.html"))


def test_detail_page_fixture_is_marked_synthetic():
    feeds = fixture_meta("bom_nsw")["feeds"]
    assert feeds["detail.html"]["synthetic"] is True
    assert feeds["feed.xml"]["synthetic"] is False


def test_list_snapshot_totals(raw):
    alerts = bom_warnings.parse_state_feed("NSW", raw)
    assert raw.count(b"<item>") == 7
    assert len(alerts) == 4
    assert by(alerts, "severity") == {"unknown": 4}  # BOM carries no AWS tier
    assert by(alerts, "alert_type") == {"bushfire": 1, "flood": 3}
    assert by(alerts, "closed") == {False: 3, True: 1}  # "Final ..." marks a cancelled warning
    assert_in_schema(alerts)


def test_stable_event_key_for_a_known_item(raw):
    alert = next(a for a in bom_warnings.parse_state_feed("NSW", raw) if a.event_key == FIRE_LINK)
    assert alert.source_key == "bom_nsw" and alert.jurisdiction == "NSW"
    assert alert.headline.startswith("Fire Weather Warning for Greater Hunter")
    assert alert.updated_at_src == "2026-11-06T05:08:23+00:00"


def test_excluded_and_unmatched_products_are_dropped(raw):
    headlines = " | ".join(a.headline for a in bom_warnings.parse_state_feed("NSW", raw))
    for dropped in ("Marine Wind", "Sheep Graziers", "Hazardous Surf"):
        assert dropped in raw.decode() and dropped not in headlines


def test_detail_parse_from_page_fixture():
    detail = bom_warnings.parse_detail(fixture_text("bom_nsw", "detail.html"))
    assert detail["issued_at"] == "2026-11-06T09:34:00+11:00"  # AEDT offset applied, not stored as UTC wall-clock
    body = detail["body"]
    assert "Hot, dry and windy" in body and "& may reach extreme" in body
    assert "Example Gauge" not in body  # river-height tables are stripped
    assert "Check conditions before you travel." in body
    assert "Copyright" not in body and "Warnings" not in body  # outside the content div


def test_list_with_detail_enrichment(raw):
    alert = next(a for a in bom_warnings.parse_state_feed("NSW", raw, detail_for=_detail_for) if a.event_key == FIRE_LINK)
    assert alert.issued_at == "2026-11-06T09:34:00+11:00"
    assert "Fire Weather Warning for the Greater Hunter" in alert.description and "Hot, dry and windy" in alert.description
    assert alert.raw_text.endswith(FIRE_LINK)


def test_detail_without_content_div_degrades_to_title_only():
    assert bom_warnings.parse_detail("<html><body>nope</body></html>") == {"issued_at": None, "issued_local": None, "body": None}


def test_fetch_is_http_get_plus_parse(raw, monkeypatch):
    monkeypatch.setattr(bom_warnings, "_http_get_bom", lambda url: raw if url.endswith(".xml") else fixture_bytes("bom_nsw", "detail.html"))
    monkeypatch.setattr(bom_warnings, "_detail_cache", {})
    assert bom_warnings.nsw.fetch() == bom_warnings.parse_state_feed("NSW", raw, detail_for=_detail_for)


# ---- "Issued at" wordings seen in production (bom_* rows, 2026-11-06): 57 of 91 had issued_at NULL ----

@pytest.mark.parametrize("line,aware,local", [
    ("Issued at 9:34 am AEST on Thursday 27 August 2026", "2026-08-27T09:34:00+10:00", "2026-08-27T09:34:00"),
    ("Issued at 10:59 am AEST on Thursday 5 November 2026", "2026-11-05T10:59:00+10:00", "2026-11-05T10:59:00"),
    # bom_nsw / bom_act: bare EDT (= Australian Eastern Daylight Time) and a trailing full stop
    ("Issued at 4:08 pm EDT on Friday 6 November 2026.", "2026-11-06T16:08:00+11:00", "2026-11-06T16:08:00"),
    ("Issued at 7:15 am EST on Monday 6 July 2026.", "2026-07-06T07:15:00+10:00", "2026-07-06T07:15:00"),
    # long timezone name
    ("Issued at 11:51 am Australian Eastern Daylight Time on Friday 6 November 2026", "2026-11-06T11:51:00+11:00", "2026-11-06T11:51:00"),
    ("Issued at 12:05 am Australian Central Daylight Time on Monday 2 November 2026", "2026-11-02T00:05:00+10:30", "2026-11-02T00:05:00"),
    ("Issued at 9:00 pm ACST on Monday 2 November 2026", "2026-11-02T21:00:00+09:30", "2026-11-02T21:00:00"),
    ("Issued at 12:30 pm AWST on Friday 6 November 2026", "2026-11-06T12:30:00+08:00", "2026-11-06T12:30:00"),
    # bom_wa: no timezone at all, weekday with a comma -> naive only
    ("Issued at 2:42 pm Friday, 6 November 2026.", None, "2026-11-06T14:42:00"),
])
def test_issued_line_wordings(line, aware, local):
    assert bom_warnings._parse_issued(f"<p>{line}</p>") == (aware, local)
    assert bom_warnings._parse_bom_issued_at(f"<p>{line}</p>") == aware


@pytest.mark.parametrize("line", [
    "Issued at 13:05 pm AEST on Friday 6 November 2026",
    "Issued at 9:34 am AEST on Friday 31 Smarch 2026",
    "Issued at 9:34 am AEST on Friday 31 February 2026",
    "Issued soon",
])
def test_unparseable_issued_lines_are_none_not_guessed(line):
    assert bom_warnings._parse_issued(f"<p>{line}</p>") == (None, None)


def test_unknown_timezone_word_is_not_guessed():
    aware, local = bom_warnings._parse_issued("<p>Issued at 9:34 am XYZT on Friday 6 November 2026</p>")
    assert aware is None and local == "2026-11-06T09:34:00"


def test_tags_inside_the_issued_line_are_ignored():
    assert bom_warnings._parse_issued("<p>Issued at <b>4:08 pm</b> EDT on Friday 6 November 2026.</p>")[0] == "2026-11-06T16:08:00+11:00"


def _item_feed(title):
    return (f'<rss><channel><item><title>{title}</title><link>http://reg.bom.gov.au/x/y.shtml</link>'
            f"<guid>g1</guid><pubDate>Fri, 06 Nov 2026 06:43:10 GMT</pubDate></item></channel></rss>").encode()


def _detail(line):
    return lambda link, pub: bom_warnings.parse_detail(f'<div id="content"><p>{line}</p><p>Body</p><!-- End: Content --></div>')


def test_wa_line_without_timezone_uses_the_states_fixed_offset():
    (alert,) = bom_warnings.parse_state_feed("WA", _item_feed("Flood Warning for X"), detail_for=_detail("Issued at 2:42 pm Friday, 6 November 2026."))
    assert alert.issued_at == "2026-11-06T14:42:00+08:00"  # matches that alert's pubDate, 06:43Z = 14:43 AWST


@pytest.mark.parametrize("state,offset", [("QLD", "+10:00"), ("NT", "+09:30")])
def test_other_no_dst_states_get_their_constant_offset(state, offset):
    (alert,) = bom_warnings.parse_state_feed(state, _item_feed("Flood Warning for X"), detail_for=_detail("Issued at 2:42 pm Friday, 6 November 2026."))
    assert alert.issued_at == f"2026-11-06T14:42:00{offset}"


@pytest.mark.parametrize("state,offset", [("NSW", "+11:00"), ("ACT", "+11:00"), ("VIC", "+11:00"), ("SA", "+10:30"), ("TAS", "+11:00")])
def test_dst_states_with_no_timezone_use_the_zone_offset_for_that_date(state, offset):
    (alert,) = bom_warnings.parse_state_feed(state, _item_feed("Flood Warning for X"), detail_for=_detail("Issued at 2:42 pm Friday, 6 November 2026."))
    assert alert.issued_at == f"2026-11-06T14:42:00{offset}"


@pytest.mark.parametrize("state,date,offset", [("SA", "5 September 2026", "+09:30"), ("SA", "11 October 2026", "+10:30"), ("NSW", "3 July 2026", "+10:00")])
def test_the_zone_offset_follows_daylight_saving_by_date(state, date, offset):
    (alert,) = bom_warnings.parse_state_feed(state, _item_feed("Flood Warning for X"), detail_for=_detail(f"Issued at 7:00 pm Saturday, {date}."))
    assert alert.issued_at.endswith(offset)


def test_missing_zone_data_leaves_issued_at_unparsed(monkeypatch):
    monkeypatch.setitem(bom_warnings._DST_STATE_ZONES, "NSW", "Not/AZone")
    (alert,) = bom_warnings.parse_state_feed("NSW", _item_feed("Flood Warning for X"), detail_for=_detail("Issued at 2:42 pm Friday, 6 November 2026."))
    assert alert.issued_at is None


def test_a_named_timezone_wins_over_the_state_default():
    (alert,) = bom_warnings.parse_state_feed("WA", _item_feed("Flood Warning for X"), detail_for=_detail("Issued at 2:42 pm AEDT on Friday 6 November 2026"))
    assert alert.issued_at == "2026-11-06T14:42:00+11:00"
