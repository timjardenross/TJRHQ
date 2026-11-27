"""Restoration status after recurrence wording. Synthetic events; no network, no model."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence import incident_clustering as ic

START = datetime(2026, 11, 25, 18, 0, tzinfo=timezone.utc)
NOW = START + timedelta(hours=26)
OUTAGE = "Telstra outage leaves thousands of customers without mobile service in Victoria"
BACK = "Telstra mobile service restored for customers in Victoria after outage"


def event(n, title, at):
    return {"id": f"{n:08x}-0000-4000-8000-000000000000", "title": title, "summary": "", "source": f"Outlet {n}", "geography": "AU",
            "collected_at": at.isoformat(), "published_at": at.isoformat(), "url": f"https://example.org/{n}"}


def telstra_status(latest):
    """(status of the incident holding the restored Telstra outage, whether the latest report joined it)."""
    events = [event(1, OUTAGE, START), event(2, BACK, START + timedelta(hours=7)), event(3, latest, START + timedelta(hours=19))]
    found = ic.cluster_incidents(events, now=NOW, force=True)
    ids = [{r.event_id for r in i.reports} for i in found]
    at = next(n for n, members in enumerate(ids) if events[1]["id"] in members)
    return found[at].restoration_status, events[2]["id"] in ids[at]


@pytest.mark.parametrize("title", [
    "Telstra outage returns, thousands of customers in Victoria without mobile service again",
    "Telstra outage has returned for mobile customers in Victoria",
    "Telstra outage: mobile customers in Victoria without service again",
    "Not again: Telstra outage returns for Victoria mobile customers",
    "Telstra outage returns as customers in Victoria say they cannot call",
])
def test_affirmed_recurrence_reopens_a_restored_service(title):
    assert telstra_status(title) == ("ongoing", True)


@pytest.mark.parametrize("title", [
    "Telstra says there is no evidence the mobile outage returned in Victoria",
    "Telstra denies mobile outage has returned in Victoria",
    "Telstra rules out claims the mobile outage returned for Victoria customers",
    "Telstra outage: mobile service is not down again for customers in Victoria",
    "Reports Telstra mobile outage returned in Victoria are false",
    "Telstra outage returns claim denied for Victoria mobile customers",
    "Telstra mobile outage hasn't recurred for customers in Victoria",
])
def test_denied_recurrence_does_not_reopen(title):
    assert telstra_status(title) == ("restored", True)      # joined the incident, so the guard is what kept it restored


@pytest.mark.parametrize("title", [
    "Telstra customers in Victoria fear mobile outage returns",
    "Has the Telstra mobile outage returned for customers in Victoria?",
    "Telstra checking whether mobile outage returned in Victoria",
    "Unconfirmed reports Telstra mobile outage returned in Victoria",
    "Telstra mobile outage reportedly returns for Victoria customers",
    "Telstra warns mobile customers in Victoria if outage returns",
    "Telstra outage: mobile service may be down again for customers in Victoria",
])
def test_uncertain_recurrence_does_not_reopen(title):
    assert telstra_status(title) == ("restored", True)      # joined the incident, so the guard is what kept it restored


@pytest.mark.parametrize("title", [
    "Optus outage returns, thousands of customers in Victoria without mobile service again",
    "Optus outage: mobile customers in Victoria without service again",
    "Vodafone outage has returned for mobile customers in Victoria",
])
def test_another_operators_recurrence_does_not_reopen(title):
    assert telstra_status(title) == ("restored", True)      # joined the incident, so the guard is what kept it restored
