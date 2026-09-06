"""
External domain signals — Health OSINT and Emergency Alert Hub assessed
output, folded into the brief's single synthesis step
(BRIEFS_CANONICAL_UPLIFT.md §4.1).

Reads ONLY already-assessed/curated rows via a plain data-boundary contract
(intelligence_store.load_assessed_health_signals /
load_active_emergency_alerts) — no import of either pipeline's ingestion,
curation, or scraper-adapter code anywhere in this module.

Distinguishes "queried, found nothing" from "could not query" (Section
30): a fetch failure is caught here and returned as an unavailable domain
result, never silently treated the same as a genuinely quiet morning.

Does NOT call an LLM. This module only normalises rows another pipeline
already assessed into one common shape brief_generator.py can fold into
its existing single narrative call and domain_picture.py can bucket
alongside OSINT-derived events — no second interpretive step, no
re-reasoning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from intelligence.persistence import intelligence_store as store

log = logging.getLogger(__name__)

_HEALTH_SEVERITY_RISK = {
    "mild": "GREEN", "moderate": "AMBER", "severe": "RED", "critical": "RED",
}

_EMERGENCY_SEVERITY_RISK = {
    "advice": "GREEN", "watch_and_act": "AMBER", "emergency_warning": "RED",
    # 'unknown' is a genuine severity gap, not a quiet one — default AMBER
    # rather than silently GREEN so it can't be missed, without overclaiming RED.
    "unknown": "AMBER",
}

# Official wording integrity (Section 30: "no hidden replacement of
# official emergency wording") — the human-readable label shown alongside
# our internal RED/AMBER/GREEN mapping, verbatim from the source's own terms.
_EMERGENCY_SEVERITY_LABEL = {
    "advice": "Advice", "watch_and_act": "Watch and Act",
    "emergency_warning": "Emergency Warning", "unknown": "Unknown",
}


@dataclass
class ExternalDomainSignal:
    """One assessed item from a domain outside the OSINT collector, in the
    minimal shape the brief's synthesis step and domain_picture.py need.
    Deliberately not forced through ClassifiedEvent/RankedEvent — wrong
    shape for non-OSINT content (same reasoning daily_digest.py already
    applies to platform core_events)."""
    domain: str                              # "health" | "emergency"
    title: str                                # verbatim from source, never paraphrased
    summary: Optional[str]
    risk_rating: str                          # GREEN | AMBER | RED
    source_name: Optional[str]
    assessed_at: Optional[str]
    canonical_url: Optional[str] = None
    official_severity_label: Optional[str] = None  # emergency alerts only

    def to_dict(self) -> dict:
        return {
            "domain": self.domain, "title": self.title, "summary": self.summary,
            "risk_rating": self.risk_rating, "source_name": self.source_name,
            "assessed_at": self.assessed_at, "canonical_url": self.canonical_url,
            "official_severity_label": self.official_severity_label,
        }


@dataclass
class DomainFetchResult:
    domain: str
    available: bool                # False = the fetch itself failed
    signals: list                  # list[ExternalDomainSignal]
    error: Optional[str] = None


def fetch_health_signals(hours: int = 24, limit: int = 10) -> DomainFetchResult:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        rows = store.load_assessed_health_signals(since, limit=limit)
    except Exception as exc:
        log.warning("Health OSINT assessed-signal fetch failed (non-fatal, domain marked unavailable): %s", exc)
        return DomainFetchResult(domain="health", available=False, signals=[], error=str(exc))

    signals = []
    for r in rows:
        severity = (r.get("severity") or "").strip().lower()
        risk = _HEALTH_SEVERITY_RISK.get(severity)
        if risk is None:
            # No domain-native severity on this row — fall back to
            # confidence_level rather than silently defaulting to GREEN.
            risk = "AMBER" if (r.get("confidence_level") or "").upper() in ("HIGH", "MEDIUM") else "GREEN"
        source_name = (r.get("health_source_registry") or {}).get("source_name")
        signals.append(ExternalDomainSignal(
            domain="health",
            title=r.get("title") or "—",
            summary=r.get("description"),
            risk_rating=risk,
            source_name=source_name,
            assessed_at=r.get("published_at") or r.get("collected_at"),
        ))
    return DomainFetchResult(domain="health", available=True, signals=signals)


def fetch_emergency_alerts(limit: int = 10) -> DomainFetchResult:
    try:
        rows = store.load_active_emergency_alerts(limit=limit)
    except Exception as exc:
        log.warning("Emergency Alert Hub assessed-alert fetch failed (non-fatal, domain marked unavailable): %s", exc)
        return DomainFetchResult(domain="emergency", available=False, signals=[], error=str(exc))

    signals = []
    for r in rows:
        severity = (r.get("severity") or "unknown").strip().lower()
        signals.append(ExternalDomainSignal(
            domain="emergency",
            title=r.get("headline") or "—",
            summary=r.get("location"),
            risk_rating=_EMERGENCY_SEVERITY_RISK.get(severity, "AMBER"),
            source_name=r.get("jurisdiction"),
            assessed_at=r.get("last_seen_at") or r.get("issued_at"),
            canonical_url=r.get("canonical_url"),
            official_severity_label=_EMERGENCY_SEVERITY_LABEL.get(severity, "Unknown"),
        ))
    return DomainFetchResult(domain="emergency", available=True, signals=signals)
