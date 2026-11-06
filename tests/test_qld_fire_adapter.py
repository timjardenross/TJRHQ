"""QLD Fire Department adapter against a real captured Bushfire Warnings snapshot (offline)."""

from __future__ import annotations

import pytest

from intelligence.ingestion.emergency_alert_adapters import qld_fire
from tests.emergency_alert_helpers import (  # noqa: F401
    assert_in_schema,
    block_network,
    by,
    fixture_json,
)

pytestmark = pytest.mark.usefixtures("block_network")


@pytest.fixture(scope="module")
def feed():
    return fixture_json("qld_fire", "feed.json")


def test_snapshot_totals(feed):
    alerts = qld_fire.parse(feed)
    assert len(feed["features"]) == 43
    assert len(alerts) == 2
    assert by(alerts, "severity") == {"advice": 2}
    assert by(alerts, "alert_type") == {"bushfire": 2}
    assert_in_schema(alerts)


def test_stable_event_key_for_a_known_item(feed):
    alert = next(a for a in qld_fire.parse(feed) if a.event_key == "WARN-13196")
    assert alert.headline.startswith("AVOID SMOKE - Wonbah")
    assert alert.canonical_url is None  # shared dashboard page would collide on the unique index
    assert alert.issued_at and alert.expiry


def test_information_tier_is_excluded(feed):
    info_ids = {f["properties"]["UniqueID"] for f in feed["features"] if f["properties"]["WarningLevel"] == "Information"}
    kept = {a.event_key for a in qld_fire.parse(feed)}
    assert len(info_ids) == 41 and not (kept & info_ids)


def _feature(level="Advice", call_to_action="Prepare", uid="WARN-1"):
    return {"properties": {"WarningLevel": level, "CallToAction": call_to_action, "UniqueID": uid, "WarningTitle": "T"}}


def test_hazard_reduction_call_to_action_is_excluded():
    assert qld_fire.parse({"features": [_feature(call_to_action="Avoid Smoke (Hazard Reduction Burn)")]}) == []


@pytest.mark.parametrize("level,expected", [("Advice", "advice"), ("Watch and Act", "watch_and_act"), ("Emergency Warning", "emergency_warning"), ("Odd", "unknown")])
def test_severity_mapping(level, expected):
    assert qld_fire.parse({"features": [_feature(level=level)]})[0].severity == expected


def test_fetch_is_http_get_plus_parse(feed, monkeypatch):
    monkeypatch.setattr(qld_fire, "http_get_json", lambda url: feed)
    assert qld_fire.fetch() == qld_fire.parse(feed)
