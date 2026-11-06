"""TAS adapter against a real captured TasALERT layer snapshot (offline). Synthetic-input tests are in test_tas_fire_adapter.py."""

from __future__ import annotations

import pytest

from intelligence.ingestion.emergency_alert_adapters import tas_fire
from tests.emergency_alert_helpers import (  # noqa: F401
    assert_in_schema,
    block_network,
    by,
    fixture_json,
)

pytestmark = pytest.mark.usefixtures("block_network")

# 2026-11-06T05:52Z, when the snapshot was captured; fixed so the expiry filter is deterministic.
NOW_MS = 1793944320000


@pytest.fixture(scope="module")
def payload():
    return fixture_json("tas_fire", "feed.json")


def test_snapshot_totals(payload):
    alerts = tas_fire.parse(payload, now_ms=NOW_MS)
    assert len(payload["features"]) == 1
    assert len(alerts) == 1
    assert by(alerts, "severity") == {"unknown": 1}  # a "Smoke Alert": states no AWS tier
    assert by(alerts, "alert_type") == {"bushfire": 1}
    assert_in_schema(alerts)


def test_stable_event_key_for_a_known_item(payload):
    alert = tas_fire.parse(payload, now_ms=NOW_MS)[0]
    assert alert.event_key == "0-90439"
    assert alert.headline == "Vehicle Fire - Smoke Alert - Tasman Highway Buckland - Avoid smoke"
    assert alert.expiry and alert.expiry.endswith("+00:00")


def test_a_record_already_expired_at_the_source_is_excluded(payload):
    expires = payload["features"][0]["attributes"]["EXPIRES_DATE"]
    assert tas_fire.parse(payload, now_ms=expires + 1) == []


def test_fetch_is_http_get_plus_parse(payload, monkeypatch):
    monkeypatch.setattr(tas_fire, "http_get_json", lambda url: payload)
    monkeypatch.setattr(tas_fire.time, "time", lambda: NOW_MS / 1000)
    assert tas_fire.fetch() == tas_fire.parse(payload, now_ms=NOW_MS)
