"""Original-publisher and original-date verification for aggregator (Google News) items.

Default OFF and NOT WIRED into ingestion, scoring or any brief (flag: INTEL_ORIGINAL_PUBLISHER_VERIFY=1).
Pure functions plus one bounded, injected-fetcher step. This module never performs network I/O itself.

Rules (owner direction):
  * An aggregator date is a CLAIM. Collection time is never used as, or substituted for, publication time.
  * A publisher name/domain is informative only. It is never proof of independence from the aggregator copy.
  * Verification is attempted only for HIGH-materiality, recent, Australian items, under a hard call budget.

See docs/ORIGINAL-PUBLISHER-VERIFICATION.md for measured results and limits.
"""
from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from intelligence import weekly_evidence as we

FLAG = "INTEL_ORIGINAL_PUBLISHER_VERIFY"
HIGH_MATERIALITY = 0.5            # same "high" cut as weekly_evidence (materiality_level)
RECENT_DAYS = 7
DEFAULT_MAX_FETCHES = 5            # hard per-run budget for the verification step
SAME_STORY_MIN_TITLE_LEN = 25      # exact-title reconciliation ignores very short, generic titles

VERIFIED_DATE = "verified_date"
PUBLISHER_KNOWN_DATE_UNVERIFIED = "publisher_known_date_unverified"
UNRESOLVED = "unresolved"
OUTCOMES = (VERIFIED_DATE, PUBLISHER_KNOWN_DATE_UNVERIFIED, UNRESOLVED)


def enabled() -> bool:
    return os.getenv(FLAG, "0") == "1"


# ── (a) publisher resolution from the title suffix ───────────────────────────

_SUFFIX = re.compile(r"\s[-–]\s([^-–]{2,40})$")


def is_aggregator(source_name: str) -> bool:
    return we.source_kind(source_name) == we.AGGREGATOR


def strip_publisher_suffix(title: str) -> str:
    return _SUFFIX.sub("", title or "").strip()


@dataclass(frozen=True)
class PublisherResolution:
    family: str                    # canonical family from weekly_evidence, or "aggregator" when no suffix
    suffix_text: str | None        # the raw trailing ' - Publisher' text, as supplied
    known: bool                    # a suffix was present and parsed
    kind: str                      # weekly_evidence source_kind of the resolved publisher name
    basis: str                     # "title_suffix" | "none"
    independence: str              # always "unproven": a name or domain is not evidence of independence
    clean_title: str


def resolve_publisher(source_name: str, title: str) -> PublisherResolution:
    """Reuses weekly_evidence.publisher_family; for non-aggregators it is the feed's own publisher."""
    clean = strip_publisher_suffix(title) if is_aggregator(source_name) else (title or "")
    fam = we.publisher_family(source_name, title)
    if not is_aggregator(source_name):
        return PublisherResolution(fam, None, True, we.source_kind(source_name), "feed_name", "unproven", clean)
    m = _SUFFIX.search(title or "")
    if not m:
        return PublisherResolution("aggregator", None, False, we.AGGREGATOR, "none", "unproven", clean)
    return PublisherResolution(fam, m.group(1).strip(), True, we.source_kind(fam), "title_suffix", "unproven", clean)


# ── (b) date-claim labelling ─────────────────────────────────────────────────

@dataclass(frozen=True)
class DateClaim:
    value: datetime | None
    basis: str          # aggregator_claimed | feed | unknown
    confidence: str     # claimed | feed | unknown  (vocabulary shared with intelligence/provenance v1)
    label: str          # human-readable caveat for display


def label_date(source_name: str, published_at, collected_at=None) -> DateClaim:
    """Label what a stored published_at actually is. collected_at is accepted only so callers can pass the
    whole row; it is NEVER returned as a publication time."""
    pub = we._parse_ts(published_at)
    if pub is None:
        return DateClaim(None, "unknown", "unknown", "no publication date supplied")
    if is_aggregator(source_name):
        return DateClaim(pub, "aggregator_claimed", "claimed",
                         "date claimed by the aggregator; original publication time not verified")
    return DateClaim(pub, "feed", "feed", "date supplied by the publisher's own feed")


# ── title-match date reconciliation (free, no fetching) ──────────────────────

def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", strip_publisher_suffix(title).lower()).strip()


@dataclass(frozen=True)
class Reconciliation:
    matched: bool
    earliest_direct_at: datetime | None = None
    direct_source: str | None = None
    delta_hours: float | None = None      # aggregator claim minus earliest direct date; positive = aggregator later
    direct_count: int = 0
    note: str = ""


def reconcile_with_direct_feeds(item: dict, direct_items: Iterable[dict]) -> Reconciliation:
    """item: {title, published_at, source}. direct_items: non-aggregator rows {title, published_at, source}.
    Evidence only: the earliest same-title DIRECT FEED date is itself a feed-supplied date, not a verified one."""
    key = _norm(item.get("title", ""))
    if len(key) < SAME_STORY_MIN_TITLE_LEN:
        return Reconciliation(False, note="title too short for an exact same-story match")
    best: tuple[datetime, str] | None = None
    n = 0
    for d in direct_items:
        if is_aggregator(d.get("source", "")) or _norm(d.get("title", "")) != key:
            continue
        ts = we._parse_ts(d.get("published_at"))
        if ts is None:
            continue
        n += 1
        if best is None or ts < best[0]:
            best = (ts, d.get("source", ""))
    if best is None:
        return Reconciliation(False, note="no direct-feed copy with a parseable date")
    claim = we._parse_ts(item.get("published_at"))
    delta = None if claim is None else round((claim - best[0]).total_seconds() / 3600, 2)
    return Reconciliation(True, best[0], best[1], delta, n, "earliest same-title direct-feed date (feed-supplied, not verified)")


