"""Data-quality signals: freshness (STALE), field drift, samples, source timezones, SA <sent>.

These never fail a source; they put a warning in the heartbeat so a feed that is fetched and
parsed fine but has gone quiet, or changed shape, is visible. Offline, on the committed fixtures."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import intelligence.emergency_alerts as ea
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
from intelligence.ingestion.emergency_alert_adapters.base import (
    CanonicalAlert,
    DropLedger,
    parse_dmy_datetime,
)
from tests.emergency_alert_helpers import (  # noqa: F401
    block_network,
    fixture_bytes,
    fixture_json,
)

pytestmark = pytest.mark.usefixtures("block_network")

CAPTURE = datetime(2026, 11, 6, 5, 52, tzinfo=timezone.utc)  # when the fixtures were captured
TAS_NOW_MS = 1793944320000

RUNS = {
    "nsw_rfs": (nsw_rfs, lambda lg: nsw_rfs.parse(fixture_json("nsw_rfs", "feed.json"), lg)),
    "qld_fire": (qld_fire, lambda lg: qld_fire.parse(fixture_json("qld_fire", "feed.json"), lg)),
    "act_esa": (act_esa, lambda lg: act_esa.parse(fixture_bytes("act_esa", "feed.xml"), lg)),
    "wa_dfes": (wa_dfes, lambda lg: wa_dfes.parse(fixture_bytes("wa_dfes", "warnings.xml"), fixture_bytes("wa_dfes", "incidents.xml"), lg)),
    "vic_emergency": (vic_emergency, lambda lg: vic_emergency.parse_incidents(fixture_json("vic_emergency", "incidents.json"), lg) + vic_emergency.parse_warnings(fixture_json("vic_emergency", "warnings.json"), lg)),
    "sa_cfs": (sa_cfs, lambda lg: sa_cfs.parse(fixture_bytes("sa_cfs", "feed.xml"), lg)),
    "tas_fire": (tas_fire, lambda lg: tas_fire.parse(fixture_json("tas_fire", "feed.json"), TAS_NOW_MS, lg)),
    "bom_nsw": (bom_warnings.nsw, lambda lg: bom_warnings.parse_state_feed("NSW", fixture_bytes("bom_nsw", "feed.xml"), ledger=lg)),
}


def _run(key):
    ledger = DropLedger()
    return RUNS[key][1](ledger), ledger


# ---- ledger.observe / samples -----------------------------------------------------------

def test_observe_keeps_the_newest_and_reads_iso_rfc822_and_naive_as_utc():
    ledger = DropLedger()
    ledger.observe("2026-11-06T14:48:00+11:00")  # 03:48Z
    ledger.observe("Fri, 06 Nov 2026 03:00:00 +0000")
    ledger.observe("2026-11-06T10:00:00")  # no offset: read as UTC
    for junk in (None, "", "not a date", 12):
        ledger.observe(junk)
    assert ledger.newest_item_at == datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc)


def test_samples_are_capped_deduplicated_and_truncated():
    ledger = DropLedger()
    for title in ("one", "two", "two", "three", "four", "x" * 200):
        ledger.exclude("r", sample=title)
    assert ledger.samples["excluded_r"] == ["one", "two", "three"]
    ledger.exclude("long", sample="y" * 200)
    assert len(ledger.samples["excluded_long"][0]) == 80
    ledger.exclude("none", sample=None)
    assert "excluded_none" not in ledger.samples
    assert ledger.counts["excluded_r"] == 6  # counting is unaffected by the sample cap


def test_wa_smoke_alerts_appear_as_samples_of_the_dropped_type():
    _, ledger = _run("wa_dfes")
    assert all(s.startswith("Smoke Alert") for s in ledger.samples["excluded_other_type"])


@pytest.mark.parametrize("key", sorted(RUNS))
def test_every_adapter_reports_the_newest_item_time_on_its_fixture(key):
    _, ledger = _run(key)
    assert ledger.newest_item_at is not None, f"{key}: no source timestamp observed, a freshness check would be blind"
    assert ledger.newest_item_at.tzinfo is not None
    assert timedelta(0) <= CAPTURE + timedelta(hours=1) - ledger.newest_item_at < timedelta(days=60)


def test_act_freshness_counts_excluded_items_so_a_busy_all_excluded_feed_is_not_stale():
    alerts, ledger = _run("act_esa")
    assert alerts == [] and ledger.excluded_total == 17  # every item is an ambulance call...
    assert ledger.newest_item_at == datetime(2026, 11, 6, 5, 51, 45, tzinfo=timezone.utc)  # ...but the feed is alive


# ---- freshness (STALE) ------------------------------------------------------------------

def _adapter(**info):
    return SimpleNamespace(SOURCE_INFO={"stale_after_hours": None, "expected_fields": [], **info})


def _ledger(newest, seen=5):
    ledger = DropLedger()
    ledger.seen(seen)
    ledger.observe(newest)
    return ledger


def test_stale_when_the_newest_item_is_older_than_the_threshold():
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
    notes = ea._integrity_notes(_adapter(stale_after_hours=48), [], _ledger("2026-11-06T00:00:00+00:00"), now)
    assert notes == ["STALE: newest item 96h old (expected under 48h)"]


def test_not_stale_inside_the_threshold_or_exactly_at_it():
    now = datetime(2026, 11, 8, tzinfo=timezone.utc)
    assert ea._integrity_notes(_adapter(stale_after_hours=48), [], _ledger("2026-11-06T01:00:00+00:00"), now) == []
    assert ea._integrity_notes(_adapter(stale_after_hours=48), [], _ledger("2026-11-06T00:00:00+00:00"), now) == []


def test_quiet_by_nature_sources_are_never_flagged_stale():
    now = datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert ea._integrity_notes(_adapter(stale_after_hours=None), [], _ledger("2026-01-01T00:00:00+00:00"), now) == []


def test_an_empty_feed_is_not_stale_only_a_feed_with_items_and_old_timestamps():
    now = datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert ea._integrity_notes(_adapter(stale_after_hours=24), [], _ledger("2026-01-01T00:00:00+00:00", seen=0), now) == []
    assert ea._integrity_notes(_adapter(stale_after_hours=24), [], _ledger(None), now) == []  # no timestamp seen: nothing to compare


def test_no_adapter_is_stale_on_its_fixture_at_capture_time():
    for key, (module, _) in RUNS.items():
        alerts, ledger = _run(key)
        stale = [n for n in ea._integrity_notes(module, alerts, ledger, CAPTURE) if n.startswith("STALE")]
        assert stale == [], f"{key}: {stale}"


def test_every_adapter_with_a_threshold_flags_stale_two_weeks_later():
    """The check can fire: each source with a threshold, aged by two weeks, is reported stale."""
    later = CAPTURE + timedelta(days=14)
    for key, (module, _) in RUNS.items():
        alerts, ledger = _run(key)
        stale = [n for n in ea._integrity_notes(module, alerts, ledger, later) if n.startswith("STALE")]
        if module.SOURCE_INFO["stale_after_hours"]:
            assert len(stale) == 1, key
        else:
            assert stale == [], key


# ---- field drift ------------------------------------------------------------------------

def _alerts(n, **fields):
    return [CanonicalAlert(source_key="s", jurisdiction="X", headline=f"h{i}", event_key=f"e{i}", **fields) for i in range(n)]


def test_field_drift_when_an_expected_field_is_missing_on_every_alert():
    notes = ea._integrity_notes(_adapter(expected_fields=["updated_at_src"]), _alerts(4), DropLedger())
    assert notes == ["FIELD DRIFT: updated_at_src missing on all 4 alerts"]


def test_no_drift_if_even_one_alert_has_the_field_or_the_sample_is_tiny():
    mixed = _alerts(3)
    mixed[1].updated_at_src = "2026-11-06T00:00:00+00:00"
    assert ea._integrity_notes(_adapter(expected_fields=["updated_at_src"]), mixed, DropLedger()) == []
    assert ea._integrity_notes(_adapter(expected_fields=["updated_at_src"]), _alerts(2), DropLedger()) == []


def test_empty_string_counts_as_missing():
    assert ea._integrity_notes(_adapter(expected_fields=["location"]), _alerts(3, location=""), DropLedger())


@pytest.mark.parametrize("key", sorted(RUNS))
def test_no_adapter_shows_field_drift_on_its_fixture(key):
    module, _ = RUNS[key]
    alerts, ledger = _run(key)
    assert [n for n in ea._integrity_notes(module, alerts, ledger, CAPTURE) if n.startswith("FIELD DRIFT")] == []


def test_bom_state_adapters_share_the_source_info():
    assert bom_warnings.nsw.SOURCE_INFO is bom_warnings.SOURCE_INFO


# ---- run_source puts the notes in the heartbeat, status stays ok ------------------------

def _run_source(alerts, ledger, adapter_info):
    adapter = SimpleNamespace(fetch_with_ledger=lambda: (alerts, ledger), SOURCE_INFO=adapter_info)
    with patch.dict(ea._ADAPTERS, {"x_src": (adapter, "emergency_alert_x")}, clear=True), \
         patch.object(ea, "_upsert_batch"), patch.object(ea, "_expire_stale", return_value=0), \
         patch.object(ea, "_record_heartbeat") as hb:
        result = ea.run_source("x_src")
    return result, hb.call_args.kwargs


def test_run_source_reports_stale_in_the_detail_and_keeps_status_ok(caplog):
    ledger = DropLedger()
    ledger.seen(3)
    ledger.observe(datetime.now(timezone.utc) - timedelta(hours=100))
    with caplog.at_level(logging.WARNING, logger="emergency-alerts"):
        _, hb = _run_source(_alerts(3, updated_at_src="x"), ledger, {"stale_after_hours": 48, "expected_fields": []})
    assert hb["status"] == "ok"
    assert "| STALE: newest item 100h old (expected under 48h) |" in hb["detail"]
    assert any("STALE" in r.getMessage() and "x_src" in r.getMessage() for r in caplog.records)


def test_run_source_combines_the_percent_invalid_warning_with_the_new_notes():
    ledger = DropLedger()
    ledger.seen(10)
    for _ in range(4):
        ledger.invalid("missing_id")
    _, hb = _run_source(_alerts(3), ledger, {"stale_after_hours": None, "expected_fields": ["location"]})
    assert "WARNING: 40% invalid" in hb["detail"] and "FIELD DRIFT: location missing on all 3 alerts" in hb["detail"]
    assert hb["detail"].index("WARNING") < hb["detail"].index("FIELD DRIFT")


def test_an_adapter_without_source_info_is_unaffected():
    adapter = SimpleNamespace(fetch=lambda: _alerts(3))
    with patch.dict(ea._ADAPTERS, {"x_src": (adapter, "emergency_alert_x")}, clear=True), \
         patch.object(ea, "_upsert_batch"), patch.object(ea, "_expire_stale", return_value=0), patch.object(ea, "_record_heartbeat") as hb:
        ea.run_source("x_src")
    assert hb.call_args.kwargs["detail"].endswith("0 expired")


# ---- source timezones (measured 2026-11-06) ---------------------------------------------

def test_parse_dmy_with_a_zone_applies_the_offset_for_that_date():
    assert parse_dmy_datetime("06/11/2026 14:48:00", "Australia/Melbourne") == "2026-11-06T14:48:00+11:00"  # AEDT
    assert parse_dmy_datetime("06/07/2026 2:48:00 PM", "Australia/Melbourne") == "2026-07-06T14:48:00+10:00"  # AEST
    assert parse_dmy_datetime("04/10/2026 03:30:00", "Australia/Melbourne") == "2026-10-04T03:30:00+11:00"  # first day of DST


def test_parse_dmy_without_a_zone_is_unchanged_so_nsw_stays_as_it_was():
    assert parse_dmy_datetime("06/11/2026 14:48:00") == "2026-11-06T14:48:00"


def test_an_unknown_zone_falls_back_to_the_offset_less_string_and_logs(caplog):
    with caplog.at_level(logging.WARNING):
        assert parse_dmy_datetime("06/11/2026 14:48:00", "Not/AZone") == "2026-11-06T14:48:00"
    assert "unavailable" in caplog.text


def test_nsw_timestamps_are_still_offset_less():
    alerts, _ = _run("nsw_rfs")
    assert all("+" not in a.updated_at_src and a.updated_at_src.count("-") == 2 for a in alerts if a.updated_at_src)


def test_vic_incident_and_act_times_now_carry_the_melbourne_and_sydney_offsets():
    incidents = vic_emergency.parse_incidents(fixture_json("vic_emergency", "incidents.json"))
    assert incidents and all(a.updated_at_src.endswith("+11:00") and a.issued_at.endswith("+11:00") for a in incidents)
    act = act_esa.parse(fixture_bytes("act_esa", "synthetic_kept.xml"))
    assert act[0].updated_at_src == "2026-08-19T23:24:36+10:00"  # AEST in August


def test_vic_incident_time_is_in_the_past_at_capture_not_eleven_hours_ahead():
    """The regression this fixes: local time stored as UTC put VIC/ACT rows ~11 h in the future."""
    for alert in vic_emergency.parse_incidents(fixture_json("vic_emergency", "incidents.json")):
        assert datetime.fromisoformat(alert.updated_at_src) <= CAPTURE


# ---- SA <sent> --------------------------------------------------------------------------

def test_sa_updated_at_src_is_read_from_alert_sent_not_info():
    """<sent> is a child of <alert>; it was read from <info>, so updated_at_src was empty on every SA row."""
    alerts = sa_cfs.parse(fixture_bytes("sa_cfs", "feed.xml"))
    assert alerts and all(a.updated_at_src and a.updated_at_src.endswith("+10:30") for a in alerts)
    assert alerts[0].updated_at_src == "2026-11-06T16:17:43+10:30"


# ---- BOM unseen products ----------------------------------------------------------------

def test_a_new_bom_product_is_named_in_the_ledger_not_just_counted():
    feed = (b"<rss><channel><item><title>06/16:44 EDT Volcanic Ash Advisory for New South Wales</title>"
            b"<link>http://reg.bom.gov.au/x.shtml</link><guid>g</guid><pubDate>Fri, 06 Nov 2026 05:44:26 GMT</pubDate></item></channel></rss>")
    ledger = DropLedger()
    assert bom_warnings.parse_state_feed("NSW", feed, ledger=ledger) == []
    assert ledger.counts["excluded_unmatched_product"] == 1
    assert ledger.counts["unmapped_product_volcanic_ash_advisory"] == 1
    assert ledger.samples["excluded_unmatched_product"] == ["06/16:44 EDT Volcanic Ash Advisory for New South Wales"]
    assert "unmapped product_volcanic_ash_advisory 1" in ledger.summary()
