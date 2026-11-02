"""core/platform/bom_areas.py - match a BOM warning to our sites by named area."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))

import bom_areas as ba

D = {
    "areas": {
        "QLD_RC001": {"product": "flood_catchment", "name": "Barcoo River to Isisford", "state": "QLD"},
        "QLD_RC002": {"product": "flood_catchment", "name": "Lower Condamine River", "state": "QLD"},
        "NSW_FW003": {"product": "fire_weather_district", "name": "Greater Hunter", "state": "NSW"},
        "QLD_PW010": {"product": "forecast_district", "name": "Wide Bay and Burnett", "state": "QLD"},
    },
    "sites": {"s1": ["QLD_RC002"], "s2": [], "s3": ["NSW_FW003"], "s4": ["QLD_PW010"]},
}
SITES = [{"id": i, "name": i, "priority": "Tier 1"} for i in ("s1", "s2", "s3", "s4", "s5")]


def _m(headline, jurisdiction):
    return ba.match_alert({"headline": headline, "jurisdiction": jurisdiction}, SITES, D)


def test_matched_lists_sites_inside_and_counts_sites_with_no_area_data():
    r = _m("Moderate Flood Warning for the Lower Condamine River", "QLD")
    assert r.kind == "matched" and [s["id"] for s in r.sites] == ["s1"] and r.unknown_sites == 1


def test_none_inside_when_area_known_but_no_site_in_it():
    r = _m("Moderate Flood Warning for the Barcoo River", "QLD")
    assert r.kind == "none_inside" and r.area_names == ["Barcoo River to Isisford"]


def test_multi_word_district_stays_whole():
    assert [s["id"] for s in _m("Severe Thunderstorm Warning for Wide Bay and Burnett Forecast District.", "QLD").sites] == ["s4"]
    assert [s["id"] for s in _m("Fire Weather Warning for the Greater Hunter fire weather district", "NSW").sites] == ["s3"]


def test_unparsed_for_cancellations_and_unresolvable_headlines():
    assert _m("Cancellation of Severe Thunderstorm Warning for X Forecast Districts.", "VIC").kind == "unparsed"
    assert _m("Tropical Cyclone Advice for Norfolk Island", "NSW").kind == "unparsed"


def test_real_data_file_loads_and_resolves_a_known_warning():
    data = ba.load_areas()
    assert len(data["areas"]) > 500 and len(data["sites"]) > 400
    sites = [{"id": i, "name": i, "priority": "Tier 1"} for i in data["sites"]]
    r = ba.match_alert({"headline": "Moderate Flood Warning for the Lower Condamine River", "jurisdiction": "QLD"}, sites)
    assert r.kind in ("matched", "none_inside") and r.area_names
