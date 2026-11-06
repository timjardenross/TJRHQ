"""ACT ESA adapter: real snapshot (all Ambulance Responses) plus a marked-synthetic kept-path supplement (offline)."""

from __future__ import annotations

import pytest

from intelligence.ingestion.emergency_alert_adapters import act_esa
from tests.emergency_alert_helpers import (  # noqa: F401
    assert_in_schema,
    block_network,
    by,
    fixture_bytes,
    fixture_meta,
)

pytestmark = pytest.mark.usefixtures("block_network")


def test_live_snapshot_is_entirely_excluded_ambulance_responses():
    raw = fixture_bytes("act_esa", "feed.xml")
    assert raw.count(b"<item>") == 17
    assert raw.count(b"<type>AMBULANCE RESPONSE</type>") == 17
    assert act_esa.parse(raw) == []


def test_synthetic_supplement_is_marked_synthetic():
    assert fixture_meta("act_esa")["feeds"]["synthetic_kept.xml"]["synthetic"] is True
    assert fixture_meta("act_esa")["feeds"]["feed.xml"]["synthetic"] is False


def test_synthetic_kept_path_totals_and_exclusions():
    alerts = act_esa.parse(fixture_bytes("act_esa", "synthetic_kept.xml"))
    assert [a.event_key for a in alerts] == ["900001-19082026", "900002-19082026", "GRASS FIRE - NO GUID"]
    assert by(alerts, "severity") == {"unknown": 3}  # the incidents feed carries no warning level
    assert by(alerts, "alert_type") == {"bushfire": 1, "other": 2}
    assert_in_schema(alerts)
    keys = {a.event_key for a in alerts}
    assert keys.isdisjoint({"900003-19082026", "900004-19082026", "900005-19082026"})  # hazard reduction, MVA, ambulance


def test_synthetic_kept_item_fields():
    bush = act_esa.parse(fixture_bytes("act_esa", "synthetic_kept.xml"))[0]
    assert (bush.latitude, bush.longitude) == (-35.3, 149.1)
    assert bush.location == "EXAMPLE VALLEY"
    assert bush.updated_at_src == "2026-08-19T23:24:36+10:00"  # local Canberra time (AEST in August), measured 2026-11-06
    assert bush.canonical_url.endswith("#900001-19082026")


def test_fetch_is_http_get_plus_parse(monkeypatch):
    raw = fixture_bytes("act_esa", "synthetic_kept.xml")
    monkeypatch.setattr(act_esa, "http_get", lambda url: raw)
    assert act_esa.fetch() == act_esa.parse(raw)
