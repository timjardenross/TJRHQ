"""DFES — Emergency WA Warnings & Incidents (real public RSS, found 2026-08-26).

Supersedes the earlier scrape-tier placeholder: the retired DFES-055 point
dataset was a red herring (that's a *GIS/data.wa.gov.au* dataset, not
DFES's own consumer-facing feed). DFES publishes its own public RSS
directly, confirmed live 2026-08-26:
  - Warnings (all regions): https://api.emergency.wa.gov.au/v1/rss/warnings
  - Incidents (all regions): https://api.emergency.wa.gov.au/v1/rss/incidents
Both are real RSS 2.0 with dfes:/geo:/georss: namespaced extensions
(region, incidentNumber, publicationTime, lat/long). DFES's own FAQ notes
these feeds should supplement, not replace, primary warning channels.

Title vocabulary (confirmed live against real items):
  - warnings feed: "<AlertType> <Level> <status text> - <location>", e.g.
    "Bushfire Advice STAY INFORMED - DAMPIER PENINSULA". Level is one of
    Advice / Watch and Act / Emergency Warning (WA's AWS vocabulary) or
    General Warning (non-fire hazards, e.g. Hazmat — excluded, see below).
  - incidents feed: "<Type> (<LOCATION>, ..., CAD-ID: <n>)", e.g.
    "Bushfire (ROEBUCK, SHIRE OF BROOME, KIMBERLEY, CAD-ID: 810137)".

Captain-directed exclusions (2026-08-26, same categories dropped platform-
wide): "Burn Off" (= Hazard Reduction, planned) and "Hazmat"/"Facility or
Park Closure" (= Hazardous Materials / Other) are dropped here too, using
these feeds' own type vocabulary — not re-derived heuristically.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

from .base import CanonicalAlert, http_get, parse_rfc822_datetime

log = logging.getLogger(__name__)

_WARNINGS_URL = "https://api.emergency.wa.gov.au/v1/rss/warnings"
_INCIDENTS_URL = "https://api.emergency.wa.gov.au/v1/rss/incidents"

_DFES_NS = "{https://emergency.wa.gov.au/xmlns/dfes}"
_GEO_NS = "{https://www.w3.org/2003/01/geo/wgs84_pos#}"

_EXCLUDED_TYPE_KEYWORDS = ("BURN OFF", "HAZMAT", "FACILITY OR PARK CLOSURE", "PARK CLOSURE")

_SEVERITY_MAP = {
    "emergency warning": "emergency_warning",
    "watch and act": "watch_and_act",
    "advice": "advice",
}

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip() or None


def _rss_items(xml_bytes: bytes) -> list[ET.Element]:
    root = ET.fromstring(xml_bytes)
    return root.findall(".//item")


def _geo(item: ET.Element) -> tuple[float | None, float | None]:
    lat_el = item.find(f"{_GEO_NS}lat")
    lon_el = item.find(f"{_GEO_NS}long")
    try:
        lat = float(lat_el.text) if lat_el is not None and lat_el.text else None
        lon = float(lon_el.text) if lon_el is not None and lon_el.text else None
    except ValueError:
        lat = lon = None
    return lat, lon


def _fetch_warnings() -> list[CanonicalAlert]:
    out: list[CanonicalAlert] = []
    for item in _rss_items(http_get(_WARNINGS_URL)):
        title_el = item.find("title")
        title = title_el.text.strip() if title_el is not None and title_el.text else "—"
        title_upper = title.upper()

        if any(kw in title_upper for kw in _EXCLUDED_TYPE_KEYWORDS):
            continue

        severity = "unknown"
        for phrase, mapped in _SEVERITY_MAP.items():
            if phrase.upper() in title_upper:
                severity = mapped
                break

        alert_type = "bushfire" if "BUSHFIRE" in title_upper else (
            "storm" if "STORM" in title_upper else (
                "cyclone" if "CYCLONE" in title_upper else (
                    "flood" if "FLOOD" in title_upper else "other"
                )
            )
        )
        if alert_type == "other":
            # Not one of the categories this hub wants (matches the
            # platform-wide "Other" exclusion) — genuinely unclassifiable
            # warning type, not worth a guess.
            continue

        guid_el = item.find("guid")
        link_el = item.find("link")
        pubdate_el = item.find("pubDate")
        region_el = item.find(f"{_DFES_NS}region")
        desc_el = item.find("description")
        lat, lon = _geo(item)

        location = region_el.text.strip() if region_el is not None and region_el.text else None

        out.append(CanonicalAlert(
            source_key="wa_dfes",
            jurisdiction="WA",
            headline=title,
            event_key=(guid_el.text.strip() if guid_el is not None and guid_el.text else title),
            alert_type=alert_type,
            severity=severity,
            description=_strip_html(desc_el.text if desc_el is not None else None),
            location=location,
            updated_at_src=parse_rfc822_datetime(pubdate_el.text.strip() if pubdate_el is not None and pubdate_el.text else None),
            canonical_url=link_el.text.strip() if link_el is not None and link_el.text else None,
            raw_text=_strip_html(desc_el.text if desc_el is not None else None),
            latitude=lat,
            longitude=lon,
        ))
    return out


_INCIDENT_TITLE_RE = re.compile(r"^(?P<type>[^(]+?)\s*\((?P<rest>.*)\)$")


def _fetch_incidents() -> list[CanonicalAlert]:
    out: list[CanonicalAlert] = []
    for item in _rss_items(http_get(_INCIDENTS_URL)):
        title_el = item.find("title")
        title = title_el.text.strip() if title_el is not None and title_el.text else "—"

        m = _INCIDENT_TITLE_RE.match(title)
        incident_type = (m.group("type").strip() if m else "").upper()

        if any(kw in incident_type for kw in _EXCLUDED_TYPE_KEYWORDS):
            continue

        # region/incidentNumber/publicationTime are embedded as raw
        # (non-namespaced) tags inside the <description> CDATA on this
        # feed, not real sibling XML elements (confirmed live 2026-08-26 —
        # unlike the warnings feed's real dfes:region sibling) — extracted
        # from the title's own "(LOCATION, ..., CAD-ID: n)" tail instead,
        # which is real structured text either way.
        location = re.sub(r",?\s*CAD-ID:\s*\d+\s*$", "", m.group("rest")).strip() if m else None

        if "STRUCTURE FIRE" in incident_type:
            alert_type = "structure_fire"
        elif "BUSHFIRE" in incident_type:
            alert_type = "bushfire"
        else:
            # Anything not bushfire/structure fire (Vehicle Fire, Rescue,
            # etc.) matches the platform-wide "Other" exclusion.
            continue

        guid_el = item.find("guid")
        link_el = item.find("link")
        pubdate_el = item.find("pubDate")
        lat, lon = _geo(item)

        out.append(CanonicalAlert(
            source_key="wa_dfes",
            jurisdiction="WA",
            headline=title,
            event_key=(guid_el.text.strip() if guid_el is not None and guid_el.text else title),
            alert_type=alert_type,
            severity="unknown",  # incidents feed is CAD data, no warning-level field — same caveat as vic_emergency.py/act_esa.py
            description=None,
            location=location,
            updated_at_src=parse_rfc822_datetime(pubdate_el.text.strip() if pubdate_el is not None and pubdate_el.text else None),
            canonical_url=link_el.text.strip() if link_el is not None and link_el.text else None,
            raw_text=None,
            latitude=lat,
            longitude=lon,
        ))
    return out


def fetch() -> list[CanonicalAlert]:
    return _fetch_warnings() + _fetch_incidents()
