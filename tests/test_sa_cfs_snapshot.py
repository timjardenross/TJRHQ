"""SA CFS adapter against a real captured CAP-AU snapshot (offline). Synthetic-input tests are in test_sa_cfs_adapter.py."""

from __future__ import annotations

import pytest

from intelligence.ingestion.emergency_alert_adapters import sa_cfs
from tests.emergency_alert_helpers import (  # noqa: F401
    assert_in_schema,
    block_network,
    by,
    fixture_bytes,
)

pytestmark = pytest.mark.usefixtures("block_network")


@pytest.fixture(scope="module")
def raw():
    return fixture_bytes("sa_cfs", "feed.xml")


def test_snapshot_totals(raw):
    alerts = sa_cfs.parse(raw)
    assert raw.count(b"<entry>") == 7
    assert len(alerts) == 3
    assert by(alerts, "severity") == {"unknown": 3}  # live WarningLevel is "Incident": no AWS tier in the value
    assert by(alerts, "alert_type") == {"bushfire": 3}
    assert_in_schema(alerts)


def test_stable_event_key_for_a_known_item(raw):
    alert = next(a for a in sa_cfs.parse(raw) if a.event_key == "F2611060088-2026-11-06T14:36:42+10:30")
    assert alert.headline == "YACKA : GRASS FIRE"
    assert alert.closed is False
    assert alert.canonical_url is None


def test_planned_burns_and_structure_fires_are_excluded(raw):
    headlines = {a.headline for a in sa_cfs.parse(raw)}
    assert headlines == {"CRAIGMORE : GRASS FIRE", "YACKA : GRASS FIRE", "SEVENHILL : GRASS FIRE"}
    for dropped in (b"BURNOFF PRESCRIBED", b"MOUNT BARKER : BURN OFF", b"LAMEROO : STRUCTURE FIRE", b"RENMARK : STRUCTURE FIRE"):
        assert dropped in raw


def test_fetch_is_http_get_plus_parse(raw, monkeypatch):
    monkeypatch.setattr(sa_cfs, "http_get", lambda url: raw)
    assert sa_cfs.fetch() == sa_cfs.parse(raw)
