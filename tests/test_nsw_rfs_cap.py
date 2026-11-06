"""NSW RFS CAP-AU enrichment: CAP fields are copied onto the GeoJSON alerts, never add or remove alerts,
and a CAP outage degrades to 'no CAP fields' plus a FIELD DRIFT warning. Offline, on committed fixtures."""

from __future__ import annotations

import logging
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import intelligence.emergency_alerts as ea
from intelligence.ingestion.emergency_alert_adapters import nsw_rfs, nsw_rfs_cap
from intelligence.ingestion.emergency_alert_adapters.base import DropLedger
from tests.emergency_alert_helpers import (  # noqa: F401
    block_network,
    fixture_bytes,
    fixture_json,
)

pytestmark = pytest.mark.usefixtures("block_network")

CAP = fixture_bytes("nsw_rfs", "cap.xml")


def _geojson_alerts():
    return nsw_rfs.parse(fixture_json("nsw_rfs", "feed.json"), DropLedger())


def test_incident_id_is_the_trailing_number():
    assert nsw_rfs_cap.incident_id("https://incidents.rfs.nsw.gov.au/api/v1/incidents/684405") == "684405"
    assert nsw_rfs_cap.incident_id("https://incidents.rfs.nsw.gov.au/api/v1/incidents/684405/") == "684405"
    assert nsw_rfs_cap.incident_id(None) is None and nsw_rfs_cap.incident_id("no-number-here") is None


def test_parse_reads_the_four_cap_fields_per_incident():
    parsed = nsw_rfs_cap.parse(CAP)
    assert len(parsed) == 8
    row = parsed["684405"]
    assert row == {"cap_event": "Grass Fire", "cap_urgency": "Expected", "cap_certainty": "Observed", "cap_severity": "Moderate"}
    assert {r["cap_event"] for r in parsed.values()} >= {"Other Non-Urgent Alerts"}


def test_parse_skips_a_malformed_alert_without_losing_the_rest():
    broken = CAP.replace(b"<incidents>684405</incidents>", b"")
    parsed = nsw_rfs_cap.parse(broken)
    assert "684405" not in parsed and len(parsed) == 7


def test_enrich_only_adds_fields_and_never_changes_which_alerts_exist():
    plain, enriched = _geojson_alerts(), _geojson_alerts()
    n = nsw_rfs_cap.enrich(enriched, CAP)
    assert n >= 1
    assert [a.event_key for a in plain] == [a.event_key for a in enriched]
    for before, after in zip(plain, enriched):
        diff = {k for k, v in asdict(after).items() if v != asdict(before)[k]}
        assert diff <= {"cap_event", "cap_urgency", "cap_certainty", "cap_severity"}
    castlerock = next(a for a in enriched if a.canonical_url.endswith("/684405"))
    assert (castlerock.cap_event, castlerock.cap_urgency, castlerock.cap_severity) == ("Grass Fire", "Expected", "Moderate")
    assert castlerock.severity == "advice"  # the AWS tier still comes from the GeoJSON category, never from CAP


@pytest.mark.parametrize("bad", [b"not xml at all", b"", b"<a/>"])
def test_enrich_never_raises_and_leaves_alerts_untouched(bad, caplog):
    alerts = _geojson_alerts()
    with caplog.at_level(logging.WARNING):
        assert nsw_rfs_cap.enrich(alerts, bad) == 0
    assert all(a.cap_urgency is None for a in alerts)


def test_enrich_survives_a_failed_fetch(caplog):
    alerts = _geojson_alerts()
    with patch.object(nsw_rfs_cap, "http_get", side_effect=OSError("timeout")), caplog.at_level(logging.WARNING):
        assert nsw_rfs_cap.enrich(alerts) == 0
    assert "CAP enrichment unavailable" in caplog.text


def test_enrich_warns_when_no_ids_match(caplog):
    alerts = _geojson_alerts()
    for a in alerts:
        a.canonical_url = "https://example.invalid/x/1"
    with caplog.at_level(logging.WARNING):
        assert nsw_rfs_cap.enrich(alerts, CAP) == 0
    assert "none matched" in caplog.text


def test_fetch_with_ledger_enriches_and_keeps_the_ledger_invariant():
    with patch.object(nsw_rfs, "http_get_json", return_value=fixture_json("nsw_rfs", "feed.json")), \
         patch.object(nsw_rfs_cap, "http_get", return_value=CAP):
        alerts, ledger = nsw_rfs.fetch_with_ledger()
    assert any(a.cap_urgency for a in alerts)
    assert ledger.items_seen == len(alerts) + ledger.excluded_total + ledger.invalid_total


def test_a_cap_outage_costs_no_alerts_and_raises_field_drift():
    with patch.object(nsw_rfs, "http_get_json", return_value=fixture_json("nsw_rfs", "feed.json")), \
         patch.object(nsw_rfs_cap, "http_get", side_effect=OSError("down")):
        alerts, ledger = nsw_rfs.fetch_with_ledger()
    assert len(alerts) == len(_geojson_alerts()) and all(a.cap_urgency is None for a in alerts)
    notes = ea._integrity_notes(nsw_rfs, alerts, ledger)
    assert any(n.startswith("FIELD DRIFT: cap_urgency") for n in notes)


def test_no_field_drift_when_cap_is_healthy():
    with patch.object(nsw_rfs, "http_get_json", return_value=fixture_json("nsw_rfs", "feed.json")), \
         patch.object(nsw_rfs_cap, "http_get", return_value=CAP):
        alerts, ledger = nsw_rfs.fetch_with_ledger()
    assert not any(n.startswith("FIELD DRIFT") for n in ea._integrity_notes(nsw_rfs, alerts, ledger))


def test_a_bare_point_geometry_gives_the_alert_coordinates():
    """Most live features are a plain Point, not a GeometryCollection; both must yield latitude/longitude."""
    data = fixture_json("nsw_rfs", "feed.json")
    kept = nsw_rfs.parse(data, DropLedger())
    by_type = {(f.get("geometry") or {}).get("type") for f in data["features"]}
    assert {"Point", "GeometryCollection"} <= by_type
    assert kept and all(a.latitude is not None and a.longitude is not None for a in kept)
    assert all(-45 < a.latitude < -28 and 140 < a.longitude < 155 for a in kept)  # NSW, and (lat, lon) not swapped


def test_malformed_geometry_leaves_coordinates_empty_without_failing():
    feature = {"properties": {"title": "T", "guid": "https://incidents.rfs.nsw.gov.au/api/v1/incidents/1", "category": "Advice", "description": "", "pubDate": "06/11/2026 5:00:00 PM"},
               "geometry": {"type": "Point", "coordinates": [150.1]}}
    (alert,) = nsw_rfs.parse({"features": [feature]}, DropLedger())
    assert alert.latitude is None and alert.longitude is None
