"""Offline tests for planned-maintenance parsers (forward-sources-maint-2kq). Fixtures: tests/fixtures/maintenance/.

ATO/ABR/DVS HTML fixtures are reconstructed from Firecrawl markdown captured 2026-11-24 (see comments inside them); the Statuspage JSON
fixtures are trimmed real payloads and the myID HTML is the real table.
"""

import json
import re
from pathlib import Path

import pytest

from intelligence.ingestion import maintenance_parsers as mp

FX = Path(__file__).resolve().parent / "fixtures" / "maintenance"


def _json(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def _html(name):
    return (FX / name).read_text(encoding="utf-8")


KEYS = {
    "event_id",
    "source_name",
    "published_at",
    "canonical_url",
    "raw_title",
    "raw_summary",
    "window_start",
    "window_end",
}


def test_statuspage_osfa_skips_completed_and_states_window():
    recs = mp.statuspage_maintenance_records(
        _json("ato_osfa_scheduled_maintenances_20261124.json"), "ATO OSFA maint"
    )
    assert len(recs) == 3  # the completed one is dropped
    r = recs[0]
    assert set(r) == KEYS
    assert (
        r["window_start"] == "2026-11-24T23:30:00+11:00"
        and r["window_end"] == "2026-11-25T07:00:00+11:00"
    )
    assert (
        "Scheduled maintenance from 24 November 2026 11:30 pm AEDT to 25 November 2026 7:00 am AEDT"
        in r["raw_summary"]
    )
    assert (
        r["canonical_url"]
        == f"https://osfa.status.ato.gov.au/incidents/{r['event_id']}"
    )


def test_statuspage_multiday_window():
    recs = mp.statuspage_maintenance_records(
        _json("ato_osfa_scheduled_maintenances_20261124.json"), "x"
    )
    assert (
        "27 November 2026 11:30 pm AEDT to 30 November 2026 7:00 am AEDT"
        in recs[1]["raw_summary"]
    )
    assert recs[1]["window_end"].startswith("2026-11-30")


@pytest.mark.parametrize("name", ["osb", "pls"])
def test_statuspage_osb_pls(name):
    recs = mp.statuspage_maintenance_records(
        _json(f"ato_{name}_scheduled_maintenances_20261124.json"), name
    )
    assert len(recs) == 1 and recs[0]["window_start"].startswith("2026-11-2")


def test_statuspage_bad_rows_are_skipped():
    payload = {
        "page": {"url": "https://p.example"},
        "scheduled_maintenances": [
            {
                "id": "a",
                "status": "scheduled",
                "scheduled_for": None,
                "scheduled_until": None,
            },
            {
                "id": "b",
                "status": "scheduled",
                "scheduled_for": "nonsense",
                "scheduled_until": "2026-01-01T00:00:00+11:00",
            },
            {
                "id": "c",
                "status": "in_progress",
                "name": "N",
                "scheduled_for": "2026-01-01T00:00:00+11:00",
                "scheduled_until": "2026-01-01T02:00:00+11:00",
                "incident_updates": [],
            },
        ],
    }
    recs = mp.statuspage_maintenance_records(payload, "s")
    assert [r["event_id"] for r in recs] == ["c"] and "12:00 am AEDT" in recs[0][
        "raw_summary"
    ]


def test_ato_page_dated_rows_only_and_weekly_table_ignored():
    recs = mp.ato_system_maintenance_records(
        _html("ato_system_maintenance_20261124.html")
    )
    assert len(recs) == 6
    assert all(re.search(r"\d{4}", r["raw_summary"]) for r in recs)
    first = recs[0]
    assert first["raw_summary"].startswith(
        "Scheduled maintenance from Friday 27 November 2026 11:30 pm AEDT to Monday 30 November 2026 7:00 am AEDT (System maintenance)"
    )
    assert first["published_at"] == "2026-11-23"
    assert first["window_start"] == "2026-11-27T23:30:00+11:00"
    noon = next(r for r in recs if "7 February 2027" in r["raw_summary"])
    assert noon["window_end"] == "2027-02-07T12:00:00+11:00"
    aest = next(r for r in recs if "29 May 2027" in r["raw_summary"])
    assert aest["window_start"] == "2027-05-29T22:00:00+10:00"
    assert (
        "SBR outage"
        in next(r for r in recs if "23 January 2027" in r["raw_summary"])["raw_summary"]
    )
    assert not any(
        "Tuesday 11:30 pm AEDT to Wednesday" in r["raw_summary"] for r in recs
    )


def test_abr_page_only_dated_abn_system_rows():
    recs = mp.abr_site_maintenance_records(
        _html("abr_scheduled_site_maintenance_20261124.html")
    )
    assert len(recs) == 3
    assert all(
        r["raw_title"].startswith("Australian Business Register ABN system")
        for r in recs
    )
    assert recs[2]["raw_summary"].startswith(
        "Scheduled maintenance from Friday 27 November 2026 11:30 pm AEDT to Monday 30 November 2026 7:00 am AEDT"
    )
    assert recs[0]["published_at"] == "2026-11-18"


def test_myid_real_table():
    recs = mp.myid_maintenance_records(_html("myid_system_maintenance_20261124.html"))
    assert len(recs) == 1
    r = recs[0]
    assert r["raw_title"] == "myID myID app: scheduled maintenance"
    assert (
        "Friday 13 November 2026 11:45 pm AEDT to Saturday 14 November 2026 2:45 am AEDT"
        in r["raw_summary"]
    )
    assert (
        r["window_start"] == "2026-11-13T23:45:00+11:00"
        and r["published_at"] == "2026-11-11"
    )


def test_myid_no_maintenance_is_empty_not_error():
    html = "<html><body><h1>System maintenance</h1><p>There is currently no planned system maintenance for myID.</p></body></html>"
    assert mp.myid_maintenance_records(html) == []


def test_dvs_production_only_by_default_and_dates_unambiguous():
    html = _html("dvs_upcoming_outages_20261124.html")
    recs = mp.dvs_outage_records(html)
    assert len(recs) == 2 and all("production" in r["raw_title"] for r in recs)
    assert recs[0]["raw_title"] == "DVS production WA BDM: scheduled maintenance"
    assert (
        recs[0]["raw_summary"]
        == "Scheduled maintenance from 26 November 2026 5:00 pm to 26 November 2026 8:00 pm."
    )
    assert (
        recs[0]["window_start"] == "2026-11-26T17:00:00"
    )  # no zone is stated by the page, none is attached
    both = mp.dvs_outage_records(html, include_test=True)
    assert len(both) == 4 and "DVS test Visa: scheduled maintenance" in {
        r["raw_title"] for r in both
    }


def test_dvs_text_input_and_invalid_date_skipped():
    text = (
        "### DVS Production Environment\nWA BDM\n31/02/2026 5:00:00 PM to 31/02/2026 8:00:00 PM\n"
        "Visa\n3/12/2026 1:00:00 AM to 3/12/2026 2:00:00 AM\n"
    )
    recs = mp.dvs_outage_records(text)
    assert (
        len(recs) == 1 and "3 December 2026 1:00 am" in recs[0]["raw_summary"]
    )  # day-first, never March 12


def test_event_ids_are_stable_and_distinct():
    a = mp.ato_system_maintenance_records(_html("ato_system_maintenance_20261124.html"))
    b = mp.ato_system_maintenance_records(_html("ato_system_maintenance_20261124.html"))
    assert [r["event_id"] for r in a] == [r["event_id"] for r in b]
    assert len({r["event_id"] for r in a}) == len(a)


def test_parse_when_rejects_impossible_and_non_months():
    assert mp._parse_when("31 February 2026 10:00 pm") is None
    assert mp._parse_when("12 Marketing 2026") is None
    assert mp._parse_when("Tuesday 11:30 pm AEDT") is None


def test_page_parsers_registry_names():
    assert set(mp.PAGE_PARSERS) == {
        "ATO System Maintenance",
        "ATO ABR Scheduled Site Maintenance",
        "myID System Maintenance",
        "DVS Status Scheduled Outages",
    }


def test_records_consumable_by_dated_events_if_present():
    """When the dated-events extractor is on this branch, the records yield explicit-date planned_maintenance events."""
    de = pytest.importorskip("tools.intelligence.analytics.dated_events")
    recs = mp.statuspage_maintenance_records(
        _json("ato_osfa_scheduled_maintenances_20261124.json"),
        "ATO Online services for agents Status",
    )
    events = de.extract_events(recs)
    assert events and all(e["kind"] == "planned_maintenance" for e in events)


# ---- wiring: API adapter, Scrape adapter, registry rows, scheduler cost list -------------------------------------------------------


def _src(name, url, source_type, endpoint=None):
    from intelligence.models import SourceRecord

    return SourceRecord(
        source_id="id-" + name[:6],
        source_name=name,
        category="critical_infrastructure",
        priority_rank=3,
        url=url,
        source_type=source_type,
        jurisdiction="AU",
        confidence_weight=0.95,
        active=True,
        api_endpoint=endpoint,
    )


def test_api_adapter_routes_scheduled_maintenances_endpoint_not_incident_parser():
    from intelligence.ingestion.api_adapter import APIAdapter

    ep = "https://osfa.status.ato.gov.au/api/v2/scheduled-maintenances.json"
    a = APIAdapter(
        _src(
            "ATO Online Services for Agents Scheduled Maintenance",
            "https://osfa.status.ato.gov.au/",
            "api",
            ep,
        )
    )
    a._fetch_json = lambda url: _json("ato_osfa_scheduled_maintenances_20261124.json")
    items = a.collect()
    assert len(items) == 3
    assert (
        "Scheduled maintenance from 24 November 2026 11:30 pm AEDT"
        in items[0].raw_summary
    )
    assert items[0].canonical_url.startswith(
        "https://osfa.status.ato.gov.au/incidents/"
    )
    assert (
        items[0].published_at is not None and items[0].published_at.tzinfo is not None
    )


def test_scrape_adapter_uses_page_parser_for_ato_page():
    from intelligence.ingestion.scrape_adapter import ScrapeAdapter

    a = ScrapeAdapter(
        _src(
            "ATO System Maintenance",
            "https://www.ato.gov.au/online-services/system-maintenance",
            "scrape",
        )
    )
    a._fetch_html = lambda url: _html("ato_system_maintenance_20261124.html")
    items = a.collect()
    assert len(items) == 6 and items[0].raw_summary.startswith(
        "Scheduled maintenance from Friday 27 November 2026"
    )
    assert items[0].published_at.date().isoformat() == "2026-11-23"


def test_registry_rows_inactive_unique_and_cost_listed():
    import importlib.util

    from intelligence import scheduler
    from intelligence.ingestion import scrape_adapter as sa

    spec = importlib.util.spec_from_file_location(
        "seed",
        Path(__file__).resolve().parents[1]
        / "tools/intelligence/seed_source_registry.py",
    )
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    names = [s["source_name"] for s in seed.SOURCES]
    assert len(names) == len(set(names))
    rows = [
        s
        for s in seed.SOURCES
        if s["source_name"].endswith("Scheduled Maintenance")
        or s["source_name"]
        in (
            "ATO System Maintenance",
            "ATO ABR Scheduled Site Maintenance",
            "DVS Status Scheduled Outages",
        )
    ]
    assert len(rows) == 6
    # 2026-11-24 activation: the three plain-fetch ATO Statuspage feeds are active (0 Firecrawl credits); the three scrape pages stay off.
    assert {r["source_name"] for r in rows if r["active"]} == {r["source_name"] for r in rows if r["source_type"] == "api"}
    assert not any(r["active"] for r in rows if r["source_type"] != "api")
    for r in rows:
        if r["source_type"] == "api":
            assert r["api_endpoint"].endswith("/api/v2/scheduled-maintenances.json")
        else:
            assert r["source_name"] in mp.PAGE_PARSERS
            assert (
                r["source_name"] in sa._FIRECRAWL_FALLBACK_SOURCE_NAMES
                and r["source_name"] in scheduler._FIRECRAWL_FETCH_SOURCE_NAMES
            )
