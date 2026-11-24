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
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urljoin, urlparse

from intelligence.config import (
    AUTH_GATED_SENTINEL_PHRASES,
    HTTP_TIMEOUT_SECONDS,
    KNOWN_JUNK_TITLE_SUBSTRINGS,
    MAX_ITEMS_PER_SOURCE,
    NO_INCIDENT_SENTINEL_PHRASES,
    STATUS_NARRATIVE_KEYWORDS,
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
    # 2026-11-24: oaic.gov.au answers the production host's plain fetch with HTTP 403 on every check (both OAIC sources,
    # every run since at least 2026-11-21). Firecrawl reaches it (200, server-rendered list). Fires only on a 403, so it
    # stops costing credits if OAIC unblocks the host. Daily sweep only (scheduler._FIRECRAWL_FETCH_SOURCE_NAMES): 2 credits/day.
    "OAIC Breach Notifications",
    "OAIC Privacy Determinations & News",
})

# OAIC media centre (https://www.oaic.gov.au/news/media-centre): a server-rendered list of `div.card` results, each with an
# `a.card-title` (a site-search redirect wrapping the real URL), `p.card-text`, topic tags and `p.date`. Value = topic tag a
# source keeps (lower-case), or None for all cards.
_OAIC_CARD_SOURCE_NAMES = {
    "OAIC Breach Notifications": "data breach",
    "OAIC Privacy Determinations & News": None,
}

# 2026-11-24: sources whose release list is rendered client-side. A plain fetch returns the page chrome without the list
# (ASIC's newsroom: 14 KB of navigation, zero releases), which is why ASIC News Centre and ASIC Enforcement Activity returned
# "no items" on every check from early September. For these names ONLY, when the plain fetch yields no items the adapter
# renders the page through Firecrawl (one credit per source per run; both are also kept to the once-daily sweep in
# scheduler._FIRECRAWL_FETCH_SOURCE_NAMES, so the cost is 2 credits/day).
_FIRECRAWL_RENDER_SOURCE_NAMES = frozenset({
    "ASIC News Centre",
    "ASIC Enforcement Activity",
    "Optus National Outage Register",
})

# Statutory outage registers (carriers publish every Major / Significant Local Outage after it is rectified). Each entry is a
# block of label:value fields, parsed by _parse_outage_register. Retrospective by design: a confirmation and restoration record,
# not a first-alert source.
_OUTAGE_REGISTER_SOURCE_NAMES = frozenset({"Optus National Outage Register"})
_AEDT = timezone(timedelta(hours=11))

# Dates the adapter reads from a page. Slash dates are day-first (Australian sources); see _extract_date.
_NAMED_MONTH_DATE_RE = re.compile(r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})\b", re.IGNORECASE)
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_SLASH_DATE_RE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?)?")
# Timezone a source publishes its dates in when the page states none (default UTC). AEMO uses NEM time: AEST, fixed UTC+10, no daylight saving.
_SOURCE_UTC_OFFSET = {
    "AEMO Market Notices": timezone(timedelta(hours=10)),
}

