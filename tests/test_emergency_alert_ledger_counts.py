"""Drop accounting per adapter: every skipped item is counted, by reason, on the
real fixtures; one malformed item is isolated instead of failing the source."""

from __future__ import annotations

import pytest

from intelligence.ingestion.emergency_alert_adapters import (
    act_esa,
    bom_warnings,
    nsw_rfs,
    qld_fire,
    sa_cfs,
    tas_fire,
    vic_emergency,
    wa_dfes,
)
from intelligence.ingestion.emergency_alert_adapters import base as adapter_base
from intelligence.ingestion.emergency_alert_adapters.base import (
    DropLedger,
    FeedRetiredError,
    convert_items,
)
from tests.emergency_alert_helpers import (  # noqa: F401
    block_network,
    fixture_bytes,
    fixture_json,
)

pytestmark = pytest.mark.usefixtures("block_network")

TAS_NOW_MS = 1793944320000  # 2026-11-06T05:52Z, snapshot time


def _run(source):
    """-> (alerts, ledger) for the fixture of `source`."""
    ledger = DropLedger()
    if source == "nsw_rfs":
        alerts = nsw_rfs.parse(fixture_json("nsw_rfs", "feed.json"), ledger)
    elif source == "qld_fire":
        alerts = qld_fire.parse(fixture_json("qld_fire", "feed.json"), ledger)
    elif source == "act_esa":
        alerts = act_esa.parse(fixture_bytes("act_esa", "feed.xml"), ledger)
    elif source == "act_esa_synthetic":
        alerts = act_esa.parse(fixture_bytes("act_esa", "synthetic_kept.xml"), ledger)
    elif source == "wa_dfes":
        alerts = wa_dfes.parse(fixture_bytes("wa_dfes", "warnings.xml"), fixture_bytes("wa_dfes", "incidents.xml"), ledger)
    elif source == "vic_emergency":
        alerts = vic_emergency.parse_incidents(fixture_json("vic_emergency", "incidents.json"), ledger)
        alerts += vic_emergency.parse_warnings(fixture_json("vic_emergency", "warnings.json"), ledger)
    elif source == "sa_cfs":
        alerts = sa_cfs.parse(fixture_bytes("sa_cfs", "feed.xml"), ledger)
    elif source == "tas_fire":
        alerts = tas_fire.parse(fixture_json("tas_fire", "feed.json"), TAS_NOW_MS, ledger)
    elif source == "bom_nsw":
        alerts = bom_warnings.parse_state_feed("NSW", fixture_bytes("bom_nsw", "feed.xml"), ledger=ledger)
    else:  # pragma: no cover
        raise AssertionError(source)
    return alerts, ledger


EXPECTED = {
    "nsw_rfs": (7, {"items_seen": 23, "excluded_not_applicable": 16}),
    "qld_fire": (2, {"items_seen": 43, "excluded_information": 41}),
    "act_esa": (0, {"items_seen": 17, "excluded_ambulance_mva": 17}),
    "act_esa_synthetic": (3, {"items_seen": 6, "excluded_ambulance_mva": 2, "excluded_hazard_reduction": 1}),
    "wa_dfes": (43, {"items_seen": 81, "excluded_hazard_reduction": 29, "excluded_not_bushfire": 4,
                     "excluded_other_type": 4, "excluded_park_closure": 1}),
    "vic_emergency": (5, {"items_seen": 40, "excluded_false_alarm": 3, "excluded_not_warning_feedtype": 23,
                          "excluded_other_type": 7, "excluded_structure_fire": 2}),
    "sa_cfs": (3, {"items_seen": 7, "excluded_hazard_reduction": 2, "excluded_structure_fire": 2}),
    "tas_fire": (1, {"items_seen": 1, "unmapped_smoke_alert": 1}),
    "bom_nsw": (4, {"items_seen": 7, "excluded_agricultural": 1, "excluded_marine": 1, "excluded_unmatched_product": 1,
                    "unmapped_product_hazardous_surf_warning": 1}),
}


