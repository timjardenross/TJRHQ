"""A feed that parses but lacks its documented container is BROKEN, not empty.

Ledger path (what run_source uses): raises FeedShapeError -> heartbeat 'failed', nothing expired.
Plain parse()/fetch(): historical lenient behaviour, unchanged."""

from __future__ import annotations

import sys
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
    DropLedger,
    FeedShapeError,
)

RSS_EMPTY = b"<rss><channel><title>t</title></channel></rss>"
RSS_NO_CHANNEL = b"<rss><item><title>x</title></item></rss>"
ATOM_EMPTY = b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
NOW = 1793944320000

JSON_CASES = [
    ("nsw_rfs", lambda d, lg: nsw_rfs.parse(d, lg), "features"),
    ("qld_fire", lambda d, lg: qld_fire.parse(d, lg), "features"),
    ("tas_fire", lambda d, lg: tas_fire.parse(d, NOW, lg), "features"),
    ("vic_emergency warnings", lambda d, lg: vic_emergency.parse_warnings(d, lg), "features"),
    ("vic_emergency incidents", lambda d, lg: vic_emergency.parse_incidents(d, lg), "results"),
]


@pytest.mark.parametrize("name,parse,key", JSON_CASES)
@pytest.mark.parametrize("payload", [{}, {"other": []}, {"features": None, "results": None}, [], "garbage"])
def test_json_without_its_container_raises_on_the_ledger_path(name, parse, key, payload):
    with pytest.raises(FeedShapeError, match="unexpected feed shape"):
        parse(payload, DropLedger())


@pytest.mark.parametrize("name,parse,key", JSON_CASES)
def test_json_with_an_empty_container_is_a_legitimately_quiet_feed(name, parse, key):
    ledger = DropLedger()
    assert parse({key: []}, ledger) == []
    assert ledger.as_dict() == {"items_seen": 0}


@pytest.mark.parametrize("plain", [nsw_rfs.parse, qld_fire.parse, vic_emergency.parse_warnings, vic_emergency.parse_incidents, tas_fire.parse])
def test_plain_parse_stays_lenient_for_a_missing_container(plain):
    assert plain({}) == []


@pytest.mark.parametrize("name,parse", [
    ("act_esa", lambda raw, lg: act_esa.parse(raw, lg)),
    ("wa warnings", lambda raw, lg: wa_dfes.parse_warnings(raw, lg)),
    ("wa incidents", lambda raw, lg: wa_dfes.parse_incidents(raw, {}, lg)),
    ("bom", lambda raw, lg: bom_warnings.parse_state_feed("NSW", raw, ledger=lg)),
])
def test_rss_without_a_channel_raises_on_the_ledger_path_but_an_empty_channel_is_quiet(name, parse):
    with pytest.raises(FeedShapeError, match="no <channel>"):
        parse(RSS_NO_CHANNEL, DropLedger())
    ledger = DropLedger()
    parse(RSS_EMPTY, ledger)
    assert ledger.as_dict() == {"items_seen": 0}


def test_rss_plain_parse_is_unchanged_without_a_channel():
    # Lenient (historical) behaviour: a channel-less document is still scanned for <item>,
    # which is exactly why the ledger path needs the explicit shape check.
    assert [a.event_key for a in act_esa.parse(RSS_NO_CHANNEL)] == ["x"]
    assert wa_dfes.parse_warnings(RSS_NO_CHANNEL)[0] == []  # type 'other' -> dropped as before


def test_atom_with_the_wrong_root_raises_but_an_empty_feed_is_quiet():
    with pytest.raises(FeedShapeError, match="not an Atom"):
        sa_cfs.parse(b"<html><body>maintenance</body></html>", DropLedger())
    assert sa_cfs.parse(ATOM_EMPTY, DropLedger()) == []
    assert sa_cfs.parse(b"<html/>") == []  # plain parse unchanged


def test_feed_shape_error_is_a_runtime_error_and_does_not_hide_per_item_errors():
    assert issubclass(FeedShapeError, RuntimeError)
    ledger = DropLedger()
    assert nsw_rfs.parse({"features": [None]}, ledger) == []
    assert ledger.invalid_total == 1  # a bad ITEM is still just invalid_unparseable_item


def test_run_source_fails_the_source_and_expires_nothing_when_the_container_is_missing():
    adapter = SimpleNamespace(fetch_with_ledger=lambda: (nsw_rfs.parse({"oops": 1}, (lg := DropLedger())), lg))
    with patch.dict(ea._ADAPTERS, {"x_src": (adapter, "emergency_alert_x")}, clear=True), \
         patch.object(ea, "_upsert_batch") as upsert, patch.object(ea, "_expire_stale") as expire, \
         patch.object(ea, "_record_heartbeat") as hb:
        result = ea.run_source("x_src")
    assert hb.call_args.kwargs["status"] == "failed"
    assert "unexpected feed shape" in hb.call_args.kwargs["error_message"]
    assert "nsw_rfs" in result["error"]
    upsert.assert_not_called()
    expire.assert_not_called()  # no false "lifted"


def test_a_missing_container_in_one_of_two_feeds_still_fails_the_source():
    """WA/VIC read two feeds: one broken feed must not hide behind the healthy one."""
    ok = b"<rss><channel></channel></rss>"
    urls = {wa_dfes._WARNINGS_URL: RSS_NO_CHANNEL, wa_dfes._INCIDENTS_URL: ok}
    with patch.object(wa_dfes, "http_get", lambda url: urls[url]), pytest.raises(FeedShapeError, match="wa_dfes warnings"):
        wa_dfes.fetch_with_ledger()
