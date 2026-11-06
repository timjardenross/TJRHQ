"""NSW RFS adapter against a real captured Major Incidents snapshot (offline)."""

from __future__ import annotations

import pytest

from intelligence.ingestion.emergency_alert_adapters import nsw_rfs
from tests.emergency_alert_helpers import (  # noqa: F401
    assert_in_schema,
    block_network,
    by,
    fixture_json,
)

pytestmark = pytest.mark.usefixtures("block_network")

KNOWN_KEY = "https://incidents.rfs.nsw.gov.au/api/v1/incidents/684405"


@pytest.fixture(scope="module")
def feed():
    return fixture_json("nsw_rfs", "feed.json")


def test_snapshot_totals(feed):
    alerts = nsw_rfs.parse(feed)
    assert len(feed["features"]) == 23
    assert len(alerts) == 7
    assert by(alerts, "severity") == {"advice": 7}
    assert by(alerts, "alert_type") == {"bushfire": 7}
    assert_in_schema(alerts)


def test_stable_event_key_for_a_known_item(feed):
    alert = next(a for a in nsw_rfs.parse(feed) if a.event_key == KNOWN_KEY)
    assert alert.headline == "CASTLEROCK RD, CASTLE ROCK"
    assert alert.canonical_url == KNOWN_KEY
    assert alert.source_key == "nsw_rfs" and alert.jurisdiction == "NSW"
    assert alert.updated_at_src == "2026-11-05T21:09:00"


def test_not_applicable_tier_is_excluded(feed):
    not_applicable = {f["properties"]["guid"] for f in feed["features"] if f["properties"]["category"] == "Not Applicable"}
    kept = {a.event_key for a in nsw_rfs.parse(feed)}
    assert len(not_applicable) == 16 and not (kept & not_applicable)
    assert kept | not_applicable == {f["properties"]["guid"] for f in feed["features"]}


def _feature(category="Advice", type_="Bush Fire", guid="https://example.invalid/1"):
    return {"properties": {"title": "T", "guid": guid, "category": category,
                           "description": f"ALERT LEVEL: {category} <br />LOCATION: Somewhere <br />STATUS: Going <br />TYPE: {type_} <br />",
                           "pubDate": "06/11/2026 3:04:00 PM"}, "geometry": None}


def test_hazard_reduction_type_is_excluded_even_at_advice_level():
    assert nsw_rfs.parse({"features": [_feature(type_="Hazard Reduction"), _feature(guid="https://example.invalid/2")]})[0].event_key == "https://example.invalid/2"
    assert len(nsw_rfs.parse({"features": [_feature(type_="Hazard Reduction")]})) == 0


@pytest.mark.parametrize("category,expected", [("Advice", "advice"), ("Watch and Act", "watch_and_act"), ("Emergency Warning", "emergency_warning"), ("Something New", "unknown")])
def test_severity_mapping(category, expected):
    assert nsw_rfs.parse({"features": [_feature(category=category)]})[0].severity == expected


def test_fetch_is_http_get_plus_parse(feed, monkeypatch):
    monkeypatch.setattr(nsw_rfs, "http_get_json", lambda url: feed)
    assert nsw_rfs.fetch() == nsw_rfs.parse(feed)