@pytest.mark.parametrize("source", sorted(EXPECTED))
def test_ledger_counts_on_the_fixture(source):
    alerts, ledger = _run(source)
    accepted, counts = EXPECTED[source]
    assert len(alerts) == accepted
    assert ledger.as_dict() == counts


@pytest.mark.parametrize("source", sorted(EXPECTED))
def test_every_item_is_accounted_for(source):
    """items_seen == accepted + excluded + invalid, on every fixture: nothing disappears silently."""
    alerts, ledger = _run(source)
    assert ledger.items_seen == len(alerts) + ledger.excluded_total + ledger.invalid_total


@pytest.mark.parametrize("source", sorted(EXPECTED))
def test_ledger_does_not_change_the_alerts(source):
    """Passing a ledger records the skips but never changes what is returned."""
    with_ledger, _ = _run(source)
    plain = {
        "nsw_rfs": lambda: nsw_rfs.parse(fixture_json("nsw_rfs", "feed.json")),
        "qld_fire": lambda: qld_fire.parse(fixture_json("qld_fire", "feed.json")),
        "act_esa": lambda: act_esa.parse(fixture_bytes("act_esa", "feed.xml")),
        "act_esa_synthetic": lambda: act_esa.parse(fixture_bytes("act_esa", "synthetic_kept.xml")),
        "wa_dfes": lambda: wa_dfes.parse(fixture_bytes("wa_dfes", "warnings.xml"), fixture_bytes("wa_dfes", "incidents.xml")),
        "vic_emergency": lambda: vic_emergency.parse_incidents(fixture_json("vic_emergency", "incidents.json")) + vic_emergency.parse_warnings(fixture_json("vic_emergency", "warnings.json")),
        "sa_cfs": lambda: sa_cfs.parse(fixture_bytes("sa_cfs", "feed.xml")),
        "tas_fire": lambda: tas_fire.parse(fixture_json("tas_fire", "feed.json"), TAS_NOW_MS),
        "bom_nsw": lambda: bom_warnings.parse_state_feed("NSW", fixture_bytes("bom_nsw", "feed.xml")),
    }[source]()
    assert with_ledger == plain


def test_no_live_fixture_has_structurally_invalid_items():
    """All real snapshots parse cleanly: the invalid_ namespace is for genuinely broken feeds only."""
    for source in EXPECTED:
        assert _run(source)[1].invalid_total == 0, source


# ---- fetch_with_ledger() --------------------------------------------------------------

def test_fetch_with_ledger_matches_fetch_for_each_adapter(monkeypatch):
    nsw = fixture_json("nsw_rfs", "feed.json")
    monkeypatch.setattr(nsw_rfs, "http_get_json", lambda url: nsw)
    alerts, ledger = nsw_rfs.fetch_with_ledger()
    assert alerts == nsw_rfs.fetch() and ledger.items_seen == 23

    urls = {wa_dfes._WARNINGS_URL: fixture_bytes("wa_dfes", "warnings.xml"), wa_dfes._INCIDENTS_URL: fixture_bytes("wa_dfes", "incidents.xml")}
    monkeypatch.setattr(wa_dfes, "http_get", lambda url: urls[url])
    alerts, ledger = wa_dfes.fetch_with_ledger()
    assert alerts == wa_dfes.fetch() and ledger.items_seen == 81

    vic = {vic_emergency._FEED_URL: fixture_json("vic_emergency", "incidents.json"), vic_emergency._WARNINGS_URL: fixture_json("vic_emergency", "warnings.json")}
    monkeypatch.setattr(vic_emergency, "http_get_json", lambda url: vic[url])
    alerts, ledger = vic_emergency.fetch_with_ledger()
    assert alerts == vic_emergency.fetch() and ledger.items_seen == 40

    raw = fixture_bytes("bom_nsw", "feed.xml")
    monkeypatch.setattr(bom_warnings, "_http_get_bom", lambda url: raw if url.endswith(".xml") else b"<html></html>")
    monkeypatch.setattr(bom_warnings, "_detail_cache", {})
    alerts, ledger = bom_warnings.nsw.fetch_with_ledger()
    assert len(alerts) == 4 and ledger.items_seen == 7


