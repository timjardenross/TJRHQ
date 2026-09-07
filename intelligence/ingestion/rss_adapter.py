"""
RSS/Atom adapter — uses feedparser.
Handles both RSS 2.0 and Atom 1.0.
Used for: AWS, GCP, Azure, BOM, ABC, Reuters, Bloomberg, BBC, AFR, RBA, etc.

Feed URL resolution order:
  1. source.rss_url          (preferred — explicit RSS/Atom endpoint)
  2. source.api_endpoint     (fallback — some sources store feed URL here)
  3. source.url              (last resort — home page, feedparser may still find a feed)
"""

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

from intelligence.config import HTTP_TIMEOUT_SECONDS, MAX_ITEMS_PER_SOURCE
from intelligence.ingestion.base_adapter import BaseSourceAdapter
from intelligence.models import IntelligenceItem, SourceRecord

log = logging.getLogger(__name__)


def _strip_fragment(url: str) -> str:
    """Remove URL fragment (#...) — HTTP clients ignore it and feedparser may choke."""
    return url.split("#")[0] if url else url


class RSSAdapter(BaseSourceAdapter):

    def __init__(self, source: SourceRecord):
        super().__init__(source)
        raw = source.rss_url or source.api_endpoint or source.url
        self._feed_url = _strip_fragment(raw) if raw else raw

    def collect(self) -> list[IntelligenceItem]:
        try:
            import feedparser
        except ImportError:
            raise RuntimeError("feedparser not installed — run: pip install feedparser")

        # feedparser < 6.x does not support timeout kwarg; use socket-level timeout
        import socket
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(HTTP_TIMEOUT_SECONDS)
        try:
            feed = feedparser.parse(
                self._feed_url,
                request_headers={"User-Agent": "USS-TJR-Intelligence-Agent/1.0"},
            )
        finally:
            socket.setdefaulttimeout(old_timeout)

        if feed.get("bozo") and not feed.entries:
            exc = feed.get("bozo_exception")
            raise RuntimeError(f"Feed parse error: {exc}")

        items = []
        for entry in feed.entries[:MAX_ITEMS_PER_SOURCE]:
            title = entry.get("title", "").strip()
            if not title:
                continue

            summary = self._get_summary(entry)
            # 2026-07-18: confirmed live against OAIC's real feed — some feeds
            # (e.g. oaic.gov.au/rss) only populate <title> per item, with no
            # <link>/<guid>/<description> anywhere in the item. raw_summary
            # genuinely has nothing to recover from in that case, but the
            # <channel>-level link (feed.feed.link) is a real destination —
            # falls back through it, then the source registry's own URL,
            # rather than leaving canonical_url null when a link does exist
            # one level up.
            url = entry.get("link") or entry.get("id") or feed.feed.get("link") or self.source.url
            published = self._parse_date(entry)

            # 2026-09-04: CISA's combined "all.xml" advisory feed (used by
            # the "CISA Alerts" source) mixes general cybersecurity
            # advisories with ICS-specific vendor bulletins
            # (cisa.gov/news-events/ics-advisories/*) — bare industrial
            # product names ("Rockwell Automation ArmorStart LT", "IXON VPN
            # Client") with no context. This platform has no ICS/OT
            # footprint anywhere (confirmed §2.2, LifeOS Wall Tablet scope
            # doc), so every one of these was noise, not signal — and the
            # classifier's geography substring-matching bug (see
            # classifier.py's _GEOGRAPHY_AU list matching "wa" inside
            # "Water", "sa" inside boilerplate, etc.) was additionally
            # mistagging them geography=AU and inflating
            # operational_relevance to the 1.00 cap, which is what pushed
            # them to Telegram as if they were real Captain-relevant
            # alerts. Filtered generically by URL path, not scoped to one
            # source_id, since any RSS feed surfacing this same CISA path
            # is equally irrelevant here.
            if url and "/ics-advisories/" in url.lower():
                continue

            items.append(self._make_item(
                raw_title=title,
                raw_summary=summary,
                canonical_url=url,
                published_at=published,
            ))

        return items

    def _get_summary(self, entry) -> Optional[str]:
        for field in ("summary", "description", "content"):
            val = entry.get(field)
            if val:
                if isinstance(val, list):
                    val = val[0].get("value", "") if val else ""
                # Strip basic HTML tags
                import re
                val = re.sub(r"<[^>]+>", " ", str(val))
                val = " ".join(val.split())
                return val[:1000] if val else None
        return None

    def _parse_date(self, entry) -> Optional[datetime]:
        for field in ("published_parsed", "updated_parsed"):
            val = entry.get(field)
            if val:
                try:
                    import time as _time
                    ts = _time.mktime(val)
                    return datetime.fromtimestamp(ts, tz=timezone.utc)
                except Exception:
                    pass
        # Fallback: try string fields
        for field in ("published", "updated"):
            val = entry.get(field)
            if val:
                try:
                    return parsedate_to_datetime(val)
                except Exception:
                    pass
        return None
