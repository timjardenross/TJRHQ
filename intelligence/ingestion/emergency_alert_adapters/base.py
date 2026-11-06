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
from datetime import datetime

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


class FeedRetiredError(RuntimeError):
    """The feed itself says it is retired (e.g. SA CFS's retirement notice).
    A RuntimeError so existing callers keep working, but a distinct type so
    the per-item guard (see convert_items) never swallows it as a bad row."""


_UNMAPPED_MAX_LABELS = 20


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (label or "").lower()).strip("_")[:40] or "blank"


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

    __slots__ = ("counts", "items_seen")

    def __init__(self) -> None:
        self.items_seen = 0
        self.counts: Counter[str] = Counter()

    def seen(self, n: int = 1) -> None:
        self.items_seen += n

    def exclude(self, reason: str) -> None:
        self.counts[f"excluded_{reason}"] += 1

    def invalid(self, reason: str) -> None:
        self.counts[f"invalid_{reason}"] += 1

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


def parse_dmy_datetime(value: str | None) -> str | None:
    """Several sources (NSW RFS) emit "DD/MM/YYYY H:MM:SS AM/PM" —
    ambiguous to Postgres's timestamptz parser (could read as MM/DD).
    Converts to ISO 8601; returns None (never invents a time) if the
    source's own format doesn't match what its docs describe."""
    if not value:
        return None
    # KNOWN GAP (flagged, not guessed): these DD/MM/YYYY sources (NSW RFS,
    # VIC Emergency) carry no timezone/offset in the string either — same
    # unresolved ambiguity as act_esa.py's ACT format. Presumed local
    # Australian time but unverified per-source; do not silently treat as UTC.
    for fmt in ("%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt).isoformat()  # noqa: DTZ007 - source has no offset info; flagged above, not resolved
        except ValueError:
            continue
    return None
