"""Timestamp / source PROVENANCE carried on each collected item (USS-TJR provenance v1).

Every field is optional and nullable. Code that does not find them behaves exactly as before, so this module can be merged and
deployed BEFORE the database migration (tools/intelligence/provenance_migration_20261124.sql): persistence only includes the
new keys in a row when PROVENANCE_COLUMNS_EXIST says the columns exist (env INTEL_PROVENANCE_COLUMNS, default OFF).

A publisher DOMAIN is recorded for display and diagnosis only. It is never proof of independence: independence stays family /
aggregator based (weekly_evidence.publisher_family / source_kind).
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

BASES = ("feed", "feed_corrected_utc", "aggregator_claimed", "date_only", "collected_fallback", "unknown")
PRECISIONS = ("second", "minute", "day", "unknown")
CONFIDENCES = ("verified", "claimed", "feed", "unknown")
# What KIND of date published_at holds. 'catalogue_addition' (CISA KEV dateAdded) dates the catalogue ENTRY, not the vulnerability's
# disclosure: it says nothing about how long ago the CVE was disclosed. 'event' is never a publication time.
LABELS = ("publication", "catalogue_addition", "event")

COLUMNS = ("publisher_domain", "publisher_family", "published_at_basis", "published_at_precision", "published_at_confidence", "published_at_label",
           "event_window_start", "event_window_end")

# Default OFF: nothing is written to (or read from) the new columns until the migration has been applied and this is switched on.
PROVENANCE_COLUMNS_EXIST = False


def columns_exist() -> bool:
    env = os.environ.get("INTEL_PROVENANCE_COLUMNS")
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes", "on")
    return PROVENANCE_COLUMNS_EXIST


def _iso(v) -> str | None:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def build_provenance(*, basis: str = "unknown", precision: str = "unknown", confidence: str = "unknown", publisher_domain: str | None = None,
                     publisher_family: str | None = None, event_window_start=None, event_window_end=None,
                     label: str | None = None) -> dict:
    """A provenance dict with every key present. Unknown enum values degrade to 'unknown' rather than raising."""
    return {
        "publisher_domain": publisher_domain.lower() if publisher_domain else None,
        "publisher_family": publisher_family or None,
        "published_at_basis": basis if basis in BASES else "unknown",
        "published_at_precision": precision if precision in PRECISIONS else "unknown",
        "published_at_confidence": confidence if confidence in CONFIDENCES else "unknown",
        "published_at_label": label if label in LABELS else None,
        "event_window_start": event_window_start, "event_window_end": event_window_end,
    }


def provenance_row_fields(prov: dict | None, *, columns_exist_override: bool | None = None) -> dict:
    """Keys to merge into a persisted row. EMPTY unless the columns are known to exist, and empty when the item carries none."""
    on = columns_exist() if columns_exist_override is None else columns_exist_override
    if not on or not prov:
        return {}
    return {k: (_iso(prov.get(k)) if k.startswith("event_window") else prov.get(k)) for k in COLUMNS}


VERIFICATION_KEY = "publisher_verification"   # key inside score_provenance (jsonb) and inside an event's provenance dict


def merge_verification_record(row: dict, prov: dict | None, *, columns_exist_override: bool | None = None) -> dict:
    """Add the original-publisher verification record (intelligence/ingestion/publisher_verification.py) to row["score_provenance"], keeping
    whatever scoring provenance is already there. No-op unless the provenance columns are known to exist and the event carries a record,
    so a row without a record is byte-identical to today's. Returns the row."""
    on = columns_exist() if columns_exist_override is None else columns_exist_override
    rec = (prov or {}).get(VERIFICATION_KEY)
    if on and rec:
        row["score_provenance"] = {**(row.get("score_provenance") or {}), VERIFICATION_KEY: rec}
    return row


def select_columns() -> str:
    """Extra PostgREST select fragment for readers (leading comma); empty while the columns are not known to exist."""
    return ("," + ",".join(COLUMNS)) if columns_exist() else ""


def event_provenance_fields(row: dict) -> dict:
    """Provenance keys of a stored row, only those present (so an event dict without them is identical to today's)."""
    return {k: row[k] for k in COLUMNS if row.get(k) is not None}


# ── per-source classifiers ────────────────────────────────────────────────────────────────────────────────────
def domain_of(url: str | None) -> str | None:
    host = (urlparse(url).hostname or "") if url else ""
    host = host.lower().removeprefix("www.")
    return host or None


def google_news_source(entry) -> tuple[str | None, str | None]:
    """(publisher_domain, publisher_name) from a Google News item's <source url="https://publisher.example">Name</source> element.
    feedparser exposes it as entry['source'] = {'href': ..., 'title': ...}. (None, None) when absent."""
    src = entry.get("source") if hasattr(entry, "get") else None
    if not src:
        return None, None
    try:
        href, title = src.get("href"), src.get("title")
    except AttributeError:
        return None, None
    return domain_of(href), (title or "").strip() or None


