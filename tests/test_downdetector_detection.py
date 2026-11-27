"""Outage detection end to end on archived page excerpts: parsing, episode identity, storage and alert eligibility.

Offline: the fetch, the observation ledger, the event table and the sender are in-memory stand-ins.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

import core.platform.notification_service as notifications
from intelligence.classification.classifier import classify
from intelligence.classification.filter import apply_filter
from intelligence.ingestion import downdetector_adapter as da
from intelligence.ingestion.phase_a_enrichment import enrich_and_save
from intelligence.persistence import intelligence_store as store
from intelligence.ranking.ranker import rank

FIXTURES = Path(__file__).parent / "fixtures" / "downdetector"
TOP = (FIXTURES / "telstra_20260709_top_status.html").read_text()          # 321 reports
MAJOR = (FIXTURES / "telstra_20260707_top_status.html").read_text()        # 7,298 reports
QUIET = (FIXTURES / "telstra_archived_quiet.html").read_text()             # 125 reports
POSSIBLE = TOP.replace("status: experiencing problems", "status: possible problems").replace(
    ">problems</span>", ">possible problems</span>")


@pytest.mark.parametrize("page,expected", [
    (MAJOR, ("problems", 7298)), (TOP, ("problems", 321)), (QUIET, ("no_problems", 125)), (POSSIBLE, ("possible_problems", 321)),
])
def test_archived_pages_parse_with_their_counts(page, expected):
    assert da.parse_status_and_count(page) == expected


class Source:
    source_id = "00000000-0000-0000-0000-000000000001"
    source_name = "Downdetector AU — Telstra"
    url = "https://downdetector.com.au/status/telstra/"
    priority_rank = 2
    confidence_weight = 0.85
    category = "critical_infrastructure"
    source_type = "downdetector"
    jurisdiction = "AU"
    content_expectation = "intermittent"
    rss_url = None
    active = True


class World:
    """One company, a controllable clock, and everything the pipeline would persist or send."""

    def __init__(self, monkeypatch, level=150, history_readable=True):
        self.now = datetime(2026, 7, 7, 3, 0, tzinfo=timezone.utc)          # 13:00 Melbourne
        self.ledger, self.events, self.alerts = [], [], []
        self.page = QUIET
        world = self

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return world.now if tz else world.now.replace(tzinfo=None)

        def post(table, row, **_):
            if table != "intelligence_events":
                return {}
            self.events.append(dict(row))
            return {"event_id": f"e{len(self.events)}", **row}

        monkeypatch.setattr(da, "datetime", Clock)
        monkeypatch.setattr(da.DowndetectorAdapter, "_fetch_html", lambda *_: world.page)
        monkeypatch.setattr(da, "get_report_count_floor", lambda *_: level)
        monkeypatch.setattr(store, "save_downdetector_observation", lambda **kw: self.ledger.append(
            {"observed_at": self.now.isoformat(), "status": kw["status"], "report_count": kw["report_count"]}))
        monkeypatch.setattr(store, "load_downdetector_history", lambda *_: list(self.ledger) if history_readable else [])
        monkeypatch.setattr(store, "_existing_values", lambda column, values: {e.get(column) for e in self.events} & set(values))
        monkeypatch.setattr(store, "_get", lambda *a, **k: [])
        monkeypatch.setattr(store, "_post", post)
        monkeypatch.setattr(notifications, "notify", lambda body, **kw: self.alerts.append(kw.get("title")) or mock.MagicMock())

    def check(self, page, hours_later=2):
        self.now += timedelta(hours=hours_later)
        self.page = page
        adapter = da.DowndetectorAdapter.__new__(da.DowndetectorAdapter)
        adapter.source = Source()
        events = store.filter_unpersisted_events([classify(i) for i in adapter.collect()])
        apply_filter(events)
        enrich_and_save(rank(events), store, shadow_mode=False)
        return len(self.events), len(self.alerts)


def test_a_qualifying_outage_is_detected_stored_and_alert_eligible(monkeypatch):
    world = World(monkeypatch)
    assert world.check(QUIET) == (0, 0)
    assert world.check(TOP) == (1, 1)
    stored = world.events[0]
    assert stored["event_type"] == "telecom_outage" and stored["customer_impact"] == "high" and not stored["suppressed"]


def test_a_continuing_outage_stays_one_incident_across_midnight(monkeypatch):
    world = World(monkeypatch)
    world.check(TOP)
    for _ in range(18):                                                     # 36 hours of two-hourly checks, past two midnights
        assert world.check(TOP) == (1, 1)


def test_a_wavering_or_sparsely_checked_outage_is_not_raised_again(monkeypatch):
    world = World(monkeypatch)
    world.check(TOP)
    assert world.check(POSSIBLE) == (1, 1)
    assert world.check(TOP) == (1, 1)
    assert world.check(TOP, hours_later=24) == (1, 1)                       # once-a-day checking


def test_two_outages_on_one_day_are_both_raised(monkeypatch):
    world = World(monkeypatch)
    assert world.check(TOP) == (1, 1)
    world.check(QUIET)
    assert world.check(MAJOR) == (2, 2)
    assert len({e["dedup_hash"] for e in world.events}) == 2 and len({e["canonical_url"] for e in world.events}) == 2


def test_a_later_outage_is_not_blocked_by_an_earlier_stored_one(monkeypatch):
    world = World(monkeypatch)
    world.check(TOP)
    world.check(QUIET, hours_later=24)
    assert world.check(TOP, hours_later=24 * 20) == (2, 2)


def test_the_detection_rule_is_unchanged(monkeypatch):
    world = World(monkeypatch, level=500)
    assert world.check(TOP) == (0, 0)                                       # top status, below the level
    assert world.check(POSSIBLE.replace("321 reports", "900 reports")) == (0, 0)     # above the level, not top status
    assert world.check(MAJOR) == (1, 1)


def test_unreadable_history_gives_one_item_a_day_not_one_per_check(monkeypatch):
    world = World(monkeypatch, history_readable=False)
    assert world.check(TOP) == (1, 1)
    assert world.check(TOP) == (1, 1)


def test_episode_start_ends_at_recovery_or_a_long_silence():
    now = datetime(2026, 7, 8, 12, tzinfo=timezone.utc)

    def row(hours, status):
        return {"observed_at": (now - timedelta(hours=hours)).isoformat(), "status": status}

    assert da.episode_start([], now) is None
    assert da.episode_start([row(6, "problems"), row(4, "possible_problems"), row(2, "problems")], now) == now - timedelta(hours=6)
    assert da.episode_start([row(6, "problems"), row(4, "no_problems"), row(2, "problems")], now) == now - timedelta(hours=2)
    assert da.episode_start([row(80, "problems"), row(2, "problems")], now) == now - timedelta(hours=2)


def test_two_companies_in_one_collection_run_are_both_stored_and_eligible(monkeypatch):
    world = World(monkeypatch)
    world.page = TOP
    items = []
    for number, name, slug in ((1, "Telstra", "telstra"), (2, "Optus", "optus")):
        source = Source()
        source.source_id, source.source_name = f"00000000-0000-0000-0000-00000000000{number}", f"Downdetector AU — {name}"
        source.url = f"https://downdetector.com.au/status/{slug}/"
        adapter = da.DowndetectorAdapter.__new__(da.DowndetectorAdapter)
        adapter.source = source
        world.page = TOP.replace(">Telstra<", f">{name}<")
        items += adapter.collect()
    events = store.filter_unpersisted_events([classify(i) for i in items])
    apply_filter(events)
    enrich_and_save(rank(events), store, shadow_mode=False)
    assert len(world.events) == 2 and len(world.alerts) == 2
