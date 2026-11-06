"""VicEmergency — Incidents feed.

https://data.emergency.vic.gov.au/Show?pageId=getIncidentJSON — confirmed
live 2026-08-26 (results[] array). This is a CAD/incidents feed (agency
response status: Responding/Investigating/etc.), NOT VicEmergency's public
warnings feed — there is no severity/warning-level field in the payload
(checked live: incidentNo, incidentType, incidentStatus, incidentSize,
category1/2, agency, territory, lat/lon, timestamps — no warning level).
severity is therefore always 'unknown' for incidents; do not invent one from
incidentSize or incidentStatus, which measure something else.

Warnings come from VicEmergency's public events feed
(https://www.emergency.vic.gov.au/public/events-geojson.json, checked live
2026-11-02): features with feedType == "warning" carry the real tier in
category1 (Advice / Watch and Act / Emergency Warning) and a CAP block with the
event, e.g. Thunderstorm Asthma Advice per weather district. Without them a VIC
Emergency Warning would never be seen as one. Only warnings are taken from that
feed; its incident/planned-burn/earthquake features are not ingested.
"""

from __future__ import annotations

import logging
import re

from .base import CanonicalAlert, http_get_json, parse_dmy_datetime

log = logging.getLogger(__name__)

_FEED_URL = "https://data.emergency.vic.gov.au/Show?pageId=getIncidentJSON"
_WARNINGS_URL = "https://www.emergency.vic.gov.au/public/events-geojson.json"

_TIER_MAP = {
    "emergency warning": "emergency_warning",
    "watch and act": "watch_and_act",
    "watch & act": "watch_and_act",
    "advice": "advice",
}
_TAG_RE = re.compile(r"<[^>]+>")

_TYPE_MAP = {
    "BUSH": "bushfire",
    "GRASS": "bushfire",
    "STRUCTURE": "structure_fire",
    "NON STRUCTURE": "other",
}


# Planned burns are dropped in every other jurisdiction (planned, not
# emergencies); the VIC feed had none live when this was added, so this is a
# guard on the incident type/name rather than a response to a seen record.
_PLANNED_BURN_RE = re.compile(r"planned\s+burn|burn[\s-]?off|hazard\s+reduction|prescribed\s+burn", re.IGNORECASE)


def _is_planned_burn(row: dict) -> bool:
    return bool(_PLANNED_BURN_RE.search(f"{row.get('incidentType') or ''} {row.get('name') or ''}"))


def _is_false_alarm(row: dict) -> bool:
    """incidentType 'FALSE ALARM' sits under category1 'Fire', so it would
    otherwise be kept as a bushfire. Not an emergency; dropped."""
    return "FALSE ALARM" in (row.get("incidentType") or "").upper()


def _alert_type(row: dict) -> str:
    incident_type = (row.get("incidentType") or "").upper()
    for key, mapped in _TYPE_MAP.items():
        if key in incident_type:
            return mapped
    if (row.get("category1") or "").lower() == "fire":
        return "bushfire"
    return "other"


def _warning_alert_type(cap: dict) -> str:
    code = (cap.get("eventCode") or "").lower()
    event = (cap.get("event") or "").lower()
    if code == "thunderstormasthma" or "thunderstorm asthma" in event:
        return "thunderstorm_asthma"
    for needle, mapped in (("fire", "bushfire"), ("flood", "flood"), ("cyclone", "cyclone"), ("storm", "storm"), ("heat", "heatwave"), ("tsunami", "tsunami")):
        if needle in event:
            return mapped
    return "other"


def _first_point(geometry: dict | None) -> tuple[float | None, float | None]:
    if not geometry:
        return None, None
    geoms = geometry.get("geometries") if geometry.get("type") == "GeometryCollection" else [geometry]
    for g in geoms or []:
        if g.get("type") == "Point" and len(g.get("coordinates") or []) >= 2:
            lon, lat = g["coordinates"][:2]
            return lat, lon
    return None, None


def parse_warnings(data: dict) -> list[CanonicalAlert]:
    """Warning features of the VicEmergency events feed -> canonical alerts.
    Tier comes only from the feed's own category1; an unrecognised label stays
    'unknown' rather than being guessed. A warning with no id is skipped."""
    out: list[CanonicalAlert] = []
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        if props.get("feedType") != "warning":
            continue
        warning_id = props.get("id") or props.get("sourceId")
        if not warning_id:
            continue
        cap = props.get("cap") or {}
        if isinstance(cap, str):
            cap = {}
        tier_label = (props.get("category1") or "").strip()
        severity = _TIER_MAP.get(tier_label.lower(), "unknown")
        alert_type = _warning_alert_type(cap)
        event = cap.get("event") or props.get("category2") or "Warning"
        location = props.get("location") or None
        headline = f"{tier_label or 'Warning'}: {event}" + (f" — {location}" if location else "")
        text = re.sub(r"[ \t]+", " ", _TAG_RE.sub("", props.get("text") or "")).strip() or None
        # A district-wide health advice has no meaningful point; leave it off so
        # it cannot be matched to sites by distance from a district centroid.
        lat, lon = (None, None) if alert_type == "thunderstorm_asthma" else _first_point(feature.get("geometry"))
        out.append(CanonicalAlert(
            source_key="vic_emergency",
            jurisdiction="VIC",
            headline=headline,
            event_key=f"warning-{warning_id}",
            alert_type=alert_type,
            severity=severity,
            description=text,
            location=location,
            issued_at=props.get("created"),
            updated_at_src=props.get("updated"),
            canonical_url=f"https://emergency.vic.gov.au/respond/#!/warning/{warning_id}/moreinfo",
            raw_text=text,
            latitude=lat,
            longitude=lon,
        ))
    return out


def fetch() -> list[CanonicalAlert]:
    """Incidents plus warnings. A warnings-feed failure raises (heartbeat fails
    loudly) rather than quietly returning incidents only: that would look like
    'no warnings' when the warnings feed is simply down."""
    return _fetch_incidents() + parse_warnings(http_get_json(_WARNINGS_URL))


def _fetch_incidents() -> list[CanonicalAlert]:
    return parse_incidents(http_get_json(_FEED_URL))


def parse_incidents(data: dict) -> list[CanonicalAlert]:
    """Pure parse of the getIncidentJSON response (results[] array); bushfire
    incidents only. Separate from fetch() so it can be tested offline."""
    out: list[CanonicalAlert] = []
    for row in data.get("results", []):
        if _is_planned_burn(row) or _is_false_alarm(row):
            continue
        alert_type = _alert_type(row)

        # Captain-directed exclusion 2026-08-26 (Other/Non-Structure), widened
        # 2026-08-26 (Structure Fire too) — drop using the same structured
        # incidentType/category1 classification _alert_type already derives,
        # not a separate heuristic. Kept: bushfire only.
        if alert_type in ("other", "structure_fire"):
            continue

        incident_no = row.get("incidentNo")
        headline = row.get("name") or row.get("incidentLocation") or f"Incident {incident_no}"
        location = ", ".join(p for p in (row.get("incidentLocation"), row.get("municipality")) if p)
        out.append(CanonicalAlert(
            source_key="vic_emergency",
            jurisdiction="VIC",
            headline=headline,
            event_key=str(incident_no) if incident_no is not None else headline,
            alert_type=alert_type,
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