def is_google_news(url: str | None) -> bool:
    return (domain_of(url) or "") == "news.google.com"


def rss_provenance(*, published, feed_url: str | None, entry, scheduled_start=None, scheduled_end=None) -> dict:
    """Google News pubDate is the aggregator's claim, not the publisher's time. Every other RSS/Atom date is the feed's own."""
    link = entry.get("link") if hasattr(entry, "get") else None
    if is_google_news(feed_url) or is_google_news(link):
        dom, name = google_news_source(entry)
        return build_provenance(basis="aggregator_claimed" if published else "unknown", precision="second" if published else "unknown",
                                confidence="claimed" if published else "unknown", publisher_domain=dom, publisher_family=name,
                                event_window_start=scheduled_start, event_window_end=scheduled_end)
    return build_provenance(basis="feed" if published else "unknown", precision="second" if published else "unknown",
                            confidence="feed" if published else "unknown", publisher_domain=domain_of(feed_url),
                            event_window_start=scheduled_start, event_window_end=scheduled_end)


def api_provenance(*, published, endpoint: str | None, date_only: bool = False, explicit_publication_date: bool = False,
                   label: str | None = None) -> dict:
    """Confidence and precision are separate. A date-only value that the source explicitly states and that dates the REPORT (CISA KEV
    ``dateAdded``, label 'catalogue_addition': the date the entry was added to the catalogue, NOT the CVE's disclosure date) is VERIFIED at
    DAY precision; any other date-only value stays CLAIMED. Date-only never establishes an hour-level time."""
    if not published:
        return build_provenance(publisher_domain=domain_of(endpoint))
    if date_only:
        return build_provenance(basis="date_only", precision="day", confidence="verified" if explicit_publication_date else "claimed",
                                publisher_domain=domain_of(endpoint), label=label)
    return build_provenance(basis="feed", precision="second", confidence="feed", publisher_domain=domain_of(endpoint))


_DATE_IN_TEXT = re.compile(r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|(?<![\d/])\d{1,2}/\d{1,2}/\d{4}", re.IGNORECASE)


def date_in_title(title: str | None) -> bool:
    """The title itself states a date: ambiguous, it may be the EVENT's date ('Planned outage on 28 November 2026')."""
    return bool(_DATE_IN_TEXT.search(title or ""))


def scrape_provenance(*, published, page_url: str | None, date_only: bool, basis_tz: str | None = None,
                      explicit_header: bool = False, title: str | None = None) -> dict:
    """A scraped date. Only an EXPLICIT publication header from a primary source (``explicit_header``: AEMO's notice header, read in its own
    timezone) is trusted. A date found in other text is ambiguous: it is CLAIMED, and when the title itself states a date it is treated as
    a possible EVENT date, never a publication date (basis/confidence unknown, kept as event_window_start). With a time of day the instant is
    converted to UTC ('feed_corrected_utc'); with only a date it is 'date_only' at DAY precision: explicit header -> verified, else claimed."""
    dom = domain_of(page_url)
    if not published:
        return build_provenance(publisher_domain=dom)
    if not explicit_header and date_in_title(title):
        return build_provenance(basis="unknown", precision="day", confidence="unknown", publisher_domain=dom, event_window_start=published, label="event")
    if date_only:
        return build_provenance(basis="date_only", precision="day", confidence="verified" if explicit_header else "claimed", publisher_domain=dom,
                                label="publication" if explicit_header else None)
    if not explicit_header:
        return build_provenance(basis="feed", precision="minute", confidence="claimed", publisher_domain=dom)
    return build_provenance(basis="feed_corrected_utc" if basis_tz else "feed", precision="minute", confidence="feed", publisher_domain=dom)


# ── scheduled-window text (Twilio / Statuspage maintenance) ────────────────────────────────────────────────────
_WIN_ISO = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})\s*(?:UTC|Z)?\s*(?:-|–|to|until|and)\s*(?:(\d{4}-\d{2}-\d{2})[ T])?(\d{2}):(\d{2})\s*(?:UTC|Z)", re.IGNORECASE)


def parse_event_window(text: str | None) -> tuple[datetime | None, datetime | None]:
    """A stated scheduled window ('2026-11-28 02:00 - 04:00 UTC', '... 22:00 UTC to 2026-11-29 01:00 UTC') as (start, end) in UTC.
    This is when the EVENT happens, never when the item was published. (None, None) when no unambiguous UTC window is stated."""
    m = _WIN_ISO.search(text or "")
    if not m:
        return None, None
    d1, h1, mi1, d2, h2, mi2 = m.groups()
    try:
        start = datetime.fromisoformat(f"{d1}T{h1}:{mi1}:00").replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(f"{d2 or d1}T{h2}:{mi2}:00").replace(tzinfo=timezone.utc)
    except ValueError:
        return None, None
    if end < start and not d2:
        end += timedelta(days=1)
    return (start, end) if end >= start else (None, None)