# CSS selectors tried in priority order for finding article/notice lists
_ARTICLE_SELECTORS = [
    "article",
    '[class*="news-item"]', '[class*="article-item"]', '[class*="release-item"]',
    '[class*="media-release"]', '[class*="press-release"]',
    "li.item", "li.entry", "li.post",
    ".listing__item", ".list-item",
    # AEMO Market Notices renders each real notice as `div.items > div.item`
    # (a heading + body, no wrapping <a> — confirmed live 2026-08-10, see
    # firecrawl-production-provisioning.md). Scoped to `.items .item`
    # (requires the nested-wrapper pattern too), not bare `.item`, to avoid
    # matching unrelated single-class="item" elements on other sites.
    ".items .item",
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
        # keep the free plain fetch when it already carries the list; render only when it does not
        _plain = BeautifulSoup(html, "html.parser")
        _has_list = (bool(_plain.select('[data-testid^="outage-result-"]')) if self.source.source_name in _OUTAGE_REGISTER_SOURCE_NAMES
                     else bool(self._extract_items(_plain)))
        if self.source.source_name in _FIRECRAWL_RENDER_SOURCE_NAMES and not _has_list:
            log.info("[%s] plain fetch has no release list (client-rendered) — rendering via Firecrawl", self.source.source_name)
            html = firecrawl_client.fetch_html(self.source.url)
        soup = BeautifulSoup(html, "html.parser")

        if self.source.source_name in _OUTAGE_REGISTER_SOURCE_NAMES:
            return self._parse_outage_register(soup)[:MAX_ITEMS_PER_SOURCE]

        if self.source.source_name in _OAIC_CARD_SOURCE_NAMES:
            cards = self._parse_oaic_cards(soup)
            if cards:
                return cards[:MAX_ITEMS_PER_SOURCE]

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

    def _validate_content(self, items: list[IntelligenceItem]) -> tuple[bool, str | None]:
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
        cost for the ~15+ other sources this adapter class already serves.

        On a read timeout (distinct from a 403 — the connection succeeds but
        the server is just slow), retries once with a doubled timeout before
        failing. ASD Publications (asd.gov.au) has timed out on every single
        check for 5+ consecutive days at the default HTTP_TIMEOUT_SECONDS
        (15s) — a slow government server, not a page-shape or auth problem —
        so a bare retry at a longer timeout is the safe fix; no fallback
        fetch path or Firecrawl spend involved."""
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            return self._do_fetch(req, HTTP_TIMEOUT_SECONDS)
        except urllib.error.HTTPError as exc:
            if exc.code == 403 and self.source.source_name in _FIRECRAWL_FALLBACK_SOURCE_NAMES:
                log.info("[%s] plain fetch 403'd — falling back to Firecrawl", self.source.source_name)
                return firecrawl_client.fetch_html(url)
            raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
        except TimeoutError:
            retry_timeout = HTTP_TIMEOUT_SECONDS * 2
            log.info(
                "[%s] plain fetch timed out after %ds — retrying once at %ds",
                self.source.source_name, HTTP_TIMEOUT_SECONDS, retry_timeout,
            )
            try:
                return self._do_fetch(req, retry_timeout)
            except Exception as exc2:
                raise RuntimeError(f"Scrape fetch failed after retry: {exc2}") from exc2
        except Exception as exc:
            raise RuntimeError(f"Scrape fetch failed: {exc}") from exc

    @staticmethod
    def _do_fetch(req: urllib.request.Request, timeout: int) -> str:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - generic fetch helper; only caller is _fetch_html(self.source.url), sourced from the curated intelligence_sources registry, not user input - reviewed 2026-09-12
            charset = "utf-8"
            content_type = resp.headers.get("Content-Type", "")
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip()
            return resp.read().decode(charset, errors="replace")

    def _parse_outage_register(self, soup) -> list[IntelligenceItem]:
        """One item per register entry. The entry reference is the identity (canonical_url '<page>#<ref>'), so a re-read never duplicates.

        published_at is the register's own 'Date and time entry first published' (day precision); the outage's start and end times are
        kept in the summary as event times and never used as the publication date."""
        items: list[IntelligenceItem] = []
        for block in soup.select('[data-testid^="outage-result-"]'):
            fields: dict[str, str] = {}
            for node in block.find_all(["h3", "p"]):
                label = node.find("span", class_=lambda c: c and "result-label" in c)
                value = node.find("span", class_=lambda c: c and "result-value" in c)
                if label and value:
                    fields[label.get_text(strip=True).rstrip(":").strip().lower()] = value.get_text(" ", strip=True)
            ref = fields.get("reference")
            title = fields.get("outage title")
            if not ref or not title:
                continue
            services = fields.get("number of each type of services affected", "")
            cause = fields.get("cause (high level)", "unknown")
            start = f"{fields.get('start date of outage', '?')} {fields.get('start time of outage', '')}".strip()
            end = f"{fields.get('end date of outage', '?')} {fields.get('end time of outage', '')}".strip()
            summary = (
                f"Restored. {fields.get('outage type', 'Outage')}. Start {start}; end {end}; duration {fields.get('duration of outage', '?').strip()} h. "
                f"Services affected: {fields.get('types of services affected', 'unknown')} ({services or 'count not stated'}). "
                f"Locations: {fields.get('affected suburbs/towns', 'n/a')} ({fields.get('affected states/territories', 'n/a')}). "
                f"Cause (as stated by the carrier): {cause}. Register reference {ref}."
            )
            published = None
            m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", fields.get("date and time entry first published", ""))
            if m:
                published = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=_AEDT).astimezone(timezone.utc)
            item = self._make_item(f"Optus outage register: {title}", summary, f"{self.source.url}#{ref}", published)
            items.append(item)
        return items

    def _parse_oaic_cards(self, soup) -> list[IntelligenceItem]:
        """One item per OAIC media-centre card, with the card's own date. The card link is a site-search redirect
        (`/s/redirect?...&url=<real url>&auth=...`); the real page URL is the identity, so the per-request `auth`/`rank` never leak in."""
        wanted_tag = _OAIC_CARD_SOURCE_NAMES.get(self.source.source_name)
        items: list[IntelligenceItem] = []
        for card in soup.select("div.card"):
            link = card.select_one("a.card-title")
            if not link:
                continue
            title = link.get_text(" ", strip=True)
            if len(title) < 10:
                continue
            tags = [t.get_text(strip=True) for t in card.select(".tags .tag")]
            if wanted_tag and wanted_tag not in {t.lower() for t in tags}:
                continue
            href = link.get("href") or ""
            real = parse_qs(urlparse(href).query).get("url", [None])[0]
            url = urljoin(self.source.url, real or href) if (real or href) else None
            date_el = card.select_one("p.date")
            published = self._extract_date(date_el) if date_el else None
            text_el = card.select_one("p.card-text")
            summary = text_el.get_text(" ", strip=True)[:500] if text_el else None
            if tags:
                summary = f"[{', '.join(tags)}] {summary or ''}".strip()
            items.append(self._make_item(title, summary, url, published))
        return items

    def _extract_items(self, soup) -> list[IntelligenceItem]:
        items = []
        base = self.source.url

        for selector in _ARTICLE_SELECTORS:
            elements = soup.select(selector)
            if len(elements) < 2:
                continue

            for el in elements:
                if el.name == "a" and self.source.source_name in _FIRECRAWL_RENDER_SOURCE_NAMES:
                    # "h2 a"/"h3 a" select the link itself: its own text is the title, and the date/summary live in the
                    # enclosing list item. (el.find("a") on an <a> finds nothing, so every such item used to be skipped.)
                    # Scoped to the repaired sources: other scrape sources that reach this selector today are served by the
                    # narrative/fallback paths, and changing their output is a separate, evidenced decision.
                    title_el = el
                    link_el = el if el.get("href") else None
                    container = el.find_parent(["li", "article", "div"]) or el
                else:
                    title_el = el.find(["h1", "h2", "h3", "h4", "strong"]) or el.find("a")
                    link_el = el.find("a", href=True)
                    container = el
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 10 or len(title) > 300:
                    continue

                url = urljoin(base, link_el["href"]) if link_el else None

                # Try to find a date near the element
                published = self._extract_date(container)

                summary_el = container.find("p")
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

    def _in_nav_chrome(self, el) -> bool:
        """True if `el` sits inside standard page chrome (a header/nav/
        footer menu) rather than the real content area. 2026-08-10 (Firecrawl
        production provisioning): AEMO Market Notices' and Fastly Status'
        Firecrawl-rendered pages both lead with a big site-nav mega-menu
        (AEMO: a real <header> ancestor; Fastly: div.navbar5/
        div.header-content, no semantic <header> tag but the same real
        pattern) — dozens of nav links ahead of the actual notices/incidents
        in DOM order were filling up MAX_ITEMS_PER_SOURCE before the real
        content was ever reached (confirmed live — see
        .claude/skills/bot-reviews/fixes-2026-08-09/
        firecrawl-production-provisioning.md). Generic HTML5-tag + common
        class-name check, not source-specific — this can only REMOVE
        already-low-confidence fallback candidates, so it's a pure
        improvement for every other ScrapeAdapter-driven source too, not
        just these two."""
        for ancestor in el.parents:
            if getattr(ancestor, "name", None) in ("header", "nav", "footer"):
                return True
            classes = " ".join(ancestor.get("class") or []).lower()
            if any(tok in classes for tok in
                   ("navbar", "nav-menu", "mega-menu", "site-header", "header-content", "global-header",
                    "footer", "footbar",
                    # AEMO Market Notices' own faceted-search sidebar (category/date
                    # filter links) sits outside any <header>/nav-classed container
                    # but is the same "chrome, not content" shape — confirmed live
                    # 2026-08-10, see firecrawl-production-provisioning.md.
                    "facet")):
                return True
        return False

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
            if self._in_nav_chrome(a):
                continue
            # A bare URL is never a real headline — some link text is
            # literally the href itself (confirmed live on Fastly Status'
            # incidents page, 2026-08-10).
            if title.startswith(("http://", "https://")):
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

    @staticmethod
    def _parse_with_dateutil(text: str) -> datetime | None:
        try:
            from dateutil import parser as dateparser
            dt = dateparser.parse(text)
            return dt.replace(tzinfo=timezone.utc) if dt else None
        except Exception as exc:  # noqa: BLE001 - best-effort date probe; a non-matching pattern just tries the next one
            log.debug("[scrape_adapter] date parse failed for %r: %s", text, exc)
            return None

    def _parse_slash_date(self, m: re.Match) -> datetime | None:
        """dd/mm/yyyy[ hh:mm[:ss][ AM|PM]] -> aware UTC, read in the source's own timezone. None when it is not a real date."""
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hour = int(m.group(4)) if m.group(4) else 0
        minute = int(m.group(5)) if m.group(5) else 0
        second = int(m.group(6)) if m.group(6) else 0
        meridiem = (m.group(7) or "").lower()
        if meridiem:
            if not 1 <= hour <= 12:
                return None
            hour = hour % 12 + (12 if meridiem == "pm" else 0)
        try:
            local = datetime(year, month, day, hour, minute, second, tzinfo=_SOURCE_UTC_OFFSET.get(self.source.source_name, timezone.utc))
        except ValueError:
            return None
        return local.astimezone(timezone.utc)

    def _extract_date(self, el) -> datetime | None:
        """Find the item's own date near the top of the element, as an aware UTC datetime.

        Slash dates are DAY-first (these are Australian sources: '12/09/2026' is 12 September). dateutil's default is month-first, which
        turned 12 Sep into 9 Dec and put AEMO notices months in the future. They keep their time-of-day and are read in the source's own
        timezone (AEMO publishes in NEM time, a fixed UTC+10). The EARLIEST date in the element wins (the header line, not a date mentioned
        later in the title or body), and a date more than a day ahead of now is an event date, not a publication date, so it is dropped."""
        text = el.get_text(" ", strip=True) if hasattr(el, "get_text") else str(el)
        found: list[tuple[int, datetime]] = []
        m = _NAMED_MONTH_DATE_RE.search(text)
        if m:
            dt = self._parse_with_dateutil(m.group(1))
            if dt:
                found.append((m.start(), dt))
        m = _ISO_DATE_RE.search(text)
        if m:
            dt = self._parse_with_dateutil(m.group(1))        # never dayfirst: dateutil would read 2026-11-12 as 2026-12-11
            if dt:
                found.append((m.start(), dt))
        for m in _SLASH_DATE_RE.finditer(text):
            dt = self._parse_slash_date(m)
            if dt:
                found.append((m.start(), dt))
                break                                           # the first valid slash date is the header; later ones are event dates
        if found:
            dt = min(found, key=lambda f: f[0])[1]
            if dt > datetime.now(timezone.utc) + timedelta(days=1):
                log.debug("[scrape_adapter] ignoring a date more than a day in the future (an event date, not a publication date): %s", dt)
            else:
                return dt

        # Try <time> element
        time_el = el.find("time")
        if time_el:
            dt_str = time_el.get("datetime") or time_el.get_text(strip=True)
            try:
                from dateutil import parser as dateparser
                dt = dateparser.parse(dt_str)
                return dt.replace(tzinfo=timezone.utc) if dt else None
            except Exception as exc:  # noqa: BLE001 - best-effort <time> element parse; falls through to None (caller treats as "no date found")
                log.debug("[scrape_adapter] <time> element date parse failed: %s", exc)
        return None
