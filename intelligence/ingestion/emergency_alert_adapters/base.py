"""Shared fetch helper + canonical record shape for emergency alert adapters."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

log = logging.getLogger(__name__)

_USER_AGENT = "USS-TJR-EmergencyAlertHub/1.0 (Starship Endeavour platform)"


@dataclass
class CanonicalAlert:
    """One normalized alert record — maps 1:1 onto the `alerts` table
    (migration 0174). `event_key` must be stable across refetches of the
    same underlying incident (source-provided ID where available, else a
    hash of jurisdiction+headline+location) so the orchestrator's dedupe
    (source_key, event_key) works; `canonical_url` is preferred when the
    source gives one, since it dedupes across the whole table, not just
    within one source."""

    source_key: str
    jurisdiction: str
    headline: str
    event_key: str
    alert_type: str = "other"
    severity: str = "unknown"
    description: str | None = None
    location: str | None = None
    issued_at: str | None = None
    updated_at_src: str | None = None
    expiry: str | None = None
    canonical_url: str | None = None
    raw_text: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    closed: bool | None = None
    """True when the source itself says this incident is closed/complete
    (e.g. SA CFS's embedded Status: COMPLETE — confirmed live 2026-08-26
    that SA keeps closed incidents in the feed rather than dropping them,
    so the orchestrator's default "gone from the next fetch = expired"
    lifecycle never catches it). None (default) means "no closure signal
    in this source" — the default absence-based lifecycle still applies.
    Never invent this for a source that doesn't actually expose it."""
    cap_urgency: str | None = None
    cap_certainty: str | None = None
    cap_severity: str | None = None
    cap_event: str | None = None
    """CAP (Common Alerting Protocol) fields, kept verbatim ONLY for sources
    that actually carry them: SA CFS (CAP-AU <info>) and VIC Emergency
    warnings (embedded `cap` object). None everywhere else - never inferred
    from another field. They are alerts-table columns since migration 0250
    (applied 2026-11-06) and are stored by default; the orchestrator strips
    them from the upsert only if EMERGENCY_ALERTS_CAP_FIELDS is set to
    0/false/off/no (for a database without the columns)."""


class FeedRetiredError(RuntimeError):
    """The feed itself says it is retired (e.g. SA CFS's retirement notice).
    A RuntimeError so existing callers keep working, but a distinct type so
    the per-item guard (see convert_items) never swallows it as a bad row."""


class FeedShapeError(RuntimeError):
    """The response parsed, but lacks the container the feed is documented to
    have (e.g. no `features` list, no RSS <channel>). That is a broken feed or a
    changed schema, NOT an empty one, so on the ledger path it fails the
    source loudly (heartbeat 'failed', nothing expired) instead of reading as
    "no alerts". Only raised when a ledger is passed; plain parse()/fetch()
    keep their historical lenient behaviour."""


def json_items(data, key: str, source: str, guard: bool) -> list:
    """data[key] as a list. Lenient (historical `data.get(key, [])`) unless guard,
    where a missing/non-list container raises FeedShapeError."""
    if guard and not (isinstance(data, dict) and isinstance(data.get(key), list)):
        raise FeedShapeError(f"{source}: response has no '{key}' list - unexpected feed shape, not an empty feed")
    return data.get(key, [])


def require_rss_channel(root, source: str, guard: bool) -> None:
    """RSS: a legitimately empty feed still has <channel>; no <channel> is a broken feed."""
    if guard and root.find("channel") is None:
        raise FeedShapeError(f"{source}: RSS response has no <channel> - unexpected feed shape, not an empty feed")


_UNMAPPED_MAX_LABELS = 20


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (label or "").lower()).strip("_")[:40] or "blank"


_SAMPLES_PER_REASON = 3
_SAMPLE_MAX_CHARS = 80


