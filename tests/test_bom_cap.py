"""BoM CAP-AU enrichment (bom_cap.py): CAP fields are copied onto the RSS-derived bom_* alerts by a conservative
match, never change which alerts exist, and an outage or a flag-off leaves them RSS-only. Offline, on fixtures
captured from the live WMO feed."""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence.ingestion.emergency_alert_adapters import bom_cap, bom_warnings
from intelligence.ingestion.emergency_alert_adapters.base import DropLedger
from tests.emergency_alert_helpers import (  # noqa: F401
    FIXTURE_ROOT,
    block_network,
    fixture_bytes,
)

pytestmark = pytest.mark.usefixtures("block_network")

INDEX = fixture_bytes("bom_nsw", "wmo_index.xml")
CAP_FIELDS = {"cap_event", "cap_urgency", "cap_certainty", "cap_severity"}


@pytest.fixture(autouse=True)
def _fresh_caches():
    bom_cap._index_cache = None
    bom_cap._message_cache.clear()
    yield
    bom_cap._index_cache = None
    bom_cap._message_cache.clear()


def _message_files() -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in (FIXTURE_ROOT / "bom_nsw").glob("cap_*.xml")}


def _serve(url: str, timeout: int = 20) -> bytes:
    """Offline stand-in for http_get: the WMO index, or a CAP message found via its index item."""
    if url == bom_cap._INDEX_URL:
        return INDEX
    for ref in bom_cap.parse_index(INDEX):
        if ref.link == url:
            name = "cap_" + re.sub(r"\W", "_", f"AusBoM-{ref.code}-{ref.sent.isoformat()}") + ".xml"
            return _message_files()[name]
    raise OSError(f"unexpected url {url}")


def _nsw_alerts():
    return bom_warnings.parse_state_feed("NSW", fixture_bytes("bom_nsw", "feed.xml"), detail_for=None, ledger=DropLedger())


def test_parse_index_reads_product_code_time_and_type():
    refs = bom_cap.parse_index(INDEX)
    assert len(refs) == 9
    fire = next(r for r in refs if r.code == "IDN22000")
    assert fire.type == "fire_weather" and fire.sent == datetime(2026, 11, 6, 5, 8, 15, tzinfo=timezone.utc)
    assert {"greater", "hunter"} <= fire.location
    assert any(r.type == "thunderstorm" for r in refs) and any(r.type == "heatwave" for r in refs)


def test_parse_message_reads_the_four_cap_fields():
    fire = _message_files()["cap_AusBoM_IDN22000_2026_11_06T05_08_15_00_00.xml"]
    assert bom_cap.parse_message(fire) == {"cap_event": "Fire Weather", "cap_urgency": "Unknown", "cap_certainty": "Unknown", "cap_severity": "Severe"}
    with pytest.raises(ValueError):
        bom_cap.parse_message(b"<alert xmlns='urn:oasis:names:tc:emergency:cap:1.2'/>")


def test_enrich_matches_the_fire_weather_alert_and_only_adds_cap_fields():
    plain, enriched = _nsw_alerts(), _nsw_alerts()
    with patch.object(bom_cap, "http_get", _serve):
        n = bom_cap.enrich(enriched, "NSW", index_raw=INDEX)
    assert n >= 1
    assert [a.event_key for a in plain] == [a.event_key for a in enriched]
    for before, after in zip(plain, enriched):
        changed = {k for k, v in asdict(after).items() if v != asdict(before)[k]}
        assert changed <= CAP_FIELDS
    fire = next(a for a in enriched if "Fire Weather" in a.headline)
    assert (fire.cap_event, fire.cap_severity) == ("Fire Weather", "Severe")
    assert fire.severity == "unknown"  # never derived from CAP


def test_unmatched_alerts_stay_rss_only():
    alerts = _nsw_alerts()
    with patch.object(bom_cap, "http_get", _serve):
        bom_cap.enrich(alerts, "NSW", index_raw=INDEX)
    floods = [a for a in alerts if "Flood" in a.headline]
    assert floods and all(a.cap_urgency is None for a in floods)  # their CAP messages are outside the captured window


def _ref(code, sent, title, link="https://x/1"):
    return bom_cap.CapRef(code, sent, title, link, bom_cap._type_of(title), bom_cap._location_words(title))


T0 = datetime(2026, 11, 6, 5, 0, tzinfo=timezone.utc)


