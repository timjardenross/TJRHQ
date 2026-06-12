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

from intelligence.config import HTTP_TIMEOUT_SECONDS, MAX_ITEMS_PER_SOURCE
from intelligence.ingestion.base_adapter import BaseSourceAdapter
from intelligence.models import IntelligenceItem, SourceRecord

log = logging.getLogger(__name__)

_UA = "USS-TJR-Intelligence-Agent/1.0 (+https://github.com/usstjros)"

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

    def collect(self) -> list[IntelligenceItem]:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise RuntimeError("beautifulsoup4 not installed — run: pip install beautifulsoup4")

        html = self._fetch_html(self.source.url)
        soup = BeautifulSoup(html, "html.parser")

        items = self._extract_items(soup)
        if not items:
            # Fallback: grab any links with date-like context
            items = self._extract_fallback(soup)

        return items[:MAX_ITEMS_PER_SOURCE]

    def _fetch_html(self, url: str) -> str:
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
            # Skip nav/footer type links
            if any(skip in title.lower() for skip in ["home", "contact", "about", "privacy", "terms", "login"]):
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
