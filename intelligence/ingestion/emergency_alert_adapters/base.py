"""Shared fetch helper + canonical record shape for emergency alert adapters."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

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
    description: Optional[str] = None
    location: Optional[str] = None
    issued_at: Optional[str] = None
    updated_at_src: Optional[str] = None
    expiry: Optional[str] = None
    canonical_url: Optional[str] = None
    raw_text: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    closed: Optional[bool] = None
    """True when the source itself says this incident is closed/complete
    (e.g. SA CFS's embedded Status: COMPLETE — confirmed live 2026-08-26
    that SA keeps closed incidents in the feed rather than dropping them,
    so the orchestrator's default "gone from the next fetch = expired"
    lifecycle never catches it). None (default) means "no closure signal
    in this source" — the default absence-based lifecycle still applies.
    Never invent this for a source that doesn't actually expose it."""


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
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_get_json(url: str, timeout: int = 20) -> dict:
    return json.loads(http_get(url, timeout=timeout))


def parse_rfc822_datetime(value: Optional[str]) -> Optional[str]:
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


def parse_dmy_datetime(value: Optional[str]) -> Optional[str]:
    """Several sources (NSW RFS) emit "DD/MM/YYYY H:MM:SS AM/PM" —
    ambiguous to Postgres's timestamptz parser (could read as MM/DD).
    Converts to ISO 8601; returns None (never invents a time) if the
    source's own format doesn't match what its docs describe."""
    if not value:
        return None
    for fmt in ("%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt).isoformat()
        except ValueError:
            continue
    return None
