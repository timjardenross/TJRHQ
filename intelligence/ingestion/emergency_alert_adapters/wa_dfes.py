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

import defusedxml.ElementTree as ET  # nosec B314 - defused parser, safe against XXE/entity-expansion on external feed XML

from .base import (
    CanonicalAlert,
    DropLedger,
    convert_items,
    http_get,
    parse_rfc822_datetime,
)

log = logging.getLogger(__name__)

_WARNINGS_URL = "https://api.emergency.wa.gov.au/v1/rss/warnings"
_INCIDENTS_URL = "https://api.emergency.wa.gov.au/v1/rss/incidents"

_DFES_NS = "{https://emergency.wa.gov.au/xmlns/dfes}"
_GEO_NS = "{https://www.w3.org/2003/01/geo/wgs84_pos#}"

_EXCLUDED_TYPE_KEYWORDS = ("BURN OFF", "HAZMAT", "FACILITY OR PARK CLOSURE", "PARK CLOSURE")

# keyword -> drop-ledger reason, same order as _EXCLUDED_TYPE_KEYWORDS ("Burn
# Off" is DFES's word for a Hazard Reduction burn; both park-closure phrasings
# are one reason). First match wins, so each dropped item is counted once.
_EXCLUDED_REASONS = (
    ("BURN OFF", "hazard_reduction"),
    ("HAZMAT", "hazmat"),
    ("FACILITY OR PARK CLOSURE", "park_closure"),
    ("PARK CLOSURE", "park_closure"),
)


def _excluded_reason(text_upper: str) -> str | None:
    return next((reason for kw, reason in _EXCLUDED_REASONS if kw in text_upper), None)

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


def parse_warnings(raw: bytes, ledger: DropLedger | None = None) -> tuple[list[CanonicalAlert], dict[str, str]]:
    """Pure parse of the warnings RSS. Returns (alerts, incident_number_to_severity)
    — the second is used by parse_incidents to enrich CAD incidents whose
    dfes:incidentNumber matches a warning already issued for the same real
    event (confirmed live 2026-08-26: WA's incidents feed has no severity
    field of its own, but some CAD-IDs do appear in the warnings feed's own
    dfes:incidentNumber, e.g. 812369/812893) — real cross-reference via a
    shared ID both feeds already carry, not an inferred value. Passing a
    ledger records every skipped item and makes one malformed item count as
    invalid_unparseable_item instead of failing the parse."""
    guard = ledger is not None
    ledger = ledger if ledger is not None else DropLedger()
    incident_severity: dict[str, str] = {}
    out = convert_items(_rss_items(raw), lambda item: _warning_to_alert(item, incident_severity, ledger), ledger, guard)
    return out, incident_severity


def _warning_to_alert(item: ET.Element, incident_severity: dict[str, str], ledger: DropLedger) -> CanonicalAlert | None:
    title_el = item.find("title")
    title = title_el.text.strip() if title_el is not None and title_el.text else "—"
    title_upper = title.upper()

    reason = _excluded_reason(title_upper)
    if reason:
        ledger.exclude(reason)
        return None

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
        # warning type, not worth a guess. (Live 2026-11: Smoke Alert and
        # Heatwave Advice warnings land here.)
        ledger.exclude("other_type")
        return None

    if severity == "unknown":
        ledger.unmapped(title.split(" - ")[0])

    guid_el = item.find("guid")
    link_el = item.find("link")
    pubdate_el = item.find("pubDate")
    region_el = item.find(f"{_DFES_NS}region")
    incident_no_el = item.find(f"{_DFES_NS}incidentNumber")
    desc_el = item.find("description")
    lat, lon = _geo(item)

    location = region_el.text.strip() if region_el is not None and region_el.text else None

    if incident_no_el is not None and incident_no_el.text:
        incident_severity[incident_no_el.text.strip()] = severity

    return CanonicalAlert(
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
    )


