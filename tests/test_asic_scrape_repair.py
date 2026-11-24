"""ASIC News Centre / Enforcement Activity returned 'no items' on every check from early September 2026.

Two demonstrated defects: (1) the release list is rendered client-side, so the plain fetch holds only page chrome;
(2) the 'h3 a' selector yields the <a> itself, and the old extraction looked for a title INSIDE it, skipping every item.
The fixture is real rendered HTML captured from asic.gov.au/newsroom/media-releases on 2026-11-24.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import scheduler
from intelligence.ingestion import scrape_adapter as sa
from intelligence.models import SourceRecord

_RENDERED = (_REPO / "tests/fixtures/asic_media_releases_rendered_20261124.html").read_text(encoding="utf-8")
_CHROME = "<html><body><nav><ul><li><a href='/newsroom/media-releases/'>Media releases</a></li></ul></nav><p>Trending:</p></body></html>"


def _adapter(name="ASIC Enforcement Activity"):
    src = SourceRecord(source_id="id-asic", source_name=name, category="financial_services", priority_rank=2,
                       url="https://www.asic.gov.au/newsroom/media-releases", source_type="scrape", jurisdiction="AU",
                       confidence_weight=0.9, active=True)
    return sa.ScrapeAdapter(src)


def test_rendered_list_parses_titles_links_and_dates():
    a = _adapter()
    a._fetch_html = lambda url: _RENDERED
    items = a.collect()
    assert len(items) == 6
    first = items[0]
    assert first.raw_title.startswith("Berndale director Stavro D") and (first.canonical_url or "").startswith("https://www.asic.gov.au/")
    assert first.published_at is not None and (first.published_at.year, first.published_at.month) == (2026, 11)


def test_plain_chrome_alone_yields_nothing_so_asic_renders_via_firecrawl(monkeypatch):
    calls = []
    monkeypatch.setattr(sa.firecrawl_client, "fetch_html", lambda url, timeout=None: calls.append(url) or _RENDERED)
    a = _adapter()
    a._fetch_html = lambda url: _CHROME
    items = a.collect()
    assert len(items) == 6 and calls == ["https://www.asic.gov.au/newsroom/media-releases"]


def test_no_firecrawl_credit_when_plain_fetch_already_has_the_list(monkeypatch):
    monkeypatch.setattr(sa.firecrawl_client, "fetch_html", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spent a credit")))
    a = _adapter("ASIC News Centre")
    a._fetch_html = lambda url: _RENDERED
    assert len(a.collect()) == 6


def test_other_sources_never_render_via_firecrawl(monkeypatch):
    monkeypatch.setattr(sa.firecrawl_client, "fetch_html", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spent a credit")))
    a = _adapter("APRA Publications")
    a._fetch_html = lambda url: _CHROME
    assert a.collect() == []  # existing behaviour for other sources; no Firecrawl credit is spent


def test_asic_is_kept_to_the_daily_sweep():
    assert sa._FIRECRAWL_RENDER_SOURCE_NAMES <= scheduler._FIRECRAWL_FETCH_SOURCE_NAMES
    assert sa._FIRECRAWL_RENDER_SOURCE_NAMES == {"ASIC News Centre", "ASIC Enforcement Activity", "Optus National Outage Register",
                                                         "ASIC Consultations"}


_OPTUS = (_REPO / "tests/fixtures/optus_outage_register_rendered_20261124.html").read_text(encoding="utf-8")


def test_optus_outage_register_parses_entries_with_reference_identity():
    a = _adapter("Optus National Outage Register")
    a.source.url = "https://www.optus.com.au/living-network/service-status/national-outage-register"
    a._fetch_html = lambda url: _OPTUS
    items = a.collect()
    assert len(items) == 5
    first = items[0]
    assert first.raw_title == "Optus outage register: Mobile outage - Springlands (4804) area Queensland"
    assert first.canonical_url.endswith("#IM2450998")
    assert "Restored." in first.raw_summary and "Mobile data 339" in first.raw_summary and "Damage by a third party" in first.raw_summary
    assert first.published_at is not None and first.published_at.date().isoformat() in ("2026-11-22", "2026-11-23")
    assert len({i.canonical_url for i in items}) == 5


def test_optus_register_renders_via_firecrawl_when_plain_fetch_has_no_list(monkeypatch):
    monkeypatch.setattr(sa.firecrawl_client, "fetch_html", lambda url, timeout=None: _OPTUS)
    a = _adapter("Optus National Outage Register")
    a._fetch_html = lambda url: "<html><body><h1>Optus National Outage Register</h1></body></html>"
    assert len(a.collect()) == 5


def test_render_source_falls_back_to_firecrawl_when_plain_fetch_fails(monkeypatch):
    # live 2026-11-24: the Optus register's plain fetch timed out on the production host and the source failed without rendering
    calls = []
    monkeypatch.setattr(sa.firecrawl_client, "fetch_html", lambda url, timeout=None: calls.append(url) or _OPTUS)
    a = _adapter("Optus National Outage Register")

    def _boom(url):
        raise RuntimeError("Scrape fetch failed after retry: The read operation timed out")

    a._fetch_html = _boom
    assert len(a.collect()) == 5
    assert len(calls) == 1  # exactly one render credit, not two


def test_other_sources_still_fail_when_plain_fetch_fails(monkeypatch):
    monkeypatch.setattr(sa.firecrawl_client, "fetch_html", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spent a credit")))
    a = _adapter("Weatherzone Warnings")

    def _boom(url):
        raise RuntimeError("timeout")

    a._fetch_html = _boom
    import pytest
    with pytest.raises(RuntimeError):
        a.collect()