@pytest.mark.parametrize("mod", [nsw_rfs, qld_fire, act_esa, wa_dfes, vic_emergency, sa_cfs, tas_fire])
def test_every_live_adapter_exposes_fetch_with_ledger(mod):
    assert callable(mod.fetch_with_ledger) and callable(mod.fetch)


# ---- one bad row must not black out a source ------------------------------------------

def test_a_malformed_feature_is_isolated_when_a_ledger_is_passed():
    good = {"properties": {"title": "T", "guid": "g1", "category": "Advice", "description": "TYPE: Bush Fire <br />"}, "geometry": None}
    ledger = DropLedger()
    alerts = nsw_rfs.parse({"features": [good, None, "garbage", good | {"properties": {**good["properties"], "guid": "g2"}}]}, ledger)
    assert [a.event_key for a in alerts] == ["g1", "g2"]
    assert ledger.as_dict() == {"items_seen": 4, "invalid_unparseable_item": 2}


def test_without_a_ledger_a_malformed_feature_still_raises_as_before():
    with pytest.raises(AttributeError):
        nsw_rfs.parse({"features": [None]})


def test_unparseable_item_log_names_only_the_exception_type(caplog):
    with caplog.at_level("WARNING", logger=adapter_base.log.name):
        nsw_rfs.parse({"features": ["TOP-SECRET-CONTENT"]}, DropLedger())
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "AttributeError" in text and "TOP-SECRET-CONTENT" not in text


def test_a_feed_retirement_notice_is_never_swallowed_as_a_bad_row():
    xml = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><content><alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">'
           b"<info><headline>Feed Retirement Notice</headline><description>moved</description></info></alert></content></entry></feed>")
    assert issubclass(FeedRetiredError, RuntimeError)  # existing callers catching RuntimeError keep working
    with pytest.raises(FeedRetiredError):
        sa_cfs.parse(xml, DropLedger())
    with pytest.raises(FeedRetiredError):
        sa_cfs.parse(xml)


def test_convert_items_counts_seen_even_when_the_converter_drops():
    ledger = DropLedger()
    assert convert_items([1, 2, 3], lambda i: ledger.exclude("x"), ledger, guard=True) == []
    assert ledger.as_dict() == {"items_seen": 3, "excluded_x": 3}


# ---- structural (invalid_) skip points ------------------------------------------------

def test_sa_entry_without_content_or_cap_alert_is_invalid():
    xml = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>a</title></entry>'
           b"<entry><content><other/></content></entry></feed>")
    ledger = DropLedger()
    assert sa_cfs.parse(xml, ledger) == []
    assert ledger.as_dict() == {"items_seen": 2, "invalid_missing_content": 1, "invalid_missing_cap_alert": 1}


def test_tas_record_without_a_headline_is_invalid():
    ledger = DropLedger()
    assert tas_fire.parse({"features": [{"attributes": {"IDENTIFIER": "x"}}]}, TAS_NOW_MS, ledger) == []
    assert ledger.as_dict() == {"items_seen": 1, "invalid_missing_headline": 1}


def test_tas_record_expired_at_source_is_a_deliberate_exclusion():
    ledger = DropLedger()
    payload = {"features": [{"attributes": {"ALERT_SUMMARY": "Advice: fire", "EXPIRES_DATE": TAS_NOW_MS - 1}}]}
    assert tas_fire.parse(payload, TAS_NOW_MS, ledger) == []
    assert ledger.as_dict() == {"items_seen": 1, "excluded_expired_at_source": 1}


def test_vic_warning_without_an_id_is_invalid():
    ledger = DropLedger()
    data = {"features": [{"properties": {"feedType": "warning", "category1": "Advice"}}]}
    assert vic_emergency.parse_warnings(data, ledger) == []
    assert ledger.as_dict() == {"items_seen": 1, "invalid_missing_id": 1}


