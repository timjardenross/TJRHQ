"""VIC adapter: planned burns are dropped like every other jurisdiction."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence.ingestion.emergency_alert_adapters import vic_emergency


def test_planned_burn_detected_in_type_or_name():
    assert vic_emergency._is_planned_burn({"incidentType": "PLANNED BURN", "name": "x"})
    assert vic_emergency._is_planned_burn({"incidentType": "GRASS", "name": "Burn off near Ballan"})


def test_real_fires_are_not_planned_burns():
    assert not vic_emergency._is_planned_burn({"incidentType": "BUSH", "name": "Fire near Ballan"})
    assert not vic_emergency._is_planned_burn({"incidentType": None, "name": None})


def _warning(id_="43562", category1="Advice", event="Thunderstorm Asthma", code="thunderstormAsthma", location="Mallee District", geometry=None):
    return {"type": "Feature", "geometry": geometry or {"type": "GeometryCollection", "geometries": [{"type": "Point", "coordinates": [142.69, -35.24]}]},
            "properties": {"feedType": "warning", "id": id_, "category1": category1, "category2": "Health", "location": location,
                           "cap": {"category": "Health", "event": event, "eventCode": code},
                           "created": "2026-11-01T16:20:15+11:00", "updated": "2026-11-01T16:20:15+11:00",
                           "text": "ADVICE - THUNDERSTORM ASTHMA\nPrepare now - <a href=\"https://x\">link</a>"}}


def test_thunderstorm_asthma_advice_parses_without_a_point():
    [a] = vic_emergency.parse_warnings({"features": [_warning()]})
    assert (a.source_key, a.jurisdiction, a.severity, a.alert_type) == ("vic_emergency", "VIC", "advice", "thunderstorm_asthma")
    assert a.headline == "Advice: Thunderstorm Asthma — Mallee District"
    assert a.event_key == "warning-43562" and a.canonical_url.endswith("/warning/43562/moreinfo")
    assert (a.latitude, a.longitude) == (None, None)
    assert "<a" not in a.description and "Prepare now" in a.description


def test_emergency_warning_keeps_its_tier_and_point():
    g = {"type": "Point", "coordinates": [145.0, -37.8]}
    [a] = vic_emergency.parse_warnings({"features": [_warning(category1="Emergency Warning", event="Bushfire", code="bushfire", geometry=g)]})
    assert (a.severity, a.alert_type, a.latitude, a.longitude) == ("emergency_warning", "bushfire", -37.8, 145.0)


def test_watch_and_act_and_unrecognised_tier():
    tiers = {a.event_key: a.severity for a in vic_emergency.parse_warnings({"features": [
        _warning("1", "Watch and Act", "Flood", "flood"), _warning("2", "Community Information", "Other", "other")]})}
    assert tiers == {"warning-1": "watch_and_act", "warning-2": "unknown"}


def test_incidents_and_planned_burns_in_the_events_feed_are_not_ingested():
    burn = {"type": "Feature", "geometry": None, "properties": {"feedType": "incident", "id": "9", "category1": "Planned Burn"}}
    assert vic_emergency.parse_warnings({"features": [burn]}) == []
    assert vic_emergency.parse_warnings({}) == []


def test_warning_without_an_id_is_skipped():
    w = _warning()
    w["properties"]["id"] = None
    assert vic_emergency.parse_warnings({"features": [w]}) == []


def test_false_alarm_is_not_an_incident():
    assert vic_emergency._is_false_alarm({"incidentType": "FALSE ALARM"})
    assert not vic_emergency._is_false_alarm({"incidentType": "BUSH"})
    assert not vic_emergency._is_false_alarm({"incidentType": None})
