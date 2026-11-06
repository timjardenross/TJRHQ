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
    assert bom_warnings.parse_detail("<html><body>nope</body></html>") == {"issued_at": None, "body": None}


def test_fetch_is_http_get_plus_parse(raw, monkeypatch):
    monkeypatch.setattr(bom_warnings, "_http_get_bom", lambda url: raw if url.endswith(".xml") else fixture_bytes("bom_nsw", "detail.html"))
    monkeypatch.setattr(bom_warnings, "_detail_cache", {})
    assert bom_warnings.nsw.fetch() == bom_warnings.parse_state_feed("NSW", raw, detail_for=_detail_for)