def test_match_prefers_location_words_and_picks_the_newest_message():
    older = _ref("IDQ20855", T0 - timedelta(hours=3), "Moderate Flood Warning for Bulloo River at Quilpie")
    newer = _ref("IDQ20855", T0 - timedelta(hours=1), "Moderate Flood Warning for Bulloo River at Quilpie", "https://x/2")
    other = _ref("IDQ20860", T0 - timedelta(hours=1), "Minor Flood Warning for Thomson River")
    got = bom_cap.match("Moderate Flood Warning for the Bulloo River", "QLD", T0, [older, newer, other])
    assert got is newer


def test_match_refuses_when_two_products_fit():
    a = _ref("IDQ20855", T0, "Minor Flood Warning for Bulloo River")
    b = _ref("IDN36631", T0, "Minor Flood Warning for Bulloo River (NSW)")
    assert bom_cap.match("Minor Flood Warning for the Bulloo River", "QLD", T0, [a, b]) is None


def test_match_falls_back_to_a_unique_same_state_message_sent_at_the_same_minute():
    surf = _ref("IDN28522", T0, "Hazardous Surf Warning for Hunter Coast: Seal Rocks to Broken Bay")
    assert bom_cap.match("Hazardous Surf Warning for New South Wales", "NSW", T0 + timedelta(seconds=40), [surf]) is surf
    assert bom_cap.match("Hazardous Surf Warning for New South Wales", "VIC", T0 + timedelta(seconds=40), [surf]) is None  # wrong state
    assert bom_cap.match("Hazardous Surf Warning for New South Wales", "NSW", T0 + timedelta(minutes=10), [surf]) is None  # too far apart


def test_match_ignores_messages_newer_than_the_rss_item():
    future = _ref("IDQ20855", T0 + timedelta(hours=2), "Moderate Flood Warning for Bulloo River")
    assert bom_cap.match("Moderate Flood Warning for the Bulloo River", "QLD", T0, [future]) is None


def test_match_needs_a_known_warning_type():
    assert bom_cap.match("Some New Product for Sydney", "NSW", T0, [_ref("IDN1", T0, "Some New Product for Sydney")]) is None


def test_outage_keeps_the_alerts_and_logs(caplog):
    alerts = _nsw_alerts()
    with patch.object(bom_cap, "http_get", side_effect=OSError("down")), caplog.at_level(logging.WARNING):
        assert bom_cap.enrich(alerts, "NSW") == 0
    assert all(a.cap_urgency is None for a in alerts)
    assert "WMO CAP index unavailable" in caplog.text


def test_bad_index_never_raises():
    assert bom_cap.enrich(_nsw_alerts(), "NSW", index_raw=b"not xml") == 0


def test_an_unreadable_cap_message_leaves_that_alert_rss_only(caplog):
    alerts = _nsw_alerts()

    def serve(url, timeout=20):
        if url != bom_cap._INDEX_URL:
            raise OSError("message fetch failed")
        return _serve(url)

    with patch.object(bom_cap, "http_get", serve), caplog.at_level(logging.WARNING):
        assert bom_cap.enrich(alerts, "NSW", index_raw=INDEX) == 0  # must not raise
    assert all(a.cap_event is None for a in alerts)
    assert "could not enrich" in caplog.text


@pytest.mark.parametrize("value", ["0", "false", "OFF", "no"])
def test_flag_off_disables_enrichment(monkeypatch, value):
    monkeypatch.setenv("EMERGENCY_ALERTS_BOM_CAP", value)
    alerts = _nsw_alerts()
    with patch.object(bom_cap, "http_get", _serve):
        assert bom_cap.enrich(alerts, "NSW", index_raw=INDEX) == 0
    assert all(a.cap_urgency is None for a in alerts)


def test_index_is_fetched_once_for_several_states():
    calls = []

    def serve(url, timeout=20):
        calls.append(url)
        return _serve(url)

    with patch.object(bom_cap, "http_get", serve):
        for state in ("NSW", "ACT", "VIC"):
            bom_cap.enrich(_nsw_alerts(), state)
    assert calls.count(bom_cap._INDEX_URL) == 1


def test_state_adapter_fetch_enriches_and_keeps_the_ledger_invariant():
    with patch.object(bom_warnings, "_http_get_bom", return_value=fixture_bytes("bom_nsw", "feed.xml")), \
         patch.object(bom_warnings, "_fetch_detail", return_value={"issued_at": None, "issued_local": None, "body": None}), \
         patch.object(bom_cap, "http_get", _serve):
        alerts, ledger = bom_warnings.nsw.fetch_with_ledger()
    assert any(a.cap_event for a in alerts)
    assert ledger.items_seen == len(alerts) + ledger.excluded_total + ledger.invalid_total
