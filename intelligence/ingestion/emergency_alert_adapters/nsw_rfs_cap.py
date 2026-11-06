"""NSW Rural Fire Service — CAP-AU incident alerts (enrichment of nsw_rfs).

https://www.rfs.nsw.gov.au/feeds/majorIncidentsCAP.xml — an EDXL-DE distribution whose
`contentObject`s each embed one CAP 1.2 (CAP-AU profile) <alert>, confirmed live 2026-11-06.

This is NOT a second source. The same incidents already arrive from the Major Incidents
GeoJSON feed (nsw_rfs.py); a second adapter would store every NSW incident twice. Instead
this module reads the CAP feed and nsw_rfs copies four CAP fields (event, urgency, certainty,
severity) onto the alerts it already produces, joining on the RFS incident id (the trailing
number of the GeoJSON guid == the CAP <incidents> element). The GeoJSON stays the source of
truth for what is an alert, its tier and its dedupe key; CAP only adds fields.

Best effort by design: if the CAP feed is down, malformed or has changed shape, nsw_rfs
logs a warning and the alerts carry no CAP fields. The `cap_urgency` expected-field check in
SOURCE_INFO then raises a FIELD DRIFT warning, so a CAP outage is visible rather than silent.
"""

from __future__ import annotations

import logging
import re

import defusedxml.ElementTree as ET  # nosec B314 - defused parser, safe against XXE/entity-expansion on external feed XML

from .base import CanonicalAlert, http_get

log = logging.getLogger(__name__)

_CAP_URL = "https://www.rfs.nsw.gov.au/feeds/majorIncidentsCAP.xml"
_CAP = "{urn:oasis:names:tc:emergency:cap:1.2}"
_INCIDENT_ID_RE = re.compile(r"(\d+)/?$")


def incident_id(guid: str | None) -> str | None:
    """The RFS incident id: the trailing number of a GeoJSON guid
    (https://incidents.rfs.nsw.gov.au/api/v1/incidents/684405 -> '684405')."""
    match = _INCIDENT_ID_RE.search((guid or "").strip())
    return match.group(1) if match else None


def _text(parent, tag: str) -> str | None:
    node = parent.find(_CAP + tag)
    value = (node.text or "").strip() if node is not None else ""
    return value or None


def parse(data: bytes) -> dict[str, dict[str, str | None]]:
    """CAP feed bytes -> {incident_id: {cap_event, cap_urgency, cap_certainty, cap_severity}}.

    One malformed <alert> (no incident id, no <info>) is skipped; it never fails the others.
    Raises a parse error only if the whole document is not XML."""
    root = ET.fromstring(data)
    out: dict[str, dict[str, str | None]] = {}
    for alert in root.iter(_CAP + "alert"):
        key = _text(alert, "incidents")
        info = alert.find(_CAP + "info")
        if not key or info is None:
            continue
        out[key] = {
            "cap_event": _text(info, "event"),
            "cap_urgency": _text(info, "urgency"),
            "cap_certainty": _text(info, "certainty"),
            "cap_severity": _text(info, "severity"),
        }
    return out


def enrich(alerts: list[CanonicalAlert], cap_data: bytes | None = None) -> int:
    """Copy CAP fields onto matching alerts in place; returns how many were enriched.

    cap_data=None fetches the live feed. Never raises: any failure is logged and 0 is returned,
    leaving the alerts exactly as the GeoJSON produced them."""
    try:
        by_incident = parse(cap_data if cap_data is not None else http_get(_CAP_URL))
    except Exception as exc:  # noqa: BLE001 - CAP is an optional enrichment; a failure must never cost the primary GeoJSON alerts
        log.warning("[nsw_rfs] CAP enrichment unavailable (alerts kept without CAP fields): %s", exc)
        return 0
    enriched = 0
    for alert in alerts:
        fields = by_incident.get(incident_id(alert.canonical_url) or "")
        if not fields:
            continue
        for name, value in fields.items():
            if value:
                setattr(alert, name, value)
        enriched += 1
    if alerts and by_incident and not enriched:
        log.warning("[nsw_rfs] CAP feed had %d alerts but none matched the %d GeoJSON incidents (id format changed?)", len(by_incident), len(alerts))
    return enriched
