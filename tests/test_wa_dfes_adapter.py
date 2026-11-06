"""WA DFES adapter against real captured warnings + incidents RSS snapshots (offline)."""

from __future__ import annotations

import pytest

from intelligence.ingestion.emergency_alert_adapters import wa_dfes
from tests.emergency_alert_helpers import (  # noqa: F401
    assert_in_schema,
    block_network,
    by,
    fixture_bytes,
)

pytestmark = pytest.mark.usefixtures("block_network")


@pytest.fixture(scope="module")
def raws():
    return fixture_bytes("wa_dfes", "warnings.xml"), fixture_bytes("wa_dfes", "incidents.xml")


def test_snapshot_totals(raws):
    warnings_raw, incidents_raw = raws
    assert warnings_raw.count(b"<item>") == 12 and incidents_raw.count(b"<item>") == 69
    alerts = wa_dfes.parse(*raws)
    assert len(alerts) == 42
    assert by(alerts, "severity") == {"advice": 11, "unknown": 31}
    assert by(alerts, "alert_type") == {"bushfire": 42}
    assert_in_schema(alerts)


def test_warnings_and_incidents_halves(raws):
    warnings, incident_severity = wa_dfes.parse_warnings(raws[0])
    incidents = wa_dfes.parse_incidents(raws[1], incident_severity)
    assert (len(warnings), len(incidents)) == (6, 36)
    assert by(warnings, "severity") == {"advice": 6}
    assert by(incidents, "severity") == {"unknown": 31, "advice": 5}  # 5 enriched via a shared CAD-ID with a warning
    assert len(incident_severity) == 5


def test_stable_event_key_for_a_known_item(raws):
    alert = next(a for a in wa_dfes.parse(*raws) if a.event_key == "6aec15815d73d091544fe038")
    assert alert.headline == "Bushfire Advice THREAT IS REDUCED - MUELLER RANGES AND ORD RIVER"
    assert alert.severity == "advice" and alert.jurisdiction == "WA"


def test_deliberate_exclusions_are_excluded(raws):
    headlines = [a.headline.upper() for a in wa_dfes.parse(*raws)]
    assert not [h for h in headlines if "BURN OFF" in h or "HAZMAT" in h or "PARK CLOSURE" in h]
    assert raws[1].count(b"Burn Off (") == 29  # present in the raw feed, absent from the output
    assert not [h for h in headlines if h.startswith(("STRUCTURE FIRE", "VEHICLE FIRE", "FIRE ("))]


def test_unclassifiable_warning_types_are_dropped_not_kept_as_other(raws):
    """Smoke Alert / Heatwave Advice warnings are not bushfire/storm/cyclone/flood: dropped by design (see wa_dfes._fetch_warnings)."""
    titles = [a.headline for a in wa_dfes.parse_warnings(raws[0])[0]]
    assert not [t for t in titles if t.startswith(("Smoke Alert", "Heatwave"))]
    assert b"Smoke Alert" in raws[0] and b"Heatwave Advice" in raws[0]


def test_fetch_is_http_get_plus_parse(raws, monkeypatch):
    urls = {wa_dfes._WARNINGS_URL: raws[0], wa_dfes._INCIDENTS_URL: raws[1]}
    monkeypatch.setattr(wa_dfes, "http_get", lambda url: urls[url])
    assert wa_dfes.fetch() == wa_dfes.parse(*raws)
