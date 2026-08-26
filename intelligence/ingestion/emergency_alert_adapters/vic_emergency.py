"""VicEmergency — Incidents feed.

https://data.emergency.vic.gov.au/Show?pageId=getIncidentJSON — confirmed
live 2026-08-26 (results[] array). This is a CAD/incidents feed (agency
response status: Responding/Investigating/etc.), NOT VicEmergency's public
warnings feed — there is no severity/warning-level field in the payload
(checked live: incidentNo, incidentType, incidentStatus, incidentSize,
category1/2, agency, territory, lat/lon, timestamps — no warning level).
severity is therefore always 'unknown' here; do not invent one from
incidentSize or incidentStatus, which measure something else.
"""

from __future__ import annotations

import logging

from .base import CanonicalAlert, http_get_json, parse_dmy_datetime

log = logging.getLogger(__name__)

_FEED_URL = "https://data.emergency.vic.gov.au/Show?pageId=getIncidentJSON"

_TYPE_MAP = {
    "BUSH": "bushfire",
    "GRASS": "bushfire",
    "STRUCTURE": "structure_fire",
    "NON STRUCTURE": "other",
}


def _alert_type(row: dict) -> str:
    incident_type = (row.get("incidentType") or "").upper()
    for key, mapped in _TYPE_MAP.items():
        if key in incident_type:
            return mapped
    if (row.get("category1") or "").lower() == "fire":
        return "bushfire"
    return "other"


def fetch() -> list[CanonicalAlert]:
    data = http_get_json(_FEED_URL)
    out: list[CanonicalAlert] = []
    for row in data.get("results", []):
        incident_no = row.get("incidentNo")
        headline = row.get("name") or row.get("incidentLocation") or f"Incident {incident_no}"
        location = ", ".join(p for p in (row.get("incidentLocation"), row.get("municipality")) if p)
        out.append(CanonicalAlert(
            source_key="vic_emergency",
            jurisdiction="VIC",
            headline=headline,
            event_key=str(incident_no) if incident_no is not None else headline,
            alert_type=_alert_type(row),
            severity="unknown",
            description=f"{row.get('incidentStatus', '?')} · {row.get('agency', '?')} · size {row.get('incidentSizeFmt', '?')}",
            location=location or None,
            issued_at=parse_dmy_datetime(row.get("originDateTime")),
            updated_at_src=parse_dmy_datetime(row.get("lastUpdateDateTime")),
            canonical_url=f"https://emergency.vic.gov.au/respond/#!/warning/{incident_no}/moreinfo" if incident_no else None,
            raw_text=None,
            latitude=row.get("latitude"),
            longitude=row.get("longitude"),
        ))
    return out
