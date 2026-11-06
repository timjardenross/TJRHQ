"""VIC Emergency adapter against real captured incidents + events (warnings) snapshots (offline)."""

from __future__ import annotations

import pytest

from intelligence.ingestion.emergency_alert_adapters import vic_emergency
from tests.emergency_alert_helpers import (  # noqa: F401
    assert_in_schema,
    block_network,
    by,
    fixture_json,
)

pytestmark = pytest.mark.usefixtures("block_network")


@pytest.fixture(scope="module")
def incidents():
    return fixture_json("vic_emergency", "incidents.json")


@pytest.fixture(scope="module")
def warnings():
    return fixture_json("vic_emergency", "warnings.json")


def test_incidents_path_totals(incidents):
    alerts = vic_emergency.parse_incidents(incidents)
    assert len(incidents["results"]) == 16
    assert len(alerts) == 4
    assert by(alerts, "severity") == {"unknown": 4}  # the incidents feed has no warning level
    assert by(alerts, "alert_type") == {"bushfire": 4}
    assert_in_schema(alerts)


def test_incidents_stable_event_key(incidents):
    alert = next(a for a in vic_emergency.parse_incidents(incidents) if a.event_key == "300972")
    assert alert.headline == "SHIRE DAM RD"
    assert alert.issued_at == "2026-11-06T14:48:00"  # no tz in source: KNOWN GAP, see base.parse_dmy_datetime
    assert alert.updated_at_src == "2026-11-06T15:39:00"


def test_incident_exclusions(incidents):
    kept = {a.event_key for a in vic_emergency.parse_incidents(incidents)}
    excluded = {str(r["incidentNo"]) for r in incidents["results"] if r["incidentType"] in ("FALSE ALARM", "STRUCTURE", "OTHER", "INCIDENT", "ASSIST OTHER AGENCY")}
    assert len(excluded) == 12 and not (kept & excluded)


def test_warnings_path_totals(warnings):
    alerts = vic_emergency.parse_warnings(warnings)
    assert len(warnings["features"]) == 24
    assert len(alerts) == 1  # the other 23 features are incidents/planned burns: not warnings
    assert by(alerts, "severity") == {"advice": 1}
    assert by(alerts, "alert_type") == {"flood": 1}
    assert_in_schema(alerts)


def test_warnings_stable_event_key(warnings):
    alert = vic_emergency.parse_warnings(warnings)[0]
    assert alert.event_key == "warning-43585"
    assert alert.headline == "Advice: Riverine Flood — The Bunyip River at Iona and Cora Lynn"


def test_non_warning_feed_types_are_excluded(warnings):
    assert {f["properties"]["feedType"] for f in warnings["features"]} == {"warning", "incident"}
    assert all(not a.event_key.startswith("incident") for a in vic_emergency.parse_warnings(warnings))


def test_fetch_is_incidents_plus_warnings(incidents, warnings, monkeypatch):
    urls = {vic_emergency._FEED_URL: incidents, vic_emergency._WARNINGS_URL: warnings}
    monkeypatch.setattr(vic_emergency, "http_get_json", lambda url: urls[url])
    assert vic_emergency.fetch() == vic_emergency.parse_incidents(incidents) + vic_emergency.parse_warnings(warnings)
