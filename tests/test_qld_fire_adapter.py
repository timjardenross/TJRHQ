"""QLD Fire Department adapter against a real captured Bushfire Warnings snapshot (offline)."""

from __future__ import annotations

import pytest

from intelligence.ingestion.emergency_alert_adapters import qld_fire
from intelligence.ingestion.emergency_alert_adapters.base import DropLedger
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
    alert = next(a for a in qld_fire.parse(feed) if a.headline.startswith("AVOID SMOKE - Wonbah"))
    assert alert.event_key.startswith("qld:") and len(alert.event_key) == 28
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


# ---- stable incident key (re-issues of one warning are one row) ----

def _qld_feature(unique_id, area, level="Advice", when="2026-11-06T11:41:53+10:00", title="PREPARE TO LEAVE - Teelah - fire as at 11:41am Friday, 6 November"):
    return {"properties": {"UniqueID": unique_id, "WarningArea": area, "WarningLevel": level, "ItemDateTimeLocal_ISO": when, "WarningTitle": title,
                           "PublishDateLocal_ISO": when, "CallToAction": "Prepare", "WarningText": "t", "Latitude": -27.0, "Longitude": 152.0}}


def test_reissues_of_a_warning_share_one_event_key_whatever_their_unique_id():
    first = qld_fire.parse({"features": [_qld_feature("WARN-1", "Teelah and surrounds", when="2026-11-06T09:00:00+10:00")]})[0]
    later = qld_fire.parse({"features": [_qld_feature("WARN-2", "Teelah  AND Surrounds ", level="Watch and Act", when="2026-11-06T15:30:00+10:00")]})[0]
    assert first.event_key == later.event_key


def test_a_different_area_or_a_different_day_is_a_different_incident():
    base = qld_fire.parse({"features": [_qld_feature("WARN-1", "Teelah")]})[0].event_key
    assert base != qld_fire.parse({"features": [_qld_feature("WARN-2", "Somme")]})[0].event_key
    assert base != qld_fire.parse({"features": [_qld_feature("WARN-3", "Teelah", when="2026-11-07T00:10:00+10:00")]})[0].event_key


def test_missing_area_or_date_falls_back_to_the_unique_id():
    assert qld_fire.parse({"features": [_qld_feature("WARN-9", None)]})[0].event_key == "WARN-9"
    assert qld_fire.parse({"features": [_qld_feature("WARN-8", "Teelah", when=None)]})[0].event_key == "WARN-8"


def test_two_warnings_for_one_area_and_day_collapse_to_the_highest_tier_and_are_counted():
    ledger = DropLedger()
    features = [_qld_feature("WARN-1", "Teelah", level="Advice"), _qld_feature("WARN-2", "Teelah", level="Emergency Warning"), _qld_feature("WARN-3", "Teelah", level="Watch and Act")]
    alerts = qld_fire.parse({"features": features}, ledger)
    assert [a.severity for a in alerts] == ["emergency_warning"]
    assert ledger.counts["excluded_superseded"] == 2 and ledger.items_seen == len(alerts) + ledger.excluded_total + ledger.invalid_total