_INCIDENT_TITLE_RE = re.compile(r"^(?P<type>[^(]+?)\s*\((?P<rest>.*)\)$")


def parse_incidents(raw: bytes, incident_severity: dict[str, str], ledger: DropLedger | None = None) -> list[CanonicalAlert]:
    """Pure parse of the incidents RSS (bushfire CAD incidents only)."""
    guard = ledger is not None
    ledger = ledger if ledger is not None else DropLedger()
    return convert_items(_rss_items(raw), lambda item: _incident_to_alert(item, incident_severity, ledger), ledger, guard)


def _incident_to_alert(item: ET.Element, incident_severity: dict[str, str], ledger: DropLedger) -> CanonicalAlert | None:
    title_el = item.find("title")
    title = title_el.text.strip() if title_el is not None and title_el.text else "—"

    m = _INCIDENT_TITLE_RE.match(title)
    incident_type = (m.group("type").strip() if m else "").upper()

    reason = _excluded_reason(incident_type)
    if reason:
        ledger.exclude(reason)
        return None

    # region/incidentNumber/publicationTime are embedded as raw
    # (non-namespaced) tags inside the <description> CDATA on this
    # feed, not real sibling XML elements (confirmed live 2026-08-26 —
    # unlike the warnings feed's real dfes:region sibling) — extracted
    # from the title's own "(LOCATION, ..., CAD-ID: n)" tail instead,
    # which is real structured text either way.
    location = re.sub(r",?\s*CAD-ID:\s*\d+\s*$", "", m.group("rest")).strip() if m else None
    cad_id_match = re.search(r"CAD-ID:\s*(\d+)", title)
    cad_id = cad_id_match.group(1) if cad_id_match else None

    # Captain-directed exclusion, widened 2026-08-26 to also drop
    # Structure Fire — kept: bushfire only.
    if "BUSHFIRE" in incident_type:
        alert_type = "bushfire"
    else:
        ledger.exclude("not_bushfire")
        return None

    guid_el = item.find("guid")
    link_el = item.find("link")
    pubdate_el = item.find("pubDate")
    lat, lon = _geo(item)

    return CanonicalAlert(
        source_key="wa_dfes",
        jurisdiction="WA",
        headline=title,
        event_key=(guid_el.text.strip() if guid_el is not None and guid_el.text else title),
        alert_type=alert_type,
        # incidents feed has no warning-level field of its own (same
        # caveat as vic_emergency.py/act_esa.py) — enriched from the
        # matching warning's real severity when this CAD-ID also has an
        # active warning (see parse_warnings' incident_severity map).
        severity=incident_severity.get(cad_id, "unknown") if cad_id else "unknown",
        description=None,
        location=location,
        updated_at_src=parse_rfc822_datetime(pubdate_el.text.strip() if pubdate_el is not None and pubdate_el.text else None),
        canonical_url=link_el.text.strip() if link_el is not None and link_el.text else None,
        raw_text=None,
        latitude=lat,
        longitude=lon,
    )


def parse(warnings_raw: bytes, incidents_raw: bytes, ledger: DropLedger | None = None) -> list[CanonicalAlert]:
    warnings, incident_severity = parse_warnings(warnings_raw, ledger)
    return warnings + parse_incidents(incidents_raw, incident_severity, ledger)


def fetch() -> list[CanonicalAlert]:
    warnings, incident_severity = parse_warnings(http_get(_WARNINGS_URL))
    return warnings + parse_incidents(http_get(_INCIDENTS_URL), incident_severity)


def fetch_with_ledger() -> tuple[list[CanonicalAlert], DropLedger]:
    """fetch() plus an account of every item skipped across both feeds, and why."""
    ledger = DropLedger()
    warnings, incident_severity = parse_warnings(http_get(_WARNINGS_URL), ledger)
    return warnings + parse_incidents(http_get(_INCIDENTS_URL), incident_severity, ledger), ledger
