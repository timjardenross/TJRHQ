"""
Scrape adapter — last resort for sources without RSS or API.
Uses httpx + BeautifulSoup4 to extract article lists from HTML pages.

Used for: APRA, ASIC, AusPayNet, NBN, Telstra, Optus, PTV, Transurban,
          Melbourne Airport, APRA Publications.

Strategy: find a list of recent articles/notices on the source page by
looking for common content list patterns. Returns up to MAX_ITEMS_PER_SOURCE
items with whatever title/date/url can be extracted.

This adapter explicitly marks its confidence lower than RSS/API sources.
"""

import logging
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

from intelligence.config import (
    HTTP_TIMEOUT_SECONDS, MAX_ITEMS_PER_SOURCE,
    NO_INCIDENT_SENTINEL_PHRASES, KNOWN_JUNK_TITLE_SUBSTRINGS,
    STATUS_NARRATIVE_KEYWORDS, AUTH_GATED_SENTINEL_PHRASES,
)
from intelligence.ingestion import firecrawl_client
from intelligence.ingestion.base_adapter import BaseSourceAdapter
from intelligence.models import IntelligenceItem, SourceRecord

log = logging.getLogger(__name__)

_UA = "USS-TJR-Intelligence-Agent/1.0 (+https://github.com/usstjros)"

# 2026-08-10 (Firecrawl production provisioning): sources explicitly
# budget-reviewed and approved to fall back to the real (credit-costing)
# Firecrawl fetch path on a plain-fetch 403 — see
# .claude/skills/bot-reviews/fixes-2026-08-09/firecrawl-production-provisioning.md
# for the cost math. Deliberately an ALLOWLIST, not a blanket
# "any scrape source that 403s" rule: ScrapeAdapter serves ~15+ other active
# sources (ACMA, ASIC, APRA, NBN, Telstra, Optus, PTV, Transurban, Melbourne
# Airport, ...) that must never silently start spending the Captain's
# personal Firecrawl account credits just because they have a bad day —
# only sources this mission's monthly-volume math actually covered may use
# the fallback. Add a new name here ONLY after doing that math again.
_FIRECRAWL_FALLBACK_SOURCE_NAMES = frozenset({
    "AEMO Market Notices",
    "Fastly Status",
})

# CSS selectors tried in priority order for finding article/notice lists
_ARTICLE_SELECTORS = [
    "article",
    '[class*="news-item"]', '[class*="article-item"]', '[class*="release-item"]',
    '[class*="media-release"]', '[class*="press-release"]',
    "li.item", "li.entry", "li.post",
    ".listing__item", ".list-item",
    "h2 a", "h3 a",
]


