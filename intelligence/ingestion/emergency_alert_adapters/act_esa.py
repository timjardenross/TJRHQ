"""ACT Emergency Services Agency — Current Incidents (GeoRSS) feed.

https://esa.act.gov.au/feeds/currentincidents.xml — confirmed live
2026-08-26 (RSS 2.0 + georss:point). Per ESA's own page: "This feed does
not include warning and alert information" — it's CAD incident data
(structure fires, hazard-reduction burns, etc.), same category of caveat
as vic_emergency.py. No severity field in the payload; always 'unknown'.
guid is a real per-incident number (e.g. "013105-14082026"), used as both
event_key and the dedupe key.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

from .base import CanonicalAlert, parse_dmy_datetime, http_get

log = logging.getLogger(__name__)

_FEED_URL = "https://esa.act.gov.au/feeds/currentincidents.xml"
_GEORSS_NS = "{http://www.georss.org/georss}"


def _act_datetime(value: str | None) -> str | None:
    """ACT's own format: "19 Aug 2026 23:24:36.053" — not covered by
    parse_dmy_datetime's DD/MM/YYYY forms, handled separately."""
    if not value:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(value.split(".")[0], "%d %b %Y %H:%M:%S").isoformat()
    except ValueError:
        return None


def fetch() -> list[CanonicalAlert]:
    raw = http_get(_FEED_URL)
    root = ET.fromstring(raw)
    out: list[CanonicalAlert] = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        guid_el = item.find("guid")
        type_el = item.find("type")
        desc_el = item.find("description")
        point_el = item.find(f"{_GEORSS_NS}point")

        title = title_el.text.strip() if title_el is not None and title_el.text else "—"
        guid = guid_el.text.strip() if guid_el is not None and guid_el.text else title
        incident_type = type_el.text.strip() if type_el is not None and type_el.text else ""

        updated_match = location_match = None
        if desc_el is not None and desc_el.text:
            updated_match = re.search(r"Updated:\s*([^\r\n]+)", desc_el.text)
            location_match = re.search(r"Location:\s*([^\r\n]+)", desc_el.text)

        lat = lon = None
        if point_el is not None and point_el.text:
            parts = point_el.text.split()
            if len(parts) == 2:
                try:
                    lat, lon = float(parts[0]), float(parts[1])
                except ValueError:
                    pass

        out.append(CanonicalAlert(
            source_key="act_esa",
            jurisdiction="ACT",
            headline=title,
            event_key=guid,
            alert_type="bushfire" if "BUSHFIRE" in incident_type.upper() else (
                "hazard_reduction" if "HAZARD REDUCTION" in incident_type.upper() else "other"
            ),
            severity="unknown",
            description=desc_el.text.strip() if desc_el is not None and desc_el.text else None,
            location=location_match.group(1).strip() if location_match else title,
            updated_at_src=_act_datetime(updated_match.group(1).strip()) if updated_match else None,
            canonical_url=f"https://esa.act.gov.au/feeds/currentincidents.xml#{guid}",
            raw_text=desc_el.text if desc_el is not None else None,
            latitude=lat,
            longitude=lon,
        ))
    return out
