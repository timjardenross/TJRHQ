"""ACMA media-releases listing parser (pure function, no network, no database).

Source page: https://www.acma.gov.au/media-releases (Drupal/GovCMS, markup observed 2026-11-24).
Each release is an ``<article class="card">`` holding ``a.card-link`` (absolute URL,
``/articles/YYYY-MM/<slug>``), ``h3.card-title``, ``p.card-body`` and
``<time class="card-date" datetime="YYYY-MM-DD">``.

Collection constraints observed 2026-11-24:
  * No RSS/Atom feed is advertised and no public API exists.
  * Plain fetches from the container's egress are dropped by ACMA's edge (empty reply / HTTP/2
    stream error), so a live run needs the metered Firecrawl fetch path (1 credit per run).
  * Content licence: CC BY 4.0 (https://www.acma.gov.au/copyright-notice); attribute
    "Australian Communications and Media Authority (c) Commonwealth of Australia".
  * Volume: roughly 3-5 releases a month, most unrelated to outages, so ``is_outage_relevant``
    is provided to keep only telco outage / emergency-call items.

This module is deliberately not wired into the collection engine; see the registry row
(``ACMA Media Releases``, active=False) for activation notes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup

LISTING_URL = "https://www.acma.gov.au/media-releases"
ATTRIBUTION = "Australian Communications and Media Authority (c) Commonwealth of Australia, CC BY 4.0"

_OUTAGE_RE = re.compile(
    r"\b(outage|outages|triple zero|emergency calls?|network disruption|service disruption)\b"
    r"|\(000\)|(?<![\d,.])000(?![\d,.])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AcmaRelease:
    title: str
    url: str
    summary: str
    published: date | None


def parse_listing(html: str) -> list[AcmaRelease]:
    """Parse the media-releases listing page into releases, in page order."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[AcmaRelease] = []
    seen: set[str] = set()
    for card in soup.select("article.card"):
        link = card.select_one("a.card-link[href]")
        title_el = card.select_one(".card-title")
        if link is None or title_el is None:
            continue
        url = link["href"].strip()
        title = " ".join(title_el.get_text().split())
        if not url or not title or url in seen:
            continue
        seen.add(url)
        body = card.select_one(".card-body")
        time_el = card.select_one("time[datetime]")
        published = None
        if time_el is not None:
            try:
                published = date.fromisoformat(time_el["datetime"].strip()[:10])
            except ValueError:
                published = None
        out.append(AcmaRelease(
            title=title,
            url=url,
            summary=" ".join(body.get_text().split()) if body else "",
            published=published,
        ))
    return out


def is_outage_relevant(release: AcmaRelease) -> bool:
    """True when the title or summary concerns outages or emergency-call access."""
    return bool(_OUTAGE_RE.search(f"{release.title} {release.summary}"))