def _as_aware_utc(value: str | datetime | None) -> datetime | None:
    """Best-effort timestamp -> aware datetime. ISO 8601 or RFC 822 strings. A value
    with no offset is read as UTC: that can only make an item look NEWER than it is
    (by up to the local offset), so staleness is under-reported, never over-reported."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = parsedate_to_datetime(text)
            except (TypeError, ValueError):
                return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class DropLedger:
    """Every item an adapter looked at and did not turn into an alert, counted
    by reason, so "no alerts" can be told apart from "broken".

    Two namespaces, deliberately never mixed:
      excluded_<reason>  deliberate, Captain-directed filters (hazard reduction
                         burns, Information tier, ambulance calls, ...). A feed
                         where everything is excluded is legitimately quiet.
      invalid_<reason>   structural failures (missing id/headline/content, an
                         item that could not be parsed at all). A feed where
                         items are seen but ALL were invalid is broken.
    Plus items_seen (raw items before any skip) and unmapped_<label>: kept
    alerts whose tier label the adapter did not recognise (severity 'unknown').

    Invariant for adapters: items_seen == accepted + excluded_total +
    invalid_total (tests assert it on every fixture).
    """

    __slots__ = ("counts", "items_seen", "newest_item_at", "samples")

    def __init__(self) -> None:
        self.items_seen = 0
        self.counts: Counter[str] = Counter()
        # Newest source-side timestamp across EVERY item looked at (before any
        # exclusion), so a feed that churns but is all-excluded still counts as fresh.
        self.newest_item_at: datetime | None = None
        # A few example headlines per ledger key, so a reviewer can see WHAT is
        # being dropped, not just how many. Public feed titles only.
        self.samples: dict[str, list[str]] = {}

    def seen(self, n: int = 1) -> None:
        self.items_seen += n

    def observe(self, when: str | datetime | None) -> None:
        """Record an item's own last-updated time (ISO / RFC 822 string or datetime)."""
        dt = _as_aware_utc(when)
        if dt is not None and (self.newest_item_at is None or dt > self.newest_item_at):
            self.newest_item_at = dt

    def _sample(self, key: str, text: str | None) -> None:
        if not text:
            return
        bucket = self.samples.setdefault(key, [])
        snippet = " ".join(str(text).split())[:_SAMPLE_MAX_CHARS]
        if len(bucket) < _SAMPLES_PER_REASON and snippet not in bucket:
            bucket.append(snippet)

    def exclude(self, reason: str, sample: str | None = None) -> None:
        self.counts[f"excluded_{reason}"] += 1
        self._sample(f"excluded_{reason}", sample)

    def invalid(self, reason: str, sample: str | None = None) -> None:
        self.counts[f"invalid_{reason}"] += 1
        self._sample(f"invalid_{reason}", sample)

    def unmapped(self, label: str) -> None:
        """An unrecognised tier label mapped to 'unknown'. Distinct labels are
        capped so a free-text field cannot grow the ledger without bound."""
        key = f"unmapped_{_slug(label)}"
        if key not in self.counts and sum(1 for k in self.counts if k.startswith("unmapped_")) >= _UNMAPPED_MAX_LABELS:
            key = "unmapped_other"
        self.counts[key] += 1

    def _total(self, prefix: str) -> int:
        return sum(n for k, n in self.counts.items() if k.startswith(prefix))

    @property
    def excluded_total(self) -> int:
        return self._total("excluded_")

    @property
    def invalid_total(self) -> int:
        return self._total("invalid_")

    def breakdown(self, prefix: str) -> list[tuple[str, int]]:
        """(reason-without-prefix, count), biggest first, ties by name."""
        items = [(k[len(prefix):], n) for k, n in self.counts.items() if k.startswith(prefix)]
        return sorted(items, key=lambda kv: (-kv[1], kv[0]))

    def top_invalid(self, n: int = 3) -> str:
        return ", ".join(f"{r} {c}" for r, c in self.breakdown("invalid_")[:n])

    def top_unmapped(self, n: int = 3) -> list[tuple[str, int]]:
        return self.breakdown("unmapped_")[:n]

    def summary(self) -> str:
        """Compact one-line form for the heartbeat detail, e.g.
        "seen 30, excluded 17 (hazard_reduction 15, not_applicable 2), invalid 1 (missing_id 1)"."""
        parts = [f"seen {self.items_seen}"]
        for label, prefix, total in (("excluded", "excluded_", self.excluded_total), ("invalid", "invalid_", self.invalid_total)):
            if total:
                parts.append(f"{label} {total} ({', '.join(f'{r} {c}' for r, c in self.breakdown(prefix))})")
        unmapped = self.top_unmapped()
        if unmapped:
            parts.append("unmapped " + ", ".join(f"{r} {c}" for r, c in unmapped))
        return ", ".join(parts)

    def as_dict(self) -> dict:
        return {"items_seen": self.items_seen, **dict(sorted(self.counts.items()))}


