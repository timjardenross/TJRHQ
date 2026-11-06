"""WA DFES JSON API enrichment of the wa_dfes RSS alerts.

https://api.emergency.wa.gov.au/v1/warnings and /v1/incidents are the JSON twins of the RSS feeds wa_dfes.py reads,
and each entry's `id` is the RSS item's <guid>, so the join is exact. The RSS carries almost nothing beyond a title,
a time and a point; the JSON adds (measured 2026-11-06):
  warnings   issued-date-time (the real issue time; the RSS only has a last-published time), and the CAP urgency /
             certainty / severity / event, which fills cap_* for WA.
  incidents  issued-date-time, incident-status (Active / Monitoring / On scene) and the street + suburbs.

An enrichment, not a source: the RSS decides which alerts exist (and the existing exclusions and tiers), and the JSON
only fills fields that are still empty. Best effort and never raises: if the API is down or has changed shape, alerts
keep their RSS-only shape and the `issued_at` expected-field check in SOURCE_INFO raises a FIELD DRIFT warning.
"""

from __future__ import annotations

import json
import logging

from .base import CanonicalAlert, http_get

log = logging.getLogger(__name__)

_WARNINGS_JSON_URL = "https://api.emergency.wa.gov.au/v1/warnings"
_INCIDENTS_JSON_URL = "https://api.emergency.wa.gov.au/v1/incidents"


def _head(value: object) -> str | None:
    """"Future - act in near future" -> "Future" (the CAP value, without DFES's gloss)."""
    text = str(value or "").split(" - ")[0].strip()
    return text or None


def _place(item: dict) -> str | None:
    street = ((item.get("location") or {}).get("value") or "").strip()
    suburbs = ", ".join(s for s in (item.get("suburbs") or []) if s)
    return ", ".join(p for p in (street, suburbs) if p) or None


def parse(warnings_raw: bytes | None, incidents_raw: bytes | None) -> dict[str, dict]:
    """JSON bodies -> {id: fields}. A missing or unreadable body contributes nothing; it never raises."""
    out: dict[str, dict] = {}
    for raw, key in ((warnings_raw, "warnings"), (incidents_raw, "incidents")):
        if raw is None:
            continue
        try:
            entries = json.loads(raw)[key]
        except (ValueError, KeyError, TypeError) as exc:
            log.warning("[wa_json] could not read the %s JSON: %s", key, type(exc).__name__)
            continue
        for item in entries if isinstance(entries, list) else []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            fields: dict[str, object] = {"issued_at": item.get("issued-date-time") or item.get("start-date-time") or None}
            if key == "warnings":
                event_types = item.get("cap-event-type") or []
                fields.update({
                    "cap_urgency": _head(item.get("cap-urgency")), "cap_certainty": _head(item.get("cap-certainty")),
                    "cap_severity": _head(item.get("cap-severity")), "cap_event": (event_types[0] if event_types else None),
                })
            else:
                status = (item.get("incident-status") or "").strip()
                place = _place(item)
                fields["description"] = " · ".join(p for p in (status, place) if p) or None
            out[str(item["id"])] = fields
    return out


def enrich(alerts: list[CanonicalAlert], warnings_raw: bytes | None = None, incidents_raw: bytes | None = None, fetch: bool = True) -> int:
    """Fill still-empty fields on matching alerts in place; returns how many were enriched. Never raises.

    With fetch=True (the live path) and no bodies given, both JSON documents are fetched."""
    if not alerts:
        return 0
    try:
        if fetch and warnings_raw is None and incidents_raw is None:
            warnings_raw, incidents_raw = http_get(_WARNINGS_JSON_URL), http_get(_INCIDENTS_JSON_URL)
        by_id = parse(warnings_raw, incidents_raw)
    except Exception as exc:  # noqa: BLE001 - optional enrichment; an outage must never cost the primary RSS alerts
        log.warning("[wa_json] DFES JSON enrichment unavailable (alerts kept RSS-only): %s", exc)
        return 0
    enriched = 0
    for alert in alerts:
        fields = by_id.get(alert.event_key)
        if not fields:
            continue
        for name, value in fields.items():
            if value and getattr(alert, name, None) in (None, ""):
                setattr(alert, name, value)
        enriched += 1
    log.info("[wa_json] %d of %d WA alerts enriched from the DFES JSON", enriched, len(alerts))
    return enriched
