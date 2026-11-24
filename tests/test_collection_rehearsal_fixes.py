"""Fixes found by the 2026-11-24 collection rehearsal (real source responses run through the real adapters).

1. ASIC's newsroom lists a release in several sections; the same release was emitted up to 4 times in one run (4 of 20).
2. OAIC cards and the Optus register carried no provenance, so with INTEL_PROVENANCE_COLUMNS=1 their rows had no basis/precision.
3. NVD publication times were naive datetimes (NVD stamps are UTC with no offset).
Fixture: https://asic.gov.au/about-asic/news-centre/ rendered through Firecrawl on 2026-11-24.
"""
from __future__ import annotations

import sys
from datetime import timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import provenance as prov
from intelligence.ingestion import scrape_adapter as sa
from intelligence.ingestion.api_adapter import APIAdapter
from intelligence.models import SourceRecord

_FX = _REPO / "tests/fixtures"


def _scrape(name, url):
    return sa.ScrapeAdapter(SourceRecord(source_id="id", source_name=name, category="regulatory", priority_rank=1, url=url,
                                         source_type="scrape", jurisdiction="AU", confidence_weight=0.95, active=True))


def test_asic_newsroom_emits_each_release_once():
    a = _scrape("ASIC News Centre", "https://asic.gov.au/about-asic/news-centre/")
    a._fetch_html = lambda url: (_FX / "asic_newsroom_rendered_20261124.html").read_text(encoding="utf-8")
    items = a.collect()
    urls = [i.canonical_url for i in items]
    assert len(items) >= 15 and len(urls) == len(set(urls))
    assert all(i.published_at is not None for i in items)


def test_oaic_cards_carry_day_precision_provenance():
    a = _scrape("OAIC Privacy Determinations & News", "https://www.oaic.gov.au/news/media-centre")
    a._fetch_html = lambda url: (_FX / "oaic_media_centre_rendered_20261124.html").read_text(encoding="utf-8")
    items = a.collect()
    assert len(items) == 10
    for i in items:
        row = prov.provenance_row_fields(i.provenance, columns_exist_override=True)
        assert row["publisher_domain"] == "oaic.gov.au"
        assert (row["published_at_basis"], row["published_at_precision"]) == ("date_only", "day")
        assert row["published_at_confidence"] == "claimed"      # never claims an hour-level or verified time


def test_optus_register_entries_carry_day_precision_provenance():
    a = _scrape("Optus National Outage Register", "https://www.optus.com.au/living-network/service-status/national-outage-register")
    a._fetch_html = lambda url: (_FX / "optus_outage_register_rendered_20261124.html").read_text(encoding="utf-8")
    items = a.collect()
    assert len(items) == 5
    for i in items:
        row = prov.provenance_row_fields(i.provenance, columns_exist_override=True)
        assert (row["published_at_basis"], row["published_at_precision"]) == ("date_only", "day")
        assert row["publisher_domain"] == "optus.com.au"


def test_nvd_publication_times_are_timezone_aware_utc():
    src = SourceRecord(source_id="id", source_name="NVD / NIST CVE Database", category="cybersecurity", priority_rank=1,
                       url="https://nvd.nist.gov/", source_type="api", jurisdiction="US", confidence_weight=0.95, active=True,
                       api_endpoint="https://services.nvd.nist.gov/rest/json/cves/2.0")
    data = {"vulnerabilities": [{"cve": {"id": "CVE-2026-1", "published": "2026-11-24T07:17:19.723",
                                         "descriptions": [{"lang": "en", "value": "x"}]}}]}
    (item,) = APIAdapter(src)._parse_nvd(data)
    assert item.published_at.tzinfo is not None and item.published_at.utcoffset().total_seconds() == 0
    assert item.published_at.astimezone(timezone.utc).isoformat().startswith("2026-11-24T07:17:19")