def test_vic_planned_burn_and_false_alarm_reasons():
    ledger = DropLedger()
    rows = {"results": [{"incidentType": "PLANNED BURN", "category1": "Fire"}, {"incidentType": "FALSE ALARM", "category1": "Fire"}]}
    assert vic_emergency.parse_incidents(rows, ledger) == []
    assert ledger.as_dict() == {"items_seen": 2, "excluded_false_alarm": 1, "excluded_hazard_reduction": 1}


def test_nsw_hazard_reduction_reason():
    ledger = DropLedger()
    feature = {"properties": {"category": "Advice", "description": "TYPE: Hazard Reduction <br />"}}
    assert nsw_rfs.parse({"features": [feature]}, ledger) == []
    assert ledger.as_dict() == {"items_seen": 1, "excluded_hazard_reduction": 1}


def test_qld_hazard_reduction_reason():
    ledger = DropLedger()
    feature = {"properties": {"WarningLevel": "Advice", "CallToAction": "Avoid Smoke (Hazard Reduction Burn)"}}
    assert qld_fire.parse({"features": [feature]}, ledger) == []
    assert ledger.as_dict() == {"items_seen": 1, "excluded_hazard_reduction": 1}


def test_sa_hazmat_reason():
    xml = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><content><alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">'
           b"<info><category>CBRNE</category><event>Hazardous Materials</event><headline>X : Hazardous Materials</headline></info></alert></content></entry></feed>")
    ledger = DropLedger()
    assert sa_cfs.parse(xml, ledger) == []
    assert ledger.as_dict() == {"items_seen": 1, "excluded_hazmat": 1}


# ---- unknown vocabulary ---------------------------------------------------------------

def test_unrecognised_tier_labels_are_counted_by_slug():
    ledger = DropLedger()
    features = [{"properties": {"guid": f"g{i}", "category": label, "description": "TYPE: Bush Fire <br />"}} for i, label in enumerate(["Catastrophic", "Catastrophic", "Code Red!", ""])]
    alerts = nsw_rfs.parse({"features": features}, ledger)
    assert {a.severity for a in alerts} == {"unknown"}
    assert ledger.as_dict() == {"items_seen": 4, "unmapped_blank": 1, "unmapped_catastrophic": 2, "unmapped_code_red": 1}


def test_known_tier_labels_are_not_counted_as_unmapped():
    ledger = DropLedger()
    features = [{"properties": {"guid": "g", "category": c, "description": "TYPE: Bush Fire <br />"}} for c in ("Advice", "Watch and Act", "Emergency Warning")]
    nsw_rfs.parse({"features": features}, ledger)
    assert ledger.as_dict() == {"items_seen": 3}


def test_sa_incident_level_is_a_known_non_tier_not_unmapped():
    _, ledger = _run("sa_cfs")
    assert not [k for k in ledger.counts if k.startswith("unmapped_")]


def test_unmapped_label_cardinality_is_capped():
    ledger = DropLedger()
    for i in range(50):
        ledger.unmapped(f"label {i}")
    labels = [k for k in ledger.counts if k.startswith("unmapped_")]
    assert len(labels) == 21 and "unmapped_other" in labels
    assert sum(ledger.counts[k] for k in labels) == 50


# ---- DropLedger itself ----------------------------------------------------------------

def test_ledger_summary_format_matches_the_spec_example():
    ledger = DropLedger()
    ledger.seen(30)
    for _ in range(15):
        ledger.exclude("hazard_reduction")
    for _ in range(2):
        ledger.exclude("not_applicable")
    ledger.invalid("missing_id")
    assert ledger.summary() == "seen 30, excluded 17 (hazard_reduction 15, not_applicable 2), invalid 1 (missing_id 1)"
    assert (ledger.excluded_total, ledger.invalid_total) == (17, 1)
    assert ledger.top_invalid() == "missing_id 1"


def test_ledger_namespaces_never_mix():
    ledger = DropLedger()
    ledger.exclude("a")
    ledger.invalid("a")
    assert ledger.excluded_total == 1 and ledger.invalid_total == 1
    assert set(ledger.counts) == {"excluded_a", "invalid_a"}