def convert_items(items: Iterable, convert: Callable, ledger: DropLedger, guard: bool) -> list[CanonicalAlert]:
    """Run convert(item) over every raw item. convert returns a CanonicalAlert,
    or None after recording why it skipped the item on the ledger.

    guard=False (the plain fetch()/parse() path) lets an exception propagate,
    exactly as before. guard=True (the ledger path used by the orchestrator)
    turns an exception on ONE item into invalid_unparseable_item so a single
    bad row cannot black out the whole source. FeedRetiredError always
    propagates. Only the exception type is logged, never item content."""
    out: list[CanonicalAlert] = []
    for item in items:
        ledger.seen()
        if guard:
            try:
                alert = convert(item)
            except FeedRetiredError:
                raise
            except Exception as exc:  # noqa: BLE001 - per-item isolation is the point: one malformed row must not fail the source; counted as invalid_unparseable_item
                log.warning("[emergency-alert-adapters] unparseable item skipped (%s)", type(exc).__name__)
                ledger.invalid("unparseable_item")
                continue
        else:
            alert = convert(item)
        if alert is not None:
            out.append(alert)
    return out


def stable_event_key(*parts: str) -> str:
    """Deterministic fallback event key for sources with no native incident
    ID — never invented per-item, always derived from the item's own
    content so the same real-world incident hashes the same way twice."""
    joined = "|".join(p.strip().lower() for p in parts if p)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]


def http_get(url: str, timeout: int = 20) -> bytes:
    """Plain fetch — every confirmed-live source in migration 0174 (NSW,
    VIC, QLD, SA, ACT) is a plain public JSON/XML endpoint with no
    JS-challenge, verified live 2026-08-26. Do not route these through
    Firecrawl — that budget (external_fetch_budget.py, 1,000 scrapes/month
    shared platform-wide) is reserved for sources that actually need it."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - generic fetch helper; callers pass this adapter module's own fixed emergency-feed URL constant, not user input - reviewed 2026-09-12
        return resp.read()


def http_get_json(url: str, timeout: int = 20) -> dict:
    return json.loads(http_get(url, timeout=timeout))


def parse_rfc822_datetime(value: str | None) -> str | None:
    """RSS pubDate is RFC 822/2822 ("Wed, 26 Aug 2026 17:23:55 +0800") —
    not reliably parsed by a bare Postgres timestamptz cast, so convert to
    ISO 8601 here rather than pass the raw string through."""
    if not value:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return None


def _localize(naive: datetime, tz_name: str | None) -> str:
    """ISO string for `naive`, with the named IANA zone's offset for that date (DST
    handled by the zone database, never guessed). No zone, or no zone data on this
    host, keeps the historical offset-less string."""
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            return naive.replace(tzinfo=ZoneInfo(tz_name)).isoformat()
        except Exception as exc:  # noqa: BLE001 - missing tzdata must not break ingestion; falls back to the old offset-less string
            log.warning("[emergency-alert-adapters] timezone %s unavailable (%s): leaving timestamps offset-less", tz_name, type(exc).__name__)
    return naive.isoformat()


def parse_dmy_datetime(value: str | None, tz: str | None = None) -> str | None:
    """Several sources (NSW RFS) emit "DD/MM/YYYY H:MM:SS AM/PM" —
    ambiguous to Postgres's timestamptz parser (could read as MM/DD).
    Converts to ISO 8601; returns None (never invents a time) if the
    source's own format doesn't match what its docs describe."""
    if not value:
        return None
    # These DD/MM/YYYY strings carry no offset, so the caller must say which zone the
    # SOURCE writes them in. MEASURED against stored rows 2026-11-06: VIC Emergency
    # incidents are local Melbourne time (stored as UTC they landed ~11 h in the
    # future), so VIC passes tz="Australia/Melbourne". NSW RFS pubDate behaves as UTC
    # (nothing in the future, freshest row ~0.1 h old), so NSW passes no tz and keeps
    # the offset-less string, which Postgres reads as UTC.
    for fmt in ("%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S"):
        try:
            return _localize(datetime.strptime(value.strip(), fmt), tz)  # noqa: DTZ007 - localised just above when the caller names the source zone
        except ValueError:
            continue
    return None
