"""Collection reliability regressions (2026-11-24).

- RSS/feed per-run ceiling no longer cuts a 60-entry feed to 20.
- NVD: newest CVEs first (the API is oldest-first), not the same 20 oldest every day.
- iTnews joins the 90-minute media sweep; the daily 06:00 job tolerates a late start.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import config, scheduler
from intelligence.ingestion import api_adapter as aa
from intelligence.models import SourceRecord


def _src(name, category="cloud_technology", source_type="rss"):
    return SourceRecord(source_id=f"id-{name}", source_name=name, category=category, priority_rank=1,
                        url="https://example.test/", source_type=source_type, jurisdiction="AU",
                        confidence_weight=0.8, active=True)


def test_feed_ceiling_above_old_flat_20():
    assert config.MAX_FEED_ITEMS_PER_SOURCE > 20
    assert config.MAX_FEED_ITEMS_PER_SOURCE >= 50  # Statuspage incidents.json returns 50


def test_statuspage_incidents_not_cut_to_20():
    adapter = aa.APIAdapter(_src("GitHub Status", "cloud_technology", "api"))
    incidents = [{"id": f"i{n}", "name": f"Incident {n}", "status": "resolved", "impact": "major",
                  "created_at": "2026-10-06T00:00:00Z", "incident_updates": []} for n in range(50)]
    assert len(adapter._parse_statuspage_incidents({"incidents": incidents})) == 50


def test_feed_bytes_not_cut_to_20():
    pytest.importorskip("feedparser")
    entries = "".join(f"<item><title>T{n}</title><link>https://x.test/{n}</link></item>" for n in range(60))
    raw = f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{entries}</channel></rss>'.encode()
    adapter = aa.APIAdapter(_src("Geoscience Australia Earthquakes", "critical_infrastructure", "api"))
    assert len(adapter._parse_feed_bytes(raw, "https://x.test/feed")["__feed_items__"]) == 60


def test_nvd_returns_newest_first_not_the_oldest_20():
    adapter = aa.APIAdapter(_src("NVD / NIST CVE Database", "cybersecurity", "api"))
    # NVD returns oldest first: day 1 .. day 40 (two per day is irrelevant, one per entry here)
    vulns = [{"cve": {"id": f"CVE-2026-{n:04d}", "published": f"2026-11-{1 + n // 2:02d}T{n % 2:02d}:00:00.000",
                      "descriptions": [{"lang": "en", "value": "d"}]}} for n in range(40)]
    items = adapter._parse_nvd({"vulnerabilities": vulns})
    assert len(items) == 40  # under NVD_MAX_ITEMS_PER_RUN
    assert items[0].raw_title == "CVE-2026-0039"  # newest first
    assert aa.NVD_MAX_ITEMS_PER_RUN >= 100


def test_nvd_cap_keeps_newest(monkeypatch):
    monkeypatch.setattr(aa, "NVD_MAX_ITEMS_PER_RUN", 5)
    adapter = aa.APIAdapter(_src("NVD / NIST CVE Database", "cybersecurity", "api"))
    vulns = [{"cve": {"id": f"CVE-{n:03d}", "published": f"2026-11-01T00:{n:02d}:00.000", "descriptions": []}}
             for n in range(30)]
    ids = [i.raw_title for i in adapter._parse_nvd({"vulnerabilities": vulns})]
    assert ids == [f"CVE-{n:03d}" for n in range(29, 24, -1)]


def test_nvd_window_covers_an_outage_but_stays_bounded():
    assert 72 <= config.NVD_WINDOW_HOURS <= 120


def test_nvd_follows_pages_so_a_catch_up_is_complete(monkeypatch):
    pages = {0: [{"cve": {"id": f"CVE-{n}", "published": "2026-11-01T00:00:00.000", "descriptions": []}} for n in range(3)],
             3: [{"cve": {"id": f"CVE-{n}", "published": "2026-11-02T00:00:00.000", "descriptions": []}} for n in range(3, 5)]}
    calls = []

    def fake(self, endpoint):
        calls.append(endpoint)
        idx = int(endpoint.split("startIndex=")[1]) if "startIndex=" in endpoint else 0
        return {"totalResults": 5, "vulnerabilities": pages[idx]}

    monkeypatch.setattr(aa.APIAdapter, "_fetch_json", fake)
    adapter = aa.APIAdapter(_src("NVD / NIST CVE Database", "cybersecurity", "api"))
    items = adapter.collect()
    assert len(calls) == 2 and "startIndex=3" in calls[1]
    assert {i.raw_title for i in items} == {f"CVE-{n}" for n in range(5)}


def test_itnews_in_media_sweep_only_as_rss():
    sources = [_src("ABC News", "media"), _src("iTnews", "cybersecurity"), _src("CISA Alerts", "cybersecurity"),
               _src("AEMO Market Notices", "critical_infrastructure", "scrape"),
               _src("iTnews", "cybersecurity", "scrape")]
    names = [(s.source_name, s.source_type) for s in scheduler._select_intraday_media_sources(sources)]
    assert names == [("ABC News", "rss"), ("iTnews", "rss")]


def test_daily_collection_has_misfire_grace():
    assert scheduler._DAILY_COLLECTION_MISFIRE_GRACE_SECONDS >= 3600


def test_github_status_paused_by_default(monkeypatch):
    monkeypatch.delenv("INTELLIGENCE_PAUSED_SOURCES", raising=False)
    assert config.paused_source_names() == frozenset({"GitHub Status"})


@pytest.mark.parametrize("val,expected", [("none", set()), ("", set()), ("A, B", {"A", "B"})])
def test_pause_env_override(monkeypatch, val, expected):
    monkeypatch.setenv("INTELLIGENCE_PAUSED_SOURCES", val)
    assert config.paused_source_names() == expected


def test_collect_all_skips_paused_source_only(monkeypatch):
    from datetime import datetime, timezone

    from intelligence.ingestion import collection_engine as ce
    seen = []

    class _A:
        def __init__(self, source):
            self.source = source

        def run(self):
            seen.append(self.source.source_name)
            return [], ce.SourceHealth(source_id=self.source.source_id, source_name=self.source.source_name,
                                       checked_at=datetime.now(timezone.utc), status="ok")

    monkeypatch.setattr(ce, "_ADAPTER_MAP", {"api": _A, "uptime_kuma": _A})
    monkeypatch.setattr(ce.store, "save_source_health_batch", lambda h: None)
    srcs = [_src("GitHub Status", source_type="api"),
            _src("GitHub Status (Uptime Kuma direct probe)", source_type="uptime_kuma")]
    monkeypatch.delenv("INTELLIGENCE_PAUSED_SOURCES", raising=False)
    ce.collect_all(sources=srcs)
    assert seen == ["GitHub Status (Uptime Kuma direct probe)"]
    seen.clear()
    monkeypatch.setenv("INTELLIGENCE_PAUSED_SOURCES", "none")
    ce.collect_all(sources=srcs)
    assert sorted(seen) == sorted(s.source_name for s in srcs)
