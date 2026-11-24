"""Forward-dated source coverage: regulator consultation closing dates, CISA KEV due dates, MSRC, vendor lifecycle (endoflife.date).

Fixtures under tests/fixtures/forward_dates are excerpts of what was observed on 2026-11-24 (APRA listing HTML, Treasury listing HTML,
CISA KEV, MSRC and endoflife.date JSON). The ASIC fixture is SYNTHETIC: rebuilt from the rendered text, the live HTML was not captured.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

bs4 = pytest.importorskip("bs4")

from intelligence.ingestion import forward_dates as fd
from intelligence.ingestion.api_adapter import APIAdapter
from intelligence.ingestion.scrape_adapter import ScrapeAdapter
from intelligence.models import SourceRecord

FX = Path(__file__).parent / "fixtures" / "forward_dates"


def soup(name):
    return bs4.BeautifulSoup((FX / name).read_text(), "html.parser")


def src(name, source_type="scrape"):
    return SourceRecord(
        source_id="s",
        source_name=name,
        category="regulatory",
        priority_rank=2,
        url="https://example.test/",
        source_type=source_type,
        jurisdiction="AU",
        confidence_weight=0.9,
        active=True,
    )


# ── APRA ────────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_apra_open_consultation_carries_closing_date_in_summary():
    rows = fd.apra_listing(soup("apra_consultations.html"))
    open_rows = [r for r in rows if r["open"]]
    assert len(open_rows) == 1
    r = open_rows[0]
    assert r["closing_date"] == date(2027, 2, 3)
    assert "open until 3 February 2027 (closing date)" in r["summary"]
    assert r["url"].startswith("https://www.apra.gov.au/consultations/")


def test_apra_closed_consultation_is_labelled_closed_not_open():
    closed = [
        r for r in fd.apra_listing(soup("apra_consultations.html")) if not r["open"]
    ]
    assert closed and all(
        "closed" in r["summary"] and "open until" not in r["summary"] for r in closed
    )


def test_apra_news_published_date_is_read_from_the_teaser():
    rows = fd.apra_listing(soup("apra_news.html"))
    assert [r["published_at"].date() for r in rows] == [
        date(2026, 11, 24),
        date(2026, 11, 23),
    ]


def test_apra_detail_sentences_pick_submission_close_only():
    got = fd.apra_detail_sentences(soup("apra_detail.html"))
    assert got == [
        "The consultation will be open for 18 weeks and submissions close on 3 February 2027."
    ]


def test_apra_detail_fetch_is_bounded(monkeypatch):
    a = ScrapeAdapter(src("APRA Consultations"))
    calls = []
    monkeypatch.setattr(
        a,
        "_fetch_html",
        lambda url: calls.append(url) or (FX / "apra_detail.html").read_text(),
    )
    rows = [
        {
            "title": f"t{i}",
            "url": f"https://x/{i}",
            "summary": "s",
            "published_at": None,
            "open": True,
        }
        for i in range(10)
    ]
    items = a._items_from_listing(rows)
    assert len(items) == 10 and len(calls) == 3  # OR_INTEL_APRA_DETAIL_MAX default
    assert "submissions close on 3 February 2027" in items[0].raw_summary
    assert "submissions close" not in items[5].raw_summary


def test_apra_detail_failure_keeps_listing_date(monkeypatch):
    a = ScrapeAdapter(src("APRA Consultations"))

    def boom(url):
        raise RuntimeError("down")

    monkeypatch.setattr(a, "_fetch_html", boom)
    rows = [
        {
            "title": "t",
            "url": "https://x/1",
            "summary": "open until 3 February 2027",
            "published_at": None,
            "open": True,
        }
    ]
    assert a._items_from_listing(rows)[0].raw_summary == "open until 3 February 2027"


def test_apra_collect_uses_listing_parser(monkeypatch):
    a = ScrapeAdapter(src("APRA Media Releases"))
    monkeypatch.setattr(
        a, "_fetch_html", lambda url: (FX / "apra_news.html").read_text()
    )
    items = a.collect()
    assert [i.published_at.date() for i in items] == [
        date(2026, 11, 24),
        date(2026, 11, 23),
    ]


# ── Treasury / ASIC ─────────────────────────────────────────────────────────────────────────────────────────────────────


def test_treasury_rows_give_open_date_as_published_and_closing_date():
    rows = fd.treasury_listing(soup("treasury_consultations.html"))
    assert [r["closing_date"] for r in rows] == [
        date(2027, 1, 14),
        date(2026, 11, 26),
        date(2026, 10, 30),
    ]
    assert rows[0]["published_at"].date() == date(2026, 11, 19)
    assert "open until 14 January 2027 (closing date)" in rows[0]["summary"]
    assert rows[2]["summary"] == "Treasury consultation closed 30 October 2026."
    assert [r["open"] for r in rows] == [True, True, False]


def test_asic_only_open_consultations_with_day_first_dates():
    rows = fd.asic_consultations(soup("asic_consultations.html"))
    assert [r["title"][:6] for r in rows] == ["CS-075", "CS-068"]
    assert [r["closing_date"] for r in rows] == [
        date(2027, 1, 22),
        date(2026, 12, 4),
    ]  # 4/12 is 4 December
    assert "open until 22 January 2027" in rows[0]["summary"]


def test_listing_parser_returning_nothing_falls_back_to_generic(monkeypatch):
    a = ScrapeAdapter(src("Australian Treasury Consultations"))
    monkeypatch.setattr(
        a, "_fetch_html", lambda url: "<html><body><p>nothing here</p></body></html>"
    )
    assert (
        a.collect() == []
    )  # parser found no rows, the generic path took over and also found none: no exception, no items


# ── CISA KEV ────────────────────────────────────────────────────────────────────────────────────────────────────────────


def kev_items():
    a = APIAdapter(src("CISA Known Exploited Vulnerabilities", "api"))
    return a._parse_cisa_kev(json.loads((FX / "kev_sample.json").read_text()))


def test_kev_due_date_is_kept_in_summary():
    by_cve = {i.raw_title.split(":")[0]: i for i in kev_items()}
    s = by_cve["CVE-2026-133968"].raw_summary
    assert "CISA remediation due date: 26 November 2026" in s
    assert "Affected: Project MONAI MONAI Label." in s
    assert "ransomware" not in s  # Unknown is not reported
    assert (
        "Known ransomware campaign use: Known." in by_cve["CVE-2020-0001"].raw_summary
    )


def test_kev_newest_added_first():
    assert [i.raw_title.split(":")[0] for i in kev_items()] == [
        "CVE-2026-133968",
        "CVE-2026-129448",
        "CVE-2020-0001",
    ]


def test_kev_summary_without_due_date_is_unchanged_shape():
    assert fd.kev_summary({"shortDescription": "x"}) == "x"
    assert fd.kev_summary({"dueDate": "bad"}) is None


# ── MSRC ────────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_msrc_drops_mariner_notes_and_orders_by_initial_release():
    a = APIAdapter(src("Microsoft Security Response Center", "api"))
    items = a._parse_msrc(json.loads((FX / "msrc_updates.json").read_text()))
    assert [i.raw_title for i in items] == [
        "October 2026 Security Updates",
        "September 2026 Security Updates",
    ]
    assert all(i.raw_title for i in items)
    assert items[0].published_at.date() == date(2026, 10, 13)
    # only the newest month states the next Patch Tuesday (after today, so never a date already past); older months state none
    assert (
        "Next planned publication:" in items[0].raw_summary
        and "derived from that rule" in items[0].raw_summary
    )
    assert "Next planned publication" not in items[1].raw_summary


def test_patch_tuesday_rule():
    assert fd.second_tuesday(2026, 11) == date(2026, 11, 10)
    assert fd.next_patch_tuesday(date(2026, 11, 24)) == date(2026, 12, 8)
    assert fd.next_patch_tuesday(date(2026, 12, 8)) == date(
        2027, 1, 12
    )  # strictly after, year rollover
    assert fd.next_patch_tuesday(date(2026, 11, 1)) == date(2026, 11, 10)


# ── endoflife.date ──────────────────────────────────────────────────────────────────────────────────────────────────────


def test_endoflife_emits_only_future_milestones_inside_horizon():
    payload = json.loads((FX / "endoflife_windows_server.json").read_text())
    recs = fd.endoflife_items(payload, today=date(2026, 11, 24), horizon_days=730)
    got = [(r["date"].isoformat(), r["milestone"], r["title"]) for r in recs]
    assert got == [
        (
            "2027-01-12",
            "eolFrom",
            "Windows Server 2016 (LTSC): end of life on 12 January 2027",
        )
    ]
    wide = fd.endoflife_items(payload, today=date(2026, 11, 24), horizon_days=365 * 5)
    assert {r["milestone"] for r in wide} == {"eolFrom", "eoasFrom", "eoesFrom"}
    assert [r["date"] for r in wide] == sorted(r["date"] for r in wide)
    assert "learn.microsoft.com/lifecycle" in recs[0]["summary"]


def test_endoflife_titles_are_stable_across_runs():
    payload = json.loads((FX / "endoflife_windows_server.json").read_text())
    a = fd.endoflife_items(payload, date(2026, 11, 24))
    b = fd.endoflife_items(payload, date(2026, 11, 25))
    assert [r["title"] for r in a] == [r["title"] for r in b]


def test_endoflife_adapter_collects_per_slug_and_skips_404(monkeypatch):
    a = APIAdapter(src("endoflife.date Vendor Lifecycle", "api"))
    a.source.api_endpoint = "https://endoflife.date/api/v1/products"
    payload = json.loads((FX / "endoflife_windows_server.json").read_text())
    seen = []

    def fake(url):
        seen.append(url)
        if url.endswith("/windows-server"):
            return payload
        raise RuntimeError("HTTP 404")

    monkeypatch.setenv("OR_INTEL_ENDOFLIFE_PRODUCTS", "windows-server,nope")
    monkeypatch.setattr(a, "_fetch_json", fake)
    monkeypatch.setattr(
        fd,
        "endoflife_items",
        lambda p, t, horizon_days=730: [
            {
                "title": "T: end of life on 12 January 2027",
                "summary": "S",
                "url": "https://endoflife.date/windows-server",
            }
        ],
    )
    items = a.collect()
    assert seen == [
        "https://endoflife.date/api/v1/products/windows-server",
        "https://endoflife.date/api/v1/products/nope",
    ]
    assert len(items) == 1 and items[0].published_at is None


def test_endoflife_adapter_errors_when_every_slug_fails(monkeypatch):
    a = APIAdapter(src("endoflife.date Vendor Lifecycle", "api"))
    a.source.api_endpoint = "https://endoflife.date/api/v1/products"
    monkeypatch.setenv("OR_INTEL_ENDOFLIFE_PRODUCTS", "a")

    def boom(url):
        raise RuntimeError("HTTP 503")

    monkeypatch.setattr(a, "_fetch_json", boom)
    with pytest.raises(RuntimeError):
        a.collect()


# ── registry ────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_new_registry_rows_are_inactive_and_unique():
    sys.path.insert(0, str(_REPO / "tools" / "intelligence"))
    import seed_source_registry as reg

    names = [s["source_name"] for s in reg.SOURCES]
    for n in ("ASIC Consultations", "endoflife.date Vendor Lifecycle"):
        assert names.count(n) == 1
        assert next(s for s in reg.SOURCES if s["source_name"] == n)["active"] is False
