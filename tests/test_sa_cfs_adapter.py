"""SA CFS adapter: parses the CAP-AU Atom feed, and refuses a retirement
notice so a dead feed fails the heartbeat instead of looking like an alert."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence.ingestion.emergency_alert_adapters import sa_cfs


def _feed(entry_inner: str) -> bytes:
    return (
        "<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'><entry><content type='text/xml'>"
        "<alert xmlns='urn:oasis:names:tc:emergency:cap:1.2'><identifier>id-1</identifier>"
        f"<sent>2026-11-02T06:05:40+10:30</sent><info>{entry_inner}</info></alert></content></entry></feed>"
    ).encode()


def _info(headline="TAILEM BEND : STRUCTURE FIRE", warning="Incident", status="Going") -> str:
    return (
        "<category>Fire</category><event>Structure Fire</event>"
        f"<headline>{headline}</headline><description>Not Available</description>"
        f"<parameter><valueName>WarningLevel</valueName><value>{warning}</value></parameter>"
        f"<parameter><valueName>Status</valueName><value>{status}</value></parameter>"
        "<area><areaDesc>15 TREVENA RD TAILEM BEND</areaDesc><circle>-35.255825,139.459285 0.0</circle></area>"
    )


def test_incident_parses_with_coordinates_and_unknown_severity():
    [a] = sa_cfs.parse(_feed(_info()))
    assert (a.source_key, a.jurisdiction, a.severity, a.closed) == ("sa_cfs", "SA", "unknown", False)
    assert (a.latitude, a.longitude) == (-35.255825, 139.459285)
    assert a.location == "15 TREVENA RD TAILEM BEND"


@pytest.mark.parametrize("level,expected", [
    ("Advice", "advice"), ("Watch and Act", "watch_and_act"), ("Emergency Warning", "emergency_warning"),
])
def test_warning_level_maps_to_tier(level, expected):
    [a] = sa_cfs.parse(_feed(_info(warning=level)))
    assert a.severity == expected


def test_complete_status_marks_closed():
    [a] = sa_cfs.parse(_feed(_info(status="COMPLETE")))
    assert a.closed is True


def test_feed_retirement_notice_raises():
    with pytest.raises(RuntimeError, match="feed retired"):
        sa_cfs.parse(_feed(_info(headline="Feed Retirement Notice")))


def test_uses_the_official_cap_au_url_not_the_retired_one():
    assert sa_cfs._FEED_URL == "https://data.eso.sa.gov.au/feeds/prod/cap-au.xml"
