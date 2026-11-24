"""Governance/aftermath headlines about a PAST outage (AGM, shareholder grilling, economic-cost modelling, 'fell short') must not read as a
live disruption. Real Telstra headlines from 12-13 Oct 2026 (collected via Google News, an aggregator) were merged into one 9-report incident
shown as 'URGENT TO VERIFY ... restoration ongoing' about an outage that happened on 8 Jul. Live Telstra reports must keep working."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import brief_evidence as be
from intelligence import event_detection as ed

GN = "Google News - Telstra"
AFTERMATH = [  # (title, published, collected)
    ("Telstra execs face shareholder grilling over outage - The Canberra Times", "2026-10-12T16:40:26Z", "2026-10-12T19:00:19Z"),
    ("‘Didn’t foot the bill’: Telstra outage cost the economy half a billion dollars, modelling finds - SMH.com.au", "2026-10-13T00:50:11Z", "2026-10-13T01:58:11Z"),
    ("‘Fell short’: Telstra on massive outage - News.com.au", "2026-10-13T00:14:46Z", "2026-10-13T01:58:11Z"),
    ("Telstra ‘fell short’ on massive outage - Herald Sun", "2026-10-13T02:13:09Z", "2026-10-13T04:58:09Z"),
    ("Telstra Outage Costs Economy $552M, Says Report [2026] - tech-insider.org", "2026-10-13T01:59:03Z", "2026-10-13T04:58:09Z"),
    ("Telstra boss faces AGM fury over national outage - The Australian", "2026-10-13T05:50:26Z", "2026-10-13T07:58:08Z"),
    ("Telstra outage cost Australia more than half a billion dollars, modelling finds - Nine.com.au", "2026-10-13T11:08:12Z", "2026-10-13T13:58:07Z"),
]
NOW = datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)


def _event(i, title, published, collected, source=GN):
    return {"id": f"e{i}", "title": title, "source": source, "geography": "AU", "published_at": published, "collected_at": collected, "summary": title}


@pytest.mark.parametrize("title,published,collected", AFTERMATH)
def test_aftermath_headline_is_retrospective_and_never_ongoing(title, published, collected):
    c = ed.detect_candidate(_event(0, title, published, collected))
    assert c.status == "retrospective" and c.ongoing is False


@pytest.mark.parametrize("title,expected", [
    ("Telstra mobile network outage hits thousands of customers across Victoria", "stated"),
    ("Telstra customers still without service as outage continues", "stated"),
    ("Optus outage: Triple Zero calls failing for customers in Victoria and South Australia", "stated"),
    ("NAB customers experiencing phone and internet banking outages", "stated"),
    ("Microsoft Outlook outage leaves millions of Australian customers unable to access email", "stated"),
    ("OFX warns shareholders of cyber incident affecting customer data", "stated"),   # 'shareholders' alone must not make a live incident retrospective
])
def test_live_reports_are_unchanged(title, expected):
    c = ed.detect_candidate(_event(0, title, "2026-10-13T05:50:26Z", "2026-10-13T06:10:00Z", source="ABC News"))
    assert c.status == expected, (title, c.status)


def test_telstra_aftermath_cluster_is_not_an_urgent_verification_or_ongoing_incident():
    events = [_event(i, t, p, c) for i, (t, p, c) in enumerate(AFTERMATH)]
    es = be.build_evidence(events, now=NOW)
    for incident in es.incidents:
        assert incident.urgent_verify is False, incident
        assert incident.record.get("restoration_status") != "ongoing", incident
    lines = be.morning_view(es)
    assert not any("URGENT TO VERIFY" in line and "Telstra" in line for line in lines)


def test_a_live_report_alongside_aftermath_still_surfaces_the_incident():
    live = _event(99, "Telstra mobile network outage hits thousands of customers across Victoria - ABC News", "2026-10-13T18:30:00Z", "2026-10-13T18:45:00Z", source="ABC News")
    events = [_event(i, t, p, c) for i, (t, p, c) in enumerate(AFTERMATH)] + [live]
    es = be.build_evidence(events, now=NOW)
    assert any(i.impact_status == "stated" or i.record.get("restoration_status") in ("ongoing", "unknown") for i in es.incidents)
