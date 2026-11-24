"""Both OAIC sources failed every check (HTTP 403 on the plain fetch) through 2026-11-23.

Diagnosis (2026-11-24): oaic.gov.au blocks the production host's plain fetch; Firecrawl gets 200. The page itself is
server-rendered (not client-rendered): the media centre holds `div.card` results with a redirect-wrapped link and a date.
The old RSS feed (https://www.oaic.gov.au/rss) is title-only (no link, no date), so it cannot carry original dates.
The fixture is the real results block captured from https://www.oaic.gov.au/news/media-centre on 2026-11-24.
"""
from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import scheduler
from intelligence.ingestion import scrape_adapter as sa
from intelligence.models import SourceRecord

_HTML = (_REPO / "tests/fixtures/oaic_media_centre_rendered_20261124.html").read_text(encoding="utf-8")
_URL = "https://www.oaic.gov.au/news/media-centre"
_BREACH, _NEWS = "OAIC Breach Notifications", "OAIC Privacy Determinations & News"


def _adapter(name=_NEWS, url=_URL):
    src = SourceRecord(source_id="id-oaic", source_name=name, category="regulatory", priority_rank=3, url=url,
                       source_type="scrape", jurisdiction="AU", confidence_weight=0.9, active=True)
    return sa.ScrapeAdapter(src)


def test_news_source_returns_all_current_publications_with_original_dates():
    a = _adapter()
    a._fetch_html = lambda url: _HTML
    items = a.collect()
    assert len(items) == 10
    first = items[0]
    assert first.raw_title == "OAIC closes preliminary inquiries into VIQ Solutions"
    assert first.published_at.date().isoformat() in ("2026-11-03", "2026-11-04")  # "4 November 2026", read in AEDT or UTC
    assert first.canonical_url == "https://www.oaic.gov.au/news/media-centre/oaic-closes-preliminary-inquiries-into-viq-solutions"
    dates = sorted({i.published_at.date().isoformat() for i in items}, reverse=True)
    assert dates[0].startswith("2026-11") and dates[-1].startswith("2026-07")  # 29 July 2026 is the oldest on the page
    assert all(i.published_at is not None for i in items)


def test_links_are_the_real_pages_not_the_search_redirect():
    a = _adapter()
    a._fetch_html = lambda url: _HTML
    for i in a.collect():
        assert i.canonical_url.startswith("https://www.oaic.gov.au/news/media-centre/")
        assert "redirect" not in i.canonical_url and "auth=" not in i.canonical_url


def test_breach_source_keeps_only_data_breach_cards():
    a = _adapter(_BREACH)
    a._fetch_html = lambda url: _HTML
    items = a.collect()
    titles = [i.raw_title for i in items]
    assert 2 <= len(items) < 10
    assert "OAIC closes preliminary inquiries into VIQ Solutions" in titles
    assert "Large-scale data breaches on the rise, latest OAIC statistics reveal" in titles
    assert "OAIC annual report shows growing demand as Australians engage privacy and information access rights" not in titles
    assert all("Data breach" in (i.raw_summary or "") for i in items)


def test_403_falls_back_to_firecrawl_for_both_oaic_sources(monkeypatch):
    calls = []
    monkeypatch.setattr(sa.firecrawl_client, "fetch_html", lambda url, timeout=None: calls.append(url) or _HTML)

    def _403(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(sa.ScrapeAdapter, "_do_fetch", staticmethod(_403))
    for name in (_NEWS, _BREACH):
        assert len(_adapter(name).collect()) >= 2
    assert calls == [_URL, _URL]


def test_no_firecrawl_credit_when_plain_fetch_works(monkeypatch):
    monkeypatch.setattr(sa.firecrawl_client, "fetch_html", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spent a credit")))
    monkeypatch.setattr(sa.ScrapeAdapter, "_do_fetch", staticmethod(lambda req, timeout: _HTML))
    assert len(_adapter().collect()) == 10


def test_oaic_is_kept_to_the_daily_sweep():
    assert {_BREACH, _NEWS} <= sa._FIRECRAWL_FALLBACK_SOURCE_NAMES
    assert {_BREACH, _NEWS} <= scheduler._FIRECRAWL_FETCH_SOURCE_NAMES
