"""NSW Rural Fire Service — Major Incidents feed.

https://www.rfs.nsw.gov.au/feeds/majorIncidents.json — GeoJSON
FeatureCollection, confirmed live 2026-08-26. properties.category is one of
Advice / Watch and Act / Emergency Warning (NSW RFS's own alert-level
vocabulary); properties.description is a "LABEL: value <br />..." block
that also carries fields (STATUS, TYPE, SIZE, COUNCIL AREA) not present as
their own JSON keys, parsed out below rather than dropped.
"""

from __future__ import annotations

import logging
import re

from .base import CanonicalAlert, http_get_json, parse_dmy_datetime

log = logging.getLogger(__name__)

_FEED_URL = "https://www.rfs.nsw.gov.au/feeds/majorIncidents.json"

_SEVERITY_MAP = {
    "advice": "advice",
    "watch and act": "watch_and_act",
    "emergency warning": "emergency_warning",
}

_DESC_FIELD_RE = re.compile(r"([A-Z ]+?):\s*(.*?)(?:<br\s*/?>|$)")


def _parse_description_fields(description: str) -> dict:
    """properties.description packs several fields into one HTML-ish blob
    (e.g. "ALERT LEVEL: Advice <br />LOCATION: ... <br />STATUS: ...") —
    NSW RFS's actual wire format, not something we chose; pull it apart
    rather than showing the raw blob as the alert body."""
    fields = {}
    for label, value in _DESC_FIELD_RE.findall(description or ""):
        fields[label.strip().upper()] = value.strip()
    return fields


def fetch() -> list[CanonicalAlert]:
    data = http_get_json(_FEED_URL)
    out: list[CanonicalAlert] = []
    for feature in data.get("features", []):
        props = feature.get("properties", {}) or {}
        title = props.get("title") or "—"
        guid = props.get("guid")
        category = (props.get("category") or "").strip().lower()
        fields = _parse_description_fields(props.get("description") or "")

        # Captain-directed exclusion 2026-08-26: Hazard Reduction / prescribed
        # burns are planned, not emergencies — drop at the source rather than
        # filtering downstream, using NSW RFS's own TYPE field (confirmed
        # live: "Hazard Reduction" vs "Bush Fire"), not a title-text guess.
        if fields.get("TYPE") == "Hazard Reduction":
            continue

        lat = lon = None
        geom = feature.get("geometry") or {}
        if geom.get("type") == "GeometryCollection":
            for g in geom.get("geometries", []):
                if g.get("type") == "Point":
                    lon, lat = g["coordinates"][0], g["coordinates"][1]
                    break

        out.append(CanonicalAlert(
            source_key="nsw_rfs",
            jurisdiction="NSW",
            headline=title,
            event_key=guid or title,
            alert_type="bushfire",
            severity=_SEVERITY_MAP.get(category, "unknown"),
            description=fields.get("STATUS") and f"{fields.get('TYPE', 'Bush Fire')} — {fields['STATUS']}" or None,
            location=fields.get("LOCATION") or title,
            issued_at=None,  # pubDate is last-update, not first-issued; see updated_at_src
            updated_at_src=parse_dmy_datetime(props.get("pubDate")),
            canonical_url=guid or props.get("link"),
            raw_text=props.get("description"),
            latitude=lat,
            longitude=lon,
        ))
    return out