class ScrapeAdapter(BaseSourceAdapter):

    def __init__(self, source: SourceRecord):
        super().__init__(source)
        # Set during collect(); read by _validate_content() (USS-TJR-MSN-0339 WP1).
        self._sentinel_matched = False
        self._used_narrative = False
        self._used_fallback = False

    def collect(self) -> list[IntelligenceItem]:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise RuntimeError("beautifulsoup4 not installed — run: pip install beautifulsoup4")

        html = self._fetch_html(self.source.url)
        soup = BeautifulSoup(html, "html.parser")

        page_text = soup.get_text(" ", strip=True).lower()

        # 0. Auth/address-gated pages have no anonymous public content at all
        #    (e.g. Telstra's outages page — MSN-0338 §4/§8). Fail loudly and
        #    visibly rather than silently degrading or fabricating content.
        if any(phrase in page_text for phrase in AUTH_GATED_SENTINEL_PHRASES):
            raise RuntimeError(
                "Source requires authentication/address lookup — no public "
                "anonymous content available (USS-TJR-MSN-0339 WP1)."
            )

        # 1. "All clear" sentinel — a real, confirmed-empty status, not a failure.
        if any(phrase in page_text for phrase in NO_INCIDENT_SENTINEL_PHRASES):
            self._sentinel_matched = True
            return []

        # 2. Structured list extraction (news/release-style pages).
        items = self._extract_items(soup)
        if items:
            return items[:MAX_ITEMS_PER_SOURCE]

        # 3. Status-narrative extraction (single-status pages: a heading + a
        #    paragraph describing current state, not a list of articles).
        items = self._extract_status_narrative(soup)
        if items:
            self._used_narrative = True
            return items[:MAX_ITEMS_PER_SOURCE]

        # 4. Last resort: grab any links with date-like context.
        items = self._extract_fallback(soup)
        if items:
            self._used_fallback = True
        return items[:MAX_ITEMS_PER_SOURCE]

    def _validate_content(self, items: list[IntelligenceItem]) -> tuple[bool, Optional[str]]:
        if self._used_narrative:
            return True, "Extracted from status-page narrative text (keyword-gated)."
        if self._used_fallback:
            return False, (
                "No structured content found — fell back to generic link extraction. "
                "Low confidence; likely site furniture rather than real notices."
            )
        return True, "Structured extraction via CSS selectors."

    def _fetch_html(self, url: str) -> str:
        """Plain fetch first (free). On HTTP 403, falls back to the shared
        Firecrawl fetch path (real API credit cost) ONLY for sources on the
        explicit _FIRECRAWL_FALLBACK_SOURCE_NAMES allowlist above — every
        other ScrapeAdapter-driven source still fails loud on a 403, exactly
        as before this change, so this never silently changes behaviour or
        cost for the ~15+ other sources this adapter class already serves."""
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                charset = "utf-8"
                content_type = resp.headers.get("Content-Type", "")
                if "charset=" in content_type:
                    charset = content_type.split("charset=")[-1].split(";")[0].strip()
                return resp.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 403 and self.source.source_name in _FIRECRAWL_FALLBACK_SOURCE_NAMES:
                log.info("[%s] plain fetch 403'd — falling back to Firecrawl", self.source.source_name)
                return firecrawl_client.fetch_html(url)
            raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
        except Exception as exc:
            raise RuntimeError(f"Scrape fetch failed: {exc}") from exc

    def _extract_items(self, soup) -> list[IntelligenceItem]:
        from bs4 import BeautifulSoup
        items = []
        base = self.source.url

        for selector in _ARTICLE_SELECTORS:
            elements = soup.select(selector)
            if len(elements) < 2:
                continue

            for el in elements:
                title_el = el.find(["h1", "h2", "h3", "h4", "strong"]) or el.find("a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 10 or len(title) > 300:
                    continue

                link_el = el.find("a", href=True)
                url = urljoin(base, link_el["href"]) if link_el else None

                # Try to find a date near the element
                published = self._extract_date(el)

                summary_el = el.find("p")
                summary = summary_el.get_text(strip=True)[:500] if summary_el else None

                items.append(self._make_item(title, summary, url, published))
                if len(items) >= MAX_ITEMS_PER_SOURCE:
                    break

            if items:
                return items

        return items

    def _extract_status_narrative(self, soup) -> list[IntelligenceItem]:
        """For single-status pages (a heading + a paragraph describing current
        state, not a list of articles) — treat the main heading/paragraph as
        one real item, but only if it actually reads as a status statement
        (USS-TJR-MSN-0339 WP1). Rejects generic marketing/informational copy
        that happens to share the page with a status section."""
        heading_el = soup.find(["h1", "h2"])
        if not heading_el:
            return []
        heading = heading_el.get_text(strip=True)

        para_el = heading_el.find_next("p")
        body = para_el.get_text(strip=True) if para_el else ""

        combined = f"{heading} {body}".lower()
        if not any(kw in combined for kw in STATUS_NARRATIVE_KEYWORDS):
            return []
        if len(heading) < 10:
            return []

        return [self._make_item(heading, body[:500] or None, self.source.url, None)]

    def _extract_fallback(self, soup) -> list[IntelligenceItem]:
        """Grab all <a> tags that look like article links."""
        items = []
        base = self.source.url
        seen_titles: set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            title = a.get_text(strip=True)
            if not title or len(title) < 15 or len(title) > 250:
                continue
            if title in seen_titles:
                continue
            title_lower = title.lower()
            # Skip nav/footer type links
            if any(skip in title_lower for skip in ["home", "contact", "about", "privacy", "terms", "login"]):
                continue
            # Skip known generic site furniture/marketing copy (USS-TJR-MSN-0339 WP1 —
            # MSN-0338 §4 found these exact titles returned on every run since seeding).
            if any(junk in title_lower for junk in KNOWN_JUNK_TITLE_SUBSTRINGS):
                continue
            seen_titles.add(title)
            url = urljoin(base, href)
            items.append(self._make_item(title, None, url, None))
            if len(items) >= MAX_ITEMS_PER_SOURCE:
                break
        return items

    def _extract_date(self, el) -> Optional[datetime]:
        """Try to find a date string near/inside the element."""
        text = el.get_text()
        # Common date patterns
        patterns = [
            r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})\b",
            r"\b(\d{4}-\d{2}-\d{2})\b",
            r"\b(\d{1,2}/\d{1,2}/\d{4})\b",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                try:
                    from dateutil import parser as dateparser
                    dt = dateparser.parse(m.group(1))
                    return dt.replace(tzinfo=timezone.utc) if dt else None
                except Exception:
                    pass

        # Try <time> element
        time_el = el.find("time")
        if time_el:
            dt_str = time_el.get("datetime") or time_el.get_text(strip=True)
            try:
                from dateutil import parser as dateparser
                dt = dateparser.parse(dt_str)
                return dt.replace(tzinfo=timezone.utc) if dt else None
            except Exception:
                pass
        return None