# ── (c) bounded verification for HIGH-materiality recent AU incidents ────────

def eligible(item: dict, *, now: datetime | None = None) -> bool:
    """HIGH materiality, Australian, recent. 'Recent' uses collected_at OR the claimed date, so an old story
    that is claimed fresh is still checked; it does not rely on the claim being right."""
    now = now or datetime.now(timezone.utc)
    if not is_aggregator(item.get("source", "")):
        return False
    title, summary = strip_publisher_suffix(item.get("title", "")), item.get("summary", "")
    if we.materiality(title, summary, item.get("geography")) < HIGH_MATERIALITY:
        return False
    text = f"{title} {summary}".lower()
    if (item.get("geography") or "").upper() != "AU" and not any(we._wb(t, text) for t in we._AU_TERMS):
        return False
    cutoff = now - timedelta(days=RECENT_DAYS)
    for k in ("collected_at", "published_at"):
        ts = we._parse_ts(item.get(k))
        if ts is not None and ts >= cutoff:
            return True
    return False


@dataclass(frozen=True)
class Verification:
    outcome: str
    publisher_url: str | None = None
    publisher_host: str | None = None
    published_at: datetime | None = None
    delta_hours: float | None = None      # aggregator claim minus the publisher's own date
    reason: str = ""


_PUB_KEYS = ("article:published_time", "publishedTime", "og:article:published_time", "datePublished", "date")
_GOOGLE_HOSTS = ("google.com", "gstatic.com", "googleusercontent.com")


def _first(meta: dict, key: str):
    v = meta.get(key)
    return v[0] if isinstance(v, list) and v else v


_HAS_TIME_RX = re.compile(r"\d{1,2}:\d{2}")
_HAS_ZONE_RX = re.compile(r"(?:Z|UTC|GMT|[+-]\d{2}(?::?\d{2})?)\s*$", re.IGNORECASE)


def _is_full_timestamp(raw) -> bool:
    """A publisher's own published-time is only evidence of WHEN if it names a time of day AND a timezone. A bare date ('2026-11-21')
    parses to midnight UTC and a zone-less time is read as UTC: either would turn a guess into a 'verified' instant."""
    text = str(raw).strip()
    return bool(_HAS_TIME_RX.search(text) and _HAS_ZONE_RX.search(text))


def classify_fetch(item: dict, fetched: dict | None, *, now: datetime | None = None) -> Verification:
    """fetched: {"url": final URL, "metadata": {...page metadata...}} or None.
    verified_date needs a resolved NON-Google publisher URL and the page's own published-time metadata that parses,
    names a time of day and a timezone (a bare date is not enough) and is not in the future. A modified-time alone is not a publication date."""
    now = now or datetime.now(timezone.utc)
    if not fetched or not fetched.get("url"):
        res = resolve_publisher(item.get("source", ""), item.get("title", ""))
        return Verification(PUBLISHER_KNOWN_DATE_UNVERIFIED if res.known and res.basis == "title_suffix" else UNRESOLVED,
                            reason="article URL not resolved")
    host = (urlparse(fetched["url"]).hostname or "").lower()
    if not host or any(host == h or host.endswith("." + h) for h in _GOOGLE_HOSTS):
        return Verification(UNRESOLVED, reason="still on the aggregator after fetch")
    meta = fetched.get("metadata") or {}
    raws = [v for k in _PUB_KEYS if (v := _first(meta, k))]
    raw = next((v for v in raws if _is_full_timestamp(v) and we._parse_ts(v) is not None), None)
    ts = we._parse_ts(raw) if raw else None
    if ts is None:
        return Verification(PUBLISHER_KNOWN_DATE_UNVERIFIED, fetched["url"], host,
                            reason=("publisher page carries no parseable timestamp with a time of day and a timezone (date-only or zone-less)" if raws
                                    else "publisher page resolved but carries no published-time metadata"))
    if ts > now + timedelta(hours=1):
        return Verification(PUBLISHER_KNOWN_DATE_UNVERIFIED, fetched["url"], host, reason="published-time is in the future")
    claim = we._parse_ts(item.get("published_at"))
    delta = None if claim is None else round((claim - ts).total_seconds() / 3600, 2)
    return Verification(VERIFIED_DATE, fetched["url"], host, ts, delta, "publisher's own published-time metadata")


def verify_batch(items: Iterable[dict], fetcher: Callable[[str], dict | None], *, max_fetches: int = DEFAULT_MAX_FETCHES,
                 now: datetime | None = None) -> dict[str, Verification]:
    """Verify at most max_fetches ELIGIBLE items (caller orders by priority). `fetcher(url)` is injected; any
    exception or None counts as unresolved. Items beyond the budget are simply not attempted (absent from result).
    Returns {item["id"]: Verification}. Does nothing unless the flag is on."""
    out: dict[str, Verification] = {}
    if not enabled() or max_fetches <= 0:
        return out
    used = 0
    for it in items:
        if used >= max_fetches:
            break
        if not eligible(it, now=now) or not it.get("url"):
            continue
        used += 1
        try:
            fetched = fetcher(it["url"])
        except Exception:                      # noqa: BLE001 - a failed fetch is an outcome, not an error
            fetched = None
        out[str(it.get("id"))] = classify_fetch(it, fetched, now=now)
    return out
