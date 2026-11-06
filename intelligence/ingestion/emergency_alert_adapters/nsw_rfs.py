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

from . import nsw_rfs_cap
from .base import (
    CanonicalAlert,
    DropLedger,
    convert_items,
    http_get_json,
    json_items,
    parse_dmy_datetime,
)

log = logging.getLogger(__name__)

_FEED_URL = "https://www.rfs.nsw.gov.au/feeds/majorIncidents.json"

_SEVERITY_MAP = {
    "advice": "advice",
    "watch and act": "watch_and_act",
    "emergency warning": "emergency_warning",
}

SOURCE_INFO = {
    "source_key": "nsw_rfs",
    "jurisdiction": "NSW",
    "feed_urls": [_FEED_URL, nsw_rfs_cap._CAP_URL],
    "format": "GeoJSON FeatureCollection (primary) + CAP-AU 1.2 in an EDXL-DE wrapper (enrichment: event, urgency, certainty, severity)",
    "fixture_dir": "tests/fixtures/emergency_alerts/nsw_rfs",
    "severity_field": "properties.category (Advice / Watch and Act / Emergency Warning)",
    "severity_map": _SEVERITY_MAP,
    "alert_type_rule": "Always 'bushfire' (Major Incidents feed).",
    "exclusions": [
        {"reason": "excluded_hazard_reduction", "field": "properties.description TYPE", "match": "== 'Hazard Reduction'", "decided": "Captain-directed 2026-08-26"},
        {"reason": "excluded_not_applicable", "field": "properties.category", "match": "== 'Not Applicable' (case-insensitive)", "decided": "2026-08-26, same class as QLD 'Information' (Captain-directed)"},
    ],
    "invalid_reasons": [],
    "stale_after_hours": 72,
    "expected_fields": ['updated_at_src', 'canonical_url', 'cap_urgency'],
    "known_gaps": [
        "CAP fields come from majorIncidentsCAP.xml (nsw_rfs_cap.py), joined on the RFS incident id. They are an enrichment only: the GeoJSON decides which alerts exist and their tier. If the CAP feed is down the alerts are kept without CAP fields and a FIELD DRIFT warning (cap_urgency missing on every alert) is raised. The CAP feed has no tier mapping of its own that we use: its severity/urgency are stored as given (cap_severity is not the AWS tier).",
        "Timestamps (properties.pubDate) are DD/MM/YYYY H:MM:SS AM/PM with no timezone/offset. MEASURED 2026-11-06 against stored rows: they behave as UTC (no row ahead of the time it was seen; freshest ~0.1 h old), so they are stored as written. If NSW ever starts sending local time this would show as rows hours in the future.",
        "A category label outside Advice / Watch and Act / Emergency Warning / Not Applicable is kept at severity 'unknown' and counted as unmapped_<label>.",
    ],
    "last_verified": "2026-08-26",
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
    alerts = parse(http_get_json(_FEED_URL))
    nsw_rfs_cap.enrich(alerts)
    return alerts


def fetch_with_ledger() -> tuple[list[CanonicalAlert], DropLedger]:
    """fetch() plus an account of every item skipped, and why (see base.DropLedger)."""
    ledger = DropLedger()
    alerts = parse(http_get_json(_FEED_URL), ledger)
    nsw_rfs_cap.enrich(alerts)  # best effort: CAP fields only; never changes which alerts exist
    return alerts, ledger


def parse(data: dict, ledger: DropLedger | None = None) -> list[CanonicalAlert]:
    """Pure parse of the Major Incidents GeoJSON FeatureCollection; separate
    from fetch() so it can be tested against a captured snapshot offline.
    Passing a ledger records every skipped item and makes one malformed
    feature count as invalid_unparseable_item instead of failing the parse."""
    guard = ledger is not None
    ledger = ledger if ledger is not None else DropLedger()
    return convert_items(json_items(data, "features", "nsw_rfs", guard), lambda feature: _to_alert(feature, ledger), ledger, guard)


def _to_alert(feature: dict, ledger: DropLedger) -> CanonicalAlert | None:
    props = feature.get("properties", {}) or {}
    title = props.get("title") or "—"
    guid = props.get("guid")
    category = (props.get("category") or "").strip().lower()
    fields = _parse_description_fields(props.get("description") or "")
    updated_at_src = parse_dmy_datetime(props.get("pubDate"))
    ledger.observe(updated_at_src)

    # Captain-directed exclusion 2026-08-26: Hazard Reduction / prescribed
    # burns are planned, not emergencies — drop at the source rather than
    # filtering downstream, using NSW RFS's own TYPE field (confirmed
    # live: "Hazard Reduction" vs "Bush Fire"), not a title-text guess.
    if fields.get("TYPE") == "Hazard Reduction":
        ledger.exclude("hazard_reduction", sample=title)
        return None

    # Found 2026-08-26 investigating why so many NSW rows sat at
    # severity=unknown: NSW RFS has a real 4th tier below its own
    # Advice/Watch and Act/Emergency Warning vocabulary —
    # category="Not Applicable" (confirmed live) — same "FYI, not a
    # real warning" class as QLD's WarningLevel="Information", already
    # excluded above. Drop it here too rather than let it sit as an
    # unclassifiable "unknown"-severity row.
    if category == "not applicable":
        ledger.exclude("not_applicable", sample=title)
        return None

    lat = lon = None
    geom = feature.get("geometry") or {}
    if geom.get("type") == "GeometryCollection":
        for g in geom.get("geometries", []):
            if g.get("type") == "Point":
                lon, lat = g["coordinates"][0], g["coordinates"][1]
                break

    severity = _SEVERITY_MAP.get(category)
    if severity is None:
        ledger.unmapped(category or "blank")
        severity = "unknown"

    return CanonicalAlert(
        source_key="nsw_rfs",
        jurisdiction="NSW",
        headline=title,
        event_key=guid or title,
        alert_type="bushfire",
        severity=severity,
        description=fields.get("STATUS") and f"{fields.get('TYPE', 'Bush Fire')} — {fields['STATUS']}" or None,
        location=fields.get("LOCATION") or title,
        issued_at=None,  # pubDate is last-update, not first-issued; see updated_at_src
        updated_at_src=updated_at_src,
        canonical_url=guid or props.get("link"),
        raw_text=props.get("description"),
        latitude=lat,
        longitude=lon,
    )
